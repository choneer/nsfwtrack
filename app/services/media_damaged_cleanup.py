from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services import local_media
from app.services.media_health import audit_local_media


class MediaDamagedCleanupError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DamagedMediaItemReference:
    id: int
    title: str


@dataclass(frozen=True)
class DamagedMediaCreatorReference:
    id: int
    name: str


@dataclass(frozen=True)
class MediaDamagedCleanupPreview:
    media: local_media.DamagedLocalMediaFile
    item_references: tuple[DamagedMediaItemReference, ...]
    creator_references: tuple[DamagedMediaCreatorReference, ...]

    @property
    def reference_count(self) -> int:
        return len(self.item_references) + len(self.creator_references)


@dataclass(frozen=True)
class MediaDamagedCleanupResult:
    deleted_path: str
    sha256: str
    size: int
    warning_code: str | None = None


def _normalize_request(
    media_path: str | None,
    sha256: str | None,
    *,
    require_sha256: bool = False,
) -> tuple[str, str | None]:
    digest = sha256.casefold() if sha256 is not None else None
    if require_sha256 and digest is None:
        raise MediaDamagedCleanupError("invalid_request")
    if digest is not None and (
        len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise MediaDamagedCleanupError("invalid_request")
    try:
        normalized = local_media.normalize_local_media_path(media_path)
    except local_media.LocalMediaPathError as exc:
        raise MediaDamagedCleanupError("invalid_request") from exc
    if normalized is None:
        raise MediaDamagedCleanupError("invalid_request")
    basename = PurePosixPath(normalized).name
    if local_media.is_cleanup_anchor_filename(
        basename
    ) or local_media.is_upload_residue_filename(basename):
        raise MediaDamagedCleanupError("not_damaged")
    return normalized, digest


def _load_references(
    db: Session,
    media_path: str,
) -> tuple[
    tuple[DamagedMediaItemReference, ...],
    tuple[DamagedMediaCreatorReference, ...],
]:
    items = tuple(
        DamagedMediaItemReference(id=row.id, title=row.title)
        for row in db.execute(
            select(Item.id, Item.title)
            .where(Item.cover_path == media_path)
            .order_by(Item.title, Item.id)
        ).all()
    )
    creators = tuple(
        DamagedMediaCreatorReference(id=row.id, name=row.name)
        for row in db.execute(
            select(Creator.id, Creator.name)
            .where(Creator.avatar_path == media_path)
            .order_by(Creator.name, Creator.id)
        ).all()
    )
    return items, creators


def _is_reported_damaged(db: Session, media_path: str) -> bool:
    return any(
        finding.code == "media_damaged_file"
        and finding.object_type == "media_file"
        and finding.object_id == media_path
        for finding in audit_local_media(db)
    )


def build_media_damaged_cleanup_preview(
    db: Session,
    *,
    media_path: str | None,
    sha256: str | None,
) -> MediaDamagedCleanupPreview:
    normalized, digest = _normalize_request(media_path, sha256)
    try:
        media = local_media.inspect_damaged_local_media_file(
            normalized,
            expected_sha256=digest,
        )
    except local_media.LocalMediaPathError as exc:
        raise MediaDamagedCleanupError("not_damaged") from exc
    if not _is_reported_damaged(db, media.media_path):
        raise MediaDamagedCleanupError("not_damaged")
    items, creators = _load_references(db, media.media_path)
    return MediaDamagedCleanupPreview(
        media=media,
        item_references=items,
        creator_references=creators,
    )


def _parse_identity_number(value: str | int | None) -> int:
    if isinstance(value, bool) or value is None:
        raise MediaDamagedCleanupError("invalid_request")
    raw = str(value)
    if len(raw) > 30 or not raw.isascii() or not raw.isdecimal():
        raise MediaDamagedCleanupError("invalid_request")
    return int(raw)


def _snapshot_matches(
    media: local_media.DamagedLocalMediaFile,
    *,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> bool:
    return (
        media.size == _parse_identity_number(expected_size)
        and media.device == _parse_identity_number(expected_device)
        and media.inode == _parse_identity_number(expected_inode)
        and media.modified_ns == _parse_identity_number(expected_modified_ns)
        and media.changed_ns == _parse_identity_number(expected_changed_ns)
    )


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def execute_media_damaged_cleanup(
    db: Session,
    *,
    media_path: str | None,
    sha256: str | None,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
) -> MediaDamagedCleanupResult:
    _normalize_request(
        media_path,
        sha256,
        require_sha256=True,
    )
    try:
        preview = build_media_damaged_cleanup_preview(
            db,
            media_path=media_path,
            sha256=sha256,
        )
    except MediaDamagedCleanupError as exc:
        if exc.code == "not_damaged":
            raise MediaDamagedCleanupError("stale_media") from exc
        raise
    if not _snapshot_matches(
        preview.media,
        expected_size=expected_size,
        expected_device=expected_device,
        expected_inode=expected_inode,
        expected_modified_ns=expected_modified_ns,
        expected_changed_ns=expected_changed_ns,
    ):
        raise MediaDamagedCleanupError("stale_media")
    if preview.reference_count:
        raise MediaDamagedCleanupError("media_referenced")

    try:
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaDamagedCleanupError("reference_check_failed") from exc

    try:
        items, creators = _load_references(db, preview.media.media_path)
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaDamagedCleanupError("reference_check_failed") from exc
    if items or creators:
        _rollback_quietly(db)
        raise MediaDamagedCleanupError("media_referenced")

    try:
        current = local_media.inspect_damaged_local_media_file(
            preview.media.media_path,
            expected_sha256=preview.media.sha256,
        )
        if not local_media.same_damaged_local_media_file_identity(
            preview.media,
            current,
        ):
            raise MediaDamagedCleanupError("stale_media")
        local_media.delete_damaged_local_media_file(current)
    except MediaDamagedCleanupError:
        _rollback_quietly(db)
        raise
    except local_media.LocalMediaPathError as exc:
        _rollback_quietly(db)
        raise MediaDamagedCleanupError("stale_media") from exc
    except local_media.LocalMediaDeleteError as exc:
        _rollback_quietly(db)
        if exc.removed:
            return MediaDamagedCleanupResult(
                deleted_path=preview.media.media_path,
                sha256=preview.media.sha256,
                size=preview.media.size,
                warning_code=exc.code,
            )
        code = (
            "stale_media"
            if exc.code in {"changed", "missing"}
            else "delete_failed"
        )
        raise MediaDamagedCleanupError(code) from exc
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaDamagedCleanupError("delete_failed") from exc

    warning_code = None
    try:
        db.commit()
    except Exception:
        _rollback_quietly(db)
        warning_code = "lock_release_failed"
    return MediaDamagedCleanupResult(
        deleted_path=preview.media.media_path,
        sha256=preview.media.sha256,
        size=preview.media.size,
        warning_code=warning_code,
    )
