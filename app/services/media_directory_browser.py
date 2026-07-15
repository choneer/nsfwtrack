from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Collection

from app.services import local_media
from app.services.media_duplicate_groups import (
    build_media_duplicate_groups,
    media_search_key,
    valid_media_sha256,
)
from app.services.media_library_query import (
    MEDIA_LIST_PAGE_SIZE,
    MediaListFilters,
    normalize_media_list_filters,
)
from app.services.pagination import PageInfo, build_page_info


@dataclass(frozen=True)
class MediaDirectoryBreadcrumb:
    name: str
    media_path: str


@dataclass(frozen=True)
class MediaDirectoryChild:
    name: str
    media_path: str
    file_count: int
    total_size: int


@dataclass(frozen=True)
class MediaDirectoryFileRow:
    entry: local_media.LocalMediaEntry
    used: bool
    duplicate_count: int


@dataclass(frozen=True)
class MediaDirectorySummary:
    file_count: int
    total_size: int
    damaged_count: int
    duplicate_count: int
    unreferenced_count: int


@dataclass(frozen=True)
class MediaDirectoryBrowserResult:
    current: local_media.ValidatedLocalMediaDirectory
    breadcrumbs: tuple[MediaDirectoryBreadcrumb, ...]
    children: tuple[MediaDirectoryChild, ...]
    rows: tuple[MediaDirectoryFileRow, ...]
    summary: MediaDirectorySummary
    filters: MediaListFilters
    page_info: PageInfo


def _parent_path(media_path: str) -> str:
    return PurePosixPath(media_path).parent.as_posix()


def _breadcrumbs(
    directory: local_media.ValidatedLocalMediaDirectory,
) -> tuple[MediaDirectoryBreadcrumb, ...]:
    rows = [MediaDirectoryBreadcrumb(name="media", media_path="/media")]
    parts: list[str] = []
    for part in directory.parts:
        parts.append(part)
        rows.append(
            MediaDirectoryBreadcrumb(
                name=part,
                media_path=f"/media/{PurePosixPath(*parts).as_posix()}",
            )
        )
    return tuple(rows)


def _matches_status(
    row: MediaDirectoryFileRow,
    status: str,
) -> bool:
    if status == "available":
        return row.entry.available
    if status == "damaged":
        return not row.entry.available
    if status == "used":
        return row.used
    if status == "unused":
        return not row.used
    if status == "duplicate":
        return row.duplicate_count > 1
    if status == "recovered":
        return row.entry.is_recovered
    return True


def _sort_rows(rows: list[MediaDirectoryFileRow], sort: str) -> None:
    filename_key = lambda row: (
        media_search_key(row.entry.filename),
        row.entry.media_path,
    )
    if sort == "filename_desc":
        rows.sort(key=filename_key, reverse=True)
    elif sort == "size_asc":
        rows.sort(key=lambda row: (row.entry.size, *filename_key(row)))
    elif sort == "size_desc":
        rows.sort(key=lambda row: (-row.entry.size, *filename_key(row)))
    else:
        rows.sort(key=filename_key)


def query_media_directory(
    scan: local_media.LocalMediaScan,
    directories: tuple[local_media.ValidatedLocalMediaDirectory, ...],
    used_paths: Collection[str],
    *,
    directory: str | None,
    q: str | None,
    status: str | None,
    sort: str | None,
    page: str | int | None,
) -> MediaDirectoryBrowserResult:
    current_path = local_media.normalize_local_media_directory_path(directory) or "/media"
    current = next(
        (candidate for candidate in directories if candidate.media_path == current_path),
        None,
    )
    if current is None:
        raise local_media.LocalMediaPathError("local media directory unavailable")

    direct_entries = tuple(
        entry for entry in scan.entries if _parent_path(entry.media_path) == current_path
    )
    duplicate_index = {
        entry.media_path: group.member_count
        for group in build_media_duplicate_groups(scan)
        for entry in group.entries
    }
    used = set(used_paths)
    all_rows = tuple(
        MediaDirectoryFileRow(
            entry=entry,
            used=entry.media_path in used,
            duplicate_count=duplicate_index.get(entry.media_path, 1),
        )
        for entry in direct_entries
    )
    summary = MediaDirectorySummary(
        file_count=len(all_rows),
        total_size=sum(row.entry.size for row in all_rows),
        damaged_count=sum(not row.entry.available for row in all_rows),
        duplicate_count=sum(row.duplicate_count > 1 for row in all_rows),
        unreferenced_count=sum(not row.used for row in all_rows),
    )

    child_rows: list[MediaDirectoryChild] = []
    for child in directories:
        if not child.parts or child.parts[:-1] != current.parts:
            continue
        child_entries = tuple(
            entry for entry in scan.entries if _parent_path(entry.media_path) == child.media_path
        )
        child_rows.append(
            MediaDirectoryChild(
                name=child.parts[-1],
                media_path=child.media_path,
                file_count=len(child_entries),
                total_size=sum(entry.size for entry in child_entries),
            )
        )
    child_rows.sort(key=lambda row: (row.name.casefold(), row.name))

    filters = normalize_media_list_filters(q=q, status=status, sort=sort)
    search_key = media_search_key(filters.q)
    rows = [
        row
        for row in all_rows
        if (
            not search_key
            or search_key in media_search_key(row.entry.filename)
            or search_key in media_search_key(row.entry.media_path)
            or (
                (digest := valid_media_sha256(row.entry)) is not None
                and digest.startswith(search_key)
            )
        )
        and _matches_status(row, filters.status)
    ]
    _sort_rows(rows, filters.sort)
    page_info = build_page_info(
        page=page,
        page_size=MEDIA_LIST_PAGE_SIZE,
        total=len(rows),
    )
    start = (page_info.page - 1) * page_info.page_size
    return MediaDirectoryBrowserResult(
        current=current,
        breadcrumbs=_breadcrumbs(current),
        children=tuple(child_rows),
        rows=tuple(rows[start : start + page_info.page_size]),
        summary=summary,
        filters=filters,
        page_info=page_info,
    )


def media_directory_query_params(
    result: MediaDirectoryBrowserResult,
) -> dict[str, str]:
    params = {"directory": result.current.media_path}
    if result.filters.q:
        params["dir_q"] = result.filters.q
    if result.filters.status != "all":
        params["dir_status"] = result.filters.status
    if result.filters.sort != "filename_asc":
        params["dir_sort"] = result.filters.sort
    return params
