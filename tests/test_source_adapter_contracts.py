from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from importlib.metadata import requires, version
from pathlib import Path

import pytest

from app.source_adapters.contracts import (
    SourceAdapter,
    SourceCreator,
    SourceDetail,
    SourceSearchPage,
    SourceSearchResult,
    SourceTag,
)
from app.source_adapters.registry import (
    BusinessParameter,
    EndpointOperation,
    EndpointRegistry,
    JsonTopLevel,
    PRODUCTION_ENDPOINT_REGISTRY,
    ProviderEndpoint,
)
from app.services.outbound_http import OutboundHttpClient, OutboundRequest


def _search_result() -> SourceSearchResult:
    return SourceSearchResult(
        provider_key="unit_test",
        external_id="record-1",
        canonical_url="https://catalog.example/record-1",
        title="Example",
        alternate_titles=("Alternate",),
        summary="Summary",
        release_date=date(2026, 1, 2),
        creators=(SourceCreator("Creator", "creator-1"),),
        tags=(SourceTag("Tag", "tag-1"),),
        source_updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        result_type="work",
        completeness=("title", "summary"),
    )


def test_runtime_dependency_promotes_the_existing_pinned_http_client() -> None:
    runtime = Path("requirements.txt").read_text(encoding="utf-8").splitlines()
    development = Path("requirements-dev.txt").read_text(encoding="utf-8").splitlines()

    assert runtime.count("httpx2==2.5.0") == 1
    assert "httpx2==2.5.0" not in development
    assert development[0] == "-r requirements.txt"
    assert version("httpx2") == "2.5.0"
    assert "httpcore2==2.5.0" in (requires("httpx2") or ())


def test_production_registry_is_empty_and_immutable() -> None:
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    with pytest.raises(AttributeError):
        PRODUCTION_ENDPOINT_REGISTRY._providers = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        del PRODUCTION_ENDPOINT_REGISTRY._providers


def test_registry_and_operation_definitions_are_immutable() -> None:
    operation = EndpointOperation(
        name="detail",
        path_template="/v1/items/{external_id}",
        expected_top_level=JsonTopLevel.OBJECT,
        path_parameter=BusinessParameter.EXTERNAL_ID,
        required_parameters=(BusinessParameter.EXTERNAL_ID,),
    )
    provider = ProviderEndpoint(
        provider_key="unit_test",
        hostname="metadata.example",
        operations=(operation,),
    )
    registry = EndpointRegistry((provider,))

    assert registry.provider("unit_test") is provider
    assert provider.operation("detail") is operation
    assert operation.render_path("a/b ?") == "/v1/items/a%2Fb%20%3F"
    with pytest.raises(FrozenInstanceError):
        operation.name = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        provider.hostname = "changed.example"  # type: ignore[misc]


@pytest.mark.parametrize(
    "hostname",
    [
        "https://metadata.example",
        "metadata.example:443",
        "metadata.example/",
        "METADATA.example",
        "127.0.0.1",
        "metadata",
        "metadata.example.",
    ],
)
def test_registry_rejects_non_fixed_hostname_forms(hostname: str) -> None:
    operation = EndpointOperation("search", "/v1/search", JsonTopLevel.OBJECT)
    with pytest.raises(ValueError):
        ProviderEndpoint("unit_test", hostname, (operation,))


@pytest.mark.parametrize(
    "path",
    [
        "https://metadata.example/v1/search",
        "//metadata.example/v1/search",
        "/v1//search",
        "/v1/../search",
        "/v1\\search",
        "/v1/search?q=x",
        "/v1/%2e%2e/search",
        "/v1/search here",
        "/v1/搜索",
        "/v1/\x00search",
        "/v1/\x7fsearch",
    ],
)
def test_registry_rejects_arbitrary_or_ambiguous_paths(path: str) -> None:
    with pytest.raises(ValueError):
        EndpointOperation("search", path, JsonTopLevel.OBJECT)


def test_source_dtos_are_frozen_and_expose_only_tuples() -> None:
    result = _search_result()
    detail = SourceDetail(
        provider_key=result.provider_key,
        external_id=result.external_id,
        stable_detail_id="detail-1",
        canonical_url=result.canonical_url,
        title=result.title,
        alternate_titles=result.alternate_titles,
        summary=result.summary,
        release_date=result.release_date,
        creators=result.creators,
        tags=result.tags,
        source_updated_at=result.source_updated_at,
        result_type=result.result_type,
        completeness=result.completeness,
        available_fields=("title", "summary"),
    )
    page = SourceSearchPage(
        provider_key="unit_test",
        query="example",
        page=1,
        page_size=20,
        results=(result,),
        total=1,
    )

    assert isinstance(result.alternate_titles, tuple)
    assert isinstance(detail.available_fields, tuple)
    assert isinstance(page.results, tuple)
    with pytest.raises(FrozenInstanceError):
        result.title = "Changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        SourceSearchResult(  # type: ignore[arg-type]
            provider_key="unit_test",
            external_id="1",
            canonical_url="https://catalog.example/1",
            title="Title",
            creators=[SourceCreator("Creator")],
        )


def test_source_dtos_reject_naive_datetime_and_cross_provider_page() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SourceSearchResult(
            provider_key="unit_test",
            external_id="1",
            canonical_url="https://catalog.example/1",
            title="Title",
            source_updated_at=datetime(2026, 1, 2),
        )
    with pytest.raises(ValueError, match="does not match"):
        SourceSearchPage(
            provider_key="other_test",
            query="example",
            page=1,
            page_size=20,
            results=(_search_result(),),
            has_more=False,
        )


@pytest.mark.parametrize(
    "canonical_url",
    [
        "javascript:alert(1)",
        "//catalog.example/1",
        "https://user:password@catalog.example/1",
        "https://catalog.example/1#fragment",
        " https://catalog.example/1",
        "https://catalog.example/a b",
        "https://catalog.example\\path",
    ],
)
def test_source_dtos_reject_noncanonical_or_credentialed_urls(
    canonical_url: str,
) -> None:
    with pytest.raises(ValueError, match="canonical_url"):
        SourceSearchResult(
            provider_key="unit_test",
            external_id="1",
            canonical_url=canonical_url,
            title="Title",
        )


def test_source_adapter_protocol_is_async_and_runtime_checkable() -> None:
    class Adapter:
        key = "unit_test"
        display_name = "Unit Test"

        async def search(
            self,
            query: str,
            *,
            page: int,
            page_size: int,
        ) -> SourceSearchPage:
            return SourceSearchPage(
                provider_key=self.key,
                query=query,
                page=page,
                page_size=page_size,
                results=(),
                total=0,
            )

        async def fetch_detail(self, external_id: str) -> SourceDetail:
            result = _search_result()
            return SourceDetail(
                provider_key=result.provider_key,
                external_id=external_id,
                stable_detail_id=external_id,
                canonical_url=result.canonical_url,
                title=result.title,
            )

    assert isinstance(Adapter(), SourceAdapter)
    assert inspect.iscoroutinefunction(SourceAdapter.search)
    assert inspect.iscoroutinefunction(SourceAdapter.fetch_detail)


def test_outbound_public_request_has_no_url_host_port_or_path_fields() -> None:
    assert tuple(inspect.signature(OutboundHttpClient.fetch_json).parameters) == (
        "self",
        "request",
    )
    assert tuple(OutboundRequest.__dataclass_fields__) == (
        "provider_key",
        "operation",
        "query",
        "external_id",
        "page",
        "page_size",
    )
