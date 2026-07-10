from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, noload, selectinload

from app.models import Collection, Creator, Item, Tag, UserItemState

STATUS_OPTIONS = ("wish", "watching", "watched", "like", "dislike", "ignore")
PAGE_SIZE_OPTIONS = (10, 20, 50, 100)
MIN_RATING_OPTIONS = (1, 2, 3, 4, 5)
TIME_RANGE_OPTIONS = ("all", "7d", "30d", "90d")
DATE_FIELD_OPTIONS = ("updated", "created")
SORT_OPTIONS = (
    "created_desc",
    "created_asc",
    "updated_desc",
    "updated_asc",
    "title_asc",
    "title_desc",
    "rating_desc",
    "rating_asc",
)

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
DEFAULT_TIME_RANGE = "all"
DEFAULT_DATE_FIELD = "updated"
DEFAULT_SORT = "updated_desc"


@dataclass(frozen=True)
class ItemListFilters:
    q: str = ""
    tag: str = ""
    creator: str = ""
    collection_id: int | None = None
    state: str = ""
    min_rating: int | None = None
    time_range: str = DEFAULT_TIME_RANGE
    date_field: str = DEFAULT_DATE_FIELD
    sort: str = DEFAULT_SORT
    page: int = DEFAULT_PAGE
    page_size: int = DEFAULT_PAGE_SIZE

    @property
    def has_filters(self) -> bool:
        return bool(
            self.q
            or self.tag
            or self.creator
            or self.collection_id is not None
            or self.state
            or self.min_rating is not None
            or self.time_range != DEFAULT_TIME_RANGE
        )


@dataclass(frozen=True)
class ItemFilterOptions:
    tags: list[Tag]
    creators: list[Creator]
    collections: list[Collection]
    statuses: tuple[str, ...] = STATUS_OPTIONS
    min_ratings: tuple[int, ...] = MIN_RATING_OPTIONS
    time_ranges: tuple[str, ...] = TIME_RANGE_OPTIONS
    date_fields: tuple[str, ...] = DATE_FIELD_OPTIONS
    sort_options: tuple[str, ...] = SORT_OPTIONS
    page_sizes: tuple[int, ...] = PAGE_SIZE_OPTIONS


@dataclass(frozen=True)
class ItemListResult:
    items: list[Item]
    filters: ItemListFilters
    total: int
    total_pages: int
    page_numbers: list[int]


def _clean_text(value: str | None) -> str:
    return value.strip() if value else ""


