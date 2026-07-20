from __future__ import annotations

from enum import Enum


class TaskType(str, Enum):
    ASSET_DOWNLOAD = "asset_download"
    SOURCE_CHECK = "source_check"
    METADATA_UPDATE = "metadata_update"


class TaskState(str, Enum):
    PLANNED = "planned"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    OUTCOME_UNKNOWN = "outcome_unknown"


CLOSED_TASK_STATES = frozenset(
    {
        TaskState.CANCELLED,
        TaskState.SUCCEEDED,
        TaskState.FAILED,
        TaskState.OUTCOME_UNKNOWN,
    }
)

TASK_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.PLANNED: frozenset(
        {TaskState.AWAITING_CONFIRMATION, TaskState.QUEUED, TaskState.CANCELLED}
    ),
    TaskState.AWAITING_CONFIRMATION: frozenset(
        {TaskState.QUEUED, TaskState.CANCELLED}
    ),
    TaskState.QUEUED: frozenset(
        {
            TaskState.RUNNING,
            TaskState.PAUSED,
            TaskState.CANCELLING,
            TaskState.CANCELLED,
            TaskState.BLOCKED,
        }
    ),
    TaskState.RUNNING: frozenset(
        {
            TaskState.PAUSED,
            TaskState.CANCELLING,
            TaskState.SUCCEEDED,
            TaskState.FAILED,
            TaskState.BLOCKED,
            TaskState.OUTCOME_UNKNOWN,
        }
    ),
    TaskState.PAUSED: frozenset({TaskState.QUEUED, TaskState.CANCELLED}),
    TaskState.CANCELLING: frozenset(
        {TaskState.CANCELLED, TaskState.FAILED, TaskState.OUTCOME_UNKNOWN}
    ),
    TaskState.CANCELLED: frozenset(),
    TaskState.SUCCEEDED: frozenset(),
    TaskState.FAILED: frozenset({TaskState.QUEUED, TaskState.CANCELLED}),
    TaskState.BLOCKED: frozenset({TaskState.QUEUED, TaskState.CANCELLED}),
    TaskState.OUTCOME_UNKNOWN: frozenset(),
}


class TaskErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    NOT_FOUND = "not_found"
    VERSION_CONFLICT = "version_conflict"
    INVALID_TRANSITION = "invalid_transition"
    CONCURRENCY_LIMIT = "concurrency_limit"
    LEASE_CONFLICT = "lease_conflict"
    RETRY_NOT_SAFE = "retry_not_safe"
    HISTORY_NOT_DELETABLE = "history_not_deletable"


class TaskTransitionError(RuntimeError):
    def __init__(self, code: TaskErrorCode) -> None:
        if not isinstance(code, TaskErrorCode):
            raise TypeError("code must be TaskErrorCode")
        self.code = code
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value


def can_transition(current: TaskState, target: TaskState) -> bool:
    return target in TASK_TRANSITIONS[current]
