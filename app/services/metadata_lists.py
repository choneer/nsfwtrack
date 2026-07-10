from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session, noload

from app.models import Creator, Tag
from app.services.pagination import PageInfo, build_page_info

METADATA_PAGE_SIZE = 50
MetadataRow = TypeVar("MetadataRow", Tag, Creator)


@dataclass(frozen=True)
class MetadataListPage(Generic[MetadataRow]):
    rows: list[MetadataRow]
    page_info: PageInfo


def list_tag_page(
    db: Session,
    *,
    page: str | int | None = None,
) -> MetadataListPage[Tag]:
    total = int(db.scalar(select(func.count(Tag.id))) or 0)
    page_info = build_page_info(page=page, page_size=METADATA_PAGE_SIZE, total=total)
    rows = db.scalars(
        select(Tag)
        .options(noload(Tag.items))
        .order_by(func.lower(Tag.name).asc(), Tag.id.asc())
        .offset((page_info.page - 1) * page_info.page_size)
        .limit(page_info.page_size)
    ).all()
    return MetadataListPage(rows=list(rows), page_info=page_info)


def list_creator_page(
    db: Session,
    *,
    page: str | int | None = None,
) -> MetadataListPage[Creator]:
    total = int(db.scalar(select(func.count(Creator.id))) or 0)
    page_info = build_page_info(page=page, page_size=METADATA_PAGE_SIZE, total=total)
    rows = db.scalars(
        select(Creator)
        .options(noload(Creator.items))
        .order_by(func.lower(Creator.name).asc(), Creator.id.asc())
        .offset((page_info.page - 1) * page_info.page_size)
        .limit(page_info.page_size)
    ).all()
    return MetadataListPage(rows=list(rows), page_info=page_info)
