"""PRODUCTION approval for nsfwpro factory key ``zuidapi-vod`` (MacCMS).

Host and path facts from nsfwpro ``providers/zuidapi/approval.json``.
Search + detail only; playback/download unauthorized.
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
    JsonTopLevel,
    MAX_PAGE_SIZE,
    MAX_RESPONSE_BYTES,
    ProviderEndpoint,
    RedirectPolicy,
    RequestEncoding,
    ResponseKind,
)

ZUIDAPI_PROVIDER_KEY = "zuidapi_vod"
ZUIDAPI_NSFWPRO_KEY = "zuidapi-vod"
ZUIDAPI_HOST = "api.zuidapi.com"
ZUIDAPI_HOST_ID = "metadata"

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


def _json_op(
    operation: ProviderOperation,
    *,
    path_template: str,
    query_parameters: tuple[tuple[BusinessParameter, str], ...] = (),
    required_parameters: tuple[BusinessParameter, ...] = (),
) -> ApprovedOperation:
    return ApprovedOperation(
        operation=operation,
        layer=operation.layer,
        host_id=ZUIDAPI_HOST_ID,
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
        fixed_headers=(
            ApprovedFixedHeader("X-Zuidapi-Contract", "maccms-vod-v1"),
        ),
        timeout_policy=ApprovedTimeoutPolicy(),
        query_parameters=query_parameters,
        required_parameters=required_parameters,
    )


ZUIDAPI_CAPABILITIES = ProviderCapabilities(
    provider_key=ZUIDAPI_PROVIDER_KEY,
    display_name="ZuidAPI MacCMS VOD",
    content_scope=(
        "MacCMS-style JSON SEARCH/DETAIL for VOD metadata; nsfwpro key zuidapi-vod; "
        "no playback resolve or VIP bypass"
    ),
    metadata=MetadataCapabilities(
        (ProviderOperation.SEARCH, ProviderOperation.DETAIL)
    ),
    auth=AuthCapabilities((ProviderAuthMode.NONE,)),
    attribution_required=True,
)

ZUIDAPI_APPROVAL = ProviderApproval(
    approval_id="zuidapi_vod_production_v1",
    approval_version=APPROVAL_FORMAT_VERSION,
    scope=ProviderApprovalScope.PRODUCTION,
    provider_key=ZUIDAPI_PROVIDER_KEY,
    display_name=ZUIDAPI_CAPABILITIES.display_name,
    content_scope=ZUIDAPI_CAPABILITIES.content_scope,
    product_fit=(
        "MacCMS list/detail metadata for local catalog enrichment. Playback lines "
        "in JSON are not resolved or downloaded in this package."
    ),
    lawful_access_basis=(
        "Operator assertion per nsfwpro zuidapi approval: end-user may only access "
        "data they lawfully hold rights to. No VIP/captcha/region bypass. "
        "Attribution: rapier15sapper/ew inventory (MacCMS path shape)."
    ),
    terms_basis=(
        "Unauthenticated collect API; operator responsible for Terms compliance. "
        "Raw JSON discarded after parse."
    ),
    attribution_policy=ApprovalAttributionPolicy.REQUIRED,
    capabilities=ZUIDAPI_CAPABILITIES.operations,
    hosts=(
        ApprovedHost(
            ZUIDAPI_HOST_ID,
            ZUIDAPI_HOST,
            ApprovedHostPurpose.METADATA,
        ),
    ),
    operations=(
        _json_op(
            ProviderOperation.SEARCH,
            path_template="/api.php/provide/vod",
            query_parameters=(
                (BusinessParameter.QUERY, "wd"),
                (BusinessParameter.PAGE, "pg"),
                (BusinessParameter.PAGE_SIZE, "limit"),
            ),
            required_parameters=(BusinessParameter.QUERY,),
        ),
        _json_op(
            ProviderOperation.DETAIL,
            path_template="/api.php/provide/vod",
            query_parameters=((BusinessParameter.EXTERNAL_ID, "ids"),),
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
        ),
    ),
    auth=ApprovedAuth(),
    asset_policy=ApprovedAssetPolicy(),
    download_policy=ApprovedDownloadPolicy(),
    explicit_exclusions=_EXCLUSIONS,
)

ZUIDAPI_ENDPOINT = ProviderEndpoint(
    provider_key=ZUIDAPI_PROVIDER_KEY,
    hostname=ZUIDAPI_HOST,
    capabilities=ZUIDAPI_CAPABILITIES,
    operations=(
        EndpointOperation(
            ProviderOperation.SEARCH,
            "/api.php/provide/vod",
            JsonTopLevel.OBJECT,
            query_parameters=(
                (BusinessParameter.QUERY, "wd"),
                (BusinessParameter.PAGE, "pg"),
                (BusinessParameter.PAGE_SIZE, "limit"),
            ),
            required_parameters=(BusinessParameter.QUERY,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            response_kind=ResponseKind.JSON,
            allowed_content_types=(
                "application/json",
                "application/*+json",
            ),
            fixed_headers=(
                ("X-Zuidapi-Contract", "maccms-vod-v1"),
            ),
            redirect_policy=RedirectPolicy.DENY,
        ),
        EndpointOperation(
            ProviderOperation.DETAIL,
            "/api.php/provide/vod",
            JsonTopLevel.OBJECT,
            query_parameters=((BusinessParameter.EXTERNAL_ID, "ids"),),
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            response_kind=ResponseKind.JSON,
            allowed_content_types=(
                "application/json",
                "application/*+json",
            ),
            fixed_headers=(
                ("X-Zuidapi-Contract", "maccms-vod-v1"),
            ),
            redirect_policy=RedirectPolicy.DENY,
        ),
    ),
)
