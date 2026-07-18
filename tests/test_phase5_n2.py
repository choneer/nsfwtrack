from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.services.backup as backup_service
from app.database import Base, SessionLocal
from app.models import Item, ItemSource, MediaIndexState, SchemaMigration
from app.services.backup import BackupError, preview_backup_data, restore_backup_data
from app.services.backup_validator import validate_backup_payload
from app.services.exporter import export_backup_data
from app.services.migrations import (
    MIGRATION_REGISTRY,
    MigrationError,
    MigrationRegistry,
    apply_upgrade,
    preview_upgrade,
)
from app.services.schema_version import (
    CURRENT_SCHEMA_VERSION,
    SchemaVersionError,
    initialize_database,
)


SCHEMA_MATRIX = {
    "empty": "fresh Schema 4",
    "schema_1": "1->2->3->4",
    "schema_2": "2->3->4",
    "schema_3": "3->4",
    "schema_4": "no upgrade",
    "schema_5_plus": "application_outdated",
    "failure": "full-chain rollback",
}

BACKUP_MATRIX = {
    "v1": "four source-tracking fields become null",
    "v2": "source-tracking fields are restored",
    "payload_duplicate": "validation error",
    "exact_local_match": "reuse without overwrite",
    "url_or_identity_conflict": "hard conflict and zero commit",
    "exception": "independent transaction outcome review",
}


def _minimal_payload(
    *,
    schema: str = "nsfwtrack.backup.v2",
    items: list[dict[str, object]] | None = None,
    sources: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema": schema,
        "exported_at": "2026-07-18T00:00:00+00:00",
        "tables": {
            "items": items or [{"id": 1, "title": "Restored item"}],
            "tags": [],
            "creators": [],
            "item_tags": [],
            "item_creators": [],
            "user_item_states": [],
            "item_sources": sources or [],
        },
    }


def _provider_source(
    *,
    item_id: int = 1,
    url: str = "https://example.com/source",
    provider_key: str | None = "provider_a",
    external_id: str | None = "Case-Sensitive-1",
    last_checked_at: object = "2026-07-18T08:00:00+08:00",
    metadata_hash: str | None = "v1:sha256:" + ("a" * 64),
) -> dict[str, object]:
    return {
        "id": 1,
        "item_id": item_id,
        "url": url,
        "normalized_url": url,
        "title": "Backup title",
        "provider_key": provider_key,
        "external_id": external_id,
        "last_checked_at": last_checked_at,
        "metadata_hash": metadata_hash,
    }


def _prepare_schema(bind: Engine, version: int) -> None:
    schema_1_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name
        not in {"item_sources", "media_index_entries", "media_index_state"}
    ]
    Base.metadata.create_all(bind=bind, tables=schema_1_tables)
    with bind.begin() as connection:
        connection.execute(
            SchemaMigration.__table__.insert().values(version=1, name="baseline")
        )
        connection.execute(Item.__table__.insert().values(title="Legacy item"))
    if version > 1:
        apply_upgrade(
            bind,
            MIGRATION_REGISTRY,
            backup_confirmed=True,
            target_version=version,
        )
        with bind.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO item_sources "
                    "(item_id, url, normalized_url, title) "
                    "VALUES (1, 'https://legacy.example/source', "
                    "'https://legacy.example/source', 'Legacy source')"
                )
            )


def _provider_index_sql(bind: Engine) -> str:
    with bind.connect() as connection:
        value = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND name='uq_item_sources_provider_identity'"
        ).scalar_one()
    return str(value)


