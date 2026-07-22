"""Drive shipped activation validators for JavDB PRODUCTION HTML+session facts.

These tests call real ``validate_approval_*`` entry points — they do not
re-implement activation rules.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.providers.javdb.approval import (
    JAVDB_APPROVAL,
    JAVDB_CAPABILITIES,
    JAVDB_ENDPOINT,
)
from app.providers.javdb.production import (
    JAVDB_PRODUCTION_APPROVAL,
    JAVDB_PRODUCTION_CAPABILITIES,
    JAVDB_PRODUCTION_ENDPOINT,
    JAVDB_PRODUCTION_HOST,
    JAVDB_PRODUCTION_REGION_POLICY,
)
from app.source_adapters import (
    ApprovalValidationError,
    ApprovalValidationErrorCode,
    ApprovedDownloadPolicy,
    ApprovedAssetPolicy,
    validate_approval_against_capabilities,
    validate_approval_against_endpoint,
    validate_approval_for_activation,
    validate_provider_approval,
)
from app.source_adapters.approval import ProviderApprovalScope
from app.source_adapters.contracts import ProviderOperation, SourceAssetKind
from app.source_adapters.registry import (
    CookiePolicy,
    PRODUCTION_ENDPOINT_REGISTRY,
    ResponseKind,
)


def test_production_html_session_metadata_passes_activation() -> None:
    assert JAVDB_PRODUCTION_APPROVAL.scope is ProviderApprovalScope.PRODUCTION
    assert JAVDB_PRODUCTION_HOST == "javdb.com"
    assert not JAVDB_PRODUCTION_HOST.endswith(".invalid")
    assert "JP" in JAVDB_PRODUCTION_REGION_POLICY and "KR" in JAVDB_PRODUCTION_REGION_POLICY
    assert all(
        op.cookie_policy is CookiePolicy.PROVIDER_SESSION
        for op in JAVDB_PRODUCTION_APPROVAL.operations
    )
    assert all(
        op.response_kind is ResponseKind.HTML
        for op in JAVDB_PRODUCTION_APPROVAL.operations
    )
    assert {
        ProviderOperation.SEARCH,
        ProviderOperation.DETAIL,
    }.issubset(set(JAVDB_PRODUCTION_APPROVAL.capabilities))
    assert ProviderOperation.ASSET_LIST in JAVDB_PRODUCTION_APPROVAL.capabilities
    assert JAVDB_PRODUCTION_APPROVAL.download_policy.enabled is False
    assert JAVDB_PRODUCTION_APPROVAL.asset_policy.locator_resolution_allowed is False

    validate_provider_approval(JAVDB_PRODUCTION_APPROVAL)
    validate_approval_against_capabilities(
        JAVDB_PRODUCTION_APPROVAL, JAVDB_PRODUCTION_CAPABILITIES
    )
    validate_approval_against_endpoint(
        JAVDB_PRODUCTION_APPROVAL, JAVDB_PRODUCTION_ENDPOINT
    )
    validate_approval_for_activation(
        JAVDB_PRODUCTION_APPROVAL,
        JAVDB_PRODUCTION_CAPABILITIES,
        JAVDB_PRODUCTION_ENDPOINT,
    )
    # Reviewed facts do not activate a network-capable runtime by default.
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()


def test_test_fixture_javdb_cannot_activate() -> None:
    validate_provider_approval(JAVDB_APPROVAL)
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_for_activation(
            JAVDB_APPROVAL, JAVDB_CAPABILITIES, JAVDB_ENDPOINT
        )
    assert exc_info.value.code is ApprovalValidationErrorCode.INVALID


def test_production_download_enabled_fails_activation() -> None:
    # Bypass ProviderApproval construction coupling so activation's own
    # fail-closed check for download_policy.enabled is exercised.
    bad = replace(JAVDB_PRODUCTION_APPROVAL)
    object.__setattr__(
        bad,
        "download_policy",
        ApprovedDownloadPolicy(
            enabled=True,
            allowed_kinds=(SourceAssetKind.MEDIA,),
            asset_host_ids=("asset",),
            max_files_per_request=1,
            max_total_bytes=1024,
            checksum_required=True,
        ),
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_for_activation(
            bad, JAVDB_PRODUCTION_CAPABILITIES, JAVDB_PRODUCTION_ENDPOINT
        )
    # Fail-closed: rejected before or at activation (download not approved).
    assert exc_info.value.code in {
        ApprovalValidationErrorCode.INCOMPLETE,
        ApprovalValidationErrorCode.DOWNLOAD_POLICY_MISMATCH,
        ApprovalValidationErrorCode.CAPABILITY_MISMATCH,
        ApprovalValidationErrorCode.INVALID,
    }


def test_production_asset_locator_enabled_fails_activation() -> None:
    bad = replace(JAVDB_PRODUCTION_APPROVAL)
    object.__setattr__(
        bad,
        "asset_policy",
        ApprovedAssetPolicy(
            allowed_kinds=(SourceAssetKind.COVER,),
            asset_host_ids=("asset",),
            max_assets_per_item=1,
            locator_resolution_allowed=True,
        ),
    )
    with pytest.raises(ApprovalValidationError) as exc_info:
        validate_approval_for_activation(
            bad, JAVDB_PRODUCTION_CAPABILITIES, JAVDB_PRODUCTION_ENDPOINT
        )
    # Fail-closed: unapproved asset locator never activates.
    assert exc_info.value.code in {
        ApprovalValidationErrorCode.INCOMPLETE,
        ApprovalValidationErrorCode.ASSET_POLICY_MISMATCH,
        ApprovalValidationErrorCode.CAPABILITY_MISMATCH,
        ApprovalValidationErrorCode.INVALID,
    }


def test_production_facts_have_no_secret_fields() -> None:
    # Approval objects are policy facts only; cookie *values* must not appear.
    blob = repr(JAVDB_PRODUCTION_APPROVAL) + repr(JAVDB_PRODUCTION_ENDPOINT)
    for needle in ("sessionid=", "password=", "Bearer ", "cookie="):
        assert needle not in blob
