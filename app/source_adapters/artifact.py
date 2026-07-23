"""Strict, local-only Provider Approval Artifact v1 loading.

Artifacts contain reviewed, non-executable Provider facts.  This module does
not discover adapters, import modules dynamically, read files, contact a
Provider, execute adapter operations, or mutate any Registry.  A caller must
provide an immutable code-owned factory registry explicitly.
"""

from __future__ import annotations

import json
import math
import re
import types
from collections.abc import Callable
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from functools import lru_cache
from hashlib import sha256
from secrets import compare_digest
from typing import Union, get_args, get_origin, get_type_hints

from app.source_adapters.approval import ProviderApproval, ProviderApprovalScope
from app.source_adapters.contracts import (
    ProviderCapabilities,
    ProviderOperation,
    _validate_provider_key,
)
from app.source_adapters.package import (
    ProviderAdapterBinding,
    ProviderAdapterKind,
    ProviderEvidenceManifest,
    ProviderPackage,
    ProviderPackageError,
    ProviderPackageErrorCode,
    validate_provider_package,
)
from app.source_adapters.registry import ProviderEndpoint


PROVIDER_ARTIFACT_FORMAT = "nsfwtrack.provider-approval"
PROVIDER_ARTIFACT_VERSION = 1
PROVIDER_ARTIFACT_ATTESTATION_ALGORITHM = "sha256"

MAX_ARTIFACT_BYTES = 256 * 1024
MAX_ARTIFACT_DEPTH = 32
MAX_ARTIFACT_NODES = 20_000
MAX_ARTIFACT_STRING_LENGTH = 8_192
MAX_ARTIFACT_ARRAY_ITEMS = 512
MAX_ARTIFACT_ID_LENGTH = 128

_OPAQUE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]{0,127}\Z")
_BINDING_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_DYNAMIC_TEXT_PATTERN = re.compile(
    r"(?:"
    r"\$(?:\{|\(|[A-Za-z_])|\{\{|\{%|<%|"
    r"%[A-Za-z_][A-Za-z0-9_]*%|"
    r"\b(?:os\.)?environ\b|\bprocess\.env\b|\bgetenv\s*\(|"
    r"\b(?:include|require)\s*(?::|\()|"
    r"\b(?:importlib|entry_points|__import__|eval|exec)\b"
    r")",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?:authorization|cookie|credential|password|secret|token|"
    r"api[_ -]?key|access[_ -]?key|client[_ -]?secret|"
    r"user[_ -]?(?:account|name))\b\s*[:=]",
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
_COMPATIBLE_OPTIONAL_ARTIFACT_FIELDS = frozenset({"fixed_query_parameters"})


class ProviderArtifactErrorCode(str, Enum):
    ARTIFACT_INVALID = "artifact_invalid"
    ARTIFACT_TOO_LARGE = "artifact_too_large"
    ARTIFACT_INVALID_UTF8 = "artifact_invalid_utf8"
    ARTIFACT_DUPLICATE_KEY = "artifact_duplicate_key"
    ARTIFACT_RESOURCE_LIMIT = "artifact_resource_limit"
    ARTIFACT_UNKNOWN_FIELD = "artifact_unknown_field"
    ARTIFACT_MISSING_FIELD = "artifact_missing_field"
    ARTIFACT_FORMAT_MISMATCH = "artifact_format_mismatch"
    ARTIFACT_VERSION_UNSUPPORTED = "artifact_version_unsupported"
    ARTIFACT_ATTESTATION_MISMATCH = "artifact_attestation_mismatch"
    ARTIFACT_PROVIDER_MISMATCH = "artifact_provider_mismatch"
    ARTIFACT_OPERATION_MISMATCH = "artifact_operation_mismatch"
    ARTIFACT_BINDING_NOT_FOUND = "artifact_binding_not_found"
    ARTIFACT_BINDING_MISMATCH = "artifact_binding_mismatch"
    ARTIFACT_FACTORY_FAILED = "artifact_factory_failed"
    ARTIFACT_PACKAGE_INVALID = "artifact_package_invalid"


@dataclass(frozen=True, slots=True)
class ProviderArtifactError(ValueError):
    code: ProviderArtifactErrorCode
    cause_code: ProviderPackageErrorCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ProviderArtifactErrorCode):
            raise TypeError("code must be ProviderArtifactErrorCode")
        if self.cause_code is not None and not isinstance(
            self.cause_code,
            ProviderPackageErrorCode,
        ):
            raise TypeError("cause_code must be ProviderPackageErrorCode")
        ValueError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        if self.cause_code is None:
            return f"ProviderArtifactError(code={self.code.value!r})"
        return (
            "ProviderArtifactError("
            f"code={self.code.value!r}, cause_code={self.cause_code.value!r})"
        )


