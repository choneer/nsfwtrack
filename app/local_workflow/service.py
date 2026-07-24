from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Item, ItemLocalAsset, ItemSource, MediaIndexEntry, MediaIndexState, OperationTask
from app.services import local_media
from app.services.media_index import invalidate_media_index, refresh_media_index
from app.services.media_operation_lock import media_operation_lock
from app.tasks import PersistentTaskService, TaskState, TaskTransitionError, TaskType

LOCAL_PROVIDER = "local_media"
INTEGRITY_PROVIDER = "local_integrity"
INDEX_PROVIDER = "local_index"
RECOVERY_PROVIDER = "local_recovery"
PLAN_FORMAT = "nsfwtrack.local-import.v1"
MAX_PLAN_FILES = 100
MAX_PLAN_TTL_SECONDS = 1_800
_TOKEN_PREFIX = "li1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class LocalWorkflowError(RuntimeError):
    """Stable, non-secret local workflow failure."""

    def __init__(self, code: str) -> None:
        self.code = code if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code or "") else "operation_failed"
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class LocalFileFact:
    relative_path: str
    size_bytes: int
    sha256: str
    mime_type: str
    device: int
    inode: int
    modified_ns: int
    changed_ns: int

    def __post_init__(self) -> None:
        normalized = local_media.normalize_local_media_path(f"/media/{self.relative_path}")
        if (
            normalized != f"/media/{self.relative_path}"
            or not self.mime_type
            or self.size_bytes < 0
            or _SHA256.fullmatch(self.sha256) is None
            or min(self.device, self.inode, self.modified_ns, self.changed_ns) < 0
        ):
            raise ValueError("invalid local file fact")

    @property
    def snapshot_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class LocalImportPlan:
    format: str
    item_id: int
    source_id: int | None
    files: tuple[LocalFileFact, ...]

    def __post_init__(self) -> None:
        if (
            self.format != PLAN_FORMAT
            or not isinstance(self.item_id, int)
            or self.item_id < 1
            or (self.source_id is not None and self.source_id < 1)
            or not 1 <= len(self.files) <= MAX_PLAN_FILES
            or len({fact.relative_path for fact in self.files}) != len(self.files)
        ):
            raise ValueError("invalid local import plan")


@dataclass(frozen=True, slots=True)
class LocalImportPreview:
    plan: LocalImportPlan
    duplicates: tuple[str, ...]

    @property
    def confirmable(self) -> bool:
        return bool(self.plan.files)


def _entry_fact(entry: local_media.LocalMediaEntry) -> LocalFileFact:
    if (
        not entry.available
        or not entry.mime_type
        or entry.device is None
        or entry.inode is None
        or entry.modified_ns is None
        or entry.changed_ns is None
    ):
        raise LocalWorkflowError("media_invalid")
    return LocalFileFact(
        relative_path=entry.media_path.removeprefix(local_media.LOCAL_MEDIA_PREFIX),
        size_bytes=entry.size,
        sha256=entry.sha256,
        mime_type=entry.mime_type,
        device=entry.device,
        inode=entry.inode,
        modified_ns=entry.modified_ns,
        changed_ns=entry.changed_ns,
    )


def _selected_entries(path: str, *, directory: bool) -> tuple[local_media.LocalMediaEntry, ...]:
    try:
        if directory:
            normalized = local_media.normalize_local_media_directory_path(path)
            if normalized is None:
                raise LocalWorkflowError("path_invalid")
        else:
            normalized = local_media.normalize_local_media_path(path)
            if normalized is None:
                raise LocalWorkflowError("path_invalid")
        scan = local_media.scan_local_media()
    except (local_media.LocalMediaPathError, OSError) as exc:
        raise LocalWorkflowError("media_unavailable") from exc
    if directory:
        prefix = normalized.rstrip("/") + "/"
        selected = tuple(entry for entry in scan.entries if entry.media_path.startswith(prefix))
    else:
        selected = tuple(entry for entry in scan.entries if entry.media_path == normalized)
    if not selected:
        raise LocalWorkflowError("media_not_found")
    if len(selected) > MAX_PLAN_FILES:
        raise LocalWorkflowError("directory_limit")
    if any(not entry.available for entry in selected):
        raise LocalWorkflowError("media_invalid")
    return selected


