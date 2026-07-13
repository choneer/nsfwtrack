from __future__ import annotations

import hashlib
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services import local_media
from app.services.local_media import LocalMediaEntry, LocalMediaScan
from app.services.media_matching import (
    MEDIA_MATCH_PAGE_SIZE,
    filename_match_parts,
    match_local_media,
    normalize_match_name,
)
from app.services.pagination import PageInfo, build_page_info


MEDIA_ITEM_CANDIDATE_PAGE_SIZE = MEDIA_MATCH_PAGE_SIZE
MAX_ITEM_TITLE_LENGTH = 255


class MediaItemCandidateError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaItemCandidate:
    candidate_id: str
    media_path: str
    filename: str
    suggested_title: str
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class MediaItemCandidateScan:
    candidates: tuple[MediaItemCandidate, ...]
    eligible_media: int
    excluded_matched: int
    excluded_avatar: int

    @property
    def conflicts(self) -> int:
        return sum(bool(candidate.conflicts) for candidate in self.candidates)


@dataclass(frozen=True)
class MediaItemCandidatePage:
    rows: tuple[MediaItemCandidate, ...]
    page_info: PageInfo


@dataclass(frozen=True)
class MediaItemCreateResult:
    created: int
    item_ids: tuple[int, ...]


def _exact_title_key(title: str) -> str:
    return unicodedata.normalize("NFKC", title).strip().casefold()


def _title_conflict_key(title: str) -> str:
    return normalize_match_name(title) or _exact_title_key(title)


def _candidate_id(media_path: str) -> str:
    return hashlib.sha256(f"{media_path}\0create_item".encode("utf-8")).hexdigest()[:24]


def _candidate_for(entry: LocalMediaEntry, title: str) -> MediaItemCandidate:
    return MediaItemCandidate(
        candidate_id=_candidate_id(entry.media_path),
        media_path=entry.media_path,
        filename=entry.filename,
        suggested_title=title,
    )


def find_media_item_candidates(
    scan: LocalMediaScan,
    items: Sequence[Item],
    creators: Sequence[Creator],
) -> MediaItemCandidateScan:
    used_paths = {
        path
        for path in [
            *(item.cover_path for item in items),
            *(creator.avatar_path for creator in creators),
        ]
        if path
    }
    matched_paths = {
        candidate.media_path
        for candidate in match_local_media(scan, items, creators).candidates
    }
    existing_exact = {_exact_title_key(item.title) for item in items}
    existing_normalized = {_title_conflict_key(item.title) for item in items}

    candidates: list[MediaItemCandidate] = []
    excluded_matched = 0
    excluded_avatar = 0
    for entry in scan.entries:
        if not entry.available or entry.media_path in used_paths:
            continue
        if entry.media_path in matched_paths:
            excluded_matched += 1
            continue
        title, role = filename_match_parts(entry.filename)
        if role == "creator":
            excluded_avatar += 1
            continue
        candidates.append(_candidate_for(entry, title))

    default_counts = Counter(
        _title_conflict_key(candidate.suggested_title)
        for candidate in candidates
        if candidate.suggested_title.strip()
    )
    classified: list[MediaItemCandidate] = []
    for candidate in candidates:
        conflicts: list[str] = []
        title = candidate.suggested_title.strip()
        if not title or len(title) > MAX_ITEM_TITLE_LENGTH:
            conflicts.append("invalid_title")
        else:
            exact_key = _exact_title_key(title)
            normalized_key = _title_conflict_key(title)
            if exact_key in existing_exact:
                conflicts.append("existing_title")
            elif normalized_key in existing_normalized:
                conflicts.append("existing_normalized_title")
            if default_counts[normalized_key] > 1:
                conflicts.append("batch_title")
        classified.append(replace(candidate, conflicts=tuple(conflicts)))

    classified.sort(key=lambda candidate: (candidate.filename.casefold(), candidate.media_path))
    return MediaItemCandidateScan(
        candidates=tuple(classified),
        eligible_media=len(classified),
        excluded_matched=excluded_matched,
        excluded_avatar=excluded_avatar,
    )


