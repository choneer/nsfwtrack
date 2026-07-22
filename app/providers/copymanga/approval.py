"""PRODUCTION approval for CopyManga-style real comic API.

Hosts are code-owned from open-source reader contracts (Venera/copy manga style).
Attribution:
- https://github.com/venera-app/venera
- https://github.com/venera-app/venera-configs

No VIP bypass; page image hosts must stay on the approved set.
"""

from __future__ import annotations

from app.source_adapters.approval import (
    APPROVAL_FORMAT_VERSION,
    ApprovalAttributionPolicy,
    ApprovedAssetPolicy,
    ApprovedAuth,
    ApprovedDownloadPolicy,
    ApprovedFixedHeader,
    ApprovedHost,
    ApprovedHostPurpose,
    ApprovedOperation,
    ApprovedRatePolicy,
    ApprovedTimeoutPolicy,
    ProviderApproval,
    ProviderApprovalScope,
)
from app.source_adapters.contracts import (
    AssetCapabilities,
    AuthCapabilities,
    MetadataCapabilities,
    ProviderAuthMode,
    ProviderCapabilities,
    ProviderOperation,
    SourceAssetKind,
)
from app.source_adapters.registry import (
    BusinessParameter,
    CookiePolicy,
    EndpointOperation,
    HttpMethod,
    JsonTopLevel,
    MAX_PAGE_SIZE,
    MAX_RESPONSE_BYTES,
    ProviderEndpoint,
    RedirectPolicy,
    RequestEncoding,
    ResponseKind,
)

COPYMANGA_PROVIDER_KEY = "copymanga"
COPYMANGA_HOST = "api.mangacopy.com"
COPYMANGA_HOST_ID = "metadata"
COPYMANGA_ASSET_HOST_ID = "asset"
# Image CDN hosts commonly paired with CopyManga-style APIs (code-owned allowlist).
COPYMANGA_IMAGE_HOSTS = (
    "api.mangacopy.com",
    "site.mangacopy.com",
)

_EXCLUSIONS = (
    ProviderOperation.AUTH_TEST,
    ProviderOperation.AUTH_LOGIN,
    ProviderOperation.AUTH_REFRESH,
    ProviderOperation.AUTH_REVOKE,
    ProviderOperation.AUTH_LOGOUT,
    ProviderOperation.DISCOVER,
    ProviderOperation.ASSET_RESOLVE,
    ProviderOperation.DOWNLOAD,
)


def _json_op(
    operation: ProviderOperation,
    *,
    host_id: str,
    path_template: str,
    path_parameter: BusinessParameter | None = None,
    query_parameters: tuple[tuple[BusinessParameter, str], ...] = (),
    required_parameters: tuple[BusinessParameter, ...] = (),
    asset_host_ids: tuple[str, ...] = (),
) -> ApprovedOperation:
    return ApprovedOperation(
        operation=operation,
        layer=operation.layer,
        host_id=host_id,
        path_template=path_template,
        method=HttpMethod.GET,
        request_encoding=RequestEncoding.NONE,
        auth_requirement=ProviderAuthMode.NONE,
        cookie_policy=CookiePolicy.NONE,
        response_kind=ResponseKind.JSON,
        expected_top_level=JsonTopLevel.OBJECT,
        allowed_content_types=("application/json", "application/*+json"),
        response_limit_bytes=MAX_RESPONSE_BYTES,
        page_size_limit=MAX_PAGE_SIZE,
        redirect_policy=RedirectPolicy.DENY,
        rate_policy=ApprovedRatePolicy(),
        fixed_headers=(ApprovedFixedHeader("X-Copymanga-Contract", "venera-json-v1"),),
        timeout_policy=ApprovedTimeoutPolicy(),
        path_parameter=path_parameter,
        query_parameters=query_parameters,
        required_parameters=required_parameters,
        asset_host_ids=asset_host_ids,
    )


COPYMANGA_CAPABILITIES = ProviderCapabilities(
    provider_key=COPYMANGA_PROVIDER_KEY,
    display_name="CopyManga Comic",
    content_scope=(
        "CopyManga-style JSON comic SEARCH/DETAIL/ASSET_LIST for local catalog "
        "and chapter page lists; page download via acquisition package"
    ),
    metadata=MetadataCapabilities(
        (ProviderOperation.SEARCH, ProviderOperation.DETAIL)
    ),
    auth=AuthCapabilities((ProviderAuthMode.NONE,)),
    assets=AssetCapabilities(
        (ProviderOperation.ASSET_LIST,),
        (SourceAssetKind.MEDIA, SourceAssetKind.ATTACHMENT),
    ),
    attribution_required=True,
)

