from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.services.exporter import BACKUP_SCHEMA

TABLE_NAMES = {
    "items",
    "tags",
    "creators",
    "item_tags",
    "item_creators",
    "user_item_states",
}
VALID_STATUSES = {"wish", "watching", "watched", "like", "dislike", "ignore"}


class BackupError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


def _raise(code: str, detail: str | None = None) -> None:
    raise BackupError(code, detail)


def _rows_from_payload(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if payload.get("schema") != BACKUP_SCHEMA:
        _raise("schema_mismatch")
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        _raise("missing_tables")
    rows: dict[str, list[dict[str, Any]]] = {}
    for table_name in TABLE_NAMES:
        table_rows = tables.get(table_name)
        if not isinstance(table_rows, list):
            _raise("invalid_table", table_name)
        if not all(isinstance(row, dict) for row in table_rows):
            _raise("invalid_rows", table_name)
        rows[table_name] = table_rows
    return rows


def _require_keys(rows: list[dict[str, Any]], table_name: str, keys: set[str]) -> None:
    for row in rows:
        for key in keys:
            if key not in row or row.get(key) in {None, ""}:
                _raise("missing_field", f"{table_name}.{key}")


def _validate_preview_rows(rows: dict[str, list[dict[str, Any]]]) -> None:
    _require_keys(rows["items"], "items", {"id", "title"})
    _require_keys(rows["tags"], "tags", {"id", "name"})
    _require_keys(rows["creators"], "creators", {"id", "name"})
    _require_keys(rows["item_tags"], "item_tags", {"item_id", "tag_id"})
    _require_keys(
        rows["item_creators"],
        "item_creators",
        {"item_id", "creator_id"},
    )
    _require_keys(rows["user_item_states"], "user_item_states", {"item_id", "status"})
    for row in rows["user_item_states"]:
        if str(row.get("status", "")).strip() not in VALID_STATUSES:
            _raise("invalid_rows", "user_item_states.status")


def preview_backup_data(payload: dict[str, Any]) -> dict[str, int | str]:
    rows = _rows_from_payload(payload)
    _validate_preview_rows(rows)
    return {
        "schema": BACKUP_SCHEMA,
        "items": len(rows["items"]),
        "tags": len(rows["tags"]),
        "creators": len(rows["creators"]),
        "item_tags": len(rows["item_tags"]),
        "item_creators": len(rows["item_creators"]),
        "user_item_states": len(rows["user_item_states"]),
    }


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _datetime_or_none(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _required_text(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key, "")).strip()
    if not value:
        _raise("missing_field", key)
    return value


def _set_optional_datetime(model: Any, key: str, value: Any) -> None:
    parsed = _datetime_or_none(value)
    if parsed is not None:
        setattr(model, key, parsed)


def _set_item_fields(item: models.Item, row: dict[str, Any]) -> None:
    item.title = _required_text(row, "title")
    item.cover_path = row.get("cover_path") or None
    item.summary = row.get("summary") or None
    item.release_date = row.get("release_date") or None
    item.extra = row.get("extra") or None
    _set_optional_datetime(item, "created_at", row.get("created_at"))
    _set_optional_datetime(item, "updated_at", row.get("updated_at"))


def _set_tag_fields(tag: models.Tag, row: dict[str, Any]) -> None:
    tag.name = _required_text(row, "name")
    tag.category = row.get("category") or None
    _set_optional_datetime(tag, "created_at", row.get("created_at"))


def _set_creator_fields(creator: models.Creator, row: dict[str, Any]) -> None:
    creator.name = _required_text(row, "name")
    creator.type = str(row.get("type") or "other").strip() or "other"
    creator.avatar_path = row.get("avatar_path") or None
    _set_optional_datetime(creator, "created_at", row.get("created_at"))


def _merge_tags(
    db: Session,
    rows: list[dict[str, Any]],
    result: dict[str, int],
) -> dict[int, int]:
    id_map: dict[int, int] = {}
    for row in rows:
        backup_id = _int_or_none(row.get("id"))
        name = _required_text(row, "name")
        tag = db.get(models.Tag, backup_id) if backup_id is not None else None
        if tag is None:
            tag = db.scalar(
                select(models.Tag).where(func.lower(models.Tag.name) == name.lower())
            )
        if tag is None:
            tag = models.Tag(id=backup_id)
            db.add(tag)
            result["created"] += 1
        else:
            result["updated"] += 1
        _set_tag_fields(tag, row)
        db.flush()
        if backup_id is not None:
            id_map[backup_id] = tag.id
    return id_map


def _merge_creators(
    db: Session,
    rows: list[dict[str, Any]],
    result: dict[str, int],
) -> dict[int, int]:
    id_map: dict[int, int] = {}
    for row in rows:
        backup_id = _int_or_none(row.get("id"))
        name = _required_text(row, "name")
        creator = db.get(models.Creator, backup_id) if backup_id is not None else None
        if creator is None:
            creator = db.scalar(
                select(models.Creator).where(
                    func.lower(models.Creator.name) == name.lower()
                )
            )
        if creator is None:
            creator = models.Creator(id=backup_id)
            db.add(creator)
            result["created"] += 1
        else:
            result["updated"] += 1
        _set_creator_fields(creator, row)
        db.flush()
        if backup_id is not None:
            id_map[backup_id] = creator.id
    return id_map


def _merge_items(
    db: Session,
    rows: list[dict[str, Any]],
    result: dict[str, int],
) -> dict[int, int]:
    id_map: dict[int, int] = {}
    for row in rows:
        backup_id = _int_or_none(row.get("id"))
        title = _required_text(row, "title")
        release_date = row.get("release_date") or None
        item = db.get(models.Item, backup_id) if backup_id is not None else None
        if item is None:
            item = db.scalar(
                select(models.Item).where(
                    models.Item.title == title,
                    models.Item.release_date == release_date,
                )
            )
        if item is None:
            item = models.Item(id=backup_id)
            db.add(item)
            result["created"] += 1
        else:
            result["updated"] += 1
        _set_item_fields(item, row)
        db.flush()
        if backup_id is not None:
            id_map[backup_id] = item.id
    return id_map


def _merge_item_tags(
    db: Session,
    rows: list[dict[str, Any]],
    item_ids: dict[int, int],
    tag_ids: dict[int, int],
    result: dict[str, int],
) -> None:
    for row in rows:
        item_id = item_ids.get(_int_or_none(row.get("item_id")) or -1)
        tag_id = tag_ids.get(_int_or_none(row.get("tag_id")) or -1)
        if item_id is None or tag_id is None:
            result["skipped"] += 1
            continue
        if db.get(models.ItemTag, (item_id, tag_id)) is None:
            db.add(models.ItemTag(item_id=item_id, tag_id=tag_id))
            result["created"] += 1


def _merge_item_creators(
    db: Session,
    rows: list[dict[str, Any]],
    item_ids: dict[int, int],
    creator_ids: dict[int, int],
    result: dict[str, int],
) -> None:
    for row in rows:
        item_id = item_ids.get(_int_or_none(row.get("item_id")) or -1)
        creator_id = creator_ids.get(_int_or_none(row.get("creator_id")) or -1)
        if item_id is None or creator_id is None:
            result["skipped"] += 1
            continue
        if db.get(models.ItemCreator, (item_id, creator_id)) is None:
            db.add(models.ItemCreator(item_id=item_id, creator_id=creator_id))
            result["created"] += 1


def _merge_states(
    db: Session,
    rows: list[dict[str, Any]],
    item_ids: dict[int, int],
    result: dict[str, int],
) -> None:
    for row in rows:
        item_id = item_ids.get(_int_or_none(row.get("item_id")) or -1)
        status = str(row.get("status", "")).strip()
        if item_id is None or status not in VALID_STATUSES:
            result["skipped"] += 1
            continue
        state = db.scalar(
            select(models.UserItemState).where(models.UserItemState.item_id == item_id)
        )
        if state is None:
            state = models.UserItemState(item_id=item_id, status=status)
            db.add(state)
            result["created"] += 1
        else:
            result["updated"] += 1
        state.status = status
        state.rating = _int_or_none(row.get("rating"))
        state.review = row.get("review") or None
        _set_optional_datetime(state, "created_at", row.get("created_at"))
        _set_optional_datetime(state, "updated_at", row.get("updated_at"))


def restore_backup_data(db: Session, payload: dict[str, Any]) -> dict[str, int]:
    rows = _rows_from_payload(payload)
    result = {"created": 0, "updated": 0, "skipped": 0}
    with db.begin():
        tag_ids = _merge_tags(db, rows["tags"], result)
        creator_ids = _merge_creators(db, rows["creators"], result)
        item_ids = _merge_items(db, rows["items"], result)
        _merge_item_tags(db, rows["item_tags"], item_ids, tag_ids, result)
        _merge_item_creators(
            db,
            rows["item_creators"],
            item_ids,
            creator_ids,
            result,
        )
        _merge_states(db, rows["user_item_states"], item_ids, result)
    return result
