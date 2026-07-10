from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, noload, selectinload

from app.models import Collection, Creator, Item, ItemCollection, Tag
from app.services.pagination import PageInfo, build_page_info

COLLECTION_LIST_PAGE_SIZE = 50
COLLECTION_ITEMS_PAGE_SIZE = 20
COLLECTION_AVAILABLE_PAGE_SIZE = 20


class CollectionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CollectionListRow:
    collection: Collection
    item_count: int


@dataclass(frozen=True)
class CollectionListPage:
    rows: list[CollectionListRow]
    page_info: PageInfo


@dataclass(frozen=True)
class AvailableItemRow:
    id: int
    title: str


@dataclass(frozen=True)
class CollectionDetailPage:
    collection: Collection
    items: list[Item]
    items_page_info: PageInfo
    available_items: list[AvailableItemRow]
    available_page_info: PageInfo
    available_query: str


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
            selectinload(Collection.items).options(
                selectinload(Item.tags).noload(Tag.items),
                selectinload(Item.creators).noload(Creator.items),
                noload(Item.collections),
                selectinload(Item.state),
                noload(Item.activity),
            ),
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


def list_collection_rows(
    db: Session,
    *,
    page: str | int | None = None,
) -> CollectionListPage:
    total = int(db.scalar(select(func.count(Collection.id))) or 0)
    page_info = build_page_info(
        page=page,
        page_size=COLLECTION_LIST_PAGE_SIZE,
        total=total,
    )
    rows = db.execute(
        select(Collection, func.count(ItemCollection.item_id).label("item_count"))
        .options(noload(Collection.items))
        .outerjoin(ItemCollection, ItemCollection.collection_id == Collection.id)
        .group_by(Collection.id)
        .order_by(func.lower(Collection.name).asc(), Collection.id.asc())
        .offset((page_info.page - 1) * page_info.page_size)
        .limit(page_info.page_size)
    ).all()
    return CollectionListPage(
        rows=[
            CollectionListRow(collection=collection, item_count=int(item_count))
            for collection, item_count in rows
        ],
        page_info=page_info,
    )


def get_collection_detail_page(
    db: Session,
    collection_id: int,
    *,
    item_page: str | int | None = None,
    available_page: str | int | None = None,
    available_query: str | None = None,
) -> CollectionDetailPage:
    collection = db.scalar(
        select(Collection)
        .where(Collection.id == collection_id)
        .options(noload(Collection.items))
    )
    if collection is None:
        raise CollectionError("not_found")

    item_total = int(
        db.scalar(
            select(func.count(ItemCollection.item_id)).where(
                ItemCollection.collection_id == collection_id
            )
        )
        or 0
    )
    items_page_info = build_page_info(
        page=item_page,
        page_size=COLLECTION_ITEMS_PAGE_SIZE,
        total=item_total,
    )
    items = db.scalars(
        select(Item)
        .join(ItemCollection, ItemCollection.item_id == Item.id)
        .where(ItemCollection.collection_id == collection_id)
        .options(
            selectinload(Item.tags).noload(Tag.items),
            selectinload(Item.creators).noload(Creator.items),
            noload(Item.collections),
            selectinload(Item.state),
            noload(Item.activity),
        )
        .order_by(func.lower(Item.title).asc(), Item.id.asc())
        .offset((items_page_info.page - 1) * items_page_info.page_size)
        .limit(items_page_info.page_size)
    ).all()

    cleaned_query = (available_query or "").strip()
    available_filter = ~select(ItemCollection.item_id).where(
        ItemCollection.item_id == Item.id,
        ItemCollection.collection_id == collection_id,
    ).exists()
    available_count_stmt = select(func.count(Item.id)).where(available_filter)
    available_stmt = select(Item.id, Item.title).where(available_filter)
    if cleaned_query:
        title_filter = Item.title.ilike(f"%{cleaned_query}%")
        available_count_stmt = available_count_stmt.where(title_filter)
        available_stmt = available_stmt.where(title_filter)
    available_total = int(db.scalar(available_count_stmt) or 0)
    available_page_info = build_page_info(
        page=available_page,
        page_size=COLLECTION_AVAILABLE_PAGE_SIZE,
        total=available_total,
    )
    available_rows = db.execute(
        available_stmt.order_by(func.lower(Item.title).asc(), Item.id.asc())
        .offset((available_page_info.page - 1) * available_page_info.page_size)
        .limit(available_page_info.page_size)
    ).all()
    return CollectionDetailPage(
        collection=collection,
        items=list(items),
        items_page_info=items_page_info,
        available_items=[
            AvailableItemRow(id=int(item_id), title=str(title))
            for item_id, title in available_rows
        ],
        available_page_info=available_page_info,
        available_query=cleaned_query,
    )


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
    return list(
        db.scalars(
            select(Item)
            .where(
                ~select(ItemCollection.item_id).where(
                    ItemCollection.item_id == Item.id,
                    ItemCollection.collection_id == collection_id,
                ).exists()
            )
            .options(
                noload(Item.tags),
                noload(Item.creators),
                noload(Item.collections),
                noload(Item.state),
                noload(Item.activity),
            )
            .order_by(func.lower(Item.title).asc(), Item.id.asc())
            .limit(COLLECTION_AVAILABLE_PAGE_SIZE)
        ).all()
    )


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
