from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal

from app.services.local_media import LocalMediaEntry, LocalMediaScan
from app.services.pagination import PageInfo, build_page_info


MEDIA_DUPLICATE_GROUP_PAGE_SIZE = 20
MAX_MEDIA_SEARCH_LENGTH = 200
MEDIA_DUPLICATE_SORT_OPTIONS = (
    "members_asc",
    "members_desc",
    "reclaimable_asc",
    "reclaimable_desc",
    "sha256_asc",
    "sha256_desc",
)
DEFAULT_MEDIA_DUPLICATE_SORT = "members_desc"

MediaDuplicateSort = Literal[
    "members_asc",
    "members_desc",
    "reclaimable_asc",
    "reclaimable_desc",
    "sha256_asc",
    "sha256_desc",
]


@dataclass(frozen=True)
class MediaDuplicateGroup:
    sha256: str
    entries: tuple[LocalMediaEntry, ...]

    @property
    def member_count(self) -> int:
        return len(self.entries)

    @property
    def file_size(self) -> int:
        return self.entries[0].size

    @property
    def total_bytes(self) -> int:
        return sum(entry.size for entry in self.entries)

    @property
    def reclaimable_bytes(self) -> int:
        return sum(entry.size for entry in self.entries[1:])


@dataclass(frozen=True)
class MediaDuplicateSummary:
    group_count: int
    file_count: int
    reclaimable_bytes: int


@dataclass(frozen=True)
class MediaDuplicateFilters:
    q: str
    sort: MediaDuplicateSort


@dataclass(frozen=True)
class MediaDuplicateGroupResult:
    groups: tuple[MediaDuplicateGroup, ...]
    filters: MediaDuplicateFilters
    page_info: PageInfo
    total_groups: int


def normalize_media_search(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").strip()
    if len(normalized) > MAX_MEDIA_SEARCH_LENGTH:
        return ""
    return normalized


def media_search_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def valid_media_sha256(entry: LocalMediaEntry) -> str | None:
    digest = entry.sha256.casefold()
    if (
        not entry.available
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        return None
    return digest


def build_media_duplicate_groups(
    scan: LocalMediaScan,
) -> tuple[MediaDuplicateGroup, ...]:
    entries_by_digest: dict[str, dict[str, LocalMediaEntry]] = {}
    for entry in scan.entries:
        digest = valid_media_sha256(entry)
        if digest is None:
            continue
        entries_by_digest.setdefault(digest, {})[entry.media_path] = entry

    groups: list[MediaDuplicateGroup] = []
    for digest in sorted(entries_by_digest):
        entries = entries_by_digest[digest]
        if len(entries) < 2:
            continue
        groups.append(
            MediaDuplicateGroup(
                sha256=digest,
                entries=tuple(
                    sorted(
                        entries.values(),
                        key=lambda entry: (
                            media_search_key(entry.media_path),
                            entry.media_path,
                        ),
                    )
                ),
            )
        )
    return tuple(groups)


def find_media_duplicate_group(
    scan: LocalMediaScan,
    sha256: str | None,
) -> MediaDuplicateGroup | None:
    digest = (sha256 or "").strip().casefold()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        return None
    return next(
        (
            group
            for group in build_media_duplicate_groups(scan)
            if group.sha256 == digest
        ),
        None,
    )


def summarize_media_duplicate_groups(
    groups: tuple[MediaDuplicateGroup, ...],
) -> MediaDuplicateSummary:
    return MediaDuplicateSummary(
        group_count=len(groups),
        file_count=sum(group.member_count for group in groups),
        reclaimable_bytes=sum(group.reclaimable_bytes for group in groups),
    )


def normalize_media_duplicate_filters(
    *,
    q: str | None,
    sort: str | None,
) -> MediaDuplicateFilters:
    normalized_sort = (
        sort
        if sort in MEDIA_DUPLICATE_SORT_OPTIONS
        else DEFAULT_MEDIA_DUPLICATE_SORT
    )
    return MediaDuplicateFilters(
        q=normalize_media_search(q),
        sort=normalized_sort,
    )


def _sort_duplicate_groups(
    groups: list[MediaDuplicateGroup],
    sort: MediaDuplicateSort,
) -> None:
    if sort == "members_asc":
        groups.sort(key=lambda group: (group.member_count, group.sha256))
    elif sort == "reclaimable_asc":
        groups.sort(key=lambda group: (group.reclaimable_bytes, group.sha256))
    elif sort == "reclaimable_desc":
        groups.sort(key=lambda group: (-group.reclaimable_bytes, group.sha256))
    elif sort == "sha256_asc":
        groups.sort(key=lambda group: group.sha256)
    elif sort == "sha256_desc":
        groups.sort(key=lambda group: group.sha256, reverse=True)
    else:
        groups.sort(key=lambda group: (-group.member_count, group.sha256))


def query_media_duplicate_groups(
    scan: LocalMediaScan,
    *,
    q: str | None,
    sort: str | None,
    page: str | int | None,
) -> MediaDuplicateGroupResult:
    filters = normalize_media_duplicate_filters(q=q, sort=sort)
    search_key = media_search_key(filters.q)
    all_groups = build_media_duplicate_groups(scan)
    groups = [
        group
        for group in all_groups
        if not search_key
        or group.sha256.startswith(search_key)
        or any(
            search_key in media_search_key(entry.filename)
            or search_key in media_search_key(entry.media_path)
            for entry in group.entries
        )
    ]
    _sort_duplicate_groups(groups, filters.sort)
    page_info = build_page_info(
        page=page,
        page_size=MEDIA_DUPLICATE_GROUP_PAGE_SIZE,
        total=len(groups),
    )
    start = (page_info.page - 1) * page_info.page_size
    end = start + page_info.page_size
    return MediaDuplicateGroupResult(
        groups=tuple(groups[start:end]),
        filters=filters,
        page_info=page_info,
        total_groups=len(all_groups),
    )


def media_duplicate_filter_query_params(
    filters: MediaDuplicateFilters,
) -> dict[str, str]:
    params: dict[str, str] = {}
    if filters.q:
        params["duplicate_q"] = filters.q
    if filters.sort != DEFAULT_MEDIA_DUPLICATE_SORT:
        params["duplicate_sort"] = filters.sort
    return params
