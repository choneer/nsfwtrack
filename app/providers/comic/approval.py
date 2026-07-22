"""TEST_FIXTURE approval for comic metadata + asset list (download via acquisition)."""

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
    MAX_PAGE_SIZE,
    MAX_RESPONSE_BYTES,
    ProviderEndpoint,
    RedirectPolicy,
    RequestEncoding,
    ResponseKind,
)

COMIC_PROVIDER_KEY = "comic_local_fixture"
COMIC_HOST = "comic.local.invalid"
COMIC_HOST_ID = "metadata"
COMIC_ASSET_HOST_ID = "asset"

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


def _op(
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
        response_kind=ResponseKind.HTML,
        expected_top_level=None,
        allowed_content_types=("text/html",),
        response_limit_bytes=MAX_RESPONSE_BYTES,
        page_size_limit=MAX_PAGE_SIZE,
        redirect_policy=RedirectPolicy.DENY,
        rate_policy=ApprovedRatePolicy(),
        fixed_headers=(ApprovedFixedHeader("X-Comic-Contract", "fixture-v1"),),
        timeout_policy=ApprovedTimeoutPolicy(),
        path_parameter=path_parameter,
        query_parameters=query_parameters,
        required_parameters=required_parameters,
        asset_host_ids=asset_host_ids,
    )


COMIC_CAPABILITIES = ProviderCapabilities(
    provider_key=COMIC_PROVIDER_KEY,
    display_name="Comic Local Fixture",
    content_scope=(
        "offline comic SEARCH/DETAIL and page ASSET_LIST; local DOWNLOAD is "
        "acquisition-package only after user confirm"
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

COMIC_APPROVAL = ProviderApproval(
    approval_id="comic_local_fixture_v1",
    approval_version=APPROVAL_FORMAT_VERSION,
    scope=ProviderApprovalScope.TEST_FIXTURE,
    provider_key=COMIC_PROVIDER_KEY,
    display_name=COMIC_CAPABILITIES.display_name,
    content_scope=COMIC_CAPABILITIES.content_scope,
    product_fit=(
        "Comics/doujin: list pages then download to local after confirm. "
        "TEST_FIXTURE only; production comic host needs a separate approval."
    ),
    lawful_access_basis="synthetic fixture data only; no live comic site",
    terms_basis="fixture hosts under .invalid",
    attribution_policy=ApprovalAttributionPolicy.REQUIRED,
    capabilities=COMIC_CAPABILITIES.operations,
    hosts=(
        ApprovedHost(COMIC_HOST_ID, COMIC_HOST, ApprovedHostPurpose.METADATA),
        ApprovedHost(COMIC_ASSET_HOST_ID, COMIC_HOST, ApprovedHostPurpose.ASSET),
    ),
    operations=(
        _op(
            ProviderOperation.SEARCH,
            host_id=COMIC_HOST_ID,
            path_template="/search",
            query_parameters=((BusinessParameter.QUERY, "q"),),
            required_parameters=(BusinessParameter.QUERY,),
        ),
        _op(
            ProviderOperation.DETAIL,
            host_id=COMIC_HOST_ID,
            path_template="/c/{external_id}",
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
        ),
        _op(
            ProviderOperation.ASSET_LIST,
            # Operation host purpose must be METADATA; asset hosts separate.
            host_id=COMIC_HOST_ID,
            path_template="/c/{external_id}/pages",
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
            asset_host_ids=(COMIC_ASSET_HOST_ID,),
        ),
    ),
    auth=ApprovedAuth(),
    asset_policy=ApprovedAssetPolicy(
        allowed_kinds=(SourceAssetKind.MEDIA, SourceAssetKind.ATTACHMENT),
        asset_host_ids=(COMIC_ASSET_HOST_ID,),
        max_assets_per_item=MAX_PAGE_SIZE,
        locator_resolution_allowed=False,
    ),
    download_policy=ApprovedDownloadPolicy(),
    explicit_exclusions=_EXCLUSIONS,
)

COMIC_ENDPOINT = ProviderEndpoint(
    provider_key=COMIC_PROVIDER_KEY,
    hostname=COMIC_HOST,
    capabilities=COMIC_CAPABILITIES,
    operations=(
        EndpointOperation(
            ProviderOperation.SEARCH,
            "/search",
            None,
            query_parameters=((BusinessParameter.QUERY, "q"),),
            required_parameters=(BusinessParameter.QUERY,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            response_kind=ResponseKind.HTML,
            allowed_content_types=("text/html",),
            fixed_headers=(("X-Comic-Contract", "fixture-v1"),),
            redirect_policy=RedirectPolicy.DENY,
        ),
        EndpointOperation(
            ProviderOperation.DETAIL,
            "/c/{external_id}",
            None,
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            response_kind=ResponseKind.HTML,
            allowed_content_types=("text/html",),
            fixed_headers=(("X-Comic-Contract", "fixture-v1"),),
            redirect_policy=RedirectPolicy.DENY,
        ),
        EndpointOperation(
            ProviderOperation.ASSET_LIST,
            "/c/{external_id}/pages",
            None,
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            response_kind=ResponseKind.HTML,
            allowed_content_types=("text/html",),
            fixed_headers=(("X-Comic-Contract", "fixture-v1"),),
            redirect_policy=RedirectPolicy.DENY,
            allowed_asset_hosts=(COMIC_HOST,),
        ),
    ),
)
