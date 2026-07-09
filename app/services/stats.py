from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Collection,
    Creator,
    Item,
    ItemCollection,
    ItemCreator,
    ItemTag,
    Tag,
    UserItemState,
)
from app.services.item_query import STATUS_OPTIONS

RATINGS = (1, 2, 3, 4, 5)
RANKING_LIMIT = 10


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _count(db: Session, stmt: Any) -> int:
    return int(db.scalar(stmt) or 0)


def _percent(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100, 1)


def _average(value: object) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _coerce_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(value).replace(tzinfo=None)


def _items_since(db: Session, column: Any, days: int, now: datetime) -> int:
    return _count(db, select(func.count(Item.id)).where(column >= now - timedelta(days=days)))


def _status_distribution(db: Session) -> list[dict[str, object]]:
    rows = db.execute(
        select(UserItemState.status, func.count(UserItemState.id)).group_by(
            UserItemState.status
        )
    ).all()
    counts = {str(status): int(count) for status, count in rows}
    total = sum(counts.values())
    return [
        {
            "status": status,
            "count": counts.get(status, 0),
            "percent": _percent(counts.get(status, 0), total),
        }
        for status in STATUS_OPTIONS
    ]


def _rating_distribution(db: Session, total_rated: int) -> list[dict[str, object]]:
    rows = db.execute(
        select(UserItemState.rating, func.count(UserItemState.id))
        .where(UserItemState.rating.is_not(None))
        .group_by(UserItemState.rating)
    ).all()
    counts = {int(rating): int(count) for rating, count in rows if rating is not None}
    return [
        {
            "rating": rating,
            "count": counts.get(rating, 0),
            "percent": _percent(counts.get(rating, 0), total_rated),
        }
        for rating in RATINGS
    ]


def _tag_ranking(db: Session) -> dict[str, object]:
    total_links = _count(db, select(func.count()).select_from(ItemTag))
    rows = db.execute(
        select(Tag.name, func.count(ItemTag.item_id).label("item_count"))
        .join(ItemTag, ItemTag.tag_id == Tag.id)
        .group_by(Tag.id)
        .order_by(func.count(ItemTag.item_id).desc(), func.lower(Tag.name).asc())
        .limit(RANKING_LIMIT)
    ).all()
    return {
        "total_links": total_links,
        "rows": [
            {
                "name": str(name),
                "count": int(count),
                "percent": _percent(int(count), total_links),
            }
            for name, count in rows
        ],
    }


def _creator_ranking(db: Session) -> dict[str, object]:
    total_links = _count(db, select(func.count()).select_from(ItemCreator))
    rows = db.execute(
        select(Creator.name, func.count(ItemCreator.item_id).label("item_count"))
        .join(ItemCreator, ItemCreator.creator_id == Creator.id)
        .group_by(Creator.id)
        .order_by(func.count(ItemCreator.item_id).desc(), func.lower(Creator.name).asc())
        .limit(RANKING_LIMIT)
    ).all()
    return {
        "total_links": total_links,
        "rows": [
            {
                "name": str(name),
                "count": int(count),
                "percent": _percent(int(count), total_links),
            }
            for name, count in rows
        ],
    }


def _collection_ranking(db: Session) -> dict[str, object]:
    total_links = _count(db, select(func.count()).select_from(ItemCollection))
    rows = db.execute(
        select(Collection.name, func.count(ItemCollection.item_id).label("item_count"))
        .join(ItemCollection, ItemCollection.collection_id == Collection.id)
        .group_by(Collection.id)
        .order_by(func.count(ItemCollection.item_id).desc(), func.lower(Collection.name).asc())
        .limit(RANKING_LIMIT)
    ).all()
    return {
        "total_links": total_links,
        "rows": [
            {
                "name": str(name),
                "count": int(count),
                "percent": _percent(int(count), total_links),
            }
            for name, count in rows
        ],
    }


def _activity(db: Session, now: datetime) -> dict[str, object]:
    created_7d = _items_since(db, Item.created_at, 7, now)
    created_30d = _items_since(db, Item.created_at, 30, now)
    updated_7d = _items_since(db, Item.updated_at, 7, now)
    updated_30d = _items_since(db, Item.updated_at, 30, now)

    today = now.date()
    start_date = today - timedelta(days=6)
    start_at = datetime.combine(start_date, time.min)
    buckets = {
        start_date + timedelta(days=offset): {
            "date": (start_date + timedelta(days=offset)).isoformat(),
            "created_count": 0,
            "updated_count": 0,
        }
        for offset in range(7)
    }
    rows = db.execute(
        select(Item.created_at, Item.updated_at).where(
            or_(Item.created_at >= start_at, Item.updated_at >= start_at)
        )
    ).all()
    for created_at, updated_at in rows:
        created_date = _coerce_datetime(created_at).date()
        updated_date = _coerce_datetime(updated_at).date()
        if created_date in buckets:
            buckets[created_date]["created_count"] += 1
        if updated_date in buckets:
            buckets[updated_date]["updated_count"] += 1

    daily_rows = list(buckets.values())
    max_daily_count = max(
        [1]
        + [
            max(int(row["created_count"]), int(row["updated_count"]))
            for row in daily_rows
        ]
    )
    for row in daily_rows:
        row["created_percent"] = _percent(int(row["created_count"]), max_daily_count)
        row["updated_percent"] = _percent(int(row["updated_count"]), max_daily_count)

    return {
        "created_7d": created_7d,
        "created_30d": created_30d,
        "updated_7d": updated_7d,
        "updated_30d": updated_30d,
        "daily": daily_rows,
        "has_recent": any(
            int(row["created_count"]) or int(row["updated_count"])
            for row in daily_rows
        ),
    }


