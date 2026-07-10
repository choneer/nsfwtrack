from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, noload, selectinload

from app import models

RECENT_ACTIVITY_LIMIT = 8
ACTIVITY_PAGE_LIMIT = 50


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _item_exists(db: Session, item_id: int) -> bool:
    return db.scalar(select(models.Item.id).where(models.Item.id == item_id)) is not None


def _get_or_create_activity(
    db: Session,
    item_id: int,
    now: datetime,
) -> models.ItemActivity | None:
    if not _item_exists(db, item_id):
        return None
    activity = db.scalar(
        select(models.ItemActivity).where(models.ItemActivity.item_id == item_id)
    )
    if activity is None:
        activity = models.ItemActivity(item_id=item_id, created_at=now, updated_at=now)
        db.add(activity)
        db.flush()
    return activity


def _coerce_item_id(raw_item_id: int | str | None) -> int | None:
    try:
        item_id = int(raw_item_id) if raw_item_id not in {None, ""} else 0
    except (TypeError, ValueError):
        return None
    return item_id if item_id > 0 else None


def record_item_view(db: Session, raw_item_id: int | str | None) -> models.ItemActivity | None:
    item_id = _coerce_item_id(raw_item_id)
    if item_id is None:
        return None
    now = _now()
    activity = _get_or_create_activity(db, item_id, now)
    if activity is None:
        db.rollback()
        return None
    activity.last_viewed_at = now
    activity.view_count = (activity.view_count or 0) + 1
    activity.updated_at = now
    db.commit()
    db.refresh(activity)
    return activity


def record_item_edit(db: Session, raw_item_id: int | str | None) -> models.ItemActivity | None:
    item_id = _coerce_item_id(raw_item_id)
    if item_id is None:
        return None
    now = _now()
    activity = _get_or_create_activity(db, item_id, now)
    if activity is None:
        db.rollback()
        return None
    activity.last_edited_at = now
    activity.edit_count = (activity.edit_count or 0) + 1
    activity.updated_at = now
    db.commit()
    db.refresh(activity)
    return activity


def record_item_edits(
    db: Session,
    raw_item_ids: Iterable[int | str],
) -> list[models.ItemActivity]:
    item_ids: list[int] = []
    seen: set[int] = set()
    for raw_item_id in raw_item_ids:
        item_id = _coerce_item_id(raw_item_id)
        if item_id is not None and item_id not in seen:
            seen.add(item_id)
            item_ids.append(item_id)
    if not item_ids:
        return []

    existing_item_ids = set(
        db.scalars(select(models.Item.id).where(models.Item.id.in_(item_ids))).all()
    )
    if not existing_item_ids:
        return []

    now = _now()
    existing_activity = {
        activity.item_id: activity
        for activity in db.scalars(
            select(models.ItemActivity).where(
                models.ItemActivity.item_id.in_(existing_item_ids)
            )
        ).all()
    }
    touched: list[models.ItemActivity] = []
    for item_id in item_ids:
        if item_id not in existing_item_ids:
            continue
        activity = existing_activity.get(item_id)
        if activity is None:
            activity = models.ItemActivity(item_id=item_id, created_at=now)
            db.add(activity)
        activity.last_edited_at = now
        activity.edit_count = (activity.edit_count or 0) + 1
        activity.updated_at = now
        touched.append(activity)
    db.commit()
    for activity in touched:
        db.refresh(activity)
    return touched


def safe_record_item_view(
    db: Session,
    raw_item_id: int | str | None,
) -> models.ItemActivity | None:
    try:
        return record_item_view(db, raw_item_id)
    except Exception:
        db.rollback()
        return None


def safe_record_item_edit(
    db: Session,
    raw_item_id: int | str | None,
) -> models.ItemActivity | None:
    try:
        return record_item_edit(db, raw_item_id)
    except Exception:
        db.rollback()
        return None


def safe_record_item_edits(
    db: Session,
    raw_item_ids: Iterable[int | str],
) -> list[models.ItemActivity]:
    try:
        return record_item_edits(db, raw_item_ids)
    except Exception:
        db.rollback()
        return []


def get_item_activity(db: Session, raw_item_id: int | str | None) -> models.ItemActivity | None:
    item_id = _coerce_item_id(raw_item_id)
    if item_id is None:
        return None
    return db.scalar(
        select(models.ItemActivity).where(models.ItemActivity.item_id == item_id)
    )


def count_item_activity(db: Session) -> int:
    return int(db.scalar(select(func.count(models.ItemActivity.id))) or 0)


def _activity_items_options() -> tuple[object, ...]:
    return (
        selectinload(models.ItemActivity.item).options(
            noload(models.Item.tags),
            noload(models.Item.creators),
            noload(models.Item.collections),
            noload(models.Item.state),
            noload(models.Item.activity),
        ),
    )


def list_recently_viewed(
    db: Session,
    *,
    limit: int = RECENT_ACTIVITY_LIMIT,
) -> list[models.ItemActivity]:
    return list(
        db.scalars(
            select(models.ItemActivity)
            .join(models.Item)
            .where(models.ItemActivity.last_viewed_at.is_not(None))
            .options(*_activity_items_options())
            .order_by(
                models.ItemActivity.last_viewed_at.desc(),
                models.ItemActivity.id.desc(),
            )
            .limit(limit)
        ).all()
    )


def list_recently_edited(
    db: Session,
    *,
    limit: int = RECENT_ACTIVITY_LIMIT,
) -> list[models.ItemActivity]:
    return list(
        db.scalars(
            select(models.ItemActivity)
            .join(models.Item)
            .where(models.ItemActivity.last_edited_at.is_not(None))
            .options(*_activity_items_options())
            .order_by(
                models.ItemActivity.last_edited_at.desc(),
                models.ItemActivity.id.desc(),
            )
            .limit(limit)
        ).all()
    )


def clear_item_activity(db: Session) -> int:
    result = db.execute(delete(models.ItemActivity))
    db.commit()
    return int(result.rowcount or 0)