COPYMANGA_APPROVAL = ProviderApproval(
    approval_id="copymanga_production_v1",
    approval_version=APPROVAL_FORMAT_VERSION,
    scope=ProviderApprovalScope.PRODUCTION,
    provider_key=COPYMANGA_PROVIDER_KEY,
    display_name=COPYMANGA_CAPABILITIES.display_name,
    content_scope=COPYMANGA_CAPABILITIES.content_scope,
    product_fit=(
        "Real-site comic metadata + chapter page list (Venera-style fixed JSON). "
        "Local page download is acquisition after user confirm. No JS runtime."
    ),
    lawful_access_basis=(
        "Operator assertion: use only lawful access. Attribution required for "
        "venera-app/venera and venera-configs. No VIP/login bypass."
    ),
    terms_basis="Operator must comply with site Terms; fixed hosts only.",
    attribution_policy=ApprovalAttributionPolicy.REQUIRED,
    capabilities=COPYMANGA_CAPABILITIES.operations,
    hosts=(
        ApprovedHost(
            COPYMANGA_HOST_ID, COPYMANGA_HOST, ApprovedHostPurpose.METADATA
        ),
        ApprovedHost(
            COPYMANGA_ASSET_HOST_ID, COPYMANGA_HOST, ApprovedHostPurpose.ASSET
        ),
    ),
    operations=(
        _json_op(
            ProviderOperation.SEARCH,
            host_id=COPYMANGA_HOST_ID,
            path_template="/api/v3/search/comic",
            query_parameters=((BusinessParameter.QUERY, "q"),),
            required_parameters=(BusinessParameter.QUERY,),
        ),
        _json_op(
            ProviderOperation.DETAIL,
            host_id=COPYMANGA_HOST_ID,
            path_template="/api/v3/comic2/{external_id}",
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
        ),
        _json_op(
            ProviderOperation.ASSET_LIST,
            host_id=COPYMANGA_HOST_ID,
            path_template="/api/v3/comic/{external_id}/group/default/chapters",
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
            asset_host_ids=(COPYMANGA_ASSET_HOST_ID,),
        ),
    ),
    auth=ApprovedAuth(),
    asset_policy=ApprovedAssetPolicy(
        allowed_kinds=(SourceAssetKind.MEDIA, SourceAssetKind.ATTACHMENT),
        asset_host_ids=(COPYMANGA_ASSET_HOST_ID,),
        max_assets_per_item=MAX_PAGE_SIZE,
        locator_resolution_allowed=False,
    ),
    download_policy=ApprovedDownloadPolicy(),
    explicit_exclusions=_EXCLUSIONS,
)

COPYMANGA_ENDPOINT = ProviderEndpoint(
    provider_key=COPYMANGA_PROVIDER_KEY,
    hostname=COPYMANGA_HOST,
    capabilities=COPYMANGA_CAPABILITIES,
    operations=(
        EndpointOperation(
            ProviderOperation.SEARCH,
            "/api/v3/search/comic",
            JsonTopLevel.OBJECT,
            query_parameters=((BusinessParameter.QUERY, "q"),),
            required_parameters=(BusinessParameter.QUERY,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            response_kind=ResponseKind.JSON,
            allowed_content_types=("application/json", "application/*+json"),
            fixed_headers=(("X-Copymanga-Contract", "venera-json-v1"),),
            redirect_policy=RedirectPolicy.DENY,
        ),
        EndpointOperation(
            ProviderOperation.DETAIL,
            "/api/v3/comic2/{external_id}",
            JsonTopLevel.OBJECT,
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            response_kind=ResponseKind.JSON,
            allowed_content_types=("application/json", "application/*+json"),
            fixed_headers=(("X-Copymanga-Contract", "venera-json-v1"),),
            redirect_policy=RedirectPolicy.DENY,
        ),
        EndpointOperation(
            ProviderOperation.ASSET_LIST,
            "/api/v3/comic/{external_id}/group/default/chapters",
            JsonTopLevel.OBJECT,
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            response_kind=ResponseKind.JSON,
            allowed_content_types=("application/json", "application/*+json"),
            fixed_headers=(("X-Copymanga-Contract", "venera-json-v1"),),
            redirect_policy=RedirectPolicy.DENY,
            allowed_asset_hosts=(COPYMANGA_HOST,),
        ),
    ),
)
