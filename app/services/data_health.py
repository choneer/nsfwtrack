from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.item_query import STATUS_OPTIONS
from app.services.saved_views import SAVED_VIEW_ALLOWED_PARAMS

CATEGORY_ORDER = ("items", "relations", "duplicates", "saved_views", "activity")
DATA_HEALTH_DETAIL_LIMIT = 200
BLOCKED_SAVED_VIEW_PARAMS = {"page", "next", "redirect"}
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


@dataclass(frozen=True)
class DataHealthIssue:
    category: str
    code: str
    severity: str
    object_type: str
    object_id: str
    detail: str = ""


@dataclass(frozen=True)
class DataHealthCategorySummary:
    category: str
    count: int


@dataclass(frozen=True)
class DataHealthReport:
    status: str
    total_issues: int
    warning_count: int
    problem_count: int
    category_summaries: list[DataHealthCategorySummary]
    issues: list[DataHealthIssue]
    displayed_issue_count: int
    details_truncated: bool
    detail_limit: int
    issue_code_counts: dict[str, int]

    @property
    def has_issues(self) -> bool:
        return self.total_issues > 0


def build_data_health_report(
    db: Session,
    *,
    detail_limit: int = DATA_HEALTH_DETAIL_LIMIT,
) -> DataHealthReport:
    if detail_limit <= 0:
        raise ValueError("detail_limit must be positive")
    issues: list[DataHealthIssue] = []
    issues.extend(_check_items(db))
    issues.extend(_check_relations(db))
    issues.extend(_check_duplicate_relations(db))
    issues.extend(_check_saved_views(db))
    issues.extend(_check_item_activity(db))
    return _build_report(issues, detail_limit=detail_limit)


def _build_report(
    issues: list[DataHealthIssue],
    *,
    detail_limit: int,
) -> DataHealthReport:
    counts = {category: 0 for category in CATEGORY_ORDER}
    issue_code_counts: dict[str, int] = {}
    warning_count = 0
    problem_count = 0
    for issue in issues:
        counts[issue.category] = counts.get(issue.category, 0) + 1
        issue_code_counts[issue.code] = issue_code_counts.get(issue.code, 0) + 1
        if issue.severity == "problem":
            problem_count += 1
        else:
            warning_count += 1

    status = "healthy"
    if problem_count:
        status = "problem"
    elif warning_count:
        status = "warning"

    return DataHealthReport(
        status=status,
        total_issues=len(issues),
        warning_count=warning_count,
        problem_count=problem_count,
        category_summaries=[
            DataHealthCategorySummary(category=category, count=counts.get(category, 0))
            for category in CATEGORY_ORDER
        ],
        issues=issues[:detail_limit],
        displayed_issue_count=min(len(issues), detail_limit),
        details_truncated=len(issues) > detail_limit,
        detail_limit=detail_limit,
        issue_code_counts=issue_code_counts,
    )


def _issue(
    category: str,
    code: str,
    object_type: str,
    object_id: Any,
    *,
    detail: str = "",
    severity: str = "problem",
) -> DataHealthIssue:
    return DataHealthIssue(
        category=category,
        code=code,
        severity=severity,
        object_type=object_type,
        object_id=str(object_id),
        detail=detail,
    )


def _rows(db: Session, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text(sql)).mappings().all()]


def _check_items(db: Session) -> list[DataHealthIssue]:
    issues: list[DataHealthIssue] = []
    for row in _rows(
        db,
        """
        SELECT id, title, created_at, updated_at, extra
        FROM items
        ORDER BY id ASC
        """,
    ):
        item_id = row["id"]
        if _is_blank(row.get("title")):
            issues.append(_issue("items", "empty_title", "item", item_id))

        created_at = _parse_datetime(row.get("created_at"))
        updated_at = _parse_datetime(row.get("updated_at"))
        issues.extend(
            _datetime_issues(
                category="items",
                object_type="item",
                object_id=item_id,
                created_at=created_at,
                updated_at=updated_at,
            )
        )

        extra = row.get("extra")
        if not _is_blank(extra):
            try:
                parsed_extra = json.loads(str(extra))
            except json.JSONDecodeError:
                issues.append(
                    _issue(
                        "items",
                        "invalid_extra_json",
                        "item",
                        item_id,
                        detail=_short_value(extra),
                        severity="warning",
                    )
                )
            else:
                if not isinstance(parsed_extra, dict):
                    issues.append(
                        _issue(
                            "items",
                            "invalid_extra_json_type",
                            "item",
                            item_id,
                            detail=type(parsed_extra).__name__,
                            severity="warning",
                        )
                    )

    for row in _rows(
        db,
        """
        SELECT id, item_id, status, rating
        FROM user_item_states
        ORDER BY id ASC
        """,
    ):
        state_id = row["id"]
        status_value = str(row.get("status") or "").strip()
        if status_value not in STATUS_OPTIONS:
            issues.append(
                _issue(
                    "items",
                    "invalid_status",
                    "user_item_state",
                    state_id,
                    detail=f"item_id={row.get('item_id')} status={_short_value(status_value)}",
                )
            )

        rating_value = row.get("rating")
        if rating_value is not None:
            try:
                rating = int(rating_value)
            except (TypeError, ValueError):
                rating = 0
            if rating < 1 or rating > 5:
                issues.append(
                    _issue(
                        "items",
                        "invalid_rating",
                        "user_item_state",
                        state_id,
                        detail=f"item_id={row.get('item_id')} rating={_short_value(rating_value)}",
                    )
                )

    return issues


