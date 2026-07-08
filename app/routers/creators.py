from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import require_api_auth
from app.database import get_db
from app.models import Creator
from app.schemas import CreatorCreate
from app.services.catalog import creator_to_dict, item_to_dict

router = APIRouter(
    prefix="/api/creators",
    tags=["creators"],
    dependencies=[Depends(require_api_auth)],
)


def _get_creator_or_404(db: Session, creator_id: int) -> Creator:
    creator = db.scalar(
        select(Creator)
        .where(Creator.id == creator_id)
        .options(selectinload(Creator.items))
    )
    if creator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creator not found",
        )
    return creator


@router.get("")
def list_creators(
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    stmt = select(Creator).order_by(Creator.name.asc())
    if q:
        stmt = stmt.where(Creator.name.ilike(f"%{q.strip()}%"))
    return [creator_to_dict(creator) for creator in db.scalars(stmt).all()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_creator(
    payload: CreatorCreate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    creator = Creator(
        name=payload.name,
        type=payload.type or "other",
        avatar_path=payload.avatar_path,
    )
    db.add(creator)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Creator already exists") from exc
    db.refresh(creator)
    return creator_to_dict(creator)


@router.get("/{creator_id}")
def get_creator(creator_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    creator = _get_creator_or_404(db, creator_id)
    data = creator_to_dict(creator)
    data["items"] = [item_to_dict(item) for item in creator.items]
    return data


@router.delete("/{creator_id}")
def delete_creator(creator_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    creator = _get_creator_or_404(db, creator_id)
    db.delete(creator)
    db.commit()
    return {"ok": True}
