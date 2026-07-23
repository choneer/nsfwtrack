from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.services.schema_version as schema_version
from app.database import Base, SessionLocal
from app.models import (
    Item,
    OperationTask,
    ProviderRuntimeState,
    SchemaMigration,
    TaskEvent,
)
from app.services.exporter import BACKUP_SCHEMA_V2, export_backup_data
from app.services.migrations import MIGRATION_REGISTRY, apply_upgrade, preview_upgrade
from app.services.schema_version import CURRENT_SCHEMA_VERSION, SchemaVersionError, initialize_database
from app.tasks import PersistentTaskService, TaskState, TaskTransitionError, TaskType
from app.tasks.contracts import TaskErrorCode


TASK_TABLES = {
    "operation_tasks",
    "task_events",
    "download_task_facts",
    "source_check_facts",
    "discovered_asset_facts",
    "item_local_assets",
}
RUNTIME_TABLES = {ProviderRuntimeState.__tablename__}


def test_schema_five_fresh_tables_are_empty_and_backup_v2_excludes_runtime() -> None:
    assert CURRENT_SCHEMA_VERSION == 6
    with SessionLocal() as db:
        names = set(inspect(db.get_bind()).get_table_names())
        assert TASK_TABLES.issubset(names)
        assert db.scalar(select(OperationTask.id)) is None
        assert db.scalar(select(TaskEvent.id)) is None
        payload = export_backup_data(db)
    assert payload["schema"] == BACKUP_SCHEMA_V2
    assert TASK_TABLES.isdisjoint(payload["tables"])


def test_schema_four_to_six_is_empty_atomic_and_repeat_safe() -> None:
    bind = create_engine("sqlite:///:memory:", future=True)
    old_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name not in TASK_TABLES | RUNTIME_TABLES
    ]
    try:
        Base.metadata.create_all(bind=bind, tables=old_tables)
        with bind.begin() as connection:
            connection.execute(
                SchemaMigration.__table__.insert().values(version=4, name="schema-4")
            )
            connection.execute(Item.__table__.insert().values(title="Preserved"))
        preview = preview_upgrade(bind, MIGRATION_REGISTRY)
        assert preview.can_upgrade
        assert [(step.from_version, step.to_version) for step in preview.steps] == [(4, 5), (5, 6)]
        result = apply_upgrade(bind, MIGRATION_REGISTRY, backup_confirmed=True)
        assert result.to_version == 6
        assert TASK_TABLES.issubset(inspect(bind).get_table_names())
        with Session(bind) as db:
            assert db.scalar(select(Item.title)) == "Preserved"
            assert db.scalar(select(OperationTask.id)) is None
        with pytest.raises(Exception) as exc_info:
            apply_upgrade(bind, MIGRATION_REGISTRY, backup_confirmed=True)
        assert getattr(exc_info.value, "code", None) == "no_upgrade_needed"
    finally:
        bind.dispose()


def test_stable_schema_four_application_rejects_schema_six(monkeypatch: pytest.MonkeyPatch) -> None:
    bind = create_engine("sqlite:///:memory:", future=True)
    try:
        initialize_database(bind)
        monkeypatch.setattr(schema_version, "CURRENT_SCHEMA_VERSION", 4)
        with pytest.raises(SchemaVersionError) as exc_info:
            schema_version.initialize_database(bind)
        assert exc_info.value.code == "application_outdated"
        assert exc_info.value.status is not None
        assert exc_info.value.status.database_version == 6
    finally:
        bind.dispose()


