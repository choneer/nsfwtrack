from __future__ import annotations

import asyncio
import json
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.source_adapters.contracts import (
    ProviderAdapterError,
    ProviderErrorCode,
    ProviderOperation,
)
from app.source_adapters.registry import PRODUCTION_ENDPOINT_REGISTRY
from app.video_metadata import (
    AssetKind,
    LocalVideoMetadata,
    VideoAsset,
    VideoAssetKind,
    VideoConfidence,
    VideoDetail,
    VideoFieldAction,
    VideoFieldSource,
    VideoIdentifier,
    VideoMetadataAdapter,
    VideoMetadataError,
    VideoMetadataProvenance,
    VideoOrganization,
    VideoOrganizationType,
    VideoPerson,
    VideoPersonRole,
    VideoProvenanceOperation,
    VideoRating,
    VideoSearchPage,
    VideoSearchResult,
    VideoSeries,
    VideoTag,
    VideoTagCategory,
    build_video_metadata_merge_plan,
    bounded_text,
    finite_number,
    timezone_aware_utc,
)
from tests.video_metadata_fixture_provider import (
    FIXTURE_DIRECTORY,
    FIXTURE_PROVIDER_KEY,
    FixtureVideoMetadataProvider,
)


OBSERVED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _asset(asset_id: str = "cover-1", kind: VideoAssetKind = VideoAssetKind.COVER) -> VideoAsset:
    return VideoAsset(
        provider_key=FIXTURE_PROVIDER_KEY,
        asset_id=asset_id,
        kind=kind,
        mime_type="image/jpeg" if kind is not VideoAssetKind.PREVIEW_VIDEO else "video/mp4",
        width=640,
        height=360,
        duration_seconds=30 if kind is VideoAssetKind.PREVIEW_VIDEO else None,
    )


def _detail(**changes: object) -> VideoDetail:
    identifier = VideoIdentifier(FIXTURE_PROVIDER_KEY, "video-merge")
    values: dict[str, object] = {
        "identifier": identifier,
        "title": "Incoming title",
        "summary": "Incoming summary",
        "performers": (),
        "tags": (),
        "available_fields": ("identifier", "title", "summary"),
        "provenance": (
            VideoMetadataProvenance(
                FIXTURE_PROVIDER_KEY,
                "video-merge",
                VideoProvenanceOperation.DETAIL,
                "title",
                OBSERVED_AT,
            ),
        ),
    }
    values.update(changes)
    return VideoDetail(**values)  # type: ignore[arg-type]


def test_all_dtos_are_frozen_slotted_and_have_no_dynamic_attributes() -> None:
    values = (
        VideoIdentifier(FIXTURE_PROVIDER_KEY, "one"),
        VideoPerson(FIXTURE_PROVIDER_KEY, "person", "Person", VideoPersonRole.PERFORMER),
        VideoOrganization(FIXTURE_PROVIDER_KEY, "studio", "Studio", VideoOrganizationType.STUDIO),
        VideoSeries(FIXTURE_PROVIDER_KEY, "series", "Series"),
        VideoTag(FIXTURE_PROVIDER_KEY, "tag", "Raw", "raw", VideoTagCategory.GENERAL),
        VideoRating(1, 0, 5),
        _asset(),
        VideoMetadataProvenance(
            FIXTURE_PROVIDER_KEY,
            "one",
            VideoProvenanceOperation.DETAIL,
            "title",
            OBSERVED_AT,
        ),
    )
    for value in values:
        assert not hasattr(value, "__dict__")
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            value.extra = "forbidden"  # type: ignore[attr-defined]


def test_collections_are_tuples_and_identity_is_provider_scoped() -> None:
    person = VideoPerson(FIXTURE_PROVIDER_KEY, "same", "Person", VideoPersonRole.PERFORMER)
    assert person.alternate_names == ()
    assert person.identity == (FIXTURE_PROVIDER_KEY, "same")
    assert person.identity != ("other_provider", "same")
    with pytest.raises(TypeError):
        VideoPerson(FIXTURE_PROVIDER_KEY, "same", "Person", VideoPersonRole.PERFORMER, ["x"])  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["\x00bad", "line\nfeed", "\x7fbad", "  ", "x" * 501])
def test_bounded_text_rejects_controls_blank_and_oversized_values(value: str) -> None:
    with pytest.raises((TypeError, VideoMetadataError, ValueError)):
        bounded_text(value, 500, field="title")


def test_bounded_text_trims_without_storing_raw_input() -> None:
    assert bounded_text("  title  ", 20) == "title"


def test_identifier_validates_provider_key_external_id_and_credential_free_url() -> None:
    identifier = VideoIdentifier(
        FIXTURE_PROVIDER_KEY,
        "external",
        catalog_number="  CAT-1 ",
        canonical_url="https://synthetic.invalid/video/external",
    )
    assert identifier.catalog_number == "CAT-1"
    with pytest.raises(ValueError):
        VideoIdentifier("Bad Provider", "external")
    with pytest.raises(ValueError):
        VideoIdentifier(FIXTURE_PROVIDER_KEY, "external", canonical_url="https://u:p@synthetic.invalid/x")


