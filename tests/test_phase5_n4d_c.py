from __future__ import annotations

import logging
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest
from sqlalchemy.orm import Session

from app.services.outbound_http import OutboundHttpClient
from app.source_adapters import (
    ApprovalValidationErrorCode,
    ApprovedAssetPolicy,
    AssetCapabilities,
    EndpointRegistry,
    PRODUCTION_ENDPOINT_REGISTRY,
    ProviderAdapterBinding,
    ProviderAdapterKind,
    ProviderApprovalScope,
    ProviderEvidenceKind,
    ProviderEvidenceManifest,
    ProviderFixtureEvidence,
    ProviderFixtureOutcome,
    ProviderOperation,
    ProviderPackage,
    ProviderPackageError,
    ProviderPackageErrorCode,
    build_adapter_bindings_from_packages,
    build_endpoint_registry_from_packages,
    validate_provider_package,
)
from tests.provider_package_fixture import (
    SOURCE_FIXTURE_DIGESTS,
    SOURCE_PACKAGE,
    VIDEO_FIXTURE_DIGESTS,
    VIDEO_PACKAGE,
    actual_fixture_digests,
)
from tests.fixture_provider import FixtureReferenceProvider
from tests.video_metadata_fixture_provider import FixtureVideoMetadataProvider


def _assert_package_error(
    code: ProviderPackageErrorCode,
    operation,
) -> ProviderPackageError:
    with pytest.raises(ProviderPackageError) as exc_info:
        operation()
    assert exc_info.value.code is code
    assert str(exc_info.value) == code.value
    return exc_info.value


def _metadata_only_package() -> ProviderPackage:
    operations = (ProviderOperation.SEARCH, ProviderOperation.DETAIL)
    capabilities = replace(VIDEO_PACKAGE.capabilities, assets=AssetCapabilities())
    endpoint = replace(
        VIDEO_PACKAGE.endpoint,
        capabilities=capabilities,
        operations=VIDEO_PACKAGE.endpoint.operations[:2],
    )
    approval = replace(
        VIDEO_PACKAGE.approval,
        capabilities=operations,
        hosts=(VIDEO_PACKAGE.approval.hosts[0],),
        operations=VIDEO_PACKAGE.approval.operations[:2],
        asset_policy=ApprovedAssetPolicy(),
        explicit_exclusions=(
            *VIDEO_PACKAGE.approval.explicit_exclusions,
            ProviderOperation.ASSET_LIST,
        ),
    )
    evidence_values = tuple(
        value
        for value in VIDEO_PACKAGE.evidence.fixture_evidence
        if value.operation in operations
    )
    evidence = replace(
        VIDEO_PACKAGE.evidence,
        reviewed_operations=operations,
        fixture_evidence=evidence_values,
    )
    evidence_ids = {value.fixture_id for value in evidence_values}
    binding = replace(VIDEO_PACKAGE.binding, operations=operations)
    return replace(
        VIDEO_PACKAGE,
        approval=approval,
        capabilities=capabilities,
        endpoint=endpoint,
        binding=binding,
        evidence=evidence,
        fixture_digests=tuple(
            value for value in VIDEO_FIXTURE_DIGESTS if value[0] in evidence_ids
        ),
    )


def test_package_contracts_are_frozen_slotted_and_typed() -> None:
    values = (
        VIDEO_PACKAGE.evidence.fixture_evidence[0],
        VIDEO_PACKAGE.evidence,
        VIDEO_PACKAGE.binding,
        VIDEO_PACKAGE,
    )
    for value in values:
        assert not hasattr(value, "__dict__")
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            value.extra = "forbidden"  # type: ignore[attr-defined]
    assert VIDEO_PACKAGE.adapter is VIDEO_PACKAGE.binding.adapter
    error = ProviderPackageError(ProviderPackageErrorCode.PACKAGE_INVALID)
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        error.extra = "forbidden"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "builder",
    [
        lambda: replace(VIDEO_PACKAGE.binding, operations=[ProviderOperation.SEARCH]),
        lambda: replace(VIDEO_PACKAGE.evidence, fixture_evidence=[]),
        lambda: replace(VIDEO_PACKAGE, fixture_digests=[]),
    ],
)
def test_package_contracts_reject_mutable_collections(builder) -> None:
    with pytest.raises(TypeError):
        builder()


