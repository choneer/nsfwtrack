from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models

BACKUP_SCHEMA = "nsfwtrack.backup.v1"


def timestamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _item_row(item: models.Item) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "cover_path": item.cover_path,
        "summary": item.summary,
        "release_date": item.release_date,
        "extra": item.extra,
        "created_at": _format_datetime(item.created_at),
        "updated_at": _format_datetime(item.updated_at),
    }


def _tag_row(tag: models.Tag) -> dict[str, Any]:
    return {
        "id": tag.id,
        "name": tag.name,
        "category": tag.category,
        "created_at": _format_datetime(tag.created_at),
    }


def _creator_row(creator: models.Creator) -> dict[str, Any]:
    return {
        "id": creator.id,
        "name": creator.name,
        "type": creator.type,
        "avatar_path": creator.avatar_path,
        "created_at": _format_datetime(creator.created_at),
    }


def _state_row(state: models.UserItemState) -> dict[str, Any]:
    return {
        "id": state.id,
        "item_id": state.item_id,
        "status": state.status,
        "rating": state.rating,
        "review": state.review,
        "created_at": _format_datetime(state.created_at),
        "updated_at": _format_datetime(state.updated_at),
    }


def _collection_row(collection: models.Collection) -> dict[str, Any]:
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "created_at": _format_datetime(collection.created_at),
        "updated_at": _format_datetime(collection.updated_at),
    }


def _saved_view_row(saved_view: models.SavedView) -> dict[str, Any]:
    return {
        "id": saved_view.id,
        "name": saved_view.name,
        "query_string": saved_view.query_string,
        "created_at": _format_datetime(saved_view.created_at),
        "updated_at": _format_datetime(saved_view.updated_at),
    }


def _item_activity_row(activity: models.ItemActivity) -> dict[str, Any]:
    return {
        "id": activity.id,
        "item_id": activity.item_id,
        "last_viewed_at": _format_datetime(activity.last_viewed_at),
        "view_count": activity.view_count,
        "last_edited_at": _format_datetime(activity.last_edited_at),
        "edit_count": activity.edit_count,
        "created_at": _format_datetime(activity.created_at),
        "updated_at": _format_datetime(activity.updated_at),
    }


def _app_setting_row(setting: models.AppSetting) -> dict[str, Any]:
    return {
        "id": setting.id,
        "key": setting.key,
        "value": setting.value,
        "created_at": _format_datetime(setting.created_at),
        "updated_at": _format_datetime(setting.updated_at),
    }


def _item_source_row(source: models.ItemSource) -> dict[str, Any]:
    return {
        "id": source.id,
        "item_id": source.item_id,
        "url": source.url,
        "normalized_url": source.normalized_url,
        "title": source.title,
        "created_at": _format_datetime(source.created_at),
    }


def export_backup_data(db: Session) -> dict[str, Any]:
    items = db.scalars(select(models.Item).order_by(models.Item.id.asc())).all()
    tags = db.scalars(select(models.Tag).order_by(models.Tag.id.asc())).all()
    creators = db.scalars(select(models.Creator).order_by(models.Creator.id.asc())).all()
    collections = db.scalars(
        select(models.Collection).order_by(models.Collection.id.asc())
    ).all()
    item_tags = db.scalars(
        select(models.ItemTag).order_by(models.ItemTag.item_id, models.ItemTag.tag_id)
    ).all()
    item_creators = db.scalars(
        select(models.ItemCreator).order_by(
            models.ItemCreator.item_id,
            models.ItemCreator.creator_id,
        )
    ).all()
    item_collections = db.scalars(
        select(models.ItemCollection).order_by(
            models.ItemCollection.item_id,
            models.ItemCollection.collection_id,
        )
    ).all()
    states = db.scalars(
        select(models.UserItemState).order_by(models.UserItemState.id.asc())
    ).all()
    saved_views = db.scalars(
        select(models.SavedView).order_by(models.SavedView.id.asc())
    ).all()
    item_activity = db.scalars(
        select(models.ItemActivity).order_by(models.ItemActivity.id.asc())
    ).all()
    app_settings = db.scalars(
        select(models.AppSetting).order_by(models.AppSetting.key.asc())
    ).all()
    item_sources = db.scalars(
        select(models.ItemSource).order_by(models.ItemSource.id.asc())
    ).all()
    return {
        "schema": BACKUP_SCHEMA,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tables": {
            "items": [_item_row(item) for item in items],
            "tags": [_tag_row(tag) for tag in tags],
            "creators": [_creator_row(creator) for creator in creators],
            "collections": [_collection_row(collection) for collection in collections],
            "item_tags": [
                {"item_id": row.item_id, "tag_id": row.tag_id} for row in item_tags
            ],
            "item_creators": [
                {"item_id": row.item_id, "creator_id": row.creator_id}
                for row in item_creators
            ],
            "item_collections": [
                {"item_id": row.item_id, "collection_id": row.collection_id}
                for row in item_collections
            ],
            "user_item_states": [_state_row(state) for state in states],
            "saved_views": [_saved_view_row(saved_view) for saved_view in saved_views],
            "item_activity": [
                _item_activity_row(activity) for activity in item_activity
            ],
            "app_settings": [_app_setting_row(setting) for setting in app_settings],
            "item_sources": [_item_source_row(source) for source in item_sources],
        },
    }


def export_backup_json(db: Session) -> str:
    return json.dumps(export_backup_data(db), ensure_ascii=False, indent=2)


def export_items_csv(db: Session) -> str:
    rows = db.scalars(
        select(models.Item)
        .options(
            selectinload(models.Item.tags),
            selectinload(models.Item.creators),
            selectinload(models.Item.collections),
            selectinload(models.Item.state),
        )
        .order_by(models.Item.id.asc())
    ).all()
    source_rows = db.scalars(
        select(models.ItemSource).order_by(models.ItemSource.item_id, models.ItemSource.id)
    ).all()
    sources_by_item: dict[int, list[models.ItemSource]] = {}
    for source in source_rows:
        sources_by_item.setdefault(source.item_id, []).append(source)
    output = StringIO()
    fieldnames = [
        "id",
        "title",
        "cover_path",
        "summary",
        "release_date",
        "tags",
        "creators",
        "collections",
        "sources",
        "status",
        "rating",
        "review",
        "created_at",
        "updated_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for item in rows:
        state = item.state
        writer.writerow(
            {
                "id": item.id,
                "title": item.title,
                "cover_path": item.cover_path or "",
                "summary": item.summary or "",
                "release_date": item.release_date or "",
                "tags": ", ".join(tag.name for tag in sorted(item.tags, key=lambda row: row.name)),
                "creators": ", ".join(
                    creator.name for creator in sorted(item.creators, key=lambda row: row.name)
                ),
                "collections": ";".join(
                    collection.name
                    for collection in sorted(item.collections, key=lambda row: row.name)
                ),
                "sources": json.dumps(
                    [
                        {"title": source.title, "url": source.url}
                        for source in sources_by_item.get(item.id, [])
                    ],
                    ensure_ascii=False,
                ),
                "status": state.status if state else "",
                "rating": state.rating if state and state.rating is not None else "",
                "review": state.review if state and state.review else "",
                "created_at": _format_datetime(item.created_at) or "",
                "updated_at": _format_datetime(item.updated_at) or "",
            }
        )
    return output.getvalue()
