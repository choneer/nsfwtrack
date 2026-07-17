from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from app.services.media_index import (
    MediaIndexError,
    invalidate_media_index,
    refresh_media_index,
)
from app.services.media_operation_lock import (
    MediaOperationLock,
    MediaOperationLockError,
    media_operation_lock,
)


class MediaFilesystemOutcome(StrEnum):
    NO_FILESYSTEM_CHANGE = "no_filesystem_change"
    FILESYSTEM_CHANGED_KNOWN = "filesystem_changed_known"
    FILESYSTEM_CHANGED_PARTIAL_KNOWN = "filesystem_changed_partial_known"
    FILESYSTEM_OUTCOME_UNKNOWN = "filesystem_outcome_unknown"


class MediaIndexCoordinationStatus(StrEnum):
    NOT_NEEDED = "not_needed"
    SYNCHRONIZED = "synchronized"
    INVALIDATED = "invalidated"
    POST_MUTATION_REFRESH_FAILED = "post_mutation_refresh_failed"
    INVALIDATION_FAILED = "invalidation_failed"


@dataclass(frozen=True)
class MediaIndexCoordinationResult:
    status: MediaIndexCoordinationStatus
    source: str
    error_code: str | None = None


T = TypeVar("T")


@dataclass(frozen=True)
class CoordinatedMediaMutation(Generic[T]):
    result: T
    outcome: MediaFilesystemOutcome
    index: MediaIndexCoordinationResult


class MediaMutationExecutionError(RuntimeError):
    def __init__(
        self,
        error: Exception,
        *,
        outcome: MediaFilesystemOutcome,
        index: MediaIndexCoordinationResult,
    ) -> None:
        self.error = error
        self.outcome = outcome
        self.index = index
        super().__init__(str(error))


ResultClassifier = Callable[[T], MediaFilesystemOutcome]
ErrorClassifier = Callable[[Exception], MediaFilesystemOutcome]
InvalidationReasonClassifier = Callable[[Exception], str | None]


def _invalidate(
    db: Session,
    *,
    source: str,
    reason: str,
    failed_status: MediaIndexCoordinationStatus,
    error_code: str | None = None,
) -> MediaIndexCoordinationResult:
    try:
        db.rollback()
        with db.begin():
            invalidate_media_index(db, reason=reason)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return MediaIndexCoordinationResult(
            MediaIndexCoordinationStatus.INVALIDATION_FAILED,
            source,
            error_code or "index_invalidation_failed",
        )
    return MediaIndexCoordinationResult(failed_status, source, error_code)


def synchronize_media_index_after_mutation(
    db: Session,
    *,
    outcome: MediaFilesystemOutcome,
    source: str,
    invalidation_reason: str | None = None,
) -> MediaIndexCoordinationResult:
    if outcome == MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE:
        return MediaIndexCoordinationResult(
            MediaIndexCoordinationStatus.NOT_NEEDED,
            source,
        )
    if outcome == MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN:
        return _invalidate(
            db,
            source=source,
            reason=invalidation_reason or "filesystem_outcome_unknown",
            failed_status=MediaIndexCoordinationStatus.INVALIDATED,
            error_code=invalidation_reason or "filesystem_outcome_unknown",
        )
    try:
        refresh_media_index(db, full=False, refresh_source=source)
    except Exception as exc:
        error_code = exc.code if isinstance(exc, MediaIndexError) else "scan_failed"
        return _invalidate(
            db,
            source=source,
            reason="post_mutation_refresh_failed",
            failed_status=MediaIndexCoordinationStatus.POST_MUTATION_REFRESH_FAILED,
            error_code=error_code,
        )
    return MediaIndexCoordinationResult(
        MediaIndexCoordinationStatus.SYNCHRONIZED,
        source,
    )


def _verify_outcome(
    handle: MediaOperationLock,
    outcome: MediaFilesystemOutcome,
) -> MediaFilesystemOutcome:
    try:
        handle.verify()
    except MediaOperationLockError:
        return MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    return outcome


def coordinate_media_mutation(
    db: Session,
    *,
    source: str,
    operation: Callable[[], T],
    classify_result: ResultClassifier[T],
    classify_error: ErrorClassifier,
    classify_invalidation_reason: InvalidationReasonClassifier | None = None,
) -> CoordinatedMediaMutation[T]:
    with media_operation_lock() as handle:
        try:
            result = operation()
        except Exception as exc:
            outcome = _verify_outcome(handle, classify_error(exc))
            index = synchronize_media_index_after_mutation(
                db,
                outcome=outcome,
                source=source,
                invalidation_reason=(
                    classify_invalidation_reason(exc)
                    if classify_invalidation_reason is not None
                    else None
                ),
            )
            raise MediaMutationExecutionError(
                exc,
                outcome=outcome,
                index=index,
            ) from exc
        outcome = _verify_outcome(handle, classify_result(result))
        index = synchronize_media_index_after_mutation(
            db,
            outcome=outcome,
            source=source,
        )
        return CoordinatedMediaMutation(result, outcome, index)