def test_evidence_validates_opaque_ids_sha_utc_text_and_duplicates() -> None:
    fixture = VIDEO_PACKAGE.evidence.fixture_evidence[0]
    with pytest.raises(ValueError, match="opaque"):
        replace(fixture, fixture_id="../synthetic-marker")
    with pytest.raises(ValueError, match="fixture_sha256"):
        replace(fixture, fixture_sha256="A" * 64)
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(VIDEO_PACKAGE.evidence, reviewed_at=datetime.now())
    with pytest.raises(ValueError, match="too long"):
        replace(VIDEO_PACKAGE.evidence, notes="x" * 2_001)
    with pytest.raises(ValueError, match="duplicates"):
        replace(
            VIDEO_PACKAGE.evidence,
            fixture_evidence=(fixture, fixture),
        )
    with pytest.raises(ValueError, match="opaque"):
        replace(VIDEO_PACKAGE.evidence, review_revision="${ENV_VALUE}")
    with pytest.raises(ValueError, match="dynamic or path-like"):
        replace(VIDEO_PACKAGE.evidence, notes="include: arbitrary/path")


@pytest.mark.parametrize(
    "notes, message",
    [
        ("$HOME", "dynamic or path-like"),
        ("os.environ.get('HOME')", "dynamic or path-like"),
        ('{"status":"synthetic-marker"}', "sensitive or raw response"),
        ("<response>synthetic-marker</response>", "dynamic or path-like"),
        ("authorization=synthetic-marker", "sensitive or raw response"),
    ],
)
def test_manifest_rejects_environment_raw_response_and_sensitive_text(
    notes: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(VIDEO_PACKAGE.evidence, notes=notes)


def test_reviewed_time_is_normalized_to_utc() -> None:
    assert VIDEO_PACKAGE.evidence.reviewed_at.tzinfo is UTC


def test_complete_source_and_video_fixture_packages_validate() -> None:
    validate_provider_package(SOURCE_PACKAGE)
    validate_provider_package(VIDEO_PACKAGE)


def test_non_package_input_returns_stable_package_invalid() -> None:
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_INVALID,
        lambda: validate_provider_package(object()),
    )


def test_fixture_kind_and_expected_outcome_must_match() -> None:
    with pytest.raises(ValueError, match="does not match"):
        replace(
            VIDEO_PACKAGE.evidence.fixture_evidence[0],
            expected_outcome=ProviderFixtureOutcome.NOT_FOUND,
        )


def test_fixture_digests_match_only_fixed_authorized_files() -> None:
    assert actual_fixture_digests(
        tuple(value[0] for value in SOURCE_FIXTURE_DIGESTS)
    ) == SOURCE_FIXTURE_DIGESTS
    assert actual_fixture_digests(
        tuple(value[0] for value in VIDEO_FIXTURE_DIGESTS)
    ) == VIDEO_FIXTURE_DIGESTS


def test_provider_identity_mismatch_is_stable() -> None:
    evidence = replace(VIDEO_PACKAGE.evidence, provider_key="other_fixture")
    package = replace(VIDEO_PACKAGE, evidence=evidence)
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_PROVIDER_MISMATCH,
        lambda: validate_provider_package(package),
    )


def test_display_name_and_content_scope_must_match() -> None:
    binding = replace(VIDEO_PACKAGE.binding, display_name="Synthetic mismatch")
    package = replace(VIDEO_PACKAGE, binding=binding)
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_PROVIDER_MISMATCH,
        lambda: validate_provider_package(package),
    )


def test_endpoint_capabilities_must_be_the_package_capabilities() -> None:
    endpoint_capabilities = replace(
        VIDEO_PACKAGE.capabilities,
        attribution_required=True,
    )
    endpoint = replace(VIDEO_PACKAGE.endpoint, capabilities=endpoint_capabilities)
    package = replace(VIDEO_PACKAGE, endpoint=endpoint)
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH,
        lambda: validate_provider_package(package),
    )


def test_evidence_approval_id_mismatch_is_stable() -> None:
    evidence = replace(VIDEO_PACKAGE.evidence, approval_id="synthetic_marker")
    package = replace(VIDEO_PACKAGE, evidence=evidence)
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_EVIDENCE_MISMATCH,
        lambda: validate_provider_package(package),
    )


def test_reviewed_operations_must_match_exact_order() -> None:
    evidence = replace(
        VIDEO_PACKAGE.evidence,
        reviewed_operations=tuple(reversed(VIDEO_PACKAGE.evidence.reviewed_operations)),
    )
    package = replace(VIDEO_PACKAGE, evidence=evidence)
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH,
        lambda: validate_provider_package(package),
    )


def test_binding_missing_operation_is_rejected() -> None:
    binding = replace(
        VIDEO_PACKAGE.binding,
        operations=VIDEO_PACKAGE.binding.operations[:-1],
    )
    package = replace(VIDEO_PACKAGE, binding=binding)
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH,
        lambda: validate_provider_package(package),
    )


def test_binding_extra_operation_is_rejected() -> None:
    package = _metadata_only_package()
    binding = replace(
        package.binding,
        operations=VIDEO_PACKAGE.binding.operations,
    )
    package = replace(package, binding=binding)
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH,
        lambda: validate_provider_package(package),
    )


def test_adapter_kind_and_adapter_identity_are_explicit() -> None:
    wrong_kind = replace(
        VIDEO_PACKAGE.binding,
        adapter_kind=ProviderAdapterKind.SOURCE_METADATA,
    )
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH,
        lambda: validate_provider_package(replace(VIDEO_PACKAGE, binding=wrong_kind)),
    )

    class WrongKeyVideoAdapter:
        key = "other_fixture"

        async def search(self, query: str, *, page: int, page_size: int):
            raise AssertionError

        async def detail(self, external_id: str):
            raise AssertionError

        async def asset_list(self, external_id: str):
            raise AssertionError

    wrong_adapter = replace(
        VIDEO_PACKAGE.binding,
        adapter=WrongKeyVideoAdapter(),
    )
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH,
        lambda: validate_provider_package(
            replace(VIDEO_PACKAGE, binding=wrong_adapter)
        ),
    )

    class WrongCapabilitiesSourceAdapter(FixtureReferenceProvider):
        capabilities = replace(
            SOURCE_PACKAGE.capabilities,
            display_name="Synthetic mismatch",
        )

    source_binding = replace(
        SOURCE_PACKAGE.binding,
        adapter=WrongCapabilitiesSourceAdapter(object()),  # type: ignore[arg-type]
    )
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH,
        lambda: validate_provider_package(
            replace(SOURCE_PACKAGE, binding=source_binding)
        ),
    )


def test_fixture_evidence_must_cover_every_operation() -> None:
    evidence = replace(
        VIDEO_PACKAGE.evidence,
        fixture_evidence=tuple(
            value
            for value in VIDEO_PACKAGE.evidence.fixture_evidence
            if value.operation is not ProviderOperation.ASSET_LIST
        ),
    )
    evidence_ids = {value.fixture_id for value in evidence.fixture_evidence}
    package = replace(
        VIDEO_PACKAGE,
        evidence=evidence,
        fixture_digests=tuple(
            value for value in VIDEO_FIXTURE_DIGESTS if value[0] in evidence_ids
        ),
    )
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_EVIDENCE_MISMATCH,
        lambda: validate_provider_package(package),
    )


def test_fixture_digest_change_is_a_redacted_stable_mismatch() -> None:
    fixture_id, _ = VIDEO_FIXTURE_DIGESTS[0]
    changed = (
        (fixture_id, "0" * 64),
        *VIDEO_FIXTURE_DIGESTS[1:],
    )
    package = replace(VIDEO_PACKAGE, fixture_digests=changed)
    error = _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_FIXTURE_MISMATCH,
        lambda: validate_provider_package(package),
    )
    rendered = f"{error!s} {error!r}"
    assert "0" * 64 not in rendered
    assert VIDEO_FIXTURE_DIGESTS[0][1] not in rendered


def test_fixture_digest_catalog_must_exactly_match_evidence() -> None:
    package = replace(
        VIDEO_PACKAGE,
        fixture_digests=VIDEO_FIXTURE_DIGESTS[:-1],
    )
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_EVIDENCE_MISMATCH,
        lambda: validate_provider_package(package),
    )


def test_test_fixture_cannot_be_treated_as_production_activation() -> None:
    package = replace(VIDEO_PACKAGE, scope=ProviderApprovalScope.PRODUCTION)
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_NOT_ACTIVATABLE,
        lambda: validate_provider_package(package),
    )
    with pytest.raises(ValueError, match="production approval cannot use fixture hosts"):
        replace(VIDEO_PACKAGE.approval, scope=ProviderApprovalScope.PRODUCTION)


def test_wrapped_approval_failure_preserves_stable_cause_code() -> None:
    capabilities = replace(
        VIDEO_PACKAGE.capabilities,
        attribution_required=True,
    )
    endpoint = replace(VIDEO_PACKAGE.endpoint, capabilities=capabilities)
    package = replace(
        VIDEO_PACKAGE,
        capabilities=capabilities,
        endpoint=endpoint,
    )
    error = _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH,
        lambda: validate_provider_package(package),
    )
    assert error.cause_code is ApprovalValidationErrorCode.CAPABILITY_MISMATCH


def test_empty_tuple_builds_empty_immutable_outputs() -> None:
    registry = build_endpoint_registry_from_packages(())
    assert isinstance(registry, EndpointRegistry)
    assert registry.providers == ()
    assert build_adapter_bindings_from_packages(()) == ()
    with pytest.raises(AttributeError):
        registry.providers = ()  # type: ignore[misc]


