from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.data_health import (
    BLOCKED_SAVED_VIEW_PARAMS,
    DataHealthReport,
)
from app.services.saved_views import (
    SAVED_VIEW_ALLOWED_PARAMS,
    normalize_saved_view_query_string,
)


@dataclass(frozen=True)
class DataHealthFixOption:
    fix_type: str
    issue_count: int


@dataclass(frozen=True)
class DataHealthFixResult:
    fix_type: str
    deleted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0


class DataHealthFixError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


FIX_ISSUE_CODES: dict[str, tuple[str, ...]] = {
    "orphan_item_tags": ("orphan_item_tag_item", "orphan_item_tag_tag"),
    "orphan_item_creators": (
        "orphan_item_creator_item",
        "orphan_item_creator_creator",
    ),
    "orphan_item_collections": (
        "orphan_item_collection_item",
        "orphan_item_collection_collection",
    ),
    "duplicate_item_tags": ("duplicate_item_tag",),
    "duplicate_item_creators": ("duplicate_item_creator",),
    "duplicate_item_collections": ("duplicate_item_collection",),
    "orphan_item_activity": ("activity_missing_item",),
    "negative_activity_counts": (
        "activity_negative_view_count",
        "activity_negative_edit_count",
    ),
    "saved_view_blocked_params": (
        "saved_view_unknown_param",
        "saved_view_blocked_param",
        "saved_view_external_url",
    ),
}

ALLOWED_FIX_TYPES = tuple(FIX_ISSUE_CODES)

_FixHandler = Callable[[Session], DataHealthFixResult]


def build_data_health_fix_options(
    report: DataHealthReport,
) -> list[DataHealthFixOption]:
    issue_counts = {
        fix_type: sum(report.issue_code_counts.get(code, 0) for code in issue_codes)
        for fix_type, issue_codes in FIX_ISSUE_CODES.items()
    }

    return [
        DataHealthFixOption(fix_type=fix_type, issue_count=issue_counts[fix_type])
        for fix_type in ALLOWED_FIX_TYPES
        if issue_counts.get(fix_type, 0) > 0
    ]


def apply_data_health_fix(
    db: Session,
    *,
    fix_type: str,
    confirm: bool,
) -> DataHealthFixResult:
    handler = _FIX_HANDLERS.get(fix_type)
    if handler is None:
        raise DataHealthFixError("invalid_fix_type")
    if not confirm:
        raise DataHealthFixError("confirm_required")

    try:
        result = handler(db)
        db.commit()
        return result
    except DataHealthFixError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise DataHealthFixError("fix_failed") from exc


def _delete_orphan_relation(
    db: Session,
    *,
    fix_type: str,
    relation_table: str,
    target_table: str,
    target_column: str,
) -> DataHealthFixResult:
    deleted_count = _write_count(
        db,
        f"""
        DELETE FROM {relation_table}
        WHERE NOT EXISTS (
            SELECT 1 FROM items WHERE items.id = {relation_table}.item_id
        )
        OR NOT EXISTS (
            SELECT 1
            FROM {target_table}
            WHERE {target_table}.id = {relation_table}.{target_column}
        )
        """,
    )
    return DataHealthFixResult(fix_type=fix_type, deleted_count=deleted_count)


def _delete_duplicate_relation(
    db: Session,
    *,
    fix_type: str,
    relation_table: str,
    target_column: str,
) -> DataHealthFixResult:
    deleted_count = _write_count(
        db,
        f"""
        DELETE FROM {relation_table}
        WHERE rowid NOT IN (
            SELECT MIN(rowid)
            FROM {relation_table}
            GROUP BY item_id, {target_column}
        )
        """,
    )
    return DataHealthFixResult(fix_type=fix_type, deleted_count=deleted_count)


def _delete_orphan_item_activity(db: Session) -> DataHealthFixResult:
    deleted_count = _write_count(
        db,
        """
        DELETE FROM item_activity
        WHERE NOT EXISTS (
            SELECT 1 FROM items WHERE items.id = item_activity.item_id
        )
        """,
    )
    return DataHealthFixResult(
        fix_type="orphan_item_activity",
        deleted_count=deleted_count,
    )


def _reset_negative_activity_counts(db: Session) -> DataHealthFixResult:
    updated_count = _write_count(
        db,
        """
        UPDATE item_activity
        SET
            view_count = CASE WHEN view_count < 0 THEN 0 ELSE view_count END,
            edit_count = CASE WHEN edit_count < 0 THEN 0 ELSE edit_count END
        WHERE view_count < 0 OR edit_count < 0
        """,
    )
    return DataHealthFixResult(
        fix_type="negative_activity_counts",
        updated_count=updated_count,
    )


