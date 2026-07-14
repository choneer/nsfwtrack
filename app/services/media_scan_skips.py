from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.local_media import LocalMediaScan, LocalMediaScanSkip
from app.services.media_duplicate_groups import media_search_key, normalize_media_search
from app.services.pagination import PageInfo, build_page_info


MEDIA_SCAN_SKIP_PAGE_SIZE = 20
MEDIA_SCAN_SKIP_TYPE_OPTIONS = (
    "all",
    "symlink",
    "unsupported",
    "unsupported_extension",
    "special_file",
    "directory_unreadable",
    "entry_error",
)
MEDIA_SCAN_SKIP_SORT_OPTIONS = (
    "path_asc",
    "path_desc",
    "type_asc",
    "type_desc",
)
DEFAULT_MEDIA_SCAN_SKIP_TYPE = "all"
DEFAULT_MEDIA_SCAN_SKIP_SORT = "path_asc"

MediaScanSkipType = Literal[
    "all",
    "symlink",
    "unsupported",
    "unsupported_extension",
    "special_file",
    "directory_unreadable",
    "entry_error",
]
MediaScanSkipSort = Literal[
    "path_asc",
    "path_desc",
    "type_asc",
    "type_desc",
]


@dataclass(frozen=True)
class MediaScanSkipFilters:
    q: str
    skip_type: MediaScanSkipType
    sort: MediaScanSkipSort

    @property
    def has_filters(self) -> bool:
        return bool(
            self.q
            or self.skip_type != DEFAULT_MEDIA_SCAN_SKIP_TYPE
            or self.sort != DEFAULT_MEDIA_SCAN_SKIP_SORT
        )


@dataclass(frozen=True)
class MediaScanSkipResult:
    rows: tuple[LocalMediaScanSkip, ...]
    filters: MediaScanSkipFilters
    page_info: PageInfo
    total_count: int
    symlink_count: int
    unsupported_extension_count: int
    special_file_count: int
    directory_unreadable_count: int
    entry_error_count: int

    @property
    def legacy_unsupported_count(self) -> int:
        return (
            self.unsupported_extension_count
            + self.special_file_count
            + self.directory_unreadable_count
            + self.entry_error_count
        )


def normalize_media_scan_skip_filters(
    *,
    q: str | None,
    skip_type: str | None,
    sort: str | None,
) -> MediaScanSkipFilters:
    normalized_type = (
        skip_type
        if skip_type in MEDIA_SCAN_SKIP_TYPE_OPTIONS
        else DEFAULT_MEDIA_SCAN_SKIP_TYPE
    )
    normalized_sort = (
        sort if sort in MEDIA_SCAN_SKIP_SORT_OPTIONS else DEFAULT_MEDIA_SCAN_SKIP_SORT
    )
    return MediaScanSkipFilters(
        q=normalize_media_search(q),
        skip_type=normalized_type,
        sort=normalized_sort,
    )


def _matches_type(entry: LocalMediaScanSkip, skip_type: MediaScanSkipType) -> bool:
    if skip_type == "all":
        return True
    if skip_type == "unsupported":
        return entry.reason != "symlink"
    return entry.reason == skip_type


def _sort_rows(
    rows: list[LocalMediaScanSkip],
    sort: MediaScanSkipSort,
) -> None:
    def path_key(entry: LocalMediaScanSkip) -> tuple[str, str, str]:
        return media_search_key(entry.path), entry.path, entry.reason

    def type_key(entry: LocalMediaScanSkip) -> tuple[str, str, str]:
        return entry.reason, media_search_key(entry.path), entry.path

    if sort == "path_desc":
        rows.sort(key=path_key, reverse=True)
    elif sort == "type_asc":
        rows.sort(key=type_key)
    elif sort == "type_desc":
        rows.sort(key=type_key, reverse=True)
    else:
        rows.sort(key=path_key)


def query_media_scan_skips(
    scan: LocalMediaScan,
    *,
    q: str | None,
    skip_type: str | None,
    sort: str | None,
    page: str | int | None,
) -> MediaScanSkipResult:
    filters = normalize_media_scan_skip_filters(
        q=q,
        skip_type=skip_type,
        sort=sort,
    )
    search = media_search_key(filters.q)
    all_rows = scan.skipped_entries
    rows = [
        entry
        for entry in all_rows
        if (not search or search in media_search_key(entry.path))
        and _matches_type(entry, filters.skip_type)
    ]
    _sort_rows(rows, filters.sort)
    page_info = build_page_info(
        page=page,
        page_size=MEDIA_SCAN_SKIP_PAGE_SIZE,
        total=len(rows),
    )
    start = (page_info.page - 1) * page_info.page_size
    counts = {
        reason: sum(entry.reason == reason for entry in all_rows)
        for reason in (
            "symlink",
            "unsupported_extension",
            "special_file",
            "directory_unreadable",
            "entry_error",
        )
    }
    return MediaScanSkipResult(
        rows=tuple(rows[start : start + page_info.page_size]),
        filters=filters,
        page_info=page_info,
        total_count=len(all_rows),
        symlink_count=counts["symlink"],
        unsupported_extension_count=counts["unsupported_extension"],
        special_file_count=counts["special_file"],
        directory_unreadable_count=counts["directory_unreadable"],
        entry_error_count=counts["entry_error"],
    )


def media_scan_skip_filter_query_params(
    filters: MediaScanSkipFilters,
) -> dict[str, str]:
    params = {
        "skip_type": filters.skip_type,
        "skip_sort": filters.sort,
    }
    if filters.q:
        params["skip_q"] = filters.q
    return params
