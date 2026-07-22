from __future__ import annotations

import asyncio
import importlib
import logging
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx2
import pytest
from sqlalchemy.orm import Session

from app.services.outbound_http import OutboundHttpClient
from app.source_adapters import (
    AssetCapabilities,
    ApprovedAssetPolicy,
    ProviderAdapterBinding,
    ProviderAdapterKind,
    ProviderAdapterError,
    ProviderError,
    ProviderErrorCode,
    ProviderOperation,
    ProviderPackage,
    ProviderPackageErrorCode,
)
from app.source_search import (
    PRODUCTION_SEARCH_PACKAGES,
    ProviderSearchService,
    ProviderSearchServiceError,
    ProviderSearchServiceErrorCode,
    SearchProviderDescriptor,
    VideoAssetListEnvelope,
    VideoAssetListRequest,
    VideoDetailEnvelope,
    VideoDetailRequest,
    VideoSearchEnvelope,
    VideoSearchRequest,
    build_production_search_service,
)
from app.video_metadata.contracts import (
    VideoAsset,
    VideoAssetKind,
    VideoDetail,
    VideoIdentifier,
    VideoSearchPage,
    VideoSearchResult,
)
from tests.provider_package_fixture import VIDEO_PACKAGE, VIDEO_FIXTURE_DIGESTS


NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
PROVIDER_KEY = VIDEO_PACKAGE.provider_key


def _identifier(provider_key: str = PROVIDER_KEY) -> VideoIdentifier:
    return VideoIdentifier(provider_key=provider_key, external_id="video-001")


def _search_page(
    *,
    provider_key: str = PROVIDER_KEY,
    page: int = 1,
    page_size: int = 10,
    query: str = "query",
) -> VideoSearchPage:
    result = VideoSearchResult(identifier=_identifier(provider_key), title="Synthetic")
    return VideoSearchPage(
        items=(result,),
        page=page,
        page_size=page_size,
        has_next=False,
        total=1,
        query=query,
    )


def _detail(provider_key: str = PROVIDER_KEY, external_id: str = "video-001") -> VideoDetail:
    return VideoDetail(
        identifier=VideoIdentifier(provider_key=provider_key, external_id=external_id),
        title="Synthetic detail",
    )


def _asset(provider_key: str = PROVIDER_KEY, asset_id: str = "cover-001") -> VideoAsset:
    return VideoAsset(
        provider_key=provider_key,
        asset_id=asset_id,
        kind=VideoAssetKind.COVER,
        display_name="Synthetic cover",
    )


class CountingAdapter:
    key = PROVIDER_KEY

    def __init__(self, *, provider_key: str = PROVIDER_KEY) -> None:
        self.key = provider_key
        self.provider_key = provider_key
        self.calls = {"search": 0, "detail": 0, "asset_list": 0}
        self.search_result: object = _search_page(provider_key=provider_key)
        self.detail_result: object = _detail(provider_key=provider_key)
        self.asset_result: object = (_asset(provider_key=provider_key),)
        self.error: ProviderAdapterError | None = None
        self.unknown_error: Exception | None = None
        self.cancelled = False

    async def search(self, query: str, *, page: int, page_size: int) -> object:
        self.calls["search"] += 1
        if self.cancelled:
            raise asyncio.CancelledError
        if self.error is not None:
            raise self.error
        if self.unknown_error is not None:
            raise self.unknown_error
        return self.search_result

    async def detail(self, external_id: str) -> object:
        self.calls["detail"] += 1
        if self.cancelled:
            raise asyncio.CancelledError
        if self.error is not None:
            raise self.error
        if self.unknown_error is not None:
            raise self.unknown_error
        return self.detail_result

    async def asset_list(self, external_id: str) -> object:
        self.calls["asset_list"] += 1
        if self.cancelled:
            raise asyncio.CancelledError
        if self.error is not None:
            raise self.error
        if self.unknown_error is not None:
            raise self.unknown_error
        return self.asset_result


def _video_package(adapter: CountingAdapter | None = None) -> ProviderPackage:
    adapter = adapter or CountingAdapter()
    binding = replace(VIDEO_PACKAGE.binding, adapter=adapter)
    return replace(VIDEO_PACKAGE, binding=binding)


