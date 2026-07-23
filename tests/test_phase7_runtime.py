"""Phase 7 runtime registry, Schema 6, diagnostics, and offline HLS coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.main import create_app
from app.cookiecloud.client import CookieCloudError, remove_cookie_header, save_cookie_header
from app.models import Base, ProviderRuntimeState, SchemaMigration
from app.provider_runtime.service import (
    ProviderRuntimeError,
    ProviderRuntimeErrorCode,
    ProviderRuntimeRegistry,
)
from app.services.migrations import (
    MIGRATION_REGISTRY,
    MigrationCheck,
    MigrationError,
    MigrationRegistry,
    MigrationStep,
    apply_upgrade,
)


@pytest.fixture
def isolated_engine() -> Engine:
    engine = create_engine("sqlite:///:memory:")
    try:
        yield engine
    finally:
        engine.dispose()


def _missing_cookie() -> str:
    from app.providers.javdb.session import SessionCookieError

    raise SessionCookieError("session is unavailable")


def test_schema_5_to_6_runtime_migration_is_atomic_on_postcheck_failure(
    isolated_engine: Engine,
) -> None:
    Base.metadata.create_all(bind=isolated_engine)
    with isolated_engine.begin() as connection:
        ProviderRuntimeState.__table__.drop(bind=connection)
        connection.execute(SchemaMigration.__table__.insert().values(version=5, name="schema-5"))

    original = MIGRATION_REGISTRY.steps[-1]
    failing = MigrationStep(
        from_version=original.from_version,
        to_version=original.to_version,
        name=original.name,
        preview=original.preview,
        apply=original.apply,
        precheck=original.precheck,
        postcheck=lambda _connection: MigrationCheck(False, "forced postcheck failure"),
    )
    with pytest.raises(MigrationError, match="postcheck_failed"):
        apply_upgrade(
            isolated_engine,
            MigrationRegistry((failing,)),
            backup_confirmed=True,
            target_version=6,
        )

    assert ProviderRuntimeState.__tablename__ not in inspect(isolated_engine).get_table_names()
    with isolated_engine.connect() as connection:
        assert connection.scalar(select(SchemaMigration.version)) == 5


def test_runtime_configuration_enable_health_and_optimistic_fencing(
    isolated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.provider_runtime.service.load_javdb_session_cookie", _missing_cookie)
    Base.metadata.create_all(bind=isolated_engine)
    with Session(isolated_engine) as db:
        registry = ProviderRuntimeRegistry(db)
        registry.sync_known_states()
        db.commit()

        initial = registry.get("zuidapi_vod")
        assert initial.enabled is False
        assert initial.configuration_status == "not_configured"

        configured = registry.save_configuration(
            "zuidapi_vod", egress_profile="direct", expected_version=initial.optimistic_version
        )
        enabled = registry.set_enabled(
            "zuidapi_vod", enabled=True, expected_version=configured.optimistic_version
        )
        plan = registry.prepare_health_check(
            "zuidapi_vod", expected_version=enabled.optimistic_version
        )
        assert plan.blocker_code is None
        ready = registry.complete_health_check(
            "zuidapi_vod",
            expected_version=enabled.optimistic_version,
            success=True,
        )
        db.commit()

        assert ready.runtime_status == "ready"
        assert ready.last_success_at is not None
        assert ready.session_status == "not_required"
        with pytest.raises(ProviderRuntimeError) as error:
            registry.set_enabled(
                "zuidapi_vod", enabled=False, expected_version=enabled.optimistic_version
            )
        assert error.value.code is ProviderRuntimeErrorCode.CONCURRENT_UPDATE


def test_runtime_projects_expired_cookie_session_without_exposing_cookie_data(
    isolated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.provider_runtime.service.load_javdb_session_cookie", _missing_cookie)
    Base.metadata.create_all(bind=isolated_engine)
    with Session(isolated_engine) as db:
        registry = ProviderRuntimeRegistry(db)
        registry.sync_known_states()
        expired = registry.record_session_import(
            "javdb_metadata",
            available=True,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.commit()

    assert expired.session_status == "expired"
    assert expired.session_expires_at is not None


def test_provider_and_diagnostics_pages_are_authenticated_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.provider_runtime.service.load_javdb_session_cookie", _missing_cookie)
    with TestClient(create_app()) as client:
        assert client.get("/providers", follow_redirects=False).status_code == 303
        assert client.get("/api/diagnostics/report").status_code == 401
        assert client.post("/api/auth/login", json={"password": "test-password"}).status_code == 200

        providers = client.get("/providers")
        report = client.get("/api/diagnostics/report")
        playback = client.get("/playback")

    assert providers.status_code == 200
    assert "javdb_metadata" in providers.text
    assert report.status_code == 200
    assert report.headers["cache-control"] == "no-store"
    payload = report.json()["report"]
    assert payload["application_version"] == "1.6.0"
    assert payload["schema"]["application_version"] == 6
    assert all("path" not in entry for entry in payload["providers"])
    assert "cookie=" not in report.text.lower()
    assert playback.status_code == 200
    assert "HLS" in playback.text


def test_cookie_session_delete_is_scoped_to_a_regular_local_file(tmp_path) -> None:
    cookie_file = tmp_path / "session.cookie"
    save_cookie_header(cookie_file, "session=temporary")
    assert remove_cookie_header(cookie_file) is True
    assert remove_cookie_header(cookie_file) is False

    target = tmp_path / "target.cookie"
    target.write_text("session=target", encoding="utf-8")
    link = tmp_path / "link.cookie"
    link.symlink_to(target)
    with pytest.raises(CookieCloudError, match="regular local file"):
        remove_cookie_header(link)
    assert target.read_text(encoding="utf-8") == "session=target"
