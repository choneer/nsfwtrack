from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services import local_media
from app.services.media_duplicate_groups import (
    MediaDuplicateGroup,
    find_media_duplicate_group,
)


class MediaDuplicateCleanupError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaItemReference:
    id: int
    title: str


@dataclass(frozen=True)
class MediaCreatorReference:
    id: int
    name: str


@dataclass(frozen=True)
class MediaDuplicateRemovalPreview:
    entry: local_media.LocalMediaEntry
    item_references: tuple[MediaItemReference, ...]
    creator_references: tuple[MediaCreatorReference, ...]


@dataclass(frozen=True)
class MediaDuplicateCleanupPreview:
    group: MediaDuplicateGroup
    keeper: local_media.LocalMediaEntry
    removals: tuple[MediaDuplicateRemovalPreview, ...]

    @property
    def member_paths(self) -> tuple[str, ...]:
        return tuple(entry.media_path for entry in self.group.entries)

    @property
    def item_reference_count(self) -> int:
        return sum(len(removal.item_references) for removal in self.removals)

    @property
    def creator_reference_count(self) -> int:
        return sum(len(removal.creator_references) for removal in self.removals)

    @property
    def reclaimable_bytes(self) -> int:
        return sum(removal.entry.size for removal in self.removals)


@dataclass(frozen=True)
class MediaDeletionFailure:
    media_path: str
    code: str


@dataclass(frozen=True)
class MediaDuplicateCleanupResult:
    sha256: str
    keeper_path: str
    migrated_items: int
    migrated_creators: int
    deleted_paths: tuple[str, ...]
    deletion_failures: tuple[MediaDeletionFailure, ...]
    deletion_warnings: tuple[MediaDeletionFailure, ...]
    released_bytes: int

    @property
    def retry_paths(self) -> tuple[str, ...]:
        return tuple(failure.media_path for failure in self.deletion_failures)


def _normalize_keeper_path(value: str | None) -> str:
    if value is None or not value.strip():
        raise MediaDuplicateCleanupError("keeper_required")
    try:
        normalized = local_media.normalize_local_media_path(value)
    except local_media.LocalMediaPathError as exc:
        raise MediaDuplicateCleanupError("keeper_not_member") from exc
    if normalized is None:
        raise MediaDuplicateCleanupError("keeper_required")
    return normalized


def _load_group(sha256: str | None) -> MediaDuplicateGroup:
    digest = (sha256 or "").strip().casefold()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise MediaDuplicateCleanupError("invalid_digest")
    try:
        scan = local_media.scan_local_media()
    except local_media.LocalMediaPathError as exc:
        raise MediaDuplicateCleanupError("storage_unavailable") from exc
    group = find_media_duplicate_group(scan, digest)
    if group is None:
        raise MediaDuplicateCleanupError("group_not_found")
    return group


def _reference_maps(
    db: Session,
    media_paths: tuple[str, ...],
) -> tuple[
    dict[str, tuple[MediaItemReference, ...]],
    dict[str, tuple[MediaCreatorReference, ...]],
]:
    item_map: dict[str, list[MediaItemReference]] = {}
    creator_map: dict[str, list[MediaCreatorReference]] = {}
    if media_paths:
        item_rows = db.execute(
            select(Item.id, Item.title, Item.cover_path)
            .where(Item.cover_path.in_(media_paths))
            .order_by(Item.title, Item.id)
        ).all()
        creator_rows = db.execute(
            select(Creator.id, Creator.name, Creator.avatar_path)
            .where(Creator.avatar_path.in_(media_paths))
            .order_by(Creator.name, Creator.id)
        ).all()
        for item in item_rows:
            item_map.setdefault(item.cover_path, []).append(
                MediaItemReference(id=item.id, title=item.title)
            )
        for creator in creator_rows:
            creator_map.setdefault(creator.avatar_path, []).append(
                MediaCreatorReference(id=creator.id, name=creator.name)
            )
    return (
        {path: tuple(rows) for path, rows in item_map.items()},
        {path: tuple(rows) for path, rows in creator_map.items()},
    )


def build_media_duplicate_cleanup_preview(
    db: Session,
    *,
    sha256: str | None,
    keeper_path: str | None,
) -> MediaDuplicateCleanupPreview:
    keeper = _normalize_keeper_path(keeper_path)
    group = _load_group(sha256)
    entries_by_path = {entry.media_path: entry for entry in group.entries}
    keeper_entry = entries_by_path.get(keeper)
    if keeper_entry is None:
        raise MediaDuplicateCleanupError("keeper_not_member")
    removal_entries = tuple(
        entry for entry in group.entries if entry.media_path != keeper
    )
    removal_paths = tuple(entry.media_path for entry in removal_entries)
    item_map, creator_map = _reference_maps(db, removal_paths)
    return MediaDuplicateCleanupPreview(
        group=group,
        keeper=keeper_entry,
        removals=tuple(
            MediaDuplicateRemovalPreview(
                entry=entry,
                item_references=item_map.get(entry.media_path, ()),
                creator_references=creator_map.get(entry.media_path, ()),
            )
            for entry in removal_entries
        ),
    )