def _integrity_overview(
    db: Session,
    *,
    total_items: int,
    state_items: int,
    rated_items: int,
) -> list[dict[str, object]]:
    missing_tags = _count(db, select(func.count(Item.id)).where(~Item.tags.any()))
    missing_creators = _count(
        db, select(func.count(Item.id)).where(~Item.creators.any())
    )
    missing_summary = _count(
        db,
        select(func.count(Item.id)).where(
            or_(Item.summary.is_(None), func.trim(Item.summary) == "")
        ),
    )
    return [
        {"key": "missing_tags", "count": missing_tags},
        {"key": "missing_creators", "count": missing_creators},
        {"key": "missing_state", "count": total_items - state_items},
        {"key": "missing_rating", "count": total_items - rated_items},
        {"key": "missing_summary", "count": missing_summary},
    ]


def build_stats_dashboard(db: Session) -> dict[str, object]:
    now = _now()
    total_items = _count(db, select(func.count(Item.id)))
    total_tags = _count(db, select(func.count(Tag.id)))
    total_creators = _count(db, select(func.count(Creator.id)))
    total_collections = _count(db, select(func.count(Collection.id)))
    items_with_collections = _count(
        db, select(func.count(Item.id)).where(Item.collections.any())
    )
    state_items = _count(db, select(func.count(UserItemState.id)))
    rated_items = _count(
        db,
        select(func.count(UserItemState.id)).where(UserItemState.rating.is_not(None)),
    )
    average_rating = _average(
        db.scalar(
            select(func.avg(UserItemState.rating)).where(
                UserItemState.rating.is_not(None)
            )
        )
    )
    highest_rating = db.scalar(
        select(func.max(UserItemState.rating)).where(UserItemState.rating.is_not(None))
    )
    lowest_rating = db.scalar(
        select(func.min(UserItemState.rating)).where(UserItemState.rating.is_not(None))
    )
    activity = _activity(db, now)

    return {
        "overview": {
            "total_items": total_items,
            "total_tags": total_tags,
            "total_creators": total_creators,
            "total_collections": total_collections,
            "items_with_collections": items_with_collections,
            "items_without_collections": max(total_items - items_with_collections, 0),
            "state_items": state_items,
            "rated_items": rated_items,
            "average_rating": average_rating,
            "created_7d": activity["created_7d"],
            "created_30d": activity["created_30d"],
        },
        "status_distribution": {
            "total": state_items,
            "rows": _status_distribution(db),
        },
        "rating_distribution": {
            "total": rated_items,
            "average_rating": average_rating,
            "highest_rating": int(highest_rating) if highest_rating is not None else None,
            "lowest_rating": int(lowest_rating) if lowest_rating is not None else None,
            "rows": _rating_distribution(db, rated_items),
        },
        "tag_ranking": _tag_ranking(db),
        "creator_ranking": _creator_ranking(db),
        "collection_ranking": _collection_ranking(db),
        "activity": activity,
        "integrity": _integrity_overview(
            db,
            total_items=total_items,
            state_items=state_items,
            rated_items=rated_items,
        ),
        "local_only": True,
    }


def stats_summary_payload(db: Session) -> dict[str, object]:
    dashboard = build_stats_dashboard(db)
    overview = dashboard["overview"]
    status_distribution = dashboard["status_distribution"]
    return {
        **overview,
        "states": {
            str(row["status"]): int(row["count"])
            for row in status_distribution["rows"]
        },
        "overview": overview,
        "status_distribution": status_distribution,
        "rating_distribution": dashboard["rating_distribution"],
        "tag_ranking": dashboard["tag_ranking"],
        "creator_ranking": dashboard["creator_ranking"],
        "collection_ranking": dashboard["collection_ranking"],
        "activity": dashboard["activity"],
        "integrity": dashboard["integrity"],
    }


def created_timeline(db: Session) -> list[dict[str, object]]:
    rows = db.execute(
        select(func.date(Item.created_at), func.count(Item.id))
        .group_by(func.date(Item.created_at))
        .order_by(func.date(Item.created_at).asc())
    ).all()
    return [{"date": date_value, "count": int(count)} for date_value, count in rows]
