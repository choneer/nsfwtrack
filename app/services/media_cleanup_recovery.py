from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services.local_media import LocalMediaEntry, LocalMediaScan
from app.services.media_duplicate_groups import media_search_key, normalize_media_search
from app.services.pagination import PageInfo, build_page_info


MEDIA_RECOVERY_PAGE_SIZE = 20
MEDIA_RECOVERY_STATUS_OPTIONS = (
    "all",
    "anchor_referenced",
    "anchor_unreferenced",
    "anchor_damaged",
    "recovered",
)
MEDIA_RECOVERY_SORT_OPTIONS = (
    "path_asc",
    "path_desc",
    "size_asc",
    "size_desc",
    "sha_asc",
    "sha_desc",
    "status_asc",
    "status_desc",
)
DEFAULT_MEDIA_RECOVERY_STATUS = "all"
DEFAULT_MEDIA_RECOVERY_SORT = "path_asc"

MediaRecoveryStatus = Literal[
    "anchor_referenced",
    "anchor_unreferenced",
    "anchor_damaged",
    "recovered",
]
MediaRecoveryFilterStatus = Literal[
    "all",
    "anchor_referenced",
    "anchor_unreferenced",
    "anchor_damaged",
    "recovered",
]
MediaRecoverySort = Literal[
    "path_asc",
    "path_desc",
    "size_asc",
    "size_desc",
    "sha_asc",
    "sha_desc",
    "status_asc",
    "status_desc",
]


@dataclass(frozen=True)
class MediaRecoveryItemReference:
    id: int
    title: str


@dataclass(frozen=True)
class MediaRecoveryCreatorReference:
    id: int
    name: str


@dataclass(frozen=True)
class MediaRecoveryFilters:
    q: str
    status: MediaRecoveryFilterStatus
    sort: MediaRecoverySort

    @property
    def has_filters(self) -> bool:
        return bool(
            self.q
            or self.status != DEFAULT_MEDIA_RECOVERY_STATUS
            or self.sort != DEFAULT_MEDIA_RECOVERY_SORT
        )


@dataclass(frozen=True)
class MediaRecoveryRow:
    entry: LocalMediaEntry
    status: MediaRecoveryStatus
    item_references: tuple[MediaRecoveryItemReference, ...]
    creator_references: tuple[MediaRecoveryCreatorReference, ...]

    @property
    def reference_count(self) -> int:
        return len(self.item_references) + len(self.creator_references)


@dataclass(frozen=True)
class MediaRecoveryResult:
    rows: tuple[MediaRecoveryRow, ...]
    filters: MediaRecoveryFilters
    page_info: PageInfo
    anchor_count: int
    referenced_anchor_count: int
    unreferenced_anchor_count: int
    damaged_anchor_count: int
    recovered_count: int


def normalize_media_recovery_filters(
    *,
    q: str | None,
    status: str | None,
    sort: str | None,
) -> MediaRecoveryFilters:
    normalized_status = (
        status
        if status in MEDIA_RECOVERY_STATUS_OPTIONS
        else DEFAULT_MEDIA_RECOVERY_STATUS
    )
    normalized_sort = (
        sort if sort in MEDIA_RECOVERY_SORT_OPTIONS else DEFAULT_MEDIA_RECOVERY_SORT
    )
    return MediaRecoveryFilters(
        q=normalize_media_search(q),
        status=normalized_status,
        sort=normalized_sort,
    )


def _reference_maps(
    db: Session,
    media_paths: tuple[str, ...],
) -> tuple[
    dict[str, tuple[MediaRecoveryItemReference, ...]],
    dict[str, tuple[MediaRecoveryCreatorReference, ...]],
]:
    item_map: dict[str, list[MediaRecoveryItemReference]] = {}
    creator_map: dict[str, list[MediaRecoveryCreatorReference]] = {}
    if media_paths:
        items = db.execute(
            select(Item.id, Item.title, Item.cover_path)
            .where(Item.cover_path.in_(media_paths))
            .order_by(Item.title, Item.id)
        ).all()
        creators = db.execute(
            select(Creator.id, Creator.name, Creator.avatar_path)
            .where(Creator.avatar_path.in_(media_paths))
            .order_by(Creator.name, Creator.id)
        ).all()
        for item in items:
            item_map.setdefault(item.cover_path, []).append(
                MediaRecoveryItemReference(id=item.id, title=item.title)
            )
        for creator in creators:
            creator_map.setdefault(creator.avatar_path, []).append(
                MediaRecoveryCreatorReference(id=creator.id, name=creator.name)
            )
    return (
        {path: tuple(references) for path, references in item_map.items()},
        {path: tuple(references) for path, references in creator_map.items()},
    )


