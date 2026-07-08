from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_api_auth
from app.database import get_db
from app.models import Tag
from app.schemas import TagCreate, TagUpdate
from app.services.catalog import tag_to_dict

router = APIRouter(
    prefix="/api/tags",
    tags=["tags"],
    dependencies=[Depends(require_api_auth)],
)


def _get_tag_or_404(db: Session, tag_id: int) -> Tag:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


@router.get("")
def list_tags(
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    stmt = select(Tag).order_by(Tag.name.asc())
    if q:
        stmt = stmt.where(Tag.name.ilike(f"%{q.strip()}%"))
    return [tag_to_dict(tag) for tag in db.scalars(stmt).all()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tag(payload: TagCreate, db: Session = Depends(get_db)) -> dict[str, object]:
    tag = Tag(name=payload.name, category=payload.category)
    db.add(tag)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Tag already exists") from exc
    db.refresh(tag)
    return tag_to_dict(tag)


@router.put("/{tag_id}")
def update_tag(
    tag_id: int,
    payload: TagUpdate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    tag = _get_tag_or_404(db, tag_id)
    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"]:
        duplicate = db.scalar(
            select(Tag).where(
                func.lower(Tag.name) == update_data["name"].lower(),
                Tag.id != tag.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Tag already exists")
        tag.name = update_data["name"]
    if "category" in update_data:
        tag.category = update_data["category"]
    db.commit()
    db.refresh(tag)
    return tag_to_dict(tag)


@router.delete("/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    tag = _get_tag_or_404(db, tag_id)
    db.delete(tag)
    db.commit()
    return {"ok": True}