def _alternate_video_package() -> ProviderPackage:
    key = "fixture_video_alt"
    adapter = CountingAdapter(provider_key=key)
    capabilities = replace(VIDEO_PACKAGE.capabilities, provider_key=key)
    endpoint = replace(
        VIDEO_PACKAGE.endpoint,
        provider_key=key,
        capabilities=capabilities,
    )
    approval = replace(
        VIDEO_PACKAGE.approval,
        provider_key=key,
        approval_id="fixture_video_alt_v1",
    )
    evidence = replace(
        VIDEO_PACKAGE.evidence,
        provider_key=key,
        approval_id="fixture_video_alt_v1",
    )
    binding = replace(
        VIDEO_PACKAGE.binding,
        provider_key=key,
        adapter=adapter,
    )
    return replace(
        VIDEO_PACKAGE,
        approval=approval,
        capabilities=capabilities,
        endpoint=endpoint,
        binding=binding,
        evidence=evidence,
    )


def _metadata_only_package(adapter: CountingAdapter) -> ProviderPackage:
    operations = (ProviderOperation.SEARCH, ProviderOperation.DETAIL)
    capabilities = replace(VIDEO_PACKAGE.capabilities, assets=AssetCapabilities())
    endpoint = replace(
        VIDEO_PACKAGE.endpoint,
        capabilities=capabilities,
        operations=VIDEO_PACKAGE.endpoint.operations[:2],
    )
    approval = replace(
        VIDEO_PACKAGE.approval,
        capabilities=operations,
        hosts=(VIDEO_PACKAGE.approval.hosts[0],),
        operations=VIDEO_PACKAGE.approval.operations[:2],
        asset_policy=ApprovedAssetPolicy(),
        explicit_exclusions=(
            *VIDEO_PACKAGE.approval.explicit_exclusions,
            ProviderOperation.ASSET_LIST,
        ),
    )
    evidence_values = tuple(
        value
        for value in VIDEO_PACKAGE.evidence.fixture_evidence
        if value.operation in operations
    )
    evidence = replace(
        VIDEO_PACKAGE.evidence,
        reviewed_operations=operations,
        fixture_evidence=evidence_values,
    )
    evidence_ids = {value.fixture_id for value in evidence_values}
    binding = replace(
        VIDEO_PACKAGE.binding,
        operations=operations,
        adapter=adapter,
    )
    return replace(
        VIDEO_PACKAGE,
        approval=approval,
        capabilities=capabilities,
        endpoint=endpoint,
        binding=binding,
        evidence=evidence,
        fixture_digests=tuple(
            value for value in VIDEO_FIXTURE_DIGESTS if value[0] in evidence_ids
        ),
    )


def _service(
    adapter: CountingAdapter | None = None,
    packages: tuple[ProviderPackage, ...] | None = None,
) -> tuple[ProviderSearchService, CountingAdapter]:
    adapter = adapter or CountingAdapter()
    packages = packages or (_video_package(adapter),)
    return ProviderSearchService(packages, clock=lambda: NOW), adapter


def _error_code(operation) -> ProviderSearchServiceErrorCode:
    with pytest.raises(ProviderSearchServiceError) as exc_info:
        asyncio.run(operation())
    return exc_info.value.code


def test_new_contracts_are_frozen_slotted_and_tuple_only() -> None:
    descriptor = SearchProviderDescriptor(
        PROVIDER_KEY,
        "Synthetic",
        "Synthetic records",
        VIDEO_PACKAGE.binding.operations,
    )
    values = (
        descriptor,
        VideoSearchRequest(PROVIDER_KEY, " query ", 1, 10),
        VideoDetailRequest(PROVIDER_KEY, "video-001"),
        VideoAssetListRequest(PROVIDER_KEY, "video-001"),
        VideoSearchEnvelope(
            descriptor,
            VideoSearchRequest(PROVIDER_KEY, "query", 1, 10),
            _search_page(),
            NOW,
        ),
        VideoDetailEnvelope(
            descriptor,
            VideoDetailRequest(PROVIDER_KEY, "video-001"),
            _detail(),
            NOW,
        ),
        VideoAssetListEnvelope(
            descriptor,
            VideoAssetListRequest(PROVIDER_KEY, "video-001"),
            (_asset(),),
            NOW,
        ),
    )
    for value in values:
        assert not hasattr(value, "__dict__")
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            value.extra = "forbidden"  # type: ignore[attr-defined]

    error = ProviderSearchServiceError(ProviderSearchServiceErrorCode.UNKNOWN)
    assert ProviderSearchServiceError.__slots__ == ("code", "cause_code")
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        error.extra = "forbidden"  # type: ignore[attr-defined]

    service, _ = _service()
    with pytest.raises(AttributeError):
        service._clock = lambda: NOW  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        del service._entries  # type: ignore[attr-defined]


