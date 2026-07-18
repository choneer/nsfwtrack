from __future__ import annotations

from collections.abc import Mapping

from app.source_adapters.contracts import (
    AssetCapabilities,
    AuthCapabilities,
    MetadataCapabilities,
    ProviderAdapterError,
    ProviderAuthMode,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCode,
    ProviderOperation,
    SourceAsset,
    SourceAssetChecksumAlgorithm,
    SourceAssetKind,
    SourceDetail,
    SourceSearchPage,
    SourceSearchResult,
)
from app.source_adapters.registry import (
    BusinessParameter,
    EndpointOperation,
    EndpointRegistry,
    HttpMethod,
    JsonTopLevel,
    ProviderEndpoint,
)
from app.services.outbound_http import (
    FrozenJsonObject,
    OutboundErrorCode,
    OutboundHttpClient,
    OutboundHttpError,
    OutboundRequest,
)


FIXTURE_PROVIDER_KEY = "fixture_reference"
FIXTURE_METADATA_HOST = "metadata.fixture.invalid"
FIXTURE_ASSET_HOST = "assets.fixture.invalid"

FIXTURE_CAPABILITIES = ProviderCapabilities(
    provider_key=FIXTURE_PROVIDER_KEY,
    display_name="Fixture Reference Provider",
    content_scope="synthetic fixture records only",
    metadata=MetadataCapabilities(
        (ProviderOperation.SEARCH, ProviderOperation.DETAIL)
    ),
    auth=AuthCapabilities((ProviderAuthMode.NONE,)),
    assets=AssetCapabilities(
        (ProviderOperation.ASSET_LIST,),
        (SourceAssetKind.COVER, SourceAssetKind.PREVIEW),
    ),
)

FIXTURE_SEARCH_OPERATION = EndpointOperation(
    operation=ProviderOperation.SEARCH,
    path_template="/fixture/search",
    expected_top_level=JsonTopLevel.OBJECT,
    query_parameters=(
        (BusinessParameter.QUERY, "q"),
        (BusinessParameter.PAGE, "page"),
        (BusinessParameter.PAGE_SIZE, "limit"),
    ),
    required_parameters=(BusinessParameter.QUERY,),
    method=HttpMethod.GET,
    fixed_headers=(("X-Fixture-Contract", "n4a"),),
)

FIXTURE_DETAIL_OPERATION = EndpointOperation(
    operation=ProviderOperation.DETAIL,
    path_template="/fixture/records/{external_id}",
    expected_top_level=JsonTopLevel.OBJECT,
    path_parameter=BusinessParameter.EXTERNAL_ID,
    required_parameters=(BusinessParameter.EXTERNAL_ID,),
)

FIXTURE_ASSET_LIST_OPERATION = EndpointOperation(
    operation=ProviderOperation.ASSET_LIST,
    path_template="/fixture/records/{external_id}/assets",
    expected_top_level=JsonTopLevel.OBJECT,
    path_parameter=BusinessParameter.EXTERNAL_ID,
    required_parameters=(BusinessParameter.EXTERNAL_ID,),
    allowed_asset_hosts=(FIXTURE_ASSET_HOST,),
)

FIXTURE_ENDPOINT = ProviderEndpoint(
    provider_key=FIXTURE_PROVIDER_KEY,
    hostname=FIXTURE_METADATA_HOST,
    capabilities=FIXTURE_CAPABILITIES,
    operations=(
        FIXTURE_SEARCH_OPERATION,
        FIXTURE_DETAIL_OPERATION,
        FIXTURE_ASSET_LIST_OPERATION,
    ),
)

FIXTURE_ENDPOINT_REGISTRY = EndpointRegistry((FIXTURE_ENDPOINT,))


def _provider_error(
    operation: ProviderOperation,
    code: ProviderErrorCode,
    *,
    retry_after_seconds: int | None = None,
) -> ProviderAdapterError:
    return ProviderAdapterError(
        ProviderError(
            code=code,
            provider_key=FIXTURE_PROVIDER_KEY,
            operation=operation,
            retry_after_seconds=retry_after_seconds,
        )
    )


def _map_outbound_error(
    operation: ProviderOperation,
    error: OutboundHttpError,
) -> ProviderAdapterError:
    code = {
        OutboundErrorCode.AUTH_NOT_CONFIGURED: ProviderErrorCode.AUTH_NOT_CONFIGURED,
        OutboundErrorCode.UNAUTHORIZED: ProviderErrorCode.AUTH_INVALID,
        OutboundErrorCode.FORBIDDEN: ProviderErrorCode.AUTH_FAILED,
        OutboundErrorCode.RATE_LIMITED: ProviderErrorCode.RATE_LIMITED,
        OutboundErrorCode.INVALID_PAYLOAD: ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
        OutboundErrorCode.MALFORMED_JSON: ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
    }.get(error.error.code, ProviderErrorCode.PROVIDER_UNAVAILABLE)
    return _provider_error(
        operation,
        code,
        retry_after_seconds=error.error.retry_after_seconds,
    )


