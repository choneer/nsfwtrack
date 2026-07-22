"""All nsfwpro factory Providers wired into nsfwtrack 1.5.0 catalogs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.main import create_app
from app.providers.jiuse.package_build import (
    build_jiuse_fixture_package,
    default_jiuse_fixture_root,
)
from app.providers.jiuse.parse import parse_jiuse_video_html
from app.providers.production_catalog import (
    NSFWPRO_FACTORY_KEY_MAP,
    nsfwpro_factory_provider_keys,
)
from app.providers.zuidapi.adapter import StaticJsonFetcher
from app.providers.zuidapi.package_build import (
    build_zuidapi_production_package,
)
from app.providers.zuidapi.parse import parse_maccms_vod_payload
from app.source_adapters.registry import PRODUCTION_ENDPOINT_REGISTRY
from app.source_search import PRODUCTION_SEARCH_PACKAGES, build_production_search_service


ROOT = Path(__file__).resolve().parents[1]
ZUIDAPI_FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "zuidapi"


def test_app_version_is_1_5_0() -> None:
    assert create_app().version == "1.5.0"


def test_nsfwpro_factory_keys_mapped_but_catalog_is_fail_closed() -> None:
    assert set(NSFWPRO_FACTORY_KEY_MAP) == {
        "javdb-metadata",
        "jiuse-vod",
        "zuidapi-vod",
    }
    expected = nsfwpro_factory_provider_keys()
    assert expected == {"javdb_metadata", "jiuse_vod", "zuidapi_vod"}

    assert PRODUCTION_SEARCH_PACKAGES == ()
    assert build_production_search_service().list_providers() == ()
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()


@pytest.mark.anyio
async def test_jiuse_offline_search_and_detail() -> None:
    package = build_jiuse_fixture_package(validate=True)
    adapter = package.adapter
    page = await adapter.search("Example", page=1, page_size=10)
    assert page.total >= 1
    assert page.items[0].identifier.provider_key == "jiuse_vod"
    detail = await adapter.detail("V-001")
    assert "Example" in detail.title or detail.identifier.external_id == "V-001"

    html = (default_jiuse_fixture_root() / "detail_V-001.html").read_text(
        encoding="utf-8"
    )
    raw = parse_jiuse_video_html(
        html,
        page_url="https://metadata.jiuse.invalid/video/view/V-001",
        approved_hosts={"metadata.jiuse.invalid", "cdn.jiuse.invalid"},
    )
    assert raw["video_id"] == "V-001"
    assert "m3u8" in raw["manifest_url"]


@pytest.mark.anyio
async def test_zuidapi_offline_search_and_detail() -> None:
    root = ZUIDAPI_FIXTURE_ROOT
    search = json.loads((root / "search-normal.json").read_text(encoding="utf-8"))
    detail = json.loads((root / "detail-normal.json").read_text(encoding="utf-8"))
    fetcher = StaticJsonFetcher(
        {
            "/api.php/provide/vod": search,
            "/api.php/provide/vod?ac=list&limit=10&pg=1&wd=Synthetic": search,
            "/api.php/provide/vod?ac=detail&ids=TEST-001": detail,
        }
    )
    package = build_zuidapi_production_package(fetcher=fetcher, validate=True)
    adapter = package.adapter
    page = await adapter.search("Synthetic", page=1, page_size=10)
    assert page.total >= 1
    assert page.items[0].identifier.external_id == "TEST-001"
    item = await adapter.detail("TEST-001")
    assert item.title == "Synthetic title"
    assert item.identifier.provider_key == "zuidapi_vod"

    parsed = parse_maccms_vod_payload(search)
    assert parsed["items"][0]["vod_id"] == "TEST-001"


def test_javdb_package_is_not_activated_by_default() -> None:
    assert PRODUCTION_SEARCH_PACKAGES == ()


def test_zuidapi_package_requires_explicit_fetcher() -> None:
    with pytest.raises(ValueError, match="controlled ZuidAPI fetcher"):
        build_zuidapi_production_package()
