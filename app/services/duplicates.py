from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.services.catalog import serialize_extra


class DuplicateError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class DuplicateCandidateGroup:
    match_type: str
    match_key: str
    items: list[models.Item]


@dataclass(frozen=True)
class DuplicateComparison:
    primary: models.Item
    duplicate: models.Item
    primary_extra: dict[str, Any] | None
    duplicate_extra: dict[str, Any] | None
    summary_conflict: bool
    status_conflict: bool
    rating_conflict: bool
    review_conflict: bool
    extra_merge_keys: list[str]
    extra_conflict_keys: list[str]


@dataclass(frozen=True)
class DuplicateMergeResult:
    primary_id: int
    primary_title: str
    duplicate_title: str
    tags_transferred: int
    creators_transferred: int
    collections_transferred: int
    summary_action: str
    status_action: str
    rating_action: str
    review_action: str
    extra_keys_merged: int
    extra_conflicts_kept: int
    duplicate_deleted: bool


def exact_title_key(title: str) -> str:
    return title.strip()


def normalized_title_key(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title)
    normalized = re.sub(r"\s+", " ", normalized.strip())
    return normalized.casefold()


def _load_items(db: Session) -> list[models.Item]:
    return list(
        db.scalars(
            select(models.Item)
            .options(
                selectinload(models.Item.tags),
                selectinload(models.Item.creators),
                selectinload(models.Item.collections),
                selectinload(models.Item.state),
            )
            .order_by(models.Item.title.asc(), models.Item.id.asc())
        ).all()
    )


def _candidate_groups(
    items: list[models.Item],
    *,
    match_type: str,
    key_func: Any,
) -> list[DuplicateCandidateGroup]:
    buckets: dict[str, list[models.Item]] = {}
    for item in items:
        key = key_func(item.title)
        if key:
            buckets.setdefault(key, []).append(item)
    groups = [
        DuplicateCandidateGroup(
            match_type=match_type,
            match_key=key,
            items=sorted(bucket, key=lambda row: row.id),
        )
        for key, bucket in buckets.items()
        if len(bucket) > 1
    ]
    return sorted(groups, key=lambda group: (group.match_key, group.items[0].id))


def find_duplicate_candidates(db: Session) -> list[DuplicateCandidateGroup]:
    items = _load_items(db)
    groups = _candidate_groups(
        items,
        match_type="exact_title",
        key_func=exact_title_key,
    )
    exact_sets = {frozenset(item.id for item in group.items) for group in groups}
    for group in _candidate_groups(
        items,
        match_type="normalized_title",
        key_func=normalized_title_key,
    ):
        item_ids = frozenset(item.id for item in group.items)
        if item_ids not in exact_sets:
            groups.append(group)
    return groups


def _parse_item_id(value: str | int | None) -> int:
    try:
        item_id = int(value) if value not in {None, ""} else 0
    except (TypeError, ValueError) as exc:
        raise DuplicateError("invalid_item") from exc
    if item_id <= 0:
        raise DuplicateError("invalid_item")
    return item_id


def _get_item(db: Session, item_id: int) -> models.Item:
    item = db.scalar(
        select(models.Item)
        .where(models.Item.id == item_id)
        .options(
            selectinload(models.Item.tags),
            selectinload(models.Item.creators),
            selectinload(models.Item.collections),
            selectinload(models.Item.state),
        )
    )
    if item is None:
        raise DuplicateError("item_not_found")
    return item


def _json_object(value: str | None) -> tuple[dict[str, Any] | None, bool]:
    if not value:
        return None, False
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}, True
    if isinstance(parsed, dict):
        return parsed, True
    return {"value": parsed}, True


