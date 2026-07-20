from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Item, ItemSource, OperationTask, SourceCheckFact, TaskEvent
from app.source_search import ProviderSearchService, VideoDetailRequest
from app.tasks import PersistentTaskService, TaskState, TaskType

MANUAL_UPDATE_FIELDS = (
    "item.summary",
    "item.release_date",
    "item_source.title",
    "item_source.last_checked_at",
    "item_source.metadata_hash",
)
_FIELD_SET = frozenset(MANUAL_UPDATE_FIELDS)
_FORMAT = "nsfwtrack.manual-update.v1"
_TOKEN_PREFIX = "u1"
_MAX_TTL_SECONDS = 1_800


class ManualUpdateErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    SOURCE_NOT_AVAILABLE = "source_not_available"
    PROVIDER_FAILED = "provider_failed"
    CHECK_EXPIRED = "check_expired"
    NOTHING_TO_APPLY = "nothing_to_apply"
    STALE_PLAN = "stale_plan"
    WRITE_FAILED = "write_failed"
    OUTCOME_UNKNOWN = "outcome_unknown"


class ManualUpdateError(RuntimeError):
    def __init__(self, code: ManualUpdateErrorCode) -> None:
        if not isinstance(code, ManualUpdateErrorCode):
            raise TypeError("code must be ManualUpdateErrorCode")
        self.code = code
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value


def _raise(code: ManualUpdateErrorCode) -> None:
    raise ManualUpdateError(code)


def _now() -> datetime:
    return datetime.now(UTC)


