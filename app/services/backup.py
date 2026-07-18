from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.services.exporter import (
    BACKUP_SCHEMA_V1,
    BACKUP_SCHEMA_V2,
    SUPPORTED_BACKUP_SCHEMAS,
)
from app.services.local_media import LocalMediaPathError, normalize_local_media_path
from app.services.saved_views import (
    MAX_SAVED_VIEW_NAME_LENGTH,
    normalize_saved_view_query_string,
)
from app.services.settings import (
    AppSettingsError,
    upsert_setting_row,
    validate_setting_value,
)
from app.services.sources import (
    SourceError,
    SourceTrackingMetadata,
    normalize_source_url,
    validate_source_tracking_metadata,
)

CORE_TABLE_NAMES = {
    "items",
    "tags",
    "creators",
    "item_tags",
    "item_creators",
    "user_item_states",
}
OPTIONAL_TABLE_NAMES = {
    "collections",
    "item_collections",
    "saved_views",
    "item_activity",
    "app_settings",
    "item_sources",
}
TABLE_NAMES = CORE_TABLE_NAMES | OPTIONAL_TABLE_NAMES
VALID_STATUSES = {"wish", "watching", "watched", "like", "dislike", "ignore"}


class BackupError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


def _raise(code: str, detail: str | None = None) -> None:
    raise BackupError(code, detail)


@dataclass(frozen=True)
class _PreparedItemSource:
    backup_item_id: int
    url: str
    normalized_url: str
    title: str | None
    created_at: datetime | None
    metadata: SourceTrackingMetadata


@dataclass(frozen=True)
class _ItemSourcePlan:
    to_create: tuple[_PreparedItemSource, ...]
    reused: int
    conflicts: tuple[str, ...]
    errors: tuple[str, ...]
    provider_sources: int
    legacy_sources: int


@dataclass(frozen=True)
class _LocalItemSource:
    id: int
    item_id: int
    normalized_url: str
    provider_key: str | None
    external_id: str | None


def _backup_schema(payload: dict[str, Any]) -> str:
    schema = payload.get("schema")
    if schema not in SUPPORTED_BACKUP_SCHEMAS:
        _raise("schema_mismatch")
    return str(schema)


