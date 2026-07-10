from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from sqlalchemy import case, func, or_, select
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


def _percent(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((count / total) * 100, 1)


def _average(value: object) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


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
    rows = db.execute(
        select(
            Tag.name,
            func.count(ItemTag.item_id).label("item_count"),
            func.sum(func.count(ItemTag.item_id)).over().label("total_links"),
        )
        .join(ItemTag, ItemTag.tag_id == Tag.id)
        .group_by(Tag.id)
        .order_by(func.count(ItemTag.item_id).desc(), func.lower(Tag.name).asc())
        .limit(RANKING_LIMIT)
    ).all()
    total_links = int(rows[0].total_links) if rows else 0
    return {
        "total_links": total_links,
        "rows": [
            {
                "name": str(name),
                "count": int(count),
                "percent": _percent(int(count), total_links),
            }
            for name, count, _ in rows
        ],
    }


def _creator_ranking(db: Session) -> dict[str, object]:
    rows = db.execute(
        select(
            Creator.name,
            func.count(ItemCreator.item_id).label("item_count"),
            func.sum(func.count(ItemCreator.item_id)).over().label("total_links"),
        )
        .join(ItemCreator, ItemCreator.creator_id == Creator.id)
        .group_by(Creator.id)
        .order_by(func.count(ItemCreator.item_id).desc(), func.lower(Creator.name).asc())
        .limit(RANKING_LIMIT)
    ).all()
    total_links = int(rows[0].total_links) if rows else 0
    return {
        "total_links": total_links,
        "rows": [
            {
                "name": str(name),
                "count": int(count),
                "percent": _percent(int(count), total_links),
            }
            for name, count, _ in rows
        ],
    }


def _collection_ranking(db: Session) -> dict[str, object]:
    rows = db.execute(
        select(
            Collection.name,
            func.count(ItemCollection.item_id).label("item_count"),
            func.sum(func.count(ItemCollection.item_id)).over().label("total_links"),
        )
        .join(ItemCollection, ItemCollection.collection_id == Collection.id)
        .group_by(Collection.id)
        .order_by(func.count(ItemCollection.item_id).desc(), func.lower(Collection.name).asc())
        .limit(RANKING_LIMIT)
    ).all()
    total_links = int(rows[0].total_links) if rows else 0
    return {
        "total_links": total_links,
        "rows": [
            {
                "name": str(name),
                "count": int(count),
                "percent": _percent(int(count), total_links),
            }
            for name, count, _ in rows
        ],
    }


def _activity(
    db: Session,
    now: datetime,
    *,
    created_7d: int,
    created_30d: int,
    updated_7d: int,
    updated_30d: int,
) -> dict[str, object]:
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
    created_rows = db.execute(
        select(func.date(Item.created_at), func.count(Item.id))
        .where(Item.created_at >= start_at)
        .group_by(func.date(Item.created_at))
    ).all()
    updated_rows = db.execute(
        select(func.date(Item.updated_at), func.count(Item.id))
        .where(Item.updated_at >= start_at)
        .group_by(func.date(Item.updated_at))
    ).all()
    for date_value, count in created_rows:
        parsed_date = datetime.fromisoformat(str(date_value)).date()
        if parsed_date in buckets:
            buckets[parsed_date]["created_count"] = int(count)
    for date_value, count in updated_rows:
        parsed_date = datetime.fromisoformat(str(date_value)).date()
        if parsed_date in buckets:
            buckets[parsed_date]["updated_count"] = int(count)

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
    *,
    total_items: int,
    state_items: int,
    rated_items: int,
    missing_tags: int,
    missing_creators: int,
    missing_summary: int,
) -> list[dict[str, object]]:
    return [
        {"key": "missing_tags", "count": missing_tags},
        {"key": "missing_creators", "count": missing_creators},
        {"key": "missing_state", "count": total_items - state_items},
        {"key": "missing_rating", "count": total_items - rated_items},
        {"key": "missing_summary", "count": missing_summary},
    ]


def _metadata_totals(db: Session) -> tuple[int, int, int]:
    row = db.execute(
        select(
            select(func.count(Tag.id)).scalar_subquery(),
            select(func.count(Creator.id)).scalar_subquery(),
            select(func.count(Collection.id)).scalar_subquery(),
        )
    ).one()
    return int(row[0]), int(row[1]), int(row[2])


def _item_metrics(db: Session, now: datetime) -> dict[str, int]:
    row = db.execute(
        select(
            func.count(Item.id),
            func.sum(case((Item.collections.any(), 1), else_=0)),
            func.sum(case((~Item.tags.any(), 1), else_=0)),
            func.sum(case((~Item.creators.any(), 1), else_=0)),
            func.sum(
                case(
                    (or_(Item.summary.is_(None), func.trim(Item.summary) == ""), 1),
                    else_=0,
                )
            ),
            func.sum(case((Item.created_at >= now - timedelta(days=7), 1), else_=0)),
            func.sum(case((Item.created_at >= now - timedelta(days=30), 1), else_=0)),
            func.sum(case((Item.updated_at >= now - timedelta(days=7), 1), else_=0)),
            func.sum(case((Item.updated_at >= now - timedelta(days=30), 1), else_=0)),
        )
    ).one()
    keys = (
        "total_items",
        "items_with_collections",
        "missing_tags",
        "missing_creators",
        "missing_summary",
        "created_7d",
        "created_30d",
        "updated_7d",
        "updated_30d",
    )
    return {key: int(value or 0) for key, value in zip(keys, row, strict=True)}


def _state_metrics(db: Session) -> dict[str, int | float | None]:
    row = db.execute(
        select(
            func.count(UserItemState.id),
            func.sum(case((UserItemState.rating.is_not(None), 1), else_=0)),
            func.avg(UserItemState.rating),
            func.max(UserItemState.rating),
            func.min(UserItemState.rating),
        )
    ).one()
    return {
        "state_items": int(row[0] or 0),
        "rated_items": int(row[1] or 0),
        "average_rating": _average(row[2]),
        "highest_rating": int(row[3]) if row[3] is not None else None,
        "lowest_rating": int(row[4]) if row[4] is not None else None,
    }


def build_stats_dashboard(db: Session) -> dict[str, object]:
    now = _now()
    total_tags, total_creators, total_collections = _metadata_totals(db)
    item_metrics = _item_metrics(db, now)
    state_metrics = _state_metrics(db)
    total_items = int(item_metrics["total_items"])
    items_with_collections = int(item_metrics["items_with_collections"])
    state_items = int(state_metrics["state_items"] or 0)
    rated_items = int(state_metrics["rated_items"] or 0)
    average_rating = state_metrics["average_rating"]
    activity = _activity(
        db,
        now,
        created_7d=int(item_metrics["created_7d"]),
        created_30d=int(item_metrics["created_30d"]),
        updated_7d=int(item_metrics["updated_7d"]),
        updated_30d=int(item_metrics["updated_30d"]),
    )

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
            "highest_rating": state_metrics["highest_rating"],
            "lowest_rating": state_metrics["lowest_rating"],
            "rows": _rating_distribution(db, rated_items),
        },
        "tag_ranking": _tag_ranking(db),
        "creator_ranking": _creator_ranking(db),
        "collection_ranking": _collection_ranking(db),
        "activity": activity,
        "integrity": _integrity_overview(
            total_items=total_items,
            state_items=state_items,
            rated_items=rated_items,
            missing_tags=int(item_metrics["missing_tags"]),
            missing_creators=int(item_metrics["missing_creators"]),
            missing_summary=int(item_metrics["missing_summary"]),
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
