from __future__ import annotations

import copy
import importlib
import json
import logging
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import httpx2
import pytest
from sqlalchemy.orm import Session

from app.services.outbound_http import OutboundHttpClient
from app.source_adapters import (
    MAX_ARTIFACT_ARRAY_ITEMS,
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACT_DEPTH,
    MAX_ARTIFACT_NODES,
    MAX_ARTIFACT_STRING_LENGTH,
    PRODUCTION_ENDPOINT_REGISTRY,
    PROVIDER_ARTIFACT_FORMAT,
    PROVIDER_ARTIFACT_VERSION,
    ProviderAdapterFactoryBinding,
    ProviderAdapterFactoryRegistry,
    ProviderAdapterKind,
    ProviderApprovalArtifact,
    ProviderArtifactAdapterRef,
    ProviderArtifactAttestation,
    ProviderArtifactError,
    ProviderArtifactErrorCode,
    ProviderArtifactHeader,
    ProviderPackageErrorCode,
    ProviderOperation,
    canonical_provider_artifact_bytes,
    compute_provider_artifact_sha256,
    load_provider_package_from_artifact,
    parse_provider_artifact,
    serialize_provider_artifact,
    verify_provider_artifact_attestation,
)
from tests.provider_artifact_fixture import (
    SYNTHETIC_ARTIFACT_BYTES,
    SYNTHETIC_BINDING_ID,
    SYNTHETIC_FACTORY_BINDING,
    SYNTHETIC_FACTORY_REGISTRY,
    SYNTHETIC_VIDEO_ARTIFACT,
    read_synthetic_artifact_bytes,
)
from tests.provider_package_fixture import VIDEO_PACKAGE
from tests.video_metadata_fixture_provider import FixtureVideoMetadataProvider


def _assert_artifact_error(
    code: ProviderArtifactErrorCode,
    operation,
) -> ProviderArtifactError:
    with pytest.raises(ProviderArtifactError) as exc_info:
        operation()
    assert exc_info.value.code is code
    assert str(exc_info.value) == code.value
    return exc_info.value


def _document() -> dict[str, object]:
    value = json.loads(SYNTHETIC_ARTIFACT_BYTES)
    assert isinstance(value, dict)
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _document_bytes(
    document: dict[str, object],
    *,
    reattest: bool = False,
    canonical: bool = True,
) -> bytes:
    value = copy.deepcopy(document)
    if reattest:
        payload = {key: child for key, child in value.items() if key != "attestation"}
        value["attestation"] = {
            "algorithm": "sha256",
            "canonical_sha256": sha256(_canonical_json(payload)).hexdigest(),
        }
    if canonical:
        return _canonical_json(value) + b"\n"
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def _attest(artifact: ProviderApprovalArtifact) -> ProviderApprovalArtifact:
    return replace(
        artifact,
        attestation=ProviderArtifactAttestation(
            algorithm="sha256",
            canonical_sha256=compute_provider_artifact_sha256(artifact),
        ),
    )


class CountingFactory:
    def __init__(self, result: object = None, error: Exception | None = None) -> None:
        self.calls = 0
        self.result = result
        self.error = error

    def __call__(self) -> object:
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.result is None:
            return FixtureVideoMetadataProvider()
        return self.result


def _factory_registry(
    factory: CountingFactory,
    *,
    provider_key: str = VIDEO_PACKAGE.provider_key,
    adapter_kind: ProviderAdapterKind = ProviderAdapterKind.VIDEO_METADATA,
    operations: tuple[ProviderOperation, ...] = VIDEO_PACKAGE.approval.capabilities,
    binding_id: str = SYNTHETIC_BINDING_ID,
) -> ProviderAdapterFactoryRegistry:
    return ProviderAdapterFactoryRegistry(
        (
            ProviderAdapterFactoryBinding(
                binding_id=binding_id,
                provider_key=provider_key,
                adapter_kind=adapter_kind,
                operations=operations,
                factory=factory,
            ),
        )
    )