def test_contracts_reject_mutable_collections_and_require_utc_time() -> None:
    with pytest.raises(TypeError):
        SearchProviderDescriptor(
            PROVIDER_KEY,
            "Synthetic",
            "Synthetic records",
            list(VIDEO_PACKAGE.binding.operations),  # type: ignore[arg-type]
        )

    descriptor = SearchProviderDescriptor(
        PROVIDER_KEY,
        "Synthetic",
        "Synthetic records",
        VIDEO_PACKAGE.binding.operations,
    )
    request = VideoAssetListRequest(PROVIDER_KEY, "video-001")
    with pytest.raises(TypeError):
        VideoAssetListEnvelope(
            descriptor,
            request,
            [_asset()],  # type: ignore[arg-type]
            NOW,
        )
    with pytest.raises(ValueError):
        VideoDetailEnvelope(
            descriptor,
            VideoDetailRequest(PROVIDER_KEY, "video-001"),
            _detail(),
            datetime(2026, 7, 19, 12, 0),
        )
    offset_time = datetime(
        2026,
        7,
        19,
        20,
        0,
        tzinfo=timezone(timedelta(hours=8)),
    )
    envelope = VideoDetailEnvelope(
        descriptor,
        VideoDetailRequest(PROVIDER_KEY, "video-001"),
        _detail(),
        offset_time,
    )
    assert envelope.received_at == NOW