def _parse_int(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_item_list_filters(
    *,
    q: str | None = None,
    tag: str | None = None,
    creator: str | None = None,
    collection: str | int | None = None,
    state: str | None = None,
    min_rating: str | int | None = None,
    time_range: str | None = None,
    date_field: str | None = None,
    sort: str | None = None,
    page: str | int | None = None,
    page_size: str | int | None = None,
) -> ItemListFilters:
    parsed_min_rating = _parse_int(min_rating)
    if parsed_min_rating not in MIN_RATING_OPTIONS:
        parsed_min_rating = None

    parsed_page = _parse_int(page)
    if parsed_page is None or parsed_page < 1:
        parsed_page = DEFAULT_PAGE

    parsed_page_size = _parse_int(page_size)
    if parsed_page_size not in PAGE_SIZE_OPTIONS:
        parsed_page_size = DEFAULT_PAGE_SIZE

    parsed_collection = _parse_int(collection)
    if parsed_collection is not None and parsed_collection <= 0:
        parsed_collection = None

    normalized_state = _clean_text(state)
    if normalized_state not in STATUS_OPTIONS:
        normalized_state = ""

    normalized_time_range = _clean_text(time_range)
    if normalized_time_range not in TIME_RANGE_OPTIONS:
        normalized_time_range = DEFAULT_TIME_RANGE

    normalized_date_field = _clean_text(date_field)
    if normalized_date_field not in DATE_FIELD_OPTIONS:
        normalized_date_field = DEFAULT_DATE_FIELD

    normalized_sort = _clean_text(sort)
    if normalized_sort not in SORT_OPTIONS:
        normalized_sort = DEFAULT_SORT

    return ItemListFilters(
        q=_clean_text(q),
        tag=_clean_text(tag),
        creator=_clean_text(creator),
        collection_id=parsed_collection,
        state=normalized_state,
        min_rating=parsed_min_rating,
        time_range=normalized_time_range,
        date_field=normalized_date_field,
        sort=normalized_sort,
        page=parsed_page,
        page_size=parsed_page_size,
    )


def _time_cutoff(time_range: str) -> datetime | None:
    days_by_range = {
        "7d": 7,
        "30d": 30,
        "90d": 90,
    }
    days = days_by_range.get(time_range)
    if days is None:
        return None
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


def _apply_filters(stmt: Any, filters: ItemListFilters) -> Any:
    if filters.q:
        stmt = stmt.where(Item.title.ilike(f"%{filters.q}%"))
    if filters.tag:
        stmt = stmt.where(Item.tags.any(Tag.name == filters.tag))
    if filters.creator:
        stmt = stmt.where(Item.creators.any(Creator.name == filters.creator))
    if filters.collection_id is not None:
        stmt = stmt.where(Item.collections.any(Collection.id == filters.collection_id))
    if filters.state:
        stmt = stmt.where(Item.state.has(UserItemState.status == filters.state))
    if filters.min_rating is not None:
        stmt = stmt.where(Item.state.has(UserItemState.rating >= filters.min_rating))

    cutoff = _time_cutoff(filters.time_range)
    if cutoff is not None:
        column = Item.created_at if filters.date_field == "created" else Item.updated_at
        stmt = stmt.where(column >= cutoff)

    return stmt


def _apply_sort(stmt: Any, sort: str) -> Any:
    if sort == "created_desc":
        return stmt.order_by(Item.created_at.desc(), Item.id.desc())
    if sort == "created_asc":
        return stmt.order_by(Item.created_at.asc(), Item.id.asc())
    if sort == "updated_asc":
        return stmt.order_by(Item.updated_at.asc(), Item.id.asc())
    if sort == "title_asc":
        return stmt.order_by(func.lower(Item.title).asc(), Item.id.asc())
    if sort == "title_desc":
        return stmt.order_by(func.lower(Item.title).desc(), Item.id.desc())
    if sort in {"rating_desc", "rating_asc"}:
        stmt = stmt.outerjoin(UserItemState, UserItemState.item_id == Item.id)
        missing_rating_last = case((UserItemState.rating.is_(None), 1), else_=0)
        rating_order = (
            UserItemState.rating.desc()
            if sort == "rating_desc"
            else UserItemState.rating.asc()
        )
        return stmt.order_by(
            missing_rating_last,
            rating_order,
            Item.updated_at.desc(),
            Item.id.desc(),
        )
    return stmt.order_by(Item.updated_at.desc(), Item.id.desc())


def _page_numbers(page: int, total_pages: int) -> list[int]:
    start = max(1, page - 2)
    end = min(total_pages, start + 4)
    start = max(1, end - 4)
    return list(range(start, end + 1))


def query_items(
    db: Session,
    *,
    q: str | None = None,
    tag: str | None = None,
    creator: str | None = None,
    collection: str | int | None = None,
    state: str | None = None,
    min_rating: str | int | None = None,
    time_range: str | None = None,
    date_field: str | None = None,
    sort: str | None = None,
    page: str | int | None = None,
    page_size: str | int | None = None,
) -> ItemListResult:
    filters = normalize_item_list_filters(
        q=q,
        tag=tag,
        creator=creator,
        collection=collection,
        state=state,
        min_rating=min_rating,
        time_range=time_range,
        date_field=date_field,
        sort=sort,
        page=page,
        page_size=page_size,
    )

    total = db.scalar(_apply_filters(select(func.count(Item.id)), filters)) or 0
    total_pages = max(ceil(total / filters.page_size), 1)
    if filters.page > total_pages:
        filters = replace(filters, page=total_pages)

    stmt = _apply_sort(_apply_filters(select(Item), filters), filters.sort)
    items = db.scalars(
        stmt.options(
            selectinload(Item.tags).noload(Tag.items),
            selectinload(Item.creators).noload(Creator.items),
            selectinload(Item.collections).noload(Collection.items),
            selectinload(Item.state),
            noload(Item.activity),
        )
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).all()

    return ItemListResult(
        items=list(items),
        filters=filters,
        total=total,
        total_pages=total_pages,
        page_numbers=_page_numbers(filters.page, total_pages),
    )


def list_item_filter_options(db: Session) -> ItemFilterOptions:
    tags = db.scalars(
        select(Tag).options(noload(Tag.items)).order_by(func.lower(Tag.name).asc())
    ).all()
    creators = db.scalars(
        select(Creator)
        .options(noload(Creator.items))
        .order_by(func.lower(Creator.name).asc())
    ).all()
    collections = db.scalars(
        select(Collection)
        .options(noload(Collection.items))
        .order_by(func.lower(Collection.name).asc())
    ).all()
    return ItemFilterOptions(
        tags=list(tags),
        creators=list(creators),
        collections=list(collections),
    )


def item_list_query_params(
    filters: ItemListFilters,
    *,
    page: int | None = None,
) -> dict[str, str]:
    params: dict[str, str] = {}
    if filters.q:
        params["q"] = filters.q
    if filters.tag:
        params["tag"] = filters.tag
    if filters.creator:
        params["creator"] = filters.creator
    if filters.collection_id is not None:
        params["collection"] = str(filters.collection_id)
    if filters.state:
        params["state"] = filters.state
    if filters.min_rating is not None:
        params["min_rating"] = str(filters.min_rating)
    if filters.time_range != DEFAULT_TIME_RANGE:
        params["time_range"] = filters.time_range
        params["date_field"] = filters.date_field
    elif filters.date_field != DEFAULT_DATE_FIELD:
        params["date_field"] = filters.date_field
    if filters.sort != DEFAULT_SORT:
        params["sort"] = filters.sort
    if filters.page_size != DEFAULT_PAGE_SIZE:
        params["page_size"] = str(filters.page_size)

    target_page = filters.page if page is None else page
    if target_page > 1:
        params["page"] = str(target_page)
    return params


def build_item_list_url(filters: ItemListFilters, *, page: int | None = None) -> str:
    params = item_list_query_params(filters, page=page)
    if not params:
        return "/items"
    return f"/items?{urlencode(params)}"
