from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.acquisition.contracts import (
    AssetDownloadDescriptor,
    DownloadServiceError,
    DownloadServiceErrorCode,
)
from app.acquisition.registry import AcquisitionRegistry
from app.models import (
    DiscoveredAssetFact,
    DownloadTaskFact,
    ItemLocalAsset,
    ItemSource,
    OperationTask,
)
from app.tasks import PersistentTaskService, TaskState, TaskType

DOWNLOAD_PLAN_FORMAT = "nsfwtrack.download-plan.v1"
DEFAULT_DOWNLOAD_PLAN_TTL_SECONDS = 600
MAX_DOWNLOAD_PLAN_TTL_SECONDS = 1_800
_TOKEN_PREFIX = "d1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _raise(code: DownloadServiceErrorCode) -> None:
    raise DownloadServiceError(code)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)
    return value.astimezone(UTC)


def validate_relative_target(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8", "strict")) > 500
        or "\x00" in value
        or "\\" in value
        or value.startswith("/")
    ):
        _raise(DownloadServiceErrorCode.TARGET_INVALID)
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(len(part.encode("utf-8")) > 255 for part in path.parts)
    ):
        _raise(DownloadServiceErrorCode.TARGET_INVALID)
    return path.as_posix()


@dataclass(frozen=True, slots=True, repr=False)
class DownloadPlan:
    format: str
    item_id: int
    source_id: int
    provider_key: str
    external_identity_hash: str
    asset_id: str
    asset_identity_hash: str
    asset_kind: str
    suggested_name: str
    relative_target: str
    mime_type: str
    expected_bytes: int | None
    expected_sha256: str | None
    max_bytes: int
    resume_allowed: bool
    source_snapshot_hash: str

    def __post_init__(self) -> None:
        if self.format != DOWNLOAD_PLAN_FORMAT:
            raise ValueError("invalid format")
        for value in (self.item_id, self.source_id, self.max_bytes):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError("invalid positive integer")
        for value in (
            self.external_identity_hash,
            self.asset_identity_hash,
            self.source_snapshot_hash,
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise ValueError("invalid digest")
        validate_relative_target(self.relative_target)

    def __repr__(self) -> str:
        return "DownloadPlan()"

    @property
    def intent_key(self) -> str:
        material = f"{self.source_id}:{self.asset_identity_hash}:{self.relative_target}"
        return f"download:{hashlib.sha256(material.encode()).hexdigest()}"


@dataclass(frozen=True, slots=True)
class DownloadPreview:
    plan: DownloadPlan | None
    already_linked: bool
    conflict_code: str | None

    @property
    def confirmable(self) -> bool:
        return self.plan is not None and not self.already_linked and self.conflict_code is None


def source_snapshot_hash(source: ItemSource) -> str:
    payload = {
        "id": source.id,
        "item_id": source.item_id,
        "provider_key": source.provider_key,
        "external_id_hash": hashlib.sha256(
            (source.external_id or "").encode("utf-8", "strict")
        ).hexdigest(),
        "metadata_hash": source.metadata_hash,
        "last_checked_at": (
            source.last_checked_at.astimezone(UTC).isoformat()
            if source.last_checked_at is not None
            else None
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_download_preview(
    db: Session,
    *,
    item_id: int,
    source_id: int,
    descriptor: AssetDownloadDescriptor,
    relative_target: str,
    max_bytes: int,
) -> DownloadPreview:
    if not isinstance(db, Session) or type(descriptor) is not AssetDownloadDescriptor:
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)
    source = db.scalar(
        select(ItemSource).where(ItemSource.id == source_id, ItemSource.item_id == item_id)
    )
    if source is None or source.provider_key is None or source.external_id is None:
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)
    if source.provider_key != descriptor.provider_key or source.external_id != descriptor.external_id:
        _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
    target = validate_relative_target(relative_target)
    if not isinstance(max_bytes, int) or not 1_024 <= max_bytes <= 10 * 1024 * 1024 * 1024:
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)
    if descriptor.expected_bytes is not None and descriptor.expected_bytes > max_bytes:
        return DownloadPreview(None, False, DownloadServiceErrorCode.TOO_LARGE.value)
    asset_hash = hashlib.sha256(descriptor.asset_id.encode()).hexdigest()
    existing = db.scalar(
        select(ItemLocalAsset.id).where(
            ItemLocalAsset.item_id == item_id,
            ItemLocalAsset.provider_key == descriptor.provider_key,
            ItemLocalAsset.asset_identity_hash == asset_hash,
        )
    )
    if existing is not None:
        return DownloadPreview(None, True, None)
    path_owner = db.scalar(
        select(ItemLocalAsset.id).where(ItemLocalAsset.relative_path == target)
    )
    if path_owner is not None:
        return DownloadPreview(None, False, DownloadServiceErrorCode.TARGET_EXISTS.value)
    try:
        plan = DownloadPlan(
            format=DOWNLOAD_PLAN_FORMAT,
            item_id=item_id,
            source_id=source_id,
            provider_key=descriptor.provider_key,
            external_identity_hash=hashlib.sha256(descriptor.external_id.encode()).hexdigest(),
            asset_id=descriptor.asset_id,
            asset_identity_hash=asset_hash,
            asset_kind=descriptor.kind.value,
            suggested_name=descriptor.suggested_filename,
            relative_target=target,
            mime_type=descriptor.mime_type,
            expected_bytes=descriptor.expected_bytes,
            expected_sha256=descriptor.expected_sha256,
            max_bytes=max_bytes,
            resume_allowed=descriptor.resume_supported,
            source_snapshot_hash=source_snapshot_hash(source),
        )
    except (TypeError, ValueError):
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)
    return DownloadPreview(plan, False, None)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError):
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)


