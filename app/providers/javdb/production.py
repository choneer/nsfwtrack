"""PRODUCTION approval facts for JavDB metadata + link ASSET_LIST (phases B–C).

Code-owned immutable facts. Does **not** populate default production catalogs
(v1.3 freeze: empty). Opt-in package builders live in ``package_build``.

Scope:
- SEARCH + DETAIL HTML scrape with operator session cookie
- ASSET_LIST of non-downloadable link descriptors (covers/previews)
- DOWNLOAD remains excluded here; optional local download is acquisition-side
- No VIP/login bypass; JP/KR egress policy text only

Attribution:
- https://github.com/Yuukiy/JavSP
- https://github.com/lmixture/JavdBviewed
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
    MAX_PAGE_SIZE,
    MAX_RESPONSE_BYTES,
    ProviderEndpoint,
    RedirectPolicy,
    RequestEncoding,
    ResponseKind,
)

JAVDB_PRODUCTION_PROVIDER_KEY = "javdb_metadata"
JAVDB_PRODUCTION_HOST = "javdb.com"
JAVDB_PRODUCTION_HOST_ID = "metadata"
JAVDB_PRODUCTION_ASSET_HOST_ID = "asset"

JAVDB_PRODUCTION_REGION_POLICY = (
    "Regional constraint: JavDB blocks JP/KR egress. Operator must route outbound "
    "Provider traffic through a non-JP/KR exit (verify via local /egress diagnostics). "
    "This approval does not authorize geo-block circumvention beyond the operator's "
    "own lawful proxy/VPN configuration."
)

_PRODUCTION_EXCLUSIONS = (
    ProviderOperation.AUTH_TEST,
    ProviderOperation.AUTH_LOGIN,
    ProviderOperation.AUTH_REFRESH,
    ProviderOperation.AUTH_REVOKE,
    ProviderOperation.AUTH_LOGOUT,
    ProviderOperation.DISCOVER,
    ProviderOperation.ASSET_RESOLVE,
    ProviderOperation.DOWNLOAD,
)


def _html_session_op(
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
        cookie_policy=CookiePolicy.PROVIDER_SESSION,
        response_kind=ResponseKind.HTML,
        expected_top_level=None,
        allowed_content_types=("text/html",),
        response_limit_bytes=MAX_RESPONSE_BYTES,
        page_size_limit=MAX_PAGE_SIZE,
        redirect_policy=RedirectPolicy.DENY,
        rate_policy=ApprovedRatePolicy(
            provider_concurrency_limit=1,
            automatic_retry_limit=0,
        ),
        fixed_headers=(
            ApprovedFixedHeader("X-Javdb-Contract", "production-metadata-v1"),
        ),
        timeout_policy=ApprovedTimeoutPolicy(),
        path_parameter=path_parameter,
        query_parameters=query_parameters,
        required_parameters=required_parameters,
        asset_host_ids=asset_host_ids,
    )


JAVDB_PRODUCTION_CAPABILITIES = ProviderCapabilities(
    provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
    display_name="JavDB Metadata",
    content_scope=(
        "JavDB video metadata SEARCH/DETAIL HTML scrape and non-downloadable "
        "ASSET_LIST link descriptors; operator session cookie; optional local "
        "download is a separate acquisition package"
    ),
    metadata=MetadataCapabilities(
        (ProviderOperation.SEARCH, ProviderOperation.DETAIL)
    ),
    auth=AuthCapabilities(
        (ProviderAuthMode.NONE, ProviderAuthMode.SESSION_COOKIE)
    ),
    assets=AssetCapabilities(
        (ProviderOperation.ASSET_LIST,),
        (SourceAssetKind.COVER, SourceAssetKind.PREVIEW),
    ),
    attribution_required=True,
)

JAVDB_PRODUCTION_SEARCH_OPERATION = _html_session_op(
    ProviderOperation.SEARCH,
    host_id=JAVDB_PRODUCTION_HOST_ID,
    path_template="/search",
    query_parameters=((BusinessParameter.QUERY, "q"),),
    required_parameters=(BusinessParameter.QUERY,),
)
JAVDB_PRODUCTION_DETAIL_OPERATION = _html_session_op(
    ProviderOperation.DETAIL,
    host_id=JAVDB_PRODUCTION_HOST_ID,
    path_template="/v/{external_id}",
    path_parameter=BusinessParameter.EXTERNAL_ID,
    required_parameters=(BusinessParameter.EXTERNAL_ID,),
)
JAVDB_PRODUCTION_ASSET_LIST_OPERATION = _html_session_op(
    ProviderOperation.ASSET_LIST,
    # Operation host purpose must be METADATA; asset hosts listed separately.
    host_id=JAVDB_PRODUCTION_HOST_ID,
    path_template="/v/{external_id}",
    path_parameter=BusinessParameter.EXTERNAL_ID,
    required_parameters=(BusinessParameter.EXTERNAL_ID,),
    asset_host_ids=(JAVDB_PRODUCTION_ASSET_HOST_ID,),
)

JAVDB_PRODUCTION_APPROVAL = ProviderApproval(
    approval_id="javdb_metadata_production_v2",
    approval_version=APPROVAL_FORMAT_VERSION,
    scope=ProviderApprovalScope.PRODUCTION,
    provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
    display_name=JAVDB_PRODUCTION_CAPABILITIES.display_name,
    content_scope=JAVDB_PRODUCTION_CAPABILITIES.content_scope,
    product_fit=(
        "Video metadata SEARCH/DETAIL plus ASSET_LIST link descriptors for "
        "local-first catalog enrichment. Optional local DOWNLOAD is acquisition "
        "only after explicit user confirm. Comics/doujin use a separate package. "
        "No VIP/login bypass."
    ),
    lawful_access_basis=(
        "Operator must hold a lawful account/session and inject only their own "
        "provider session cookie. Cookie values are never stored in this approval. "
        + JAVDB_PRODUCTION_REGION_POLICY
        + " Attribution required: Yuukiy/JavSP, lmixture/JavdBviewed."
    ),
    terms_basis=(
        "Operator complies with site Terms and applicable law. Technical allowlist "
        "only. Raw HTML discarded after parse (DISCARD retention)."
    ),
    attribution_policy=ApprovalAttributionPolicy.REQUIRED,
    capabilities=JAVDB_PRODUCTION_CAPABILITIES.operations,
    hosts=(
        ApprovedHost(
            JAVDB_PRODUCTION_HOST_ID,
            JAVDB_PRODUCTION_HOST,
            ApprovedHostPurpose.METADATA,
            credential_allowed=False,
            port=443,
        ),
        ApprovedHost(
            JAVDB_PRODUCTION_ASSET_HOST_ID,
            JAVDB_PRODUCTION_HOST,
            ApprovedHostPurpose.ASSET,
            credential_allowed=False,
            port=443,
        ),
    ),
    operations=(
        JAVDB_PRODUCTION_SEARCH_OPERATION,
        JAVDB_PRODUCTION_DETAIL_OPERATION,
        JAVDB_PRODUCTION_ASSET_LIST_OPERATION,
    ),
    auth=ApprovedAuth(
        modes=(ProviderAuthMode.NONE, ProviderAuthMode.SESSION_COOKIE),
    ),
    asset_policy=ApprovedAssetPolicy(
        allowed_kinds=(SourceAssetKind.COVER, SourceAssetKind.PREVIEW),
        asset_host_ids=(JAVDB_PRODUCTION_ASSET_HOST_ID,),
        max_assets_per_item=MAX_PAGE_SIZE,
        locator_resolution_allowed=False,
    ),
    download_policy=ApprovedDownloadPolicy(),
    explicit_exclusions=_PRODUCTION_EXCLUSIONS,
)

JAVDB_PRODUCTION_ENDPOINT = ProviderEndpoint(
    provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
    hostname=JAVDB_PRODUCTION_HOST,
    capabilities=JAVDB_PRODUCTION_CAPABILITIES,
    operations=(
        EndpointOperation(
            ProviderOperation.SEARCH,
            "/search",
            None,
            query_parameters=((BusinessParameter.QUERY, "q"),),
            required_parameters=(BusinessParameter.QUERY,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            auth_requirement=ProviderAuthMode.NONE,
            cookie_policy=CookiePolicy.PROVIDER_SESSION,
            response_kind=ResponseKind.HTML,
            allowed_content_types=("text/html",),
            fixed_headers=(("X-Javdb-Contract", "production-metadata-v1"),),
            redirect_policy=RedirectPolicy.DENY,
        ),
        EndpointOperation(
            ProviderOperation.DETAIL,
            "/v/{external_id}",
            None,
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            auth_requirement=ProviderAuthMode.NONE,
            cookie_policy=CookiePolicy.PROVIDER_SESSION,
            response_kind=ResponseKind.HTML,
            allowed_content_types=("text/html",),
            fixed_headers=(("X-Javdb-Contract", "production-metadata-v1"),),
            redirect_policy=RedirectPolicy.DENY,
        ),
        EndpointOperation(
            ProviderOperation.ASSET_LIST,
            "/v/{external_id}",
            None,
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            auth_requirement=ProviderAuthMode.NONE,
            cookie_policy=CookiePolicy.PROVIDER_SESSION,
            response_kind=ResponseKind.HTML,
            allowed_content_types=("text/html",),
            fixed_headers=(("X-Javdb-Contract", "production-metadata-v1"),),
            redirect_policy=RedirectPolicy.DENY,
            allowed_asset_hosts=(JAVDB_PRODUCTION_HOST,),
        ),
    ),
)