def test_artifact_contracts_are_frozen_slotted_and_tuple_only() -> None:
    values = (
        SYNTHETIC_VIDEO_ARTIFACT.header,
        SYNTHETIC_VIDEO_ARTIFACT.adapter_ref,
        SYNTHETIC_VIDEO_ARTIFACT.attestation,
        SYNTHETIC_VIDEO_ARTIFACT,
        SYNTHETIC_FACTORY_BINDING,
        SYNTHETIC_FACTORY_REGISTRY,
    )
    for value in values:
        assert not hasattr(value, "__dict__")
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            value.extra = "forbidden"  # type: ignore[attr-defined]

    with pytest.raises(TypeError):
        replace(
            SYNTHETIC_VIDEO_ARTIFACT.adapter_ref,
            operations=[ProviderOperation.SEARCH],
        )
    with pytest.raises(TypeError):
        replace(SYNTHETIC_VIDEO_ARTIFACT, fixture_digests=[])
    with pytest.raises(TypeError):
        ProviderAdapterFactoryRegistry([SYNTHETIC_FACTORY_BINDING])  # type: ignore[arg-type]


def test_factory_registry_rejects_duplicate_binding_id() -> None:
    with pytest.raises(ValueError, match="duplicated"):
        ProviderAdapterFactoryRegistry(
            (SYNTHETIC_FACTORY_BINDING, SYNTHETIC_FACTORY_BINDING)
        )


@pytest.mark.parametrize(
    "binding_id",
    [
        "module.Factory",
        "module:factory",
        "path/factory",
        "path\\factory",
        "http://fixture.invalid",
        "file://fixture",
    ],
)
def test_binding_id_rejects_import_path_and_url_forms(binding_id: str) -> None:
    with pytest.raises(ValueError, match="opaque"):
        replace(SYNTHETIC_VIDEO_ARTIFACT.adapter_ref, binding_id=binding_id)


def test_header_and_attestation_validate_utc_enum_and_sha_grammar() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(SYNTHETIC_VIDEO_ARTIFACT.header, created_at=datetime.now())
    offset = timezone(timedelta(hours=8))
    normalized = replace(
        SYNTHETIC_VIDEO_ARTIFACT.header,
        created_at=datetime(2026, 7, 19, 8, 0, tzinfo=offset),
    )
    assert normalized.created_at.utcoffset() == timedelta(0)
    with pytest.raises(TypeError, match="adapter_kind"):
        replace(
            SYNTHETIC_VIDEO_ARTIFACT.adapter_ref,
            adapter_kind="video_metadata",
        )
    with pytest.raises(ValueError, match="canonical_sha256"):
        ProviderArtifactAttestation("sha256", "A" * 64)


def test_stable_error_code_set_is_complete() -> None:
    assert {value.value for value in ProviderArtifactErrorCode} == {
        "artifact_invalid",
        "artifact_too_large",
        "artifact_invalid_utf8",
        "artifact_duplicate_key",
        "artifact_resource_limit",
        "artifact_unknown_field",
        "artifact_missing_field",
        "artifact_format_mismatch",
        "artifact_version_unsupported",
        "artifact_attestation_mismatch",
        "artifact_provider_mismatch",
        "artifact_operation_mismatch",
        "artifact_binding_not_found",
        "artifact_binding_mismatch",
        "artifact_factory_failed",
        "artifact_package_invalid",
    }


def test_canonical_fixture_matches_serializer_and_round_trips() -> None:
    fixture_bytes = read_synthetic_artifact_bytes()
    assert fixture_bytes == SYNTHETIC_ARTIFACT_BYTES
    assert fixture_bytes == serialize_provider_artifact(SYNTHETIC_VIDEO_ARTIFACT)
    assert fixture_bytes == canonical_provider_artifact_bytes(
        SYNTHETIC_VIDEO_ARTIFACT
    )
    parsed = parse_provider_artifact(fixture_bytes)
    assert parsed == SYNTHETIC_VIDEO_ARTIFACT
    assert serialize_provider_artifact(parsed) == fixture_bytes
    verify_provider_artifact_attestation(parsed)