@pytest.mark.parametrize(
    "factory",
    [
        lambda: VideoSearchRequest(PROVIDER_KEY, "", 1, 10),
        lambda: VideoSearchRequest(PROVIDER_KEY, "\x00", 1, 10),
        lambda: VideoSearchRequest(PROVIDER_KEY, "x" * 201, 1, 10),
        lambda: VideoSearchRequest(PROVIDER_KEY, "query", True, 10),
        lambda: VideoSearchRequest(PROVIDER_KEY, "query", 1, True),
        lambda: VideoSearchRequest(PROVIDER_KEY, "query", 1, 51),
        lambda: VideoDetailRequest(PROVIDER_KEY, "https://not-an-id"),
        lambda: VideoDetailRequest(PROVIDER_KEY, "../not-an-id"),
        lambda: VideoAssetListRequest(PROVIDER_KEY, "a\\b"),
    ],
)
def test_request_boundaries_reject_invalid_values(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_request_trim_and_external_id_are_opaque() -> None:
    request = VideoSearchRequest(PROVIDER_KEY, "  query  ", 1, 10)
    assert request.query == "query"
    detail = VideoDetailRequest(PROVIDER_KEY, "video-001")
    assert detail.external_id == "video-001"


def test_service_requires_exact_request_types() -> None:
    class SearchRequestSubclass(VideoSearchRequest):
        pass

    class DetailRequestSubclass(VideoDetailRequest):
        pass

    class AssetListRequestSubclass(VideoAssetListRequest):
        pass

    service, adapter = _service()
    operations = (
        lambda: service.search(
            SearchRequestSubclass(PROVIDER_KEY, "query", 1, 10)
        ),
        lambda: service.detail(
            DetailRequestSubclass(PROVIDER_KEY, "video-001")
        ),
        lambda: service.asset_list(
            AssetListRequestSubclass(PROVIDER_KEY, "video-001")
        ),
    )
    for operation in operations:
        with pytest.raises(ProviderSearchServiceError) as error:
            asyncio.run(operation())
        assert error.value.code is ProviderSearchServiceErrorCode.INVALID_REQUEST
    assert adapter.calls == {"search": 0, "detail": 0, "asset_list": 0}


def test_envelope_parity_and_asset_duplicate_validation() -> None:
    descriptor = SearchProviderDescriptor(
        PROVIDER_KEY,
        "Synthetic",
        "Synthetic records",
        VIDEO_PACKAGE.binding.operations,
    )
    request = VideoSearchRequest(PROVIDER_KEY, "query", 1, 10)
    envelope = VideoSearchEnvelope(descriptor, request, _search_page(), NOW)
    assert envelope.received_at == NOW
    with pytest.raises(ValueError):
        VideoSearchEnvelope(
            descriptor,
            request,
            _search_page(page=2),
            NOW,
        )
    with pytest.raises(ValueError):
        VideoAssetListEnvelope(
            descriptor,
            VideoAssetListRequest(PROVIDER_KEY, "video-001"),
            (_asset(), _asset()),
            NOW,
        )


def test_production_service_is_empty_and_rejects_unknown() -> None:
    service = build_production_search_service(clock=lambda: NOW)
    assert service.list_providers() == ()
    # Synthetic N5A fixture key is not a production provider.
    requests = (
        lambda: service.search(VideoSearchRequest(PROVIDER_KEY, "query", 1, 10)),
        lambda: service.detail(VideoDetailRequest(PROVIDER_KEY, "video-001")),
        lambda: service.asset_list(VideoAssetListRequest(PROVIDER_KEY, "video-001")),
    )
    for request in requests:
        assert _error_code(request) is ProviderSearchServiceErrorCode.PROVIDER_NOT_AVAILABLE


def test_service_constructor_validates_packages_and_sorts_descriptors() -> None:
    service, adapter = _service()
    assert [value.provider_key for value in service.list_providers()] == [PROVIDER_KEY]
    assert adapter.calls == {"search": 0, "detail": 0, "asset_list": 0}
    alternate = _alternate_video_package()
    ordered = ProviderSearchService(
        (_video_package(), alternate),
        clock=lambda: NOW,
    )
    assert [value.provider_key for value in ordered.list_providers()] == sorted(
        (PROVIDER_KEY, "fixture_video_alt")
    )
    with pytest.raises(ProviderSearchServiceError) as duplicate:
        ProviderSearchService((VIDEO_PACKAGE, VIDEO_PACKAGE), clock=lambda: NOW)
    assert duplicate.value.code is ProviderSearchServiceErrorCode.ADAPTER_MISMATCH
    for packages in ([VIDEO_PACKAGE], (object(),)):
        with pytest.raises(ProviderSearchServiceError) as invalid:
            ProviderSearchService(packages, clock=lambda: NOW)  # type: ignore[arg-type]
        assert invalid.value.code is ProviderSearchServiceErrorCode.INVALID_REQUEST


def test_constructor_rejects_source_adapter_kind_and_invalid_package() -> None:
    from tests.provider_package_fixture import SOURCE_PACKAGE

    with pytest.raises(ProviderSearchServiceError) as source:
        ProviderSearchService((SOURCE_PACKAGE,), clock=lambda: NOW)
    assert source.value.code is ProviderSearchServiceErrorCode.ADAPTER_MISMATCH

    invalid_binding = replace(VIDEO_PACKAGE.binding, display_name="mismatch")
    with pytest.raises(ProviderSearchServiceError) as invalid:
        ProviderSearchService(
            (replace(VIDEO_PACKAGE, binding=invalid_binding),),
            clock=lambda: NOW,
        )
    assert invalid.value.code is ProviderSearchServiceErrorCode.ADAPTER_MISMATCH
    assert invalid.value.cause_code is not None


def test_search_calls_only_search_once_and_wraps_page() -> None:
    service, adapter = _service()
    result = asyncio.run(
        service.search(VideoSearchRequest(PROVIDER_KEY, "query", 1, 10))
    )
    assert isinstance(result, VideoSearchEnvelope)
    assert result.page.page == 1
    assert adapter.calls == {"search": 1, "detail": 0, "asset_list": 0}


def test_detail_calls_only_detail_once_and_wraps_identity() -> None:
    service, adapter = _service()
    result = asyncio.run(
        service.detail(VideoDetailRequest(PROVIDER_KEY, "video-001"))
    )
    assert isinstance(result, VideoDetailEnvelope)
    assert result.detail.external_id == "video-001"
    assert adapter.calls == {"search": 0, "detail": 1, "asset_list": 0}


def test_asset_list_calls_only_asset_list_once() -> None:
    service, adapter = _service()
    result = asyncio.run(
        service.asset_list(
            VideoAssetListRequest(PROVIDER_KEY, "video-001")
        )
    )
    assert isinstance(result, VideoAssetListEnvelope)
    assert result.assets[0].asset_id == "cover-001"
    assert adapter.calls == {"search": 0, "detail": 0, "asset_list": 1}


def test_missing_asset_capability_is_rejected_before_adapter_call() -> None:
    adapter = CountingAdapter()
    service = ProviderSearchService(
        (_metadata_only_package(adapter),),
        clock=lambda: NOW,
    )
    with pytest.raises(ProviderSearchServiceError) as error:
        asyncio.run(
            service.asset_list(
                VideoAssetListRequest(PROVIDER_KEY, "video-001")
            )
        )
    assert error.value.code is ProviderSearchServiceErrorCode.OPERATION_NOT_APPROVED
    assert adapter.calls == {"search": 0, "detail": 0, "asset_list": 0}


@pytest.mark.parametrize(
    "result",
    [
        {},
        [],
        VideoSearchPage(items=(), page=2, page_size=10, has_next=False, total=0, query="query"),
        VideoSearchPage(items=(), page=1, page_size=9, has_next=False, total=0, query="query"),
        VideoSearchPage(
            items=(),
            page=1,
            page_size=10,
            has_next=False,
            total=0,
            query="other-query",
        ),
        VideoSearchPage(
            items=(_search_page(provider_key="other_fixture").items[0],),
            page=1,
            page_size=10,
            has_next=False,
            total=1,
            query="query",
        ),
    ],
)
def test_search_result_parity_rejects_wrong_or_mutable_result(result: object) -> None:
    adapter = CountingAdapter()
    adapter.search_result = result
    service, _ = _service(adapter)
    with pytest.raises(ProviderSearchServiceError) as error:
        asyncio.run(
            service.search(VideoSearchRequest(PROVIDER_KEY, "query", 1, 10))
        )
    assert error.value.code is ProviderSearchServiceErrorCode.INVALID_RESULT


def test_detail_result_identity_and_type_are_validated() -> None:
    adapter = CountingAdapter()
    service, _ = _service(adapter)
    for result in (
        _detail(external_id="video-002"),
        _detail(provider_key="other_fixture"),
        {"external_id": "video-001"},
    ):
        adapter.detail_result = result
        with pytest.raises(ProviderSearchServiceError) as error:
            asyncio.run(
                service.detail(
                    VideoDetailRequest(PROVIDER_KEY, "video-001")
                )
            )
        assert error.value.code is ProviderSearchServiceErrorCode.INVALID_RESULT


def test_asset_result_type_provider_duplicate_and_limit_are_validated() -> None:
    adapter = CountingAdapter()
    service, _ = _service(adapter)
    for result in (
        [_asset()],
        (_asset(provider_key="other_fixture"),),
        (_asset(), _asset()),
        tuple(_asset(asset_id=f"cover-{index:03d}") for index in range(65)),
    ):
        adapter.asset_result = result
        with pytest.raises(ProviderSearchServiceError) as error:
            asyncio.run(
                service.asset_list(
                    VideoAssetListRequest(PROVIDER_KEY, "video-001")
                )
            )
        assert error.value.code is ProviderSearchServiceErrorCode.INVALID_RESULT


def test_provider_error_unknown_and_cancelled_semantics_are_stable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = CountingAdapter()
    service, _ = _service(adapter)
    adapter.error = ProviderAdapterError(
        ProviderError(
            ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            PROVIDER_KEY,
            ProviderOperation.SEARCH,
        )
    )
    with pytest.raises(ProviderSearchServiceError) as provider_error:
        asyncio.run(
            service.search(
                VideoSearchRequest(PROVIDER_KEY, "private-query", 1, 10)
            )
        )
    assert provider_error.value.code is ProviderSearchServiceErrorCode.PROVIDER_ERROR
    assert provider_error.value.cause_code is ProviderErrorCode.INVALID_PROVIDER_PAYLOAD

    marker = "private-adapter-marker"
    adapter.error = None
    adapter.unknown_error = RuntimeError(marker)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ProviderSearchServiceError) as unknown:
        asyncio.run(
            service.search(
                VideoSearchRequest(PROVIDER_KEY, "private-query", 1, 10)
            )
        )
    rendered = f"{unknown.value!s} {unknown.value!r} {caplog.text}"
    assert unknown.value.code is ProviderSearchServiceErrorCode.UNKNOWN
    assert marker not in rendered

    assert str(provider_error.value) == "provider_error"
    assert repr(provider_error.value) == (
        "ProviderSearchServiceError(code='provider_error', "
        "cause_code='invalid_provider_payload')"
    )

    adapter.unknown_error = ProviderSearchServiceError(
        ProviderSearchServiceErrorCode.INVALID_RESULT
    )
    with pytest.raises(ProviderSearchServiceError) as untrusted_service_error:
        asyncio.run(
            service.search(VideoSearchRequest(PROVIDER_KEY, "query", 1, 10))
        )
    assert untrusted_service_error.value.code is ProviderSearchServiceErrorCode.UNKNOWN

    adapter.unknown_error = None
    adapter.cancelled = True
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            service.search(VideoSearchRequest(PROVIDER_KEY, "query", 1, 10))
        )


