from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import Collection, Item, ItemCollection


class CollectionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CollectionListRow:
    collection: Collection
    item_count: int


def _clean_required(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise CollectionError("name_required")
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _parse_id(value: str | int | None, required_code: str) -> int:
    if value in {None, ""}:
        raise CollectionError(required_code)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CollectionError(required_code) from exc
    if parsed <= 0:
        raise CollectionError(required_code)
    return parsed


def _name_exists(db: Session, name: str, *, exclude_id: int | None = None) -> bool:
    stmt = select(Collection.id).where(func.lower(Collection.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(Collection.id != exclude_id)
    return db.scalar(stmt) is not None


def get_collection(db: Session, collection_id: int) -> Collection:
    collection = db.scalar(
        select(Collection)
        .where(Collection.id == collection_id)
        .options(
            selectinload(Collection.items).selectinload(Item.tags),
            selectinload(Collection.items).selectinload(Item.creators),
            selectinload(Collection.items).selectinload(Item.state),
        )
    )
    if collection is None:
        raise CollectionError("not_found")
    return collection


def list_collections(db: Session) -> list[Collection]:
    return list(
        db.scalars(
            select(Collection).order_by(func.lower(Collection.name).asc(), Collection.id.asc())
        ).all()
    )


def list_collection_rows(db: Session) -> list[CollectionListRow]:
    rows = db.execute(
        select(Collection, func.count(ItemCollection.item_id).label("item_count"))
        .outerjoin(ItemCollection, ItemCollection.collection_id == Collection.id)
        .group_by(Collection.id)
        .order_by(func.lower(Collection.name).asc(), Collection.id.asc())
    ).all()
    return [
        CollectionListRow(collection=collection, item_count=int(item_count))
        for collection, item_count in rows
    ]


def create_collection(
    db: Session,
    *,
    name: str | None,
    description: str | None,
) -> Collection:
    cleaned_name = _clean_required(name)
    if _name_exists(db, cleaned_name):
        raise CollectionError("name_exists")
    collection = Collection(name=cleaned_name, description=_clean_optional(description))
    db.add(collection)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CollectionError("name_exists") from exc
    db.refresh(collection)
    return collection


def update_collection(
    db: Session,
    collection_id: int,
    *,
    name: str | None,
    description: str | None,
) -> Collection:
    collection = get_collection(db, collection_id)
    cleaned_name = _clean_required(name)
    if _name_exists(db, cleaned_name, exclude_id=collection.id):
        raise CollectionError("name_exists")
    collection.name = cleaned_name
    collection.description = _clean_optional(description)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CollectionError("name_exists") from exc
    db.refresh(collection)
    return collection


def delete_collection(db: Session, collection_id: int) -> None:
    collection = get_collection(db, collection_id)
    db.delete(collection)
    db.commit()


def list_available_items_for_collection(
    db: Session,
    collection_id: int,
) -> list[Item]:
    collection = get_collection(db, collection_id)
    current_ids = {item.id for item in collection.items}
    stmt = (
        select(Item)
        .options(
            selectinload(Item.tags),
            selectinload(Item.creators),
            selectinload(Item.state),
        )
        .order_by(func.lower(Item.title).asc(), Item.id.asc())
    )
    if current_ids:
        stmt = stmt.where(Item.id.not_in(current_ids))
    return list(db.scalars(stmt).all())


def list_available_collections_for_item(db: Session, item_id: int) -> list[Collection]:
    item = _get_item_with_collections(db, item_id)
    current_ids = {collection.id for collection in item.collections}
    stmt = select(Collection).order_by(func.lower(Collection.name).asc(), Collection.id.asc())
    if current_ids:
        stmt = stmt.where(Collection.id.not_in(current_ids))
    return list(db.scalars(stmt).all())


def _get_item_with_collections(db: Session, item_id: int) -> Item:
    item = db.scalar(
        select(Item)
        .where(Item.id == item_id)
        .options(
            selectinload(Item.collections),
            selectinload(Item.tags),
            selectinload(Item.creators),
            selectinload(Item.state),
        )
    )
    if item is None:
        raise CollectionError("item_not_found")
    return item


def add_item_to_collection(
    db: Session,
    *,
    item_id: str | int | None,
    collection_id: str | int | None,
) -> None:
    parsed_item_id = _parse_id(item_id, "item_required")
    parsed_collection_id = _parse_id(collection_id, "collection_required")
    item = _get_item_with_collections(db, parsed_item_id)
    collection = get_collection(db, parsed_collection_id)
    if any(existing.id == collection.id for existing in item.collections):
        raise CollectionError("duplicate_relation")
    item.collections.append(collection)
    db.commit()


def remove_item_from_collection(
    db: Session,
    *,
    item_id: str | int | None,
    collection_id: str | int | None,
) -> None:
    parsed_item_id = _parse_id(item_id, "item_required")
    parsed_collection_id = _parse_id(collection_id, "collection_required")
    item = _get_item_with_collections(db, parsed_item_id)
    collection = get_collection(db, parsed_collection_id)
    item.collections = [
        existing for existing in item.collections if existing.id != collection.id
    ]
    db.commit()