def _datetime_issues(
    *,
    category: str,
    object_type: str,
    object_id: Any,
    created_at: tuple[datetime | None, str | None],
    updated_at: tuple[datetime | None, str | None],
) -> list[DataHealthIssue]:
    issues: list[DataHealthIssue] = []
    created_value, created_error = created_at
    updated_value, updated_error = updated_at

    if created_error:
        issues.append(
            _issue(
                category,
                f"{created_error}_created_at",
                object_type,
                object_id,
            )
        )
    if updated_error:
        issues.append(
            _issue(
                category,
                f"{updated_error}_updated_at",
                object_type,
                object_id,
            )
        )
    if (
        created_value is not None
        and updated_value is not None
        and updated_value < created_value
    ):
        issues.append(
            _issue(category, "updated_before_created", object_type, object_id)
        )
    return issues


def _check_relations(db: Session) -> list[DataHealthIssue]:
    relation_checks = (
        (
            "item_tags",
            "tag",
            "tag_id",
            "tags",
            "orphan_item_tag_item",
            "orphan_item_tag_tag",
        ),
        (
            "item_creators",
            "creator",
            "creator_id",
            "creators",
            "orphan_item_creator_item",
            "orphan_item_creator_creator",
        ),
        (
            "item_collections",
            "collection",
            "collection_id",
            "collections",
            "orphan_item_collection_item",
            "orphan_item_collection_collection",
        ),
    )

    issues: list[DataHealthIssue] = []
    for (
        relation_table,
        object_name,
        object_column,
        target_table,
        item_code,
        target_code,
    ) in relation_checks:
        missing_relations_sql = f"""
            SELECT
                relation.item_id,
                relation.{object_column} AS target_id,
                items.id AS existing_item_id,
                target.id AS existing_target_id
            FROM {relation_table} AS relation
            LEFT JOIN items ON items.id = relation.item_id
            LEFT JOIN {target_table} AS target
                ON target.id = relation.{object_column}
            WHERE items.id IS NULL OR target.id IS NULL
            ORDER BY relation.item_id ASC, relation.{object_column} ASC
        """
        for row in _rows(db, missing_relations_sql):
            object_id = _relation_id(row.get("item_id"), row.get("target_id"))
            detail = (
                f"item_id={row.get('item_id')} "
                f"{object_name}_id={row.get('target_id')}"
            )
            if row.get("existing_item_id") is None:
                issues.append(
                    _issue(
                        "relations",
                        item_code,
                        relation_table[:-1],
                        object_id,
                        detail=detail,
                    )
                )
            if row.get("existing_target_id") is None:
                issues.append(
                    _issue(
                        "relations",
                        target_code,
                        relation_table[:-1],
                        object_id,
                        detail=detail,
                    )
                )

    return issues


def _check_duplicate_relations(db: Session) -> list[DataHealthIssue]:
    duplicate_checks = (
        ("item_tags", "tag", "tag_id", "duplicate_item_tag"),
        ("item_creators", "creator", "creator_id", "duplicate_item_creator"),
        ("item_collections", "collection", "collection_id", "duplicate_item_collection"),
    )
    issues: list[DataHealthIssue] = []
    for relation_table, object_name, object_column, code in duplicate_checks:
        duplicate_sql = f"""
            SELECT item_id, {object_column} AS target_id, COUNT(*) AS duplicate_count
            FROM {relation_table}
            GROUP BY item_id, {object_column}
            HAVING COUNT(*) > 1
            ORDER BY item_id ASC, {object_column} ASC
        """
        for row in _rows(db, duplicate_sql):
            issues.append(
                _issue(
                    "duplicates",
                    code,
                    relation_table[:-1],
                    _relation_id(row.get("item_id"), row.get("target_id")),
                    detail=(
                        f"item_id={row.get('item_id')} "
                        f"{object_name}_id={row.get('target_id')} "
                        f"count={row.get('duplicate_count')}"
                    ),
                )
            )
    return issues


def _check_saved_views(db: Session) -> list[DataHealthIssue]:
    issues: list[DataHealthIssue] = []
    for row in _rows(
        db,
        """
        SELECT id, name, query_string
        FROM saved_views
        ORDER BY id ASC
        """,
    ):
        saved_view_id = row["id"]
        if _is_blank(row.get("name")):
            issues.append(
                _issue("saved_views", "saved_view_empty_name", "saved_view", saved_view_id)
            )

        query_string = row.get("query_string")
        if _is_blank(query_string):
            issues.append(
                _issue(
                    "saved_views",
                    "saved_view_empty_query",
                    "saved_view",
                    saved_view_id,
                    severity="warning",
                )
            )
            continue

        issues.extend(_check_saved_view_query(saved_view_id, str(query_string)))
    return issues