def _row_status(
    entry: LocalMediaEntry,
    *,
    referenced: bool,
) -> MediaRecoveryStatus:
    if entry.is_recovered:
        return "recovered"
    if not entry.available:
        return "anchor_damaged"
    if referenced:
        return "anchor_referenced"
    return "anchor_unreferenced"


def _sort_rows(rows: list[MediaRecoveryRow], sort: MediaRecoverySort) -> None:
    def path_key(row: MediaRecoveryRow) -> tuple[str, str]:
        return media_search_key(row.entry.media_path), row.entry.media_path

    if sort == "path_desc":
        rows.sort(key=path_key, reverse=True)
    elif sort == "size_asc":
        rows.sort(key=lambda row: (row.entry.size, *path_key(row)))
    elif sort == "size_desc":
        rows.sort(key=lambda row: (-row.entry.size, *path_key(row)))
    elif sort == "sha_asc":
        rows.sort(key=lambda row: (row.entry.sha256, *path_key(row)))
    elif sort == "sha_desc":
        rows.sort(key=lambda row: (row.entry.sha256, *path_key(row)), reverse=True)
    elif sort == "status_asc":
        rows.sort(key=lambda row: (row.status, *path_key(row)))
    elif sort == "status_desc":
        rows.sort(key=lambda row: (row.status, *path_key(row)), reverse=True)
    else:
        rows.sort(key=path_key)


def query_media_cleanup_recovery(
    db: Session,
    scan: LocalMediaScan,
    *,
    q: str | None,
    status: str | None,
    sort: str | None,
    page: str | int | None,
) -> MediaRecoveryResult:
    filters = normalize_media_recovery_filters(q=q, status=status, sort=sort)
    entries = tuple(
        entry
        for entry in scan.entries
        if entry.is_cleanup_anchor or entry.is_recovered
    )
    media_paths = tuple(entry.media_path for entry in entries)
    item_map, creator_map = _reference_maps(db, media_paths)
    rows = [
        MediaRecoveryRow(
            entry=entry,
            status=_row_status(
                entry,
                referenced=bool(
                    item_map.get(entry.media_path)
                    or creator_map.get(entry.media_path)
                ),
            ),
            item_references=item_map.get(entry.media_path, ()),
            creator_references=creator_map.get(entry.media_path, ()),
        )
        for entry in entries
    ]
    anchor_rows = [row for row in rows if row.entry.is_cleanup_anchor]
    search_key = media_search_key(filters.q)
    filtered_rows = [
        row
        for row in rows
        if (
            not search_key
            or search_key in media_search_key(row.entry.media_path)
            or row.entry.sha256.startswith(search_key)
        )
        and (filters.status == "all" or row.status == filters.status)
    ]
    _sort_rows(filtered_rows, filters.sort)
    page_info = build_page_info(
        page=page,
        page_size=MEDIA_RECOVERY_PAGE_SIZE,
        total=len(filtered_rows),
    )
    start = (page_info.page - 1) * page_info.page_size
    end = start + page_info.page_size
    return MediaRecoveryResult(
        rows=tuple(filtered_rows[start:end]),
        filters=filters,
        page_info=page_info,
        anchor_count=len(anchor_rows),
        referenced_anchor_count=sum(
            row.status == "anchor_referenced" for row in anchor_rows
        ),
        unreferenced_anchor_count=sum(
            row.status == "anchor_unreferenced" for row in anchor_rows
        ),
        damaged_anchor_count=sum(
            row.status == "anchor_damaged" for row in anchor_rows
        ),
        recovered_count=sum(row.entry.is_recovered for row in rows),
    )


def media_recovery_filter_query_params(
    filters: MediaRecoveryFilters,
) -> dict[str, str]:
    params: dict[str, str] = {}
    if filters.q:
        params["recovery_q"] = filters.q
    if filters.status != DEFAULT_MEDIA_RECOVERY_STATUS:
        params["recovery_status"] = filters.status
    if filters.sort != DEFAULT_MEDIA_RECOVERY_SORT:
        params["recovery_sort"] = filters.sort
    return params