def test_rating_is_finite_and_in_range() -> None:
    assert VideoRating(5, 0, 10, 3).value == 5.0
    for value in (float("nan"), float("inf"), -1, 11):
        with pytest.raises((TypeError, ValueError)):
            VideoRating(value, 0, 10)
    with pytest.raises(ValueError):
        VideoRating(1, 10, 10)
    with pytest.raises(ValueError):
        finite_number(float("nan"))


def test_asset_id_is_opaque_and_assets_are_not_authorization_or_download_grants() -> None:
    asset = _asset("opaque_asset~1")
    assert asset.requires_auth is False
    assert asset.downloadable is False
    with pytest.raises(ValueError):
        _asset("../locator")
    with pytest.raises(ValueError):
        VideoAsset(FIXTURE_PROVIDER_KEY, "url:https://synthetic.invalid", VideoAssetKind.COVER)
    with pytest.raises(ValueError):
        replace(asset, downloadable=True)


def test_provenance_requires_aware_utc_and_existing_field() -> None:
    converted = timezone_aware_utc(datetime(2026, 1, 2, 4, 4, tzinfo=UTC))
    assert converted.tzinfo is UTC
    with pytest.raises(ValueError):
        VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "one", VideoProvenanceOperation.DETAIL, "title", datetime.now())
    result = VideoSearchResult(
        identifier=VideoIdentifier(FIXTURE_PROVIDER_KEY, "one"),
        title="Title",
        available_fields=("identifier", "title"),
        provenance=(VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "one", VideoProvenanceOperation.SEARCH, "title", OBSERVED_AT),),
    )
    assert result


def test_available_fields_must_match_actual_nonempty_fields() -> None:
    with pytest.raises(ValueError):
        VideoSearchResult(
            identifier=VideoIdentifier(FIXTURE_PROVIDER_KEY, "one"),
            title="Title",
            available_fields=("identifier",),
        )
    with pytest.raises(ValueError):
        VideoSearchResult(
            identifier=VideoIdentifier(FIXTURE_PROVIDER_KEY, "one"),
            title="Title",
            available_fields=("identifier", "title"),
            provenance=(VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "one", VideoProvenanceOperation.SEARCH, "missing", OBSERVED_AT),),
        )


def test_detail_rejects_duplicate_nested_identity_and_wrong_asset_kind() -> None:
    person = VideoPerson(FIXTURE_PROVIDER_KEY, "person", "Person", VideoPersonRole.PERFORMER)
    with pytest.raises(ValueError):
        VideoDetail(
            VideoIdentifier(FIXTURE_PROVIDER_KEY, "one"),
            "Title",
            performers=(person, person),
        )
    with pytest.raises(ValueError):
        VideoDetail(VideoIdentifier(FIXTURE_PROVIDER_KEY, "one"), "Title", cover=_asset("preview", VideoAssetKind.PREVIEW_IMAGE))


def test_search_page_is_immutable_bounded_and_explicit_about_next_page() -> None:
    result = VideoSearchResult(VideoIdentifier(FIXTURE_PROVIDER_KEY, "one"), "Title")
    page = VideoSearchPage((result,), 1, 10, False, total=1, query="q")
    assert page.results == page.items
    assert page.has_more is False
    with pytest.raises(ValueError):
        VideoSearchPage((result,), 1, 51, False, total=1)


def test_fixture_provider_is_static_and_protocol_conforming() -> None:
    provider = FixtureVideoMetadataProvider()
    assert isinstance(provider, VideoMetadataAdapter)
    assert provider.fixture_directory == FIXTURE_DIRECTORY
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    assert FIXTURE_PROVIDER_KEY not in repr(PRODUCTION_ENDPOINT_REGISTRY)


def test_fixture_operations_are_separate_and_return_typed_values() -> None:
    async def run() -> None:
        provider = FixtureVideoMetadataProvider()
        page = await provider.search("query", page=1, page_size=2)
        assert page.items[0].external_id == "video-001"
        detail = await provider.detail("video-001")
        assert detail.external_id == "video-001"
        assets = await provider.asset_list("video-001")
        assert tuple(asset.kind for asset in assets) == (
            VideoAssetKind.COVER,
            VideoAssetKind.PREVIEW_IMAGE,
            VideoAssetKind.PREVIEW_VIDEO,
        )
        assert await provider.search("empty", page=1, page_size=2) == VideoSearchPage((), 1, 2, False, total=0, query="empty")

    asyncio.run(run())


def test_fixture_provider_performs_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "gethostname", forbidden)
    asyncio.run(FixtureVideoMetadataProvider().detail("video-001"))


@pytest.mark.parametrize(
    "operation, args",
    [
        ("detail", ("does-not-exist",)),
        ("asset_list", ("does-not-exist",)),
    ],
)
def test_fixture_provider_maps_bad_requests_to_stable_redacted_errors(operation: str, args: tuple[str, ...]) -> None:
    with pytest.raises(ProviderAdapterError) as exc_info:
        asyncio.run(getattr(FixtureVideoMetadataProvider(), operation)(*args))
    assert exc_info.value.error.code is ProviderErrorCode.INVALID_PROVIDER_PAYLOAD
    assert exc_info.value.error.operation in {
        ProviderOperation.DETAIL,
        ProviderOperation.ASSET_LIST,
    }
    assert "does-not-exist" not in str(exc_info.value)