def _rows_from_payload(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    _backup_schema(payload)
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        _raise("missing_tables")
    rows: dict[str, list[dict[str, Any]]] = {}
    for table_name in CORE_TABLE_NAMES:
        table_rows = tables.get(table_name)
        if not isinstance(table_rows, list):
            _raise("invalid_table", table_name)
        if not all(isinstance(row, dict) for row in table_rows):
            _raise("invalid_rows", table_name)
        rows[table_name] = table_rows
    for table_name in OPTIONAL_TABLE_NAMES:
        table_rows = tables.get(table_name, [])
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


def _validate_preview_rows(
    rows: dict[str, list[dict[str, Any]]],
    input_schema: str,
) -> None:
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
    for row in rows["items"]:
        try:
            normalize_local_media_path(row.get("cover_path"))
        except LocalMediaPathError:
            _raise("invalid_local_media_path", "items.cover_path")
    for row in rows["creators"]:
        try:
            normalize_local_media_path(row.get("avatar_path"))
        except LocalMediaPathError:
            _raise("invalid_local_media_path", "creators.avatar_path")
    _require_keys(
        rows["item_sources"],
        "item_sources",
        {"item_id", "url", "normalized_url"},
    )
    seen_item_ids: set[int] = set()
    for row in rows["items"]:
        item_id = _safe_int_or_none(row.get("id"))
        if item_id is None or item_id <= 0:
            _raise("invalid_rows", "items.id")
        if item_id in seen_item_ids:
            _raise("duplicate_item_id", str(item_id))
        seen_item_ids.add(item_id)
    for row in rows["item_sources"]:
        _prepare_item_source(row, input_schema)


def _prepare_item_source(
    row: dict[str, Any],
    input_schema: str,
) -> _PreparedItemSource:
    backup_item_id = _safe_int_or_none(row.get("item_id"))
    if backup_item_id is None or backup_item_id <= 0:
        _raise("invalid_rows", "item_sources.item_id")
    try:
        normalized = normalize_source_url(row.get("url"))
    except SourceError:
        _raise("invalid_rows", "item_sources.url")
    if normalized != str(row.get("normalized_url") or ""):
        _raise("invalid_rows", "item_sources.normalized_url")

    if input_schema == BACKUP_SCHEMA_V1:
        if any(
            row.get(field) is not None
            for field in (
                "provider_key",
                "external_id",
                "last_checked_at",
                "metadata_hash",
            )
        ):
            _raise("v1_source_metadata_not_allowed", "item_sources")
        metadata = SourceTrackingMetadata(None, None, None, None)
    else:
        for field in (
            "provider_key",
            "external_id",
            "last_checked_at",
            "metadata_hash",
        ):
            if field not in row:
                _raise("missing_field", f"item_sources.{field}")
        try:
            metadata = validate_source_tracking_metadata(
                provider_key=row.get("provider_key"),
                external_id=row.get("external_id"),
                last_checked_at=row.get("last_checked_at"),
                metadata_hash=row.get("metadata_hash"),
            )
        except SourceError as exc:
            _raise(exc.code, "item_sources")
    return _PreparedItemSource(
        backup_item_id=backup_item_id,
        url=str(row.get("url") or "").strip(),
        normalized_url=normalized,
        title=" ".join(str(row.get("title") or "").split())[:255] or None,
        created_at=_safe_datetime(row.get("created_at")),
        metadata=metadata,
    )


def _prepared_item_sources(
    rows: dict[str, list[dict[str, Any]]],
    input_schema: str,
) -> tuple[_PreparedItemSource, ...]:
    return tuple(_prepare_item_source(row, input_schema) for row in rows["item_sources"])


def _source_payload_errors(
    prepared: tuple[_PreparedItemSource, ...],
) -> tuple[str, ...]:
    errors: list[str] = []
    seen_urls: dict[str, tuple[str | None, str | None, datetime | None, str | None]] = {}
    seen_identities: dict[tuple[str, str], tuple[str, datetime | None, str | None]] = {}
    for source in prepared:
        metadata = source.metadata
        identity = (
            (metadata.provider_key, metadata.external_id)
            if metadata.provider_key is not None and metadata.external_id is not None
            else None
        )
        metadata_facts = (
            metadata.provider_key,
            metadata.external_id,
            metadata.last_checked_at,
            metadata.metadata_hash,
        )
        previous_url = seen_urls.get(source.normalized_url)
        if previous_url is not None:
            errors.append("duplicate_source_url")
            if previous_url[:2] != metadata_facts[:2]:
                errors.append("source_url_identity_conflict")
            if previous_url[2:] != metadata_facts[2:]:
                errors.append("source_metadata_conflict")
        else:
            seen_urls[source.normalized_url] = metadata_facts
        if identity is not None:
            previous_identity = seen_identities.get(identity)
            identity_facts = (
                source.normalized_url,
                metadata.last_checked_at,
                metadata.metadata_hash,
            )
            if previous_identity is not None:
                errors.append("duplicate_provider_identity")
                if previous_identity[0] != source.normalized_url:
                    errors.append("source_identity_url_conflict")
                if previous_identity[1:] != identity_facts[1:]:
                    errors.append("source_metadata_conflict")
            else:
                seen_identities[identity] = identity_facts
    return tuple(dict.fromkeys(errors))


def _safe_int_or_none(value: Any) -> int | None:
    try:
        return _int_or_none(value)
    except (TypeError, ValueError):
        return None


def _valid_collection_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("name", "")).strip()]