def test_synthetic_artifact_is_fixture_only_and_video_only() -> None:
    artifact = SYNTHETIC_VIDEO_ARTIFACT
    assert artifact.header.format == PROVIDER_ARTIFACT_FORMAT
    assert artifact.header.version == PROVIDER_ARTIFACT_VERSION
    assert artifact.header.scope.value == "test_fixture"
    assert all(host.hostname.endswith(".invalid") for host in artifact.approval.hosts)
    assert len(artifact.fixture_digests) == 6
    assert all(fixture_id.startswith("video-") for fixture_id, _ in artifact.fixture_digests)
    assert b"://" not in SYNTHETIC_ARTIFACT_BYTES
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_ENDPOINT_REGISTRY.providers)


@pytest.mark.parametrize(
    "value",
    [
        "{}",
        Path("artifact.json"),
        bytearray(b"{}"),
        memoryview(b"{}"),
    ],
)
def test_parser_accepts_exact_bytes_only(value: object) -> None:
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_INVALID,
        lambda: parse_provider_artifact(value),  # type: ignore[arg-type]
    )


def test_parser_rejects_bytes_subclasses() -> None:
    class BytesSubclass(bytes):
        pass

    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_INVALID,
        lambda: parse_provider_artifact(BytesSubclass(SYNTHETIC_ARTIFACT_BYTES)),
    )


def test_size_precedes_utf8_and_invalid_utf8_is_stable() -> None:
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_TOO_LARGE,
        lambda: parse_provider_artifact(b"\xff" * (MAX_ARTIFACT_BYTES + 1)),
    )
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_INVALID_UTF8,
        lambda: parse_provider_artifact(b"{\"x\":\xff}"),
    )


@pytest.mark.parametrize(
    "payload",
    [
        b'{"header":{},"header":{}}',
        b'{"header":{"format":"a","format":"b"}}',
        b'{"items":[{"value":1,"value":2}]}',
    ],
)
def test_duplicate_json_key_is_rejected_at_any_depth(payload: bytes) -> None:
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_DUPLICATE_KEY,
        lambda: parse_provider_artifact(payload),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"unknown": None}),
        lambda value: value["approval"].update({"unknown": None}),
        lambda value: value["endpoint"]["operations"][0].update(
            {"unknown": None}
        ),
    ],
)
def test_unknown_fields_are_rejected_at_any_schema_level(mutation) -> None:
    document = _document()
    mutation(document)
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_UNKNOWN_FIELD,
        lambda: parse_provider_artifact(_document_bytes(document)),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("attestation"),
        lambda value: value["header"].pop("artifact_id"),
        lambda value: value["approval"].pop("approval_version"),
        lambda value: value["evidence"]["fixture_evidence"][0].pop(
            "expected_outcome"
        ),
    ],
)
def test_missing_fields_are_rejected_at_any_schema_level(mutation) -> None:
    document = _document()
    mutation(document)
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_MISSING_FIELD,
        lambda: parse_provider_artifact(_document_bytes(document)),
    )


@pytest.mark.parametrize(
    "constant",
    [b"NaN", b"Infinity", b"-Infinity", b"1e999"],
)
def test_non_finite_json_constants_are_rejected(constant: bytes) -> None:
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_INVALID,
        lambda: parse_provider_artifact(b'{"value":' + constant + b"}"),
    )


def test_bool_is_not_accepted_as_int() -> None:
    document = _document()
    document["header"]["version"] = True
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_VERSION_UNSUPPORTED,
        lambda: parse_provider_artifact(_document_bytes(document)),
    )

    document = _document()
    document["approval"]["approval_version"] = True
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_INVALID,
        lambda: parse_provider_artifact(
            _document_bytes(document, reattest=True)
        ),
    )


