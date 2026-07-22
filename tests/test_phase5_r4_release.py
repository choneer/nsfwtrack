"""Phase 5-R4 formal-release invariants."""

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


def test_formal_release_versions_and_production_catalogs_are_frozen() -> None:
    assert app.version == "1.5.0"
    assert CURRENT_SCHEMA_VERSION == 5
    assert BACKUP_SCHEMA_V1 == "nsfwtrack.backup.v1"
    assert BACKUP_SCHEMA_V2 == "nsfwtrack.backup.v2"
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_ENDPOINT_REGISTRY.providers)
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_SEARCH_PACKAGES)
    assert {p.provider_key for p in build_production_search_service().list_providers()} >= {"javdb_metadata", "comic_local_fixture"}


def test_formal_release_source_search_route_matrix_is_exact() -> None:
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


def test_readme_records_the_formal_release_without_pending_candidate_copy() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Current application version: `1.5.0` (Schema `5`)" in readme
    assert "v1.3.0" in readme
    assert (
        "https://github.com/choneer/nsfwtrack/releases/tag/v1.3.0"
        in readme
    )
    assert "Phase 5-R4 formally released" in readme
    assert "Hermes acceptance: PASS" in readme
    for obsolete in (
        "Current release candidate:",
        "candidate is not tagged or released",
        "Hermes acceptance is pending",
        "R4 formal release remains pending",
    ):
        assert obsolete not in readme


def test_changelog_starts_with_empty_unreleased_then_v1_3_0_release() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert changelog.startswith(
        "# Changelog / 变更记录\n\n"
        "## Unreleased\n\n"
    )
    assert "## [1.2.0] - 2026-07-20\n" in changelog


def test_formal_release_document_anchors_are_consistent() -> None:
    for relative_path in (
        "PLAN.md",
        "REVIEW.md",
        "PROVIDER_CONTRACT.md",
        "docs/provider-research/provider-roadmap.md",
    ):
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "N5C = complete/frozen" in text
        assert "N6/N7 = not implemented" in text
        assert "R1 = PASS" in text
        assert "R2 = skipped" in text
        assert "R3 = frozen" in text
        assert "Hermes = PASS" in text
        assert "R4 = released" in text
        assert ("Production catalogs = empty" in text) or ("Production catalogs = populated (1.5.0)" in text)
        assert "N100 = not deployed" in text
