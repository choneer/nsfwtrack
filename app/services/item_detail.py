from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Creator, Tag, UserItemState
from app.services.catalog import get_item_or_404
from app.services.item_query import MIN_RATING_OPTIONS, STATUS_OPTIONS


class ItemDetailError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _normalize_relation_id(raw_value: str | int | None, required_code: str) -> int:
    if raw_value in {None, ""}:
        raise ItemDetailError(required_code)
    try:
        relation_id = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ItemDetailError(required_code) from exc
    if relation_id <= 0:
        raise ItemDetailError(required_code)
    return relation_id


def _normalize_status(raw_status: str | None) -> str:
    status_value = (raw_status or "").strip()
    if status_value not in STATUS_OPTIONS:
        raise ItemDetailError("invalid_status")
    return status_value


def _normalize_rating(raw_rating: str | int | None) -> int | None:
    if raw_rating is None:
        return None
    if isinstance(raw_rating, str):
        raw_rating = raw_rating.strip()
        if raw_rating == "":
            return None
    try:
        rating = int(raw_rating)
    except (TypeError, ValueError) as exc:
        raise ItemDetailError("invalid_rating") from exc
    if rating not in MIN_RATING_OPTIONS:
        raise ItemDetailError("invalid_rating")
    return rating


def _normalize_review(raw_review: str | None) -> str | None:
    if raw_review is None:
        return None
    return raw_review.strip() or None


def list_available_tags(db: Session, item_id: int) -> list[Tag]:
    item = get_item_or_404(db, item_id)
    current_ids = {tag.id for tag in item.tags}
    stmt = select(Tag).order_by(Tag.name.asc(), Tag.id.asc())
    if current_ids:
        stmt = stmt.where(Tag.id.not_in(current_ids))
    return list(db.scalars(stmt).all())


def list_available_creators(db: Session, item_id: int) -> list[Creator]:
    item = get_item_or_404(db, item_id)
    current_ids = {creator.id for creator in item.creators}
    stmt = select(Creator).order_by(Creator.name.asc(), Creator.id.asc())
    if current_ids:
        stmt = stmt.where(Creator.id.not_in(current_ids))
    return list(db.scalars(stmt).all())


def save_item_state(
    db: Session,
    item_id: int,
    status_value: str | None,
    rating: str | int | None,
    review: str | None,
) -> UserItemState:
    item = get_item_or_404(db, item_id)
    normalized_status = _normalize_status(status_value)
    normalized_rating = _normalize_rating(rating)
    normalized_review = _normalize_review(review)

    if item.state is None:
        state_row = UserItemState(item_id=item.id, status=normalized_status)
        db.add(state_row)
    else:
        state_row = item.state
        state_row.status = normalized_status
    state_row.rating = normalized_rating
    state_row.review = normalized_review
    db.commit()
    db.refresh(state_row)
    return state_row


def add_existing_tag(db: Session, item_id: int, raw_tag_id: str | int | None) -> None:
    item = get_item_or_404(db, item_id)
    tag_id = _normalize_relation_id(raw_tag_id, "tag_required")
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise ItemDetailError("tag_not_found")
    if any(existing_tag.id == tag.id for existing_tag in item.tags):
        raise ItemDetailError("duplicate_relation")
    item.tags.append(tag)
    db.commit()


def remove_existing_tag(db: Session, item_id: int, raw_tag_id: str | int | None) -> None:
    item = get_item_or_404(db, item_id)
    tag_id = _normalize_relation_id(raw_tag_id, "tag_required")
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise ItemDetailError("tag_not_found")
    item.tags = [existing_tag for existing_tag in item.tags if existing_tag.id != tag.id]
    db.commit()


def add_existing_creator(
    db: Session,
    item_id: int,
    raw_creator_id: str | int | None,
) -> None:
    item = get_item_or_404(db, item_id)
    creator_id = _normalize_relation_id(raw_creator_id, "creator_required")
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise ItemDetailError("creator_not_found")
    if any(existing_creator.id == creator.id for existing_creator in item.creators):
        raise ItemDetailError("duplicate_relation")
    item.creators.append(creator)
    db.commit()


def remove_existing_creator(
    db: Session,
    item_id: int,
    raw_creator_id: str | int | None,
) -> None:
    item = get_item_or_404(db, item_id)
    creator_id = _normalize_relation_id(raw_creator_id, "creator_required")
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise ItemDetailError("creator_not_found")
    item.creators = [
        existing_creator
        for existing_creator in item.creators
        if existing_creator.id != creator.id
    ]
    db.commit()