def _check_saved_view_query(
    saved_view_id: Any,
    raw_query_string: str,
) -> list[DataHealthIssue]:
    issues: list[DataHealthIssue] = []
    query_string = raw_query_string.strip()
    if _BAD_PERCENT_RE.search(query_string):
        issues.append(
            _issue(
                "saved_views",
                "saved_view_invalid_query",
                "saved_view",
                saved_view_id,
                detail=_short_value(query_string),
                severity="warning",
            )
        )

    parsed_url = urlsplit(query_string)
    if parsed_url.scheme or parsed_url.netloc or query_string.startswith("//"):
        issues.append(
            _issue(
                "saved_views",
                "saved_view_external_url",
                "saved_view",
                saved_view_id,
                detail=_short_value(query_string),
                severity="warning",
            )
        )
        query_to_parse = parsed_url.query
    elif parsed_url.query and parsed_url.path:
        query_to_parse = parsed_url.query
    else:
        query_to_parse = query_string[1:] if query_string.startswith("?") else query_string

    pairs = parse_qsl(query_to_parse, keep_blank_values=True)
    if query_to_parse and not pairs:
        issues.append(
            _issue(
                "saved_views",
                "saved_view_invalid_query",
                "saved_view",
                saved_view_id,
                detail=_short_value(query_string),
                severity="warning",
            )
        )

    for key, value in pairs:
        if key in BLOCKED_SAVED_VIEW_PARAMS:
            issues.append(
                _issue(
                    "saved_views",
                    "saved_view_blocked_param",
                    "saved_view",
                    saved_view_id,
                    detail=key,
                    severity="warning",
                )
            )
        elif key not in SAVED_VIEW_ALLOWED_PARAMS:
            issues.append(
                _issue(
                    "saved_views",
                    "saved_view_unknown_param",
                    "saved_view",
                    saved_view_id,
                    detail=key,
                    severity="warning",
                )
            )
        if _looks_external_url(value):
            issues.append(
                _issue(
                    "saved_views",
                    "saved_view_external_url",
                    "saved_view",
                    saved_view_id,
                    detail=f"{key}={_short_value(value)}",
                    severity="warning",
                )
            )
    return issues


def _check_item_activity(db: Session) -> list[DataHealthIssue]:
    issues: list[DataHealthIssue] = []
    for row in _rows(
        db,
        """
        SELECT
            item_activity.id,
            item_activity.item_id,
            item_activity.last_viewed_at,
            item_activity.view_count,
            item_activity.last_edited_at,
            item_activity.edit_count,
            items.id AS existing_item_id
        FROM item_activity
        LEFT JOIN items ON items.id = item_activity.item_id
        ORDER BY item_activity.id ASC
        """,
    ):
        activity_id = row["id"]
        if row.get("existing_item_id") is None:
            issues.append(
                _issue(
                    "activity",
                    "activity_missing_item",
                    "item_activity",
                    activity_id,
                    detail=f"item_id={row.get('item_id')}",
                )
            )

        for column, code in (
            ("view_count", "activity_negative_view_count"),
            ("edit_count", "activity_negative_edit_count"),
        ):
            value = row.get(column)
            try:
                count = int(value)
            except (TypeError, ValueError):
                count = -1
            if count < 0:
                issues.append(
                    _issue(
                        "activity",
                        code,
                        "item_activity",
                        activity_id,
                        detail=f"{column}={_short_value(value)}",
                    )
                )

        for column, code in (
            ("last_viewed_at", "activity_invalid_last_viewed_at"),
            ("last_edited_at", "activity_invalid_last_edited_at"),
        ):
            value = row.get(column)
            if _is_blank(value):
                continue
            _, error = _parse_datetime(value)
            if error:
                issues.append(
                    _issue(
                        "activity",
                        code,
                        "item_activity",
                        activity_id,
                        detail=f"{column}={_short_value(value)}",
                    )
                )

    return issues


def _parse_datetime(value: Any) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, "missing"
    if isinstance(value, datetime):
        return _drop_timezone(value), None

    raw_value = str(value).strip()
    if not raw_value:
        return None, "missing"
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"
    try:
        return _drop_timezone(datetime.fromisoformat(raw_value)), None
    except ValueError:
        return None, "invalid"


def _drop_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


def _relation_id(item_id: Any, target_id: Any) -> str:
    return f"{item_id}:{target_id}"


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _looks_external_url(value: str) -> bool:
    cleaned = value.strip()
    parsed = urlsplit(cleaned)
    return bool(parsed.scheme or parsed.netloc or cleaned.startswith("//"))


def _short_value(value: Any, *, limit: int = 160) -> str:
    cleaned = str(value)
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."
