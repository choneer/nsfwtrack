from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services.backup import CORE_TABLE_NAMES, OPTIONAL_TABLE_NAMES, TABLE_NAMES
from app.services.exporter import BACKUP_SCHEMA
from app.services.item_query import STATUS_OPTIONS
from app.services.local_media import LocalMediaPathError, normalize_local_media_path
from app.services.saved_views import SAVED_VIEW_ALLOWED_PARAMS
from app.services.settings import AppSettingsError, validate_setting_value
from app.services.sources import SourceError, normalize_source_url

TOP_LEVEL_FIELDS = {"schema", "exported_at", "tables"}
BLOCKED_SAVED_VIEW_PARAMS = {"page", "next", "redirect"}
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")

_TABLE_REQUIRED_FIELDS: dict[str, set[str]] = {
    "items": {"id", "title"},
    "tags": {"id", "name"},
    "creators": {"id", "name"},
    "item_tags": {"item_id", "tag_id"},
    "item_creators": {"item_id", "creator_id"},
    "user_item_states": {"item_id", "status"},
    "collections": {"id", "name"},
    "item_collections": {"item_id", "collection_id"},
    "saved_views": {"id", "name", "query_string"},
    "item_activity": {"item_id"},
    "app_settings": {"key", "value"},
    "item_sources": {"item_id", "url", "normalized_url"},
}

_TABLE_KNOWN_FIELDS: dict[str, set[str]] = {
    "items": {
        "id",
        "title",
        "cover_path",
        "summary",
        "release_date",
        "extra",
        "created_at",
        "updated_at",
    },
    "tags": {"id", "name", "category", "created_at"},
    "creators": {"id", "name", "type", "avatar_path", "created_at"},
    "item_tags": {"item_id", "tag_id"},
    "item_creators": {"item_id", "creator_id"},
    "user_item_states": {
        "id",
        "item_id",
        "status",
        "rating",
        "review",
        "created_at",
        "updated_at",
    },
    "collections": {"id", "name", "description", "created_at", "updated_at"},
    "item_collections": {"item_id", "collection_id", "created_at"},
    "saved_views": {"id", "name", "query_string", "created_at", "updated_at"},
    "item_activity": {
        "id",
        "item_id",
        "last_viewed_at",
        "view_count",
        "last_edited_at",
        "edit_count",
        "created_at",
        "updated_at",
    },
    "app_settings": {"id", "key", "value", "created_at", "updated_at"},
    "item_sources": {
        "id",
        "item_id",
        "url",
        "normalized_url",
        "title",
        "created_at",
    },
}


@dataclass(frozen=True)
class BackupValidationIssue:
    severity: str
    code: str
    data_type: str
    row: int | None = None
    object_id: str = ""
    detail: str = ""


@dataclass(frozen=True)
class BackupValidationReport:
    status: str
    error_count: int
    warning_count: int
    info_count: int
    table_counts: dict[str, int]
    relation_count: int
    skipped_count: int
    issues: list[BackupValidationIssue]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [asdict(issue) for issue in self.issues]
        return payload


def validate_backup_payload(
    payload: dict[str, Any],
    db: Session | None = None,
) -> BackupValidationReport:
    issues: list[BackupValidationIssue] = []
    rows = _collect_rows(payload, issues)
    if rows:
        issues.extend(_validate_rows(rows))
        issues.extend(_validate_relations(rows))
        issues.extend(_validate_saved_views(rows))
        issues.extend(_validate_item_activity(rows))
        issues.extend(_restore_dry_run_infos(rows, db))
    return _build_report(rows, issues)