@pytest.mark.parametrize("start_version", [1, 2, 3])
def test_schema_matrix_upgrades_continuously_to_four(start_version: int) -> None:
    bind = create_engine("sqlite:///:memory:", future=True)
    try:
        _prepare_schema(bind, start_version)
        dry_run = preview_upgrade(bind, MIGRATION_REGISTRY)
        assert dry_run.can_upgrade
        assert dry_run.current_version == start_version
        assert dry_run.target_version == 4

        result = apply_upgrade(bind, MIGRATION_REGISTRY, backup_confirmed=True)

        assert result.to_version == 4
        columns = {
            column["name"] for column in inspect(bind).get_columns("item_sources")
        }
        assert {
            "provider_key",
            "external_id",
            "last_checked_at",
            "metadata_hash",
        }.issubset(columns)
        assert "WHERE provider_key IS NOT NULL AND external_id IS NOT NULL" in (
            _provider_index_sql(bind)
        )
        with bind.connect() as connection:
            assert connection.scalar(
                select(SchemaMigration.version)
                .order_by(SchemaMigration.version.desc())
                .limit(1)
            ) == 4
            if start_version > 1:
                row = connection.exec_driver_sql(
                    "SELECT provider_key, external_id, last_checked_at, metadata_hash "
                    "FROM item_sources"
                ).one()
                assert row == (None, None, None, None)
    finally:
        bind.dispose()


def test_fresh_schema_four_has_partial_unique_identity_index() -> None:
    bind = create_engine("sqlite:///:memory:", future=True)
    try:
        status = initialize_database(bind)
        assert status.database_version == CURRENT_SCHEMA_VERSION == 4
        assert "WHERE provider_key IS NOT NULL AND external_id IS NOT NULL" in (
            _provider_index_sql(bind)
        )
        with bind.begin() as connection:
            connection.execute(Item.__table__.insert().values(id=1, title="One"))
            connection.execute(Item.__table__.insert().values(id=2, title="Two"))
            connection.execute(
                ItemSource.__table__.insert().values(
                    item_id=1,
                    url="https://one.example/a",
                    normalized_url="https://one.example/a",
                )
            )
            connection.execute(
                ItemSource.__table__.insert().values(
                    item_id=2,
                    url="https://two.example/a",
                    normalized_url="https://two.example/a",
                )
            )
        with pytest.raises(IntegrityError):
            with bind.begin() as connection:
                connection.execute(
                    ItemSource.__table__.insert().values(
                        item_id=1,
                        url="https://one.example/provider",
                        normalized_url="https://one.example/provider",
                        provider_key="provider_a",
                        external_id="Same-ID",
                    )
                )
                connection.execute(
                    ItemSource.__table__.insert().values(
                        item_id=2,
                        url="https://two.example/provider",
                        normalized_url="https://two.example/provider",
                        provider_key="provider_a",
                        external_id="Same-ID",
                    )
                )
    finally:
        bind.dispose()


def test_fresh_and_migrated_schema_four_source_structures_are_equivalent() -> None:
    fresh = create_engine("sqlite:///:memory:", future=True)
    migrated = create_engine("sqlite:///:memory:", future=True)
    try:
        initialize_database(fresh)
        _prepare_schema(migrated, 3)
        apply_upgrade(migrated, MIGRATION_REGISTRY, backup_confirmed=True)

        def structure(bind: Engine) -> tuple[object, object, str]:
            inspector = inspect(bind)
            columns = tuple(
                sorted(
                    (
                        column["name"],
                        str(column["type"]).upper(),
                        bool(column["nullable"]),
                        int(column.get("primary_key") or 0),
                    )
                    for column in inspector.get_columns("item_sources")
                )
            )
            indexes = tuple(
                sorted(
                    (
                        index["name"],
                        tuple(index.get("column_names") or ()),
                        bool(index.get("unique")),
                    )
                    for index in inspector.get_indexes("item_sources")
                )
            )
            predicate = "".join(_provider_index_sql(bind).casefold().split()).split(
                "where", 1
            )[1]
            return columns, indexes, predicate

        assert structure(fresh) == structure(migrated)
    finally:
        fresh.dispose()
        migrated.dispose()


@pytest.mark.parametrize(
    "replacement_sql",
    [
        None,
        (
            "CREATE UNIQUE INDEX uq_item_sources_provider_identity "
            "ON item_sources (provider_key, external_id) "
            "WHERE provider_key IS NOT NULL"
        ),
    ],
)
def test_current_schema_four_refuses_missing_or_invalid_partial_index(
    replacement_sql: str | None,
) -> None:
    bind = create_engine("sqlite:///:memory:", future=True)
    try:
        initialize_database(bind)
        with bind.begin() as connection:
            connection.exec_driver_sql(
                "DROP INDEX uq_item_sources_provider_identity"
            )
            if replacement_sql is not None:
                connection.exec_driver_sql(replacement_sql)

        with pytest.raises(SchemaVersionError) as exc_info:
            initialize_database(bind)

        assert exc_info.value.code == "structure_invalid"
        assert any(
            "provider identity" in problem
            for problem in exc_info.value.problems
        )
    finally:
        bind.dispose()


def test_schema_four_repeat_apply_is_rejected_without_changes() -> None:
    bind = create_engine("sqlite:///:memory:", future=True)
    try:
        _prepare_schema(bind, 3)
        apply_upgrade(bind, MIGRATION_REGISTRY, backup_confirmed=True)
        with bind.connect() as connection:
            before_versions = tuple(
                connection.scalars(
                    select(SchemaMigration.version).order_by(SchemaMigration.version)
                )
            )
            before_index_sql = _provider_index_sql(bind)

        with pytest.raises(MigrationError) as exc_info:
            apply_upgrade(bind, MIGRATION_REGISTRY, backup_confirmed=True)

        assert exc_info.value.code == "no_upgrade_needed"
        with bind.connect() as connection:
            assert tuple(
                connection.scalars(
                    select(SchemaMigration.version).order_by(SchemaMigration.version)
                )
            ) == before_versions
        assert _provider_index_sql(bind) == before_index_sql
    finally:
        bind.dispose()


def test_future_schema_is_rejected_as_application_outdated() -> None:
    bind = create_engine("sqlite:///:memory:", future=True)
    try:
        initialize_database(bind)
        with bind.begin() as connection:
            connection.execute(
                SchemaMigration.__table__.insert().values(
                    version=5,
                    name="future_schema",
                )
            )

        with pytest.raises(SchemaVersionError) as exc_info:
            initialize_database(bind)

        assert exc_info.value.code == "application_outdated"
        assert exc_info.value.status is not None
        assert exc_info.value.status.database_version == 5
    finally:
        bind.dispose()


def test_schema_full_chain_failure_rolls_back_every_step() -> None:
    bind = create_engine("sqlite:///:memory:", future=True)
    try:
        _prepare_schema(bind, 1)
        original = MIGRATION_REGISTRY.steps[-1]

        def fail_after_schema_four(connection: object) -> None:
            original.apply(connection)  # type: ignore[arg-type]
            raise RuntimeError("injected Schema 4 failure")

        registry = MigrationRegistry(
            (*MIGRATION_REGISTRY.steps[:-1], replace(original, apply=fail_after_schema_four))
        )
        with pytest.raises(MigrationError):
            apply_upgrade(bind, registry, backup_confirmed=True)

        assert "item_sources" not in inspect(bind).get_table_names()
        assert "media_index_entries" not in inspect(bind).get_table_names()
        with bind.connect() as connection:
            assert list(connection.scalars(select(SchemaMigration.version))) == [1]
            assert connection.scalar(select(Item.title)) == "Legacy item"
    finally:
        bind.dispose()


def test_backup_v2_exports_and_restores_tracking_metadata() -> None:
    checked = datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        item = Item(title="Provider item")
        db.add(item)
        db.flush()
        db.add(
            ItemSource(
                item_id=item.id,
                url="https://example.com/source",
                normalized_url="https://example.com/source",
                provider_key="provider_a",
                external_id="Case-Sensitive-1",
                last_checked_at=checked,
                metadata_hash="v1:sha256:" + ("a" * 64),
            )
        )
        db.commit()
        payload = export_backup_data(db)
    assert payload["schema"] == "nsfwtrack.backup.v2"
    row = payload["tables"]["item_sources"][0]
    assert row["provider_key"] == "provider_a"
    assert row["external_id"] == "Case-Sensitive-1"
    assert row["last_checked_at"] == "2026-07-18T00:00:00+00:00"

    with SessionLocal() as db:
        db.query(ItemSource).delete()
        db.query(Item).delete()
        db.commit()
        result = restore_backup_data(db, payload)
        restored = db.scalar(select(ItemSource))
    assert result["database_outcome"] == "committed"
    assert restored is not None
    assert restored.provider_key == "provider_a"
    assert restored.external_id == "Case-Sensitive-1"
    assert restored.last_checked_at == checked


def test_schema_three_can_export_and_preview_v2_before_upgrade() -> None:
    bind = create_engine("sqlite:///:memory:", future=True)
    try:
        _prepare_schema(bind, 3)
        SchemaThreeSession = sessionmaker(bind=bind, future=True)
        with SchemaThreeSession() as db:
            payload = export_backup_data(db)
            source = payload["tables"]["item_sources"][0]
            assert payload["schema"] == "nsfwtrack.backup.v2"
            assert source["provider_key"] is None
            assert source["external_id"] is None
            preview = preview_backup_data(payload, db)
            assert preview["input_schema"] == "nsfwtrack.backup.v2"
            assert preview["item_sources_to_reuse"] == 1
            assert preview["item_sources_conflicts"] == 0
    finally:
        bind.dispose()


def test_backup_v1_restores_tracking_fields_as_null() -> None:
    payload = _minimal_payload(
        schema="nsfwtrack.backup.v1",
        sources=[
            {
                "id": 1,
                "item_id": 1,
                "url": "https://legacy.example/source",
                "normalized_url": "https://legacy.example/source",
                "title": "Legacy",
            }
        ],
    )
    with SessionLocal() as db:
        result = restore_backup_data(db, payload)
        source = db.scalar(select(ItemSource))
    assert result["input_schema"] == "nsfwtrack.backup.v1"
    assert source is not None
    assert (
        source.provider_key,
        source.external_id,
        source.last_checked_at,
        source.metadata_hash,
    ) == (None, None, None, None)


def test_backup_v2_accepts_explicit_null_tracking_fields_for_legacy_sources() -> None:
    source = _provider_source(
        provider_key=None,
        external_id=None,
        last_checked_at=None,
        metadata_hash=None,
    )
    report = validate_backup_payload(
        _minimal_payload(sources=[source])
    ).to_dict()
    assert report["error_count"] == 0


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"provider_key": None}, "invalid_provider_identity"),
        ({"provider_key": "Provider"}, "invalid_provider_key"),
        ({"external_id": "bad\nvalue"}, "invalid_external_id"),
        ({"last_checked_at": "2026-07-18T00:00:00"}, "invalid_last_checked_at"),
        ({"metadata_hash": "sha256:bad"}, "invalid_metadata_hash"),
    ],
)
def test_backup_v2_validation_rejects_invalid_tracking_values(
    changes: dict[str, object],
    code: str,
) -> None:
    source = _provider_source()
    source.update(changes)
    report = validate_backup_payload(
        _minimal_payload(sources=[source])
    ).to_dict()
    assert report["status"] == "blocked"
    assert code in {issue["code"] for issue in report["issues"]}


def test_payload_duplicate_url_and_identity_are_blocking_errors() -> None:
    first = _provider_source()
    second = _provider_source()
    second["id"] = 2
    report = validate_backup_payload(
        _minimal_payload(sources=[first, second])
    ).to_dict()
    codes = {issue["code"] for issue in report["issues"]}
    assert report["status"] == "blocked"
    assert {"duplicate_source_url", "duplicate_provider_identity"}.issubset(codes)


def test_backup_page_shows_v2_source_create_reuse_and_conflict_metrics(
    auth_client: TestClient,
) -> None:
    payload = _minimal_payload(sources=[_provider_source()])
    response = auth_client.post(
        "/backup/preview",
        files={
            "file": (
                "backup.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        },
    )
    assert response.status_code == 200
    assert "将创建来源链接" in response.text
    assert "将精确复用来源链接" in response.text
    assert "阻塞来源冲突" in response.text
    assert "Provider 来源" in response.text


def test_exact_reuse_does_not_overwrite_local_source_metadata() -> None:
    with SessionLocal() as db:
        item = Item(id=1, title="Restored item")
        db.add(item)
        db.add(
            ItemSource(
                item_id=1,
                url="https://example.com/source",
                normalized_url="https://example.com/source",
                title="Local title",
                provider_key="provider_a",
                external_id="Case-Sensitive-1",
                last_checked_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                metadata_hash="v1:sha256:" + ("b" * 64),
            )
        )
        db.commit()
        payload = _minimal_payload(sources=[_provider_source()])
        preview = preview_backup_data(payload, db)
        assert preview["item_sources_to_reuse"] == 1
        assert preview["item_sources_conflicts"] == 0
        result = restore_backup_data(db, payload)
        source = db.scalar(select(ItemSource))
    assert result["item_sources_reused"] == 1
    assert source is not None
    assert source.title == "Local title"
    assert source.metadata_hash == "v1:sha256:" + ("b" * 64)


@pytest.mark.parametrize(
    "incoming",
    [
        _provider_source(item_id=2),
        _provider_source(url="https://example.com/different"),
    ],
)
def test_local_source_conflicts_block_the_entire_restore(
    incoming: dict[str, object],
) -> None:
    with SessionLocal() as db:
        db.add_all([Item(id=1, title="One"), Item(id=2, title="Two")])
        db.add(
            ItemSource(
                item_id=1,
                url="https://example.com/source",
                normalized_url="https://example.com/source",
                provider_key="provider_a",
                external_id="Case-Sensitive-1",
            )
        )
        db.commit()
        incoming_item_id = int(incoming["item_id"])
        payload = _minimal_payload(
            items=[
                {
                    "id": incoming_item_id,
                    "title": "One" if incoming_item_id == 1 else "Two",
                }
            ],
            sources=[incoming],
        )
        preview = preview_backup_data(payload, db)
        assert preview["item_sources_conflicts"] == 1
        before_titles = list(db.scalars(select(Item.title).order_by(Item.id)))
        with pytest.raises(BackupError) as exc_info:
            restore_backup_data(db, payload)
        after_titles = list(db.scalars(select(Item.title).order_by(Item.id)))
    assert exc_info.value.code == "source_local_conflict"
    assert after_titles == before_titles


def test_local_source_conflict_http_response_is_stable_and_zero_commit(
    auth_client: TestClient,
) -> None:
    with SessionLocal() as db:
        db.add(Item(id=1, title="Existing item"))
        db.add(
            ItemSource(
                item_id=1,
                url="https://example.com/source",
                normalized_url="https://example.com/source",
                provider_key="provider_a",
                external_id="Case-Sensitive-1",
            )
        )
        db.commit()

    payload = _minimal_payload(
        items=[{"id": 2, "title": "Conflicting item"}],
        sources=[_provider_source(item_id=2)],
    )
    response = auth_client.post(
        "/api/backup/restore/json",
        data={"confirm": "1"},
        files={
            "file": (
                "backup.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert response.status_code == 400
    assert "来源 URL 或 provider 身份与当前数据库冲突" in response.json()["detail"]
    with SessionLocal() as db:
        assert db.get(Item, 2) is None
        assert db.scalar(select(ItemSource).where(ItemSource.item_id == 1)) is not None


def test_restore_exception_rolls_back_and_independently_confirms_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _minimal_payload(sources=[_provider_source()])

    def fail_sources(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("injected restore failure")

    monkeypatch.setattr(backup_service, "_create_item_sources", fail_sources)
    with SessionLocal() as db:
        with pytest.raises(BackupError) as exc_info:
            restore_backup_data(db, payload)
        assert db.scalar(select(Item.id)) is None
    assert exc_info.value.code == "restore_rolled_back"


def test_restore_uses_begin_immediate_and_revalidates_inside_transaction() -> None:
    payload = _minimal_payload(sources=[_provider_source()])
    statements: list[str] = []

    def record_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        statements.append(statement.strip().upper())

    with SessionLocal() as db:
        event.listen(db.get_bind(), "before_cursor_execute", record_statement)
        try:
            result = restore_backup_data(db, payload)
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", record_statement)
    assert result["database_outcome"] == "committed"
    assert "BEGIN IMMEDIATE" in statements


def test_commit_error_after_real_commit_is_reported_from_independent_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _minimal_payload(sources=[_provider_source()])
    with SessionLocal() as db:
        original_commit = db.commit

        def commit_then_raise() -> None:
            original_commit()
            raise RuntimeError("injected post-commit error")

        monkeypatch.setattr(db, "commit", commit_then_raise)
        result = restore_backup_data(db, payload)
    assert result["database_outcome"] == "committed_after_error"
    with SessionLocal() as verification_db:
        assert verification_db.scalar(select(ItemSource.id)) is not None


def test_restore_independent_review_failure_reports_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _minimal_payload(sources=[_provider_source()])

    def fail_sources(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("injected restore failure")

    monkeypatch.setattr(backup_service, "_create_item_sources", fail_sources)
    monkeypatch.setattr(
        backup_service,
        "_independent_restore_state_digest",
        lambda _db: None,
    )
    with SessionLocal() as db:
        with pytest.raises(BackupError) as exc_info:
            restore_backup_data(db, payload)
    assert exc_info.value.code == "restore_outcome_unknown"


def test_restore_unknown_outcome_http_response_preserves_database(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _minimal_payload(sources=[_provider_source()])

    def fail_sources(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("injected restore failure")

    monkeypatch.setattr(backup_service, "_create_item_sources", fail_sources)
    monkeypatch.setattr(
        backup_service,
        "_independent_restore_state_digest",
        lambda _db: None,
    )
    response = auth_client.post(
        "/api/backup/restore/json",
        data={"confirm": "1"},
        files={
            "file": (
                "backup.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert response.status_code == 400
    assert "恢复事务结果无法独立确认" in response.json()["detail"]
    with SessionLocal() as db:
        assert db.scalar(select(Item.id)) is None


def test_successful_restore_invalidates_media_index() -> None:
    payload = _minimal_payload(sources=[_provider_source()])
    with SessionLocal() as db:
        state = db.get(MediaIndexState, 1)
        assert state is not None
        state.valid = True
        state.stale_reason = "manual_test"
        db.commit()

        result = restore_backup_data(db, payload)
        db.refresh(state)

        assert result["database_outcome"] == "committed"
        assert state.valid is False
        assert state.stale_reason == "backup_restored"


def test_migration_backup_preview_and_restore_do_not_call_outbound_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.outbound_http import OutboundHttpClient

    async def reject_network(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("outbound network must not be called")

    monkeypatch.setattr(OutboundHttpClient, "fetch_json", reject_network)
    bind = create_engine("sqlite:///:memory:", future=True)
    try:
        _prepare_schema(bind, 3)
        assert preview_upgrade(bind, MIGRATION_REGISTRY).can_upgrade
        assert apply_upgrade(
            bind,
            MIGRATION_REGISTRY,
            backup_confirmed=True,
        ).to_version == 4
    finally:
        bind.dispose()
    payload = _minimal_payload(sources=[_provider_source()])
    with SessionLocal() as db:
        assert preview_backup_data(payload, db)["can_restore"] is True
        assert restore_backup_data(db, payload)["database_outcome"] == "committed"


def test_backup_http_get_preview_and_restore_do_not_call_outbound_client(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.outbound_http import OutboundHttpClient

    async def reject_network(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("outbound network must not be called")

    monkeypatch.setattr(OutboundHttpClient, "fetch_json", reject_network)
    payload = _minimal_payload(sources=[_provider_source()])
    upload = {
        "file": (
            "backup.json",
            json.dumps(payload).encode("utf-8"),
            "application/json",
        )
    }

    assert auth_client.get("/backup").status_code == 200
    assert auth_client.post("/api/backup/preview/json", files=upload).status_code == 200
    restore_response = auth_client.post(
        "/api/backup/restore/json",
        data={"confirm": "1"},
        files=upload,
    )
    assert restore_response.status_code == 200
