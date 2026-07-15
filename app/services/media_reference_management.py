from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media


MediaReferenceObjectType = Literal["item_cover", "creator_avatar"]
MediaReferenceAction = Literal["set", "replace", "clear"]
_MISSING_OBJECT = object()


class MediaReferenceManagementError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaReferenceTarget:
    object_type: MediaReferenceObjectType
    object_id: int
    object_name: str
    original_path: str | None
    object_token: str


@dataclass(frozen=True)
class MediaReferenceManagementPreview:
    target: MediaReferenceTarget
    media: local_media.ValidatedLocalMediaFile
    mime_type: str
    is_recovered: bool
    action: MediaReferenceAction


@dataclass(frozen=True)
class MediaReferenceManagementResult:
    target: MediaReferenceTarget
    action: MediaReferenceAction
    new_path: str | None
    warning_code: str | None = None


def _parse_object_id(value: str | int | None) -> int:
    if isinstance(value, bool) or value is None:
        raise MediaReferenceManagementError("invalid_request")
    raw = str(value)
    if len(raw) > 20 or not raw.isascii() or not raw.isdecimal():
        raise MediaReferenceManagementError("invalid_request")
    parsed = int(raw)
    if parsed <= 0:
        raise MediaReferenceManagementError("invalid_request")
    return parsed