def _build_report(
    rows: dict[str, list[dict[str, Any]]] | None,
    issues: list[BackupValidationIssue],
) -> BackupValidationReport:
    table_counts = {table_name: 0 for table_name in sorted(TABLE_NAMES)}
    if rows is not None:
        for table_name in table_counts:
            table_counts[table_name] = len(rows.get(table_name, []))

    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    info_count = sum(1 for issue in issues if issue.severity == "info")
    status = "ready"
    if error_count:
        status = "blocked"
    elif warning_count:
        status = "warning"

    relation_count = sum(
        table_counts.get(table_name, 0)
        for table_name in (
            "item_tags",
            "item_creators",
            "item_collections",
            "item_sources",
        )
    )
    skipped_count = sum(
        1
        for issue in issues
        if issue.severity == "error" and (issue.row is not None or issue.object_id)
    )
    return BackupValidationReport(
        status=status,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        table_counts=table_counts,
        relation_count=relation_count,
        skipped_count=skipped_count,
        issues=issues,
    )


def _collect_rows(
    payload: dict[str, Any],
    issues: list[BackupValidationIssue],
) -> dict[str, list[dict[str, Any]]] | None:
    for key in sorted(set(payload) - TOP_LEVEL_FIELDS):
        issues.append(_issue("warning", "unknown_top_level_field", "backup", detail=key))

    if payload.get("schema") != BACKUP_SCHEMA:
        issues.append(
            _issue(
                "error",
                "schema_mismatch",
                "backup",
                detail=str(payload.get("schema", "")),
            )
        )

    tables = payload.get("tables")
    if not isinstance(tables, dict):
        issues.append(_issue("error", "missing_tables", "backup"))
        return None

    for table_name in sorted(set(tables) - TABLE_NAMES):
        issues.append(
            _issue("warning", "unknown_table", table_name, detail=table_name)
        )

    rows: dict[str, list[dict[str, Any]]] = {}
    for table_name in sorted(TABLE_NAMES):
        table_rows = tables.get(table_name)
        if table_rows is None:
            if table_name in CORE_TABLE_NAMES:
                issues.append(_issue("error", "missing_table", table_name))
                rows[table_name] = []
            else:
                issues.append(_issue("info", "optional_table_missing", table_name))
                rows[table_name] = []
            continue
        if not isinstance(table_rows, list):
            issues.append(_issue("error", "invalid_table", table_name))
            rows[table_name] = []
            continue

        cleaned_rows: list[dict[str, Any]] = []
        for index, row in enumerate(table_rows, start=1):
            if not isinstance(row, dict):
                issues.append(_issue("error", "invalid_row", table_name, row=index))
                continue
            cleaned_rows.append(row)
        rows[table_name] = cleaned_rows
    return rows


def _validate_rows(rows: dict[str, list[dict[str, Any]]]) -> list[BackupValidationIssue]:
    issues: list[BackupValidationIssue] = []
    for table_name, table_rows in rows.items():
        required_fields = _TABLE_REQUIRED_FIELDS.get(table_name, set())
        known_fields = _TABLE_KNOWN_FIELDS.get(table_name, set())
        seen_ids: set[int] = set()
        for index, row in enumerate(table_rows, start=1):
            for field in sorted(set(row) - known_fields):
                issues.append(
                    _issue(
                        "warning",
                        "unknown_field",
                        table_name,
                        row=index,
                        object_id=_row_id(row),
                        detail=field,
                    )
                )
            for field in sorted(required_fields):
                if _is_blank(row.get(field)):
                    issues.append(
                        _issue(
                            "error",
                            "missing_field",
                            table_name,
                            row=index,
                            object_id=_row_id(row),
                            detail=field,
                        )
                    )
            row_id = _safe_int(row.get("id"))
            if row_id is not None:
                if row_id in seen_ids:
                    issues.append(
                        _issue(
                            "warning",
                            "duplicate_id",
                            table_name,
                            row=index,
                            object_id=str(row_id),
                        )
                    )
                seen_ids.add(row_id)
            issues.extend(_validate_table_values(table_name, row, index))
    return issues