def test_depth_array_string_and_node_resource_limits() -> None:
    long_string = b'{"value":"' + b"x" * (MAX_ARTIFACT_STRING_LENGTH + 1) + b'"}'
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_RESOURCE_LIMIT,
        lambda: parse_provider_artifact(long_string),
    )

    too_many_items = b"[" + b",".join(
        b"0" for _ in range(MAX_ARTIFACT_ARRAY_ITEMS + 1)
    ) + b"]"
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_RESOURCE_LIMIT,
        lambda: parse_provider_artifact(too_many_items),
    )

    deep: object = 0
    for _ in range(MAX_ARTIFACT_DEPTH):
        deep = [deep]
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_RESOURCE_LIMIT,
        lambda: parse_provider_artifact(_canonical_json(deep)),
    )

    many_nodes = {f"k{index}": 0 for index in range(MAX_ARTIFACT_NODES // 2 + 1)}
    encoded = _canonical_json(many_nodes)
    assert len(encoded) <= MAX_ARTIFACT_BYTES
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_RESOURCE_LIMIT,
        lambda: parse_provider_artifact(encoded),
    )


def test_format_and_version_checks_are_stable() -> None:
    document = _document()
    document["header"]["format"] = "synthetic-marker"
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_FORMAT_MISMATCH,
        lambda: parse_provider_artifact(_document_bytes(document)),
    )

    document = _document()
    document["header"]["version"] = 2
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_VERSION_UNSUPPORTED,
        lambda: parse_provider_artifact(_document_bytes(document)),
    )


def test_attestation_mismatch_is_stable_and_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    document = _document()
    marker_digest = "f" * 64
    document["attestation"]["canonical_sha256"] = marker_digest
    error = _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_ATTESTATION_MISMATCH,
        lambda: parse_provider_artifact(_document_bytes(document)),
    )
    rendered = f"{error!s} {error!r} {caplog.text}"
    assert marker_digest not in rendered
    assert SYNTHETIC_VIDEO_ARTIFACT.attestation.canonical_sha256 not in rendered


def test_attestation_digest_excludes_attestation_itself() -> None:
    changed = replace(
        SYNTHETIC_VIDEO_ARTIFACT,
        attestation=ProviderArtifactAttestation("sha256", "0" * 64),
    )
    assert compute_provider_artifact_sha256(changed) == (
        SYNTHETIC_VIDEO_ARTIFACT.attestation.canonical_sha256
    )


def test_attestation_failure_precedes_binding_lookup_and_factory() -> None:
    document = _document()
    document["attestation"]["canonical_sha256"] = "f" * 64
    factory = CountingFactory()
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_ATTESTATION_MISMATCH,
        lambda: load_provider_package_from_artifact(
            _document_bytes(document),
            _factory_registry(factory, binding_id="other_synthetic_binding"),
        ),
    )
    assert factory.calls == 0


@pytest.mark.parametrize(
    "field, value",
    [
        ("algorithm", "sha512"),
        ("canonical_sha256", "A" * 64),
    ],
)
def test_attestation_algorithm_and_grammar_are_exact(field: str, value: str) -> None:
    document = _document()
    document["attestation"][field] = value
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_ATTESTATION_MISMATCH,
        lambda: parse_provider_artifact(_document_bytes(document)),
    )


def test_noncanonical_json_converges_to_canonical_bytes() -> None:
    document = _document()
    reversed_document = dict(reversed(tuple(document.items())))
    noncanonical = _document_bytes(reversed_document, canonical=False)
    assert noncanonical != SYNTHETIC_ARTIFACT_BYTES
    parsed = parse_provider_artifact(noncanonical)
    assert serialize_provider_artifact(parsed) == SYNTHETIC_ARTIFACT_BYTES
    assert serialize_provider_artifact(parsed) == serialize_provider_artifact(parsed)


