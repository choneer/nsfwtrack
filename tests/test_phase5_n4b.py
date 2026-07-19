from __future__ import annotations

import logging
import socket
from dataclasses import FrozenInstanceError, replace

import pytest

from app.source_adapters import (
    APPROVAL_FORMAT_VERSION,
    ApprovalAttributionPolicy,
    ApprovalValidationError,
    ApprovalValidationErrorCode,
    ApprovedAssetPolicy,
    ApprovedAuth,
    ApprovedDownloadPolicy,
    ApprovedFixedHeader,
    ApprovedHost,
    ApprovedHostPurpose,
    ApprovedOperation,
    ApprovedRatePolicy,
    ProviderApproval,
    ProviderApprovalScope,
    validate_approval_against_capabilities,
    validate_approval_against_endpoint,
    validate_approval_for_activation,
    validate_approval_secret_fields,
    validate_provider_approval,
)
from app.source_adapters.contracts import (
    AssetCapabilities,
    AuthCapabilities,
    DiscoveryCapabilities,
    DownloadCapabilities,
    MetadataCapabilities,
    ProviderAuthMode,
    ProviderCapabilities,
    ProviderCapabilityLayer,
    ProviderOperation,
    SourceAsset,
    SourceAssetKind,
)
from app.source_adapters.registry import (
    BusinessParameter,
    CookiePolicy,
    EndpointOperation,
    EndpointRegistry,
    HttpMethod,
    JsonTopLevel,
    MAX_PAGE_SIZE,
    MAX_RESPONSE_BYTES,
    PRODUCTION_ENDPOINT_REGISTRY,
    ProviderEndpoint,
    RedirectPolicy,
    RequestEncoding,
    ResponseKind,
)


PROVIDER_KEY = "approval_fixture"
METADATA_HOST = "metadata.approval.invalid"
ASSET_HOST = "assets.approval.invalid"
APPROVED_EXCLUSIONS = (
    ProviderOperation.AUTH_TEST,
    ProviderOperation.AUTH_LOGIN,
    ProviderOperation.AUTH_REFRESH,
    ProviderOperation.AUTH_REVOKE,
    ProviderOperation.AUTH_LOGOUT,
    ProviderOperation.DISCOVER,
    ProviderOperation.ASSET_RESOLVE,
    ProviderOperation.DOWNLOAD,
)


def _operation(
    operation: ProviderOperation,
    *,
    host_id: str = "metadata",
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
        fixed_headers=(
            (ApprovedFixedHeader("X-Fixture-Contract", "n4a"),)
            if operation is ProviderOperation.SEARCH
            else ()
        ),
        path_parameter=path_parameter,
        query_parameters=query_parameters,
        required_parameters=required_parameters,
        asset_host_ids=asset_host_ids,
    )


SEARCH_APPROVAL_OPERATION = _operation(
    ProviderOperation.SEARCH,
    path_template="/fixture/search",
    query_parameters=(
        (BusinessParameter.QUERY, "q"),
        (BusinessParameter.PAGE, "page"),
        (BusinessParameter.PAGE_SIZE, "limit"),
    ),
    required_parameters=(BusinessParameter.QUERY,),
)
DETAIL_APPROVAL_OPERATION = _operation(
    ProviderOperation.DETAIL,
    path_template="/fixture/records/{external_id}",
    path_parameter=BusinessParameter.EXTERNAL_ID,
    required_parameters=(BusinessParameter.EXTERNAL_ID,),
)
ASSET_LIST_APPROVAL_OPERATION = _operation(
    ProviderOperation.ASSET_LIST,
    path_template="/fixture/records/{external_id}/assets",
    path_parameter=BusinessParameter.EXTERNAL_ID,
    required_parameters=(BusinessParameter.EXTERNAL_ID,),
    asset_host_ids=("asset",),
)