def _validate_table_values(
    table_name: str,
    row: dict[str, Any],
    index: int,
) -> list[BackupValidationIssue]:
    issues: list[BackupValidationIssue] = []
    object_id = _row_id(row)
    if table_name == "items":
        title = str(row.get("title") or "").strip()
        if not title:
            issues.append(_issue("error", "empty_title", table_name, index, object_id))
        extra = row.get("extra")
        if not _is_blank(extra):
            try:
                parsed_extra = json.loads(str(extra))
            except json.JSONDecodeError:
                issues.append(
                    _issue("warning", "invalid_extra_json", table_name, index, object_id)
                )
            else:
                if not isinstance(parsed_extra, dict):
                    issues.append(
                        _issue(
                            "warning",
                            "invalid_extra_json",
                            table_name,
                            index,
                            object_id,
                            detail=type(parsed_extra).__name__,
                        )
                    )
        try:
            normalize_local_media_path(row.get("cover_path"))
        except LocalMediaPathError:
            issues.append(
                _issue(
                    "error",
                    "invalid_local_media_path",
                    table_name,
                    index,
                    object_id,
                    detail="cover_path",
                )
            )
    elif table_name in {"tags", "creators", "collections"}:
        if _is_blank(row.get("name")):
            issues.append(_issue("error", "empty_name", table_name, index, object_id))
        if table_name == "creators":
            try:
                normalize_local_media_path(row.get("avatar_path"))
            except LocalMediaPathError:
                issues.append(
                    _issue(
                        "error",
                        "invalid_local_media_path",
                        table_name,
                        index,
                        object_id,
                        detail="avatar_path",
                    )
                )
    elif table_name == "user_item_states":
        status = str(row.get("status") or "").strip()
        if status and status not in STATUS_OPTIONS:
            issues.append(
                _issue(
                    "error",
                    "invalid_status",
                    table_name,
                    index,
                    object_id,
                    detail=status,
                )
            )
        rating = row.get("rating")
        if not _is_blank(rating):
            parsed_rating = _safe_int(rating)
            if parsed_rating is None or parsed_rating < 1 or parsed_rating > 5:
                issues.append(
                    _issue(
                        "error",
                        "invalid_rating",
                        table_name,
                        index,
                        object_id,
                        detail=str(rating),
                    )
                )
    elif table_name == "app_settings":
        key = str(row.get("key") or "").strip()
        try:
            validate_setting_value(key, row.get("value"))
        except AppSettingsError:
            issues.append(
                _issue(
                    "error",
                    "invalid_setting",
                    table_name,
                    index,
                    object_id,
                    detail=key,
                )
            )
    elif table_name == "item_sources":
        try:
            normalized = normalize_source_url(row.get("url"))
        except SourceError:
            issues.append(
                _issue(
                    "error",
                    "invalid_source_url",
                    table_name,
                    index,
                    object_id,
                )
            )
        else:
            if normalized != str(row.get("normalized_url") or ""):
                issues.append(
                    _issue(
                        "error",
                        "source_normalization_mismatch",
                        table_name,
                        index,
                        object_id,
                    )
                )
    return issues