def test_package_builders_are_stably_sorted() -> None:
    packages = (VIDEO_PACKAGE, SOURCE_PACKAGE)
    registry = build_endpoint_registry_from_packages(packages)
    bindings = build_adapter_bindings_from_packages(packages)
    expected = tuple(sorted((VIDEO_PACKAGE.provider_key, SOURCE_PACKAGE.provider_key)))
    assert tuple(value.provider_key for value in registry.providers) == expected
    assert tuple(value.provider_key for value in bindings) == expected


@pytest.mark.parametrize(
    "builder",
    [build_endpoint_registry_from_packages, build_adapter_bindings_from_packages],
)
def test_duplicate_provider_package_fails_without_partial_result(builder) -> None:
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_DUPLICATE_PROVIDER,
        lambda: builder((VIDEO_PACKAGE, VIDEO_PACKAGE)),
    )
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_ENDPOINT_REGISTRY.providers)


@pytest.mark.parametrize(
    "builder",
    [build_endpoint_registry_from_packages, build_adapter_bindings_from_packages],
)
def test_invalid_second_package_fails_all_or_nothing(builder) -> None:
    fixture_id, _ = VIDEO_FIXTURE_DIGESTS[0]
    invalid = replace(
        VIDEO_PACKAGE,
        fixture_digests=((fixture_id, "f" * 64), *VIDEO_FIXTURE_DIGESTS[1:]),
    )
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_FIXTURE_MISMATCH,
        lambda: builder((SOURCE_PACKAGE, invalid)),
    )
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_ENDPOINT_REGISTRY.providers)


def test_binding_authority_does_not_expand_from_extra_methods() -> None:
    class AdapterWithExtraAuthority:
        key = VIDEO_PACKAGE.provider_key

        async def search(self, query: str, *, page: int, page_size: int):
            raise AssertionError

        async def detail(self, external_id: str):
            raise AssertionError

        async def asset_list(self, external_id: str):
            raise AssertionError

        async def download(self):
            raise AssertionError

    binding = replace(
        VIDEO_PACKAGE.binding,
        adapter=AdapterWithExtraAuthority(),
    )
    package = replace(VIDEO_PACKAGE, binding=binding)
    validate_provider_package(package)
    assert callable(binding.handler_for(ProviderOperation.SEARCH))
    _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH,
        lambda: binding.handler_for(ProviderOperation.DOWNLOAD),
    )


def test_validation_and_builders_execute_no_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object):
        raise AssertionError("side effect is forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "gethostbyname", forbidden)
    monkeypatch.setattr(httpx2.AsyncClient, "request", forbidden)
    monkeypatch.setattr(OutboundHttpClient, "fetch_json", forbidden)
    monkeypatch.setattr(Session, "execute", forbidden)
    monkeypatch.setattr(Session, "commit", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(FixtureVideoMetadataProvider, "search", forbidden)
    monkeypatch.setattr(FixtureVideoMetadataProvider, "detail", forbidden)
    monkeypatch.setattr(FixtureVideoMetadataProvider, "asset_list", forbidden)
    monkeypatch.setattr(FixtureReferenceProvider, "search", forbidden)
    monkeypatch.setattr(FixtureReferenceProvider, "fetch_detail", forbidden)
    monkeypatch.setattr(FixtureReferenceProvider, "list_assets", forbidden)

    packages = (replace(SOURCE_PACKAGE), replace(VIDEO_PACKAGE))
    for package in packages:
        validate_provider_package(package)
    assert build_endpoint_registry_from_packages(packages).providers == (
        SOURCE_PACKAGE.endpoint,
        VIDEO_PACKAGE.endpoint,
    )
    assert build_adapter_bindings_from_packages(packages) == (
        SOURCE_PACKAGE.binding,
        VIDEO_PACKAGE.binding,
    )


def test_errors_do_not_leak_marker_path_digest_or_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "synthetic-marker-private"
    caplog.set_level(logging.DEBUG)
    evidence = replace(VIDEO_PACKAGE.evidence, approval_id=marker)
    package = replace(VIDEO_PACKAGE, evidence=evidence)
    error = _assert_package_error(
        ProviderPackageErrorCode.PACKAGE_EVIDENCE_MISMATCH,
        lambda: validate_provider_package(package),
    )
    rendered = f"{error!s} {error!r} {caplog.text}"
    assert marker not in rendered
    assert "/fixtures/" not in rendered
    assert VIDEO_FIXTURE_DIGESTS[0][1] not in rendered


def test_production_registry_remains_empty_and_unmodified() -> None:
    before = PRODUCTION_ENDPOINT_REGISTRY
    built = build_endpoint_registry_from_packages((VIDEO_PACKAGE,))
    assert built is not before
    assert built.providers == (VIDEO_PACKAGE.endpoint,)
    assert PRODUCTION_ENDPOINT_REGISTRY is before
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_ENDPOINT_REGISTRY.providers)
