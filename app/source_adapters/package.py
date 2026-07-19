"""Offline Provider package validation and activation planning.

Provider packages bind already reviewed, immutable facts.  This module does
not discover packages, read fixtures, contact a Provider, execute an adapter,
or mutate the production registry.  Trusted package definitions supply an
opaque fixture-ID digest catalog after any file handling has happened outside
this boundary.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Callable

from app.source_adapters.approval import (
    ApprovalValidationError,
    ApprovalValidationErrorCode,
    ProviderApproval,
    ProviderApprovalScope,
    validate_approval_against_capabilities,
    validate_approval_against_endpoint,
    validate_approval_for_activation,
    validate_provider_approval,
)
from app.source_adapters.contracts import (
    ProviderAssetAdapter,
    ProviderCapabilities,
    ProviderOperation,
    SourceMetadataAdapter,
    _validate_provider_key,
)
from app.source_adapters.registry import EndpointRegistry, ProviderEndpoint
from app.video_metadata.contracts import VideoMetadataAdapter


MAX_EVIDENCE_ID_LENGTH = 128
MAX_EVIDENCE_TEXT_LENGTH = 2_000
MAX_FIXTURE_EVIDENCE = 256

_OPAQUE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,127}\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_DYNAMIC_MANIFEST_PATTERN = re.compile(
    r"(?:"
    r"\$\{?|\$\(|\{\{|\{%|<%|"
    r"%[A-Za-z_][A-Za-z0-9_]*%|"
    r"\b(?:os\.)?environ\b|\bprocess\.env\b|\bgetenv\s*\(|"
    r"\b(?:include|require)\s*(?::|\()|"
    r"\b(?:__import__|eval|exec)\s*\(|\b(?:lambda|import)\b"
    r")",
    re.IGNORECASE,
)
_SENSITIVE_MANIFEST_PATTERN = re.compile(
    r"\b(?:authorization|cookie|credential|password|secret|session[_ -]?id|"
    r"token|user[_ -]?(?:account|name))\b",
    re.IGNORECASE,
)
_RAW_RESPONSE_KEY_PATTERN = re.compile(r'''["'][^"']+["']\s*:''')
_SUPPORTED_OPERATIONS = frozenset(
    {
        ProviderOperation.SEARCH,
        ProviderOperation.DETAIL,
        ProviderOperation.ASSET_LIST,
    }
)


class ProviderEvidenceKind(str, Enum):
    SUCCESS = "success"
    EMPTY = "empty"
    PARTIAL = "partial"
    MALFORMED = "malformed"
    INVALID_TYPE = "invalid_type"
    DUPLICATE_IDENTITY = "duplicate_identity"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    PROVIDER_ERROR = "provider_error"


class ProviderFixtureOutcome(str, Enum):
    SUCCESS = "success"
    EMPTY = "empty"
    PARTIAL = "partial"
    INVALID_PROVIDER_PAYLOAD = "invalid_provider_payload"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    PROVIDER_ERROR = "provider_error"


_EXPECTED_OUTCOME_BY_KIND = {
    ProviderEvidenceKind.SUCCESS: ProviderFixtureOutcome.SUCCESS,
    ProviderEvidenceKind.EMPTY: ProviderFixtureOutcome.EMPTY,
    ProviderEvidenceKind.PARTIAL: ProviderFixtureOutcome.PARTIAL,
    ProviderEvidenceKind.MALFORMED: ProviderFixtureOutcome.INVALID_PROVIDER_PAYLOAD,
    ProviderEvidenceKind.INVALID_TYPE: ProviderFixtureOutcome.INVALID_PROVIDER_PAYLOAD,
    ProviderEvidenceKind.DUPLICATE_IDENTITY: (
        ProviderFixtureOutcome.INVALID_PROVIDER_PAYLOAD
    ),
    ProviderEvidenceKind.NOT_FOUND: ProviderFixtureOutcome.NOT_FOUND,
    ProviderEvidenceKind.RATE_LIMITED: ProviderFixtureOutcome.RATE_LIMITED,
    ProviderEvidenceKind.PROVIDER_ERROR: ProviderFixtureOutcome.PROVIDER_ERROR,
}


class ProviderAdapterKind(str, Enum):
    SOURCE_METADATA = "source_metadata"
    VIDEO_METADATA = "video_metadata"


class ProviderPackageErrorCode(str, Enum):
    PACKAGE_INVALID = "package_invalid"
    PACKAGE_PROVIDER_MISMATCH = "package_provider_mismatch"
    PACKAGE_OPERATION_MISMATCH = "package_operation_mismatch"
    PACKAGE_ADAPTER_MISMATCH = "package_adapter_mismatch"
    PACKAGE_EVIDENCE_MISMATCH = "package_evidence_mismatch"
    PACKAGE_FIXTURE_MISMATCH = "package_fixture_mismatch"
    PACKAGE_DUPLICATE_PROVIDER = "package_duplicate_provider"
    PACKAGE_NOT_ACTIVATABLE = "package_not_activatable"


@dataclass(frozen=True, slots=True)
class ProviderPackageError(ValueError):
    code: ProviderPackageErrorCode
    cause_code: ApprovalValidationErrorCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ProviderPackageErrorCode):
            raise TypeError("code must be ProviderPackageErrorCode")
        if self.cause_code is not None and not isinstance(
            self.cause_code,
            ApprovalValidationErrorCode,
        ):
            raise TypeError("cause_code must be ApprovalValidationErrorCode")
        ValueError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        if self.cause_code is None:
            return f"ProviderPackageError(code={self.code.value!r})"
        return (
            "ProviderPackageError("
            f"code={self.code.value!r}, cause_code={self.cause_code.value!r})"
        )


def _raise(
    code: ProviderPackageErrorCode,
    *,
    cause_code: ApprovalValidationErrorCode | None = None,
) -> None:
    raise ProviderPackageError(code, cause_code) from None


def _bounded_text(value: str, *, field: str, optional: bool = False) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not optional and not value.strip():
        raise ValueError(f"{field} must not be blank")
    if len(value) > MAX_EVIDENCE_TEXT_LENGTH:
        raise ValueError(f"{field} is too long")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field} contains control characters")


def _safe_manifest_text(
    value: str,
    *,
    field: str,
    optional: bool = False,
) -> None:
    _bounded_text(value, field=field, optional=optional)
    if optional and not value:
        return
    if (
        _DYNAMIC_MANIFEST_PATTERN.search(value) is not None
        or "://" in value
        or "/" in value
        or "\\" in value
    ):
        raise ValueError(f"{field} contains a dynamic or path-like value")
    stripped = value.strip()
    if (
        _SENSITIVE_MANIFEST_PATTERN.search(value) is not None
        or _RAW_RESPONSE_KEY_PATTERN.search(value) is not None
        or (
            len(stripped) >= 2
            and (stripped[0], stripped[-1]) in {
                ("{", "}"),
                ("[", "]"),
                ("<", ">"),
            }
        )
    ):
        raise ValueError(f"{field} contains sensitive or raw response content")


def _opaque_id(value: str, *, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) > MAX_EVIDENCE_ID_LENGTH
        or _OPAQUE_ID_PATTERN.fullmatch(value) is None
        or value in {".", ".."}
        or ".." in value
    ):
        raise ValueError(f"{field} must be an opaque identifier")


def _operation_tuple(
    values: tuple[ProviderOperation, ...],
    *,
    field: str,
) -> None:
    if not isinstance(values, tuple) or not all(
        isinstance(value, ProviderOperation) for value in values
    ):
        raise TypeError(f"{field} must be a ProviderOperation tuple")
    if not values:
        raise ValueError(f"{field} must not be empty")
    if len(set(values)) != len(values):
        raise ValueError(f"{field} contains duplicates")
    if any(value not in _SUPPORTED_OPERATIONS for value in values):
        raise ValueError(f"{field} contains an unsupported operation")


@dataclass(frozen=True, slots=True)
class ProviderFixtureEvidence:
    operation: ProviderOperation
    fixture_id: str
    fixture_sha256: str
    fixture_kind: ProviderEvidenceKind
    expected_outcome: ProviderFixtureOutcome

    def __post_init__(self) -> None:
        if (
            not isinstance(self.operation, ProviderOperation)
            or self.operation not in _SUPPORTED_OPERATIONS
        ):
            raise ValueError("operation is not supported by Provider packages")
        _opaque_id(self.fixture_id, field="fixture_id")
        if (
            not isinstance(self.fixture_sha256, str)
            or _SHA256_PATTERN.fullmatch(self.fixture_sha256) is None
        ):
            raise ValueError("fixture_sha256 is invalid")
        if not isinstance(self.fixture_kind, ProviderEvidenceKind):
            raise TypeError("fixture_kind must be ProviderEvidenceKind")
        if not isinstance(self.expected_outcome, ProviderFixtureOutcome):
            raise TypeError("expected_outcome must be ProviderFixtureOutcome")
        if self.expected_outcome is not _EXPECTED_OUTCOME_BY_KIND[self.fixture_kind]:
            raise ValueError("expected_outcome does not match fixture_kind")


@dataclass(frozen=True, slots=True)
class ProviderEvidenceManifest:
    provider_key: str
    scope: ProviderApprovalScope
    display_name: str
    content_scope: str
    approval_id: str
    review_revision: str
    reviewed_at: datetime
    reviewed_operations: tuple[ProviderOperation, ...]
    fixture_evidence: tuple[ProviderFixtureEvidence, ...]
    license_conclusion: str
    terms_conclusion: str
    lawful_access_conclusion: str
    notes: str | None = None

    def __post_init__(self) -> None:
        _validate_provider_key(self.provider_key)
        if not isinstance(self.scope, ProviderApprovalScope):
            raise TypeError("scope must be ProviderApprovalScope")
        _bounded_text(self.display_name, field="display_name")
        _bounded_text(self.content_scope, field="content_scope")
        _opaque_id(self.approval_id, field="approval_id")
        _opaque_id(self.review_revision, field="review_revision")
        if (
            not isinstance(self.reviewed_at, datetime)
            or self.reviewed_at.tzinfo is None
            or self.reviewed_at.utcoffset() is None
        ):
            raise ValueError("reviewed_at must be timezone-aware")
        object.__setattr__(self, "reviewed_at", self.reviewed_at.astimezone(UTC))
        _operation_tuple(self.reviewed_operations, field="reviewed_operations")
        if (
            not isinstance(self.fixture_evidence, tuple)
            or not self.fixture_evidence
            or len(self.fixture_evidence) > MAX_FIXTURE_EVIDENCE
            or not all(
                type(value) is ProviderFixtureEvidence
                for value in self.fixture_evidence
            )
        ):
            raise TypeError(
                "fixture_evidence must be an immutable ProviderFixtureEvidence tuple"
            )
        identities = tuple(
            (value.operation, value.fixture_id) for value in self.fixture_evidence
        )
        fixture_ids = tuple(value.fixture_id for value in self.fixture_evidence)
        if len(set(identities)) != len(identities):
            raise ValueError("fixture_evidence contains duplicates")
        if len(set(fixture_ids)) != len(fixture_ids):
            raise ValueError("fixture_id must be unique within a manifest")
        for value, field in (
            (self.license_conclusion, "license_conclusion"),
            (self.terms_conclusion, "terms_conclusion"),
            (self.lawful_access_conclusion, "lawful_access_conclusion"),
        ):
            _safe_manifest_text(value, field=field)
        if self.notes is not None:
            _safe_manifest_text(self.notes, field="notes", optional=True)


_ADAPTER_METHODS = {
    ProviderAdapterKind.SOURCE_METADATA: {
        ProviderOperation.SEARCH: "search",
        ProviderOperation.DETAIL: "fetch_detail",
        ProviderOperation.ASSET_LIST: "list_assets",
    },
    ProviderAdapterKind.VIDEO_METADATA: {
        ProviderOperation.SEARCH: "search",
        ProviderOperation.DETAIL: "detail",
        ProviderOperation.ASSET_LIST: "asset_list",
    },
}


@dataclass(frozen=True, slots=True)
class ProviderAdapterBinding:
    provider_key: str
    display_name: str
    content_scope: str
    operations: tuple[ProviderOperation, ...]
    adapter: object
    adapter_kind: ProviderAdapterKind

    def __post_init__(self) -> None:
        _validate_provider_key(self.provider_key)
        _bounded_text(self.display_name, field="display_name")
        _bounded_text(self.content_scope, field="content_scope")
        _operation_tuple(self.operations, field="operations")
        if not isinstance(self.adapter_kind, ProviderAdapterKind):
            raise TypeError("adapter_kind must be ProviderAdapterKind")
        if self.adapter is None:
            raise TypeError("adapter must not be None")

    def handler_for(self, operation: ProviderOperation) -> Callable[..., object]:
        if operation not in self.operations:
            _raise(ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH)
        method_name = _ADAPTER_METHODS[self.adapter_kind][operation]
        handler = getattr(self.adapter, method_name)
        if not callable(handler):
            _raise(ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH)
        return handler


def _digest_catalog(
    values: tuple[tuple[str, str], ...],
) -> dict[str, str]:
    if not isinstance(values, tuple):
        raise TypeError("fixture_digests must be a tuple")
    result: dict[str, str] = {}
    for value in values:
        if not isinstance(value, tuple) or len(value) != 2:
            raise TypeError("fixture_digests entries must be pairs")
        fixture_id, digest = value
        _opaque_id(fixture_id, field="fixture_id")
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
            raise ValueError("fixture digest is invalid")
        if fixture_id in result:
            raise ValueError("fixture_digests contains duplicates")
        result[fixture_id] = digest
    return result


@dataclass(frozen=True, slots=True)
class ProviderPackage:
    scope: ProviderApprovalScope
    approval: ProviderApproval
    capabilities: ProviderCapabilities
    endpoint: ProviderEndpoint
    binding: ProviderAdapterBinding
    evidence: ProviderEvidenceManifest
    fixture_digests: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ProviderApprovalScope):
            raise TypeError("scope must be ProviderApprovalScope")
        if type(self.approval) is not ProviderApproval:
            raise TypeError("approval must be ProviderApproval")
        if type(self.capabilities) is not ProviderCapabilities:
            raise TypeError("capabilities must be ProviderCapabilities")
        if type(self.endpoint) is not ProviderEndpoint:
            raise TypeError("endpoint must be ProviderEndpoint")
        if type(self.binding) is not ProviderAdapterBinding:
            raise TypeError("binding must be ProviderAdapterBinding")
        if type(self.evidence) is not ProviderEvidenceManifest:
            raise TypeError("evidence must be ProviderEvidenceManifest")
        _digest_catalog(self.fixture_digests)

    @property
    def provider_key(self) -> str:
        return self.approval.provider_key

    @property
    def adapter(self) -> object:
        return self.binding.adapter


def _package_code_for_approval(
    code: ApprovalValidationErrorCode,
) -> ProviderPackageErrorCode:
    if code is ApprovalValidationErrorCode.PROVIDER_MISMATCH:
        return ProviderPackageErrorCode.PACKAGE_PROVIDER_MISMATCH
    if code in {
        ApprovalValidationErrorCode.CAPABILITY_MISMATCH,
        ApprovalValidationErrorCode.OPERATION_MISMATCH,
    }:
        return ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH
    return ProviderPackageErrorCode.PACKAGE_INVALID


def _run_approval_check(check: Callable[[], None]) -> None:
    try:
        check()
    except ApprovalValidationError as error:
        _raise(
            _package_code_for_approval(error.code),
            cause_code=error.code,
        )


def _adapter_provider_key(adapter: object) -> object:
    value = inspect.getattr_static(adapter, "key", None)
    if value is None:
        value = inspect.getattr_static(adapter, "provider_key", None)
    return value


def _validate_binding(
    binding: ProviderAdapterBinding,
    *,
    provider_key: str,
    display_name: str,
    content_scope: str,
    capabilities: ProviderCapabilities,
    operations: tuple[ProviderOperation, ...],
) -> None:
    if (
        binding.provider_key != provider_key
        or _adapter_provider_key(binding.adapter) != provider_key
    ):
        _raise(ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH)
    if (
        binding.display_name != display_name
        or binding.content_scope != content_scope
    ):
        _raise(ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH)
    if binding.operations != operations:
        _raise(ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH)
    if binding.adapter_kind is ProviderAdapterKind.VIDEO_METADATA and not isinstance(
        binding.adapter,
        VideoMetadataAdapter,
    ):
        _raise(ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH)
    if binding.adapter_kind is ProviderAdapterKind.SOURCE_METADATA:
        if not isinstance(binding.adapter, SourceMetadataAdapter):
            _raise(ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH)
        if (
            inspect.getattr_static(binding.adapter, "display_name", None)
            != display_name
            or inspect.getattr_static(binding.adapter, "capabilities", None)
            != capabilities
        ):
            _raise(ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH)
        if ProviderOperation.ASSET_LIST in binding.operations and not isinstance(
            binding.adapter,
            ProviderAssetAdapter,
        ):
            _raise(ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH)
    method_names = _ADAPTER_METHODS[binding.adapter_kind]
    for operation in binding.operations:
        method = inspect.getattr_static(
            binding.adapter,
            method_names[operation],
            None,
        )
        if method is None or not callable(method):
            _raise(ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH)


def _validate_evidence(package: ProviderPackage) -> None:
    evidence = package.evidence
    approval = package.approval
    if evidence.provider_key != approval.provider_key:
        _raise(ProviderPackageErrorCode.PACKAGE_PROVIDER_MISMATCH)
    if evidence.scope is not package.scope:
        _raise(ProviderPackageErrorCode.PACKAGE_NOT_ACTIVATABLE)
    if (
        evidence.display_name != approval.display_name
        or evidence.content_scope != approval.content_scope
    ):
        _raise(ProviderPackageErrorCode.PACKAGE_PROVIDER_MISMATCH)
    if evidence.approval_id != approval.approval_id:
        _raise(ProviderPackageErrorCode.PACKAGE_EVIDENCE_MISMATCH)
    operations = approval.capabilities
    if evidence.reviewed_operations != operations:
        _raise(ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH)
    covered = {value.operation for value in evidence.fixture_evidence}
    if covered != set(operations):
        _raise(ProviderPackageErrorCode.PACKAGE_EVIDENCE_MISMATCH)
    expected = {
        value.fixture_id: value.fixture_sha256
        for value in evidence.fixture_evidence
    }
    actual = _digest_catalog(package.fixture_digests)
    if set(actual) != set(expected):
        _raise(ProviderPackageErrorCode.PACKAGE_EVIDENCE_MISMATCH)
    if any(actual[fixture_id] != digest for fixture_id, digest in expected.items()):
        _raise(ProviderPackageErrorCode.PACKAGE_FIXTURE_MISMATCH)


def validate_provider_package(package: object) -> None:
    if type(package) is not ProviderPackage:
        _raise(ProviderPackageErrorCode.PACKAGE_INVALID)

    approval = package.approval
    capabilities = package.capabilities
    endpoint = package.endpoint
    binding = package.binding
    evidence = package.evidence
    components = (
        capabilities.provider_key,
        endpoint.provider_key,
        binding.provider_key,
        evidence.provider_key,
    )
    if any(value != approval.provider_key for value in components):
        _raise(ProviderPackageErrorCode.PACKAGE_PROVIDER_MISMATCH)
    if endpoint.capabilities != capabilities:
        _raise(ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH)
    if package.scope is not approval.scope:
        _raise(ProviderPackageErrorCode.PACKAGE_NOT_ACTIVATABLE)
    if (
        capabilities.display_name != approval.display_name
        or capabilities.content_scope != approval.content_scope
        or binding.display_name != approval.display_name
        or binding.content_scope != approval.content_scope
        or evidence.display_name != approval.display_name
        or evidence.content_scope != approval.content_scope
    ):
        _raise(ProviderPackageErrorCode.PACKAGE_PROVIDER_MISMATCH)
    operations = approval.capabilities
    if (
        capabilities.operations != operations
        or tuple(value.operation for value in endpoint.operations) != operations
        or binding.operations != operations
        or evidence.reviewed_operations != operations
    ):
        _raise(ProviderPackageErrorCode.PACKAGE_OPERATION_MISMATCH)

    _run_approval_check(lambda: validate_provider_approval(approval))
    _run_approval_check(
        lambda: validate_approval_against_capabilities(approval, capabilities)
    )
    _run_approval_check(
        lambda: validate_approval_against_endpoint(approval, endpoint)
    )
    if package.scope is ProviderApprovalScope.PRODUCTION:
        try:
            validate_approval_for_activation(approval, capabilities, endpoint)
        except ApprovalValidationError as error:
            _raise(
                ProviderPackageErrorCode.PACKAGE_NOT_ACTIVATABLE,
                cause_code=error.code,
            )
    elif package.scope is not ProviderApprovalScope.TEST_FIXTURE:
        _raise(ProviderPackageErrorCode.PACKAGE_NOT_ACTIVATABLE)

    _validate_binding(
        binding,
        provider_key=approval.provider_key,
        display_name=approval.display_name,
        content_scope=approval.content_scope,
        capabilities=capabilities,
        operations=operations,
    )
    _validate_evidence(package)


def _validated_packages(packages: object) -> tuple[ProviderPackage, ...]:
    if not isinstance(packages, tuple) or not all(
        type(package) is ProviderPackage for package in packages
    ):
        _raise(ProviderPackageErrorCode.PACKAGE_INVALID)
    for package in packages:
        validate_provider_package(package)
    keys = tuple(package.provider_key for package in packages)
    if len(set(keys)) != len(keys):
        _raise(ProviderPackageErrorCode.PACKAGE_DUPLICATE_PROVIDER)
    return tuple(sorted(packages, key=lambda package: package.provider_key))


def build_endpoint_registry_from_packages(
    packages: tuple[ProviderPackage, ...],
) -> EndpointRegistry:
    validated = _validated_packages(packages)
    return EndpointRegistry(tuple(package.endpoint for package in validated))


def build_adapter_bindings_from_packages(
    packages: tuple[ProviderPackage, ...],
) -> tuple[ProviderAdapterBinding, ...]:
    validated = _validated_packages(packages)
    return tuple(package.binding for package in validated)


__all__ = [
    "ProviderAdapterBinding",
    "ProviderAdapterKind",
    "ProviderEvidenceKind",
    "ProviderEvidenceManifest",
    "ProviderFixtureEvidence",
    "ProviderFixtureOutcome",
    "ProviderPackage",
    "ProviderPackageError",
    "ProviderPackageErrorCode",
    "build_adapter_bindings_from_packages",
    "build_endpoint_registry_from_packages",
    "validate_provider_package",
]