def test_unicode_null_and_tuple_round_trip_is_deterministic() -> None:
    display_name = "合成影视元数据 Provider"
    capabilities = replace(
        SYNTHETIC_VIDEO_ARTIFACT.capabilities,
        display_name=display_name,
    )
    artifact = replace(
        SYNTHETIC_VIDEO_ARTIFACT,
        approval=replace(
            SYNTHETIC_VIDEO_ARTIFACT.approval,
            display_name=display_name,
        ),
        capabilities=capabilities,
        endpoint=replace(
            SYNTHETIC_VIDEO_ARTIFACT.endpoint,
            capabilities=capabilities,
        ),
        evidence=replace(
            SYNTHETIC_VIDEO_ARTIFACT.evidence,
            display_name=display_name,
            notes=None,
        ),
    )
    artifact = _attest(artifact)
    encoded = serialize_provider_artifact(artifact)
    assert display_name.encode("utf-8") in encoded
    assert b'"notes":null' in encoded
    parsed = parse_provider_artifact(encoded)
    assert parsed == artifact
    assert isinstance(parsed.adapter_ref.operations, tuple)
    assert isinstance(parsed.fixture_digests, tuple)
    assert serialize_provider_artifact(parsed) == encoded


def test_provider_and_operation_parity_fail_before_factory() -> None:
    factory = CountingFactory()
    registry = _factory_registry(factory)

    document = _document()
    document["header"]["provider_key"] = "other_fixture"
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_PROVIDER_MISMATCH,
        lambda: load_provider_package_from_artifact(
            _document_bytes(document, reattest=True),
            registry,
        ),
    )
    assert factory.calls == 0

    document = _document()
    document["adapter_ref"]["operations"] = ["detail", "search", "asset_list"]
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_OPERATION_MISMATCH,
        lambda: load_provider_package_from_artifact(
            _document_bytes(document, reattest=True),
            registry,
        ),
    )
    assert factory.calls == 0


def test_fixture_digest_parity_fails_before_factory() -> None:
    document = _document()
    document["fixture_digests"] = document["fixture_digests"][:-1]
    factory = CountingFactory()
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_INVALID,
        lambda: load_provider_package_from_artifact(
            _document_bytes(document, reattest=True),
            _factory_registry(factory),
        ),
    )
    assert factory.calls == 0


@pytest.mark.parametrize(
    "text",
    [
        "$HOME",
        "${SYNTHETIC_VALUE}",
        "os.environ.get('SYNTHETIC_VALUE')",
        "authorization=synthetic-private-marker",
        '{"raw":"synthetic-private-marker"}',
    ],
)
def test_dynamic_sensitive_and_raw_policy_text_fails_before_factory(
    text: str,
) -> None:
    document = _document()
    document["approval"]["product_fit"] = text
    factory = CountingFactory()
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_INVALID,
        lambda: load_provider_package_from_artifact(
            _document_bytes(document, reattest=True),
            _factory_registry(factory),
        ),
    )
    assert factory.calls == 0


def test_binding_lookup_and_metadata_are_code_owned() -> None:
    _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_BINDING_NOT_FOUND,
        lambda: load_provider_package_from_artifact(
            SYNTHETIC_ARTIFACT_BYTES,
            ProviderAdapterFactoryRegistry(()),
        ),
    )

    for values in (
        {"provider_key": "other_fixture"},
        {"adapter_kind": ProviderAdapterKind.SOURCE_METADATA},
        {"operations": tuple(reversed(VIDEO_PACKAGE.approval.capabilities))},
    ):
        factory = CountingFactory()
        registry = _factory_registry(factory, **values)
        _assert_artifact_error(
            ProviderArtifactErrorCode.ARTIFACT_BINDING_MISMATCH,
            lambda registry=registry: load_provider_package_from_artifact(
                SYNTHETIC_ARTIFACT_BYTES,
                registry,
            ),
        )
        assert factory.calls == 0


def test_factory_failure_is_redacted_and_called_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "synthetic-private-factory-marker"
    factory = CountingFactory(error=RuntimeError(marker))
    caplog.set_level(logging.DEBUG)
    error = _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_FACTORY_FAILED,
        lambda: load_provider_package_from_artifact(
            SYNTHETIC_ARTIFACT_BYTES,
            _factory_registry(factory),
        ),
    )
    assert factory.calls == 1
    assert marker not in f"{error!s} {error!r} {caplog.text}"


