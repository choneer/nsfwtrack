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
    default_zuidapi_fixture_root,
)
from app.providers.zuidapi.parse import parse_maccms_vod_payload
from app.source_adapters.registry import PRODUCTION_ENDPOINT_REGISTRY
from app.source_search import PRODUCTION_SEARCH_PACKAGES, build_production_search_service


def test_app_version_is_1_5_0() -> None:
    assert create_app().version == "1.5.0"


def test_nsfwpro_factory_keys_mapped_and_catalog_listed() -> None:
    assert set(NSFWPRO_FACTORY_KEY_MAP) == {
        "javdb-metadata",
        "jiuse-vod",
        "zuidapi-vod",
    }
    expected = nsfwpro_factory_provider_keys()
    assert expected == {"javdb_metadata", "jiuse_vod", "zuidapi_vod"}

    search_keys = {p.provider_key for p in PRODUCTION_SEARCH_PACKAGES}
    assert expected.issubset(search_keys)

    listed = {
        d.provider_key for d in build_production_search_service().list_providers()
    }
    assert expected.issubset(listed)

    endpoint_keys = {p.provider_key for p in PRODUCTION_ENDPOINT_REGISTRY.providers}
    # PRODUCTION hosts only (jiuse remains TEST_FIXTURE offline)
    assert "javdb_metadata" in endpoint_keys
    assert "zuidapi_vod" in endpoint_keys


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_zuidapi_offline_search_and_detail() -> None:
    root = default_zuidapi_fixture_root()
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


def test_javdb_package_still_in_catalog() -> None:
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_SEARCH_PACKAGES)
