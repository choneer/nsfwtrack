from __future__ import annotations

import logging
import socket
from dataclasses import FrozenInstanceError, replace

import pytest

from app.services.outbound_http import (
    CONNECT_TIMEOUT_SECONDS,
    TOTAL_TIMEOUT_SECONDS,
)
from app.source_adapters import (
    APPROVAL_FORMAT_VERSION,
    ApprovalValidationError,
    ApprovalValidationErrorCode,
    ApprovedErrorMappingProfile,
    ApprovedFixedHeader,
    ApprovedHost,
    ApprovedHostPurpose,
    ApprovedOperation,
    ApprovedRawPayloadRetention,
    ApprovedTimeoutPolicy,
    ProviderApproval,
    ProviderApprovalScope,
    ProviderEndpoint,
    validate_approval_against_endpoint,
    validate_approval_for_activation,
    validate_provider_approval,
)
from app.source_adapters.contracts import ProviderOperation
from app.source_adapters.registry import PRODUCTION_ENDPOINT_REGISTRY
from tests.test_phase5_n4b import (
    APPROVAL,
    ASSET_HOST,
    ASSET_LIST_APPROVAL_OPERATION,
    CAPABILITIES,
    DETAIL_APPROVAL_OPERATION,
    ENDPOINT,
    METADATA_HOST,
    SEARCH_APPROVAL_OPERATION,
)


PUBLIC_HEADER = ApprovedFixedHeader("X-Public-Version", "2026-07")
SECOND_PUBLIC_HEADER = ApprovedFixedHeader("X-Contract-Revision", "v1")
PRODUCTION_METADATA_HOST = "metadata.n4d-a.test"
PRODUCTION_ASSET_HOST = "assets.n4d-a.test"


def _approval_with_search(search: ApprovedOperation) -> ProviderApproval:
    return replace(
        APPROVAL,
        operations=(
            search,
            DETAIL_APPROVAL_OPERATION,
            ASSET_LIST_APPROVAL_OPERATION,
        ),
    )


def _endpoint_with_search_headers(
    headers: tuple[tuple[str, str], ...],
) -> ProviderEndpoint:
    return replace(
        ENDPOINT,
        operations=(
            replace(ENDPOINT.operations[0], fixed_headers=headers),
            *ENDPOINT.operations[1:],
        ),
    )


def _production_pair(
    retention: ApprovedRawPayloadRetention = ApprovedRawPayloadRetention.DISCARD,
) -> tuple[ProviderApproval, ProviderEndpoint]:
    operations = tuple(
        replace(operation, raw_payload_retention=retention)
        for operation in APPROVAL.operations
    )
    approval = replace(
        APPROVAL,
        scope=ProviderApprovalScope.PRODUCTION,
        hosts=(
            ApprovedHost(
                "metadata",
                PRODUCTION_METADATA_HOST,
                ApprovedHostPurpose.METADATA,
            ),
            ApprovedHost(
                "asset",
                PRODUCTION_ASSET_HOST,
                ApprovedHostPurpose.ASSET,
            ),
        ),
        operations=operations,
    )
    endpoint_operations = tuple(
        replace(
            operation,
            allowed_asset_hosts=(PRODUCTION_ASSET_HOST,),
        )
        if operation.operation is ProviderOperation.ASSET_LIST
        else operation
        for operation in ENDPOINT.operations
    )
    endpoint = replace(
        ENDPOINT,
        hostname=PRODUCTION_METADATA_HOST,
        operations=endpoint_operations,
    )
    return approval, endpoint