def test_task_state_machine_optimistic_version_terminal_and_retry_rules() -> None:
    with SessionLocal() as db:
        service = PersistentTaskService(db, max_concurrency=1)
        task, created = service.create(
            task_type=TaskType.SOURCE_CHECK,
            intent_key="test:task-state-machine",
            initial_state=TaskState.QUEUED,
        )
        assert created
        replay, replay_created = service.create(
            task_type=TaskType.SOURCE_CHECK,
            intent_key="test:task-state-machine",
            initial_state=TaskState.QUEUED,
        )
        assert not replay_created and replay.id == task.id
        with pytest.raises(TaskTransitionError) as version_error:
            service.transition(
                task.id,
                TaskState.RUNNING,
                expected_version=99,
                event_type="start_requested",
            )
        assert version_error.value.code is TaskErrorCode.VERSION_CONFLICT
        task = service.transition(
            task.id,
            TaskState.RUNNING,
            expected_version=task.version,
            event_type="start_requested",
        )
        task = service.transition(
            task.id,
            TaskState.OUTCOME_UNKNOWN,
            expected_version=task.version,
            event_type="commit_uncertain",
            error_code="outcome_unknown",
            error_detail="https://secret.invalid/path?token=value",
        )
        assert task.error_detail == "redacted"
        with pytest.raises(TaskTransitionError) as retry_error:
            service.retry(task.id, expected_version=task.version)
        assert retry_error.value.code is TaskErrorCode.RETRY_NOT_SAFE
        with pytest.raises(TaskTransitionError):
            service.transition(
                task.id,
                TaskState.SUCCEEDED,
                expected_version=task.version,
                event_type="invalid_success",
            )


def test_leases_concurrency_and_restart_recovery_require_explicit_action() -> None:
    with SessionLocal() as db:
        service = PersistentTaskService(db, max_concurrency=1)
        first, _ = service.create(
            task_type=TaskType.ASSET_DOWNLOAD,
            intent_key="test:lease-one",
            initial_state=TaskState.QUEUED,
        )
        first = service.transition(
            first.id,
            TaskState.RUNNING,
            expected_version=first.version,
            event_type="start_requested",
        )
        first = service.acquire_lease(
            first.id,
            owner="runner-one",
            expected_version=first.version,
            ttl_seconds=30,
        )
        generation = first.lease_generation
        first = service.heartbeat(
            first.id,
            owner="runner-one",
            generation=generation,
            ttl_seconds=30,
        )
        assert first.lease_generation == generation
        second, _ = service.create(
            task_type=TaskType.SOURCE_CHECK,
            intent_key="test:lease-two",
            initial_state=TaskState.QUEUED,
        )
        with pytest.raises(TaskTransitionError) as limit_error:
            service.transition(
                second.id,
                TaskState.RUNNING,
                expected_version=second.version,
                event_type="start_requested",
            )
        assert limit_error.value.code is TaskErrorCode.CONCURRENCY_LIMIT
        first_id = first.id
        db.commit()

    with SessionLocal() as db:
        recovered = PersistentTaskService(db, max_concurrency=1).recover_interrupted()
        db.commit()
        task = db.get(OperationTask, first_id)
        assert recovered == 1
        assert task is not None and task.state == TaskState.PAUSED.value
        assert task.lease_owner is None and task.lease_expires_at is None