async def coordinate_media_mutation_async(
    db: Session,
    *,
    source: str,
    operation: Callable[[], Awaitable[T]],
    classify_result: ResultClassifier[T],
    classify_error: ErrorClassifier,
    classify_invalidation_reason: InvalidationReasonClassifier | None = None,
) -> CoordinatedMediaMutation[T]:
    with media_operation_lock() as handle:
        try:
            result = await operation()
        except Exception as exc:
            outcome = _verify_outcome(handle, classify_error(exc))
            index = synchronize_media_index_after_mutation(
                db,
                outcome=outcome,
                source=source,
                invalidation_reason=(
                    classify_invalidation_reason(exc)
                    if classify_invalidation_reason is not None
                    else None
                ),
            )
            raise MediaMutationExecutionError(
                exc,
                outcome=outcome,
                index=index,
            ) from exc
        outcome = _verify_outcome(handle, classify_result(result))
        index = synchronize_media_index_after_mutation(
            db,
            outcome=outcome,
            source=source,
        )
        return CoordinatedMediaMutation(result, outcome, index)


def classify_media_operation_error(
    operation: str,
    error: Exception,
) -> MediaFilesystemOutcome:
    code = getattr(error, "code", None)
    if operation == "upload" and code == "storage_unavailable":
        return MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    if operation in {"rename", "move"} and code == "target_cleanup_failed":
        return MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    if operation == "duplicate" and code == "anchor_cleanup_failed":
        return MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    if operation == "recovery" and code == "recovery_cleanup_failed":
        return MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    if operation == "root_init" and bool(getattr(error, "created", False)):
        return MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    expected_error_names = {
        "upload": "LocalMediaUploadError",
        "rename": "MediaFileRenameError",
        "move": "MediaFileRenameError",
        "batch": "MediaBatchError",
        "alias": "MediaAliasNormalizationError",
        "duplicate": "MediaDuplicateCleanupError",
        "damaged": "MediaDamagedCleanupError",
        "recovery": "MediaCleanupRestoreError",
        "anchor_delete": "MediaCleanupDeleteError",
        "residue_delete": "MediaUploadResidueCleanupError",
        "root_init": "MediaRootDiagnosticError",
    }
    if type(error).__name__ == expected_error_names.get(operation):
        return MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE
    return MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN


def classify_upload_result(result: object) -> MediaFilesystemOutcome:
    changed = bool(getattr(result, "filesystem_changed", False))
    return (
        MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN
        if changed
        else MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE
    )


def classify_rename_result(result: object) -> MediaFilesystemOutcome:
    if getattr(result, "warning_code", None) == "commit_outcome_unknown":
        return MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    if not bool(getattr(result, "source_removed", False)):
        return MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN
    return MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN


def classify_batch_result(result: object) -> MediaFilesystemOutcome:
    items = tuple(getattr(result, "items", ()))
    if any(
        getattr(item, "status", None) == "unknown"
        or getattr(item, "code", None)
        in {"commit_outcome_unknown", "target_cleanup_failed", "unexpected_failure"}
        for item in items
    ):
        return MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    changed = any(
        getattr(item, "status", None) in {"success", "source_retained"}
        for item in items
    )
    if not changed:
        return MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE
    if any(getattr(item, "status", None) == "failed" for item in items):
        return MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN
    if any(getattr(item, "status", None) == "source_retained" for item in items):
        return MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN
    return MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN


def classify_alias_result(result: object) -> MediaFilesystemOutcome:
    if getattr(result, "database_outcome", None) == "unknown":
        return MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    paths = tuple(getattr(result, "paths", ()))
    deleted = [path for path in paths if getattr(path, "status", None) == "deleted"]
    if not deleted:
        return MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE
    if any(getattr(path, "status", None) == "retained" for path in paths):
        return MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN
    return MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN


def classify_duplicate_result(result: object) -> MediaFilesystemOutcome:
    if tuple(getattr(result, "deletion_failures", ())):
        return MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN
    return MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN


def classify_recovery_result(result: object) -> MediaFilesystemOutcome:
    if not bool(getattr(result, "anchor_removed", False)):
        return MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN
    return MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN


def classify_known_filesystem_change(result: object) -> MediaFilesystemOutcome:
    del result
    return MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN
