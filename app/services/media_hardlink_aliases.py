from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services import local_media
from app.services.media_duplicate_groups import (
    media_search_key,
    normalize_media_search,
    valid_media_sha256,
)
from app.services.pagination import PageInfo, build_page_info


MEDIA_HARDLINK_ALIAS_PAGE_SIZE = 20
MEDIA_HARDLINK_ALIAS_SORT_OPTIONS = (
    "paths_desc",
    "paths_asc",
    "references_desc",
    "path_asc",
)
DEFAULT_MEDIA_HARDLINK_ALIAS_SORT = "paths_desc"

MediaHardlinkAliasSort = Literal[
    "paths_desc",
    "paths_asc",
    "references_desc",
    "path_asc",
]


@dataclass(frozen=True)
class MediaAliasItemReference:
    id: int
    title: str


@dataclass(frozen=True)
class MediaAliasCreatorReference:
    id: int
    name: str


@dataclass(frozen=True)
class MediaHardlinkAliasPath:
    entry: local_media.LocalMediaEntry
    item_references: tuple[MediaAliasItemReference, ...]
    creator_references: tuple[MediaAliasCreatorReference, ...]

    @property
    def reference_count(self) -> int:
        return len(self.item_references) + len(self.creator_references)


@dataclass(frozen=True)
class MediaHardlinkAliasGroup:
    device: int
    inode: int
    sha256: str
    paths: tuple[MediaHardlinkAliasPath, ...]
    same_sha_independent_paths: tuple[local_media.LocalMediaEntry, ...]

    @property
    def path_count(self) -> int:
        return len(self.paths)

    @property
    def reference_count(self) -> int:
        return sum(path.reference_count for path in self.paths)

    @property
    def logical_bytes(self) -> int:
        return sum(path.entry.size for path in self.paths)

    @property
    def physical_bytes(self) -> int:
        return self.paths[0].entry.size


@dataclass(frozen=True)
class MediaHardlinkAliasFilters:
    q: str
    sort: MediaHardlinkAliasSort


@dataclass(frozen=True)
class MediaHardlinkAliasResult:
    groups: tuple[MediaHardlinkAliasGroup, ...]
    filters: MediaHardlinkAliasFilters
    page_info: PageInfo
    total_groups: int
    total_paths: int


def _eligible_entry(entry: local_media.LocalMediaEntry) -> bool:
    return (
        valid_media_sha256(entry) is not None
        and entry.device is not None
        and entry.inode is not None
        and not entry.is_cleanup_anchor
        and not local_media.is_upload_residue_filename(entry.filename)
    )


def _reference_maps(
    db: Session,
) -> tuple[
    dict[str, tuple[MediaAliasItemReference, ...]],
    dict[str, tuple[MediaAliasCreatorReference, ...]],
]:
    item_rows: dict[str, list[MediaAliasItemReference]] = {}
    for row in db.execute(
        select(Item.id, Item.title, Item.cover_path)
        .where(Item.cover_path.is_not(None))
        .order_by(Item.title, Item.id)
    ):
        item_rows.setdefault(row.cover_path, []).append(
            MediaAliasItemReference(id=row.id, title=row.title)
        )
    creator_rows: dict[str, list[MediaAliasCreatorReference]] = {}
    for row in db.execute(
        select(Creator.id, Creator.name, Creator.avatar_path)
        .where(Creator.avatar_path.is_not(None))
        .order_by(Creator.name, Creator.id)
    ):
        creator_rows.setdefault(row.avatar_path, []).append(
            MediaAliasCreatorReference(id=row.id, name=row.name)
        )
    return (
        {path: tuple(rows) for path, rows in item_rows.items()},
        {path: tuple(rows) for path, rows in creator_rows.items()},
    )