def test_heartbeat_is_generation_fenced_and_expiry_fails_closed() -> None:
    with SessionLocal() as db:
        service = PersistentTaskService(db, max_concurrency=2)
        task, _ = service.create(
            task_type=TaskType.ASSET_DOWNLOAD,
            intent_key="test:fenced-heartbeat",
            initial_state=TaskState.QUEUED,
        )
        task = service.transition(
            task.id,
            TaskState.RUNNING,
            expected_version=task.version,
            event_type="start_requested",
        )
        task = service.acquire_lease(
            task.id,
            owner="current-owner",
            expected_version=task.version,
            ttl_seconds=30,
        )
        task_id = task.id
        generation = task.lease_generation
        first_heartbeat = task.lease_heartbeat_at
        first_expiry = task.lease_expires_at
        db.commit()

        refreshed = service.heartbeat(
            task_id,
            owner="current-owner",
            generation=generation,
            ttl_seconds=60,
            bytes_processed=4096,
            stage="downloading",
        )
        db.commit()
        assert refreshed.lease_generation == generation
        assert refreshed.lease_heartbeat_at >= first_heartbeat
        assert refreshed.lease_expires_at > first_expiry
        assert refreshed.bytes_processed == 4096

        for owner, candidate_generation in (
            ("stale-owner", generation),
            ("current-owner", generation - 1),
        ):
            with pytest.raises(TaskTransitionError) as conflict:
                service.heartbeat(
                    task_id,
                    owner=owner,
                    generation=candidate_generation,
                    ttl_seconds=30,
                )
            assert conflict.value.code is TaskErrorCode.LEASE_CONFLICT
            db.rollback()

        db.execute(
            update(OperationTask)
            .where(OperationTask.id == task_id)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.commit()
        with pytest.raises(TaskTransitionError) as expired:
            service.heartbeat(
                task_id,
                owner="current-owner",
                generation=generation,
                ttl_seconds=30,
            )
        assert expired.value.code is TaskErrorCode.LEASE_CONFLICT


def test_concurrent_start_and_resume_claims_obey_atomic_max_concurrency() -> None:
    with SessionLocal() as db:
        service = PersistentTaskService(db, max_concurrency=1)
        first, _ = service.create(
            task_type=TaskType.ASSET_DOWNLOAD,
            intent_key="test:atomic-start",
            initial_state=TaskState.QUEUED,
        )
        second, _ = service.create(
            task_type=TaskType.ASSET_DOWNLOAD,
            intent_key="test:atomic-resume",
            initial_state=TaskState.PAUSED,
        )
        second = service.transition(
            second.id,
            TaskState.QUEUED,
            expected_version=second.version,
            event_type="resume_requested",
        )
        first_id, second_id = first.id, second.id
        db.commit()

    barrier = Barrier(2)

    def claim(task_id: int) -> str:
        with SessionLocal() as candidate:
            service = PersistentTaskService(candidate, max_concurrency=1)
            task = service.get(task_id)
            barrier.wait()
            try:
                service.transition(
                    task.id,
                    TaskState.RUNNING,
                    expected_version=task.version,
                    event_type="start_requested",
                )
                candidate.commit()
                return "running"
            except TaskTransitionError as error:
                candidate.rollback()
                return error.code.value

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(claim, (first_id, second_id)))
    assert sorted(results) == ["concurrency_limit", "running"]
    with SessionLocal() as db:
        assert db.scalar(
            select(func.count()).select_from(OperationTask).where(
                OperationTask.state == TaskState.RUNNING.value
            )
        ) == 1


def test_database_constraints_reject_unknown_task_state() -> None:
    with SessionLocal() as db:
        db.add(
            OperationTask(
                task_type="source_check",
                state="invented",
                intent_key="test:invalid-state",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_bounded_history_cleanup_removes_only_unlinked_old_terminal_tasks() -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        service = PersistentTaskService(db, max_concurrency=2)
        old, _ = service.create(
            task_type=TaskType.SOURCE_CHECK,
            intent_key="test:old-history",
            initial_state=TaskState.QUEUED,
        )
        old = service.transition(
            old.id,
            TaskState.CANCELLED,
            expected_version=old.version,
            event_type="cancel_requested",
        )
        old.finished_at = now - timedelta(days=40)
        recent, _ = service.create(
            task_type=TaskType.SOURCE_CHECK,
            intent_key="test:recent-history",
            initial_state=TaskState.QUEUED,
        )
        recent = service.transition(
            recent.id,
            TaskState.CANCELLED,
            expected_version=recent.version,
            event_type="cancel_requested",
        )
        recent.finished_at = now - timedelta(days=2)
        old_id = old.id
        recent_id = recent.id
        db.commit()
        removed = service.cleanup_history(retention_days=30, now=now, limit=10)
        db.commit()
        assert removed == 1
        assert db.get(OperationTask, old_id) is None
        assert db.get(OperationTask, recent_id) is not None
