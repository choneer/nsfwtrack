from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import ItemLocalAsset, OperationTask, TaskEvent
from app.tasks.contracts import (
    CLOSED_TASK_STATES,
    TaskErrorCode,
    TaskState,
    TaskTransitionError,
    TaskType,
    can_transition,
)

_SAFE_KEY = re.compile(r"[a-z0-9][a-z0-9._:-]{0,95}\Z")
_SAFE_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_RECOVERY_REVIEW_STAGES = frozenset(
    {"published", "db_linked", "index_coordinated", "durable_verified"}
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def identity_hash(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 2_048:
        raise TaskTransitionError(TaskErrorCode.INVALID_REQUEST)
    return hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()


def _safe_error(code: str | None, detail: str | None) -> tuple[str | None, str | None]:
    if code is None:
        return None, None
    if not isinstance(code, str) or _SAFE_CODE.fullmatch(code) is None:
        code = "operation_failed"
    if detail is None:
        return code, None
    if not isinstance(detail, str):
        return code, "redacted"
    lowered = detail.casefold()
    if any(
        marker in lowered
        for marker in ("http://", "https://", "token", "cookie", "password", "secret", "/home/", "/root/", "\\")
    ):
        return code, "redacted"
    cleaned = " ".join(detail.split())[:500]
    return code, cleaned or None


class PersistentTaskService:
    def __init__(self, db: Session, *, max_concurrency: int = 2) -> None:
        if not isinstance(db, Session) or not isinstance(max_concurrency, int) or not 1 <= max_concurrency <= 32:
            raise TaskTransitionError(TaskErrorCode.INVALID_REQUEST)
        self.db = db
        self.max_concurrency = max_concurrency

    def create(
        self,
        *,
        task_type: TaskType,
        intent_key: str,
        initial_state: TaskState = TaskState.PLANNED,
        item_id: int | None = None,
        source_id: int | None = None,
        provider_key: str | None = None,
        external_identity: str | None = None,
        asset_identity: str | None = None,
        relative_target: str | None = None,
        snapshot_hash: str | None = None,
    ) -> tuple[OperationTask, bool]:
        if (
            not isinstance(task_type, TaskType)
            or not isinstance(initial_state, TaskState)
            or initial_state in {TaskState.RUNNING, TaskState.CANCELLING, TaskState.SUCCEEDED}
            or not isinstance(intent_key, str)
            or _SAFE_KEY.fullmatch(intent_key) is None
        ):
            raise TaskTransitionError(TaskErrorCode.INVALID_REQUEST)
        existing = self.db.scalar(
            select(OperationTask).where(OperationTask.intent_key == intent_key)
        )
        if existing is not None:
            return existing, False
        now = utc_now()
        task = OperationTask(
            task_type=task_type.value,
            state=initial_state.value,
            version=1,
            intent_key=intent_key,
            item_id=item_id,
            source_id=source_id,
            provider_key=provider_key,
            external_identity_hash=(identity_hash(external_identity) if external_identity else None),
            asset_identity_hash=(identity_hash(asset_identity) if asset_identity else None),
            relative_target=relative_target,
            snapshot_hash=snapshot_hash,
            stage="planned",
            created_at=now,
            updated_at=now,
        )
        self.db.add(task)
        self.db.flush()
        self.db.add(
            TaskEvent(
                task_id=task.id,
                version=1,
                event_type="created",
                from_state=None,
                to_state=initial_state.value,
                created_at=now,
            )
        )
        return task, True

    def get(self, task_id: int) -> OperationTask:
        if not isinstance(task_id, int) or task_id < 1:
            raise TaskTransitionError(TaskErrorCode.INVALID_REQUEST)
        task = self.db.get(OperationTask, task_id)
        if task is None:
            raise TaskTransitionError(TaskErrorCode.NOT_FOUND)
        return task

    def transition(
        self,
        task_id: int,
        target: TaskState,
        *,
        expected_version: int,
        event_type: str,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> OperationTask:
        task = self.get(task_id)
        if (
            not isinstance(target, TaskState)
            or not isinstance(expected_version, int)
            or expected_version < 1
            or not isinstance(event_type, str)
            or _SAFE_CODE.fullmatch(event_type) is None
        ):
            raise TaskTransitionError(TaskErrorCode.INVALID_REQUEST)
        if task.version != expected_version:
            raise TaskTransitionError(TaskErrorCode.VERSION_CONFLICT)
        current = TaskState(task.state)
        if not can_transition(current, target):
            raise TaskTransitionError(TaskErrorCode.INVALID_TRANSITION)
        if target is TaskState.RUNNING:
            running = self.db.scalar(
                select(func.count()).select_from(OperationTask).where(
                    OperationTask.state == TaskState.RUNNING.value,
                    OperationTask.id != task.id,
                )
            )
            if int(running or 0) >= self.max_concurrency:
                raise TaskTransitionError(TaskErrorCode.CONCURRENCY_LIMIT)
        safe_code, safe_detail = _safe_error(error_code, error_detail)
        now = utc_now()
        next_version = task.version + 1
        values: dict[str, object] = {
            "state": target.value,
            "version": next_version,
            "updated_at": now,
            "error_code": safe_code,
            "error_detail": safe_detail,
        }
        if target is TaskState.RUNNING:
            values["started_at"] = task.started_at or now
            values["attempt_count"] = task.attempt_count + 1
        if target in {TaskState.PAUSED, TaskState.BLOCKED, TaskState.QUEUED}:
            values["lease_owner"] = None
            values["lease_started_at"] = None
            values["lease_heartbeat_at"] = None
            values["lease_expires_at"] = None
        if target is TaskState.QUEUED:
            values["finished_at"] = None
            values["cancel_requested"] = False
        if target in CLOSED_TASK_STATES:
            values["finished_at"] = now
            values["lease_owner"] = None
            values["lease_started_at"] = None
            values["lease_heartbeat_at"] = None
            values["lease_expires_at"] = None
        result = self.db.execute(
            update(OperationTask)
            .where(OperationTask.id == task.id, OperationTask.version == expected_version)
            .values(**values)
        )
        if result.rowcount != 1:
            raise TaskTransitionError(TaskErrorCode.VERSION_CONFLICT)
        self.db.add(
            TaskEvent(
                task_id=task.id,
                version=next_version,
                event_type=event_type,
                from_state=current.value,
                to_state=target.value,
                error_code=safe_code,
                created_at=now,
            )
        )
        self.db.flush()
        self.db.refresh(task)
        return task

    def acquire_lease(
        self,
        task_id: int,
        *,
        owner: str,
        expected_version: int,
        ttl_seconds: int = 30,
    ) -> OperationTask:
        task = self.get(task_id)
        now = utc_now()
        if (
            task.version != expected_version
            or task.state != TaskState.RUNNING.value
            or not isinstance(owner, str)
            or _SAFE_KEY.fullmatch(owner) is None
            or not isinstance(ttl_seconds, int)
            or not 5 <= ttl_seconds <= 300
        ):
            raise TaskTransitionError(TaskErrorCode.LEASE_CONFLICT)
        if task.lease_expires_at is not None and task.lease_expires_at > now and task.lease_owner != owner:
            raise TaskTransitionError(TaskErrorCode.LEASE_CONFLICT)
        task.lease_owner = owner
        task.lease_generation += 1
        task.lease_started_at = now
        task.lease_heartbeat_at = now
        task.lease_expires_at = now + timedelta(seconds=ttl_seconds)
        task.updated_at = now
        self.db.flush()
        return task

    def heartbeat(self, task_id: int, *, owner: str, generation: int, ttl_seconds: int = 30) -> OperationTask:
        task = self.get(task_id)
        now = utc_now()
        if (
            task.state != TaskState.RUNNING.value
            or task.lease_owner != owner
            or task.lease_generation != generation
            or task.lease_expires_at is None
            or task.lease_expires_at <= now
            or not 5 <= ttl_seconds <= 300
        ):
            raise TaskTransitionError(TaskErrorCode.LEASE_CONFLICT)
        task.lease_heartbeat_at = now
        task.lease_expires_at = now + timedelta(seconds=ttl_seconds)
        task.updated_at = now
        self.db.flush()
        return task

    def request_cancel(self, task_id: int, *, expected_version: int) -> OperationTask:
        task = self.get(task_id)
        state = TaskState(task.state)
        if state in CLOSED_TASK_STATES or state is TaskState.OUTCOME_UNKNOWN:
            raise TaskTransitionError(TaskErrorCode.INVALID_TRANSITION)
        target = TaskState.CANCELLING if state is TaskState.RUNNING else TaskState.CANCELLED
        task.cancel_requested = True
        return self.transition(
            task_id,
            target,
            expected_version=expected_version,
            event_type="cancel_requested",
        )

    def retry(self, task_id: int, *, expected_version: int) -> OperationTask:
        task = self.get(task_id)
        if task.state not in {TaskState.FAILED.value, TaskState.BLOCKED.value}:
            raise TaskTransitionError(TaskErrorCode.RETRY_NOT_SAFE)
        if task.stage in _RECOVERY_REVIEW_STAGES:
            raise TaskTransitionError(TaskErrorCode.RETRY_NOT_SAFE)
        return self.transition(
            task_id,
            TaskState.QUEUED,
            expected_version=expected_version,
            event_type="retry_requested",
        )

    def recover_interrupted(self) -> int:
        rows = tuple(
            self.db.scalars(
                select(OperationTask).where(
                    OperationTask.state.in_(
                        (TaskState.RUNNING.value, TaskState.CANCELLING.value)
                    )
                )
            ).all()
        )
        recovered = 0
        for task in rows:
            target = (
                TaskState.BLOCKED
                if task.stage in _RECOVERY_REVIEW_STAGES
                else TaskState.PAUSED
            )
            self.transition(
                task.id,
                target,
                expected_version=task.version,
                event_type="restart_recovery",
                error_code="restart_recovery_required",
                error_detail="explicit review or resume required",
            )
            recovered += 1
        return recovered

    def delete_history(self, task_id: int) -> None:
        task = self.get(task_id)
        if TaskState(task.state) not in CLOSED_TASK_STATES or task.state == TaskState.OUTCOME_UNKNOWN.value:
            raise TaskTransitionError(TaskErrorCode.HISTORY_NOT_DELETABLE)
        if self.db.scalar(select(ItemLocalAsset.id).where(ItemLocalAsset.task_id == task.id)) is not None:
            raise TaskTransitionError(TaskErrorCode.HISTORY_NOT_DELETABLE)
        self.db.execute(delete(OperationTask).where(OperationTask.id == task.id))

    def cleanup_history(
        self,
        *,
        retention_days: int,
        now: datetime | None = None,
        limit: int = 100,
    ) -> int:
        if (
            not isinstance(retention_days, int)
            or not 1 <= retention_days <= 3_650
            or not isinstance(limit, int)
            or not 1 <= limit <= 1_000
        ):
            raise TaskTransitionError(TaskErrorCode.INVALID_REQUEST)
        cutoff = (now or utc_now()) - timedelta(days=retention_days)
        candidates = tuple(
            self.db.scalars(
                select(OperationTask.id)
                .where(
                    OperationTask.state.in_(
                        (
                            TaskState.CANCELLED.value,
                            TaskState.SUCCEEDED.value,
                            TaskState.FAILED.value,
                        )
                    ),
                    OperationTask.finished_at.is_not(None),
                    OperationTask.finished_at < cutoff,
                    ~select(ItemLocalAsset.id)
                    .where(ItemLocalAsset.task_id == OperationTask.id)
                    .exists(),
                )
                .order_by(OperationTask.finished_at.asc(), OperationTask.id.asc())
                .limit(limit)
            ).all()
        )
        if candidates:
            self.db.execute(
                delete(OperationTask).where(OperationTask.id.in_(candidates))
            )
        return len(candidates)
