"""Phase 6-R3 v1.3.0 release-candidate freeze invariants."""

from __future__ import annotations

import ast
from pathlib import Path

from app.acquisition.registry import (
    PRODUCTION_ACQUISITION_PACKAGES,
    build_production_acquisition_registry,
)
from app.main import app
from app.routers.source_search import router as source_search_router
from app.routers.tasks import router as tasks_router
from app.services.exporter import BACKUP_SCHEMA_V1, BACKUP_SCHEMA_V2
from app.services.schema_version import CURRENT_SCHEMA_VERSION
from app.source_adapters import PRODUCTION_ENDPOINT_REGISTRY
from app.source_search import (
    PRODUCTION_SEARCH_PACKAGES,
    build_production_search_service,
)


ROOT = Path(__file__).resolve().parents[1]


def _route_matrix(router: object) -> dict[str, set[str]]:
    actual: dict[str, set[str]] = {}
    for route in router.routes:  # type: ignore[attr-defined]
        assert route.path not in actual
        actual[route.path] = set(route.methods or ())
    return actual


def test_v1_3_0_candidate_versions_and_empty_production_catalogs() -> None:
    assert app.version == "1.5.0"
    assert CURRENT_SCHEMA_VERSION == 5
    assert BACKUP_SCHEMA_V1 == "nsfwtrack.backup.v1"
    assert BACKUP_SCHEMA_V2 == "nsfwtrack.backup.v2"
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_ENDPOINT_REGISTRY.providers)
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_SEARCH_PACKAGES)
    assert {p.provider_key for p in build_production_search_service().list_providers()} >= {"javdb_metadata", "comic_local_fixture"}
    assert any(p.provider_key == "comic_local_fixture" for p in PRODUCTION_ACQUISITION_PACKAGES)
    assert {p.provider_key for p in build_production_acquisition_registry().packages} >= {"javdb_metadata", "comic_local_fixture"}


def test_synthetic_adapters_cannot_enter_production_modules() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules = (node.module or "",)
            else:
                continue
            if any(module == "tests" or module.startswith("tests.") for module in modules):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_phase6_task_download_and_manual_update_route_matrix_is_frozen() -> None:
    assert _route_matrix(tasks_router) == {
        "/tasks": {"GET"},
        "/tasks/{task_id}": {"GET"},
        "/items/{item_id}/sources/{source_id}/check": {"POST"},
        "/items/{item_id}/sources/{source_id}/assets/check": {"POST"},
        "/tasks/{task_id}/update-preview": {"POST"},
        "/tasks/update-confirm": {"POST"},
        "/tasks/{task_id}/assets/{asset_id}/download-preview": {"POST"},
        "/tasks/download-confirm": {"POST"},
        "/tasks/{task_id}/start": {"POST"},
        "/tasks/{task_id}/resume": {"POST"},
        "/tasks/{task_id}/pause": {"POST"},
        "/tasks/{task_id}/cancel": {"POST"},
        "/tasks/{task_id}/retry": {"POST"},
        "/tasks/{task_id}/delete-history": {"POST"},
    }
    assert _route_matrix(source_search_router) == {
        "/source-search": {"GET"},
        "/source-search/search": {"POST"},
        "/source-search/detail": {"POST"},
        "/source-search/apply": {"POST"},
    }


def test_phase6_security_boundaries_remain_explicit() -> None:
    downloader = (ROOT / "app/acquisition/downloader.py").read_text(encoding="utf-8")
    task_service = (ROOT / "app/tasks/service.py").read_text(encoding="utf-8")
    source_update = (ROOT / "app/source_update/service.py").read_text(encoding="utf-8")
    task_router = (ROOT / "app/routers/tasks.py").read_text(encoding="utf-8")
    provider_web = (ROOT / "app/provider_apply/web.py").read_text(encoding="utf-8")

    assert "O_NOFOLLOW" in downloader
    assert "follow_symlinks=False" in downloader
    assert "lease_generation" in downloader
    assert "_verify_download_committed_state(" in downloader
    assert "expected_stage=\"durable_verified\"" in downloader
    assert ".scalar_subquery()" in task_service
    assert "statement.where(running_count < self.max_concurrency)" in task_service
    assert "OperationTask.lease_owner == owner" in task_service
    assert "lease_generation == generation" in task_service
    assert "BEGIN IMMEDIATE" in source_update
    assert "_verify_manual_update_state(" in source_update
    assert "expected_stage=\"committed_verified\"" in source_update
    assert 'response.headers["Cache-Control"] = "no-store"' in task_router
    assert "session_generation" in provider_web


def test_formal_release_documents_preserve_release_and_history_boundaries() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    plan = (ROOT / "PLAN.md").read_text(encoding="utf-8")
    migrations = (ROOT / "app/services/migrations.py").read_text(encoding="utf-8")
    assert "Current application version: `1.5.0` (Schema `5`)" in readme
    assert "v1.3.0" in readme
    assert "releases/tag/v1.3.0" in readme
    assert "Phase 6 = complete/frozen" in readme
    assert "Phase 6-R4 = released" in readme
    assert "v1.3.0 Tag = not created" not in readme
    assert "v1.3.0 Release = not created" not in readme
    assert changelog.startswith("# Changelog / 变更记录\n\n## Unreleased\n")
    assert "## [1.3.0] - 2026-07-21\n" in changelog
    assert "## [1.2.0] - 2026-07-20\n" in changelog
    assert "22781d3e5cd040d6d1def24f140b6725dc25c0db" in plan
    assert "fb7ba82e1da5dd54d270e35099909e698541732c" in plan
    assert "GitHub Release ID: 356757190" in plan
    assert "Schema 5 databases are intentionally rejected by stable v1.2.0" in migrations
