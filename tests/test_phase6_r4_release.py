"""Phase 6-R4 v1.3.0 formal-release invariants."""

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
    return {
        route.path: set(route.methods or ())
        for route in router.routes  # type: ignore[attr-defined]
    }


def test_v1_3_0_formal_release_runtime_and_catalogs_are_frozen() -> None:
    assert app.version == "1.3.0"
    assert CURRENT_SCHEMA_VERSION == 5
    assert BACKUP_SCHEMA_V1 == "nsfwtrack.backup.v1"
    assert BACKUP_SCHEMA_V2 == "nsfwtrack.backup.v2"
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    assert PRODUCTION_SEARCH_PACKAGES == ()
    assert build_production_search_service().list_providers() == ()
    assert PRODUCTION_ACQUISITION_PACKAGES == ()
    assert build_production_acquisition_registry().packages == ()


def test_phase6_routes_and_security_boundaries_remain_frozen() -> None:
    task_routes = _route_matrix(tasks_router)
    assert task_routes["/tasks"] == {"GET"}
    assert task_routes["/tasks/{task_id}"] == {"GET"}
    for path in (
        "/items/{item_id}/sources/{source_id}/check",
        "/items/{item_id}/sources/{source_id}/assets/check",
        "/tasks/{task_id}/update-preview",
        "/tasks/update-confirm",
        "/tasks/{task_id}/assets/{asset_id}/download-preview",
        "/tasks/download-confirm",
        "/tasks/{task_id}/start",
        "/tasks/{task_id}/resume",
        "/tasks/{task_id}/pause",
        "/tasks/{task_id}/cancel",
        "/tasks/{task_id}/retry",
        "/tasks/{task_id}/delete-history",
    ):
        assert task_routes[path] == {"POST"}
    assert _route_matrix(source_search_router) == {
        "/source-search": {"GET"},
        "/source-search/search": {"POST"},
        "/source-search/detail": {"POST"},
        "/source-search/apply": {"POST"},
    }

    downloader = (ROOT / "app/acquisition/downloader.py").read_text(encoding="utf-8")
    source_update = (ROOT / "app/source_update/service.py").read_text(encoding="utf-8")
    task_router = (ROOT / "app/routers/tasks.py").read_text(encoding="utf-8")
    assert "O_NOFOLLOW" in downloader
    assert "lease_generation" in downloader
    assert "_verify_download_committed_state(" in downloader
    assert "expected_stage=\"durable_verified\"" in downloader
    assert "BEGIN IMMEDIATE" in source_update
    assert "_verify_manual_update_state(" in source_update
    assert "expected_stage=\"committed_verified\"" in source_update
    assert 'response.headers["Cache-Control"] = "no-store"' in task_router


def test_synthetic_adapters_remain_tests_only() -> None:
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


def test_readme_records_v1_3_0_as_the_formal_latest_release() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Current application version: `1.3.0` (Schema `5`)" in readme
    assert "Latest stable release: `v1.3.0`" in readme
    assert "releases/tag/v1.3.0" in readme
    assert "Phase 6 = complete/frozen" in readme
    assert "Phase 6-R3 = frozen" in readme
    assert "Cloud RC diff review = PASS" in readme
    assert "Hermes acceptance = PASS" in readme
    assert "Phase 6-R4 = released" in readme
    assert "Production catalogs = empty" in readme
    assert "Published image = none" in readme
    assert "N100 = not deployed" in readme
    assert "Real Provider/Auth/Host/Credential/Content = none" in readme
    for obsolete in (
        "Application is the unreleased `1.3.0` release candidate",
        "v1.3.0 Tag = not created",
        "v1.3.0 Release = not created",
    ):
        assert obsolete not in readme


def test_formal_release_status_is_consistent_across_current_documents() -> None:
    for relative_path in ("README.md", "PLAN.md", "TASKS.md", "REVIEW.md"):
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for marker in (
            "Phase 6-R3 = frozen",
            "Cloud RC diff review = PASS",
            "Hermes acceptance = PASS",
            "Phase 6-R4 = released",
            "Production catalogs = empty",
            "Published image = none",
            "N100 = not deployed",
        ):
            assert marker in text


def test_changelog_archives_complete_phase6_and_preserves_history() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.startswith(
        "# Changelog / 变更记录\n\n"
        "## Unreleased\n\n"
        "## [1.3.0] - 2026-07-21\n\n"
        "### Added\n"
    )
    release = changelog.split("## [1.3.0] - 2026-07-21\n", 1)[1].split(
        "## [1.2.0] - 2026-07-20\n", 1
    )[0]
    for marker in (
        "unified persistent task model",
        "Session-bound signed Confirm",
        "directory-descriptor safe downloader",
        "manual ItemSource Check",
        "bilingual Task Center",
        "owner/generation/expiry/cancel",
        "independent post-commit proof",
    ):
        assert marker in release
    assert "## [1.2.0] - 2026-07-20\n" in changelog
    assert "## [1.1.0] - 2026-07-17\n" in changelog