def test_n4d_a_models_are_frozen_slotted_typed_and_format_v1() -> None:
    timeout = ApprovedTimeoutPolicy()
    assert APPROVAL_FORMAT_VERSION == 1
    assert SEARCH_APPROVAL_OPERATION.fixed_headers == (
        ApprovedFixedHeader("X-Fixture-Contract", "n4a"),
    )
    assert DETAIL_APPROVAL_OPERATION.fixed_headers == ()
    assert timeout.connect_timeout_seconds == CONNECT_TIMEOUT_SECONDS == 3.0
    assert timeout.total_timeout_seconds == TOTAL_TIMEOUT_SECONDS == 10.0
    assert (
        SEARCH_APPROVAL_OPERATION.error_mapping_profile
        is ApprovedErrorMappingProfile.SHARED_OUTBOUND_V1
    )
    assert (
        SEARCH_APPROVAL_OPERATION.raw_payload_retention
        is ApprovedRawPayloadRetention.DISCARD
    )
    for value in (PUBLIC_HEADER, timeout, SEARCH_APPROVAL_OPERATION):
        assert not hasattr(value, "__dict__")
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            value.extra = "forbidden"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "name",
    [
        "Accept",
        "Accept-Encoding",
        "Authorization",
        "Connection",
        "Content-Length",
        "Content-Type",
        "Cookie",
        "Host",
        "Proxy-Authorization",
        "Set-Cookie",
        "Transfer-Encoding",
        "X-API-Key",
        "API-Key",
        "X-Auth-Token",
        "X-Access-Token",
        "X-Refresh-Token",
        "X-Client-Secret",
        "X-Session-Id",
        "X-Credential",
    ],
)
def test_fixed_header_rejects_forbidden_and_credential_like_names(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        ApprovedFixedHeader(name, "public-value")


def test_public_header_words_are_not_rejected_by_credential_substrings() -> None:
    assert ApprovedFixedHeader("X-Author-Version", "v1").value == "v1"


@pytest.mark.parametrize(
    "value",
    [
        "Bearer synthetic-marker",
        "bearer synthetic-marker",
        "Basic synthetic-marker",
        "Token synthetic-marker",
        "ApiKey synthetic-marker",
        "APIKEY synthetic-marker",
    ],
)
def test_fixed_header_rejects_authentication_value_forms(value: str) -> None:
    with pytest.raises(ValueError, match="authentication") as exc_info:
        ApprovedFixedHeader("X-Public-Version", value)
    assert "synthetic-marker" not in str(exc_info.value)


@pytest.mark.parametrize(
    "name,value",
    [
        ("", "value"),
        ("1-Invalid", "value"),
        ("X_Invalid", "value"),
        ("X-Public", ""),
        ("X-Public", "line\rbreak"),
        ("X-Public", "line\nbreak"),
        ("X-Public", "nul\x00break"),
        ("X-Public", "\x7f"),
        ("X-Public", "v" * 513),
    ],
)
def test_fixed_header_rejects_invalid_grammar_or_value(name: str, value: str) -> None:
    with pytest.raises(ValueError):
        ApprovedFixedHeader(name, value)


def test_fixed_header_tuple_is_typed_and_rejects_case_insensitive_duplicates() -> None:
    with pytest.raises(TypeError, match="ApprovedFixedHeader"):
        replace(
            SEARCH_APPROVAL_OPERATION,
            fixed_headers=(("X-Public-Version", "v1"),),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="ApprovedFixedHeader"):
        replace(
            SEARCH_APPROVAL_OPERATION,
            fixed_headers=[PUBLIC_HEADER],  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="duplicate"):
        replace(
            SEARCH_APPROVAL_OPERATION,
            fixed_headers=(
                ApprovedFixedHeader("X-Public-Version", "v1"),
                ApprovedFixedHeader("x-public-version", "v1"),
            ),
        )


def test_fixed_header_exact_match_ignores_name_case_and_order() -> None:
    approval = _approval_with_search(
        replace(
            SEARCH_APPROVAL_OPERATION,
            fixed_headers=(
                SECOND_PUBLIC_HEADER,
                ApprovedFixedHeader("x-public-version", "2026-07"),
                ApprovedFixedHeader("x-fixture-contract", "n4a"),
            ),
        )
    )
    endpoint = _endpoint_with_search_headers(
        (
            ("X-PUBLIC-VERSION", "2026-07"),
            ("X-Fixture-Contract", "n4a"),
            ("x-contract-revision", "v1"),
        )
    )

    validate_approval_against_endpoint(approval, endpoint)


@pytest.mark.parametrize(
    "approved_headers,runtime_headers",
    [
        (
            (ApprovedFixedHeader("X-Fixture-Contract", "n4a"),),
            (
                ("X-Fixture-Contract", "n4a"),
                ("X-Public-Version", "v1"),
            ),
        ),
        (
            (
                ApprovedFixedHeader("X-Fixture-Contract", "n4a"),
                ApprovedFixedHeader("X-Public-Version", "v1"),
            ),
            (("X-Fixture-Contract", "n4a"),),
        ),
        (
            (ApprovedFixedHeader("X-Fixture-Contract", "n4a"),),
            (("X-Fixture-Contract-Renamed", "n4a"),),
        ),
        (
            (ApprovedFixedHeader("X-Fixture-Contract", "n4a"),),
            (("X-Fixture-Contract", "N4A"),),
        ),
    ],
    ids=("runtime-added", "runtime-removed", "name-changed", "value-changed"),
)
def test_fixed_header_add_remove_rename_or_value_change_fails_exact_match(
    approved_headers: tuple[ApprovedFixedHeader, ...],
    runtime_headers: tuple[tuple[str, str], ...],
) -> None:
    approval = _approval_with_search(
        replace(SEARCH_APPROVAL_OPERATION, fixed_headers=approved_headers)
    )
    endpoint = _endpoint_with_search_headers(runtime_headers)

    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(approval, endpoint)
    assert exc_info.value.code is ApprovalValidationErrorCode.OPERATION_MISMATCH


def test_header_mismatch_error_and_logs_do_not_expose_value_marker(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "synthetic-public-header-marker"
    approval = _approval_with_search(
        replace(
            SEARCH_APPROVAL_OPERATION,
            fixed_headers=(ApprovedFixedHeader("X-Public-Version", marker),),
        )
    )
    endpoint = _endpoint_with_search_headers((("X-Public-Version", "different"),))

    with caplog.at_level(logging.INFO), pytest.raises(
        ApprovalValidationError
    ) as exc_info:
        validate_approval_against_endpoint(approval, endpoint)
    assert exc_info.value.code is ApprovalValidationErrorCode.OPERATION_MISMATCH
    assert marker not in str(exc_info.value)
    assert marker not in caplog.text
    assert marker not in repr(approval.operations[0].fixed_headers[0])
    assert marker not in repr(approval.operations[0])


@pytest.mark.parametrize(
    "kwargs,expected_exception",
    [
        ({"connect_timeout_seconds": True}, TypeError),
        ({"total_timeout_seconds": False}, TypeError),
        ({"connect_timeout_seconds": 0.0}, ValueError),
        ({"connect_timeout_seconds": -1.0}, ValueError),
        ({"total_timeout_seconds": 0.0}, ValueError),
        ({"connect_timeout_seconds": float("nan")}, ValueError),
        ({"total_timeout_seconds": float("nan")}, ValueError),
        ({"connect_timeout_seconds": float("inf")}, ValueError),
        ({"total_timeout_seconds": float("inf")}, ValueError),
        (
            {"connect_timeout_seconds": 4.0, "total_timeout_seconds": 3.0},
            ValueError,
        ),
        ({"connect_timeout_seconds": 61.0}, ValueError),
        ({"total_timeout_seconds": 301.0}, ValueError),
    ],
)
def test_timeout_policy_rejects_invalid_values(
    kwargs: dict[str, object],
    expected_exception: type[Exception],
) -> None:
    with pytest.raises(expected_exception):
        ApprovedTimeoutPolicy(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "constant,value",
    [
        ("CONNECT_TIMEOUT_SECONDS", 4.0),
        ("TOTAL_TIMEOUT_SECONDS", 11.0),
    ],
)
def test_timeout_must_exactly_match_shared_client_constants(
    monkeypatch: pytest.MonkeyPatch,
    constant: str,
    value: float,
) -> None:
    monkeypatch.setattr(f"app.services.outbound_http.{constant}", value)
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(APPROVAL, ENDPOINT)
    assert exc_info.value.code is ApprovalValidationErrorCode.OPERATION_MISMATCH


def test_timeout_policy_field_is_typed() -> None:
    with pytest.raises(TypeError, match="ApprovedTimeoutPolicy"):
        replace(
            SEARCH_APPROVAL_OPERATION,
            timeout_policy={"connect": 3.0},  # type: ignore[arg-type]
        )


def test_error_mapping_profile_is_bounded_typed_and_exact() -> None:
    assert tuple(ApprovedErrorMappingProfile) == (
        ApprovedErrorMappingProfile.SHARED_OUTBOUND_V1,
    )
    assert ApprovedErrorMappingProfile.SHARED_OUTBOUND_V1.value == "shared_outbound_v1"
    with pytest.raises(TypeError, match="ApprovedErrorMappingProfile"):
        replace(
            SEARCH_APPROVAL_OPERATION,
            error_mapping_profile="provider_dynamic",  # type: ignore[arg-type]
        )

    mutated = replace(SEARCH_APPROVAL_OPERATION)
    object.__setattr__(mutated, "error_mapping_profile", object())
    approval = _approval_with_search(mutated)
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_against_endpoint(approval, ENDPOINT)
    assert exc_info.value.code is ApprovalValidationErrorCode.OPERATION_MISMATCH
    assert "provider_dynamic" not in str(exc_info.value)


def test_raw_payload_retention_is_bounded_and_typed() -> None:
    assert tuple(ApprovedRawPayloadRetention) == (
        ApprovedRawPayloadRetention.DISCARD,
        ApprovedRawPayloadRetention.TEST_FIXTURE_ONLY,
    )
    with pytest.raises(TypeError, match="ApprovedRawPayloadRetention"):
        replace(
            SEARCH_APPROVAL_OPERATION,
            raw_payload_retention="persist",  # type: ignore[arg-type]
        )


def test_test_fixture_only_retention_is_valid_for_fixture_local_validation() -> None:
    operations = tuple(
        replace(
            operation,
            raw_payload_retention=ApprovedRawPayloadRetention.TEST_FIXTURE_ONLY,
        )
        for operation in APPROVAL.operations
    )
    fixture = replace(APPROVAL, operations=operations)

    validate_provider_approval(fixture)
    validate_approval_against_endpoint(fixture, ENDPOINT)
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_for_activation(fixture, CAPABILITIES, ENDPOINT)
    assert exc_info.value.code is ApprovalValidationErrorCode.INVALID


def test_production_discard_can_pass_activation_without_registry_or_network_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval, endpoint = _production_pair()

    def forbidden(*_: object, **__: object) -> object:
        raise AssertionError("DNS or network access is forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

    validate_approval_for_activation(approval, CAPABILITIES, endpoint)
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()


def test_production_test_fixture_only_retention_fails_activation_incomplete() -> None:
    approval, endpoint = _production_pair(
        ApprovedRawPayloadRetention.TEST_FIXTURE_ONLY
    )

    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_provider_approval(approval)
    assert exc_info.value.code is ApprovalValidationErrorCode.INCOMPLETE

    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_for_activation(approval, CAPABILITIES, endpoint)
    assert exc_info.value.code is ApprovalValidationErrorCode.INCOMPLETE


def test_n4d_a_contract_does_not_change_outbound_constants_or_production_registry() -> None:
    assert CONNECT_TIMEOUT_SECONDS == 3.0
    assert TOTAL_TIMEOUT_SECONDS == 10.0
    assert METADATA_HOST.endswith(".invalid")
    assert ASSET_HOST.endswith(".invalid")
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