def _clean_optional(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def get_duplicate_comparison(
    db: Session,
    primary_id: str | int | None,
    duplicate_id: str | int | None,
) -> DuplicateComparison:
    parsed_primary_id = _parse_item_id(primary_id)
    parsed_duplicate_id = _parse_item_id(duplicate_id)
    if parsed_primary_id == parsed_duplicate_id:
        raise DuplicateError("same_item")

    primary = _get_item(db, parsed_primary_id)
    duplicate = _get_item(db, parsed_duplicate_id)
    primary_extra, primary_has_extra = _json_object(primary.extra)
    duplicate_extra, duplicate_has_extra = _json_object(duplicate.extra)
    primary_extra_keys = set(primary_extra or {})
    duplicate_extra_keys = set(duplicate_extra or {})
    conflict_keys = (
        [
            key
            for key in sorted(primary_extra_keys & duplicate_extra_keys)
            if (primary_extra or {}).get(key) != (duplicate_extra or {}).get(key)
        ]
        if primary_has_extra and duplicate_has_extra
        else []
    )
    merge_keys = (
        sorted(duplicate_extra_keys - primary_extra_keys)
        if primary_has_extra and duplicate_has_extra
        else sorted(duplicate_extra_keys)
        if duplicate_has_extra and not primary_has_extra
        else []
    )

    return DuplicateComparison(
        primary=primary,
        duplicate=duplicate,
        primary_extra=primary_extra,
        duplicate_extra=duplicate_extra,
        summary_conflict=bool(
            _clean_optional(primary.summary)
            and _clean_optional(duplicate.summary)
            and _clean_optional(primary.summary) != _clean_optional(duplicate.summary)
        ),
        status_conflict=bool(
            primary.state
            and duplicate.state
            and primary.state.status != duplicate.state.status
        ),
        rating_conflict=bool(
            primary.state
            and duplicate.state
            and primary.state.rating != duplicate.state.rating
        ),
        review_conflict=bool(
            primary.state
            and duplicate.state
            and _clean_optional(primary.state.review)
            != _clean_optional(duplicate.state.review)
        ),
        extra_merge_keys=merge_keys,
        extra_conflict_keys=conflict_keys,
    )


def _transfer_relation(
    primary_relations: list[Any],
    duplicate_relations: list[Any],
) -> int:
    existing_ids = {relation.id for relation in primary_relations}
    transferred = 0
    for relation in duplicate_relations:
        if relation.id not in existing_ids:
            primary_relations.append(relation)
            existing_ids.add(relation.id)
            transferred += 1
    duplicate_relations.clear()
    return transferred


def _apply_summary(
    primary: models.Item,
    duplicate: models.Item,
    *,
    use_duplicate_summary: bool,
) -> str:
    primary_summary = _clean_optional(primary.summary)
    duplicate_summary = _clean_optional(duplicate.summary)
    if not primary_summary and duplicate_summary:
        primary.summary = duplicate.summary
        return "copied"
    if (
        use_duplicate_summary
        and duplicate_summary
        and primary_summary != duplicate_summary
    ):
        primary.summary = duplicate.summary
        return "overwritten"
    if primary_summary and duplicate_summary and primary_summary != duplicate_summary:
        return "kept_primary"
    return "unchanged"


def _copy_state(source: models.UserItemState, target_item_id: int) -> models.UserItemState:
    return models.UserItemState(
        item_id=target_item_id,
        status=source.status,
        rating=source.rating,
        review=source.review,
    )


def _apply_state(
    db: Session,
    primary: models.Item,
    duplicate: models.Item,
    *,
    use_duplicate_status: bool,
    use_duplicate_rating: bool,
    use_duplicate_review: bool,
) -> tuple[str, str, str]:
    if duplicate.state is None:
        return "unchanged", "unchanged", "unchanged"
    if primary.state is None:
        primary.state = _copy_state(duplicate.state, primary.id)
        db.add(primary.state)
        return "copied", "copied", "copied"

    status_action = (
        "kept_primary" if primary.state.status != duplicate.state.status else "unchanged"
    )
    rating_action = (
        "kept_primary" if primary.state.rating != duplicate.state.rating else "unchanged"
    )
    review_action = (
        "kept_primary"
        if _clean_optional(primary.state.review) != _clean_optional(duplicate.state.review)
        else "unchanged"
    )

    if use_duplicate_status:
        primary.state.status = duplicate.state.status
        status_action = "overwritten"
    if use_duplicate_rating:
        primary.state.rating = duplicate.state.rating
        rating_action = "overwritten"
    if use_duplicate_review:
        primary.state.review = duplicate.state.review
        review_action = "overwritten"
    return status_action, rating_action, review_action


def _apply_extra(primary: models.Item, duplicate: models.Item) -> tuple[int, int]:
    primary_extra, primary_has_extra = _json_object(primary.extra)
    duplicate_extra, duplicate_has_extra = _json_object(duplicate.extra)
    if not duplicate_has_extra or duplicate_extra is None:
        return 0, 0
    if not primary_has_extra or primary_extra is None:
        primary.extra = serialize_extra(duplicate_extra)
        return len(duplicate_extra), 0

    merged = dict(primary_extra)
    merged_count = 0
    conflict_count = 0
    for key, value in duplicate_extra.items():
        if key not in merged:
            merged[key] = value
            merged_count += 1
        elif merged[key] != value:
            conflict_count += 1
    primary.extra = serialize_extra(merged)
    return merged_count, conflict_count


def merge_duplicate_items(
    db: Session,
    *,
    primary_id: str | int | None,
    duplicate_id: str | int | None,
    use_duplicate_summary: bool = False,
    use_duplicate_status: bool = False,
    use_duplicate_rating: bool = False,
    use_duplicate_review: bool = False,
) -> DuplicateMergeResult:
    try:
        comparison = get_duplicate_comparison(db, primary_id, duplicate_id)
        primary = comparison.primary
        duplicate = comparison.duplicate
        duplicate_title = duplicate.title

        tags_transferred = _transfer_relation(primary.tags, duplicate.tags)
        creators_transferred = _transfer_relation(primary.creators, duplicate.creators)
        collections_transferred = _transfer_relation(
            primary.collections,
            duplicate.collections,
        )
        summary_action = _apply_summary(
            primary,
            duplicate,
            use_duplicate_summary=use_duplicate_summary,
        )
        status_action, rating_action, review_action = _apply_state(
            db,
            primary,
            duplicate,
            use_duplicate_status=use_duplicate_status,
            use_duplicate_rating=use_duplicate_rating,
            use_duplicate_review=use_duplicate_review,
        )
        extra_keys_merged, extra_conflicts_kept = _apply_extra(primary, duplicate)

        db.delete(duplicate)
        db.commit()
        db.refresh(primary)
        return DuplicateMergeResult(
            primary_id=primary.id,
            primary_title=primary.title,
            duplicate_title=duplicate_title,
            tags_transferred=tags_transferred,
            creators_transferred=creators_transferred,
            collections_transferred=collections_transferred,
            summary_action=summary_action,
            status_action=status_action,
            rating_action=rating_action,
            review_action=review_action,
            extra_keys_merged=extra_keys_merged,
            extra_conflicts_kept=extra_conflicts_kept,
            duplicate_deleted=True,
        )
    except DuplicateError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise DuplicateError("merge_failed") from exc