def _clean_saved_view_blocked_params(db: Session) -> DataHealthFixResult:
    updated_count = 0
    skipped_count = 0
    rows = db.execute(
        text(
            """
            SELECT id, query_string
            FROM saved_views
            ORDER BY id ASC
            """
        )
    ).mappings()

    for row in rows:
        cleaned_query_string, should_fix = _clean_saved_view_query_string(
            row.get("query_string")
        )
        if not should_fix:
            continue
        current_query_string = str(row.get("query_string") or "").strip()
        if cleaned_query_string == current_query_string:
            skipped_count += 1
            continue
        updated_count += _write_count(
            db,
            """
            UPDATE saved_views
            SET query_string = :query_string
            WHERE id = :id
            """,
            {"query_string": cleaned_query_string, "id": row["id"]},
        )

    return DataHealthFixResult(
        fix_type="saved_view_blocked_params",
        updated_count=updated_count,
        skipped_count=skipped_count,
    )


def _clean_saved_view_query_string(value: Any) -> tuple[str, bool]:
    raw_query_string = str(value or "").strip()
    if not raw_query_string:
        return "", False

    parsed_url = urlsplit(raw_query_string)
    has_external_source = bool(
        parsed_url.scheme or parsed_url.netloc or raw_query_string.startswith("//")
    )
    if has_external_source:
        query_to_parse = parsed_url.query
    elif parsed_url.query and parsed_url.path:
        query_to_parse = parsed_url.query
    else:
        query_to_parse = (
            raw_query_string[1:]
            if raw_query_string.startswith("?")
            else raw_query_string
        )

    pairs = parse_qsl(query_to_parse, keep_blank_values=True)
    if query_to_parse and not pairs:
        return raw_query_string, False

    should_fix = has_external_source
    cleaned_values: dict[str, str] = {}
    for key, raw_value in pairs:
        value = str(raw_value)
        if key in BLOCKED_SAVED_VIEW_PARAMS or key not in SAVED_VIEW_ALLOWED_PARAMS:
            should_fix = True
            continue
        if _looks_external_url(value):
            should_fix = True
            continue
        cleaned_values[str(key)] = value

    if not should_fix:
        return raw_query_string, False
    return normalize_saved_view_query_string(cleaned_values), True


def _looks_external_url(value: str) -> bool:
    cleaned = value.strip()
    parsed = urlsplit(cleaned)
    return bool(parsed.scheme or parsed.netloc or cleaned.startswith("//"))


def _write_count(
    db: Session,
    sql: str,
    params: dict[str, Any] | None = None,
) -> int:
    result = db.execute(text(sql), params or {})
    rowcount = result.rowcount
    if rowcount is None or rowcount < 0:
        return 0
    return rowcount


_FIX_HANDLERS: dict[str, _FixHandler] = {
    "orphan_item_tags": lambda db: _delete_orphan_relation(
        db,
        fix_type="orphan_item_tags",
        relation_table="item_tags",
        target_table="tags",
        target_column="tag_id",
    ),
    "orphan_item_creators": lambda db: _delete_orphan_relation(
        db,
        fix_type="orphan_item_creators",
        relation_table="item_creators",
        target_table="creators",
        target_column="creator_id",
    ),
    "orphan_item_collections": lambda db: _delete_orphan_relation(
        db,
        fix_type="orphan_item_collections",
        relation_table="item_collections",
        target_table="collections",
        target_column="collection_id",
    ),
    "duplicate_item_tags": lambda db: _delete_duplicate_relation(
        db,
        fix_type="duplicate_item_tags",
        relation_table="item_tags",
        target_column="tag_id",
    ),
    "duplicate_item_creators": lambda db: _delete_duplicate_relation(
        db,
        fix_type="duplicate_item_creators",
        relation_table="item_creators",
        target_column="creator_id",
    ),
    "duplicate_item_collections": lambda db: _delete_duplicate_relation(
        db,
        fix_type="duplicate_item_collections",
        relation_table="item_collections",
        target_column="collection_id",
    ),
    "orphan_item_activity": _delete_orphan_item_activity,
    "negative_activity_counts": _reset_negative_activity_counts,
    "saved_view_blocked_params": _clean_saved_view_blocked_params,
}
