from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from time import perf_counter
from typing import Any

from sqlalchemy import Engine, event, func, insert, select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.database import Base
from app.services.activity import (
    ACTIVITY_PAGE_LIMIT,
    count_item_activity,
    list_recently_edited,
    list_recently_viewed,
)
from app.services.backup import preview_backup_data
from app.services.backup_validator import validate_backup_payload
from app.services.collections import (
    get_collection,
    list_available_items_for_collection,
    list_collection_rows,
)
from app.services.danger import get_danger_policy
from app.services.data_health import build_data_health_report
from app.services.duplicates import find_duplicate_candidates
from app.services.exporter import export_backup_data
from app.services.importer import preview_json_import
from app.services.item_query import list_item_filter_options, query_items
from app.services.metadata_cleanup import find_metadata_cleanup_candidates
from app.services.saved_views import list_saved_views
from app.services.settings import get_app_settings, get_default_language
from app.services.stats import build_stats_dashboard

_SPACE_RE = re.compile(r"\s+")
_WRITE_PREFIXES = ("ALTER", "CREATE", "DELETE", "DROP", "INSERT", "REPLACE", "UPDATE")
_STATUS_VALUES = ("wish", "watching", "watched", "like", "dislike", "ignore")


class PerformanceAuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class QueryPlanSummary:
    statement: str
    executions: int
    details: tuple[str, ...]
    full_scan_details: tuple[str, ...]