CAPABILITIES = ProviderCapabilities(
    provider_key=PROVIDER_KEY,
    display_name="Approval Fixture Provider",
    content_scope="synthetic approval records only",
    metadata=MetadataCapabilities(
        (ProviderOperation.SEARCH, ProviderOperation.DETAIL)
    ),
    auth=AuthCapabilities((ProviderAuthMode.NONE,)),
    assets=AssetCapabilities(
        (ProviderOperation.ASSET_LIST,),
        (SourceAssetKind.COVER, SourceAssetKind.PREVIEW),
    ),
)

APPROVAL = ProviderApproval(
    approval_id="approval_fixture_v1",
    approval_version=APPROVAL_FORMAT_VERSION,
    scope=ProviderApprovalScope.TEST_FIXTURE,
    provider_key=PROVIDER_KEY,
    display_name=CAPABILITIES.display_name,
    content_scope=CAPABILITIES.content_scope,
    product_fit="synthetic fixture validation only",
    lawful_access_basis="synthetic test data only",
    terms_basis="synthetic test data only",
    attribution_policy=ApprovalAttributionPolicy.NOT_REQUIRED,
    capabilities=CAPABILITIES.operations,
    hosts=(
        ApprovedHost(
            "metadata",
            METADATA_HOST,
            ApprovedHostPurpose.METADATA,
        ),
        ApprovedHost(
            "asset",
            ASSET_HOST,
            ApprovedHostPurpose.ASSET,
        ),
    ),
    operations=(
        SEARCH_APPROVAL_OPERATION,
        DETAIL_APPROVAL_OPERATION,
        ASSET_LIST_APPROVAL_OPERATION,
    ),
    auth=ApprovedAuth(),
    asset_policy=ApprovedAssetPolicy(
        allowed_kinds=(SourceAssetKind.COVER, SourceAssetKind.PREVIEW),
        asset_host_ids=("asset",),
        max_assets_per_item=MAX_PAGE_SIZE,
    ),
    download_policy=ApprovedDownloadPolicy(),
    explicit_exclusions=APPROVED_EXCLUSIONS,
)

ENDPOINT = ProviderEndpoint(
    provider_key=PROVIDER_KEY,
    hostname=METADATA_HOST,
    capabilities=CAPABILITIES,
    operations=(
        EndpointOperation(
            ProviderOperation.SEARCH,
            "/fixture/search",
            JsonTopLevel.OBJECT,
            query_parameters=(
                (BusinessParameter.QUERY, "q"),
                (BusinessParameter.PAGE, "page"),
                (BusinessParameter.PAGE_SIZE, "limit"),
            ),
            required_parameters=(BusinessParameter.QUERY,),
            fixed_headers=(("X-Fixture-Contract", "n4a"),),
        ),
        EndpointOperation(
            ProviderOperation.DETAIL,
            "/fixture/records/{external_id}",
            JsonTopLevel.OBJECT,
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
        ),
        EndpointOperation(
            ProviderOperation.ASSET_LIST,
            "/fixture/records/{external_id}/assets",
            JsonTopLevel.OBJECT,
            path_parameter=BusinessParameter.EXTERNAL_ID,
            required_parameters=(BusinessParameter.EXTERNAL_ID,),
            allowed_asset_hosts=(ASSET_HOST,),
        ),
    ),
)


def _approval_with_operations(
    operations: tuple[ApprovedOperation, ...],
    capabilities: tuple[ProviderOperation, ...],
    *,
    exclusions: tuple[ProviderOperation, ...] = APPROVED_EXCLUSIONS,
) -> ProviderApproval:
    return replace(
        APPROVAL,
        operations=operations,
        capabilities=capabilities,
        explicit_exclusions=exclusions,
    )


def test_approval_is_immutable_typed_and_separate_from_production_registry() -> None:
    assert PRODUCTION_ENDPOINT_REGISTRY is not EndpointRegistry(())
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    validate_provider_approval(APPROVAL)
    with pytest.raises(FrozenInstanceError):
        APPROVAL.provider_key = "changed"  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        APPROVAL.extra = "rejected"  # type: ignore[attr-defined]
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_provider_approval(object())
    assert exc_info.value.code is ApprovalValidationErrorCode.INVALID


