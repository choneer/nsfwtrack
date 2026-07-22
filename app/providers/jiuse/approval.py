"""TEST_FIXTURE approval for nsfwpro factory key ``jiuse-vod``.

nsfwpro approval marks search/detail/playback unauthorized until endpoint freeze;
this package is catalog-visible as TEST_FIXTURE for offline parse/search wiring only.
Live host activation and VIP/download remain excluded.
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
    AuthCapabilities,
    MetadataCapabilities,
    ProviderAuthMode,
    ProviderCapabilities,
    ProviderOperation,
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

# nsfwtrack key; nsfwpro factory key is ``jiuse-vod``.
JIUSE_PROVIDER_KEY = "jiuse_vod"
JIUSE_NSFWPRO_KEY = "jiuse-vod"
JIUSE_HOST = "metadata.jiuse.invalid"
JIUSE_HOST_ID = "metadata"

_EXCLUSIONS = (
    ProviderOperation.AUTH_TEST,
    ProviderOperation.AUTH_LOGIN,
    ProviderOperation.AUTH_REFRESH,
    ProviderOperation.AUTH_REVOKE,
    ProviderOperation.AUTH_LOGOUT,
    ProviderOperation.DISCOVER,
    ProviderOperation.ASSET_LIST,
    ProviderOperation.ASSET_RESOLVE,
    ProviderOperation.DOWNLOAD,
)


def _op(
    operation: ProviderOperation,
    *,
    path_template: str,
    path_parameter: BusinessParameter | None = None,
    query_parameters: tuple[tuple[BusinessParameter, str], ...] = (),
    required_parameters: tuple[BusinessParameter, ...] = (),
) -> ApprovedOperation:
    return ApprovedOperation(
        operation=operation,
        layer=operation.layer,
        host_id=JIUSE_HOST_ID,
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
        fixed_headers=(ApprovedFixedHeader("X-Jiuse-Contract", "fixture-v1"),),
        timeout_policy=ApprovedTimeoutPolicy(),
        path_parameter=path_parameter,
        query_parameters=query_parameters,
        required_parameters=required_parameters,
    )


JIUSE_CAPABILITIES = ProviderCapabilities(
    provider_key=JIUSE_PROVIDER_KEY,
    display_name="Jiuse VOD (fixture)",
    content_scope=(
        "offline Jiuse-shaped HTML metadata SEARCH/DETAIL; nsfwpro key jiuse-vod; "
        "no VIP bypass; playback/HLS download not activated"
    ),
    metadata=MetadataCapabilities(
        (ProviderOperation.SEARCH, ProviderOperation.DETAIL)
    ),
    auth=AuthCapabilities((ProviderAuthMode.NONE,)),
    attribution_required=True,
)

JIUSE_APPROVAL = ProviderApproval(
    approval_id="jiuse_vod_test_fixture_v1",
    approval_version=APPROVAL_FORMAT_VERSION,
    scope=ProviderApprovalScope.TEST_FIXTURE,
    provider_key=JIUSE_PROVIDER_KEY,
    display_name=JIUSE_CAPABILITIES.display_name,
    content_scope=JIUSE_CAPABILITIES.content_scope,
    product_fit=(
        "Catalog wiring for nsfwpro factory jiuse-vod. Offline parse only until "
        "nsfwpro endpoint freeze; no production activation of jiuse.io."
    ),
    lawful_access_basis=(
        "TEST_FIXTURE synthetic HTML. nsfwpro approval keeps live capabilities "
        "unauthorized pending endpoint package. No VIP/captcha/region bypass."
    ),
    terms_basis="fixture hosts under .invalid; live Terms apply only under future PRODUCTION",
    attribution_policy=ApprovalAttributionPolicy.REQUIRED,
    capabilities=JIUSE_CAPABILITIES.operations,
    hosts=(
        ApprovedHost(JIUSE_HOST_ID, JIUSE_HOST, ApprovedHostPurpose.METADATA),
    ),
    operations=(
        _op(
            ProviderOperation.SEARCH,
            path_template="/search",
            query_parameters=((BusinessParameter.QUERY, "q"),),
            required_parameters=(BusinessParameter.QUERY,),
        ),
        _op(
            ProviderOperation.DETAIL,
            path_template="/video/view/{external_id}",
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
        ),
    ),
    auth=ApprovedAuth(),
    asset_policy=ApprovedAssetPolicy(),
    download_policy=ApprovedDownloadPolicy(),
    explicit_exclusions=_EXCLUSIONS,
)

JIUSE_ENDPOINT = ProviderEndpoint(
    provider_key=JIUSE_PROVIDER_KEY,
    hostname=JIUSE_HOST,
    capabilities=JIUSE_CAPABILITIES,
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
            fixed_headers=(("X-Jiuse-Contract", "fixture-v1"),),
            redirect_policy=RedirectPolicy.DENY,
        ),
        EndpointOperation(
            ProviderOperation.DETAIL,
            "/video/view/{external_id}",
            None,
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            response_kind=ResponseKind.HTML,
            allowed_content_types=("text/html",),
            fixed_headers=(("X-Jiuse-Contract", "fixture-v1"),),
            redirect_policy=RedirectPolicy.DENY,
        ),
    ),
)