@dataclass(frozen=True)
class AuditResult:
    operation: str
    dataset_size: int
    duration_ms: float
    query_count: int
    unique_query_count: int
    repeated_query_count: int
    full_scan_count: int
    n_plus_one_detected: bool
    bounded: bool
    risk: str
    metrics: dict[str, int | str | bool]
    plans: tuple[QueryPlanSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditArtifacts:
    backup_payload: dict[str, Any]
    import_content: bytes


@dataclass(frozen=True)
class AuditOperation:
    name: str
    bounded: bool
    run: Callable[[Session, AuditArtifacts], dict[str, int | str | bool]]


@dataclass(frozen=True)
class _CapturedQuery:
    statement: str
    parameters: Any


class _QueryRecorder:
    def __init__(self) -> None:
        self.queries: list[_CapturedQuery] = []

    def before_cursor_execute(
        self,
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        del connection, cursor, context, executemany
        normalized = statement.lstrip().upper()
        if normalized.startswith(_WRITE_PREFIXES):
            raise PerformanceAuditError("write statement blocked during read-only audit")
        if normalized.startswith(("SELECT", "WITH")):
            self.queries.append(_CapturedQuery(statement=statement, parameters=parameters))


def _fingerprint(statement: str) -> str:
    return _SPACE_RE.sub(" ", statement.strip())


def _is_full_scan(detail: str) -> bool:
    upper = detail.upper()
    return (
        "SCAN " in upper
        and "USING INDEX" not in upper
        and "USING COVERING INDEX" not in upper
        and "SCAN CONSTANT ROW" not in upper
        and "SCAN SUBQUERY" not in upper
    )


def _explain_queries(
    connection: Any,
    queries: list[_CapturedQuery],
) -> tuple[QueryPlanSummary, ...]:
    grouped: dict[str, list[_CapturedQuery]] = {}
    for query in queries:
        grouped.setdefault(_fingerprint(query.statement), []).append(query)

    plans: list[QueryPlanSummary] = []
    raw_connection = connection.connection.driver_connection
    for fingerprint, occurrences in grouped.items():
        query = occurrences[0]
        details: list[str] = []
        cursor = raw_connection.cursor()
        try:
            cursor.execute(f"EXPLAIN QUERY PLAN {query.statement}", query.parameters)
            details = [str(row[3]) for row in cursor.fetchall()]
        except Exception as exc:
            details = [f"EXPLAIN unavailable: {type(exc).__name__}"]
        finally:
            cursor.close()
        full_scans = tuple(detail for detail in details if _is_full_scan(detail))
        plans.append(
            QueryPlanSummary(
                statement=fingerprint,
                executions=len(occurrences),
                details=tuple(details),
                full_scan_details=full_scans,
            )
        )
    return tuple(plans)


def run_read_only_operation(
    engine: Engine,
    operation: AuditOperation,
    artifacts: AuditArtifacts,
    *,
    dataset_size: int,
) -> AuditResult:
    recorder = _QueryRecorder()
    with engine.connect() as connection:
        if connection.dialect.name != "sqlite":
            raise PerformanceAuditError("performance audit currently supports SQLite only")
        connection.exec_driver_sql("PRAGMA query_only = ON")
        try:
            event.listen(connection, "before_cursor_execute", recorder.before_cursor_execute)
            session = Session(bind=connection, autoflush=False, expire_on_commit=False)
            started = perf_counter()
            try:
                metrics = operation.run(session, artifacts)
                duration_ms = (perf_counter() - started) * 1000
                session.rollback()
            finally:
                session.close()
                event.remove(connection, "before_cursor_execute", recorder.before_cursor_execute)
            plans = _explain_queries(connection, recorder.queries)
        finally:
            connection.exec_driver_sql("PRAGMA query_only = OFF")

    unique_query_count = len(plans)
    query_count = len(recorder.queries)
    repeated_query_count = query_count - unique_query_count
    full_scan_count = sum(len(plan.full_scan_details) for plan in plans)
    compared_row_counts = {
        int(metrics[key])
        for key in ("result_rows", "collection_items", "candidate_items", "candidate_objects")
        if key in metrics and isinstance(metrics[key], int) and int(metrics[key]) >= 5
    }
    n_plus_one_detected = any(
        plan.executions in compared_row_counts
        and plan.executions >= 5
        and (" = ?" in plan.statement or "? = " in plan.statement)
        for plan in plans
    )
    if n_plus_one_detected or (not operation.bounded and full_scan_count):
        risk = "high"
    elif full_scan_count or repeated_query_count:
        risk = "medium"
    else:
        risk = "low"
    return AuditResult(
        operation=operation.name,
        dataset_size=dataset_size,
        duration_ms=round(duration_ms, 3),
        query_count=query_count,
        unique_query_count=unique_query_count,
        repeated_query_count=repeated_query_count,
        full_scan_count=full_scan_count,
        n_plus_one_detected=n_plus_one_detected,
        bounded=operation.bounded,
        risk=risk,
        metrics=metrics,
        plans=plans,
    )


def _base_context_reads(db: Session) -> None:
    get_default_language(db)
    get_danger_policy(db)


def _touch_items(items: Iterable[models.Item]) -> int:
    touched = 0
    for item in items:
        touched += len(item.tags) + len(item.creators) + len(item.collections)
        touched += 1 if item.state is not None else 0
    return touched


def _items_page(
    db: Session,
    artifacts: AuditArtifacts,
    *,
    filtered: bool,
) -> dict[str, int | str | bool]:
    del artifacts
    settings = get_app_settings(db)
    kwargs: dict[str, str] = {
        "sort": settings.item_list_sort,
        "page_size": str(settings.default_page_size),
    }
    if filtered:
        kwargs.update(
            {
                "q": "Item",
                "state": "watched",
                "min_rating": "3",
                "sort": "rating_desc",
                "page": "2",
                "page_size": "50",
            }
        )
    result = query_items(db, **kwargs)
    options = list_item_filter_options(db)
    views = list_saved_views(db)
    _base_context_reads(db)
    return {
        "result_rows": len(result.items),
        "total_matches": result.total,
        "page_size": result.filters.page_size,
        "metadata_options": len(options.tags) + len(options.creators) + len(options.collections),
        "saved_views_loaded": len(views),
        "relations_touched": _touch_items(result.items),
    }


def _default_items_page(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    return _items_page(db, artifacts, filtered=False)


def _filtered_items_page(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    return _items_page(db, artifacts, filtered=True)


def _workbench(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    del artifacts
    get_app_settings(db)
    recent_items = list(
        db.scalars(
            select(models.Item)
            .options(
                selectinload(models.Item.tags),
                selectinload(models.Item.creators),
                selectinload(models.Item.state),
            )
            .order_by(models.Item.created_at.desc(), models.Item.id.desc())
            .limit(8)
        ).all()
    )
    totals = (
        int(db.scalar(select(func.count(models.Item.id))) or 0)
        + int(db.scalar(select(func.count(models.Tag.id))) or 0)
        + int(db.scalar(select(func.count(models.Creator.id))) or 0)
    )
    recent_viewed = list_recently_viewed(db, limit=4)
    recent_edited = list_recently_edited(db, limit=4)
    views = list_saved_views(db)
    _base_context_reads(db)
    activity_items = [row.item for row in [*recent_viewed, *recent_edited]]
    return {
        "recent_items": len(recent_items),
        "activity_rows": len(activity_items),
        "saved_views_loaded": len(views),
        "total_entities": totals,
        "relations_touched": _touch_items([*recent_items, *activity_items]),
    }


def _stats(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    del artifacts
    dashboard = build_stats_dashboard(db)
    _base_context_reads(db)
    return {
        "total_items": int(dashboard["overview"]["total_items"]),
        "ranking_rows": sum(
            len(dashboard[key]["rows"])
            for key in ("tag_ranking", "creator_ranking", "collection_ranking")
        ),
        "daily_rows": len(dashboard["activity"]["daily"]),
    }


def _tags(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    del artifacts
    rows = list(db.scalars(select(models.Tag).order_by(models.Tag.name.asc())).all())
    _base_context_reads(db)
    return {"result_rows": len(rows)}


def _creators(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    del artifacts
    rows = list(
        db.scalars(select(models.Creator).order_by(models.Creator.name.asc())).all()
    )
    _base_context_reads(db)
    return {"result_rows": len(rows)}


def _collections(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    del artifacts
    rows = list_collection_rows(db)
    _base_context_reads(db)
    return {"result_rows": len(rows)}


def _collection_detail(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    del artifacts
    collection = get_collection(db, 1)
    available = list_available_items_for_collection(db, 1)
    _base_context_reads(db)
    return {
        "collection_items": len(collection.items),
        "available_items_loaded": len(available),
        "relations_touched": _touch_items([*collection.items, *available]),
    }


def _saved_views(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    del artifacts
    rows = list_saved_views(db)
    _base_context_reads(db)
    return {"result_rows": len(rows)}


def _activity(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    del artifacts
    viewed = list_recently_viewed(db, limit=ACTIVITY_PAGE_LIMIT)
    edited = list_recently_edited(db, limit=ACTIVITY_PAGE_LIMIT)
    total = count_item_activity(db)
    _base_context_reads(db)
    activity_items = [row.item for row in [*viewed, *edited]]
    return {
        "result_rows": len(activity_items),
        "activity_total": total,
        "relations_touched": _touch_items(activity_items),
    }


def _duplicates(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    del artifacts
    groups = find_duplicate_candidates(db)
    items = [item for group in groups for item in group.items]
    _base_context_reads(db)
    return {
        "candidate_groups": len(groups),
        "candidate_items": len(items),
        "relations_touched": _touch_items(items),
    }


def _cleanup(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    del artifacts
    sections = find_metadata_cleanup_candidates(db)
    objects = [obj for section in sections for group in section.groups for obj in group.objects]
    _base_context_reads(db)
    return {
        "candidate_groups": sum(len(section.groups) for section in sections),
        "candidate_objects": len(objects),
        "related_items": sum(len(obj.items) for obj in objects),
    }


def _data_health(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    del artifacts
    report = build_data_health_report(db)
    _base_context_reads(db)
    return {"issues": report.total_issues, "status": report.status}


def _backup_validation(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    preview = preview_backup_data(artifacts.backup_payload, db)
    report = validate_backup_payload(artifacts.backup_payload, db)
    return {
        "status": report.status,
        "issues": len(report.issues),
        "relation_rows": report.relation_count,
        "item_rows": report.table_counts["items"],
        "preview_items": int(preview["items"]),
    }


def _import_dry_run(db: Session, artifacts: AuditArtifacts) -> dict[str, int | str | bool]:
    preview = preview_json_import(db, artifacts.import_content)
    return {
        "valid_rows": int(preview["summary"]["valid_rows"]),
        "error_rows": int(preview["summary"]["error_rows"]),
        "issues": len(preview["dry_run_report"]["issues"]),
    }


AUDIT_OPERATIONS: tuple[AuditOperation, ...] = (
    AuditOperation("items_page", False, _default_items_page),
    AuditOperation("items_filtered_sorted", False, _filtered_items_page),
    AuditOperation("workbench", False, _workbench),
    AuditOperation("stats", True, _stats),
    AuditOperation("tags", False, _tags),
    AuditOperation("creators", False, _creators),
    AuditOperation("collections", False, _collections),
    AuditOperation("collection_detail", False, _collection_detail),
    AuditOperation("saved_views", False, _saved_views),
    AuditOperation("activity", True, _activity),
    AuditOperation("duplicates", False, _duplicates),
    AuditOperation("cleanup", False, _cleanup),
    AuditOperation("data_health", False, _data_health),
    AuditOperation("backup_validation", False, _backup_validation),
    AuditOperation("import_dry_run", False, _import_dry_run),
)


def build_audit_artifacts(engine: Engine, dataset_size: int) -> AuditArtifacts:
    with Session(engine) as db:
        backup_payload = export_backup_data(db)
    import_rows = [
        {
            "title": f"Import candidate {index:05d}",
            "summary": "Performance audit import row",
            "status": _STATUS_VALUES[index % len(_STATUS_VALUES)],
            "rating": (index % 5) + 1,
            "tags": [f"Imported tag {index % 20}"],
            "creators": [f"Imported creator {index % 10}"],
            "collections": [f"Imported collection {index % 5}"],
        }
        for index in range(1, dataset_size + 1)
    ]
    return AuditArtifacts(
        backup_payload=backup_payload,
        import_content=json.dumps({"items": import_rows}).encode("utf-8"),
    )


def run_audit_suite(
    engine: Engine,
    artifacts: AuditArtifacts,
    *,
    dataset_size: int,
    operations: Iterable[AuditOperation] = AUDIT_OPERATIONS,
) -> list[AuditResult]:
    return [
        run_read_only_operation(
            engine,
            operation,
            artifacts,
            dataset_size=dataset_size,
        )
        for operation in operations
    ]


def _chunks(rows: list[dict[str, Any]], size: int = 1000) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _bulk_insert(connection: Any, model: type[Any], rows: list[dict[str, Any]]) -> None:
    for chunk in _chunks(rows):
        connection.execute(insert(model), chunk)


def create_performance_fixture(engine: Engine, dataset_size: int) -> dict[str, int]:
    if dataset_size <= 0:
        raise ValueError("dataset_size must be positive")
    Base.metadata.create_all(engine)
    tag_count = max(10, dataset_size // 10)
    creator_count = max(5, dataset_size // 20)
    collection_count = max(2, dataset_size // 50)
    saved_view_count = max(5, dataset_size // 20)
    timestamp = datetime(2026, 7, 10, 12, 0, 0)

    def metadata_name(prefix: str, index: int) -> str:
        pair = index // 40
        if index % 40 == 1:
            return f"{prefix} duplicate {pair}"
        if index % 40 == 2:
            return f"{prefix.upper()} DUPLICATE {pair}"
        return f"{prefix} {index:05d}"

    items: list[dict[str, Any]] = []
    for index in range(1, dataset_size + 1):
        title = (
            f"Duplicate title {index // 100}"
            if index % 100 in {1, 2}
            else f"Item {index:05d}"
        )
        items.append(
            {
                "id": index,
                "title": title,
                "summary": f"Local performance fixture item {index}",
                "extra": json.dumps({"fixture": index}),
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )

    with engine.begin() as connection:
        _bulk_insert(connection, models.Item, items)
        _bulk_insert(
            connection,
            models.Tag,
            [
                {"id": index, "name": metadata_name("Tag", index), "created_at": timestamp}
                for index in range(1, tag_count + 1)
            ],
        )
        _bulk_insert(
            connection,
            models.Creator,
            [
                {
                    "id": index,
                    "name": metadata_name("Creator", index),
                    "type": "other",
                    "created_at": timestamp,
                }
                for index in range(1, creator_count + 1)
            ],
        )
        _bulk_insert(
            connection,
            models.Collection,
            [
                {
                    "id": index,
                    "name": metadata_name("Collection", index),
                    "description": f"Fixture collection {index}",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
                for index in range(1, collection_count + 1)
            ],
        )
        _bulk_insert(
            connection,
            models.ItemTag,
            [
                {"item_id": index, "tag_id": ((index - 1) % tag_count) + 1}
                for index in range(1, dataset_size + 1)
            ],
        )
        _bulk_insert(
            connection,
            models.ItemCreator,
            [
                {"item_id": index, "creator_id": ((index - 1) % creator_count) + 1}
                for index in range(1, dataset_size + 1)
            ],
        )
        _bulk_insert(
            connection,
            models.ItemCollection,
            [
                {
                    "item_id": index,
                    "collection_id": ((index - 1) % collection_count) + 1,
                    "created_at": timestamp,
                }
                for index in range(1, dataset_size + 1)
            ],
        )
        _bulk_insert(
            connection,
            models.UserItemState,
            [
                {
                    "id": index,
                    "item_id": index,
                    "status": _STATUS_VALUES[index % len(_STATUS_VALUES)],
                    "rating": (index % 5) + 1,
                    "review": f"Fixture review {index}",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
                for index in range(1, dataset_size + 1)
            ],
        )
        _bulk_insert(
            connection,
            models.ItemActivity,
            [
                {
                    "id": index,
                    "item_id": index,
                    "last_viewed_at": timestamp,
                    "view_count": index,
                    "last_edited_at": timestamp,
                    "edit_count": index,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
                for index in range(1, dataset_size + 1)
            ],
        )
        _bulk_insert(
            connection,
            models.SavedView,
            [
                {
                    "id": index,
                    "name": f"Fixture view {index:05d}",
                    "query_string": (
                        "q=Item&page_size=20&tag="
                        f"Tag+{((index - 1) % tag_count) + 1:05d}"
                    ),
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
                for index in range(1, saved_view_count + 1)
            ],
        )
        connection.execute(
            insert(models.SchemaMigration),
            {"version": 1, "name": "baseline", "applied_at": timestamp},
        )
    return {
        "items": dataset_size,
        "tags": tag_count,
        "creators": creator_count,
        "collections": collection_count,
        "saved_views": saved_view_count,
        "activity": dataset_size,
    }