@pytest.mark.parametrize(
    "hostname",
    (
        "*.approval.invalid",
        "approval.invalid/path",
        "https://approval.invalid",
        "approval.invalid?query",
        "approval.invalid#fragment",
        "127.0.0.1",
        "::1",
    ),
)
def test_approved_host_rejects_wildcard_ip_and_url_forms(hostname: str) -> None:
    with pytest.raises(ValueError):
        ApprovedHost("bad_host", hostname, ApprovedHostPurpose.METADATA)


def test_approval_rejects_invalid_shape_and_duplicate_or_cross_layer_operations() -> None:
    with pytest.raises(ValueError):
        ApprovedHost("non443", METADATA_HOST, ApprovedHostPurpose.METADATA, port=8443)
    with pytest.raises(ValueError, match="duplicated"):
        replace(
            APPROVAL,
            hosts=(
                APPROVAL.hosts[0],
                replace(APPROVAL.hosts[1], host_id=APPROVAL.hosts[0].host_id),
            ),
        )
    with pytest.raises(ValueError, match="another capability layer"):
        ApprovedOperation(
            operation=ProviderOperation.SEARCH,
            layer=ProviderCapabilityLayer.ASSET,
            host_id="metadata",
            path_template="/fixture/search",
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.NONE,
            auth_requirement=ProviderAuthMode.NONE,
            cookie_policy=CookiePolicy.NONE,
            response_kind=ResponseKind.JSON,
            expected_top_level=JsonTopLevel.OBJECT,
            allowed_content_types=("application/json",),
            response_limit_bytes=1,
            page_size_limit=1,
            redirect_policy=RedirectPolicy.DENY,
            rate_policy=ApprovedRatePolicy(),
        )
    with pytest.raises(ValueError, match="operation is duplicated"):
        replace(
            APPROVAL,
            operations=(
                SEARCH_APPROVAL_OPERATION,
                SEARCH_APPROVAL_OPERATION,
                ASSET_LIST_APPROVAL_OPERATION,
            ),
        )
    with pytest.raises(ValueError):
        replace(APPROVAL, capabilities=())
    with pytest.raises(ValueError, match="production approval"):
        replace(APPROVAL, scope=ProviderApprovalScope.PRODUCTION)


def test_approval_requires_metadata_and_rejects_unapproved_references() -> None:
    with pytest.raises(ValueError, match="metadata"):
        replace(
            APPROVAL,
            capabilities=(ProviderOperation.ASSET_LIST,),
            operations=(ASSET_LIST_APPROVAL_OPERATION,),
        )
    with pytest.raises(ValueError, match="unapproved host"):
        replace(
            APPROVAL,
            operations=(
                replace(ASSET_LIST_APPROVAL_OPERATION, asset_host_ids=("missing",)),
                SEARCH_APPROVAL_OPERATION,
                DETAIL_APPROVAL_OPERATION,
            ),
        )


def test_approval_requires_auth_and_cookie_policy_consistency() -> None:
    protected = replace(
        SEARCH_APPROVAL_OPERATION,
        auth_requirement=ProviderAuthMode.API_TOKEN,
    )
    with pytest.raises(ValueError, match="auth mode"):
        _approval_with_operations(
            (protected, DETAIL_APPROVAL_OPERATION, ASSET_LIST_APPROVAL_OPERATION),
            CAPABILITIES.operations,
        )
    session = replace(
        SEARCH_APPROVAL_OPERATION,
        cookie_policy=CookiePolicy.PROVIDER_SESSION,
    )
    with pytest.raises(ValueError, match="session cookie"):
        _approval_with_operations(
            (session, DETAIL_APPROVAL_OPERATION, ASSET_LIST_APPROVAL_OPERATION),
            CAPABILITIES.operations,
        )
    auth_operation = replace(
        SEARCH_APPROVAL_OPERATION,
        operation=ProviderOperation.AUTH_TEST,
        layer=ProviderCapabilityLayer.AUTH,
        host_id="auth",
    )
    with pytest.raises(ValueError, match="credentialed mode"):
        replace(
            APPROVAL,
            hosts=(
                *APPROVAL.hosts,
                ApprovedHost(
                    "auth",
                    "auth.approval.invalid",
                    ApprovedHostPurpose.AUTH,
                    credential_allowed=True,
                ),
            ),
            operations=(
                auth_operation,
                DETAIL_APPROVAL_OPERATION,
                ASSET_LIST_APPROVAL_OPERATION,
            ),
            capabilities=(
                ProviderOperation.AUTH_TEST,
                ProviderOperation.DETAIL,
                ProviderOperation.ASSET_LIST,
            ),
            explicit_exclusions=tuple(
                operation
                for operation in APPROVED_EXCLUSIONS
                if operation is not ProviderOperation.AUTH_TEST
            ),
        )

    redirect_operation = replace(
        SEARCH_APPROVAL_OPERATION,
        redirect_policy=RedirectPolicy.EXACT_ALLOWLIST,
        redirect_host_ids=("missing",),
        max_redirects=1,
    )
    with pytest.raises(ValueError, match="unapproved host"):
        _approval_with_operations(
            (redirect_operation, DETAIL_APPROVAL_OPERATION, ASSET_LIST_APPROVAL_OPERATION),
            CAPABILITIES.operations,
        )


