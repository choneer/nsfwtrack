"""Phase 5-R1 static integration-freeze invariants."""

from __future__ import annotations

import ast
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


def test_release_candidate_constants_and_production_catalogs_remain_frozen() -> None:
    assert app.version == "1.2.0"
    assert CURRENT_SCHEMA_VERSION == 5
    assert BACKUP_SCHEMA_V1 == "nsfwtrack.backup.v1"
    assert BACKUP_SCHEMA_V2 == "nsfwtrack.backup.v2"
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    assert PRODUCTION_SEARCH_PACKAGES == ()
    assert build_production_search_service().list_providers() == ()


def test_source_search_route_method_matrix_is_explicit() -> None:
    expected = {
        "/source-search": {"GET"},
        "/source-search/search": {"POST"},
        "/source-search/detail": {"POST"},
        "/source-search/apply": {"POST"},
    }
    actual: dict[str, set[str]] = {}
    for route in source_search_router.routes:
        path = getattr(route, "path", None)
        if path in expected:
            assert path not in actual
            actual[path] = set(route.methods or ())
    assert actual == expected


def test_production_modules_do_not_import_test_fixtures() -> None:
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


def test_release_documentation_preserves_the_r1_freeze_state() -> None:
    for relative_path in (
        "PLAN.md",
        "REVIEW.md",
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
        assert "Production catalogs = empty" in text


def test_source_search_module_describes_the_complete_web_flow() -> None:
    path = ROOT / "app/routers/source_search.py"
    module_docstring = ast.get_docstring(ast.parse(path.read_bytes(), filename=str(path)))
    assert module_docstring is not None
    assert "read-only" not in module_docstring.lower()
    for term in ("Search", "Detail", "Preview", "Confirm"):
        assert term in module_docstring