def _object(value: object) -> Mapping[str, object]:
    if not isinstance(value, FrozenJsonObject):
        raise TypeError
    return value


def _array(value: object) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise TypeError
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _optional_text(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise TypeError


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError
    return value


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError
    return value


class FixtureReferenceProvider:
    key = FIXTURE_PROVIDER_KEY
    display_name = FIXTURE_CAPABILITIES.display_name
    capabilities = FIXTURE_CAPABILITIES

    def __init__(self, client: OutboundHttpClient) -> None:
        self._client = client

    async def search(
        self,
        query: str,
        *,
        page: int,
        page_size: int,
    ) -> SourceSearchPage:
        operation = ProviderOperation.SEARCH
        self.capabilities.require(operation)
        try:
            response = await self._client.fetch_json(
                OutboundRequest(
                    self.key,
                    operation.value,
                    query=query,
                    page=page,
                    page_size=page_size,
                )
            )
        except OutboundHttpError as exc:
            raise _map_outbound_error(operation, exc) from None
        try:
            payload = _object(response.data)
            results = tuple(
                SourceSearchResult(
                    provider_key=self.key,
                    external_id=_text(row["external_id"]),
                    canonical_url=_text(row["canonical_url"]),
                    title=_text(row["title"]),
                    summary=_optional_text(row.get("summary")),
                    result_type=_optional_text(row.get("result_type")),
                )
                for row in (
                    _object(value) for value in _array(payload["results"])
                )
            )
            return SourceSearchPage(
                provider_key=self.key,
                query=query,
                page=page,
                page_size=page_size,
                results=results,
                total=_integer(payload["total"]),
            )
        except (KeyError, TypeError, ValueError):
            raise _provider_error(
                operation,
                ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            ) from None

    async def fetch_detail(self, external_id: str) -> SourceDetail:
        operation = ProviderOperation.DETAIL
        self.capabilities.require(operation)
        try:
            response = await self._client.fetch_json(
                OutboundRequest(
                    self.key,
                    operation.value,
                    external_id=external_id,
                )
            )
        except OutboundHttpError as exc:
            raise _map_outbound_error(operation, exc) from None
        try:
            payload = _object(response.data)
            response_external_id = _text(payload["external_id"])
            if response_external_id != external_id:
                raise ValueError
            return SourceDetail(
                provider_key=self.key,
                external_id=response_external_id,
                stable_detail_id=_text(payload["stable_detail_id"]),
                canonical_url=_text(payload["canonical_url"]),
                title=_text(payload["title"]),
                summary=_optional_text(payload.get("summary")),
                result_type=_optional_text(payload.get("result_type")),
                available_fields=tuple(
                    _text(value) for value in _array(payload["available_fields"])
                ),
            )
        except (KeyError, TypeError, ValueError):
            raise _provider_error(
                operation,
                ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            ) from None

    async def list_assets(self, external_id: str) -> tuple[SourceAsset, ...]:
        operation = ProviderOperation.ASSET_LIST
        self.capabilities.require(operation)
        try:
            response = await self._client.fetch_json(
                OutboundRequest(
                    self.key,
                    operation.value,
                    external_id=external_id,
                )
            )
        except OutboundHttpError as exc:
            raise _map_outbound_error(operation, exc) from None
        try:
            payload = _object(response.data)
            assets = tuple(
                self._asset_from_payload(_object(value), external_id)
                for value in _array(payload["assets"])
            )
            return assets
        except (KeyError, TypeError, ValueError):
            raise _provider_error(
                operation,
                ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            ) from None

    def _asset_from_payload(
        self,
        payload: Mapping[str, object],
        external_id: str,
    ) -> SourceAsset:
        response_external_id = _text(payload["external_id"])
        if response_external_id != external_id:
            raise ValueError
        kind = SourceAssetKind(_text(payload["kind"]))
        if kind not in self.capabilities.assets.kinds:
            raise ValueError
        checksum_name = _optional_text(payload.get("checksum_algorithm"))
        checksum_algorithm = (
            None
            if checksum_name is None
            else SourceAssetChecksumAlgorithm(checksum_name)
        )
        size_value = payload.get("size_bytes")
        requires_auth = _boolean(payload["requires_auth"])
        downloadable = _boolean(payload["downloadable"])
        if requires_auth and self.capabilities.auth_modes == (ProviderAuthMode.NONE,):
            raise ValueError
        if downloadable and not self.capabilities.supports(
            ProviderOperation.DOWNLOAD
        ):
            raise ValueError
        return SourceAsset(
            provider_key=self.key,
            external_id=response_external_id,
            asset_id=_text(payload["asset_id"]),
            kind=kind,
            display_name=_optional_text(payload.get("display_name")),
            mime_type=_optional_text(payload.get("mime_type")),
            size_bytes=None if size_value is None else _integer(size_value),
            checksum_algorithm=checksum_algorithm,
            checksum_value=_optional_text(payload.get("checksum_value")),
            requires_auth=requires_auth,
            downloadable=downloadable,
        )
