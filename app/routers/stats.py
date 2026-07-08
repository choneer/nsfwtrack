from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_api_auth
from app.database import get_db
from app.models import Creator, Item, Tag, UserItemState

router = APIRouter(
    prefix="/api/stats",
    tags=["stats"],
    dependencies=[Depends(require_api_auth)],
)


@router.get("/summary")
def stats_summary(db: Session = Depends(get_db)) -> dict[str, object]:
    state_rows = db.execute(
        select(UserItemState.status, func.count(UserItemState.id)).group_by(
            UserItemState.status
        )
    ).all()
    return {
        "total_items": db.scalar(select(func.count(Item.id))) or 0,
        "total_tags": db.scalar(select(func.count(Tag.id))) or 0,
        "total_creators": db.scalar(select(func.count(Creator.id))) or 0,
        "states": {status: count for status, count in state_rows},
    }


@router.get("/timeline")
def stats_timeline(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.execute(
        select(func.date(Item.created_at), func.count(Item.id))
        .group_by(func.date(Item.created_at))
        .order_by(func.date(Item.created_at).asc())
    ).all()
    return [{"date": date_value, "count": count} for date_value, count in rows]
