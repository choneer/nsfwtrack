"""Phases B runtime / C / D: packages, live adapter (static fetch), acquisition."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.acquisition.contracts import AssetDownloadDescriptor
from app.providers.comic.package_build import (
    build_comic_acquisition_package,
    build_comic_fixture_package,
    default_comic_fixture_root,
)
from app.providers.javdb.fetch import StaticHtmlFetcher
from app.providers.javdb.live_adapter import JavDBLiveVideoMetadataAdapter
from app.providers.javdb.package_build import (
    build_javdb_acquisition_package,
    build_javdb_production_package,
)
from app.providers.javdb.session import SessionCookieError
from app.providers.javdb.production import JAVDB_PRODUCTION_APPROVAL
from app.providers.opt_in_catalog import (
    build_opt_in_search_packages,
    build_opt_in_search_service,
    opt_in_enabled,
)
from app.source_adapters import (
    validate_approval_for_activation,
)
from app.source_adapters.contracts import ProviderOperation, SourceAssetKind
from app.source_adapters.package import validate_provider_package
from app.source_adapters.registry import PRODUCTION_ENDPOINT_REGISTRY
from app.source_search import (
    PRODUCTION_SEARCH_PACKAGES,
    build_production_search_service,
)
from app.source_adapters.contracts import ProviderOperation as PO


FIXTURE_HTML = Path(__file__).parent / "fixtures" / "javdb_metadata"


@pytest.mark.anyio
async def test_javdb_live_adapter_search_detail_assets_static() -> None:
    fetcher = StaticHtmlFetcher(
        {
            "/search": (FIXTURE_HTML / "search_normal.html").read_text(encoding="utf-8"),
            "/v/RM29z": (FIXTURE_HTML / "detail_RM29z.html").read_text(encoding="utf-8"),
        }
    )
    adapter = JavDBLiveVideoMetadataAdapter(fetcher)
    page = await adapter.search("SSIS", page=1, page_size=10)
    assert page.total >= 1
    assert page.items[0].identifier.external_id
    detail = await adapter.detail("RM29z")
    assert detail.title
    assets = await adapter.asset_list("RM29z")
    # cover and/or previews depending on fixture
    assert isinstance(assets, tuple)


def test_javdb_production_package_validates_with_static_fetcher() -> None:
    package = build_javdb_production_package(
        fetcher=StaticHtmlFetcher(
            {
                "/search": (FIXTURE_HTML / "search_normal.html").read_text(
                    encoding="utf-8"
                ),
                "/v/RM29z": (FIXTURE_HTML / "detail_RM29z.html").read_text(
                    encoding="utf-8"
                ),
            }
        ),
        validate=True,
    )
    validate_provider_package(package)
    assert package.provider_key == "javdb_metadata"
    assert ProviderOperation.ASSET_LIST in package.binding.operations
    validate_approval_for_activation(
        package.approval, package.capabilities, package.endpoint
    )
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    assert PRODUCTION_SEARCH_PACKAGES == ()
    assert build_production_search_service().list_providers() == ()


def test_javdb_production_package_requires_explicit_fetcher() -> None:
    with pytest.raises(SessionCookieError, match="controlled JavDB fetcher"):
        build_javdb_production_package()


@pytest.mark.anyio
async def test_javdb_optional_download_acquisition() -> None:
    desc = AssetDownloadDescriptor(
        provider_key="javdb_metadata",
        external_id="RM29z",
        asset_id="cover.jpg",
        kind=SourceAssetKind.COVER,
        display_name="cover",
        suggested_filename="cover.jpg",
        mime_type="image/jpeg",
        expected_bytes=4,
        requires_auth=False,
        resume_supported=True,
    )
    package = build_javdb_acquisition_package(
        cookie="session=test",
        static_bodies={"cover.jpg": b"\xff\xd8\xff\xd9"},
        static_lists={"RM29z": (desc,)},
    )
    assert package.approved_download is True
    listed = await package.adapter.list_assets("RM29z")
    assert listed and listed[0].asset_id == "cover.jpg"
    opened = await package.adapter.open_asset(
        "RM29z", "cover.jpg", offset=0, timeout_seconds=5
    )
    chunks = []
    async for part in opened.chunks:
        chunks.append(part)
    assert b"".join(chunks) == b"\xff\xd8\xff\xd9"


def test_comic_fixture_package_and_download() -> None:
    package = build_comic_fixture_package(validate=True)
    assert package.scope.value == "test_fixture"
    assert package.provider_key == "comic_local_fixture"
    root = default_comic_fixture_root()
    assert (root / "demo_book").is_dir()


@pytest.mark.anyio
async def test_comic_acquisition_downloads_local_pages() -> None:
    package = build_comic_acquisition_package()
    assert package.approved_download is True
    assets = await package.adapter.list_assets("demo_book")
    assert len(assets) >= 1
    first = assets[0]
    opened = await package.adapter.open_asset(
        "demo_book", first.asset_id, offset=0, timeout_seconds=5
    )
    data = b""
    async for chunk in opened.chunks:
        data += chunk
    assert data[:2] == b"\xff\xd8" or len(data) > 0


def test_opt_in_catalog_default_off() -> None:
    assert opt_in_enabled({}) is False
    service = build_opt_in_search_service(env={})
    assert service.list_providers() == ()


def test_legacy_opt_in_catalog_remains_fail_closed() -> None:
    assert build_opt_in_search_packages() == ()
    assert build_opt_in_search_service(
        env={"NSFWTRACK_ENABLE_OPT_IN_PROVIDERS": "1"}
    ).list_providers() == ()


def test_production_approval_includes_asset_list() -> None:
    assert PO.ASSET_LIST in JAVDB_PRODUCTION_APPROVAL.capabilities
    assert JAVDB_PRODUCTION_APPROVAL.download_policy.enabled is False
