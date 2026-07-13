from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Collection, Literal

from app.services.local_media import LocalMediaEntry, LocalMediaScan
from app.services.pagination import PageInfo, build_page_info


MEDIA_LIST_PAGE_SIZE = 20
MAX_MEDIA_SEARCH_LENGTH = 200
MEDIA_STATUS_OPTIONS = (
    "all",
    "available",
    "damaged",
    "used",
    "unused",
    "duplicate",
)
MEDIA_SORT_OPTIONS = (
    "filename_asc",
    "filename_desc",
    "size_asc",
    "size_desc",
)
DEFAULT_MEDIA_STATUS = "all"
DEFAULT_MEDIA_SORT = "filename_asc"

MediaStatus = Literal[
    "all",
    "available",
    "damaged",
    "used",
    "unused",
    "duplicate",
]
MediaSort = Literal["filename_asc", "filename_desc", "size_asc", "size_desc"]


@dataclass(frozen=True)
class MediaListFilters:
    q: str
    status: MediaStatus
    sort: MediaSort

    @property
    def has_filters(self) -> bool:
        return bool(self.q or self.status != DEFAULT_MEDIA_STATUS)


@dataclass(frozen=True)
class MediaListRow:
    entry: LocalMediaEntry
    used: bool
    duplicate_group: tuple[LocalMediaEntry, ...]

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_group) if self.duplicate_group else 1

    @property
    def duplicate_paths(self) -> tuple[str, ...]:
        return tuple(
            member.media_path
            for member in self.duplicate_group
            if member.media_path != self.entry.media_path
        )


@dataclass(frozen=True)
class MediaDuplicateSummary:
    group_count: int
    file_count: int
    reclaimable_bytes: int


@dataclass(frozen=True)
class MediaListResult:
    rows: tuple[MediaListRow, ...]
    filters: MediaListFilters
    page_info: PageInfo
    duplicate_summary: MediaDuplicateSummary


def _normalize_search(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").strip()
    if len(normalized) > MAX_MEDIA_SEARCH_LENGTH:
        return ""
    return normalized


def normalize_media_list_filters(
    *,
    q: str | None,
    status: str | None,
    sort: str | None,
) -> MediaListFilters:
    normalized_status = status if status in MEDIA_STATUS_OPTIONS else DEFAULT_MEDIA_STATUS
    normalized_sort = sort if sort in MEDIA_SORT_OPTIONS else DEFAULT_MEDIA_SORT
    return MediaListFilters(
        q=_normalize_search(q),
        status=normalized_status,
        sort=normalized_sort,
    )


def _search_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _canonical_sha256(entry: LocalMediaEntry) -> str | None:
    digest = entry.sha256.casefold()
    if (
        not entry.available
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        return None
    return digest


def _build_duplicate_index(
    scan: LocalMediaScan,
) -> tuple[dict[str, tuple[LocalMediaEntry, ...]], MediaDuplicateSummary]:
    entries_by_digest: dict[str, dict[str, LocalMediaEntry]] = {}
    for entry in scan.entries:
        digest = _canonical_sha256(entry)
        if digest is None:
            continue
        entries_by_digest.setdefault(digest, {})[entry.media_path] = entry

    duplicate_groups: list[tuple[LocalMediaEntry, ...]] = []
    for digest in sorted(entries_by_digest):
        entries = entries_by_digest[digest]
        if len(entries) < 2:
            continue
        duplicate_groups.append(
            tuple(
                sorted(
                    entries.values(),
                    key=lambda entry: (_search_key(entry.media_path), entry.media_path),
                )
            )
        )

    index = {
        entry.media_path: group
        for group in duplicate_groups
        for entry in group
    }
    return index, MediaDuplicateSummary(
        group_count=len(duplicate_groups),
        file_count=sum(len(group) for group in duplicate_groups),
        reclaimable_bytes=sum(
            sum(entry.size for entry in group[1:])
            for group in duplicate_groups
        ),
    )


def _matches_status(
    entry: LocalMediaEntry,
    *,
    used: bool,
    duplicate: bool,
    status: MediaStatus,
) -> bool:
    if status == "available":
        return entry.available
    if status == "damaged":
        return not entry.available
    if status == "used":
        return used
    if status == "unused":
        return not used
    if status == "duplicate":
        return duplicate
    return True


def _sort_rows(rows: list[MediaListRow], sort: MediaSort) -> None:
    def filename_key(row: MediaListRow) -> tuple[str, str]:
        return (_search_key(row.entry.filename), row.entry.media_path)

    if sort == "filename_desc":
        rows.sort(key=filename_key, reverse=True)
    elif sort == "size_asc":
        rows.sort(
            key=lambda row: (
                row.entry.size,
                _search_key(row.entry.filename),
                row.entry.media_path,
            )
        )
    elif sort == "size_desc":
        rows.sort(
            key=lambda row: (
                -row.entry.size,
                _search_key(row.entry.filename),
                row.entry.media_path,
            )
        )
    else:
        rows.sort(key=filename_key)


def query_media_library(
    scan: LocalMediaScan,
    used_paths: Collection[str],
    *,
    q: str | None,
    status: str | None,
    sort: str | None,
    page: str | int | None,
) -> MediaListResult:
    filters = normalize_media_list_filters(q=q, status=status, sort=sort)
    search_key = _search_key(filters.q)
    used = set(used_paths)
    duplicate_index, duplicate_summary = _build_duplicate_index(scan)
    rows: list[MediaListRow] = []
    for entry in scan.entries:
        digest = _canonical_sha256(entry)
        duplicate_group = duplicate_index.get(entry.media_path)
        if search_key and not (
            search_key in _search_key(entry.filename)
            or search_key in _search_key(entry.media_path)
            or (digest is not None and digest.startswith(search_key))
        ):
            continue
        if not _matches_status(
            entry,
            used=entry.media_path in used,
            duplicate=duplicate_group is not None,
            status=filters.status,
        ):
            continue
        rows.append(
            MediaListRow(
                entry=entry,
                used=entry.media_path in used,
                duplicate_group=duplicate_group or (),
            )
        )
    _sort_rows(rows, filters.sort)
    page_info = build_page_info(
        page=page,
        page_size=MEDIA_LIST_PAGE_SIZE,
        total=len(rows),
    )
    start = (page_info.page - 1) * page_info.page_size
    end = start + page_info.page_size
    return MediaListResult(
        rows=tuple(rows[start:end]),
        filters=filters,
        page_info=page_info,
        duplicate_summary=duplicate_summary,
    )


def media_filter_query_params(filters: MediaListFilters) -> dict[str, str]:
    params: dict[str, str] = {}
    if filters.q:
        params["media_q"] = filters.q
    if filters.status != DEFAULT_MEDIA_STATUS:
        params["media_status"] = filters.status
    if filters.sort != DEFAULT_MEDIA_SORT:
        params["media_sort"] = filters.sort
    return params