def test_factory_returned_adapter_still_passes_package_validation() -> None:
    class WrongAdapter:
        key = VIDEO_PACKAGE.provider_key

    factory = CountingFactory(result=WrongAdapter())
    error = _assert_artifact_error(
        ProviderArtifactErrorCode.ARTIFACT_PACKAGE_INVALID,
        lambda: load_provider_package_from_artifact(
            SYNTHETIC_ARTIFACT_BYTES,
            _factory_registry(factory),
        ),
    )
    assert factory.calls == 1
    assert error.cause_code is ProviderPackageErrorCode.PACKAGE_ADAPTER_MISMATCH


def test_success_calls_factory_once_and_executes_no_adapter_operation() -> None:
    class ForbiddenOperationAdapter:
        key = VIDEO_PACKAGE.provider_key

        async def search(self, query: str, *, page: int, page_size: int):
            raise AssertionError("search must not execute")

        async def detail(self, external_id: str):
            raise AssertionError("detail must not execute")

        async def asset_list(self, external_id: str):
            raise AssertionError("asset_list must not execute")

    factory = CountingFactory(result=ForbiddenOperationAdapter())
    package = load_provider_package_from_artifact(
        SYNTHETIC_ARTIFACT_BYTES,
        _factory_registry(factory),
    )
    assert factory.calls == 1
    assert package.approval == VIDEO_PACKAGE.approval
    assert package.capabilities == VIDEO_PACKAGE.capabilities
    assert package.endpoint == VIDEO_PACKAGE.endpoint
    assert package.evidence == VIDEO_PACKAGE.evidence
    assert package.fixture_digests == VIDEO_PACKAGE.fixture_digests
    assert package.binding.adapter is factory.result
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_ENDPOINT_REGISTRY.providers)


@pytest.mark.parametrize(
    "artifact_bytes, code",
    [
        ("not-bytes", ProviderArtifactErrorCode.ARTIFACT_INVALID),
        (b"\xff", ProviderArtifactErrorCode.ARTIFACT_INVALID_UTF8),
        (
            b'{"x":1,"x":2}',
            ProviderArtifactErrorCode.ARTIFACT_DUPLICATE_KEY,
        ),
    ],
)
def test_factory_is_never_called_before_parser_gates(
    artifact_bytes: object,
    code: ProviderArtifactErrorCode,
) -> None:
    factory = CountingFactory()
    _assert_artifact_error(
        code,
        lambda: load_provider_package_from_artifact(
            artifact_bytes,  # type: ignore[arg-type]
            _factory_registry(factory),
        ),
    )
    assert factory.calls == 0


def test_parser_serializer_attestation_and_loader_have_zero_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_bytes = read_synthetic_artifact_bytes()

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
    monkeypatch.setattr(importlib, "import_module", forbidden)
    monkeypatch.setattr(FixtureVideoMetadataProvider, "search", forbidden)
    monkeypatch.setattr(FixtureVideoMetadataProvider, "detail", forbidden)
    monkeypatch.setattr(FixtureVideoMetadataProvider, "asset_list", forbidden)

    parsed = parse_provider_artifact(fixture_bytes)
    assert serialize_provider_artifact(parsed) == fixture_bytes
    assert canonical_provider_artifact_bytes(parsed) == fixture_bytes
    assert compute_provider_artifact_sha256(parsed) == (
        parsed.attestation.canonical_sha256
    )
    verify_provider_artifact_attestation(parsed)
    package = load_provider_package_from_artifact(
        fixture_bytes,
        SYNTHETIC_FACTORY_REGISTRY,
    )
    assert package.provider_key == VIDEO_PACKAGE.provider_key
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_ENDPOINT_REGISTRY.providers)


def test_final_production_registry_identity_is_unchanged() -> None:
    before = PRODUCTION_ENDPOINT_REGISTRY
    package = load_provider_package_from_artifact(
        SYNTHETIC_ARTIFACT_BYTES,
        SYNTHETIC_FACTORY_REGISTRY,
    )
    assert package.binding.adapter_kind is ProviderAdapterKind.VIDEO_METADATA
    assert PRODUCTION_ENDPOINT_REGISTRY is before
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_ENDPOINT_REGISTRY.providers)
