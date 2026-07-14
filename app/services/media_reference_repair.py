from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services import local_media
from app.services.media_duplicate_groups import media_search_key, normalize_media_search
from app.services.media_health import audit_local_media
from app.services.pagination import PageInfo, build_page_info


MEDIA_REFERENCE_REPAIR_PAGE_SIZE = 20
REPAIRABLE_MEDIA_REFERENCE_ISSUES = frozenset(
    {
        "media_reference_invalid_path",
        "media_reference_path_escape",
        "media_reference_symlink",
        "media_reference_missing",
        "media_reference_damaged",
    }
)
REPAIRABLE_MEDIA_REFERENCE_OBJECTS = frozenset({"item_cover", "creator_avatar"})

MediaReferenceRepairMode = Literal["replace", "clear"]


class MediaReferenceRepairError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaReferenceRepairTarget:
    object_type: str
    object_id: int
    object_name: str
    original_path: str
    issue_code: str
    object_token: str


@dataclass(frozen=True)
class MediaReferenceReplacement:
    media: local_media.ValidatedLocalMediaFile
    mime_type: str
    is_recovered: bool


@dataclass(frozen=True)
class MediaReferenceRepairPreview:
    target: MediaReferenceRepairTarget
    replacements: tuple[MediaReferenceReplacement, ...]
    page_info: PageInfo
    query: str
    candidate_scan_failed: bool


@dataclass(frozen=True)
class MediaReferenceRepairResult:
    mode: MediaReferenceRepairMode
    object_type: str
    object_id: int
    object_name: str
    old_path: str
    new_path: str | None


def is_repairable_media_reference_issue(
    *,
    object_type: str,
    issue_code: str,
) -> bool:
    return (
        object_type in REPAIRABLE_MEDIA_REFERENCE_OBJECTS
        and issue_code in REPAIRABLE_MEDIA_REFERENCE_ISSUES
    )


def _parse_object_id(value: str | int | None) -> int:
    if isinstance(value, bool) or value is None:
        raise MediaReferenceRepairError("invalid_request")
    raw = str(value)
    if not raw.isascii() or not raw.isdecimal():
        raise MediaReferenceRepairError("invalid_request")
    parsed = int(raw)
    if parsed <= 0:
        raise MediaReferenceRepairError("invalid_request")
    return parsed