def test_approval_auth_policy_requires_oauth_state_pkce_and_no_password_value() -> None:
    with pytest.raises(ValueError, match="state and PKCE"):
        ApprovedAuth((ProviderAuthMode.OAUTH,))
    with pytest.raises(ValueError, match="username/password"):
        ApprovedAuth(password_storage_allowed=True)
    auth = ApprovedAuth(
        (ProviderAuthMode.OAUTH, ProviderAuthMode.API_TOKEN),
        oauth_state_required=True,
        oauth_pkce_required=True,
    )
    assert auth.password_storage_allowed is False


def test_matching_approval_capabilities_and_endpoint_validate_without_side_effects() -> None:
    validate_provider_approval(APPROVAL)
    validate_approval_against_capabilities(APPROVAL, CAPABILITIES)
    validate_approval_against_endpoint(APPROVAL, ENDPOINT)


def test_capability_validator_rejects_provider_key_capability_and_attribution_mismatch() -> None:
    other = replace(CAPABILITIES, provider_key="other_fixture")
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_capabilities(APPROVAL, other)
    assert exc_info.value.code is ApprovalValidationErrorCode.PROVIDER_MISMATCH

    fewer = replace(
        CAPABILITIES,
        metadata=MetadataCapabilities((ProviderOperation.SEARCH,)),
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_capabilities(APPROVAL, fewer)
    assert exc_info.value.code is ApprovalValidationErrorCode.CAPABILITY_MISMATCH

    attributed = replace(CAPABILITIES, attribution_required=True)
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_capabilities(APPROVAL, attributed)
    assert exc_info.value.code is ApprovalValidationErrorCode.CAPABILITY_MISMATCH


def test_capability_validator_rejects_explicitly_excluded_runtime_operation() -> None:
    expanded = replace(
        CAPABILITIES,
        discovery=DiscoveryCapabilities((ProviderOperation.DISCOVER,)),
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_capabilities(APPROVAL, expanded)
    assert exc_info.value.code is ApprovalValidationErrorCode.CAPABILITY_MISMATCH


def test_download_policy_is_complete_and_compared_to_runtime_capabilities() -> None:
    with pytest.raises(ValueError, match="incomplete"):
        ApprovedDownloadPolicy(enabled=True)

    download_operation = ApprovedOperation(
        operation=ProviderOperation.DOWNLOAD,
        layer=ProviderCapabilityLayer.DOWNLOAD,
        host_id="asset",
        path_template="/fixture/download/{external_id}",
        method=HttpMethod.GET,
        request_encoding=RequestEncoding.NONE,
        auth_requirement=ProviderAuthMode.NONE,
        cookie_policy=CookiePolicy.NONE,
        response_kind=ResponseKind.FILE,
        expected_top_level=None,
        allowed_content_types=("application/octet-stream",),
        response_limit_bytes=1_024,
        page_size_limit=1,
        redirect_policy=RedirectPolicy.DENY,
        rate_policy=ApprovedRatePolicy(),
        path_parameter=BusinessParameter.EXTERNAL_ID,
        required_parameters=(BusinessParameter.EXTERNAL_ID,),
        asset_host_ids=("asset",),
    )
    download_policy = ApprovedDownloadPolicy(
        enabled=True,
        allowed_kinds=(SourceAssetKind.MEDIA,),
        asset_host_ids=("asset",),
        max_files_per_request=1,
        max_total_bytes=2_048,
        checksum_required=True,
    )
    approval = replace(
        APPROVAL,
        capabilities=(*APPROVAL.capabilities, ProviderOperation.DOWNLOAD),
        operations=(*APPROVAL.operations, download_operation),
        download_policy=download_policy,
        explicit_exclusions=tuple(
            operation
            for operation in APPROVED_EXCLUSIONS
            if operation is not ProviderOperation.DOWNLOAD
        ),
    )
    matching = replace(
        CAPABILITIES,
        downloads=DownloadCapabilities(
            (ProviderOperation.DOWNLOAD,),
            (SourceAssetKind.MEDIA,),
        ),
    )
    validate_approval_against_capabilities(approval, matching)

    mismatch = replace(
        matching,
        downloads=DownloadCapabilities(
            (ProviderOperation.DOWNLOAD,),
            (SourceAssetKind.ATTACHMENT,),
        ),
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_capabilities(approval, mismatch)
    assert (
        exc_info.value.code
        is ApprovalValidationErrorCode.DOWNLOAD_POLICY_MISMATCH
    )


@pytest.mark.parametrize("field", ("method", "response_kind", "path_template"))
def test_endpoint_validator_rejects_operation_policy_mismatch(field: str) -> None:
    runtime_operation = ENDPOINT.operation(ProviderOperation.SEARCH)
    assert runtime_operation is not None
    if field == "method":
        changed = replace(
            runtime_operation,
            method=HttpMethod.POST,
            request_encoding=RequestEncoding.JSON,
            query_parameters=(
                (BusinessParameter.PAGE, "page"),
                (BusinessParameter.PAGE_SIZE, "limit"),
            ),
            body_parameters=((BusinessParameter.QUERY, "query"),),
            required_parameters=(BusinessParameter.QUERY,),
        )
    elif field == "response_kind":
        changed = replace(
            runtime_operation,
            response_kind=ResponseKind.HTML,
            expected_top_level=None,
            allowed_content_types=("text/html",),
        )
    else:
        changed = replace(runtime_operation, path_template="/fixture/changed")
    endpoint = replace(
        ENDPOINT,
        capabilities=replace(
            CAPABILITIES,
            metadata=MetadataCapabilities(
                (ProviderOperation.SEARCH, ProviderOperation.DETAIL)
            ),
        ),
        operations=(changed, ENDPOINT.operation(ProviderOperation.DETAIL), ENDPOINT.operation(ProviderOperation.ASSET_LIST)),  # type: ignore[arg-type]
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(APPROVAL, endpoint)
    assert exc_info.value.code is ApprovalValidationErrorCode.OPERATION_MISMATCH


def test_endpoint_validator_rejects_host_auth_asset_and_limit_mismatch() -> None:
    host_endpoint = replace(ENDPOINT, hostname="other.approval.invalid")
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(APPROVAL, host_endpoint)
    assert exc_info.value.code is ApprovalValidationErrorCode.HOST_MISMATCH

    redirect_endpoint = replace(
        ENDPOINT,
        operations=(
            replace(
                ENDPOINT.operations[0],
                redirect_policy=RedirectPolicy.EXACT_ALLOWLIST,
                redirect_hosts=("redirect.approval.invalid",),
                max_redirects=1,
            ),
            *ENDPOINT.operations[1:],
        ),
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(APPROVAL, redirect_endpoint)
    assert exc_info.value.code is ApprovalValidationErrorCode.HOST_MISMATCH

    auth_capabilities = replace(
        CAPABILITIES,
        auth=AuthCapabilities((ProviderAuthMode.NONE, ProviderAuthMode.API_TOKEN)),
    )
    search = ENDPOINT.operation(ProviderOperation.SEARCH)
    assert search is not None
    auth_endpoint = replace(
        ENDPOINT,
        capabilities=auth_capabilities,
        operations=(
            replace(search, auth_requirement=ProviderAuthMode.API_TOKEN),
            ENDPOINT.operation(ProviderOperation.DETAIL),
            ENDPOINT.operation(ProviderOperation.ASSET_LIST),
        ),  # type: ignore[arg-type]
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(APPROVAL, auth_endpoint)
    assert exc_info.value.code is ApprovalValidationErrorCode.AUTH_MISMATCH

    cookie_capabilities = replace(
        CAPABILITIES,
        auth=AuthCapabilities(
            (ProviderAuthMode.NONE, ProviderAuthMode.SESSION_COOKIE)
        ),
    )
    cookie_endpoint = replace(
        ENDPOINT,
        capabilities=cookie_capabilities,
        operations=(
            replace(search, cookie_policy=CookiePolicy.PROVIDER_SESSION),
            ENDPOINT.operation(ProviderOperation.DETAIL),
            ENDPOINT.operation(ProviderOperation.ASSET_LIST),
        ),  # type: ignore[arg-type]
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(APPROVAL, cookie_endpoint)
    assert exc_info.value.code is ApprovalValidationErrorCode.AUTH_MISMATCH

    asset = ENDPOINT.operation(ProviderOperation.ASSET_LIST)
    assert asset is not None
    asset_endpoint = replace(
        ENDPOINT,
        operations=(
            ENDPOINT.operation(ProviderOperation.SEARCH),
            ENDPOINT.operation(ProviderOperation.DETAIL),
            replace(asset, allowed_asset_hosts=("other-assets.approval.invalid",)),
        ),  # type: ignore[arg-type]
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(APPROVAL, asset_endpoint)
    assert exc_info.value.code is ApprovalValidationErrorCode.ASSET_POLICY_MISMATCH

    fewer_endpoint = replace(
        ENDPOINT,
        capabilities=replace(
            CAPABILITIES,
            metadata=MetadataCapabilities((ProviderOperation.SEARCH,)),
            assets=AssetCapabilities(),
        ),
        operations=(search,),
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(APPROVAL, fewer_endpoint)
    assert exc_info.value.code is ApprovalValidationErrorCode.OPERATION_MISMATCH

    limited_approval = _approval_with_operations(
        (
            replace(SEARCH_APPROVAL_OPERATION, response_limit_bytes=512),
            DETAIL_APPROVAL_OPERATION,
            ASSET_LIST_APPROVAL_OPERATION,
        ),
        CAPABILITIES.operations,
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(limited_approval, ENDPOINT)
    assert exc_info.value.code is ApprovalValidationErrorCode.OPERATION_MISMATCH


def test_endpoint_operation_set_mismatch_is_rejected_before_runtime_capability_check() -> None:
    expanded_capabilities = replace(
        CAPABILITIES,
        discovery=DiscoveryCapabilities((ProviderOperation.DISCOVER,)),
    )
    expanded_operation = EndpointOperation(
        ProviderOperation.DISCOVER,
        "/fixture/discover",
        JsonTopLevel.OBJECT,
    )
    endpoint = replace(
        ENDPOINT,
        capabilities=expanded_capabilities,
        operations=(*ENDPOINT.operations, expanded_operation),
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(APPROVAL, endpoint)
    assert exc_info.value.code is ApprovalValidationErrorCode.OPERATION_MISMATCH


def test_endpoint_validator_compares_approval_to_runtime_rate_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.outbound_http.PROVIDER_CONCURRENCY_LIMIT",
        2,
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(APPROVAL, ENDPOINT)
    assert exc_info.value.code is ApprovalValidationErrorCode.OPERATION_MISMATCH


def test_fixture_approval_cannot_be_activated_and_validator_does_not_call_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_: object, **__: object) -> object:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_for_activation(APPROVAL, CAPABILITIES, ENDPOINT)
    assert exc_info.value.code is ApprovalValidationErrorCode.INVALID
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()


def test_unimplemented_approval_capability_is_blocked_before_fixture_scope_check() -> None:
    unsupported_operation = replace(
        SEARCH_APPROVAL_OPERATION,
        operation=ProviderOperation.DISCOVER,
        layer=ProviderCapabilityLayer.DISCOVERY,
        path_template="/fixture/discover",
        fixed_headers=(),
    )
    unsupported = _approval_with_operations(
        (
            SEARCH_APPROVAL_OPERATION,
            DETAIL_APPROVAL_OPERATION,
            ASSET_LIST_APPROVAL_OPERATION,
            unsupported_operation,
        ),
        (
            ProviderOperation.SEARCH,
            ProviderOperation.DETAIL,
            ProviderOperation.ASSET_LIST,
            ProviderOperation.DISCOVER,
        ),
        exclusions=tuple(
            operation
            for operation in APPROVED_EXCLUSIONS
            if operation is not ProviderOperation.DISCOVER
        ),
    )
    expanded_capabilities = replace(
        CAPABILITIES,
        discovery=DiscoveryCapabilities((ProviderOperation.DISCOVER,)),
    )
    expanded_endpoint = replace(
        ENDPOINT,
        capabilities=expanded_capabilities,
        operations=(
            *ENDPOINT.operations,
            EndpointOperation(
                ProviderOperation.DISCOVER,
                "/fixture/discover",
                JsonTopLevel.OBJECT,
                query_parameters=(
                    (BusinessParameter.QUERY, "q"),
                    (BusinessParameter.PAGE, "page"),
                    (BusinessParameter.PAGE_SIZE, "limit"),
                ),
                required_parameters=(BusinessParameter.QUERY,),
            ),
        ),
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_for_activation(
            unsupported,
            expanded_capabilities,
            expanded_endpoint,
        )
    assert exc_info.value.code is ApprovalValidationErrorCode.INCOMPLETE


def test_secret_field_boundary_rejects_markers_without_echoing_them() -> None:
    marker = "synthetic-secret-marker"
    for field in (
        "password_value",
        "token_value",
        "cookie_value",
        "secret_value",
    ):
        with pytest.raises(ApprovalValidationError) as exc_info:
            validate_approval_secret_fields({field: marker})
        assert exc_info.value.code is ApprovalValidationErrorCode.CONTAINS_SECRET
        assert marker not in str(exc_info.value)
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_secret_fields({"nested": {"unknown": object()}})
    assert exc_info.value.code is ApprovalValidationErrorCode.INVALID

    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_secret_fields({"numeric": float("nan")})
    assert exc_info.value.code is ApprovalValidationErrorCode.INVALID


def test_validator_does_not_log_approval_text_or_secret_markers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "synthetic-approval-marker"
    with caplog.at_level(logging.DEBUG):
        validate_provider_approval(APPROVAL)
        validate_approval_secret_fields({"note": marker})
    assert marker not in caplog.text
    assert repr(APPROVAL) not in caplog.text


def test_asset_id_is_opaque_and_external_id_compatibility_is_unchanged() -> None:
    forbidden = (
        "https://opaque.invalid/path",
        "http://opaque.invalid/path",
        "file:/path",
        "data:value",
        "//host/path",
        "/absolute/path",
        r"\windows\path",
        r"C:\path",
        "../relative",
        "./relative",
        "folder/file",
        r"folder\file",
        ".",
        "..",
        "a..b",
        "with space",
        "tab\tvalue",
        "a:b",
    )
    for asset_id in forbidden:
        with pytest.raises(ValueError):
            SourceAsset(
                provider_key=PROVIDER_KEY,
                external_id="../external id remains compatible",
                asset_id=asset_id,
                kind=SourceAssetKind.COVER,
            )
    asset = SourceAsset(
        provider_key=PROVIDER_KEY,
        external_id="../external id remains compatible",
        asset_id="asset_01.~preview",
        kind=SourceAssetKind.PREVIEW,
    )
    assert asset.external_id == "../external id remains compatible"
    assert asset.asset_id == "asset_01.~preview"
