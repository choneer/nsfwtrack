from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, func, insert, select
from sqlalchemy.orm import Session

from app import models
from app.services.performance_audit import (
    AUDIT_OPERATIONS,
    AuditArtifacts,
    AuditOperation,
    PerformanceAuditError,
    build_audit_artifacts,
    create_performance_fixture,
    run_audit_suite,
    run_read_only_operation,
)


def _engine(path: Path) -> Engine:
    return create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        future=True,
    )


def test_audit_suite_is_read_only_and_covers_required_operations(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "performance.db")
    fixture = create_performance_fixture(engine, 30)
    artifacts = build_audit_artifacts(engine, 30)
    with Session(engine) as db:
        before = int(db.scalar(select(func.count(models.Item.id))) or 0)

    results = run_audit_suite(engine, artifacts, dataset_size=30)

    assert fixture["items"] == 30
    assert {result.operation for result in results} == {
        operation.name for operation in AUDIT_OPERATIONS
    }
    assert all(result.query_count >= result.unique_query_count for result in results)
    assert all(result.duration_ms >= 0 for result in results)
    assert all(
        not result.plans or all(plan.statement for plan in result.plans)
        for result in results
    )
    by_operation = {result.operation: result for result in results}
    assert by_operation["items_page"].query_count <= 11
    assert by_operation["cleanup"].query_count <= 4
    assert by_operation["collection_detail"].query_count <= 10
    assert by_operation["tags"].query_count <= 3
    assert by_operation["creators"].query_count <= 3
    assert by_operation["collections"].query_count <= 3
    assert by_operation["duplicates"].query_count <= 7
    assert by_operation["stats"].query_count <= 11
    assert by_operation["data_health"].query_count <= 12
    with Session(engine) as db:
        after = int(db.scalar(select(func.count(models.Item.id))) or 0)
    assert after == before == 30
    engine.dispose()


def test_read_only_audit_blocks_write_statements(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "readonly.db")
    create_performance_fixture(engine, 10)
    artifacts = AuditArtifacts(backup_payload={}, import_content=b'{"items": []}')

    def attempt_write(
        db: Session,
        audit_artifacts: AuditArtifacts,
    ) -> dict[str, int | str | bool]:
        del audit_artifacts
        db.execute(insert(models.Tag), {"name": "must not persist"})
        return {"written": True}

    operation = AuditOperation("write_attempt", True, attempt_write)
    with pytest.raises(PerformanceAuditError, match="write statement blocked"):
        run_read_only_operation(engine, operation, artifacts, dataset_size=10)
    with Session(engine) as db:
        assert db.scalar(select(models.Tag.id).where(models.Tag.name == "must not persist")) is None
        db.add(models.Tag(name="connection remains writable after audit"))
        db.commit()
    engine.dispose()


def test_paginated_item_query_count_does_not_grow_per_row(tmp_path: Path) -> None:
    query_counts: list[int] = []
    for size in (20, 200):
        engine = _engine(tmp_path / f"items-{size}.db")
        create_performance_fixture(engine, size)
        artifacts = build_audit_artifacts(engine, size)
        operation = next(row for row in AUDIT_OPERATIONS if row.name == "items_page")
        result = run_read_only_operation(engine, operation, artifacts, dataset_size=size)
        query_counts.append(result.query_count)
        assert result.metrics["result_rows"] <= result.metrics["page_size"]
        engine.dispose()

    assert query_counts[1] - query_counts[0] <= 2


def test_collection_detail_eliminates_n_plus_one_and_bounds_rows(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "collection-detail.db")
    create_performance_fixture(engine, 100)
    artifacts = build_audit_artifacts(engine, 100)
    operation = next(
        row for row in AUDIT_OPERATIONS if row.name == "collection_detail"
    )

    result = run_read_only_operation(engine, operation, artifacts, dataset_size=100)

    assert result.metrics["collection_items"] == 50
    assert result.metrics["collection_items_loaded"] == 20
    assert result.metrics["available_items_loaded"] == 20
    assert result.n_plus_one_detected is False
    assert result.query_count <= 10
    engine.dispose()
