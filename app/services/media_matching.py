from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Literal, Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Creator, Item
from app.services import local_media
from app.services.local_media import LocalMediaEntry, LocalMediaScan
from app.services.pagination import PageInfo, build_page_info


MEDIA_MATCH_PAGE_SIZE = 20
_ROLE_SUFFIX_RE = re.compile(r"^(.*?)[._\-\s]+(cover|avatar)$", re.IGNORECASE)

TargetType = Literal["item", "creator"]


class MediaMatchError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MediaMatchCandidate:
    candidate_id: str
    media_path: str
    filename: str
    target_type: TargetType
    target_id: int
    target_name: str
    reason: str
    confidence: str
    conflicts: tuple[str, ...] = ()

    @property
    def can_apply(self) -> bool:
        return not self.conflicts


@dataclass(frozen=True)
class MediaMatchScan:
    candidates: tuple[MediaMatchCandidate, ...]
    unused_media: int
    unmatched_media: int
    empty_items: int
    empty_creators: int

    @property
    def ready(self) -> int:
        return sum(candidate.can_apply for candidate in self.candidates)

    @property
    def conflicts(self) -> int:
        return len(self.candidates) - self.ready


@dataclass(frozen=True)
class MediaMatchPage:
    rows: tuple[MediaMatchCandidate, ...]
    page_info: PageInfo


@dataclass(frozen=True)
class MediaMatchApplyResult:
    applied: int


@dataclass(frozen=True)
class _Target:
    target_type: TargetType
    target_id: int
    name: str


def normalize_match_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _exact_match_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _filename_match_parts(filename: str) -> tuple[str, TargetType | None]:
    stem = PurePosixPath(filename).stem.strip()
    matched = _ROLE_SUFFIX_RE.fullmatch(stem)
    if matched is None or not matched.group(1).strip():
        return stem, None
    role: TargetType = "item" if matched.group(2).casefold() == "cover" else "creator"
    return matched.group(1).strip(), role


def _candidate_id(
    *,
    media_path: str,
    target_type: TargetType,
    target_id: int,
    reason: str,
) -> str:
    payload = f"{media_path}\0{target_type}\0{target_id}\0{reason}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def _candidate_for(
    entry: LocalMediaEntry,
    target: _Target,
    reason: str,
) -> MediaMatchCandidate:
    confidence = "high" if reason in {"exact", "suffix_exact"} else "medium"
    return MediaMatchCandidate(
        candidate_id=_candidate_id(
            media_path=entry.media_path,
            target_type=target.target_type,
            target_id=target.target_id,
            reason=reason,
        ),
        media_path=entry.media_path,
        filename=entry.filename,
        target_type=target.target_type,
        target_id=target.target_id,
        target_name=target.name,
        reason=reason,
        confidence=confidence,
    )


def _entry_candidates(
    entry: LocalMediaEntry,
    targets: Sequence[_Target],
) -> list[MediaMatchCandidate]:
    match_name, role = _filename_match_parts(entry.filename)
    if not match_name:
        return []
    eligible = [target for target in targets if role is None or target.target_type == role]
    exact_key = _exact_match_name(match_name)
    exact_targets = [
        target for target in eligible if _exact_match_name(target.name) == exact_key
    ]
    suffix = "suffix_" if role is not None else ""
    if exact_targets:
        return [
            _candidate_for(entry, target, f"{suffix}exact")
            for target in exact_targets
        ]

    normalized_key = normalize_match_name(match_name)
    if not normalized_key:
        return []
    normalized_targets = [
        target
        for target in eligible
        if normalize_match_name(target.name) == normalized_key
    ]
    return [
        _candidate_for(entry, target, f"{suffix}normalized")
        for target in normalized_targets
    ]