def _validate_relations(rows: dict[str, list[dict[str, Any]]]) -> list[BackupValidationIssue]:
    item_ids = _id_set(rows["items"])
    tag_ids = _id_set(rows["tags"])
    creator_ids = _id_set(rows["creators"])
    collection_ids = _id_set(rows["collections"])
    relation_specs = (
        ("item_tags", "tag_id", tag_ids, "orphan_item_tag"),
        ("item_creators", "creator_id", creator_ids, "orphan_item_creator"),
        ("item_collections", "collection_id", collection_ids, "orphan_item_collection"),
    )

    issues: list[BackupValidationIssue] = []
    for table_name, target_key, target_ids, orphan_code in relation_specs:
        seen_pairs: set[tuple[int, int]] = set()
        for index, row in enumerate(rows[table_name], start=1):
            item_id = _safe_int(row.get("item_id"))
            target_id = _safe_int(row.get(target_key))
            object_id = _relation_id(item_id, target_id)
            if item_id is None or item_id not in item_ids:
                issues.append(
                    _issue(
                        "error",
                        f"{orphan_code}_item",
                        table_name,
                        index,
                        object_id,
                        detail=f"item_id={row.get('item_id')}",
                    )
                )
            if target_id is None or target_id not in target_ids:
                issues.append(
                    _issue(
                        "error",
                        f"{orphan_code}_target",
                        table_name,
                        index,
                        object_id,
                        detail=f"{target_key}={row.get(target_key)}",
                    )
                )
            if item_id is None or target_id is None:
                continue
            pair = (item_id, target_id)
            if pair in seen_pairs:
                issues.append(
                    _issue(
                        "warning",
                        "duplicate_relation",
                        table_name,
                        index,
                        object_id,
                    )
                )
            seen_pairs.add(pair)
    seen_source_urls: set[str] = set()
    for index, row in enumerate(rows["item_sources"], start=1):
        item_id = _safe_int(row.get("item_id"))
        normalized = str(row.get("normalized_url") or "")
        object_id = _row_id(row)
        if item_id is None or item_id not in item_ids:
            issues.append(
                _issue(
                    "error",
                    "orphan_item_source",
                    "item_sources",
                    index,
                    object_id,
                    detail=f"item_id={row.get('item_id')}",
                )
            )
        if normalized in seen_source_urls:
            issues.append(
                _issue(
                    "warning",
                    "duplicate_source_url",
                    "item_sources",
                    index,
                    object_id,
                )
            )
        elif normalized:
            seen_source_urls.add(normalized)
    return issues


def _validate_saved_views(
    rows: dict[str, list[dict[str, Any]]],
) -> list[BackupValidationIssue]:
    issues: list[BackupValidationIssue] = []
    for index, row in enumerate(rows["saved_views"], start=1):
        query_string = row.get("query_string")
        if _is_blank(query_string):
            issues.append(
                _issue(
                    "warning",
                    "saved_view_empty_query",
                    "saved_views",
                    index,
                    _row_id(row),
                )
            )
            continue
        issues.extend(_saved_view_query_issues(str(query_string), row, index))
    return issues


def _saved_view_query_issues(
    query_string: str,
    row: dict[str, Any],
    index: int,
) -> list[BackupValidationIssue]:
    issues: list[BackupValidationIssue] = []
    object_id = _row_id(row)
    query = query_string.strip()
    if _BAD_PERCENT_RE.search(query):
        issues.append(
            _issue("warning", "saved_view_invalid_query", "saved_views", index, object_id)
        )

    parsed = urlsplit(query)
    if parsed.scheme or parsed.netloc or query.startswith("//"):
        issues.append(
            _issue(
                "warning",
                "saved_view_external_url",
                "saved_views",
                index,
                object_id,
            )
        )
        query_to_parse = parsed.query
    elif parsed.query and parsed.path:
        query_to_parse = parsed.query
    else:
        query_to_parse = query[1:] if query.startswith("?") else query

    for key, value in parse_qsl(query_to_parse, keep_blank_values=True):
        if key in BLOCKED_SAVED_VIEW_PARAMS:
            issues.append(
                _issue(
                    "warning",
                    "saved_view_blocked_param",
                    "saved_views",
                    index,
                    object_id,
                    detail=key,
                )
            )
        elif key not in SAVED_VIEW_ALLOWED_PARAMS:
            issues.append(
                _issue(
                    "warning",
                    "saved_view_unknown_param",
                    "saved_views",
                    index,
                    object_id,
                    detail=key,
                )
            )
        if _looks_external_url(value):
            issues.append(
                _issue(
                    "warning",
                    "saved_view_external_url",
                    "saved_views",
                    index,
                    object_id,
                    detail=f"{key}={value}",
                )
            )
    return issues