def sign_download_plan(
    plan: DownloadPlan,
    *,
    secret: bytes,
    context: str,
    now: datetime,
    ttl_seconds: int = DEFAULT_DOWNLOAD_PLAN_TTL_SECONDS,
) -> str:
    if (
        type(plan) is not DownloadPlan
        or not isinstance(secret, bytes)
        or len(secret) < 32
        or not isinstance(context, str)
        or not context
        or not isinstance(ttl_seconds, int)
        or not 1 <= ttl_seconds <= MAX_DOWNLOAD_PLAN_TTL_SECONDS
    ):
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)
    issued = _utc(now)
    document = {
        "format": DOWNLOAD_PLAN_FORMAT,
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(seconds=ttl_seconds)).isoformat(),
        "context_hash": hashlib.sha256(context.encode()).hexdigest(),
        "plan": asdict(plan),
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    segment = _b64(payload)
    signature = _b64(hmac.new(secret, b"nsfwtrack-download\0" + segment.encode(), hashlib.sha256).digest())
    return f"{_TOKEN_PREFIX}.{segment}.{signature}"


def verify_download_token(
    token: str,
    *,
    secret: bytes,
    context: str,
    now: datetime,
) -> DownloadPlan:
    if not isinstance(token, str) or len(token) > 16_384 or not isinstance(secret, bytes) or len(secret) < 32:
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != _TOKEN_PREFIX:
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)
    expected = hmac.new(secret, b"nsfwtrack-download\0" + parts[1].encode(), hashlib.sha256).digest()
    supplied = _unb64(parts[2])
    if not hmac.compare_digest(expected, supplied):
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)
    try:
        document = json.loads(_unb64(parts[1]))
        if set(document) != {"format", "issued_at", "expires_at", "context_hash", "plan"}:
            raise ValueError
        if document["format"] != DOWNLOAD_PLAN_FORMAT:
            raise ValueError
        checked = _utc(now)
        issued = datetime.fromisoformat(document["issued_at"]).astimezone(UTC)
        expires = datetime.fromisoformat(document["expires_at"]).astimezone(UTC)
        if checked < issued or checked >= expires or expires - issued > timedelta(seconds=MAX_DOWNLOAD_PLAN_TTL_SECONDS):
            raise ValueError
        if not hmac.compare_digest(document["context_hash"], hashlib.sha256(context.encode()).hexdigest()):
            raise ValueError
        return DownloadPlan(**document["plan"])
    except (KeyError, TypeError, ValueError, OverflowError):
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)