def build_local_import_preview(
    db: Session,
    *,
    item_id: int,
    source_id: int | None,
    path: str,
    directory: bool = False,
) -> LocalImportPreview:
    if db.get(Item, item_id) is None:
        raise LocalWorkflowError("item_not_found")
    if source_id is not None:
        source = db.get(ItemSource, source_id)
        if source is None or source.item_id != item_id:
            raise LocalWorkflowError("source_mismatch")
    facts = tuple(_entry_fact(entry) for entry in _selected_entries(path, directory=directory))
    existing_paths = set(
        db.scalars(
            select(ItemLocalAsset.relative_path).where(
                ItemLocalAsset.relative_path.in_(tuple(fact.relative_path for fact in facts))
            )
        ).all()
    )
    existing_hashes = set(
        db.scalars(
            select(ItemLocalAsset.sha256).where(
                ItemLocalAsset.sha256.in_(tuple(fact.sha256 for fact in facts))
            )
        ).all()
    )
    duplicates: list[str] = []
    importable: list[LocalFileFact] = []
    selected_hashes: set[str] = set()
    for fact in facts:
        if (
            fact.relative_path in existing_paths
            or fact.sha256 in existing_hashes
            or fact.sha256 in selected_hashes
        ):
            duplicates.append(fact.relative_path)
            continue
        selected_hashes.add(fact.sha256)
        importable.append(fact)
    if not importable:
        raise LocalWorkflowError("duplicate_media")
    return LocalImportPreview(
        LocalImportPlan(PLAN_FORMAT, item_id, source_id, tuple(importable)),
        tuple(duplicates),
    )


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise LocalWorkflowError("token_invalid") from exc


