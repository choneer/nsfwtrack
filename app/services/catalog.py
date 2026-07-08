from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import models
from app.schemas import ItemCreate, ItemUpdate, StateCreate


def clean_name(value: str) -> str:
    return value.strip()


def split_names(values: Iterable[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = values.replace("\n", ",").split(",")
    else:
        raw_values = list(values)
    names: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        for piece in str(value).replace("|", ",").replace(";", ",").split(","):
            name = clean_name(piece)
            key = name.casefold()
            if name and key not in seen:
                seen.add(key)
                names.append(name)
    return names


def serialize_extra(extra: dict[str, Any] | None) -> str | None:
    if extra is None:
        return None
    return json.dumps(extra, ensure_ascii=False, sort_keys=True)


def parse_extra(extra: str | None) -> dict[str, Any] | None:
    if not extra:
        return None
    try:
        value = json.loads(extra)
    except json.JSONDecodeError:
        return {"raw": extra}
    return value if isinstance(value, dict) else {"value": value}


def get_item_or_404(db: Session, item_id: int) -> models.Item:
    item = db.scalar(
        select(models.Item)
        .where(models.Item.id == item_id)
        .options(
            selectinload(models.Item.tags),
            selectinload(models.Item.creators),
            selectinload(models.Item.state),
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


def _get_or_create_tag(db: Session, name: str) -> models.Tag:
    cleaned = clean_name(name)
    if not cleaned:
        raise HTTPException(status_code=422, detail="Tag name cannot be empty")
    tag = db.scalar(select(models.Tag).where(func.lower(models.Tag.name) == cleaned.lower()))
    if tag is not None:
        return tag
    tag = models.Tag(name=cleaned)
    db.add(tag)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        tag = db.scalar(select(models.Tag).where(func.lower(models.Tag.name) == cleaned.lower()))
        if tag is None:
            raise
    return tag


def _get_or_create_creator(db: Session, name: str) -> models.Creator:
    cleaned = clean_name(name)
    if not cleaned:
        raise HTTPException(status_code=422, detail="Creator name cannot be empty")
    creator = db.scalar(
        select(models.Creator).where(func.lower(models.Creator.name) == cleaned.lower())
    )
    if creator is not None:
        return creator
    creator = models.Creator(name=cleaned, type="other")
    db.add(creator)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        creator = db.scalar(
            select(models.Creator).where(func.lower(models.Creator.name) == cleaned.lower())
        )
        if creator is None:
            raise
    return creator


def set_item_relations(
    db: Session,
    item: models.Item,
    tag_names: Iterable[str] | str | None,
    creator_names: Iterable[str] | str | None,
) -> None:
    item.tags = [_get_or_create_tag(db, name) for name in split_names(tag_names)]
    item.creators = [
        _get_or_create_creator(db, name) for name in split_names(creator_names)
    ]


def create_item(db: Session, payload: ItemCreate) -> models.Item:
    item = models.Item(
        title=payload.title,
        cover_path=payload.cover_path,
        summary=payload.summary,
        release_date=payload.release_date,
        extra=serialize_extra(payload.extra),
    )
    db.add(item)
    db.flush()
    set_item_relations(db, item, payload.tags, payload.creators)
    db.commit()
    db.refresh(item)
    return get_item_or_404(db, item.id)


def update_item(db: Session, item: models.Item, payload: ItemUpdate) -> models.Item:
    update_data = payload.model_dump(exclude_unset=True)
    if "title" in update_data:
        item.title = update_data["title"]
    if "cover_path" in update_data:
        item.cover_path = update_data["cover_path"]
    if "summary" in update_data:
        item.summary = update_data["summary"]
    if "release_date" in update_data:
        item.release_date = update_data["release_date"]
    if "extra" in update_data:
        item.extra = serialize_extra(update_data["extra"])
    if "tags" in update_data or "creators" in update_data:
        set_item_relations(
            db,
            item,
            update_data.get("tags", [tag.name for tag in item.tags]),
            update_data.get("creators", [creator.name for creator in item.creators]),
        )
    db.commit()
    db.refresh(item)
    return get_item_or_404(db, item.id)


def set_state(db: Session, item: models.Item, payload: StateCreate) -> models.UserItemState:
    if item.state is None:
        state_row = models.UserItemState(item_id=item.id, status=payload.status)
        db.add(state_row)
    else:
        state_row = item.state
        state_row.status = payload.status
    state_row.rating = payload.rating
    state_row.review = payload.review
    db.commit()
    db.refresh(state_row)
    return state_row


def delete_state(db: Session, item: models.Item) -> None:
    if item.state is not None:
        db.delete(item.state)
        db.commit()


def tag_to_dict(tag: models.Tag) -> dict[str, Any]:
    return {
        "id": tag.id,
        "name": tag.name,
        "category": tag.category,
        "created_at": tag.created_at,
    }


def creator_to_dict(creator: models.Creator) -> dict[str, Any]:
    return {
        "id": creator.id,
        "name": creator.name,
        "type": creator.type,
        "avatar_path": creator.avatar_path,
        "created_at": creator.created_at,
    }


def state_to_dict(state_row: models.UserItemState | None) -> dict[str, Any] | None:
    if state_row is None:
        return None
    return {
        "id": state_row.id,
        "item_id": state_row.item_id,
        "status": state_row.status,
        "rating": state_row.rating,
        "review": state_row.review,
        "created_at": state_row.created_at,
        "updated_at": state_row.updated_at,
    }


def item_to_dict(item: models.Item) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "cover_path": item.cover_path,
        "summary": item.summary,
        "release_date": item.release_date,
        "extra": parse_extra(item.extra),
        "tags": [tag_to_dict(tag) for tag in sorted(item.tags, key=lambda row: row.name)],
        "creators": [
            creator_to_dict(creator)
            for creator in sorted(item.creators, key=lambda row: row.name)
        ],
        "state": state_to_dict(item.state),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }
