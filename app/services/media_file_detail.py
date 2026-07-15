from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services import local_media
from app.services.media_duplicate_groups import (
    MediaDuplicateGroup,
    find_media_duplicate_group,
)


class MediaFileDetailError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaFileItemReference:
    id: int
    title: str


@dataclass(frozen=True)
class MediaFileCreatorReference:
    id: int
    name: str


@dataclass(frozen=True)
class MediaFileDetail:
    entry: local_media.LocalMediaEntry
    filename: str
    extension: str
    item_references: tuple[MediaFileItemReference, ...]
    creator_references: tuple[MediaFileCreatorReference, ...]
    duplicate_group: MediaDuplicateGroup | None

    @property
    def reference_count(self) -> int:
        return len(self.item_references) + len(self.creator_references)

    @property
    def is_duplicate(self) -> bool:
        return self.duplicate_group is not None


def _load_references(
    db: Session,
    media_path: str,
) -> tuple[
    tuple[MediaFileItemReference, ...],
    tuple[MediaFileCreatorReference, ...],
]:
    item_rows = db.execute(
        select(Item.id, Item.title)
        .where(Item.cover_path == media_path)
        .order_by(Item.title, Item.id)
    ).all()
    creator_rows = db.execute(
        select(Creator.id, Creator.name)
        .where(Creator.avatar_path == media_path)
        .order_by(Creator.name, Creator.id)
    ).all()
    return (
        tuple(
            MediaFileItemReference(id=row.id, title=row.title)
            for row in item_rows
        ),
        tuple(
            MediaFileCreatorReference(id=row.id, name=row.name)
            for row in creator_rows
        ),
    )


def build_media_file_detail(
    db: Session,
    *,
    media_path: str | None,
) -> MediaFileDetail:
    try:
        normalized = local_media.normalize_interactive_local_media_path(media_path)
    except local_media.LocalMediaPathError as exc:
        raise MediaFileDetailError("invalid_request") from exc
    if normalized is None:
        raise MediaFileDetailError("invalid_request")

    try:
        scan = local_media.scan_local_media()
    except (local_media.LocalMediaPathError, OSError) as exc:
        raise MediaFileDetailError("scan_failed") from exc
    entry = next(
        (candidate for candidate in scan.entries if candidate.media_path == normalized),
        None,
    )
    if entry is None or entry.is_cleanup_anchor:
        raise MediaFileDetailError("not_found")

    duplicate_group = None
    if entry.available and entry.sha256:
        candidate_group = find_media_duplicate_group(scan, entry.sha256)
        if candidate_group is not None and any(
            member.media_path == entry.media_path
            for member in candidate_group.entries
        ):
            duplicate_group = candidate_group

    item_references, creator_references = _load_references(db, normalized)
    path = PurePosixPath(entry.media_path)
    return MediaFileDetail(
        entry=entry,
        filename=path.name,
        extension=path.suffix.casefold(),
        item_references=item_references,
        creator_references=creator_references,
        duplicate_group=duplicate_group,
    )
