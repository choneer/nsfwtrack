from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services import local_media
from app.services.media_cleanup_restore import (
    MediaCleanupRestoreError,
    build_media_cleanup_restore_preview,
)


class MediaCleanupDeleteError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaCleanupDeletePreview:
    anchor: local_media.ValidatedLocalMediaFile
    mime_type: str


@dataclass(frozen=True)
class MediaCleanupDeleteResult:
    deleted_path: str
    sha256: str
    size: int
    warning_code: str | None = None


def build_media_cleanup_delete_preview(
    db: Session,
    *,
    media_path: str | None,
    sha256: str | None,
) -> MediaCleanupDeletePreview:
    try:
        restore_preview = build_media_cleanup_restore_preview(
            db,
            media_path=media_path,
            sha256=sha256,
        )
    except MediaCleanupRestoreError as exc:
        raise MediaCleanupDeleteError(exc.code) from exc
    if restore_preview.reference_count:
        raise MediaCleanupDeleteError("anchor_referenced")
    return MediaCleanupDeletePreview(
        anchor=restore_preview.anchor,
        mime_type=restore_preview.mime_type,
    )


def _parse_identity_number(value: str | int | None) -> int:
    if isinstance(value, bool) or value is None:
        raise MediaCleanupDeleteError("invalid_request")
    raw = str(value)
    if not raw.isascii() or not raw.isdecimal():
        raise MediaCleanupDeleteError("invalid_request")
    return int(raw)


def _snapshot_matches(
    record: local_media.ValidatedLocalMediaFile,
    *,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> bool:
    return (
        record.size == _parse_identity_number(expected_size)
        and record.device == _parse_identity_number(expected_device)
        and record.inode == _parse_identity_number(expected_inode)
        and record.modified_ns == _parse_identity_number(expected_modified_ns)
        and record.changed_ns == _parse_identity_number(expected_changed_ns)
    )


def _reference_counts(db: Session, media_path: str) -> tuple[int, int]:
    return (
        int(
            db.scalar(
                select(func.count(Item.id)).where(Item.cover_path == media_path)
            )
            or 0
        ),
        int(
            db.scalar(
                select(func.count(Creator.id)).where(
                    Creator.avatar_path == media_path
                )
            )
            or 0
        ),
    )


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def execute_media_cleanup_delete(
    db: Session,
    *,
    media_path: str | None,
    sha256: str | None,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> MediaCleanupDeleteResult:
    preview = build_media_cleanup_delete_preview(
        db,
        media_path=media_path,
        sha256=sha256,
    )
    if not _snapshot_matches(
        preview.anchor,
        expected_size=expected_size,
        expected_device=expected_device,
        expected_inode=expected_inode,
        expected_modified_ns=expected_modified_ns,
        expected_changed_ns=expected_changed_ns,
    ):
        raise MediaCleanupDeleteError("stale_anchor")

    try:
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaCleanupDeleteError("reference_check_failed") from exc

    try:
        reference_counts = _reference_counts(db, preview.anchor.media_path)
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaCleanupDeleteError("reference_check_failed") from exc
    if any(reference_counts):
        _rollback_quietly(db)
        raise MediaCleanupDeleteError("anchor_referenced")

    try:
        current_anchor = local_media.validate_local_media_file(
            preview.anchor.media_path,
            expected_sha256=preview.anchor.sha256,
        )
        if not local_media.same_local_media_file_identity(
            preview.anchor,
            current_anchor,
        ):
            raise MediaCleanupDeleteError("stale_anchor")
        local_media.delete_validated_local_media_file(current_anchor)
    except MediaCleanupDeleteError:
        _rollback_quietly(db)
        raise
    except local_media.LocalMediaPathError as exc:
        _rollback_quietly(db)
        raise MediaCleanupDeleteError("stale_anchor") from exc
    except local_media.LocalMediaDeleteError as exc:
        _rollback_quietly(db)
        if exc.removed:
            return MediaCleanupDeleteResult(
                deleted_path=preview.anchor.media_path,
                sha256=preview.anchor.sha256,
                size=preview.anchor.size,
                warning_code=exc.code,
            )
        code = (
            "stale_anchor"
            if exc.code in {"changed", "missing"}
            else "delete_failed"
        )
        raise MediaCleanupDeleteError(code) from exc
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaCleanupDeleteError("delete_failed") from exc

    warning_code = None
    try:
        db.commit()
    except Exception:
        _rollback_quietly(db)
        warning_code = "lock_release_failed"
    return MediaCleanupDeleteResult(
        deleted_path=preview.anchor.media_path,
        sha256=preview.anchor.sha256,
        size=preview.anchor.size,
        warning_code=warning_code,
    )
