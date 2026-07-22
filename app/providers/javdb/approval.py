"""TEST_FIXTURE approval constants for JavDB-shaped metadata.

Hosts end with ``.invalid`` (required for TEST_FIXTURE). Path templates mirror
the real site contract studied offline:

- SEARCH GET /search?q=
- DETAIL GET /v/{external_id}  (slug as external_id)

Real hostnames (javdb.com, mirrors) are documented for a future PRODUCTION
approval only and are intentionally not listed here.
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

JAVDB_PROVIDER_KEY = "javdb_metadata"
JAVDB_METADATA_HOST = "metadata.javdb.invalid"
JAVDB_HOST_ID = "metadata"

# Path slug is the stable external_id for DETAIL (e.g. RM29z).
# Catalog numbers such as SSIS-001 are display/search fields only.

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


def _html_op(
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
        host_id=JAVDB_HOST_ID,
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
        rate_policy=ApprovedRatePolicy(
            provider_concurrency_limit=1,
            automatic_retry_limit=0,
        ),
        fixed_headers=(
            ApprovedFixedHeader("X-Javdb-Contract", "test-fixture-v1"),
        ),
        timeout_policy=ApprovedTimeoutPolicy(),
        path_parameter=path_parameter,
        query_parameters=query_parameters,
        required_parameters=required_parameters,
    )


JAVDB_CAPABILITIES = ProviderCapabilities(
    provider_key=JAVDB_PROVIDER_KEY,
    display_name="JavDB Metadata (test fixture)",
    content_scope="offline HTML fixtures shaped like JavDB search/detail pages",
    metadata=MetadataCapabilities(
        (ProviderOperation.SEARCH, ProviderOperation.DETAIL)
    ),
    auth=AuthCapabilities((ProviderAuthMode.NONE,)),
    attribution_required=True,
)

JAVDB_SEARCH_OPERATION = _html_op(
    ProviderOperation.SEARCH,
    path_template="/search",
    query_parameters=((BusinessParameter.QUERY, "q"),),
    required_parameters=(BusinessParameter.QUERY,),
)
JAVDB_DETAIL_OPERATION = _html_op(
    ProviderOperation.DETAIL,
    path_template="/v/{external_id}",
    path_parameter=BusinessParameter.EXTERNAL_ID,
    required_parameters=(BusinessParameter.EXTERNAL_ID,),
)

JAVDB_APPROVAL = ProviderApproval(
    approval_id="javdb_metadata_test_fixture_v1",
    approval_version=APPROVAL_FORMAT_VERSION,
    scope=ProviderApprovalScope.TEST_FIXTURE,
    provider_key=JAVDB_PROVIDER_KEY,
    display_name=JAVDB_CAPABILITIES.display_name,
    content_scope=JAVDB_CAPABILITIES.content_scope,
    product_fit="Video metadata SEARCH/DETAIL for local catalog enrichment",
    lawful_access_basis=(
        "TEST_FIXTURE only; synthetic HTML. Production access requires a separate "
        "PRODUCTION approval and operator lawful-access basis. Reference contracts: "
        "Yuukiy/JavSP, lmixture/JavdBviewed (attribution required)."
    ),
    terms_basis=(
        "Test fixture hosts under .invalid. Real-site Terms apply only under a "
        "future PRODUCTION approval; no production activation in this package."
    ),
    attribution_policy=ApprovalAttributionPolicy.REQUIRED,
    capabilities=JAVDB_CAPABILITIES.operations,
    hosts=(
        ApprovedHost(
            JAVDB_HOST_ID,
            JAVDB_METADATA_HOST,
            ApprovedHostPurpose.METADATA,
            credential_allowed=False,
            port=443,
        ),
    ),
    operations=(JAVDB_SEARCH_OPERATION, JAVDB_DETAIL_OPERATION),
    auth=ApprovedAuth(),
    asset_policy=ApprovedAssetPolicy(),
    download_policy=ApprovedDownloadPolicy(),
    explicit_exclusions=_EXCLUSIONS,
)

JAVDB_ENDPOINT = ProviderEndpoint(
    provider_key=JAVDB_PROVIDER_KEY,
    hostname=JAVDB_METADATA_HOST,
    capabilities=JAVDB_CAPABILITIES,
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
            cookie_policy=CookiePolicy.NONE,
            response_kind=ResponseKind.HTML,
            allowed_content_types=("text/html",),
            fixed_headers=(("X-Javdb-Contract", "test-fixture-v1"),),
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
            cookie_policy=CookiePolicy.NONE,
            response_kind=ResponseKind.HTML,
            allowed_content_types=("text/html",),
            fixed_headers=(("X-Javdb-Contract", "test-fixture-v1"),),
            redirect_policy=RedirectPolicy.DENY,
        ),
    ),
)
