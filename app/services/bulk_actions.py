from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Collection, Item, Tag, UserItemState
from app.services.item_query import MIN_RATING_OPTIONS, STATUS_OPTIONS


class BulkActionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BulkActionResult:
    processed: int
    skipped: int
    item_ids: tuple[int, ...] = ()

    @property
    def ok(self) -> bool:
        return True


def normalize_item_ids(raw_item_ids: Iterable[str | int] | None) -> list[int]:
    if raw_item_ids is None:
        raise BulkActionError("no_selection")

    item_ids: list[int] = []
    seen: set[int] = set()
    for raw_item_id in raw_item_ids:
        try:
            item_id = int(raw_item_id)
        except (TypeError, ValueError):
            continue
        if item_id > 0 and item_id not in seen:
            seen.add(item_id)
            item_ids.append(item_id)

    if not item_ids:
        raise BulkActionError("no_selection")
    return item_ids


def _load_items(db: Session, item_ids: list[int]) -> list[Item]:
    return list(
        db.scalars(
            select(Item)
            .where(Item.id.in_(item_ids))
            .options(
                selectinload(Item.tags),
                selectinload(Item.creators),
                selectinload(Item.collections),
                selectinload(Item.state),
            )
        ).all()
    )


def _result(item_ids: list[int], items: list[Item]) -> BulkActionResult:
    return BulkActionResult(
        processed=len(items),
        skipped=max(len(item_ids) - len(items), 0),
        item_ids=tuple(item.id for item in items),
    )


def set_items_status(
    db: Session,
    raw_item_ids: Iterable[str | int] | None,
    status_value: str | None,
) -> BulkActionResult:
    item_ids = normalize_item_ids(raw_item_ids)
    if status_value not in STATUS_OPTIONS:
        raise BulkActionError("invalid_status")

    items = _load_items(db, item_ids)
    for item in items:
        if item.state is None:
            db.add(UserItemState(item_id=item.id, status=status_value))
        else:
            item.state.status = status_value
    db.commit()
    return _result(item_ids, items)


def _get_existing_tag(db: Session, raw_tag_id: str | int | None) -> Tag:
    try:
        tag_id = int(raw_tag_id) if raw_tag_id not in {None, ""} else 0
    except (TypeError, ValueError):
        tag_id = 0
    if tag_id <= 0:
        raise BulkActionError("tag_required")

    tag = db.get(Tag, tag_id)
    if tag is None:
        raise BulkActionError("tag_not_found")
    return tag


def _get_existing_collection(
    db: Session,
    raw_collection_id: str | int | None,
) -> Collection:
    try:
        collection_id = int(raw_collection_id) if raw_collection_id not in {None, ""} else 0
    except (TypeError, ValueError):
        collection_id = 0
    if collection_id <= 0:
        raise BulkActionError("collection_required")

    collection = db.get(Collection, collection_id)
    if collection is None:
        raise BulkActionError("collection_not_found")
    return collection


def add_items_tag(
    db: Session,
    raw_item_ids: Iterable[str | int] | None,
    raw_tag_id: str | int | None,
) -> BulkActionResult:
    item_ids = normalize_item_ids(raw_item_ids)
    tag = _get_existing_tag(db, raw_tag_id)
    items = _load_items(db, item_ids)

    for item in items:
        if all(existing_tag.id != tag.id for existing_tag in item.tags):
            item.tags.append(tag)
    db.commit()
    return _result(item_ids, items)


def remove_items_tag(
    db: Session,
    raw_item_ids: Iterable[str | int] | None,
    raw_tag_id: str | int | None,
) -> BulkActionResult:
    item_ids = normalize_item_ids(raw_item_ids)
    tag = _get_existing_tag(db, raw_tag_id)
    items = _load_items(db, item_ids)

    for item in items:
        item.tags = [existing_tag for existing_tag in item.tags if existing_tag.id != tag.id]
    db.commit()
    return _result(item_ids, items)


def add_items_collection(
    db: Session,
    raw_item_ids: Iterable[str | int] | None,
    raw_collection_id: str | int | None,
) -> BulkActionResult:
    item_ids = normalize_item_ids(raw_item_ids)
    collection = _get_existing_collection(db, raw_collection_id)
    items = _load_items(db, item_ids)

    for item in items:
        if all(existing.id != collection.id for existing in item.collections):
            item.collections.append(collection)
    db.commit()
    return _result(item_ids, items)


def remove_items_collection(
    db: Session,
    raw_item_ids: Iterable[str | int] | None,
    raw_collection_id: str | int | None,
) -> BulkActionResult:
    item_ids = normalize_item_ids(raw_item_ids)
    collection = _get_existing_collection(db, raw_collection_id)
    items = _load_items(db, item_ids)

    for item in items:
        item.collections = [
            existing for existing in item.collections if existing.id != collection.id
        ]
    db.commit()
    return _result(item_ids, items)


def set_items_rating(
    db: Session,
    raw_item_ids: Iterable[str | int] | None,
    raw_rating: str | int | None,
) -> BulkActionResult:
    item_ids = normalize_item_ids(raw_item_ids)
    try:
        rating = int(raw_rating) if raw_rating not in {None, ""} else 0
    except (TypeError, ValueError):
        rating = 0
    if rating not in MIN_RATING_OPTIONS:
        raise BulkActionError("invalid_rating")

    items = _load_items(db, item_ids)
    for item in items:
        if item.state is None:
            db.add(UserItemState(item_id=item.id, status="watched", rating=rating))
        else:
            item.state.rating = rating
    db.commit()
    return _result(item_ids, items)


def delete_items(
    db: Session,
    raw_item_ids: Iterable[str | int] | None,
) -> BulkActionResult:
    item_ids = normalize_item_ids(raw_item_ids)
    items = _load_items(db, item_ids)

    for item in items:
        db.delete(item)
    db.commit()
    return _result(item_ids, items)
