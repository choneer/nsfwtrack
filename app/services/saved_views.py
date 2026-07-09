from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import SavedView
from app.services.item_query import item_list_query_params, normalize_item_list_filters

MAX_SAVED_VIEW_NAME_LENGTH = 80
SAVED_VIEW_PARAM_ORDER = (
    "q",
    "tag",
    "creator",
    "collection",
    "state",
    "min_rating",
    "time_range",
    "date_field",
    "sort",
    "page_size",
)
SAVED_VIEW_ALLOWED_PARAMS = set(SAVED_VIEW_PARAM_ORDER)


class SavedViewError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _query_pairs(source: str | Mapping[str, Any] | None) -> list[tuple[str, str]]:
    if source is None:
        return []
    if isinstance(source, str):
        query_string = source.strip()
        if query_string.startswith("?"):
            query_string = query_string[1:]
        return [
            (str(key), str(value))
            for key, value in parse_qsl(query_string, keep_blank_values=True)
        ]
    if hasattr(source, "multi_items"):
        return [(str(key), str(value)) for key, value in source.multi_items()]
    return [(str(key), str(value)) for key, value in source.items()]


def normalize_saved_view_query_string(
    source: str | Mapping[str, Any] | None,
) -> str:
    raw_values: dict[str, str] = {}
    for key, value in _query_pairs(source):
        if key in SAVED_VIEW_ALLOWED_PARAMS:
            raw_values[key] = value

    filters = normalize_item_list_filters(
        q=raw_values.get("q"),
        tag=raw_values.get("tag"),
        creator=raw_values.get("creator"),
        collection=raw_values.get("collection"),
        state=raw_values.get("state"),
        min_rating=raw_values.get("min_rating"),
        time_range=raw_values.get("time_range"),
        date_field=raw_values.get("date_field"),
        sort=raw_values.get("sort"),
        page=1,
        page_size=raw_values.get("page_size"),
    )
    params = item_list_query_params(filters, page=1)
    params.pop("page", None)
    ordered_params = [
        (key, params[key]) for key in SAVED_VIEW_PARAM_ORDER if key in params
    ]
    return urlencode(ordered_params)


def saved_view_items_url(query_string: str) -> str:
    normalized = normalize_saved_view_query_string(query_string)
    if not normalized:
        return "/items"
    return f"/items?{normalized}"


def _clean_name(name: str | None) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise SavedViewError("name_required")
    if len(cleaned) > MAX_SAVED_VIEW_NAME_LENGTH:
        raise SavedViewError("name_too_long")
    return cleaned


def _name_exists(db: Session, name: str, *, exclude_id: int | None = None) -> bool:
    stmt = select(SavedView.id).where(func.lower(SavedView.name) == name.lower())
    if exclude_id is not None:
        stmt = stmt.where(SavedView.id != exclude_id)
    return db.scalar(stmt) is not None


def list_saved_views(db: Session) -> list[SavedView]:
    return list(
        db.scalars(
            select(SavedView).order_by(
                func.lower(SavedView.name).asc(),
                SavedView.id.asc(),
            )
        ).all()
    )


def get_saved_view(db: Session, saved_view_id: int) -> SavedView:
    saved_view = db.get(SavedView, saved_view_id)
    if saved_view is None:
        raise SavedViewError("not_found")
    return saved_view


def create_saved_view(
    db: Session,
    *,
    name: str | None,
    query_string: str | Mapping[str, Any] | None,
) -> SavedView:
    cleaned_name = _clean_name(name)
    if _name_exists(db, cleaned_name):
        raise SavedViewError("name_exists")
    saved_view = SavedView(
        name=cleaned_name,
        query_string=normalize_saved_view_query_string(query_string),
    )
    db.add(saved_view)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SavedViewError("name_exists") from exc
    db.refresh(saved_view)
    return saved_view


def update_saved_view(
    db: Session,
    saved_view_id: int,
    *,
    query_string: str | Mapping[str, Any] | None,
) -> SavedView:
    saved_view = get_saved_view(db, saved_view_id)
    saved_view.query_string = normalize_saved_view_query_string(query_string)
    db.commit()
    db.refresh(saved_view)
    return saved_view


def delete_saved_view(db: Session, saved_view_id: int) -> None:
    saved_view = get_saved_view(db, saved_view_id)
    db.delete(saved_view)
    db.commit()