def _serialized_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _object_token(object_type: str, values: tuple[Any, ...]) -> str:
    payload = json.dumps(
        [object_type, *(_serialized_value(value) for value in values)],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_target(
    db: Session,
    *,
    object_type: str,
    object_id: str | int | None,
) -> MediaReferenceRepairTarget:
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
            raise MediaReferenceRepairError("object_not_found")
        original_path = row.cover_path
        object_name = row.title
        token_values = tuple(row)
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
            raise MediaReferenceRepairError("object_not_found")
        original_path = row.avatar_path
        object_name = row.name
        token_values = tuple(row)
    else:
        raise MediaReferenceRepairError("invalid_request")

    if original_path is None:
        raise MediaReferenceRepairError("issue_not_repairable")
    return MediaReferenceRepairTarget(
        object_type=object_type,
        object_id=parsed_id,
        object_name=str(object_name),
        original_path=str(original_path),
        issue_code="",
        object_token=_object_token(object_type, token_values),
    )


def _load_current_issue(
    db: Session,
    target: MediaReferenceRepairTarget,
) -> MediaReferenceRepairTarget:
    issue_codes = {
        finding.code
        for finding in audit_local_media(db)
        if finding.object_type == target.object_type
        and finding.object_id == str(target.object_id)
        and is_repairable_media_reference_issue(
            object_type=finding.object_type,
            issue_code=finding.code,
        )
    }
    if len(issue_codes) != 1:
        raise MediaReferenceRepairError("issue_not_repairable")
    return MediaReferenceRepairTarget(
        object_type=target.object_type,
        object_id=target.object_id,
        object_name=target.object_name,
        original_path=target.original_path,
        issue_code=issue_codes.pop(),
        object_token=target.object_token,
    )


def _query_replacements(
    *,
    query: str,
    page: str | int | None,
) -> tuple[tuple[MediaReferenceReplacement, ...], PageInfo, bool]:
    try:
        scan = local_media.scan_local_media()
    except (local_media.LocalMediaPathError, OSError):
        page_info = build_page_info(
            page=1,
            page_size=MEDIA_REFERENCE_REPAIR_PAGE_SIZE,
            total=0,
        )
        return (), page_info, True

    search_key = media_search_key(query)
    replacements: list[MediaReferenceReplacement] = []
    for entry in scan.entries:
        if (
            not entry.available
            or not entry.sha256
            or entry.is_cleanup_anchor
            or (
                search_key
                and search_key not in media_search_key(entry.media_path)
                and search_key not in entry.sha256.casefold()
            )
        ):
            continue
        try:
            media = local_media.validate_local_media_file(
                entry.media_path,
                expected_sha256=entry.sha256,
            )
        except local_media.LocalMediaPathError:
            continue
        replacements.append(
            MediaReferenceReplacement(
                media=media,
                mime_type=entry.mime_type,
                is_recovered=entry.is_recovered,
            )
        )

    replacements.sort(
        key=lambda replacement: (
            media_search_key(replacement.media.media_path),
            replacement.media.media_path,
            replacement.media.sha256,
        )
    )
    page_info = build_page_info(
        page=page,
        page_size=MEDIA_REFERENCE_REPAIR_PAGE_SIZE,
        total=len(replacements),
    )
    start = (page_info.page - 1) * page_info.page_size
    return (
        tuple(replacements[start : start + page_info.page_size]),
        page_info,
        False,
    )


def build_media_reference_repair_preview(
    db: Session,
    *,
    object_type: str | None,
    object_id: str | int | None,
    q: str | None,
    page: str | int | None,
) -> MediaReferenceRepairPreview:
    target = _load_current_issue(
        db,
        _load_target(db, object_type=object_type or "", object_id=object_id),
    )
    query = normalize_media_search(q)
    replacements, page_info, scan_failed = _query_replacements(
        query=query,
        page=page,
    )
    return MediaReferenceRepairPreview(
        target=target,
        replacements=replacements,
        page_info=page_info,
        query=query,
        candidate_scan_failed=scan_failed,
    )


def _valid_digest(value: str | None) -> str:
    digest = (value or "").strip().casefold()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise MediaReferenceRepairError("invalid_request")
    return digest


def _parse_identity_number(value: str | int | None) -> int:
    if isinstance(value, bool) or value is None:
        raise MediaReferenceRepairError("invalid_request")
    raw = str(value)
    if not raw.isascii() or not raw.isdecimal():
        raise MediaReferenceRepairError("invalid_request")
    return int(raw)


def _validate_expected_replacement(
    *,
    media_path: str | None,
    sha256: str | None,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> local_media.ValidatedLocalMediaFile:
    try:
        normalized = local_media.normalize_local_media_path(media_path)
    except local_media.LocalMediaPathError as exc:
        raise MediaReferenceRepairError("replacement_invalid") from exc
    if normalized is None or normalized != media_path:
        raise MediaReferenceRepairError("replacement_invalid")
    if local_media.is_cleanup_anchor_filename(normalized):
        raise MediaReferenceRepairError("replacement_anchor")
    digest = _valid_digest(sha256)
    try:
        current = local_media.validate_local_media_file(
            normalized,
            expected_sha256=digest,
        )
    except local_media.LocalMediaPathError as exc:
        raise MediaReferenceRepairError("replacement_stale") from exc
    expected = (
        _parse_identity_number(expected_size),
        _parse_identity_number(expected_device),
        _parse_identity_number(expected_inode),
        _parse_identity_number(expected_modified_ns),
        _parse_identity_number(expected_changed_ns),
    )
    actual = (
        current.size,
        current.device,
        current.inode,
        current.modified_ns,
        current.changed_ns,
    )
    if actual != expected:
        raise MediaReferenceRepairError("replacement_stale")
    return current


def _validate_submission_target(
    db: Session,
    *,
    object_type: str,
    object_id: str | int | None,
    expected_object_token: str | None,
    expected_original_path: str | None,
    expected_issue_code: str | None,
) -> MediaReferenceRepairTarget:
    target = _load_target(db, object_type=object_type, object_id=object_id)
    if (
        expected_original_path is None
        or target.original_path != expected_original_path
    ):
        raise MediaReferenceRepairError("stale_reference")
    if _valid_digest(expected_object_token) != target.object_token:
        raise MediaReferenceRepairError("stale_object")
    current = _load_current_issue(db, target)
    if (
        expected_issue_code not in REPAIRABLE_MEDIA_REFERENCE_ISSUES
        or current.issue_code != expected_issue_code
    ):
        raise MediaReferenceRepairError("stale_issue")
    return current


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def execute_media_reference_repair(
    db: Session,
    *,
    object_type: str,
    object_id: str | int | None,
    expected_object_token: str | None,
    expected_original_path: str | None,
    expected_issue_code: str | None,
    mode: str,
    replacement_path: str | None = None,
    replacement_sha256: str | None = None,
    expected_size: str | int | None = None,
    expected_device: str | int | None = None,
    expected_inode: str | int | None = None,
    expected_modified_ns: str | int | None = None,
    expected_changed_ns: str | int | None = None,
) -> MediaReferenceRepairResult:
    if mode not in {"replace", "clear"}:
        raise MediaReferenceRepairError("invalid_request")

    _validate_submission_target(
        db,
        object_type=object_type,
        object_id=object_id,
        expected_object_token=expected_object_token,
        expected_original_path=expected_original_path,
        expected_issue_code=expected_issue_code,
    )
    try:
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaReferenceRepairError("database_failed") from exc

    try:
        target = _validate_submission_target(
            db,
            object_type=object_type,
            object_id=object_id,
            expected_object_token=expected_object_token,
            expected_original_path=expected_original_path,
            expected_issue_code=expected_issue_code,
        )
        replacement = None
        if mode == "replace":
            replacement = _validate_expected_replacement(
                media_path=replacement_path,
                sha256=replacement_sha256,
                expected_size=expected_size,
                expected_device=expected_device,
                expected_inode=expected_inode,
                expected_modified_ns=expected_modified_ns,
                expected_changed_ns=expected_changed_ns,
            )
        new_path = replacement.media_path if replacement is not None else None
        if target.object_type == "item_cover":
            statement = (
                update(Item)
                .where(
                    Item.id == target.object_id,
                    Item.cover_path == target.original_path,
                )
                .values(cover_path=new_path)
            )
        else:
            statement = (
                update(Creator)
                .where(
                    Creator.id == target.object_id,
                    Creator.avatar_path == target.original_path,
                )
                .values(avatar_path=new_path)
            )
        result = db.execute(statement)
        if result.rowcount != 1:
            raise MediaReferenceRepairError("stale_reference")
        if replacement is not None:
            final_replacement = _validate_expected_replacement(
                media_path=replacement_path,
                sha256=replacement_sha256,
                expected_size=expected_size,
                expected_device=expected_device,
                expected_inode=expected_inode,
                expected_modified_ns=expected_modified_ns,
                expected_changed_ns=expected_changed_ns,
            )
            if not local_media.same_local_media_file_identity(
                replacement,
                final_replacement,
            ):
                raise MediaReferenceRepairError("replacement_stale")
        db.commit()
    except MediaReferenceRepairError:
        _rollback_quietly(db)
        raise
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaReferenceRepairError("database_failed") from exc

    return MediaReferenceRepairResult(
        mode=mode,
        object_type=target.object_type,
        object_id=target.object_id,
        object_name=target.object_name,
        old_path=target.original_path,
        new_path=new_path,
    )
