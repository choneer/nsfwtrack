from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_api_auth
from app.database import get_db
from app.models import Item
from app.schemas import ItemCreate, ItemUpdate, StateCreate
from app.services.catalog import (
    create_item,
    delete_state,
    get_item_or_404,
    item_to_dict,
    set_state,
    state_to_dict,
    update_item,
)

router = APIRouter(
    prefix="/api/items",
    tags=["items"],
    dependencies=[Depends(require_api_auth)],
)


@router.get("")
def list_items(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    total = db.scalar(select(func.count(Item.id))) or 0
    rows = db.scalars(
        select(Item)
        .options(
            selectinload(Item.tags),
            selectinload(Item.creators),
            selectinload(Item.state),
        )
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


@router.post("", status_code=status.HTTP_201_CREATED)
def create_item_endpoint(
    payload: ItemCreate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return item_to_dict(create_item(db, payload))


@router.get("/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    return item_to_dict(get_item_or_404(db, item_id))


@router.put("/{item_id}")
def update_item_endpoint(
    item_id: int,
    payload: ItemUpdate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    item = get_item_or_404(db, item_id)
    return item_to_dict(update_item(db, item, payload))


@router.delete("/{item_id}")
def delete_item_endpoint(item_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    item = get_item_or_404(db, item_id)
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post("/{item_id}/state", status_code=status.HTTP_201_CREATED)
def set_item_state(
    item_id: int,
    payload: StateCreate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    item = get_item_or_404(db, item_id)
    return state_to_dict(set_state(db, item, payload)) or {}


@router.get("/{item_id}/state")
def get_item_state(item_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    item = get_item_or_404(db, item_id)
    state_row = state_to_dict(item.state)
    if state_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="State not found")
    return state_row


@router.delete("/{item_id}/state")
def delete_item_state(item_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    item = get_item_or_404(db, item_id)
    delete_state(db, item)
    return {"ok": True}
