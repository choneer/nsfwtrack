from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media


class MediaFileRenameError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaFileRenameItemReference:
    id: int
    title: str


@dataclass(frozen=True)
class MediaFileRenameCreatorReference:
    id: int
    name: str


@dataclass(frozen=True)
class MediaFileRenamePreview:
    source: local_media.ValidatedLocalMediaFile
    target_directory: local_media.ValidatedLocalMediaDirectory
    target_media_path: str
    target_basename: str
    mime_type: str
    is_recovered: bool
    item_references: tuple[MediaFileRenameItemReference, ...]
    creator_references: tuple[MediaFileRenameCreatorReference, ...]

    @property
    def reference_count(self) -> int:
        return len(self.item_references) + len(self.creator_references)

    @property
    def item_reference_ids(self) -> tuple[int, ...]:
        return tuple(reference.id for reference in self.item_references)

    @property
    def creator_reference_ids(self) -> tuple[int, ...]:
        return tuple(reference.id for reference in self.creator_references)


@dataclass(frozen=True)
class MediaFileRenameResult:
    source_path: str
    target_path: str
    sha256: str
    migrated_items: int
    migrated_creators: int
    source_removed: bool
    warning_code: str | None = None


_RESERVED_BASENAME_PREFIXES = (
    local_media.LOCAL_MEDIA_CLEANUP_ANCHOR_PREFIX,
    local_media.LOCAL_MEDIA_RECOVERY_PREFIX,
    local_media.LOCAL_MEDIA_UPLOAD_RESIDUE_PREFIX,
)


def _normalize_source_path(value: str | None) -> str:
    try:
        normalized = local_media.normalize_interactive_local_media_path(value)
    except local_media.LocalMediaPathError as exc:
        raise MediaFileRenameError("invalid_source") from exc
    if normalized is None:
        raise MediaFileRenameError("invalid_source")
    basename = PurePosixPath(normalized).name
    if (
        local_media.is_cleanup_anchor_filename(basename)
        or local_media.is_upload_residue_filename(basename)
    ):
        raise MediaFileRenameError("source_not_eligible")
    return normalized


def _normalize_target(
    source_media_path: str,
    target_basename: str | None,
    target_directory: str | None,
) -> tuple[str, str, str]:
    if target_basename is None or not target_basename:
        if target_directory is None:
            raise MediaFileRenameError("basename_required")
        target_basename = PurePosixPath(source_media_path).name
    if target_basename != target_basename.strip():
        raise MediaFileRenameError("invalid_basename")
    if (
        target_basename in {".", ".."}
        or "/" in target_basename
        or "\\" in target_basename
        or "%" in target_basename
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in target_basename
        )
    ):
        raise MediaFileRenameError("invalid_basename")
    try:
        encoded_name = target_basename.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise MediaFileRenameError("invalid_basename") from exc
    if len(encoded_name) > 255:
        raise MediaFileRenameError("basename_too_long")
    if target_basename.casefold().startswith(
        tuple(prefix.casefold() for prefix in _RESERVED_BASENAME_PREFIXES)
    ):
        raise MediaFileRenameError("reserved_basename")

    source_path = PurePosixPath(source_media_path)
    if PurePosixPath(target_basename).suffix != source_path.suffix:
        raise MediaFileRenameError("extension_changed")
    source_directory = source_path.parent.as_posix()
    if source_directory == "/media":
        source_directory = "/media"
    try:
        normalized_directory = local_media.normalize_local_media_directory_path(
            target_directory or source_directory
        )
    except local_media.LocalMediaPathError as exc:
        raise MediaFileRenameError("invalid_target_directory") from exc
    if normalized_directory is None:
        raise MediaFileRenameError("invalid_target_directory")
    target_path = f"{normalized_directory}/{target_basename}"
    try:
        normalized_target = local_media.normalize_local_media_path(target_path)
    except local_media.LocalMediaPathError as exc:
        raise MediaFileRenameError("invalid_basename") from exc
    if normalized_target != target_path:
        raise MediaFileRenameError("invalid_basename")
    if normalized_target == source_media_path:
        raise MediaFileRenameError("basename_unchanged")
    return normalized_target, target_basename, normalized_directory


def _entry_matches_record(
    entry: local_media.LocalMediaEntry,
    record: local_media.ValidatedLocalMediaFile,
) -> bool:
    return (
        entry.available
        and entry.sha256 == record.sha256
        and entry.size == record.size
        and entry.device == record.device
        and entry.inode == record.inode
        and entry.modified_ns == record.modified_ns
        and entry.changed_ns == record.changed_ns
    )