def _preview_collection_counts(
    rows: dict[str, list[dict[str, Any]]],
    db: Session | None,
) -> dict[str, int]:
    valid_collections = _valid_collection_rows(rows["collections"])
    collection_errors = len(rows["collections"]) - len(valid_collections)
    existing_names: set[str] = set()
    if db is not None:
        existing_names = {
            name.casefold() for name in db.scalars(select(models.Collection.name)).all()
        }

    backup_collection_ids: set[int] = set()
    seen_names: set[str] = set()
    collections_to_create = 0
    collections_to_merge = 0
    for row in valid_collections:
        backup_id = _safe_int_or_none(row.get("id"))
        name = str(row.get("name", "")).strip()
        key = name.casefold()
        if backup_id is not None:
            backup_collection_ids.add(backup_id)
        if key in seen_names:
            collections_to_merge += 1
            continue
        seen_names.add(key)
        if key in existing_names:
            collections_to_merge += 1
        else:
            collections_to_create += 1

    backup_item_ids = {
        item_id
        for item_id in (_safe_int_or_none(row.get("id")) for row in rows["items"])
        if item_id is not None
    }
    seen_pairs: set[tuple[int, int]] = set()
    restorable_item_collections = 0
    unrestorable_item_collections = 0
    for row in rows["item_collections"]:
        item_id = _safe_int_or_none(row.get("item_id"))
        collection_id = _safe_int_or_none(row.get("collection_id"))
        if (
            item_id is None
            or collection_id is None
            or item_id not in backup_item_ids
            or collection_id not in backup_collection_ids
        ):
            unrestorable_item_collections += 1
            collection_errors += 1
            continue
        pair = (item_id, collection_id)
        if pair in seen_pairs:
            unrestorable_item_collections += 1
            continue
        seen_pairs.add(pair)
        restorable_item_collections += 1

    return {
        "collections": len(rows["collections"]),
        "item_collections": len(rows["item_collections"]),
        "collections_to_create": collections_to_create,
        "collections_to_merge": collections_to_merge,
        "item_collections_restorable": restorable_item_collections,
        "item_collections_unrestorable": unrestorable_item_collections,
        "collection_errors": collection_errors,
    }


def _valid_saved_view_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if str(row.get("name", "")).strip()
        and len(str(row.get("name", "")).strip()) <= MAX_SAVED_VIEW_NAME_LENGTH
    ]


def _preview_saved_view_counts(
    rows: dict[str, list[dict[str, Any]]],
    db: Session | None,
) -> dict[str, int]:
    valid_saved_views = _valid_saved_view_rows(rows["saved_views"])
    saved_view_errors = len(rows["saved_views"]) - len(valid_saved_views)
    existing_names: set[str] = set()
    if db is not None:
        existing_names = {
            name.casefold() for name in db.scalars(select(models.SavedView.name)).all()
        }

    seen_names: set[str] = set()
    saved_views_to_create = 0
    saved_views_to_update = 0
    for row in valid_saved_views:
        key = str(row.get("name", "")).strip().casefold()
        if key in seen_names:
            saved_view_errors += 1
            continue
        seen_names.add(key)
        if key in existing_names:
            saved_views_to_update += 1
        else:
            saved_views_to_create += 1

    return {
        "saved_views": len(rows["saved_views"]),
        "saved_views_to_create": saved_views_to_create,
        "saved_views_to_update": saved_views_to_update,
        "saved_view_errors": saved_view_errors,
    }


def _valid_item_activity_rows(
    rows: dict[str, list[dict[str, Any]]],
) -> tuple[int, int, int]:
    backup_item_ids = {
        item_id
        for item_id in (_safe_int_or_none(row.get("id")) for row in rows["items"])
        if item_id is not None
    }
    seen_item_ids: set[int] = set()
    restorable = 0
    skipped = 0
    errors = 0
    for row in rows["item_activity"]:
        item_id = _safe_int_or_none(row.get("item_id"))
        if item_id is None or item_id not in backup_item_ids:
            skipped += 1
            errors += 1
            continue
        if item_id in seen_item_ids:
            skipped += 1
            continue
        seen_item_ids.add(item_id)
        restorable += 1
    return restorable, skipped, errors