def _serialized(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _object_token(object_type: str, values: tuple[Any, ...]) -> str:
    payload = json.dumps(
        [object_type, *(_serialized(value) for value in values)],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_target(
    db: Session,
    *,
    object_type: str | None,
    object_id: str | int | None,
) -> MediaReferenceTarget:
    parsed_id = _parse_object_id(object_id)
    if object_type == "item_cover":
        row = db.execute(
            select(
                Item.id,
                Item.title,
                Item.cover_path,
                Item.summary,
                Item.release_date,
                Item.extra,
                Item.created_at,
                Item.updated_at,
            ).where(Item.id == parsed_id)
        ).one_or_none()
        if row is None:
            raise MediaReferenceManagementError("object_not_found")
        name = row.title
        original_path = row.cover_path
        values = tuple(row)
        normalized_type: MediaReferenceObjectType = "item_cover"
    elif object_type == "creator_avatar":
        row = db.execute(
            select(
                Creator.id,
                Creator.name,
                Creator.type,
                Creator.avatar_path,
                Creator.created_at,
            ).where(Creator.id == parsed_id)
        ).one_or_none()
        if row is None:
            raise MediaReferenceManagementError("object_not_found")
        name = row.name
        original_path = row.avatar_path
        values = tuple(row)
        normalized_type = "creator_avatar"
    else:
        raise MediaReferenceManagementError("invalid_request")
    return MediaReferenceTarget(
        object_type=normalized_type,
        object_id=parsed_id,
        object_name=str(name),
        original_path=str(original_path) if original_path is not None else None,
        object_token=_object_token(normalized_type, values),
    )


def _load_media(media_path: str | None) -> tuple[local_media.ValidatedLocalMediaFile, str, bool]:
    try:
        normalized = local_media.normalize_interactive_local_media_path(media_path)
    except local_media.LocalMediaPathError as exc:
        raise MediaReferenceManagementError("invalid_media") from exc
    if normalized is None:
        raise MediaReferenceManagementError("invalid_media")
    try:
        scan = local_media.scan_local_media()
    except (local_media.LocalMediaPathError, OSError) as exc:
        raise MediaReferenceManagementError("storage_unavailable") from exc
    entry = next(
        (candidate for candidate in scan.entries if candidate.media_path == normalized),
        None,
    )
    if (
        entry is None
        or not entry.available
        or not entry.sha256
        or entry.is_cleanup_anchor
        or local_media.is_upload_residue_filename(entry.filename)
    ):
        raise MediaReferenceManagementError("media_not_eligible")
    try:
        media = local_media.validate_local_media_file(
            normalized,
            expected_sha256=entry.sha256,
        )
    except local_media.LocalMediaPathError as exc:
        raise MediaReferenceManagementError("media_changed") from exc
    if (
        media.size != entry.size
        or media.device != entry.device
        or media.inode != entry.inode
        or media.modified_ns != entry.modified_ns
        or media.changed_ns != entry.changed_ns
    ):
        raise MediaReferenceManagementError("media_changed")
    return media, entry.mime_type, entry.is_recovered


def _resolve_action(
    *,
    operation: str | None,
    target: MediaReferenceTarget,
    media_path: str,
) -> MediaReferenceAction:
    if operation == "clear":
        if target.original_path != media_path:
            raise MediaReferenceManagementError("stale_reference")
        return "clear"
    if operation != "set":
        raise MediaReferenceManagementError("invalid_request")
    if target.original_path == media_path:
        raise MediaReferenceManagementError("already_set")
    return "set" if target.original_path is None else "replace"


def build_media_reference_management_preview(
    db: Session,
    *,
    media_path: str | None,
    object_type: str | None,
    object_id: str | int | None,
    operation: str | None,
) -> MediaReferenceManagementPreview:
    media, mime_type, is_recovered = _load_media(media_path)
    target = _load_target(db, object_type=object_type, object_id=object_id)
    action = _resolve_action(
        operation=operation,
        target=target,
        media_path=media.media_path,
    )
    return MediaReferenceManagementPreview(
        target=target,
        media=media,
        mime_type=mime_type,
        is_recovered=is_recovered,
        action=action,
    )


def _valid_digest(value: str | None) -> str:
    digest = (value or "").strip().casefold()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise MediaReferenceManagementError("invalid_snapshot")
    return digest


def _parse_identity_number(value: str | int | None) -> int:
    if isinstance(value, bool) or value is None:
        raise MediaReferenceManagementError("invalid_snapshot")
    raw = str(value)
    if len(raw) > 30 or not raw.isascii() or not raw.isdecimal():
        raise MediaReferenceManagementError("invalid_snapshot")
    return int(raw)


def _snapshot_matches(
    preview: MediaReferenceManagementPreview,
    *,
    expected_object_token: str | None,
    expected_action: str | None,
    expected_sha256: str | None,
    expected_mode: str | int | None,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> bool:
    return (
        _valid_digest(expected_object_token) == preview.target.object_token
        and expected_action == preview.action
        and _valid_digest(expected_sha256) == preview.media.sha256
        and _parse_identity_number(expected_mode) == preview.media.mode
        and _parse_identity_number(expected_size) == preview.media.size
        and _parse_identity_number(expected_device) == preview.media.device
        and _parse_identity_number(expected_inode) == preview.media.inode
        and _parse_identity_number(expected_modified_ns) == preview.media.modified_ns
        and _parse_identity_number(expected_changed_ns) == preview.media.changed_ns
    )


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _current_reference(
    db: Session,
    *,
    object_type: MediaReferenceObjectType,
    object_id: int,
) -> str | None | object:
    if object_type == "item_cover":
        row = db.execute(
            select(Item.id, Item.cover_path).where(Item.id == object_id)
        ).one_or_none()
    else:
        row = db.execute(
            select(Creator.id, Creator.avatar_path).where(Creator.id == object_id)
        ).one_or_none()
    return _MISSING_OBJECT if row is None else row[1]


def _inspect_commit_outcome(
    *,
    target: MediaReferenceTarget,
    desired_path: str | None,
) -> str:
    try:
        with SessionLocal() as verification_db:
            current = _current_reference(
                verification_db,
                object_type=target.object_type,
                object_id=target.object_id,
            )
    except Exception:
        return "unknown"
    if current is _MISSING_OBJECT:
        return "unknown"
    if current == desired_path:
        return "committed"
    if current == target.original_path:
        return "not_committed"
    return "unknown"


def execute_media_reference_management(
    db: Session,
    *,
    media_path: str | None,
    object_type: str | None,
    object_id: str | int | None,
    operation: str | None,
    expected_object_token: str | None,
    expected_action: str | None,
    expected_sha256: str | None,
    expected_mode: str | int | None,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> MediaReferenceManagementResult:
    try:
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaReferenceManagementError("transaction_unavailable") from exc

    try:
        preview = build_media_reference_management_preview(
            db,
            media_path=media_path,
            object_type=object_type,
            object_id=object_id,
            operation=operation,
        )
        if not _snapshot_matches(
            preview,
            expected_object_token=expected_object_token,
            expected_action=expected_action,
            expected_sha256=expected_sha256,
            expected_mode=expected_mode,
            expected_size=expected_size,
            expected_device=expected_device,
            expected_inode=expected_inode,
            expected_modified_ns=expected_modified_ns,
            expected_changed_ns=expected_changed_ns,
        ):
            raise MediaReferenceManagementError("stale_preview")
        new_path = None if preview.action == "clear" else preview.media.media_path
        if preview.target.object_type == "item_cover":
            if preview.target.original_path is None:
                statement = text(
                    "UPDATE items SET cover_path = :new_path "
                    "WHERE id = :object_id AND cover_path IS NULL"
                )
            else:
                statement = text(
                    "UPDATE items SET cover_path = :new_path "
                    "WHERE id = :object_id AND cover_path = :original_path"
                )
        elif preview.target.original_path is None:
            statement = text(
                "UPDATE creators SET avatar_path = :new_path "
                "WHERE id = :object_id AND avatar_path IS NULL"
            )
        else:
            statement = text(
                "UPDATE creators SET avatar_path = :new_path "
                "WHERE id = :object_id AND avatar_path = :original_path"
            )
        update_result = db.execute(
            statement,
            {
                "new_path": new_path,
                "object_id": preview.target.object_id,
                "original_path": preview.target.original_path,
            },
        )
        if int(update_result.rowcount or 0) != 1:
            raise MediaReferenceManagementError("stale_reference")
        if _current_reference(
            db,
            object_type=preview.target.object_type,
            object_id=preview.target.object_id,
        ) != new_path:
            raise MediaReferenceManagementError("reference_update_failed")
        current_media, _, _ = _load_media(preview.media.media_path)
        if not local_media.same_local_media_file_identity(preview.media, current_media):
            raise MediaReferenceManagementError("media_changed")
    except MediaReferenceManagementError:
        _rollback_quietly(db)
        raise
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaReferenceManagementError("database_failed") from exc

    try:
        db.commit()
    except Exception as exc:
        _rollback_quietly(db)
        outcome = _inspect_commit_outcome(target=preview.target, desired_path=new_path)
        if outcome == "not_committed":
            raise MediaReferenceManagementError("database_failed") from exc
        return MediaReferenceManagementResult(
            target=preview.target,
            action=preview.action,
            new_path=new_path,
            warning_code=(
                "committed_after_error" if outcome == "committed" else "commit_outcome_unknown"
            ),
        )
    return MediaReferenceManagementResult(
        target=preview.target,
        action=preview.action,
        new_path=new_path,
    )