def match_local_media(
    scan: LocalMediaScan,
    items: Sequence[Item],
    creators: Sequence[Creator],
) -> MediaMatchScan:
    used_paths = {
        value
        for value in [
            *(item.cover_path for item in items),
            *(creator.avatar_path for creator in creators),
        ]
        if value
    }
    empty_items = [item for item in items if not item.cover_path]
    empty_creators = [creator for creator in creators if not creator.avatar_path]
    targets = [
        *(_Target("item", item.id, item.title) for item in empty_items),
        *(_Target("creator", creator.id, creator.name) for creator in empty_creators),
    ]
    unused_entries = [
        entry
        for entry in scan.entries
        if entry.available and entry.media_path not in used_paths
    ]

    candidates: list[MediaMatchCandidate] = []
    matched_media: set[str] = set()
    for entry in unused_entries:
        entry_matches = _entry_candidates(entry, targets)
        if entry_matches:
            matched_media.add(entry.media_path)
            candidates.extend(entry_matches)

    media_counts = Counter(candidate.media_path for candidate in candidates)
    target_counts = Counter(
        (candidate.target_type, candidate.target_id) for candidate in candidates
    )
    classified: list[MediaMatchCandidate] = []
    for candidate in candidates:
        conflicts: list[str] = []
        if media_counts[candidate.media_path] > 1:
            conflicts.append("media_multiple_targets")
        if target_counts[(candidate.target_type, candidate.target_id)] > 1:
            conflicts.append("target_multiple_media")
        classified.append(replace(candidate, conflicts=tuple(conflicts)))

    classified.sort(
        key=lambda candidate: (
            candidate.filename.casefold(),
            candidate.target_type,
            candidate.target_name.casefold(),
            candidate.target_id,
        )
    )
    return MediaMatchScan(
        candidates=tuple(classified),
        unused_media=len(unused_entries),
        unmatched_media=len(unused_entries) - len(matched_media),
        empty_items=len(empty_items),
        empty_creators=len(empty_creators),
    )


def build_local_media_matches(db: Session) -> MediaMatchScan:
    scan = local_media.scan_local_media()
    items = list(db.scalars(select(Item).order_by(Item.title, Item.id)).all())
    creators = list(
        db.scalars(select(Creator).order_by(Creator.name, Creator.id)).all()
    )
    return match_local_media(scan, items, creators)


def paginate_media_matches(
    match_scan: MediaMatchScan,
    page: str | int | None,
) -> MediaMatchPage:
    page_info = build_page_info(
        page=page,
        page_size=MEDIA_MATCH_PAGE_SIZE,
        total=len(match_scan.candidates),
    )
    start = (page_info.page - 1) * page_info.page_size
    end = start + page_info.page_size
    return MediaMatchPage(match_scan.candidates[start:end], page_info)


def apply_local_media_matches(
    db: Session,
    candidate_ids: Sequence[str] | None,
    *,
    current_page: str | int | None = None,
) -> MediaMatchApplyResult:
    selected_ids = tuple(dict.fromkeys(candidate_ids or ()))
    if not selected_ids:
        raise MediaMatchError("no_selection")
    if len(selected_ids) > MEDIA_MATCH_PAGE_SIZE:
        raise MediaMatchError("outside_current_page")

    match_scan = build_local_media_matches(db)
    by_id = {candidate.candidate_id: candidate for candidate in match_scan.candidates}
    try:
        selected = [by_id[candidate_id] for candidate_id in selected_ids]
    except KeyError as exc:
        raise MediaMatchError("stale_candidate") from exc

    if current_page is not None:
        page = paginate_media_matches(match_scan, current_page)
        page_ids = {candidate.candidate_id for candidate in page.rows}
        if not set(selected_ids).issubset(page_ids):
            raise MediaMatchError("outside_current_page")
    if any(not candidate.can_apply for candidate in selected):
        raise MediaMatchError("conflict")

    try:
        for candidate in selected:
            local_media.resolve_local_media_file(
                candidate.media_path.removeprefix(local_media.LOCAL_MEDIA_PREFIX)
            )
        for candidate in selected:
            if candidate.target_type == "item":
                statement = (
                    update(Item)
                    .where(Item.id == candidate.target_id, Item.cover_path.is_(None))
                    .values(cover_path=candidate.media_path)
                )
            else:
                statement = (
                    update(Creator)
                    .where(
                        Creator.id == candidate.target_id,
                        Creator.avatar_path.is_(None),
                    )
                    .values(avatar_path=candidate.media_path)
                )
            if db.execute(statement).rowcount != 1:
                raise MediaMatchError("target_already_assigned")
        db.commit()
    except MediaMatchError:
        db.rollback()
        raise
    except (local_media.LocalMediaPathError, OSError) as exc:
        db.rollback()
        raise MediaMatchError("stale_candidate") from exc
    except Exception as exc:
        db.rollback()
        raise MediaMatchError("apply_failed") from exc
    return MediaMatchApplyResult(applied=len(selected))