def build_media_hardlink_alias_groups(
    db: Session,
    scan: local_media.LocalMediaScan,
) -> tuple[MediaHardlinkAliasGroup, ...]:
    entries = tuple(entry for entry in scan.entries if _eligible_entry(entry))
    by_identity: dict[tuple[int, int], list[local_media.LocalMediaEntry]] = {}
    by_sha: dict[str, list[local_media.LocalMediaEntry]] = {}
    for entry in entries:
        identity = (int(entry.device), int(entry.inode))
        by_identity.setdefault(identity, []).append(entry)
        by_sha.setdefault(entry.sha256.casefold(), []).append(entry)

    item_references, creator_references = _reference_maps(db)
    groups: list[MediaHardlinkAliasGroup] = []
    for (device, inode), members in by_identity.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda entry: (media_search_key(entry.media_path), entry.media_path))
        digest = members[0].sha256.casefold()
        member_paths = [
            MediaHardlinkAliasPath(
                entry=entry,
                item_references=item_references.get(entry.media_path, ()),
                creator_references=creator_references.get(entry.media_path, ()),
            )
            for entry in members
        ]
        aliases = tuple(
            sorted(
                member_paths,
                key=lambda row: (
                    media_search_key(row.entry.media_path),
                    row.entry.media_path,
                ),
            )
        )
        independent = tuple(
            sorted(
                (
                    entry
                    for entry in by_sha.get(digest, ())
                    if (entry.device, entry.inode) != (device, inode)
                ),
                key=lambda entry: (
                    media_search_key(entry.media_path),
                    entry.media_path,
                ),
            )
        )
        groups.append(
            MediaHardlinkAliasGroup(
                device=device,
                inode=inode,
                sha256=digest,
                paths=aliases,
                same_sha_independent_paths=independent,
            )
        )
    return tuple(groups)


def query_media_hardlink_aliases(
    db: Session,
    scan: local_media.LocalMediaScan,
    *,
    q: str | None,
    sort: str | None,
    page: str | int | None,
) -> MediaHardlinkAliasResult:
    filters = MediaHardlinkAliasFilters(
        q=normalize_media_search(q),
        sort=(
            sort
            if sort in MEDIA_HARDLINK_ALIAS_SORT_OPTIONS
            else DEFAULT_MEDIA_HARDLINK_ALIAS_SORT
        ),
    )
    all_groups = build_media_hardlink_alias_groups(db, scan)
    search_key = media_search_key(filters.q)
    groups = [
        group
        for group in all_groups
        if not search_key
        or group.sha256.startswith(search_key)
        or search_key in str(group.device)
        or search_key in str(group.inode)
        or any(
            search_key in media_search_key(path.entry.media_path)
            or any(
                search_key in media_search_key(reference.title)
                for reference in path.item_references
            )
            or any(
                search_key in media_search_key(reference.name)
                for reference in path.creator_references
            )
            for path in group.paths
        )
    ]
    first_path = lambda group: group.paths[0].entry.media_path
    if filters.sort == "paths_asc":
        groups.sort(key=lambda group: (group.path_count, first_path(group)))
    elif filters.sort == "references_desc":
        groups.sort(key=lambda group: (-group.reference_count, first_path(group)))
    elif filters.sort == "path_asc":
        groups.sort(key=first_path)
    else:
        groups.sort(key=lambda group: (-group.path_count, first_path(group)))
    page_info = build_page_info(
        page=page,
        page_size=MEDIA_HARDLINK_ALIAS_PAGE_SIZE,
        total=len(groups),
    )
    start = (page_info.page - 1) * page_info.page_size
    return MediaHardlinkAliasResult(
        groups=tuple(groups[start : start + page_info.page_size]),
        filters=filters,
        page_info=page_info,
        total_groups=len(all_groups),
        total_paths=sum(group.path_count for group in all_groups),
    )


def media_hardlink_alias_query_params(
    filters: MediaHardlinkAliasFilters,
) -> dict[str, str]:
    params: dict[str, str] = {}
    if filters.q:
        params["alias_q"] = filters.q
    if filters.sort != DEFAULT_MEDIA_HARDLINK_ALIAS_SORT:
        params["alias_sort"] = filters.sort
    return params
