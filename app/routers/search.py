from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_api_auth
from app.database import get_db
from app.models import Item, Tag, UserItemState
from app.services.catalog import item_to_dict

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    dependencies=[Depends(require_api_auth)],
)


@router.get("")
def search_items(
    q: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    stmt = select(Item)
    count_stmt = select(func.count(func.distinct(Item.id)))

    if q:
        keyword = f"%{q.strip()}%"
        stmt = stmt.where(Item.title.ilike(keyword))
        count_stmt = count_stmt.where(Item.title.ilike(keyword))
    if tag:
        stmt = stmt.join(Item.tags).where(Tag.name == tag.strip())
        count_stmt = count_stmt.join(Item.tags).where(Tag.name == tag.strip())
    if status:
        stmt = stmt.join(Item.state).where(UserItemState.status == status.strip())
        count_stmt = count_stmt.join(Item.state).where(
            UserItemState.status == status.strip()
        )

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.options(
            selectinload(Item.tags),
            selectinload(Item.creators),
            selectinload(Item.state),
        )
        .distinct()
        .order_by(Item.created_at.desc(), Item.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [item_to_dict(item) for item in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }
