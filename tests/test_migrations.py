from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text, update
from sqlalchemy.engine import Connection, Engine

import app.routers.pages as pages_router
from app.database import Base, SessionLocal, engine
from app.models import (
    AppSetting,
    Item,
    ItemSource,
    MediaIndexEntry,
    MediaIndexState,
    SchemaMigration,
)
from app.services.migrations import (
    MIGRATION_REGISTRY,
    MigrationCheck,
    MigrationError,
    MigrationPreview,
    MigrationRegistry,
    MigrationStep,
    apply_upgrade,
    build_upgrade_plan,
    preview_upgrade,
)
from app.services.schema_version import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_STATUS_UPGRADE_REQUIRED,
    initialize_database,
)


@pytest.fixture
def isolated_engine() -> Generator[Engine, None, None]:
    test_engine = create_engine("sqlite:///:memory:", future=True)
    try:
        yield test_engine
    finally:
        test_engine.dispose()


def _prepare_versioned_database(bind: Engine, version: int = 0) -> None:
    SchemaMigration.__table__.create(bind=bind)
    with bind.begin() as connection:
        connection.execute(
            SchemaMigration.__table__.insert().values(
                version=version,
                name=f"test-version-{version}",
            )
        )
        connection.execute(text("CREATE TABLE migration_probe (value INTEGER NOT NULL)"))
        connection.execute(text("INSERT INTO migration_probe (value) VALUES (0)"))


def _probe_value(bind: Engine) -> int:
    with bind.connect() as connection:
        value = connection.scalar(text("SELECT value FROM migration_probe"))
    assert value is not None
    return int(value)


def _versions(bind: Engine) -> list[int]:
    with bind.connect() as connection:
        return list(
            connection.execute(
                select(SchemaMigration.version).order_by(SchemaMigration.version)
            ).scalars()
        )


def _step(
    from_version: int,
    to_version: int,
    *,
    name: str | None = None,
    fail_apply: bool = False,
    fail_postcheck: bool = False,
    preview_write: str | None = None,
    create_table: str | None = None,
) -> MigrationStep:
    step_name = name or f"test-{from_version}-to-{to_version}"

    def preview(connection: Connection) -> MigrationPreview:
        if preview_write == "data":
            connection.execute(text("UPDATE migration_probe SET value = 999"))
        if preview_write == "schema":
            connection.execute(text("CREATE TABLE preview_forbidden (id INTEGER)"))
        return MigrationPreview(
            changes=(f"probe {from_version} -> {to_version}",),
            warnings=(f"warning-{step_name}",),
        )

    def precheck(connection: Connection) -> MigrationCheck:
        value = connection.scalar(text("SELECT value FROM migration_probe"))
        return MigrationCheck(
            passed=value == from_version,
            message=f"probe is {value}",
        )

    def apply(connection: Connection) -> None:
        connection.execute(
            text("UPDATE migration_probe SET value = :value"),
            {"value": to_version},
        )
        if create_table:
            connection.execute(text(f"CREATE TABLE {create_table} (id INTEGER)"))
        if fail_apply:
            raise RuntimeError("simulated migration failure")

    def postcheck(connection: Connection) -> MigrationCheck:
        value = connection.scalar(text("SELECT value FROM migration_probe"))
        return MigrationCheck(
            passed=value == to_version and not fail_postcheck,
            message=f"probe is {value}",
        )

    return MigrationStep(
        from_version=from_version,
        to_version=to_version,
        name=step_name,
        preview=preview,
        apply=apply,
        precheck=precheck,
        postcheck=postcheck,
    )


def test_production_registry_contains_continuous_schema_1_to_3_steps() -> None:
    assert [
        (step.from_version, step.to_version, step.name)
        for step in MIGRATION_REGISTRY.steps
    ] == [
        (1, 2, "create_item_sources"),
        (2, 3, "create_media_index"),
    ]
    assert CURRENT_SCHEMA_VERSION == 3


def test_production_schema_1_to_3_upgrade_preserves_items(
    isolated_engine: Engine,
) -> None:
    legacy_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name
        not in {"item_sources", "media_index_entries", "media_index_state"}
    ]
    Base.metadata.create_all(bind=isolated_engine, tables=legacy_tables)
    with isolated_engine.begin() as connection:
        connection.execute(
            SchemaMigration.__table__.insert().values(version=1, name="baseline")
        )
        connection.execute(Item.__table__.insert().values(title="Legacy item"))

    dry_run = preview_upgrade(isolated_engine, MIGRATION_REGISTRY)
    assert dry_run.can_upgrade
    assert dry_run.current_version == 1
    assert dry_run.target_version == 3
    assert dry_run.steps[0].name == "create_item_sources"
    assert dry_run.steps[1].name == "create_media_index"
    assert "item_sources" not in inspect(isolated_engine).get_table_names()
    assert "media_index_entries" not in inspect(isolated_engine).get_table_names()

    result = apply_upgrade(
        isolated_engine,
        MIGRATION_REGISTRY,
        backup_confirmed=True,
    )

    assert result.from_version == 1
    assert result.to_version == 3
    assert result.applied_steps == ("create_item_sources", "create_media_index")
    assert "item_sources" in inspect(isolated_engine).get_table_names()
    assert "media_index_entries" in inspect(isolated_engine).get_table_names()
    assert "media_index_state" in inspect(isolated_engine).get_table_names()
    with isolated_engine.connect() as connection:
        assert connection.scalar(select(Item.title)) == "Legacy item"
        latest_version = connection.scalar(
            select(SchemaMigration.version).order_by(SchemaMigration.version.desc())
        )
        assert latest_version == 3
        assert connection.scalar(select(MediaIndexEntry.id)) is None
        state = connection.execute(
            select(MediaIndexState.valid, MediaIndexState.stale_reason)
        ).one()
        assert state == (False, "never_scanned")
        connection.execute(
            ItemSource.__table__.insert().values(
                item_id=1,
                url="https://example.com",
                normalized_url="https://example.com/",
            )
        )


def test_production_schema_2_to_3_upgrade_preserves_business_data(
    isolated_engine: Engine,
) -> None:
    schema_2_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name not in {"media_index_entries", "media_index_state"}
    ]
    Base.metadata.create_all(bind=isolated_engine, tables=schema_2_tables)
    with isolated_engine.begin() as connection:
        connection.execute(
            SchemaMigration.__table__.insert().values(version=2, name="schema-2")
        )
        connection.execute(Item.__table__.insert().values(title="Schema 2 item"))
        connection.execute(
            ItemSource.__table__.insert().values(
                item_id=1,
                url="https://example.com/source",
                normalized_url="https://example.com/source",
            )
        )

    dry_run = preview_upgrade(isolated_engine, MIGRATION_REGISTRY)

    assert dry_run.can_upgrade
    assert [(step.from_version, step.to_version) for step in dry_run.steps] == [(2, 3)]
    assert "media_index_entries" not in inspect(isolated_engine).get_table_names()
    result = apply_upgrade(
        isolated_engine,
        MIGRATION_REGISTRY,
        backup_confirmed=True,
    )

    assert result.applied_steps == ("create_media_index",)
    with isolated_engine.connect() as connection:
        assert connection.scalar(select(Item.title)) == "Schema 2 item"
        assert connection.scalar(select(ItemSource.url)) == "https://example.com/source"
        assert connection.scalar(select(MediaIndexEntry.id)) is None
        assert connection.scalar(select(MediaIndexState.valid)) is False
        assert list(
            connection.execute(
                select(SchemaMigration.version).order_by(SchemaMigration.version)
            ).scalars()
        ) == [2, 3]


def test_production_schema_2_to_3_failure_rolls_back_tables_and_version(
    monkeypatch: pytest.MonkeyPatch,
    isolated_engine: Engine,
) -> None:
    schema_2_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name not in {"media_index_entries", "media_index_state"}
    ]
    Base.metadata.create_all(bind=isolated_engine, tables=schema_2_tables)
    with isolated_engine.begin() as connection:
        connection.execute(
            SchemaMigration.__table__.insert().values(version=2, name="schema-2")
        )
        connection.execute(Item.__table__.insert().values(title="Preserved"))

    def fail_state_table_create(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("simulated state-table DDL failure")

    monkeypatch.setattr(MediaIndexState.__table__, "create", fail_state_table_create)
    with pytest.raises(MigrationError) as exc_info:
        apply_upgrade(
            isolated_engine,
            MIGRATION_REGISTRY,
            backup_confirmed=True,
        )

    assert exc_info.value.code == "apply_failed"
    tables = set(inspect(isolated_engine).get_table_names())
    assert "media_index_entries" not in tables
    assert "media_index_state" not in tables
    with isolated_engine.connect() as connection:
        assert connection.scalar(select(Item.title)) == "Preserved"
        assert list(connection.execute(select(SchemaMigration.version)).scalars()) == [2]


@pytest.mark.parametrize(
    ("steps", "code"),
    [
        ((_step(0, 1), _step(0, 1, name="duplicate")), "duplicate_step"),
        ((_step(0, 1), _step(2, 3)), "registry_gap"),
        ((_step(0, 2),), "version_jump"),
        ((_step(1, 0),), "invalid_direction"),
        ((_step(0, 1), _step(1, 0, name="cycle")), "invalid_direction"),
    ],
)
def test_registry_rejects_invalid_paths(
    steps: tuple[MigrationStep, ...],
    code: str,
) -> None:
    with pytest.raises(MigrationError) as exc_info:
        MigrationRegistry(steps)

    assert exc_info.value.code == code


def test_current_version_needs_no_upgrade(isolated_engine: Engine) -> None:
    _prepare_versioned_database(isolated_engine, version=1)

    plan = build_upgrade_plan(
        isolated_engine,
        MigrationRegistry(),
        target_version=1,
    )

    assert plan.state == "current"
    assert plan.steps == ()
    assert not plan.can_preview


def test_low_version_resolves_continuous_path(isolated_engine: Engine) -> None:
    _prepare_versioned_database(isolated_engine)
    registry = MigrationRegistry((_step(0, 1), _step(1, 2)))

    plan = build_upgrade_plan(isolated_engine, registry, target_version=2)

    assert plan.state == "ready"
    assert [(step.from_version, step.to_version) for step in plan.steps] == [
        (0, 1),
        (1, 2),
    ]


def test_missing_path_and_higher_version_are_rejected(
    isolated_engine: Engine,
) -> None:
    _prepare_versioned_database(isolated_engine)
    missing = build_upgrade_plan(
        isolated_engine,
        MigrationRegistry((_step(1, 2),)),
        target_version=2,
    )
    assert missing.state == "missing_path"
    assert missing.error_code == "missing_path"

    with isolated_engine.begin() as connection:
        connection.execute(update(SchemaMigration).values(version=3))
    higher = build_upgrade_plan(
        isolated_engine,
        MigrationRegistry(),
        target_version=2,
    )
    assert higher.state == "application_outdated"
    assert higher.error_code == "downgrade_not_supported"


def test_database_version_is_read_before_path_resolution(
    isolated_engine: Engine,
) -> None:
    class TrackingRegistry(MigrationRegistry):
        def __init__(self) -> None:
            super().__init__()
            self.resolve_called = False

        def resolve(
            self,
            from_version: int,
            to_version: int,
        ) -> tuple[MigrationStep, ...]:
            self.resolve_called = True
            return super().resolve(from_version, to_version)

    registry = TrackingRegistry()

    plan = build_upgrade_plan(isolated_engine, registry, target_version=1)

    assert plan.state == "unknown"
    assert not registry.resolve_called


def test_lower_version_startup_does_not_require_latest_structure(
    isolated_engine: Engine,
) -> None:
    SchemaMigration.__table__.create(bind=isolated_engine)
    with isolated_engine.begin() as connection:
        connection.execute(
            SchemaMigration.__table__.insert().values(
                version=CURRENT_SCHEMA_VERSION - 1,
                name="old-structure",
            )
        )

    status = initialize_database(isolated_engine)

    assert status.state == SCHEMA_STATUS_UPGRADE_REQUIRED
    assert set(inspect(isolated_engine).get_table_names()) == {"schema_migrations"}


def test_preview_is_read_only_and_reports_order(isolated_engine: Engine) -> None:
    _prepare_versioned_database(isolated_engine)
    registry = MigrationRegistry((_step(0, 1), _step(1, 2)))
    before_tables = set(inspect(isolated_engine).get_table_names())

    report = preview_upgrade(isolated_engine, registry, target_version=2)

    assert report.can_upgrade
    assert report.state == "ready"
    assert _probe_value(isolated_engine) == 0
    assert _versions(isolated_engine) == [0]
    assert set(inspect(isolated_engine).get_table_names()) == before_tables
    assert [step.name for step in report.steps] == ["test-0-to-1", "test-1-to-2"]
    assert report.steps[0].precheck_state == "passed"
    assert report.steps[1].precheck_state == "deferred"


@pytest.mark.parametrize("write_kind", ["data", "schema"])
def test_preview_blocks_write_attempts(
    isolated_engine: Engine,
    write_kind: str,
) -> None:
    _prepare_versioned_database(isolated_engine)
    registry = MigrationRegistry((_step(0, 1, preview_write=write_kind),))

    report = preview_upgrade(isolated_engine, registry, target_version=1)

    assert not report.can_upgrade
    assert report.errors == ("preview_failed",)
    assert _probe_value(isolated_engine) == 0
    assert _versions(isolated_engine) == [0]
    assert "preview_forbidden" not in inspect(isolated_engine).get_table_names()


def test_apply_requires_backup_confirmation(isolated_engine: Engine) -> None:
    _prepare_versioned_database(isolated_engine)

    with pytest.raises(MigrationError) as exc_info:
        apply_upgrade(
            isolated_engine,
            MigrationRegistry((_step(0, 1),)),
            backup_confirmed=False,
            target_version=1,
        )

    assert exc_info.value.code == "backup_confirmation_required"
    assert _probe_value(isolated_engine) == 0
    assert _versions(isolated_engine) == [0]


def test_apply_rejects_downgrade_without_changes(isolated_engine: Engine) -> None:
    _prepare_versioned_database(isolated_engine, version=2)

    with pytest.raises(MigrationError) as exc_info:
        apply_upgrade(
            isolated_engine,
            MigrationRegistry(),
            backup_confirmed=True,
            target_version=1,
        )

    assert exc_info.value.code == "downgrade_not_supported"
    assert _probe_value(isolated_engine) == 0
    assert _versions(isolated_engine) == [2]


def test_two_step_failure_rolls_back_chain_schema_and_versions(
    isolated_engine: Engine,
) -> None:
    _prepare_versioned_database(isolated_engine)
    registry = MigrationRegistry(
        (
            _step(0, 1, create_table="migration_step_one"),
            _step(1, 2, fail_apply=True, create_table="migration_step_two"),
        )
    )

    with pytest.raises(MigrationError) as exc_info:
        apply_upgrade(
            isolated_engine,
            registry,
            backup_confirmed=True,
            target_version=2,
        )

    assert exc_info.value.code == "apply_failed"
    assert _probe_value(isolated_engine) == 0
    assert _versions(isolated_engine) == [0]
    tables = set(inspect(isolated_engine).get_table_names())
    assert "migration_step_one" not in tables
    assert "migration_step_two" not in tables


def test_postcheck_failure_rolls_back_change_and_version(
    isolated_engine: Engine,
) -> None:
    _prepare_versioned_database(isolated_engine)
    registry = MigrationRegistry(
        (_step(0, 1, fail_postcheck=True, create_table="failed_postcheck"),)
    )

    with pytest.raises(MigrationError) as exc_info:
        apply_upgrade(
            isolated_engine,
            registry,
            backup_confirmed=True,
            target_version=1,
        )

    assert exc_info.value.code == "postcheck_failed"
    assert _probe_value(isolated_engine) == 0
    assert _versions(isolated_engine) == [0]
    assert "failed_postcheck" not in inspect(isolated_engine).get_table_names()


def test_successful_apply_records_each_version_atomically(
    isolated_engine: Engine,
) -> None:
    _prepare_versioned_database(isolated_engine)
    registry = MigrationRegistry((_step(0, 1), _step(1, 2)))

    result = apply_upgrade(
        isolated_engine,
        registry,
        backup_confirmed=True,
        target_version=2,
    )

    assert result.from_version == 0
    assert result.to_version == 2
    assert result.applied_steps == ("test-0-to-1", "test-1-to-2")
    assert _probe_value(isolated_engine) == 2
    assert _versions(isolated_engine) == [0, 1, 2]


@pytest.fixture
def route_registry(monkeypatch: pytest.MonkeyPatch) -> Generator[MigrationRegistry, None, None]:
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS migration_probe"))
        connection.execute(text("CREATE TABLE migration_probe (value INTEGER NOT NULL)"))
        connection.execute(text("INSERT INTO migration_probe (value) VALUES (0)"))
        connection.execute(
            update(SchemaMigration).values(version=0, name="route-test-version")
        )
    registry = MigrationRegistry(
        (
            _step(0, 1, name="route-test-upgrade"),
            _step(1, 2, name="route-test-upgrade-2"),
            _step(2, 3, name="route-test-upgrade-3"),
        )
    )
    monkeypatch.setattr(pages_router, "MIGRATION_REGISTRY", registry)
    try:
        yield registry
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS migration_probe"))


def _global_probe_and_versions() -> tuple[int, list[int]]:
    return _probe_value(engine), _versions(engine)


def test_upgrade_routes_require_login(client: TestClient) -> None:
    assert client.get("/schema-upgrade", follow_redirects=False).status_code == 303
    assert (
        client.post("/schema-upgrade/preview", follow_redirects=False).status_code
        == 303
    )
    assert client.post("/schema-upgrade/apply", follow_redirects=False).status_code == 303


def test_current_upgrade_page_is_read_only(auth_client: TestClient) -> None:
    before = _versions(engine)

    response = auth_client.get("/schema-upgrade")
    preview_response = auth_client.post("/schema-upgrade/preview")

    assert response.status_code == 200
    assert "数据库升级" in response.text
    assert "当前数据库已是应用支持的版本" in response.text
    assert preview_response.status_code == 200
    assert _versions(engine) == before


def test_get_and_preview_do_not_execute_migration(
    auth_client: TestClient,
    route_registry: MigrationRegistry,
) -> None:
    del route_registry
    get_response = auth_client.get("/schema-upgrade")
    preview_response = auth_client.post(
        "/schema-upgrade/preview",
        data={
            "sql": "DROP TABLE items",
            "table": "items",
            "target_version": "999",
        },
    )
    get_apply = auth_client.get(
        "/schema-upgrade/apply?confirm=1&backup_confirmed=1",
        follow_redirects=False,
    )
    get_preview = auth_client.get(
        "/schema-upgrade/preview",
        follow_redirects=False,
    )

    assert get_response.status_code == 200
    assert preview_response.status_code == 200
    assert "升级 dry-run" in preview_response.text
    assert "route-test-upgrade" in preview_response.text
    assert 'name="target_version"' not in preview_response.text
    assert 'name="sql"' not in preview_response.text
    assert 'name="table"' not in preview_response.text
    assert 'name="backup_confirmed"' in preview_response.text
    assert 'name="confirm"' in preview_response.text
    assert "data-confirm-message" in preview_response.text
    assert get_apply.status_code == 405
    assert get_preview.status_code == 405
    assert _global_probe_and_versions() == (0, [0])
    assert "items" in inspect(engine).get_table_names()


def test_upgrade_page_does_not_require_latest_settings_table(
    auth_client: TestClient,
    route_registry: MigrationRegistry,
) -> None:
    del route_registry
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE app_settings"))

    response = auth_client.get("/schema-upgrade")
    preview_response = auth_client.post("/schema-upgrade/preview")

    assert response.status_code == 200
    assert preview_response.status_code == 200
    assert "route-test-upgrade" in preview_response.text
    assert _global_probe_and_versions() == (0, [0])


def test_standard_apply_requires_confirm_and_backup_then_uses_code_path(
    auth_client: TestClient,
    route_registry: MigrationRegistry,
) -> None:
    del route_registry
    missing_confirm = auth_client.post(
        "/schema-upgrade/apply",
        data={"backup_confirmed": "1"},
        follow_redirects=True,
    )
    assert "缺少手动确认" in missing_confirm.text
    assert _global_probe_and_versions() == (0, [0])

    missing_backup = auth_client.post(
        "/schema-upgrade/apply",
        data={"confirm": "1"},
        follow_redirects=True,
    )
    assert "必须确认已了解并完成升级前备份" in missing_backup.text
    assert _global_probe_and_versions() == (0, [0])

    applied = auth_client.post(
        "/schema-upgrade/apply",
        data={
            "confirm": "1",
            "backup_confirmed": "1",
            "sql": "DROP TABLE items",
            "table": "items",
            "target_version": "999",
        },
        follow_redirects=True,
    )
    assert "显式升级到 3" in applied.text
    assert _global_probe_and_versions() == (3, [0, 1, 2, 3])
    assert "items" in inspect(engine).get_table_names()


def test_strict_apply_requires_exact_confirm_text(
    auth_client: TestClient,
    route_registry: MigrationRegistry,
) -> None:
    del route_registry
    with SessionLocal() as db:
        db.add(AppSetting(key="danger_confirmation_mode", value="strict"))
        db.commit()

    preview_response = auth_client.post("/schema-upgrade/preview")
    assert "data-strict-confirm-message" in preview_response.text

    missing = auth_client.post(
        "/schema-upgrade/apply",
        data={"confirm": "1", "backup_confirmed": "1"},
        follow_redirects=True,
    )
    wrong = auth_client.post(
        "/schema-upgrade/apply",
        data={
            "confirm": "1",
            "backup_confirmed": "1",
            "confirmation_text": "confirm",
        },
        follow_redirects=True,
    )
    assert "严格模式要求输入固定文本 CONFIRM" in missing.text
    assert "严格模式要求输入固定文本 CONFIRM" in wrong.text
    assert _global_probe_and_versions() == (0, [0])

    applied = auth_client.post(
        "/schema-upgrade/apply",
        data={
            "confirm": "1",
            "backup_confirmed": "1",
            "confirmation_text": "CONFIRM",
        },
        follow_redirects=True,
    )
    assert "显式升级到 3" in applied.text
    assert _global_probe_and_versions() == (3, [0, 1, 2, 3])


def test_upgrade_page_copy_is_available_in_english(auth_client: TestClient) -> None:
    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/schema-upgrade"},
    )

    response = auth_client.get("/schema-upgrade")

    assert response.status_code == 200
    assert "Database Upgrade" in response.text
    assert "Startup, GET, and dry-run never upgrade" in response.text