def test_provider_error_identity_mismatch_is_adapter_mismatch() -> None:
    adapter = CountingAdapter()
    service, _ = _service(adapter)
    adapter.error = ProviderAdapterError(
        ProviderError(
            ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            "other_fixture",
            ProviderOperation.SEARCH,
        )
    )
    with pytest.raises(ProviderSearchServiceError) as error:
        asyncio.run(
            service.search(VideoSearchRequest(PROVIDER_KEY, "query", 1, 10))
        )
    assert error.value.code is ProviderSearchServiceErrorCode.ADAPTER_MISMATCH
    assert error.value.cause_code is ProviderErrorCode.INVALID_PROVIDER_PAYLOAD


def test_non_awaitable_adapter_result_is_invalid() -> None:
    adapter = CountingAdapter()
    package = _video_package(adapter)

    def synchronous_search(query: str, *, page: int, page_size: int) -> object:
        adapter.calls["search"] += 1
        return _search_page(page=page, page_size=page_size, query=query)

    adapter.search = synchronous_search  # type: ignore[method-assign]
    service = ProviderSearchService((package,), clock=lambda: NOW)
    with pytest.raises(ProviderSearchServiceError) as error:
        asyncio.run(
            service.search(VideoSearchRequest(PROVIDER_KEY, "query", 1, 10))
        )
    assert error.value.code is ProviderSearchServiceErrorCode.INVALID_RESULT
    assert adapter.calls == {"search": 1, "detail": 0, "asset_list": 0}


def test_service_and_preflight_paths_have_zero_external_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object):
        raise AssertionError("side effect is forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "gethostbyname", forbidden)
    monkeypatch.setattr(httpx2, "AsyncClient", forbidden)
    monkeypatch.setattr(OutboundHttpClient, "__init__", forbidden)
    monkeypatch.setattr(Session, "execute", forbidden)
    monkeypatch.setattr(Session, "commit", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)

    # Warm catalogs before forbidding network/import side effects.
    service = build_production_search_service(clock=lambda: NOW)
    assert service.list_providers() == ()
    assert PRODUCTION_SEARCH_PACKAGES == ()
    monkeypatch.setattr(importlib, "import_module", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert _error_code(
        lambda: service.search(VideoSearchRequest(PROVIDER_KEY, "query", 1, 10))
    ) is ProviderSearchServiceErrorCode.PROVIDER_NOT_AVAILABLE

    available, adapter = _service()
    assert _error_code(
        lambda: available.search(VideoDetailRequest(PROVIDER_KEY, "video-001"))
    ) is ProviderSearchServiceErrorCode.INVALID_REQUEST
    assert adapter.calls == {"search": 0, "detail": 0, "asset_list": 0}