def _raise(
    code: ProviderArtifactErrorCode,
    *,
    cause_code: ProviderPackageErrorCode | None = None,
) -> None:
    raise ProviderArtifactError(code, cause_code) from None


def _opaque_id(value: str, *, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) > MAX_ARTIFACT_ID_LENGTH
        or _OPAQUE_ID_PATTERN.fullmatch(value) is None
        or value in {".", ".."}
        or ".." in value
    ):
        raise ValueError(f"{field_name} must be an opaque identifier")


def _binding_id(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) > MAX_ARTIFACT_ID_LENGTH
        or _BINDING_ID_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("binding_id must be a code-owned opaque identifier")


def _operation_tuple(
    values: tuple[ProviderOperation, ...],
    *,
    field_name: str,
) -> None:
    if not isinstance(values, tuple) or not all(
        isinstance(value, ProviderOperation) for value in values
    ):
        raise TypeError(f"{field_name} must be a ProviderOperation tuple")
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} contains duplicates")
    if any(value not in _SUPPORTED_OPERATIONS for value in values):
        raise ValueError(f"{field_name} contains an unsupported operation")


def _utc(value: datetime, *, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ProviderArtifactHeader:
    format: str
    version: int
    artifact_id: str
    provider_key: str
    scope: ProviderApprovalScope
    created_at: datetime
    review_revision: str

    def __post_init__(self) -> None:
        if self.format != PROVIDER_ARTIFACT_FORMAT:
            raise ValueError("artifact format is not supported")
        if type(self.version) is not int or self.version != PROVIDER_ARTIFACT_VERSION:
            raise ValueError("artifact version is not supported")
        _opaque_id(self.artifact_id, field_name="artifact_id")
        _validate_provider_key(self.provider_key)
        if not isinstance(self.scope, ProviderApprovalScope):
            raise TypeError("scope must be ProviderApprovalScope")
        object.__setattr__(
            self,
            "created_at",
            _utc(self.created_at, field_name="created_at"),
        )
        _opaque_id(self.review_revision, field_name="review_revision")


@dataclass(frozen=True, slots=True)
class ProviderArtifactAdapterRef:
    binding_id: str
    adapter_kind: ProviderAdapterKind
    operations: tuple[ProviderOperation, ...]

    def __post_init__(self) -> None:
        _binding_id(self.binding_id)
        if not isinstance(self.adapter_kind, ProviderAdapterKind):
            raise TypeError("adapter_kind must be ProviderAdapterKind")
        _operation_tuple(self.operations, field_name="operations")


@dataclass(frozen=True, slots=True)
class ProviderArtifactAttestation:
    algorithm: str
    canonical_sha256: str

    def __post_init__(self) -> None:
        if self.algorithm != PROVIDER_ARTIFACT_ATTESTATION_ALGORITHM:
            raise ValueError("attestation algorithm is not supported")
        if (
            not isinstance(self.canonical_sha256, str)
            or _SHA256_PATTERN.fullmatch(self.canonical_sha256) is None
        ):
            raise ValueError("canonical_sha256 is invalid")


def _validate_fixture_digests(values: tuple[tuple[str, str], ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError("fixture_digests must be a tuple")
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, tuple) or len(value) != 2:
            raise TypeError("fixture_digests entries must be pairs")
        fixture_id, digest = value
        _opaque_id(fixture_id, field_name="fixture_id")
        if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
            raise ValueError("fixture digest is invalid")
        if fixture_id in seen:
            raise ValueError("fixture_digests contains duplicates")
        seen.add(fixture_id)


@dataclass(frozen=True, slots=True)
class ProviderApprovalArtifact:
    header: ProviderArtifactHeader
    approval: ProviderApproval
    capabilities: ProviderCapabilities
    endpoint: ProviderEndpoint
    evidence: ProviderEvidenceManifest
    fixture_digests: tuple[tuple[str, str], ...]
    adapter_ref: ProviderArtifactAdapterRef
    attestation: ProviderArtifactAttestation

    def __post_init__(self) -> None:
        for value, expected_type, field_name in (
            (self.header, ProviderArtifactHeader, "header"),
            (self.approval, ProviderApproval, "approval"),
            (self.capabilities, ProviderCapabilities, "capabilities"),
            (self.endpoint, ProviderEndpoint, "endpoint"),
            (self.evidence, ProviderEvidenceManifest, "evidence"),
            (self.adapter_ref, ProviderArtifactAdapterRef, "adapter_ref"),
            (self.attestation, ProviderArtifactAttestation, "attestation"),
        ):
            if type(value) is not expected_type:
                raise TypeError(f"{field_name} has an invalid type")
        _validate_fixture_digests(self.fixture_digests)


@dataclass(frozen=True, slots=True)
class ProviderAdapterFactoryBinding:
    binding_id: str
    provider_key: str
    adapter_kind: ProviderAdapterKind
    operations: tuple[ProviderOperation, ...]
    factory: Callable[[], object] = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _binding_id(self.binding_id)
        _validate_provider_key(self.provider_key)
        if not isinstance(self.adapter_kind, ProviderAdapterKind):
            raise TypeError("adapter_kind must be ProviderAdapterKind")
        _operation_tuple(self.operations, field_name="operations")
        if not callable(self.factory):
            raise TypeError("factory must be callable")


@dataclass(frozen=True, slots=True)
class ProviderAdapterFactoryRegistry:
    bindings: tuple[ProviderAdapterFactoryBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, tuple) or not all(
            type(binding) is ProviderAdapterFactoryBinding
            for binding in self.bindings
        ):
            raise TypeError(
                "bindings must be an immutable ProviderAdapterFactoryBinding tuple"
            )
        binding_ids = tuple(binding.binding_id for binding in self.bindings)
        if len(set(binding_ids)) != len(binding_ids):
            raise ValueError("binding_id is duplicated")

    def binding(self, binding_id: str) -> ProviderAdapterFactoryBinding | None:
        for binding in self.bindings:
            if binding.binding_id == binding_id:
                return binding
        return None


class _DuplicateKeyError(ValueError):
    pass


class _DecodeError(ValueError):
    pass


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise _DecodeError


def _audit_resources(value: object) -> None:
    nodes = 0

    def visit(current: object, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > MAX_ARTIFACT_DEPTH or nodes > MAX_ARTIFACT_NODES:
            _raise(ProviderArtifactErrorCode.ARTIFACT_RESOURCE_LIMIT)
        if type(current) is dict:
            for key, child in current.items():
                nodes += 1
                if nodes > MAX_ARTIFACT_NODES:
                    _raise(ProviderArtifactErrorCode.ARTIFACT_RESOURCE_LIMIT)
                if (
                    type(key) is not str
                    or len(key) > MAX_ARTIFACT_STRING_LENGTH
                ):
                    _raise(ProviderArtifactErrorCode.ARTIFACT_RESOURCE_LIMIT)
                try:
                    key.encode("utf-8", "strict")
                except UnicodeEncodeError:
                    _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
                visit(child, depth + 1)
            return
        if type(current) is list:
            if len(current) > MAX_ARTIFACT_ARRAY_ITEMS:
                _raise(ProviderArtifactErrorCode.ARTIFACT_RESOURCE_LIMIT)
            for child in current:
                visit(child, depth + 1)
            return
        if type(current) is str:
            if len(current) > MAX_ARTIFACT_STRING_LENGTH:
                _raise(ProviderArtifactErrorCode.ARTIFACT_RESOURCE_LIMIT)
            try:
                current.encode("utf-8", "strict")
            except UnicodeEncodeError:
                _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
            return
        if type(current) is float and not math.isfinite(current):
            _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
        if current is None or type(current) in {bool, int, float}:
            return
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)

    visit(value, 1)


@lru_cache(maxsize=None)
def _type_hints(model_type: type[object]) -> dict[str, object]:
    return get_type_hints(model_type)


def _union_args(annotation: object) -> tuple[object, ...] | None:
    origin = get_origin(annotation)
    if origin in {Union, types.UnionType}:
        return get_args(annotation)
    return None


def _validate_schema_shape(value: object, annotation: object) -> None:
    union_args = _union_args(annotation)
    if union_args is not None:
        if value is None and type(None) in union_args:
            return
        remaining = tuple(item for item in union_args if item is not type(None))
        if len(remaining) != 1:
            _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
        _validate_schema_shape(value, remaining[0])
        return

    origin = get_origin(annotation)
    if origin is tuple:
        if type(value) is not list:
            _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
        arguments = get_args(annotation)
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            for child in value:
                _validate_schema_shape(child, arguments[0])
            return
        if len(value) != len(arguments):
            _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
        for child, child_type in zip(value, arguments, strict=True):
            _validate_schema_shape(child, child_type)
        return

    if isinstance(annotation, type) and is_dataclass(annotation):
        if type(value) is not dict:
            _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
        model_fields = fields(annotation)
        expected = {model_field.name for model_field in model_fields}
        actual = set(value)
        if actual - expected:
            _raise(ProviderArtifactErrorCode.ARTIFACT_UNKNOWN_FIELD)
        missing = expected - actual
        if any(
            model_field.name in missing
            and (
                model_field.name not in _COMPATIBLE_OPTIONAL_ARTIFACT_FIELDS
                or model_field.default is MISSING
            )
            for model_field in model_fields
        ):
            _raise(ProviderArtifactErrorCode.ARTIFACT_MISSING_FIELD)
        hints = _type_hints(annotation)
        for model_field in model_fields:
            if model_field.name in value:
                _validate_schema_shape(
                    value[model_field.name],
                    hints[model_field.name],
                )


def _datetime_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decode_datetime(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise _DecodeError
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise _DecodeError from None
    if _datetime_text(parsed) != value:
        raise _DecodeError
    return parsed


def _decode_value(value: object, annotation: object) -> object:
    union_args = _union_args(annotation)
    if union_args is not None:
        if value is None and type(None) in union_args:
            return None
        remaining = tuple(item for item in union_args if item is not type(None))
        if len(remaining) != 1:
            raise _DecodeError
        return _decode_value(value, remaining[0])

    origin = get_origin(annotation)
    if origin is tuple:
        if type(value) is not list:
            raise _DecodeError
        arguments = get_args(annotation)
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(_decode_value(child, arguments[0]) for child in value)
        if len(value) != len(arguments):
            raise _DecodeError
        return tuple(
            _decode_value(child, child_type)
            for child, child_type in zip(value, arguments, strict=True)
        )

    if annotation is datetime:
        return _decode_datetime(value)
    if annotation is str:
        if type(value) is not str:
            raise _DecodeError
        return value
    if annotation is bool:
        if type(value) is not bool:
            raise _DecodeError
        return value
    if annotation is int:
        if type(value) is not int:
            raise _DecodeError
        return value
    if annotation is float:
        if type(value) not in {int, float} or not math.isfinite(value):
            raise _DecodeError
        return value
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if type(value) is not str:
            raise _DecodeError
        try:
            return annotation(value)
        except ValueError:
            raise _DecodeError from None
    if isinstance(annotation, type) and is_dataclass(annotation):
        if type(value) is not dict:
            raise _DecodeError
        hints = _type_hints(annotation)
        keyword_values: dict[str, object] = {}
        for model_field in fields(annotation):
            if model_field.name in value:
                keyword_values[model_field.name] = _decode_value(
                    value[model_field.name],
                    hints[model_field.name],
                )
            elif (
                model_field.name in _COMPATIBLE_OPTIONAL_ARTIFACT_FIELDS
                and model_field.default is not MISSING
            ):
                keyword_values[model_field.name] = model_field.default
            else:
                raise _DecodeError
        try:
            return annotation(**keyword_values)
        except (TypeError, ValueError):
            raise _DecodeError from None
    if annotation is type(None) and value is None:
        return None
    raise _DecodeError


def _raw_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return _datetime_text(value)
    if is_dataclass(value) and not isinstance(value, type):
        raw: dict[str, object] = {}
        for model_field in fields(value):
            raw_value = _raw_value(getattr(value, model_field.name))
            if (
                model_field.name in _COMPATIBLE_OPTIONAL_ARTIFACT_FIELDS
                and raw_value == []
            ):
                continue
            raw[model_field.name] = raw_value
        return raw
    if isinstance(value, tuple):
        return [_raw_value(child) for child in value]
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise _DecodeError


def _canonical_json_bytes(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return rendered.encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise _DecodeError from None


def _artifact_raw(artifact: ProviderApprovalArtifact) -> dict[str, object]:
    if type(artifact) is not ProviderApprovalArtifact:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    try:
        raw = _raw_value(artifact)
    except _DecodeError:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    if type(raw) is not dict:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    return raw


def canonical_provider_artifact_bytes(
    artifact: ProviderApprovalArtifact,
) -> bytes:
    raw = _artifact_raw(artifact)
    try:
        rendered = _canonical_json_bytes(raw) + b"\n"
    except _DecodeError:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    if len(rendered) > MAX_ARTIFACT_BYTES:
        _raise(ProviderArtifactErrorCode.ARTIFACT_TOO_LARGE)
    return rendered


def serialize_provider_artifact(artifact: ProviderApprovalArtifact) -> bytes:
    return canonical_provider_artifact_bytes(artifact)


def compute_provider_artifact_sha256(
    artifact: ProviderApprovalArtifact,
) -> str:
    raw = _artifact_raw(artifact)
    raw.pop("attestation", None)
    try:
        payload = _canonical_json_bytes(raw)
    except _DecodeError:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    return sha256(payload).hexdigest()


def verify_provider_artifact_attestation(
    artifact: ProviderApprovalArtifact,
) -> None:
    expected = compute_provider_artifact_sha256(artifact)
    if not compare_digest(expected, artifact.attestation.canonical_sha256):
        _raise(ProviderArtifactErrorCode.ARTIFACT_ATTESTATION_MISMATCH)


def _decode_json(artifact_bytes: object) -> dict[str, object]:
    if type(artifact_bytes) is not bytes:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    if len(artifact_bytes) > MAX_ARTIFACT_BYTES:
        _raise(ProviderArtifactErrorCode.ARTIFACT_TOO_LARGE)
    try:
        decoded = artifact_bytes.decode("utf-8", "strict")
    except UnicodeDecodeError:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID_UTF8)
    try:
        document = json.loads(
            decoded,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except _DuplicateKeyError:
        _raise(ProviderArtifactErrorCode.ARTIFACT_DUPLICATE_KEY)
    except RecursionError:
        _raise(ProviderArtifactErrorCode.ARTIFACT_RESOURCE_LIMIT)
    except (json.JSONDecodeError, _DecodeError, ValueError):
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    _audit_resources(document)
    _validate_schema_shape(document, ProviderApprovalArtifact)
    if type(document) is not dict:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    return document


def _validate_raw_format(document: dict[str, object]) -> None:
    header = document["header"]
    if type(header) is not dict:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    if header["format"] != PROVIDER_ARTIFACT_FORMAT:
        _raise(ProviderArtifactErrorCode.ARTIFACT_FORMAT_MISMATCH)
    version = header["version"]
    if type(version) is not int or version != PROVIDER_ARTIFACT_VERSION:
        _raise(ProviderArtifactErrorCode.ARTIFACT_VERSION_UNSUPPORTED)


def _verify_raw_attestation(document: dict[str, object]) -> None:
    attestation = document["attestation"]
    if type(attestation) is not dict:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    algorithm = attestation["algorithm"]
    digest = attestation["canonical_sha256"]
    if (
        algorithm != PROVIDER_ARTIFACT_ATTESTATION_ALGORITHM
        or type(digest) is not str
        or _SHA256_PATTERN.fullmatch(digest) is None
    ):
        _raise(ProviderArtifactErrorCode.ARTIFACT_ATTESTATION_MISMATCH)
    payload = {
        key: value
        for key, value in document.items()
        if key != "attestation"
    }
    try:
        expected = sha256(_canonical_json_bytes(payload)).hexdigest()
    except _DecodeError:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    if not compare_digest(expected, digest):
        _raise(ProviderArtifactErrorCode.ARTIFACT_ATTESTATION_MISMATCH)


def _typed_artifact(document: dict[str, object]) -> ProviderApprovalArtifact:
    try:
        artifact = _decode_value(document, ProviderApprovalArtifact)
    except _DecodeError:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    if type(artifact) is not ProviderApprovalArtifact:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    try:
        normalized = _raw_value(artifact)
    except _DecodeError:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    if normalized != document:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    return artifact


def parse_provider_artifact(artifact_bytes: bytes) -> ProviderApprovalArtifact:
    document = _decode_json(artifact_bytes)
    _validate_raw_format(document)
    _verify_raw_attestation(document)
    return _typed_artifact(document)


def _validate_cross_component_parity(artifact: ProviderApprovalArtifact) -> None:
    header = artifact.header
    approval = artifact.approval
    capabilities = artifact.capabilities
    endpoint = artifact.endpoint
    evidence = artifact.evidence
    adapter_ref = artifact.adapter_ref

    if (
        header.provider_key != approval.provider_key
        or capabilities.provider_key != approval.provider_key
        or endpoint.provider_key != approval.provider_key
        or evidence.provider_key != approval.provider_key
    ):
        _raise(ProviderArtifactErrorCode.ARTIFACT_PROVIDER_MISMATCH)
    if (
        header.scope is not approval.scope
        or evidence.scope is not approval.scope
        or header.review_revision != evidence.review_revision
        or header.created_at != evidence.reviewed_at
        or evidence.approval_id != approval.approval_id
        or capabilities.display_name != approval.display_name
        or capabilities.content_scope != approval.content_scope
        or evidence.display_name != approval.display_name
        or evidence.content_scope != approval.content_scope
    ):
        _raise(ProviderArtifactErrorCode.ARTIFACT_PROVIDER_MISMATCH)
    if endpoint.capabilities != capabilities:
        _raise(ProviderArtifactErrorCode.ARTIFACT_OPERATION_MISMATCH)
    operations = approval.capabilities
    if (
        capabilities.operations != operations
        or tuple(value.operation for value in endpoint.operations) != operations
        or evidence.reviewed_operations != operations
        or adapter_ref.operations != operations
    ):
        _raise(ProviderArtifactErrorCode.ARTIFACT_OPERATION_MISMATCH)
    evidence_digests = {
        value.fixture_id: value.fixture_sha256
        for value in evidence.fixture_evidence
    }
    artifact_digests = dict(artifact.fixture_digests)
    if artifact_digests != evidence_digests:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)

    policy_texts = (
        approval.display_name,
        approval.content_scope,
        approval.product_fit,
        approval.lawful_access_basis,
        approval.terms_basis,
        capabilities.display_name,
        capabilities.content_scope,
        evidence.display_name,
        evidence.content_scope,
        evidence.license_conclusion,
        evidence.terms_conclusion,
        evidence.lawful_access_conclusion,
        *(value for value in (evidence.notes,) if value is not None),
        *(
            header.value
            for operation in approval.operations
            for header in operation.fixed_headers
        ),
        *(
            value
            for operation in endpoint.operations
            for _name, value in operation.fixed_headers
        ),
    )
    for value in policy_texts:
        stripped = value.strip()
        if (
            "://" in value
            or _DYNAMIC_TEXT_PATTERN.search(value) is not None
            or _SENSITIVE_ASSIGNMENT_PATTERN.search(value) is not None
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
            _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)


def load_provider_package_from_artifact(
    artifact_bytes: bytes,
    factory_registry: ProviderAdapterFactoryRegistry,
) -> ProviderPackage:
    artifact = parse_provider_artifact(artifact_bytes)
    _validate_cross_component_parity(artifact)

    if type(factory_registry) is not ProviderAdapterFactoryRegistry:
        _raise(ProviderArtifactErrorCode.ARTIFACT_INVALID)
    factory_binding = factory_registry.binding(artifact.adapter_ref.binding_id)
    if factory_binding is None:
        _raise(ProviderArtifactErrorCode.ARTIFACT_BINDING_NOT_FOUND)
    if (
        factory_binding.provider_key != artifact.header.provider_key
        or factory_binding.adapter_kind is not artifact.adapter_ref.adapter_kind
        or factory_binding.operations != artifact.adapter_ref.operations
    ):
        _raise(ProviderArtifactErrorCode.ARTIFACT_BINDING_MISMATCH)

    try:
        adapter = factory_binding.factory()
    except Exception:
        _raise(ProviderArtifactErrorCode.ARTIFACT_FACTORY_FAILED)

    try:
        binding = ProviderAdapterBinding(
            provider_key=artifact.approval.provider_key,
            display_name=artifact.approval.display_name,
            content_scope=artifact.approval.content_scope,
            operations=artifact.adapter_ref.operations,
            adapter=adapter,
            adapter_kind=artifact.adapter_ref.adapter_kind,
        )
        package = ProviderPackage(
            scope=artifact.header.scope,
            approval=artifact.approval,
            capabilities=artifact.capabilities,
            endpoint=artifact.endpoint,
            binding=binding,
            evidence=artifact.evidence,
            fixture_digests=artifact.fixture_digests,
        )
        validate_provider_package(package)
    except ProviderPackageError as error:
        _raise(
            ProviderArtifactErrorCode.ARTIFACT_PACKAGE_INVALID,
            cause_code=error.code,
        )
    except Exception:
        _raise(ProviderArtifactErrorCode.ARTIFACT_PACKAGE_INVALID)
    return package


__all__ = [
    "MAX_ARTIFACT_ARRAY_ITEMS",
    "MAX_ARTIFACT_BYTES",
    "MAX_ARTIFACT_DEPTH",
    "MAX_ARTIFACT_NODES",
    "MAX_ARTIFACT_STRING_LENGTH",
    "PROVIDER_ARTIFACT_ATTESTATION_ALGORITHM",
    "PROVIDER_ARTIFACT_FORMAT",
    "PROVIDER_ARTIFACT_VERSION",
    "ProviderAdapterFactoryBinding",
    "ProviderAdapterFactoryRegistry",
    "ProviderApprovalArtifact",
    "ProviderArtifactAdapterRef",
    "ProviderArtifactAttestation",
    "ProviderArtifactError",
    "ProviderArtifactErrorCode",
    "ProviderArtifactHeader",
    "canonical_provider_artifact_bytes",
    "compute_provider_artifact_sha256",
    "load_provider_package_from_artifact",
    "parse_provider_artifact",
    "serialize_provider_artifact",
    "verify_provider_artifact_attestation",
]
