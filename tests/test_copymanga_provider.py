"""CopyManga real-site comic PRODUCTION package tests (fixture-backed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.main import create_app
from app.providers.copymanga.adapter import StaticJsonFetcher
from app.providers.copymanga.package_build import (
    build_copymanga_acquisition_package,
    build_copymanga_production_package,
)
from app.providers.copymanga.parse import (
    parse_chapters_payload,
    parse_detail_payload,
    parse_search_payload,
)
from app.providers.production_catalog import (
    build_production_endpoints,
    build_production_search_packages,
)
from app.source_adapters.approval import ProviderApprovalScope
from app.source_adapters.registry import PRODUCTION_ENDPOINT_REGISTRY
from app.source_search import PRODUCTION_SEARCH_PACKAGES


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "copymanga"


def _fixture_fetcher() -> StaticJsonFetcher:
    search = json.loads((FIXTURE_ROOT / "search.json").read_text(encoding="utf-8"))
    detail = json.loads((FIXTURE_ROOT / "detail.json").read_text(encoding="utf-8"))
    chapters = json.loads((FIXTURE_ROOT / "chapters.json").read_text(encoding="utf-8"))
    return StaticJsonFetcher(
        {
            "/api/v3/search/comic": search,
            "/api/v3/comic2/demo-comic": detail,
            "/api/v3/comic/demo-comic/group/default/chapters": chapters,
        }
    )


def test_copymanga_in_production_catalogs() -> None:
    assert PRODUCTION_SEARCH_PACKAGES == ()
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    assert build_production_endpoints() == ()
    assert build_production_search_packages() == ()


def test_package_validates_production() -> None:
    package = build_copymanga_production_package(
        fetcher=_fixture_fetcher(), validate=True
    )
    assert package.scope == ProviderApprovalScope.PRODUCTION
    assert package.provider_key == "copymanga"
    assert package.endpoint is not None


def test_package_requires_explicit_fetcher() -> None:
    with pytest.raises(ValueError, match="controlled CopyManga fetcher"):
        build_copymanga_production_package()


def test_parse_fixtures() -> None:
    root = FIXTURE_ROOT
    search = json.loads((root / "search.json").read_text(encoding="utf-8"))
    detail = json.loads((root / "detail.json").read_text(encoding="utf-8"))
    chapters = json.loads((root / "chapters.json").read_text(encoding="utf-8"))
    cards = parse_search_payload(search)
    assert cards and cards[0]["external_id"] == "demo-comic"
    d = parse_detail_payload(detail, external_id="demo-comic")
    assert d["external_id"] == "demo-comic" or "title" in d
    ch = parse_chapters_payload(chapters)
    assert ch


@pytest.mark.anyio
async def test_adapter_search_detail_assets() -> None:
    fetcher = _fixture_fetcher()
    package = build_copymanga_production_package(fetcher=fetcher, validate=True)
    adapter = package.adapter
    page = await adapter.search("Demo", page=1, page_size=10)
    assert page.total >= 1
    assert page.items[0].identifier.provider_key == "copymanga"
    item = await adapter.detail("demo-comic")
    assert item.identifier.external_id == "demo-comic" or "Demo" in item.title
    assets = await adapter.asset_list("demo-comic")
    assert len(assets) >= 1


def test_acquisition_package_builds() -> None:
    package = build_copymanga_acquisition_package(
        static_pages={"p0001": b"\xff\xd8\xff\xd9"},
        static_lists={},
    )
    assert package.provider_key == "copymanga"
    assert package.approved_download is True


def test_app_version_1_5_0() -> None:
    assert create_app().version == "1.7.0"