def _datetime_text(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def _item_snapshot(item: Item) -> str:
    raw = [item.id, item.title, item.summary, item.release_date, _datetime_text(item.updated_at)]
    return hashlib.sha256(json.dumps(raw, separators=(",", ":")).encode()).hexdigest()


def _source_snapshot(source: ItemSource) -> str:
    raw = [
        source.id,
        source.item_id,
        source.title,
        source.provider_key,
        hashlib.sha256((source.external_id or "").encode()).hexdigest(),
        _datetime_text(source.last_checked_at),
        source.metadata_hash,
    ]
    return hashlib.sha256(json.dumps(raw, separators=(",", ":")).encode()).hexdigest()


def _projection_hash(values: dict[str, str | None]) -> str:
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def execute_source_check(
    db: Session,
    service: ProviderSearchService,
    *,
    item_id: int,
    source_id: int,
    max_concurrency: int,
    result_ttl_seconds: int = 900,
) -> OperationTask:
    if not isinstance(db, Session) or not isinstance(service, ProviderSearchService):
        _raise(ManualUpdateErrorCode.INVALID_REQUEST)
    source = db.scalar(
        select(ItemSource).where(ItemSource.id == source_id, ItemSource.item_id == item_id)
    )
    item = db.get(Item, item_id)
    if (
        source is None
        or item is None
        or source.provider_key is None
        or source.external_id is None
        or not 30 <= result_ttl_seconds <= _MAX_TTL_SECONDS
    ):
        _raise(ManualUpdateErrorCode.SOURCE_NOT_AVAILABLE)
    tasks = PersistentTaskService(db, max_concurrency=max_concurrency)
    task, _created = tasks.create(
        task_type=TaskType.SOURCE_CHECK,
        intent_key=f"source-check:{source_id}:{secrets.token_hex(16)}",
        initial_state=TaskState.QUEUED,
        item_id=item_id,
        source_id=source_id,
        provider_key=source.provider_key,
        external_identity=source.external_id,
        snapshot_hash=_source_snapshot(source),
    )
    task = tasks.transition(
        task.id,
        TaskState.RUNNING,
        expected_version=task.version,
        event_type="source_check_started",
    )
    db.commit()
    try:
        # This is the only Provider operation in the Check flow. There is no
        # search, asset listing, or download call before or after it.
        envelope = await service.detail(
            VideoDetailRequest(source.provider_key, source.external_id)
        )
        received_at = envelope.received_at.astimezone(UTC)
        values = {
            "summary": envelope.detail.summary,
            "release_date": (
                envelope.detail.release_date.isoformat()
                if envelope.detail.release_date is not None
                else None
            ),
            "source_title": envelope.detail.title,
            "checked_at": received_at.isoformat(),
        }
        detail_hash = _projection_hash(values)
        db.add(
            SourceCheckFact(
                task_id=task.id,
                item_snapshot_hash=_item_snapshot(item),
                source_snapshot_hash=_source_snapshot(source),
                detail_hash=detail_hash,
                proposed_summary=values["summary"],
                proposed_release_date=values["release_date"],
                proposed_source_title=values["source_title"],
                proposed_checked_at=received_at,
                proposed_metadata_hash=detail_hash,
                expires_at=_now() + timedelta(seconds=result_ttl_seconds),
            )
        )
        task = tasks.transition(
            task.id,
            TaskState.SUCCEEDED,
            expected_version=task.version,
            event_type="source_check_succeeded",
        )
        db.commit()
        return task
    except Exception as error:
        db.rollback()
        task = tasks.get(task.id)
        if task.state == TaskState.RUNNING.value:
            tasks.transition(
                task.id,
                TaskState.FAILED,
                expected_version=task.version,
                event_type="source_check_failed",
                error_code="provider_failed",
            )
            db.commit()
        if isinstance(error, ManualUpdateError):
            raise
        _raise(ManualUpdateErrorCode.PROVIDER_FAILED)


@dataclass(frozen=True, slots=True, repr=False)
class ManualFieldChange:
    field: str
    old: str | None
    new: str | None

    def __post_init__(self) -> None:
        if self.field not in _FIELD_SET:
            raise ValueError("field is not allowed")
        for value in (self.old, self.new):
            if value is not None and (not isinstance(value, str) or len(value) > 20_000):
                raise ValueError("field value is invalid")


@dataclass(frozen=True, slots=True, repr=False)
class ManualUpdatePlan:
    format: str
    check_task_id: int
    item_id: int
    source_id: int
    provider_key: str
    item_snapshot_hash: str
    source_snapshot_hash: str
    selected: tuple[ManualFieldChange, ...]
    detail_hash: str

    def __post_init__(self) -> None:
        if self.format != _FORMAT:
            raise ValueError("format is invalid")
        if any(not isinstance(value, int) or value < 1 for value in (self.check_task_id, self.item_id, self.source_id)):
            raise ValueError("identity is invalid")
        if not isinstance(self.selected, tuple) or not self.selected:
            raise ValueError("selected fields are required")
        if len({change.field for change in self.selected}) != len(self.selected):
            raise ValueError("selected fields contain duplicates")

    def __repr__(self) -> str:
        return "ManualUpdatePlan()"


def build_manual_update_plan(
    db: Session,
    *,
    check_task_id: int,
    selected_fields: tuple[str, ...],
    now: datetime | None = None,
) -> ManualUpdatePlan:
    if not isinstance(selected_fields, tuple) or any(field not in _FIELD_SET for field in selected_fields):
        _raise(ManualUpdateErrorCode.INVALID_REQUEST)
    task = db.get(OperationTask, check_task_id)
    fact = db.get(SourceCheckFact, check_task_id)
    if task is None or fact is None or task.state != TaskState.SUCCEEDED.value:
        _raise(ManualUpdateErrorCode.INVALID_REQUEST)
    checked_at = (now or _now()).astimezone(UTC)
    if checked_at >= fact.expires_at:
        _raise(ManualUpdateErrorCode.CHECK_EXPIRED)
    item = db.get(Item, task.item_id)
    source = db.get(ItemSource, task.source_id)
    if item is None or source is None or _item_snapshot(item) != fact.item_snapshot_hash or _source_snapshot(source) != fact.source_snapshot_hash:
        _raise(ManualUpdateErrorCode.STALE_PLAN)
    values = {
        "item.summary": (item.summary, fact.proposed_summary),
        "item.release_date": (item.release_date, fact.proposed_release_date),
        "item_source.title": (source.title, fact.proposed_source_title),
        "item_source.last_checked_at": (
            _datetime_text(source.last_checked_at),
            _datetime_text(fact.proposed_checked_at),
        ),
        "item_source.metadata_hash": (source.metadata_hash, fact.proposed_metadata_hash),
    }
    changes: list[ManualFieldChange] = []
    for field in MANUAL_UPDATE_FIELDS:
        if field not in selected_fields:
            continue
        old, new = values[field]
        # Provider emptiness is never authority to clear local data.
        if new is None and old not in {None, ""}:
            continue
        if old != new:
            changes.append(ManualFieldChange(field, old, new))
    if not changes:
        _raise(ManualUpdateErrorCode.NOTHING_TO_APPLY)
    try:
        return ManualUpdatePlan(
            format=_FORMAT,
            check_task_id=task.id,
            item_id=item.id,
            source_id=source.id,
            provider_key=task.provider_key or "",
            item_snapshot_hash=fact.item_snapshot_hash,
            source_snapshot_hash=fact.source_snapshot_hash,
            selected=tuple(changes),
            detail_hash=fact.detail_hash,
        )
    except (TypeError, ValueError):
        _raise(ManualUpdateErrorCode.INVALID_REQUEST)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (TypeError, ValueError):
        _raise(ManualUpdateErrorCode.INVALID_REQUEST)


def sign_manual_update_plan(
    plan: ManualUpdatePlan,
    *,
    secret: bytes,
    context: str,
    now: datetime,
    ttl_seconds: int = 600,
) -> str:
    if type(plan) is not ManualUpdatePlan or len(secret) < 32 or not context or not 1 <= ttl_seconds <= _MAX_TTL_SECONDS:
        _raise(ManualUpdateErrorCode.INVALID_REQUEST)
    issued = now.astimezone(UTC)
    raw_plan = asdict(plan)
    raw_plan["selected"] = [asdict(change) for change in plan.selected]
    payload = json.dumps(
        {
            "format": _FORMAT,
            "issued_at": issued.isoformat(),
            "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
            "context_hash": hashlib.sha256(context.encode()).hexdigest(),
            "plan": raw_plan,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    segment = _b64(payload)
    signature = _b64(hmac.new(secret, b"nsfwtrack-update\0" + segment.encode(), hashlib.sha256).digest())
    return f"{_TOKEN_PREFIX}.{segment}.{signature}"


def verify_manual_update_token(token: str, *, secret: bytes, context: str, now: datetime) -> ManualUpdatePlan:
    try:
        prefix, segment, signature = token.split(".")
    except (AttributeError, ValueError):
        _raise(ManualUpdateErrorCode.INVALID_REQUEST)
    if prefix != _TOKEN_PREFIX or len(token) > 64_000:
        _raise(ManualUpdateErrorCode.INVALID_REQUEST)
    expected = hmac.new(secret, b"nsfwtrack-update\0" + segment.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _unb64(signature)):
        _raise(ManualUpdateErrorCode.INVALID_REQUEST)
    try:
        document = json.loads(_unb64(segment))
        if document["format"] != _FORMAT:
            raise ValueError
        checked = now.astimezone(UTC)
        issued = datetime.fromisoformat(document["issued_at"]).astimezone(UTC)
        expires = datetime.fromisoformat(document["expires_at"]).astimezone(UTC)
        if checked < issued or checked >= expires or expires - issued > timedelta(seconds=_MAX_TTL_SECONDS):
            raise ValueError
        if not hmac.compare_digest(document["context_hash"], hashlib.sha256(context.encode()).hexdigest()):
            raise ValueError
        raw = document["plan"]
        raw["selected"] = tuple(ManualFieldChange(**value) for value in raw["selected"])
        return ManualUpdatePlan(**raw)
    except (KeyError, TypeError, ValueError, OverflowError):
        _raise(ManualUpdateErrorCode.INVALID_REQUEST)


@dataclass(frozen=True, slots=True)
class ManualUpdateResult:
    task_id: int
    written_fields: tuple[str, ...]
    commit_status: str


class _IndependentManualVerificationFailed(RuntimeError):
    pass


def _manual_intent_key(plan: ManualUpdatePlan) -> str:
    material = json.dumps(asdict(plan), sort_keys=True, default=str).encode()
    return f"metadata-update:{hashlib.sha256(material).hexdigest()}"


def _item_proof_values(item: Item) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "cover_path": item.cover_path,
        "summary": item.summary,
        "release_date": item.release_date,
        "extra": item.extra,
        "created_at": item.created_at,
    }


def _source_proof_values(source: ItemSource) -> dict[str, object]:
    return {
        "id": source.id,
        "item_id": source.item_id,
        "url": source.url,
        "normalized_url": source.normalized_url,
        "title": source.title,
        "provider_key": source.provider_key,
        "external_id": source.external_id,
        "last_checked_at": source.last_checked_at,
        "metadata_hash": source.metadata_hash,
        "created_at": source.created_at,
    }


def _expected_manual_values(
    plan: ManualUpdatePlan,
    *,
    pre_item: dict[str, object],
    pre_source: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    expected_item = dict(pre_item)
    expected_source = dict(pre_source)
    for change in plan.selected:
        if change.field == "item.summary":
            expected_item["summary"] = change.new
        elif change.field == "item.release_date":
            expected_item["release_date"] = change.new
        elif change.field == "item_source.title":
            expected_source["title"] = change.new
        elif change.field == "item_source.last_checked_at":
            expected_source["last_checked_at"] = datetime.fromisoformat(change.new or "")
        elif change.field == "item_source.metadata_hash":
            expected_source["metadata_hash"] = change.new
    return expected_item, expected_source


def _verify_manual_update_state(
    bind: object,
    *,
    plan: ManualUpdatePlan,
    task_id: int,
    expected_state: TaskState,
    expected_stage: str,
    expected_version: int,
    pre_item: dict[str, object],
    pre_source: dict[str, object],
) -> None:
    expected_item, expected_source = _expected_manual_values(
        plan,
        pre_item=pre_item,
        pre_source=pre_source,
    )
    intent_key = _manual_intent_key(plan)
    try:
        with Session(bind=bind) as verification:
            item = verification.get(Item, plan.item_id)
            source = verification.get(ItemSource, plan.source_id)
            tasks = tuple(
                verification.scalars(
                    select(OperationTask).where(OperationTask.intent_key == intent_key)
                ).all()
            )
            if (
                item is None
                or source is None
                or _item_proof_values(item) != expected_item
                or _source_proof_values(source) != expected_source
                or len(tasks) != 1
                or tasks[0].id != task_id
            ):
                raise _IndependentManualVerificationFailed
            task = tasks[0]
            if (
                task.task_type != TaskType.METADATA_UPDATE.value
                or task.state != expected_state.value
                or task.stage != expected_stage
                or task.version != expected_version
                or task.item_id != plan.item_id
                or task.source_id != plan.source_id
                or task.provider_key != plan.provider_key
                or task.snapshot_hash != plan.detail_hash
                or task.external_identity_hash is not None
                or task.asset_identity_hash is not None
                or task.relative_target is not None
            ):
                raise _IndependentManualVerificationFailed
            events = tuple(
                verification.scalars(
                    select(TaskEvent)
                    .where(TaskEvent.task_id == task_id)
                    .order_by(TaskEvent.version)
                ).all()
            )
            expected_events = (
                ("created", "metadata_apply_started")
                if expected_state is TaskState.RUNNING
                else ("created", "metadata_apply_started", "metadata_apply_succeeded")
            )
            if tuple(event.event_type for event in events) != expected_events:
                raise _IndependentManualVerificationFailed
            fact = verification.get(SourceCheckFact, plan.check_task_id)
            check_task = verification.get(OperationTask, plan.check_task_id)
            if (
                fact is None
                or check_task is None
                or check_task.state != TaskState.SUCCEEDED.value
                or fact.detail_hash != plan.detail_hash
                or fact.item_snapshot_hash != plan.item_snapshot_hash
                or fact.source_snapshot_hash != plan.source_snapshot_hash
            ):
                raise _IndependentManualVerificationFailed
    except _IndependentManualVerificationFailed:
        raise
    except Exception as error:
        raise _IndependentManualVerificationFailed from error


def _verify_manual_pre_state(
    bind: object,
    *,
    plan: ManualUpdatePlan,
    pre_item: dict[str, object],
    pre_source: dict[str, object],
) -> None:
    try:
        with Session(bind=bind) as verification:
            item = verification.get(Item, plan.item_id)
            source = verification.get(ItemSource, plan.source_id)
            count = verification.scalar(
                select(func.count())
                .select_from(OperationTask)
                .where(OperationTask.intent_key == _manual_intent_key(plan))
            )
            if (
                item is None
                or source is None
                or _item_proof_values(item) != pre_item
                or _source_proof_values(source) != pre_source
                or int(count or 0) != 0
            ):
                raise _IndependentManualVerificationFailed
    except _IndependentManualVerificationFailed:
        raise
    except Exception as error:
        raise _IndependentManualVerificationFailed from error


def _verify_manual_replay(
    bind: object,
    *,
    plan: ManualUpdatePlan,
    task_id: int,
) -> None:
    changes = {change.field: change.new for change in plan.selected}
    try:
        with Session(bind=bind) as verification:
            item = verification.get(Item, plan.item_id)
            source = verification.get(ItemSource, plan.source_id)
            tasks = tuple(
                verification.scalars(
                    select(OperationTask).where(
                        OperationTask.intent_key == _manual_intent_key(plan)
                    )
                ).all()
            )
            if item is None or source is None or len(tasks) != 1 or tasks[0].id != task_id:
                raise _IndependentManualVerificationFailed
            task = tasks[0]
            if (
                task.state != TaskState.SUCCEEDED.value
                or task.stage != "committed_verified"
                or task.snapshot_hash != plan.detail_hash
                or task.item_id != plan.item_id
                or task.source_id != plan.source_id
                or task.provider_key != plan.provider_key
            ):
                raise _IndependentManualVerificationFailed
            actual = {
                "item.summary": item.summary,
                "item.release_date": item.release_date,
                "item_source.title": source.title,
                "item_source.last_checked_at": _datetime_text(source.last_checked_at),
                "item_source.metadata_hash": source.metadata_hash,
            }
            if any(actual[field] != value for field, value in changes.items()):
                raise _IndependentManualVerificationFailed
            event_count = verification.scalar(
                select(func.count()).select_from(TaskEvent).where(TaskEvent.task_id == task_id)
            )
            if int(event_count or 0) != 3:
                raise _IndependentManualVerificationFailed
    except _IndependentManualVerificationFailed:
        raise
    except Exception as error:
        raise _IndependentManualVerificationFailed from error


def apply_manual_update(
    db: Session,
    *,
    plan: ManualUpdatePlan,
    max_concurrency: int,
) -> ManualUpdateResult:
    if db.new or db.dirty or db.deleted:
        _raise(ManualUpdateErrorCode.INVALID_REQUEST)
    if db.in_transaction():
        db.rollback()
    try:
        if db.get_bind().dialect.name == "sqlite":
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    except Exception:
        db.rollback()
        _raise(ManualUpdateErrorCode.WRITE_FAILED)
    written_fields = tuple(change.field for change in plan.selected)
    intent_key = _manual_intent_key(plan)
    tasks = PersistentTaskService(db, max_concurrency=max_concurrency)
    existing = db.scalar(
        select(OperationTask).where(OperationTask.intent_key == intent_key)
    )
    if existing is not None:
        existing_id = existing.id
        if existing.state != TaskState.SUCCEEDED.value:
            db.rollback()
            _raise(ManualUpdateErrorCode.STALE_PLAN)
        db.rollback()
        try:
            _verify_manual_replay(db.get_bind(), plan=plan, task_id=existing_id)
        except _IndependentManualVerificationFailed:
            _raise(ManualUpdateErrorCode.OUTCOME_UNKNOWN)
        return ManualUpdateResult(
            existing_id,
            written_fields,
            "already_applied_verified",
        )

    item = db.get(Item, plan.item_id)
    source = db.get(ItemSource, plan.source_id)
    fact = db.get(SourceCheckFact, plan.check_task_id)
    if (
        item is None
        or source is None
        or fact is None
        or _item_snapshot(item) != plan.item_snapshot_hash
        or _source_snapshot(source) != plan.source_snapshot_hash
        or fact.detail_hash != plan.detail_hash
    ):
        db.rollback()
        _raise(ManualUpdateErrorCode.STALE_PLAN)
    pre_item = _item_proof_values(item)
    pre_source = _source_proof_values(source)
    task, created = tasks.create(
        task_type=TaskType.METADATA_UPDATE,
        intent_key=intent_key,
        initial_state=TaskState.QUEUED,
        item_id=plan.item_id,
        source_id=plan.source_id,
        provider_key=plan.provider_key,
        snapshot_hash=plan.detail_hash,
    )
    if not created:
        db.rollback()
        _raise(ManualUpdateErrorCode.STALE_PLAN)
    task = tasks.transition(
        task.id,
        TaskState.RUNNING,
        expected_version=task.version,
        event_type="metadata_apply_started",
    )
    task_id = task.id
    written_version = task.version
    changes = {change.field: change.new for change in plan.selected}
    item_values: dict[str, str | None] = {}
    source_values: dict[str, object] = {}
    if "item.summary" in changes:
        item_values["summary"] = changes["item.summary"]
    if "item.release_date" in changes:
        item_values["release_date"] = changes["item.release_date"]
    if "item_source.title" in changes:
        source_values["title"] = changes["item_source.title"]
    if "item_source.last_checked_at" in changes:
        source_values["last_checked_at"] = datetime.fromisoformat(changes["item_source.last_checked_at"] or "")
    if "item_source.metadata_hash" in changes:
        source_values["metadata_hash"] = changes["item_source.metadata_hash"]
    try:
        if item_values:
            result = db.execute(
                update(Item)
                .where(Item.id == item.id, Item.title == item.title)
                .values(**item_values)
            )
            if result.rowcount != 1:
                _raise(ManualUpdateErrorCode.STALE_PLAN)
        if source_values:
            result = db.execute(
                update(ItemSource)
                .where(
                    ItemSource.id == source.id,
                    ItemSource.provider_key == source.provider_key,
                    ItemSource.external_id == source.external_id,
                    ItemSource.title.is_(source.title) if source.title is None else ItemSource.title == source.title,
                    ItemSource.last_checked_at.is_(source.last_checked_at) if source.last_checked_at is None else ItemSource.last_checked_at == source.last_checked_at,
                    ItemSource.metadata_hash.is_(source.metadata_hash) if source.metadata_hash is None else ItemSource.metadata_hash == source.metadata_hash,
                )
                .values(**source_values)
            )
            if result.rowcount != 1:
                _raise(ManualUpdateErrorCode.STALE_PLAN)
        task.stage = "written"
        db.commit()
    except ManualUpdateError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        try:
            _verify_manual_update_state(
                db.get_bind(),
                plan=plan,
                task_id=task_id,
                expected_state=TaskState.RUNNING,
                expected_stage="written",
                expected_version=written_version,
                pre_item=pre_item,
                pre_source=pre_source,
            )
        except _IndependentManualVerificationFailed:
            try:
                _verify_manual_pre_state(
                    db.get_bind(),
                    plan=plan,
                    pre_item=pre_item,
                    pre_source=pre_source,
                )
            except _IndependentManualVerificationFailed:
                _raise(ManualUpdateErrorCode.OUTCOME_UNKNOWN)
            _raise(ManualUpdateErrorCode.WRITE_FAILED)

    try:
        _verify_manual_update_state(
            db.get_bind(),
            plan=plan,
            task_id=task_id,
            expected_state=TaskState.RUNNING,
            expected_stage="written",
            expected_version=written_version,
            pre_item=pre_item,
            pre_source=pre_source,
        )
    except _IndependentManualVerificationFailed:
        try:
            _verify_manual_pre_state(
                db.get_bind(),
                plan=plan,
                pre_item=pre_item,
                pre_source=pre_source,
            )
        except _IndependentManualVerificationFailed:
            _raise(ManualUpdateErrorCode.OUTCOME_UNKNOWN)
        else:
            _raise(ManualUpdateErrorCode.WRITE_FAILED)

    db.expire_all()
    task = tasks.get(task_id)
    try:
        task = tasks.transition(
            task.id,
            TaskState.SUCCEEDED,
            expected_version=task.version,
            event_type="metadata_apply_succeeded",
        )
        task.stage = "committed_verified"
        success_version = task.version
        db.commit()
    except Exception:
        db.rollback()
        success_version = written_version + 1

    try:
        _verify_manual_update_state(
            db.get_bind(),
            plan=plan,
            task_id=task_id,
            expected_state=TaskState.SUCCEEDED,
            expected_stage="committed_verified",
            expected_version=success_version,
            pre_item=pre_item,
            pre_source=pre_source,
        )
        return ManualUpdateResult(task_id, written_fields, "committed_verified")
    except _IndependentManualVerificationFailed:
        try:
            _verify_manual_update_state(
                db.get_bind(),
                plan=plan,
                task_id=task_id,
                expected_state=TaskState.RUNNING,
                expected_stage="written",
                expected_version=written_version,
                pre_item=pre_item,
                pre_source=pre_source,
            )
        except _IndependentManualVerificationFailed:
            try:
                db.expire_all()
                current = tasks.get(task_id)
                if (
                    current.state == TaskState.SUCCEEDED.value
                    and current.stage == "committed_verified"
                    and current.version == success_version
                ):
                    tasks.mark_verification_unknown(
                        task_id,
                        expected_version=success_version,
                        expected_stage="committed_verified",
                        event_type="metadata_verification_unknown",
                    )
                    db.commit()
            except Exception:
                db.rollback()
            _raise(ManualUpdateErrorCode.OUTCOME_UNKNOWN)
        _raise(ManualUpdateErrorCode.WRITE_FAILED)