def build_media_item_candidates(db: Session) -> MediaItemCandidateScan:
    scan = local_media.scan_local_media()
    items = list(db.scalars(select(Item).order_by(Item.title, Item.id)).all())
    creators = list(
        db.scalars(select(Creator).order_by(Creator.name, Creator.id)).all()
    )
    return find_media_item_candidates(scan, items, creators)


def paginate_media_item_candidates(
    candidate_scan: MediaItemCandidateScan,
    page: str | int | None,
) -> MediaItemCandidatePage:
    page_info = build_page_info(
        page=page,
        page_size=MEDIA_ITEM_CANDIDATE_PAGE_SIZE,
        total=len(candidate_scan.candidates),
    )
    start = (page_info.page - 1) * page_info.page_size
    end = start + page_info.page_size
    return MediaItemCandidatePage(candidate_scan.candidates[start:end], page_info)


def _clean_titles(titles: Sequence[str]) -> tuple[str, ...]:
    cleaned = tuple(title.strip() for title in titles)
    if any(not title or len(title) > MAX_ITEM_TITLE_LENGTH for title in cleaned):
        raise MediaItemCandidateError("invalid_title")
    return cleaned


def create_items_from_media_candidates(
    db: Session,
    candidate_ids: Sequence[str] | None,
    titles: Sequence[str] | None,
    *,
    current_page: str | int | None,
) -> MediaItemCreateResult:
    selected_ids = tuple(candidate_ids or ())
    submitted_titles = tuple(titles or ())
    if not selected_ids:
        raise MediaItemCandidateError("no_selection")
    if (
        len(selected_ids) != len(submitted_titles)
        or len(selected_ids) > MEDIA_ITEM_CANDIDATE_PAGE_SIZE
        or len(set(selected_ids)) != len(selected_ids)
    ):
        raise MediaItemCandidateError("invalid_payload")
    cleaned_titles = _clean_titles(submitted_titles)

    try:
        candidate_scan = build_media_item_candidates(db)
        candidate_page = paginate_media_item_candidates(candidate_scan, current_page)
        candidates_by_id = {
            candidate.candidate_id: candidate
            for candidate in candidate_scan.candidates
        }
        try:
            selected = [
                candidates_by_id[candidate_id] for candidate_id in selected_ids
            ]
        except KeyError as exc:
            raise MediaItemCandidateError("stale_candidate") from exc
        page_ids = {candidate.candidate_id for candidate in candidate_page.rows}
        if not set(selected_ids).issubset(page_ids):
            raise MediaItemCandidateError("outside_current_page")

        title_keys = [_title_conflict_key(title) for title in cleaned_titles]
        if len(set(title_keys)) != len(title_keys):
            raise MediaItemCandidateError("batch_title")

        existing_titles = tuple(db.scalars(select(Item.title)).all())
        existing_exact = {_exact_title_key(title) for title in existing_titles}
        existing_normalized = {
            _title_conflict_key(title) for title in existing_titles
        }
        for title, normalized_key in zip(cleaned_titles, title_keys, strict=True):
            if _exact_title_key(title) in existing_exact:
                raise MediaItemCandidateError("existing_title")
            if normalized_key in existing_normalized:
                raise MediaItemCandidateError("existing_normalized_title")

        for candidate in selected:
            local_media.resolve_local_media_file(
                candidate.media_path.removeprefix(local_media.LOCAL_MEDIA_PREFIX)
            )
        new_items = [
            Item(title=title, cover_path=candidate.media_path)
            for candidate, title in zip(selected, cleaned_titles, strict=True)
        ]
        db.add_all(new_items)
        db.flush()
        item_ids = tuple(item.id for item in new_items)
        db.commit()
    except MediaItemCandidateError:
        db.rollback()
        raise
    except (local_media.LocalMediaPathError, OSError) as exc:
        db.rollback()
        raise MediaItemCandidateError("stale_candidate") from exc
    except Exception as exc:
        db.rollback()
        raise MediaItemCandidateError("create_failed") from exc
    return MediaItemCreateResult(created=len(item_ids), item_ids=item_ids)