def _load_references(
    db: Session,
    media_path: str,
) -> tuple[
    tuple[MediaFileRenameItemReference, ...],
    tuple[MediaFileRenameCreatorReference, ...],
]:
    items = tuple(
        MediaFileRenameItemReference(id=row.id, title=row.title)
        for row in db.execute(
            select(Item.id, Item.title)
            .where(Item.cover_path == media_path)
            .order_by(Item.id)
        ).all()
    )
    creators = tuple(
        MediaFileRenameCreatorReference(id=row.id, name=row.name)
        for row in db.execute(
            select(Creator.id, Creator.name)
            .where(Creator.avatar_path == media_path)
            .order_by(Creator.id)
        ).all()
    )
    return items, creators


def _reference_ids(
    db: Session,
    media_path: str,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    item_ids = tuple(
        db.scalars(
            select(Item.id)
            .where(Item.cover_path == media_path)
            .order_by(Item.id)
        ).all()
    )
    creator_ids = tuple(
        db.scalars(
            select(Creator.id)
            .where(Creator.avatar_path == media_path)
            .order_by(Creator.id)
        ).all()
    )
    return item_ids, creator_ids


def build_media_file_rename_preview(
    db: Session,
    *,
    media_path: str | None,
    target_basename: str | None,
    target_directory: str | None = None,
) -> MediaFileRenamePreview:
    source_path = _normalize_source_path(media_path)
    target_path, normalized_basename, normalized_directory = _normalize_target(
        source_path,
        target_basename,
        target_directory,
    )
    try:
        scan = local_media.scan_local_media()
    except (local_media.LocalMediaPathError, OSError) as exc:
        raise MediaFileRenameError("storage_unavailable") from exc
    entry = next(
        (candidate for candidate in scan.entries if candidate.media_path == source_path),
        None,
    )
    if (
        entry is None
        or not entry.available
        or entry.is_cleanup_anchor
        or local_media.is_upload_residue_filename(entry.filename)
        or not entry.sha256
    ):
        raise MediaFileRenameError("source_not_eligible")
    try:
        source = local_media.validate_local_media_file(
            source_path,
            expected_sha256=entry.sha256,
        )
    except local_media.LocalMediaPathError as exc:
        raise MediaFileRenameError("source_changed") from exc
    if not _entry_matches_record(entry, source):
        raise MediaFileRenameError("source_changed")
    try:
        target_directory_record = local_media.validate_local_media_directory(
            normalized_directory
        )
    except local_media.LocalMediaPathError as exc:
        raise MediaFileRenameError("target_directory_unavailable") from exc
    try:
        local_media.ensure_local_media_target_absent(
            source,
            target_path,
            target_directory=target_directory_record,
        )
    except local_media.LocalMediaSafetyAnchorError as exc:
        code = "target_exists" if exc.code == "target_exists" else "source_changed"
        raise MediaFileRenameError(code) from exc

    target_item_ids, target_creator_ids = _reference_ids(db, target_path)
    if target_item_ids or target_creator_ids:
        raise MediaFileRenameError("target_referenced")
    items, creators = _load_references(db, source_path)
    return MediaFileRenamePreview(
        source=source,
        target_directory=target_directory_record,
        target_media_path=target_path,
        target_basename=normalized_basename,
        mime_type=entry.mime_type,
        is_recovered=entry.is_recovered,
        item_references=items,
        creator_references=creators,
    )


def _parse_identity_number(value: str | int | None) -> int:
    if isinstance(value, bool) or value is None:
        raise MediaFileRenameError("invalid_snapshot")
    raw = str(value)
    if len(raw) > 30 or not raw.isascii() or not raw.isdecimal():
        raise MediaFileRenameError("invalid_snapshot")
    return int(raw)


def _parse_reference_ids(values: list[str] | tuple[str, ...] | None) -> tuple[int, ...]:
    if values is None:
        return ()
    if len(values) > 10000:
        raise MediaFileRenameError("invalid_snapshot")
    parsed: list[int] = []
    for value in values:
        if len(value) > 20 or not value.isascii() or not value.isdecimal():
            raise MediaFileRenameError("invalid_snapshot")
        parsed.append(int(value))
    if any(value <= 0 for value in parsed) or len(set(parsed)) != len(parsed):
        raise MediaFileRenameError("invalid_snapshot")
    return tuple(sorted(parsed))


def _snapshot_matches(
    preview: MediaFileRenamePreview,
    *,
    expected_sha256: str | None,
    expected_mode: str | int | None,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
    expected_item_ids: tuple[int, ...],
    expected_creator_ids: tuple[int, ...],
    expected_source_directory_token: str | None = None,
    expected_target_directory_token: str | None = None,
    require_directory_tokens: bool = False,
) -> bool:
    identities_match = (
        expected_sha256 == preview.source.sha256
        and _parse_identity_number(expected_mode) == preview.source.mode
        and _parse_identity_number(expected_size) == preview.source.size
        and _parse_identity_number(expected_device) == preview.source.device
        and _parse_identity_number(expected_inode) == preview.source.inode
        and _parse_identity_number(expected_modified_ns)
        == preview.source.modified_ns
        and _parse_identity_number(expected_changed_ns) == preview.source.changed_ns
        and expected_item_ids == preview.item_reference_ids
        and expected_creator_ids == preview.creator_reference_ids
    )
    if not identities_match:
        return False
    if not require_directory_tokens:
        return True
    return (
        expected_source_directory_token
        == local_media.local_media_directory_identity_token(preview.source)
        and expected_target_directory_token
        == local_media.local_media_directory_identity_token(preview.target_directory)
    )


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _inspect_commit_outcome(
    *,
    source_path: str,
    target_path: str,
    expected_item_ids: tuple[int, ...],
    expected_creator_ids: tuple[int, ...],
) -> str:
    try:
        with SessionLocal() as verification_db:
            source_item_ids, source_creator_ids = _reference_ids(
                verification_db,
                source_path,
            )
            target_item_ids, target_creator_ids = _reference_ids(
                verification_db,
                target_path,
            )
    except Exception:
        return "unknown"

    if not expected_item_ids and not expected_creator_ids:
        return "unknown"
    if (
        source_item_ids == expected_item_ids
        and source_creator_ids == expected_creator_ids
        and not target_item_ids
        and not target_creator_ids
    ):
        return "not_committed"
    if (
        not source_item_ids
        and not source_creator_ids
        and target_item_ids == expected_item_ids
        and target_creator_ids == expected_creator_ids
    ):
        return "committed"
    return "unknown"


def _remove_rolled_back_target(
    link: local_media.ValidatedLocalMediaHardlink,
) -> None:
    try:
        link.remove_target()
    except local_media.LocalMediaSafetyAnchorError as exc:
        raise MediaFileRenameError("target_cleanup_failed") from exc


def _remove_source_after_commit(
    db: Session,
    link: local_media.ValidatedLocalMediaHardlink,
    *,
    expected_item_ids: tuple[int, ...],
    expected_creator_ids: tuple[int, ...],
) -> local_media.LocalMediaLinkRemoval:
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        source_item_ids, source_creator_ids = _reference_ids(
            db,
            link.source.media_path,
        )
        target_item_ids, target_creator_ids = _reference_ids(
            db,
            link.target.media_path,
        )
    except Exception:
        _rollback_quietly(db)
        return local_media.LocalMediaLinkRemoval(False, "reference_check_failed")
    if source_item_ids or source_creator_ids:
        _rollback_quietly(db)
        return local_media.LocalMediaLinkRemoval(False, "references_remaining")
    if (
        target_item_ids != expected_item_ids
        or target_creator_ids != expected_creator_ids
    ):
        _rollback_quietly(db)
        return local_media.LocalMediaLinkRemoval(False, "target_references_changed")

    removal = link.remove_source()
    try:
        db.commit()
    except Exception:
        _rollback_quietly(db)
        if removal.removed:
            return local_media.LocalMediaLinkRemoval(True, "lock_release_failed")
        return local_media.LocalMediaLinkRemoval(
            False,
            removal.code or "reference_check_failed",
        )
    return removal


def execute_media_file_rename(
    db: Session,
    *,
    media_path: str | None,
    target_basename: str | None,
    target_directory: str | None = None,
    expected_sha256: str | None,
    expected_mode: str | int | None,
    expected_size: str | int | None,
    expected_device: str | int | None,
    expected_inode: str | int | None,
    expected_modified_ns: str | int | None,
    expected_changed_ns: str | int | None,
    expected_item_reference_ids: list[str] | tuple[str, ...] | None,
    expected_creator_reference_ids: list[str] | tuple[str, ...] | None,
    expected_source_directory_token: str | None = None,
    expected_target_directory_token: str | None = None,
) -> MediaFileRenameResult:
    expected_item_ids = _parse_reference_ids(expected_item_reference_ids)
    expected_creator_ids = _parse_reference_ids(expected_creator_reference_ids)
    try:
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))
    except Exception as exc:
        _rollback_quietly(db)
        raise MediaFileRenameError("transaction_unavailable") from exc

    try:
        preview = build_media_file_rename_preview(
            db,
            media_path=media_path,
            target_basename=target_basename,
            target_directory=target_directory,
        )
        if not _snapshot_matches(
            preview,
            expected_sha256=expected_sha256,
            expected_mode=expected_mode,
            expected_size=expected_size,
            expected_device=expected_device,
            expected_inode=expected_inode,
            expected_modified_ns=expected_modified_ns,
            expected_changed_ns=expected_changed_ns,
            expected_item_ids=expected_item_ids,
            expected_creator_ids=expected_creator_ids,
            expected_source_directory_token=expected_source_directory_token,
            expected_target_directory_token=expected_target_directory_token,
            require_directory_tokens=target_directory is not None,
        ):
            raise MediaFileRenameError("stale_preview")
    except Exception:
        _rollback_quietly(db)
        raise

    try:
        if preview.target_directory.parts == preview.source.parts[:-1]:
            link_context = local_media.create_validated_local_media_hardlink(
                preview.source,
                preview.target_media_path,
            )
        else:
            link_context = local_media.create_validated_local_media_hardlink(
                preview.source,
                preview.target_media_path,
                target_directory=preview.target_directory,
            )
        with link_context as link:
            try:
                link.verify()
                item_result = db.execute(
                    update(Item)
                    .where(Item.cover_path == preview.source.media_path)
                    .values(cover_path=preview.target_media_path)
                )
                creator_result = db.execute(
                    update(Creator)
                    .where(Creator.avatar_path == preview.source.media_path)
                    .values(avatar_path=preview.target_media_path)
                )
                source_item_ids, source_creator_ids = _reference_ids(
                    db,
                    preview.source.media_path,
                )
                target_item_ids, target_creator_ids = _reference_ids(
                    db,
                    preview.target_media_path,
                )
                if (
                    int(item_result.rowcount or 0) != len(expected_item_ids)
                    or int(creator_result.rowcount or 0)
                    != len(expected_creator_ids)
                    or source_item_ids
                    or source_creator_ids
                    or target_item_ids != expected_item_ids
                    or target_creator_ids != expected_creator_ids
                ):
                    raise MediaFileRenameError("reference_migration_failed")
                link.verify()
            except Exception as exc:
                _rollback_quietly(db)
                _remove_rolled_back_target(link)
                if isinstance(exc, MediaFileRenameError):
                    raise
                if isinstance(exc, local_media.LocalMediaSafetyAnchorError):
                    raise MediaFileRenameError("stale_source") from exc
                raise MediaFileRenameError("database_failed") from exc

            try:
                db.commit()
            except Exception as exc:
                _rollback_quietly(db)
                commit_outcome = _inspect_commit_outcome(
                    source_path=preview.source.media_path,
                    target_path=preview.target_media_path,
                    expected_item_ids=expected_item_ids,
                    expected_creator_ids=expected_creator_ids,
                )
                if commit_outcome == "not_committed":
                    _remove_rolled_back_target(link)
                    raise MediaFileRenameError("database_failed") from exc
                if commit_outcome == "committed":
                    try:
                        link.verify()
                    except local_media.LocalMediaSafetyAnchorError:
                        commit_outcome = "unknown"
                removal = local_media.LocalMediaLinkRemoval(
                    False,
                    "committed_source_retained"
                    if commit_outcome == "committed"
                    else "commit_outcome_unknown",
                )
            else:
                removal = _remove_source_after_commit(
                    db,
                    link,
                    expected_item_ids=expected_item_ids,
                    expected_creator_ids=expected_creator_ids,
                )
    except local_media.LocalMediaSafetyAnchorError as exc:
        _rollback_quietly(db)
        code = {
            "target_exists": "target_exists",
            "invalid_target": "invalid_basename",
            "source_changed": "stale_source",
            "link_changed": "stale_source",
            "target_cleanup_failed": "target_cleanup_failed",
        }.get(exc.code, "publish_failed")
        raise MediaFileRenameError(code) from exc

    return MediaFileRenameResult(
        source_path=preview.source.media_path,
        target_path=preview.target_media_path,
        sha256=preview.source.sha256,
        migrated_items=len(expected_item_ids),
        migrated_creators=len(expected_creator_ids),
        source_removed=removal.removed,
        warning_code=removal.code,
    )