def sign_local_import_plan(
    plan: LocalImportPlan,
    *,
    secret: bytes,
    context: str,
    now: datetime,
    ttl_seconds: int = 600,
) -> str:
    if (
        type(plan) is not LocalImportPlan
        or not isinstance(secret, bytes)
        or len(secret) < 32
        or not context
        or now.tzinfo is None
        or not 1 <= ttl_seconds <= MAX_PLAN_TTL_SECONDS
    ):
        raise LocalWorkflowError("token_invalid")
    issued = now.astimezone(UTC)
    document = {
        "format": PLAN_FORMAT,
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
        "context_hash": hashlib.sha256(context.encode()).hexdigest(),
        "plan": {
            "format": plan.format,
            "item_id": plan.item_id,
            "source_id": plan.source_id,
            "files": [asdict(fact) for fact in plan.files],
        },
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(secret, _TOKEN_PREFIX.encode() + b"." + payload, hashlib.sha256).digest()
    return f"{_TOKEN_PREFIX}.{_b64(payload)}.{_b64(signature)}"


def verify_local_import_token(
    token: str,
    *,
    secret: bytes,
    context: str,
    now: datetime,
) -> LocalImportPlan:
    try:
        prefix, payload_part, signature_part = token.split(".")
        if prefix != _TOKEN_PREFIX or len(secret) < 32 or now.tzinfo is None:
            raise ValueError
        payload = _unb64(payload_part)
        signature = _unb64(signature_part)
        expected = hmac.new(secret, prefix.encode() + b"." + payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        document = json.loads(payload)
        if (
            document["format"] != PLAN_FORMAT
            or document["context_hash"] != hashlib.sha256(context.encode()).hexdigest()
            or now.astimezone(UTC) > datetime.fromisoformat(document["expires_at"]).astimezone(UTC)
        ):
            raise ValueError
        raw = document["plan"]
        return LocalImportPlan(
            raw["format"],
            raw["item_id"],
            raw["source_id"],
            tuple(LocalFileFact(**fact) for fact in raw["files"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, LocalWorkflowError) as exc:
        raise LocalWorkflowError("token_invalid") from exc


def _intent(prefix: str, *values: object) -> str:
    material = ":".join(str(value) for value in values)
    return f"{prefix}:{hashlib.sha256(material.encode()).hexdigest()}"


def _verify_confirmed_tasks(
    factory: Callable[[], Session],
    plan: LocalImportPlan,
    task_ids: tuple[int, ...],
) -> None:
    with factory() as independent:
        tasks = tuple(
            independent.scalars(
                select(OperationTask)
                .where(OperationTask.id.in_(task_ids))
                .order_by(OperationTask.id)
            ).all()
        )
        expected = {fact.relative_path: fact for fact in plan.files}
        if len(tasks) != len(task_ids) or len(tasks) != len(expected):
            raise LocalWorkflowError("confirmation_unverified")
        for task in tasks:
            fact = expected.get(task.relative_target or "")
            if (
                fact is None
                or task.state
                not in {
                    TaskState.QUEUED.value,
                    TaskState.RUNNING.value,
                    TaskState.PAUSED.value,
                    TaskState.BLOCKED.value,
                    TaskState.SUCCEEDED.value,
                }
                or (
                    task.state == TaskState.QUEUED.value
                    and task.stage != "local_import_queued"
                )
                or (
                    task.state == TaskState.SUCCEEDED.value
                    and task.stage != "durable_verified"
                )
                or task.item_id != plan.item_id
                or task.source_id != plan.source_id
                or task.provider_key != LOCAL_PROVIDER
                or task.snapshot_hash != fact.snapshot_hash
                or task.expected_bytes != fact.size_bytes
                or task.mime_type != fact.mime_type
                or task.sha256 != fact.sha256
            ):
                raise LocalWorkflowError("confirmation_unverified")


def confirm_local_import(
    db: Session,
    *,
    plan: LocalImportPlan,
    max_concurrency: int,
    independent_session_factory: Callable[[], Session] = SessionLocal,
) -> tuple[OperationTask, ...]:
    if db.get(Item, plan.item_id) is None:
        raise LocalWorkflowError("item_not_found")
    if plan.source_id is not None:
        source = db.get(ItemSource, plan.source_id)
        if source is None or source.item_id != plan.item_id:
            raise LocalWorkflowError("source_mismatch")
    service = PersistentTaskService(db, max_concurrency=max_concurrency)
    tasks: list[OperationTask] = []
    try:
        for fact in plan.files:
            current = _entry_fact(
                next(
                    entry
                    for entry in _selected_entries(
                        f"/media/{fact.relative_path}", directory=False
                    )
                )
            )
            if current != fact:
                raise LocalWorkflowError("snapshot_changed")
            task, created = service.create(
                task_type=TaskType.ASSET_DOWNLOAD,
                intent_key=_intent("local-import", plan.item_id, fact.relative_path, fact.sha256),
                initial_state=TaskState.QUEUED,
                item_id=plan.item_id,
                source_id=plan.source_id,
                provider_key=LOCAL_PROVIDER,
                asset_identity=f"local:{fact.sha256}",
                relative_target=fact.relative_path,
                snapshot_hash=fact.snapshot_hash,
            )
            if task.provider_key != LOCAL_PROVIDER:
                raise LocalWorkflowError("intent_conflict")
            if created:
                task.stage = "local_import_queued"
                task.expected_bytes = fact.size_bytes
                task.mime_type = fact.mime_type
                task.sha256 = fact.sha256
            elif (
                task.item_id != plan.item_id
                or task.source_id != plan.source_id
                or task.relative_target != fact.relative_path
                or task.snapshot_hash != fact.snapshot_hash
                or task.expected_bytes != fact.size_bytes
                or task.mime_type != fact.mime_type
                or task.sha256 != fact.sha256
            ):
                raise LocalWorkflowError("intent_conflict")
            tasks.append(task)
        db.commit()
        task_ids = tuple(task.id for task in tasks)
        try:
            _verify_confirmed_tasks(independent_session_factory, plan, task_ids)
        except Exception as exc:
            db.rollback()
            db.expire_all()
            for task_id in task_ids:
                current = db.get(OperationTask, task_id)
                if current is not None and current.state == TaskState.QUEUED.value:
                    service.transition(
                        current.id,
                        TaskState.BLOCKED,
                        expected_version=current.version,
                        event_type="confirmation_unverified",
                        error_code="confirmation_unverified",
                    )
            db.commit()
            raise LocalWorkflowError("confirmation_unverified") from exc
        db.expire_all()
        return tuple(service.get(task_id) for task_id in task_ids)
    except LocalWorkflowError:
        db.rollback()
        raise
    except (IntegrityError, SQLAlchemyError, StopIteration, TaskTransitionError) as exc:
        db.rollback()
        raise LocalWorkflowError("confirmation_failed") from exc


def create_integrity_task(
    db: Session, *, asset_id: int, max_concurrency: int
) -> OperationTask:
    asset = db.get(ItemLocalAsset, asset_id)
    if asset is None:
        raise LocalWorkflowError("asset_not_found")
    service = PersistentTaskService(db, max_concurrency=max_concurrency)
    task, _ = service.create(
        task_type=TaskType.SOURCE_CHECK,
        intent_key=_intent("local-integrity", asset.id, asset.sha256, asset.size_bytes),
        initial_state=TaskState.QUEUED,
        item_id=asset.item_id,
        source_id=asset.source_id,
        provider_key=INTEGRITY_PROVIDER,
        asset_identity=f"local:{asset.sha256}",
        relative_target=asset.relative_path,
        snapshot_hash=hashlib.sha256(
            f"{asset.relative_path}:{asset.size_bytes}:{asset.sha256}".encode()
        ).hexdigest(),
    )
    task.stage = "integrity_queued"
    task.expected_bytes = asset.size_bytes
    task.mime_type = asset.mime_type
    task.sha256 = asset.sha256
    db.commit()
    return task


def _singleton_task(
    db: Session, *, provider: str, stage: str, max_concurrency: int
) -> OperationTask:
    service = PersistentTaskService(db, max_concurrency=max_concurrency)
    active = db.scalar(
        select(OperationTask).where(
            OperationTask.provider_key == provider,
            OperationTask.state.in_(
                (TaskState.QUEUED.value, TaskState.RUNNING.value, TaskState.PAUSED.value)
            ),
        )
    )
    if active is not None:
        return active
    task, _ = service.create(
        task_type=TaskType.METADATA_UPDATE,
        intent_key=_intent(provider, datetime.now(UTC).isoformat(), secrets.token_hex(8)),
        initial_state=TaskState.QUEUED,
        provider_key=provider,
    )
    task.stage = stage
    db.commit()
    return task


def create_index_task(db: Session, *, max_concurrency: int) -> OperationTask:
    return _singleton_task(
        db, provider=INDEX_PROVIDER, stage="index_queued", max_concurrency=max_concurrency
    )


def create_recovery_task(db: Session, *, max_concurrency: int) -> OperationTask:
    return _singleton_task(
        db,
        provider=RECOVERY_PROVIDER,
        stage="recovery_queued",
        max_concurrency=max_concurrency,
    )


def effective_task_state(task: OperationTask) -> str:
    """Expose requested UI states without falsifying the persisted Schema 6 state."""

    if (
        task.state in {TaskState.PAUSED.value, TaskState.BLOCKED.value}
        and task.error_code == "restart_recovery_required"
    ):
        return "interrupted"
    if task.state in {TaskState.FAILED.value, TaskState.BLOCKED.value} and task.stage not in {
        "published",
        "db_linked",
        "index_coordinated",
        "durable_verified",
        "recovery_required",
    }:
        return "retryable"
    return task.state


def _current_fact(relative_path: str) -> LocalFileFact:
    entries = _selected_entries(f"/media/{relative_path}", directory=False)
    return _entry_fact(entries[0])


def _verify_asset_and_index(
    factory: Callable[[], Session],
    *,
    task_id: int,
    fact: LocalFileFact,
    expect_link: bool,
) -> None:
    current = _current_fact(fact.relative_path)
    if current != fact:
        raise LocalWorkflowError("filesystem_mismatch")
    with factory() as independent:
        task = independent.get(OperationTask, task_id)
        if task is None or task.stage not in {"db_linked", "integrity_checked"}:
            raise LocalWorkflowError("task_unverified")
        links = tuple(
            independent.scalars(
                select(ItemLocalAsset).where(ItemLocalAsset.task_id == task_id)
            ).all()
        )
        if expect_link:
            if len(links) != 1:
                raise LocalWorkflowError("asset_unverified")
            link = links[0]
            if (
                link.item_id != task.item_id
                or link.source_id != task.source_id
                or link.relative_path != fact.relative_path
                or link.mime_type != fact.mime_type
                or link.size_bytes != fact.size_bytes
                or link.sha256 != fact.sha256
            ):
                raise LocalWorkflowError("asset_unverified")
        state = independent.get(MediaIndexState, 1)
        indexed = independent.scalar(
            select(MediaIndexEntry).where(
                MediaIndexEntry.media_path == f"/media/{fact.relative_path}"
            )
        )
        if (
            state is None
            or not state.valid
            or indexed is None
            or not indexed.valid
            or indexed.size != fact.size_bytes
            or indexed.sha256 != fact.sha256
            or indexed.mime_type != fact.mime_type
        ):
            raise LocalWorkflowError("index_unverified")


def _mark_unknown(db: Session, task: OperationTask) -> None:
    try:
        db.expire_all()
        current = db.get(OperationTask, task.id)
        if current is not None and current.state == TaskState.RUNNING.value:
            current.stage = "recovery_required"
            PersistentTaskService(db).transition(
                current.id,
                TaskState.OUTCOME_UNKNOWN,
                expected_version=current.version,
                event_type="verification_failed",
                error_code="outcome_unknown",
            )
            invalidate_media_index(db, reason="local_workflow_unverified")
            db.commit()
    except Exception:
        db.rollback()


def _mark_prewrite_failure(db: Session, task_id: int, code: str) -> None:
    try:
        db.expire_all()
        current = db.get(OperationTask, task_id)
        if current is not None and current.state == TaskState.RUNNING.value:
            current.stage = "validation_failed"
            PersistentTaskService(db).transition(
                current.id,
                TaskState.FAILED,
                expected_version=current.version,
                event_type="execution_failed",
                error_code=code,
            )
            db.commit()
    except Exception:
        db.rollback()


def execute_local_task(
    db: Session,
    *,
    task_id: int,
    max_concurrency: int,
    resume: bool = False,
    independent_session_factory: Callable[[], Session] = SessionLocal,
) -> OperationTask:
    service = PersistentTaskService(db, max_concurrency=max_concurrency)
    task = service.get(task_id)
    if task.provider_key not in {
        LOCAL_PROVIDER,
        INTEGRITY_PROVIDER,
        INDEX_PROVIDER,
        RECOVERY_PROVIDER,
    }:
        raise LocalWorkflowError("task_not_local")
    if task.state == TaskState.SUCCEEDED.value:
        return task
    try:
        if resume:
            task = service.transition(
                task.id,
                TaskState.QUEUED,
                expected_version=task.version,
                event_type="resume_requested",
            )
        task = service.transition(
            task.id,
            TaskState.RUNNING,
            expected_version=task.version,
            event_type="start_requested",
        )
        owner = f"local-{secrets.token_hex(16)}"
        task = service.acquire_lease(task.id, owner=owner, expected_version=task.version)
        generation = task.lease_generation
        db.commit()

        if task.provider_key in {LOCAL_PROVIDER, INTEGRITY_PROVIDER}:
            if not task.relative_target:
                raise LocalWorkflowError("path_invalid")
            fact = _current_fact(task.relative_target)
            if (
                task.snapshot_hash
                and task.provider_key == LOCAL_PROVIDER
                and fact.snapshot_hash != task.snapshot_hash
            ) or task.sha256 != fact.sha256 or task.expected_bytes != fact.size_bytes:
                raise LocalWorkflowError("snapshot_changed")
            task = service.heartbeat(
                task.id,
                owner=owner,
                generation=generation,
                bytes_processed=fact.size_bytes,
                stage="integrity_check",
            )
            db.commit()
            with media_operation_lock():
                refresh_media_index(db, full=False)
                task = service.get(task_id)
                if task.provider_key == LOCAL_PROVIDER:
                    existing = db.scalar(
                        select(ItemLocalAsset).where(
                            ItemLocalAsset.relative_path == fact.relative_path
                        )
                    )
                    if existing is None:
                        db.add(
                            ItemLocalAsset(
                                item_id=task.item_id,
                                source_id=task.source_id,
                                task_id=task.id,
                                provider_key=LOCAL_PROVIDER,
                                asset_identity_hash=task.asset_identity_hash,
                                relative_path=fact.relative_path,
                                mime_type=fact.mime_type,
                                size_bytes=fact.size_bytes,
                                sha256=fact.sha256,
                            )
                        )
                    elif existing.task_id != task.id:
                        raise LocalWorkflowError("duplicate_media")
                    task.stage = "db_linked"
                else:
                    asset = db.scalar(
                        select(ItemLocalAsset).where(
                            ItemLocalAsset.relative_path == fact.relative_path,
                            ItemLocalAsset.item_id == task.item_id,
                        )
                    )
                    if asset is None or asset.sha256 != fact.sha256:
                        raise LocalWorkflowError("asset_mismatch")
                    task.stage = "integrity_checked"
                db.commit()
            _verify_asset_and_index(
                independent_session_factory,
                task_id=task.id,
                fact=fact,
                expect_link=task.provider_key == LOCAL_PROVIDER,
            )
        else:
            task = service.heartbeat(
                task.id,
                owner=owner,
                generation=generation,
                stage="indexing" if task.provider_key == INDEX_PROVIDER else "recovering",
            )
            db.commit()
            with media_operation_lock():
                if task.provider_key == RECOVERY_PROVIDER:
                    invalidate_media_index(db, reason="explicit_recovery")
                refresh_media_index(db, full=True)
                task.stage = "index_verified"
                db.commit()
            with independent_session_factory() as independent:
                state = independent.get(MediaIndexState, 1)
                if state is None or not state.valid or state.last_scan_result != "success":
                    raise LocalWorkflowError("index_unverified")

        db.expire_all()
        task = service.get(task_id)
        task.stage = "durable_verified"
        task = service.transition(
            task.id,
            TaskState.SUCCEEDED,
            expected_version=task.version,
            event_type="durable_verified",
        )
        db.commit()
        with independent_session_factory() as independent:
            verified = independent.get(OperationTask, task.id)
            if (
                verified is None
                or verified.state != TaskState.SUCCEEDED.value
                or verified.stage != "durable_verified"
            ):
                raise LocalWorkflowError("final_state_unverified")
        db.expire_all()
        return service.get(task.id)
    except Exception as exc:
        db.rollback()
        with db.no_autoflush:
            current = db.get(OperationTask, task_id)
        if current is not None and current.stage in {
            "db_linked",
            "integrity_checked",
            "index_verified",
            "recovery_required",
        }:
            _mark_unknown(db, current)
        else:
            _mark_prewrite_failure(
                db,
                task_id,
                exc.code if isinstance(exc, LocalWorkflowError) else "operation_failed",
            )
        raise