def _validate_snapshot_paths(paths: list[str] | tuple[str, ...] | None) -> set[str]:
    if paths is None or len(paths) < 2:
        raise MediaDuplicateCleanupError("invalid_snapshot")
    normalized_paths: list[str] = []
    for path in paths:
        try:
            normalized = local_media.normalize_local_media_path(path)
        except local_media.LocalMediaPathError as exc:
            raise MediaDuplicateCleanupError("invalid_snapshot") from exc
        if normalized is None or normalized != path:
            raise MediaDuplicateCleanupError("invalid_snapshot")
        normalized_paths.append(normalized)
    if len(set(normalized_paths)) != len(normalized_paths):
        raise MediaDuplicateCleanupError("invalid_snapshot")
    return set(normalized_paths)


def _same_file_identity(
    first: local_media.ValidatedLocalMediaFile,
    second: local_media.ValidatedLocalMediaFile,
) -> bool:
    return (
        first.path == second.path
        and first.sha256 == second.sha256
        and first.size == second.size
        and first.device == second.device
        and first.inode == second.inode
        and first.modified_ns == second.modified_ns
        and first.changed_ns == second.changed_ns
    )


def _restore_references(
    db: Session,
    preview: MediaDuplicateCleanupPreview,
) -> None:
    try:
        for removal in preview.removals:
            for item in removal.item_references:
                db.execute(
                    update(Item)
                    .where(
                        Item.id == item.id,
                        Item.cover_path == preview.keeper.media_path,
                    )
                    .values(cover_path=removal.entry.media_path)
                )
            for creator in removal.creator_references:
                db.execute(
                    update(Creator)
                    .where(
                        Creator.id == creator.id,
                        Creator.avatar_path == preview.keeper.media_path,
                    )
                    .values(avatar_path=removal.entry.media_path)
                )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise MediaDuplicateCleanupError("database_failed") from exc


def execute_media_duplicate_cleanup(
    db: Session,
    *,
    sha256: str | None,
    keeper_path: str | None,
    expected_member_paths: list[str] | tuple[str, ...] | None,
) -> MediaDuplicateCleanupResult:
    expected_paths = _validate_snapshot_paths(expected_member_paths)
    try:
        preview = build_media_duplicate_cleanup_preview(
            db,
            sha256=sha256,
            keeper_path=keeper_path,
        )
    except MediaDuplicateCleanupError as exc:
        if exc.code in {"group_not_found", "keeper_not_member"}:
            raise MediaDuplicateCleanupError("stale_group") from exc
        raise
    if expected_paths != set(preview.member_paths):
        raise MediaDuplicateCleanupError("stale_group")

    try:
        validated_files = {
            entry.media_path: local_media.validate_local_media_file(
                entry.media_path,
                expected_sha256=preview.group.sha256,
            )
            for entry in preview.group.entries
        }
    except local_media.LocalMediaPathError as exc:
        raise MediaDuplicateCleanupError("stale_group") from exc

    removal_paths = tuple(removal.entry.media_path for removal in preview.removals)
    try:
        db.execute(
            update(Item)
            .where(Item.cover_path.in_(removal_paths))
            .values(cover_path=preview.keeper.media_path)
        )
        db.execute(
            update(Creator)
            .where(Creator.avatar_path.in_(removal_paths))
            .values(avatar_path=preview.keeper.media_path)
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise MediaDuplicateCleanupError("database_failed") from exc

    keeper_record = validated_files[preview.keeper.media_path]
    try:
        current_keeper = local_media.validate_local_media_file(
            preview.keeper.media_path,
            expected_sha256=preview.group.sha256,
        )
    except local_media.LocalMediaPathError as exc:
        _restore_references(db, preview)
        raise MediaDuplicateCleanupError("keeper_changed") from exc
    if not _same_file_identity(keeper_record, current_keeper):
        _restore_references(db, preview)
        raise MediaDuplicateCleanupError("keeper_changed")

    deleted_paths: list[str] = []
    deletion_failures: list[MediaDeletionFailure] = []
    deletion_warnings: list[MediaDeletionFailure] = []
    released_bytes = 0
    for removal in preview.removals:
        media_path = removal.entry.media_path
        try:
            remaining_item_references = db.scalar(
                select(func.count(Item.id)).where(Item.cover_path == media_path)
            ) or 0
            remaining_creator_references = db.scalar(
                select(func.count(Creator.id)).where(Creator.avatar_path == media_path)
            ) or 0
        except Exception:
            db.rollback()
            deletion_failures.append(
                MediaDeletionFailure(media_path, "reference_check_failed")
            )
            continue
        if remaining_item_references or remaining_creator_references:
            deletion_failures.append(
                MediaDeletionFailure(media_path, "references_remaining")
            )
            continue
        try:
            local_media.delete_validated_local_media_file(
                validated_files[media_path]
            )
        except local_media.LocalMediaDeleteError as exc:
            failure = MediaDeletionFailure(media_path, exc.code)
            if exc.removed:
                deleted_paths.append(media_path)
                released_bytes += removal.entry.size
                deletion_warnings.append(failure)
            else:
                deletion_failures.append(failure)
        except OSError:
            deletion_failures.append(MediaDeletionFailure(media_path, "delete_failed"))
        except Exception:
            deletion_failures.append(MediaDeletionFailure(media_path, "delete_failed"))
        else:
            deleted_paths.append(media_path)
            released_bytes += removal.entry.size

    return MediaDuplicateCleanupResult(
        sha256=preview.group.sha256,
        keeper_path=preview.keeper.media_path,
        migrated_items=preview.item_reference_count,
        migrated_creators=preview.creator_reference_count,
        deleted_paths=tuple(deleted_paths),
        deletion_failures=tuple(deletion_failures),
        deletion_warnings=tuple(deletion_warnings),
        released_bytes=released_bytes,
    )