def _validate_item_activity(
    rows: dict[str, list[dict[str, Any]]],
) -> list[BackupValidationIssue]:
    item_ids = _id_set(rows["items"])
    seen_item_ids: set[int] = set()
    issues: list[BackupValidationIssue] = []
    for index, row in enumerate(rows["item_activity"], start=1):
        item_id = _safe_int(row.get("item_id"))
        object_id = _row_id(row) or str(row.get("item_id") or "")
        if item_id is None or item_id not in item_ids:
            issues.append(
                _issue(
                    "error",
                    "item_activity_missing_item",
                    "item_activity",
                    index,
                    object_id,
                    detail=f"item_id={row.get('item_id')}",
                )
            )
        elif item_id in seen_item_ids:
            issues.append(
                _issue(
                    "warning",
                    "duplicate_item_activity",
                    "item_activity",
                    index,
                    object_id,
                )
            )
        if item_id is not None:
            seen_item_ids.add(item_id)

        for field, code in (
            ("view_count", "negative_view_count"),
            ("edit_count", "negative_edit_count"),
        ):
            value = row.get(field)
            if _is_blank(value):
                continue
            parsed = _safe_int(value)
            if parsed is None or parsed < 0:
                issues.append(
                    _issue(
                        "error",
                        code,
                        "item_activity",
                        index,
                        object_id,
                        detail=f"{field}={value}",
                    )
                )
    return issues


def _restore_dry_run_infos(
    rows: dict[str, list[dict[str, Any]]],
    db: Session | None,
) -> list[BackupValidationIssue]:
    issues = [
        _issue("info", "dry_run_no_write", "backup"),
        _issue("info", "backup_recommended", "backup"),
        _issue(
            "info",
            "restore_read_items",
            "items",
            detail=str(len(rows["items"])),
        ),
        _issue(
            "info",
            "restore_read_relations",
            "relations",
            detail=str(
                len(rows["item_tags"])
                + len(rows["item_creators"])
                + len(rows["item_collections"])
                + len(rows["item_sources"])
            ),
        ),
    ]
    if db is not None:
        existing_counts = {
            "items": db.scalar(select(models.Item.id).limit(1)) is not None,
            "tags": db.scalar(select(models.Tag.id).limit(1)) is not None,
            "creators": db.scalar(select(models.Creator.id).limit(1)) is not None,
            "collections": db.scalar(select(models.Collection.id).limit(1)) is not None,
            "saved_views": db.scalar(select(models.SavedView.id).limit(1)) is not None,
            "item_activity": db.scalar(select(models.ItemActivity.id).limit(1))
            is not None,
            "app_settings": db.scalar(select(models.AppSetting.id).limit(1))
            is not None,
            "item_sources": db.scalar(select(models.ItemSource.id).limit(1))
            is not None,
        }
        touched = ", ".join(
            table_name for table_name, has_rows in existing_counts.items() if has_rows
        )
        if touched:
            issues.append(
                _issue("info", "restore_may_merge_existing", "backup", detail=touched)
            )
    return issues


def _issue(
    severity: str,
    code: str,
    data_type: str,
    row: int | None = None,
    object_id: str = "",
    detail: str = "",
) -> BackupValidationIssue:
    return BackupValidationIssue(
        severity=severity,
        code=code,
        data_type=data_type,
        row=row,
        object_id=object_id,
        detail=_short_value(detail),
    )


def _id_set(rows: list[dict[str, Any]]) -> set[int]:
    return {
        parsed
        for parsed in (_safe_int(row.get("id")) for row in rows)
        if parsed is not None
    }


def _row_id(row: dict[str, Any]) -> str:
    value = row.get("id")
    if value is None:
        return ""
    return str(value)


def _relation_id(item_id: int | None, target_id: int | None) -> str:
    left = "" if item_id is None else str(item_id)
    right = "" if target_id is None else str(target_id)
    return f"{left}:{right}"


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _looks_external_url(value: str) -> bool:
    cleaned = value.strip()
    parsed = urlsplit(cleaned)
    return bool(parsed.scheme or parsed.netloc or cleaned.startswith("//"))


def _short_value(value: str, limit: int = 160) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}..."
