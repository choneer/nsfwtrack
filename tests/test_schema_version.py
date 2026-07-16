from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, inspect, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Item, MediaIndexEntry, MediaIndexState, SchemaMigration
from app.services.schema_version import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_MIGRATIONS_TABLE,
    SCHEMA_STATUS_APPLICATION_OUTDATED,
    SCHEMA_STATUS_CURRENT,
    SCHEMA_STATUS_UNKNOWN,
    SCHEMA_STATUS_UPGRADE_REQUIRED,
    SchemaVersionError,
    get_schema_status,
    initialize_database,
)


@pytest.fixture
def isolated_engine() -> Generator[Engine, None, None]:
    test_engine = create_engine("sqlite:///:memory:", future=True)
    try:
        yield test_engine
    finally:
        test_engine.dispose()


def _create_business_schema(bind: Engine, *, omit: set[str] | None = None) -> None:
    omitted = omit or set()
    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name != SCHEMA_MIGRATIONS_TABLE and table.name not in omitted
    ]
    Base.metadata.create_all(bind=bind, tables=tables)


def _set_isolated_version(bind: Engine, version: int) -> None:
    with bind.begin() as connection:
        connection.execute(
            update(SchemaMigration).values(version=version, name=f"version-{version}")
        )


def _global_schema_row() -> tuple[int, str]:
    with SessionLocal() as db:
        row = db.scalar(select(SchemaMigration))
        assert row is not None
        return row.version, row.name


def test_new_database_registers_current_baseline(isolated_engine: Engine) -> None:
    status = initialize_database(isolated_engine)

    assert status.state == SCHEMA_STATUS_CURRENT
    assert status.application_version == CURRENT_SCHEMA_VERSION
    assert status.database_version == CURRENT_SCHEMA_VERSION
    assert status.last_applied_at is not None
    with isolated_engine.connect() as connection:
        row = connection.execute(
            select(
                SchemaMigration.version,
                SchemaMigration.name,
                SchemaMigration.applied_at,
            )
        ).one()
    assert row.version == CURRENT_SCHEMA_VERSION
    assert row.name == "baseline"
    assert row.applied_at is not None
    with isolated_engine.connect() as connection:
        assert connection.scalar(select(MediaIndexEntry.id)) is None
        state = connection.execute(
            select(
                MediaIndexState.index_format_version,
                MediaIndexState.valid,
                MediaIndexState.stale_reason,
            )
        ).one()
    assert state == (1, False, "never_scanned")


def test_legacy_database_is_validated_registered_and_preserved(
    isolated_engine: Engine,
) -> None:
    _create_business_schema(isolated_engine)
    with isolated_engine.begin() as connection:
        connection.execute(Item.__table__.insert().values(title="Legacy Item"))

    status = initialize_database(isolated_engine)

    assert status.state == SCHEMA_STATUS_CURRENT
    assert SCHEMA_MIGRATIONS_TABLE in inspect(isolated_engine).get_table_names()
    with isolated_engine.connect() as connection:
        assert connection.scalar(select(Item.title)) == "Legacy Item"
        assert connection.scalar(select(SchemaMigration.version)) == (
            CURRENT_SCHEMA_VERSION
        )


def test_legacy_database_missing_required_table_is_not_registered(
    isolated_engine: Engine,
) -> None:
    _create_business_schema(isolated_engine, omit={"app_settings"})

    with pytest.raises(SchemaVersionError) as exc_info:
        initialize_database(isolated_engine)

    assert exc_info.value.code == "structure_invalid"
    assert "missing table app_settings" in str(exc_info.value)
    assert SCHEMA_MIGRATIONS_TABLE not in inspect(isolated_engine).get_table_names()


def test_legacy_database_missing_required_column_is_not_registered(
    isolated_engine: Engine,
) -> None:
    _create_business_schema(isolated_engine, omit={"app_settings"})
    with isolated_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE app_settings ("
                "id INTEGER PRIMARY KEY, key VARCHAR(64), value TEXT)"
            )
        )

    with pytest.raises(SchemaVersionError) as exc_info:
        initialize_database(isolated_engine)

    assert exc_info.value.code == "structure_invalid"
    assert "missing columns in app_settings" in str(exc_info.value)
    assert SCHEMA_MIGRATIONS_TABLE not in inspect(isolated_engine).get_table_names()


def test_matching_version_passes_preflight_without_new_record(
    isolated_engine: Engine,
) -> None:
    initialize_database(isolated_engine)

    status = initialize_database(isolated_engine)

    assert status.state == SCHEMA_STATUS_CURRENT
    with isolated_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(SchemaMigration)) == 1


def test_matching_version_allows_application_lifespan() -> None:
    with TestClient(app):
        assert app.state.schema_status.state == SCHEMA_STATUS_CURRENT
        assert app.state.schema_status.database_version == CURRENT_SCHEMA_VERSION


def test_higher_database_version_refuses_startup(isolated_engine: Engine) -> None:
    initialize_database(isolated_engine)
    _set_isolated_version(isolated_engine, CURRENT_SCHEMA_VERSION + 1)

    with pytest.raises(SchemaVersionError) as exc_info:
        initialize_database(isolated_engine)

    assert exc_info.value.code == "application_outdated"
    assert "startup was refused" in str(exc_info.value)
    assert "Back up the database" in str(exc_info.value)
    with isolated_engine.connect() as connection:
        assert connection.scalar(select(SchemaMigration.version)) == (
            CURRENT_SCHEMA_VERSION + 1
        )


def test_application_lifespan_refuses_higher_database_version() -> None:
    with SessionLocal() as db:
        row = db.scalar(select(SchemaMigration))
        assert row is not None
        row.version = CURRENT_SCHEMA_VERSION + 1
        db.commit()

    try:
        with pytest.raises(SchemaVersionError) as exc_info:
            with TestClient(app):
                pass
    finally:
        with SessionLocal() as db:
            row = db.scalar(select(SchemaMigration))
            assert row is not None
            row.version = CURRENT_SCHEMA_VERSION
            db.commit()

    assert exc_info.value.code == "application_outdated"


def test_lower_database_version_reports_upgrade_without_migrating(
    isolated_engine: Engine,
) -> None:
    initialize_database(isolated_engine)
    lower_version = CURRENT_SCHEMA_VERSION - 1
    _set_isolated_version(isolated_engine, lower_version)

    status = initialize_database(isolated_engine)

    assert status.state == SCHEMA_STATUS_UPGRADE_REQUIRED
    assert status.database_version == lower_version
    with isolated_engine.connect() as connection:
        rows = connection.execute(select(SchemaMigration.version)).scalars().all()
    assert rows == [lower_version]


def test_initialization_failure_does_not_leave_version_record(
    isolated_engine: Engine,
) -> None:
    def fail_baseline_insert(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        if statement.lstrip().upper().startswith("INSERT INTO SCHEMA_MIGRATIONS"):
            raise RuntimeError("simulated registration failure")

    event.listen(isolated_engine, "before_cursor_execute", fail_baseline_insert)
    try:
        with pytest.raises(SchemaVersionError) as exc_info:
            initialize_database(isolated_engine)
    finally:
        event.remove(isolated_engine, "before_cursor_execute", fail_baseline_insert)

    assert exc_info.value.code == "initialization_failed"
    if SCHEMA_MIGRATIONS_TABLE in inspect(isolated_engine).get_table_names():
        with isolated_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM schema_migrations")) == 0


def test_empty_version_table_is_not_blindly_registered(
    isolated_engine: Engine,
) -> None:
    Base.metadata.create_all(bind=isolated_engine)

    with pytest.raises(SchemaVersionError) as exc_info:
        initialize_database(isolated_engine)

    assert exc_info.value.code == "version_unknown"
    with isolated_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(SchemaMigration)) == 0


def test_schema_version_is_unique(isolated_engine: Engine) -> None:
    initialize_database(isolated_engine)

    with pytest.raises(IntegrityError):
        with isolated_engine.begin() as connection:
            connection.execute(
                SchemaMigration.__table__.insert().values(
                    version=CURRENT_SCHEMA_VERSION,
                    name="duplicate",
                )
            )


def test_settings_schema_status_requires_login(client: TestClient) -> None:
    unauthenticated = client.get("/settings", follow_redirects=False)
    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"] == "/login"


def test_settings_schema_status_is_read_only(auth_client: TestClient) -> None:
    before = _global_schema_row()
    response = auth_client.get("/settings?schema_version=999")
    rejected_post = auth_client.post(
        "/settings",
        data={"schema_version": "999"},
        follow_redirects=True,
    )
    missing_endpoint = auth_client.post("/settings/schema-version")

    assert response.status_code == 200
    assert "数据库版本状态" in response.text
    assert "当前应用 schema 版本" in response.text
    assert "当前数据库 schema 版本" in response.text
    assert "正常" in response.text
    assert "升级前先导出 JSON 备份" in response.text
    assert 'name="schema_version"' not in response.text
    assert "/settings/schema-version" not in response.text
    assert rejected_post.status_code == 200
    assert "设置项无效" in rejected_post.text
    assert missing_endpoint.status_code in {404, 405}
    assert _global_schema_row() == before


def test_settings_page_displays_all_non_current_schema_states(
    auth_client: TestClient,
) -> None:
    with SessionLocal() as db:
        row = db.scalar(select(SchemaMigration))
        assert row is not None
        row.version = CURRENT_SCHEMA_VERSION - 1
        db.commit()
    assert "需要升级" in auth_client.get("/settings").text

    with SessionLocal() as db:
        row = db.scalar(select(SchemaMigration))
        assert row is not None
        row.version = CURRENT_SCHEMA_VERSION + 1
        db.commit()
    assert "应用过旧" in auth_client.get("/settings").text

    with SessionLocal() as db:
        db.query(SchemaMigration).delete()
        db.commit()
    unknown_response = auth_client.get("/settings")
    assert unknown_response.status_code == 200
    assert "无法确认" in unknown_response.text
    assert get_schema_status(engine).state == SCHEMA_STATUS_UNKNOWN


def test_schema_status_copy_is_available_in_english(auth_client: TestClient) -> None:
    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/settings"},
    )

    response = auth_client.get("/settings")

    assert response.status_code == 200
    assert "Database Schema Status" in response.text
    assert "Application Schema Version" in response.text
    assert "Database Schema Version" in response.text
    assert "Export a JSON backup before upgrading" in response.text
