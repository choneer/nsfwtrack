"""Phase 5-R3 release-candidate freeze invariants."""

from __future__ import annotations

from pathlib import Path

from app.main import app
from app.routers.source_search import router as source_search_router
from app.services.exporter import BACKUP_SCHEMA_V1, BACKUP_SCHEMA_V2
from app.services.schema_version import CURRENT_SCHEMA_VERSION
from app.source_adapters import PRODUCTION_ENDPOINT_REGISTRY
from app.source_search import (
    PRODUCTION_SEARCH_PACKAGES,
    build_production_search_service,
)


ROOT = Path(__file__).resolve().parents[1]


def test_release_candidate_versions_and_production_catalogs_are_frozen() -> None:
    assert app.version == "1.2.0"
    assert CURRENT_SCHEMA_VERSION == 4
    assert BACKUP_SCHEMA_V1 == "nsfwtrack.backup.v1"
    assert BACKUP_SCHEMA_V2 == "nsfwtrack.backup.v2"
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    assert PRODUCTION_SEARCH_PACKAGES == ()
    assert build_production_search_service().list_providers() == ()


def test_release_candidate_source_search_route_matrix_is_exact() -> None:
    expected = {
        "/source-search": {"GET"},
        "/source-search/search": {"POST"},
        "/source-search/detail": {"POST"},
        "/source-search/apply": {"POST"},
    }
    actual: dict[str, set[str]] = {}
    for route in source_search_router.routes:
        if route.path in expected:
            assert route.path not in actual
            actual[route.path] = set(route.methods or ())
    assert actual == expected


def test_release_candidate_documentation_state_is_explicit() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Latest stable release: `v1.1.0`" in readme
    assert "Current release candidate: `v1.2.0`" in readme
    assert "R3 candidate is not tagged or released" in readme
    assert "Hermes acceptance is pending" in readme

    for relative_path in (
        "PLAN.md",
        "REVIEW.md",
        "PROVIDER_CONTRACT.md",
        "docs/provider-research/provider-roadmap.md",
    ):
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "R1 = PASS" in text
        assert "R2 = skipped" in text
        assert "N5C = complete/frozen" in text
        assert "N6/N7 = not implemented" in text
        assert "R3 = Application 1.2.0 release candidate" in text
        assert "Hermes = not called" in text
        assert "R4 = not released" in text
        assert "Production catalogs = empty" in text


def test_changelog_remains_unreleased_and_has_no_v1_2_0_release_section() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.startswith("# Changelog / 变更记录\n\n## Unreleased\n")
    assert "## [1.2.0] -" not in changelog