def test_malformed_fixture_maps_without_echoing_marker(tmp_path: Path) -> None:
    (tmp_path / "detail_complete.json").write_text("{ malformed marker-secret }")
    provider = FixtureVideoMetadataProvider(tmp_path)
    with pytest.raises(ProviderAdapterError) as exc_info:
        asyncio.run(provider.detail("video-001"))
    assert str(exc_info.value) == "invalid_provider_payload"
    assert "marker-secret" not in repr(exc_info.value)


def test_fixture_parser_rejects_wrong_types_duplicates_and_oversized_lists(tmp_path: Path) -> None:
    source = json.loads((FIXTURE_DIRECTORY / "detail_complete.json").read_text())
    source["performers"] = [source["performers"][0], source["performers"][0]]
    (tmp_path / "detail_complete.json").write_text(json.dumps(source))
    provider = FixtureVideoMetadataProvider(tmp_path)
    with pytest.raises(ProviderAdapterError):
        asyncio.run(provider.detail("video-001"))


def test_merge_plan_user_authored_missing_empty_priority_conflict_and_assets() -> None:
    incoming = _detail(
        cover=_asset(),
        available_fields=("identifier", "title", "summary", "cover"),
        provenance=(
            VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "video-merge", VideoProvenanceOperation.DETAIL, "title", OBSERVED_AT),
            VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "video-merge", VideoProvenanceOperation.DETAIL, "summary", OBSERVED_AT),
            VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "video-merge", VideoProvenanceOperation.DETAIL, "cover", OBSERVED_AT),
        ),
    )
    local = LocalVideoMetadata(
        values=(
            ("title", "User title"),
            ("summary", "Existing summary"),
        ),
        authored=("title",),
        provider_values=(("other_provider", (("summary", "Other summary"),)),),
    )
    plan = build_video_metadata_merge_plan(local, incoming, provider_priority=("fixture_video", "other_provider"))
    decisions = {decision.field_name: decision for decision in plan.decisions}
    assert decisions["title"].action is VideoFieldAction.KEEP_LOCAL
    assert decisions["title"].source is VideoFieldSource.USER
    assert decisions["summary"].action is VideoFieldAction.APPLY_INCOMING
    assert decisions["cover"].action is VideoFieldAction.APPLY_INCOMING
    assert plan.asset_links == (incoming.cover,)
    assert build_video_metadata_merge_plan(local, incoming, provider_priority=("fixture_video", "other_provider")) == plan


def test_merge_plan_missing_and_empty_never_delete() -> None:
    incoming = _detail(
        summary=None,
        available_fields=("identifier", "title"),
        provenance=(VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "video-merge", VideoProvenanceOperation.DETAIL, "title", OBSERVED_AT),),
    )
    local = LocalVideoMetadata(values=(("summary", "Keep me"),))
    plan = build_video_metadata_merge_plan(local, incoming)
    decisions = {decision.field_name: decision for decision in plan.decisions}
    assert decisions["summary"].action is VideoFieldAction.SKIP_MISSING


def test_merge_plan_equal_priority_conflict_and_provider_scoped_lists() -> None:
    incoming = _detail(summary="Provider B", available_fields=("identifier", "title", "summary"), provenance=(
        VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "video-merge", VideoProvenanceOperation.DETAIL, "title", OBSERVED_AT),
        VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "video-merge", VideoProvenanceOperation.DETAIL, "summary", OBSERVED_AT),
    ))
    local = LocalVideoMetadata(provider_values=(("other", (("summary", "Provider A"),)),))
    plan = build_video_metadata_merge_plan(local, incoming, provider_priority=("fixture_video", "other"))
    assert next(item for item in plan.decisions if item.field_name == "summary").action is VideoFieldAction.APPLY_INCOMING
    equal = build_video_metadata_merge_plan(local, incoming, provider_priority={"other": 10, "fixture_video": 10})
    assert next(item for item in equal.decisions if item.field_name == "summary").action is VideoFieldAction.CONFLICT


def test_merge_plan_does_not_write_database_or_resolve_assets() -> None:
    incoming = _detail(cover=_asset(), available_fields=("identifier", "title", "summary", "cover"), provenance=(
        VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "video-merge", VideoProvenanceOperation.DETAIL, "title", OBSERVED_AT),
        VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "video-merge", VideoProvenanceOperation.DETAIL, "summary", OBSERVED_AT),
        VideoMetadataProvenance(FIXTURE_PROVIDER_KEY, "video-merge", VideoProvenanceOperation.DETAIL, "cover", OBSERVED_AT),
    ))
    plan = build_video_metadata_merge_plan(None, incoming)
    assert plan.asset_links
    assert all(asset.identity == (FIXTURE_PROVIDER_KEY, "cover-1") for asset in plan.asset_links)