def confirm_download_plan(
    db: Session,
    *,
    plan: DownloadPlan,
    max_concurrency: int,
) -> tuple[OperationTask, bool]:
    source = db.scalar(
        select(ItemSource).where(
            ItemSource.id == plan.source_id,
            ItemSource.item_id == plan.item_id,
            ItemSource.provider_key == plan.provider_key,
        )
    )
    if (
        source is None
        or source.external_id is None
        or hashlib.sha256(source.external_id.encode()).hexdigest() != plan.external_identity_hash
        or source_snapshot_hash(source) != plan.source_snapshot_hash
    ):
        _raise(DownloadServiceErrorCode.SNAPSHOT_CHANGED)
    service = PersistentTaskService(db, max_concurrency=max_concurrency)
    task, created = service.create(
        task_type=TaskType.ASSET_DOWNLOAD,
        intent_key=plan.intent_key,
        initial_state=TaskState.QUEUED,
        item_id=plan.item_id,
        source_id=plan.source_id,
        provider_key=plan.provider_key,
        external_identity=source.external_id,
        asset_identity=plan.asset_id,
        relative_target=plan.relative_target,
        snapshot_hash=plan.source_snapshot_hash,
    )
    if created:
        task.expected_bytes = plan.expected_bytes
        task.mime_type = plan.mime_type
        db.add(
            DownloadTaskFact(
                task_id=task.id,
                asset_id=plan.asset_id,
                asset_kind=plan.asset_kind,
                suggested_name=plan.suggested_name,
                expected_sha256=plan.expected_sha256,
                max_bytes=plan.max_bytes,
                resume_allowed=plan.resume_allowed,
            )
        )
    return task, created


async def discover_assets(
    db: Session,
    registry: AcquisitionRegistry,
    *,
    item_id: int,
    source_id: int,
    max_concurrency: int,
) -> OperationTask:
    source = db.scalar(
        select(ItemSource).where(ItemSource.id == source_id, ItemSource.item_id == item_id)
    )
    if source is None or source.provider_key is None or source.external_id is None:
        _raise(DownloadServiceErrorCode.INVALID_REQUEST)
    package = registry.require(source.provider_key)
    tasks = PersistentTaskService(db, max_concurrency=max_concurrency)
    task, _created = tasks.create(
        task_type=TaskType.SOURCE_CHECK,
        intent_key=f"asset-list:{source_id}:{hashlib.sha256(str(datetime.now(UTC).timestamp()).encode()).hexdigest()}",
        initial_state=TaskState.QUEUED,
        item_id=item_id,
        source_id=source_id,
        provider_key=source.provider_key,
        external_identity=source.external_id,
        snapshot_hash=source_snapshot_hash(source),
    )
    task = tasks.transition(
        task.id,
        TaskState.RUNNING,
        expected_version=task.version,
        event_type="asset_list_started",
    )
    db.commit()
    try:
        descriptors = await package.adapter.list_assets(source.external_id)
        if (
            not isinstance(descriptors, tuple)
            or len(descriptors) > 256
            or not all(type(value) is AssetDownloadDescriptor for value in descriptors)
            or any(
                value.provider_key != source.provider_key
                or value.external_id != source.external_id
                for value in descriptors
            )
            or len({value.asset_id for value in descriptors}) != len(descriptors)
        ):
            _raise(DownloadServiceErrorCode.PROVIDER_ERROR)
        for value in descriptors:
            db.add(
                DiscoveredAssetFact(
                    task_id=task.id,
                    asset_id=value.asset_id,
                    asset_kind=value.kind.value,
                    display_name=value.display_name,
                    suggested_filename=value.suggested_filename,
                    mime_type=value.mime_type,
                    expected_bytes=value.expected_bytes,
                    expected_sha256=value.expected_sha256,
                    requires_auth=value.requires_auth,
                    resume_supported=value.resume_supported,
                )
            )
        task.stage = "assets_checked"
        task = tasks.transition(
            task.id,
            TaskState.SUCCEEDED,
            expected_version=task.version,
            event_type="asset_list_succeeded",
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
                event_type="asset_list_failed",
                error_code="provider_failed",
            )
            db.commit()
        if isinstance(error, DownloadServiceError):
            raise
        _raise(DownloadServiceErrorCode.PROVIDER_ERROR)