def _preview_item_activity_counts(rows: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    restorable, skipped, errors = _valid_item_activity_rows(rows)
    return {
        "item_activity": len(rows["item_activity"]),
        "item_activity_restorable": restorable,
        "item_activity_skipped": skipped,
        "item_activity_errors": errors,
    }


def _preview_app_settings_counts(rows: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    valid = 0
    skipped = 0
    errors = 0
    seen_keys: set[str] = set()
    for row in rows["app_settings"]:
        key = str(row.get("key") or "").strip()
        try:
            validate_setting_value(key, row.get("value"))
        except AppSettingsError:
            skipped += 1
            errors += 1
            continue
        if key in seen_keys:
            skipped += 1
            continue
        seen_keys.add(key)
        valid += 1
    return {
        "app_settings": len(rows["app_settings"]),
        "app_settings_valid": valid,
        "app_settings_skipped": skipped,
        "app_settings_errors": errors,
    }


def _preview_item_id_map(
    rows: dict[str, list[dict[str, Any]]],
    db: Session | None,
) -> dict[int, int | None]:
    mapping: dict[int, int | None] = {}
    for row in rows["items"]:
        backup_id = _safe_int_or_none(row.get("id"))
        if backup_id is None:
            continue
        if db is None:
            mapping[backup_id] = None
            continue
        item = db.get(models.Item, backup_id)
        if item is None:
            item = db.scalar(
                select(models.Item).where(
                    models.Item.title == str(row.get("title") or "").strip(),
                    models.Item.release_date == (row.get("release_date") or None),
                )
            )
        mapping[backup_id] = item.id if item is not None else None
    return mapping


def _classify_item_sources(
    db: Session | None,
    prepared: tuple[_PreparedItemSource, ...],
    item_ids: dict[int, int | None],
) -> _ItemSourcePlan:
    local_sources = _load_local_item_sources(db) if db is not None else []
    by_url: dict[str, list[_LocalItemSource]] = {}
    by_identity: dict[tuple[str, str], list[_LocalItemSource]] = {}
    for source in local_sources:
        by_url.setdefault(source.normalized_url, []).append(source)
        if source.provider_key is not None and source.external_id is not None:
            by_identity.setdefault((source.provider_key, source.external_id), []).append(
                source
            )

    creates: list[_PreparedItemSource] = []
    conflicts: list[str] = []
    errors: list[str] = []
    reused = 0
    provider_sources = 0
    legacy_sources = 0
    for incoming in prepared:
        metadata = incoming.metadata
        identity = (
            (metadata.provider_key, metadata.external_id)
            if metadata.provider_key is not None and metadata.external_id is not None
            else None
        )
        if identity is None:
            legacy_sources += 1
        else:
            provider_sources += 1
        if incoming.backup_item_id not in item_ids:
            errors.append("source_missing_item")
            continue
        target_item_id = item_ids[incoming.backup_item_id]
        candidates = list(by_url.get(incoming.normalized_url, ()))
        if identity is not None:
            candidates.extend(by_identity.get(identity, ()))
        unique_candidates = {candidate.id: candidate for candidate in candidates}
        if not unique_candidates:
            creates.append(incoming)
            continue
        if len(unique_candidates) != 1 or target_item_id is None:
            conflicts.append("source_local_mapping_conflict")
            continue
        existing = next(iter(unique_candidates.values()))
        if (
            existing.item_id == target_item_id
            and existing.normalized_url == incoming.normalized_url
            and existing.provider_key == metadata.provider_key
            and existing.external_id == metadata.external_id
        ):
            reused += 1
            continue
        if existing.normalized_url == incoming.normalized_url:
            conflicts.append("source_url_local_conflict")
        elif identity is not None:
            conflicts.append("source_identity_local_conflict")
        else:
            conflicts.append("source_local_mapping_conflict")
    return _ItemSourcePlan(
        to_create=tuple(creates),
        reused=reused,
        conflicts=tuple(conflicts),
        errors=tuple(errors),
        provider_sources=provider_sources,
        legacy_sources=legacy_sources,
    )


def _load_local_item_sources(db: Session) -> list[_LocalItemSource]:
    columns = {
        column["name"]
        for column in inspect(db.get_bind()).get_columns(models.ItemSource.__tablename__)
    }
    tracking_available = {
        "provider_key",
        "external_id",
        "last_checked_at",
        "metadata_hash",
    }.issubset(columns)
    selected = [
        models.ItemSource.id,
        models.ItemSource.item_id,
        models.ItemSource.normalized_url,
    ]
    if tracking_available:
        selected.extend(
            [models.ItemSource.provider_key, models.ItemSource.external_id]
        )
    rows = db.execute(
        select(*selected).order_by(models.ItemSource.id)
    ).all()
    return [
        _LocalItemSource(
            id=int(row[0]),
            item_id=int(row[1]),
            normalized_url=str(row[2]),
            provider_key=(None if not tracking_available else row[3]),
            external_id=(None if not tracking_available else row[4]),
        )
        for row in rows
    ]


def _preview_item_source_counts(
    rows: dict[str, list[dict[str, Any]]],
    input_schema: str,
    db: Session | None,
) -> dict[str, int | bool]:
    prepared = _prepared_item_sources(rows, input_schema)
    payload_errors = _source_payload_errors(prepared)
    plan = _classify_item_sources(db, prepared, _preview_item_id_map(rows, db))
    conflict_count = len(payload_errors) + len(plan.conflicts)
    error_count = len(payload_errors) + len(plan.errors)
    skipped = plan.reused + conflict_count + len(plan.errors)
    return {
        "item_sources": len(rows["item_sources"]),
        "item_sources_restorable": len(plan.to_create),
        "item_sources_to_create": len(plan.to_create),
        "item_sources_to_reuse": plan.reused,
        "item_sources_conflicts": conflict_count,
        "item_sources_payload_errors": len(payload_errors),
        "item_sources_skipped": skipped,
        "item_sources_errors": error_count,
        "provider_sources": plan.provider_sources,
        "legacy_sources": plan.legacy_sources,
        "can_restore": conflict_count == 0 and error_count == 0,
    }


def preview_backup_data(
    payload: dict[str, Any],
    db: Session | None = None,
) -> dict[str, int | str | bool]:
    input_schema = _backup_schema(payload)
    rows = _rows_from_payload(payload)
    _validate_preview_rows(rows, input_schema)
    return {
        "schema": input_schema,
        "input_schema": input_schema,
        "items": len(rows["items"]),
        "tags": len(rows["tags"]),
        "creators": len(rows["creators"]),
        "item_tags": len(rows["item_tags"]),
        "item_creators": len(rows["item_creators"]),
        "user_item_states": len(rows["user_item_states"]),
        **_preview_collection_counts(rows, db),
        **_preview_saved_view_counts(rows, db),
        **_preview_item_activity_counts(rows),
        **_preview_app_settings_counts(rows),
        **_preview_item_source_counts(rows, input_schema, db),
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


def _set_collection_fields(collection: models.Collection, row: dict[str, Any]) -> None:
    collection.name = _required_text(row, "name")
    collection.description = row.get("description") or None
    _set_optional_datetime(collection, "created_at", row.get("created_at"))
    _set_optional_datetime(collection, "updated_at", row.get("updated_at"))


def _set_saved_view_fields(saved_view: models.SavedView, row: dict[str, Any]) -> None:
    saved_view.name = _required_text(row, "name")[:MAX_SAVED_VIEW_NAME_LENGTH]
    saved_view.query_string = normalize_saved_view_query_string(
        row.get("query_string") or ""
    )
    _set_optional_datetime(saved_view, "created_at", row.get("created_at"))
    _set_optional_datetime(saved_view, "updated_at", row.get("updated_at"))


def _safe_count(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _safe_datetime(value: Any) -> datetime | None:
    try:
        return _datetime_or_none(value)
    except (TypeError, ValueError):
        return None


def _newer_datetime(
    current_value: datetime | None,
    backup_value: datetime | None,
) -> datetime | None:
    if backup_value is None:
        return current_value
    if current_value is None or backup_value > current_value:
        return backup_value
    return current_value


def _set_activity_fields(
    activity: models.ItemActivity,
    row: dict[str, Any],
) -> None:
    activity.last_viewed_at = _newer_datetime(
        activity.last_viewed_at,
        _safe_datetime(row.get("last_viewed_at")),
    )
    activity.view_count = max(activity.view_count or 0, _safe_count(row.get("view_count")))
    activity.last_edited_at = _newer_datetime(
        activity.last_edited_at,
        _safe_datetime(row.get("last_edited_at")),
    )
    activity.edit_count = max(activity.edit_count or 0, _safe_count(row.get("edit_count")))
    created_at = _safe_datetime(row.get("created_at"))
    if created_at is not None and (
        activity.created_at is None or created_at < activity.created_at
    ):
        activity.created_at = created_at
    activity.updated_at = _newer_datetime(
        activity.updated_at,
        _safe_datetime(row.get("updated_at")),
    )


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


def _merge_collections(
    db: Session,
    rows: list[dict[str, Any]],
    result: dict[str, int],
) -> dict[int, int]:
    id_map: dict[int, int] = {}
    seen_names: set[str] = set()
    for row in rows:
        backup_id = _safe_int_or_none(row.get("id"))
        name = str(row.get("name", "")).strip()
        if not name:
            result["skipped"] += 1
            result["collections_skipped"] += 1
            result["collection_errors"] += 1
            continue

        key = name.casefold()
        collection = db.scalar(
            select(models.Collection).where(func.lower(models.Collection.name) == name.lower())
        )
        if collection is None and backup_id is not None:
            collection = db.get(models.Collection, backup_id)

        if key in seen_names:
            if collection is not None and backup_id is not None:
                id_map[backup_id] = collection.id
            result["skipped"] += 1
            result["collections_skipped"] += 1
            continue

        seen_names.add(key)
        if collection is None:
            collection = models.Collection(id=backup_id)
            db.add(collection)
            result["created"] += 1
            result["collections_created"] += 1
        else:
            result["updated"] += 1
        _set_collection_fields(collection, row)
        db.flush()
        if backup_id is not None:
            id_map[backup_id] = collection.id
    return id_map


def _merge_saved_views(
    db: Session,
    rows: list[dict[str, Any]],
    result: dict[str, int],
) -> None:
    seen_names: set[str] = set()
    for row in rows:
        backup_id = _safe_int_or_none(row.get("id"))
        name = str(row.get("name", "")).strip()
        if not name or len(name) > MAX_SAVED_VIEW_NAME_LENGTH:
            result["skipped"] += 1
            result["saved_views_skipped"] += 1
            result["saved_view_errors"] += 1
            continue

        key = name.casefold()
        if key in seen_names:
            result["skipped"] += 1
            result["saved_views_skipped"] += 1
            result["saved_view_errors"] += 1
            continue
        seen_names.add(key)

        saved_view = db.scalar(
            select(models.SavedView).where(
                func.lower(models.SavedView.name) == name.lower()
            )
        )
        if saved_view is None and backup_id is not None:
            saved_view = db.get(models.SavedView, backup_id)

        if saved_view is None:
            saved_view = models.SavedView(id=backup_id)
            db.add(saved_view)
            result["created"] += 1
            result["saved_views_created"] += 1
        else:
            result["updated"] += 1
            result["saved_views_updated"] += 1
        _set_saved_view_fields(saved_view, row)
        db.flush()


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


def _merge_item_collections(
    db: Session,
    rows: list[dict[str, Any]],
    item_ids: dict[int, int],
    collection_ids: dict[int, int],
    result: dict[str, int],
) -> None:
    seen_pairs: set[tuple[int, int]] = set()
    for row in rows:
        item_id = item_ids.get(_safe_int_or_none(row.get("item_id")) or -1)
        collection_id = collection_ids.get(
            _safe_int_or_none(row.get("collection_id")) or -1
        )
        if item_id is None or collection_id is None:
            result["skipped"] += 1
            result["item_collections_skipped"] += 1
            result["collection_errors"] += 1
            continue
        pair = (item_id, collection_id)
        if pair in seen_pairs:
            result["skipped"] += 1
            result["item_collections_skipped"] += 1
            continue
        seen_pairs.add(pair)
        if db.get(models.ItemCollection, pair) is None:
            db.add(models.ItemCollection(item_id=item_id, collection_id=collection_id))
            result["created"] += 1
            result["item_collections_created"] += 1
        else:
            result["skipped"] += 1
            result["item_collections_skipped"] += 1


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


def _merge_item_activity(
    db: Session,
    rows: list[dict[str, Any]],
    item_ids: dict[int, int],
    result: dict[str, int],
) -> None:
    seen_item_ids: set[int] = set()
    for row in rows:
        backup_item_id = _safe_int_or_none(row.get("item_id"))
        item_id = item_ids.get(backup_item_id or -1)
        if item_id is None:
            result["skipped"] += 1
            result["item_activity_skipped"] += 1
            result["item_activity_errors"] += 1
            continue
        if item_id in seen_item_ids:
            result["skipped"] += 1
            result["item_activity_skipped"] += 1
            continue
        seen_item_ids.add(item_id)

        activity = db.scalar(
            select(models.ItemActivity).where(models.ItemActivity.item_id == item_id)
        )
        if activity is None:
            activity = models.ItemActivity(item_id=item_id)
            db.add(activity)
            result["created"] += 1
            result["item_activity_created"] += 1
        else:
            result["updated"] += 1
            result["item_activity_updated"] += 1
        _set_activity_fields(activity, row)
        db.flush()


def _merge_app_settings(
    db: Session,
    rows: list[dict[str, Any]],
    result: dict[str, int],
) -> None:
    seen_keys: set[str] = set()
    for row in rows:
        key = str(row.get("key") or "").strip()
        try:
            value = validate_setting_value(key, row.get("value"))
        except AppSettingsError:
            result["skipped"] += 1
            result["app_settings_skipped"] += 1
            result["app_settings_errors"] += 1
            continue
        if key in seen_keys:
            result["skipped"] += 1
            result["app_settings_skipped"] += 1
            continue
        seen_keys.add(key)

        action = upsert_setting_row(db, key, value)
        if action == "created":
            result["created"] += 1
            result["app_settings_created"] += 1
        elif action == "updated":
            result["updated"] += 1
            result["app_settings_updated"] += 1
        else:
            result["skipped"] += 1
            result["app_settings_skipped"] += 1


def _create_item_sources(
    db: Session,
    rows: tuple[_PreparedItemSource, ...],
    item_ids: dict[int, int],
    result: dict[str, int],
) -> None:
    for row in rows:
        target_item_id = item_ids[row.backup_item_id]
        source = models.ItemSource(
            item_id=target_item_id,
            url=row.url,
            normalized_url=row.normalized_url,
            title=row.title,
            provider_key=row.metadata.provider_key,
            external_id=row.metadata.external_id,
            last_checked_at=row.metadata.last_checked_at,
            metadata_hash=row.metadata.metadata_hash,
        )
        if row.created_at is not None:
            source.created_at = row.created_at
        db.add(source)
        result["created"] += 1
        result["item_sources_created"] += 1


_RESTORE_STATE_TABLES = (
    models.Item.__table__,
    models.Tag.__table__,
    models.Creator.__table__,
    models.Collection.__table__,
    models.ItemTag.__table__,
    models.ItemCreator.__table__,
    models.ItemCollection.__table__,
    models.UserItemState.__table__,
    models.SavedView.__table__,
    models.ItemActivity.__table__,
    models.AppSetting.__table__,
    models.ItemSource.__table__,
    models.MediaIndexState.__table__,
)


def _digest_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def _restore_state_digest(db: Session) -> str:
    state: dict[str, list[list[Any]]] = {}
    for table in _RESTORE_STATE_TABLES:
        columns = tuple(table.columns)
        primary_key = tuple(table.primary_key.columns)
        statement = select(*columns)
        if primary_key:
            statement = statement.order_by(*primary_key)
        rows = db.execute(statement).all()
        state[table.name] = [
            [_digest_value(value) for value in row]
            for row in rows
        ]
    encoded = json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _independent_restore_state_digest(db: Session) -> str | None:
    try:
        VerificationSession = sessionmaker(
            bind=db.get_bind(),
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
        with VerificationSession() as verification_db:
            return _restore_state_digest(verification_db)
    except Exception:
        return None


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def restore_backup_data(
    db: Session,
    payload: dict[str, Any],
) -> dict[str, int | str]:
    from app.services.media_index import invalidate_media_index

    input_schema = _backup_schema(payload)
    rows = _rows_from_payload(payload)
    _validate_preview_rows(rows, input_schema)
    prepared_sources = _prepared_item_sources(rows, input_schema)
    payload_errors = _source_payload_errors(prepared_sources)
    if payload_errors:
        _raise("source_payload_conflict", payload_errors[0])
    result: dict[str, int | str] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "collections_created": 0,
        "collections_skipped": 0,
        "item_collections_created": 0,
        "item_collections_skipped": 0,
        "collection_errors": 0,
        "saved_views_created": 0,
        "saved_views_updated": 0,
        "saved_views_skipped": 0,
        "saved_view_errors": 0,
        "item_activity_created": 0,
        "item_activity_updated": 0,
        "item_activity_skipped": 0,
        "item_activity_errors": 0,
        "app_settings_created": 0,
        "app_settings_updated": 0,
        "app_settings_skipped": 0,
        "app_settings_errors": 0,
        "item_sources_created": 0,
        "item_sources_reused": 0,
        "item_sources_conflicts": 0,
        "item_sources_skipped": 0,
        "item_sources_errors": 0,
        "input_schema": input_schema,
        "database_outcome": "not_started",
    }
    db.rollback()
    before_digest = _restore_state_digest(db)
    expected_digest: str | None = None
    original_error: Exception | None = None
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        item_ids = _merge_items(db, rows["items"], result)
        source_plan = _classify_item_sources(db, prepared_sources, item_ids)
        result["item_sources_reused"] = source_plan.reused
        result["item_sources_skipped"] = source_plan.reused
        result["skipped"] = int(result["skipped"]) + source_plan.reused
        result["item_sources_conflicts"] = len(source_plan.conflicts)
        result["item_sources_errors"] = len(source_plan.errors)
        if source_plan.conflicts:
            _raise("source_local_conflict", source_plan.conflicts[0])
        if source_plan.errors:
            _raise("source_payload_conflict", source_plan.errors[0])

        tag_ids = _merge_tags(db, rows["tags"], result)
        creator_ids = _merge_creators(db, rows["creators"], result)
        collection_ids = _merge_collections(db, rows["collections"], result)
        _merge_item_tags(db, rows["item_tags"], item_ids, tag_ids, result)
        _merge_item_creators(
            db,
            rows["item_creators"],
            item_ids,
            creator_ids,
            result,
        )
        _merge_item_collections(
            db,
            rows["item_collections"],
            item_ids,
            collection_ids,
            result,
        )
        _merge_states(db, rows["user_item_states"], item_ids, result)
        _merge_saved_views(db, rows["saved_views"], result)
        _merge_item_activity(db, rows["item_activity"], item_ids, result)
        _merge_app_settings(db, rows["app_settings"], result)
        _create_item_sources(db, source_plan.to_create, item_ids, result)
        invalidate_media_index(db, reason="backup_restored")
        db.flush()
        expected_digest = _restore_state_digest(db)
        db.commit()
        result["database_outcome"] = "committed"
        return result
    except Exception as exc:
        original_error = exc
        _rollback_quietly(db)

    actual_digest = _independent_restore_state_digest(db)
    if expected_digest is not None and actual_digest == expected_digest:
        result["database_outcome"] = "committed_after_error"
        return result
    if actual_digest == before_digest:
        if isinstance(original_error, BackupError):
            raise original_error
        raise BackupError("restore_rolled_back") from original_error
    raise BackupError("restore_outcome_unknown") from original_error
