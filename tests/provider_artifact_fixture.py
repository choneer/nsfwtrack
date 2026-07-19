"""Synthetic Provider Approval Artifact used only by N4D-D-A tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.source_adapters import (
    PROVIDER_ARTIFACT_ATTESTATION_ALGORITHM,
    PROVIDER_ARTIFACT_FORMAT,
    PROVIDER_ARTIFACT_VERSION,
    ProviderAdapterFactoryBinding,
    ProviderAdapterFactoryRegistry,
    ProviderAdapterKind,
    ProviderApprovalArtifact,
    ProviderArtifactAdapterRef,
    ProviderArtifactAttestation,
    ProviderArtifactHeader,
    compute_provider_artifact_sha256,
    serialize_provider_artifact,
)
from tests.provider_package_fixture import VIDEO_PACKAGE
from tests.video_metadata_fixture_provider import FixtureVideoMetadataProvider


SYNTHETIC_BINDING_ID = "synthetic_video_adapter_v1"
SYNTHETIC_ARTIFACT_ID = "fixture_video_artifact_v1"
SYNTHETIC_ARTIFACT_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "provider_artifact"
    / "synthetic_video_artifact.json"
)

_UNATTESTED_ARTIFACT = ProviderApprovalArtifact(
    header=ProviderArtifactHeader(
        format=PROVIDER_ARTIFACT_FORMAT,
        version=PROVIDER_ARTIFACT_VERSION,
        artifact_id=SYNTHETIC_ARTIFACT_ID,
        provider_key=VIDEO_PACKAGE.provider_key,
        scope=VIDEO_PACKAGE.scope,
        created_at=VIDEO_PACKAGE.evidence.reviewed_at,
        review_revision=VIDEO_PACKAGE.evidence.review_revision,
    ),
    approval=VIDEO_PACKAGE.approval,
    capabilities=VIDEO_PACKAGE.capabilities,
    endpoint=VIDEO_PACKAGE.endpoint,
    evidence=VIDEO_PACKAGE.evidence,
    fixture_digests=VIDEO_PACKAGE.fixture_digests,
    adapter_ref=ProviderArtifactAdapterRef(
        binding_id=SYNTHETIC_BINDING_ID,
        adapter_kind=ProviderAdapterKind.VIDEO_METADATA,
        operations=VIDEO_PACKAGE.approval.capabilities,
    ),
    attestation=ProviderArtifactAttestation(
        algorithm=PROVIDER_ARTIFACT_ATTESTATION_ALGORITHM,
        canonical_sha256="0" * 64,
    ),
)

SYNTHETIC_VIDEO_ARTIFACT = replace(
    _UNATTESTED_ARTIFACT,
    attestation=ProviderArtifactAttestation(
        algorithm=PROVIDER_ARTIFACT_ATTESTATION_ALGORITHM,
        canonical_sha256=compute_provider_artifact_sha256(_UNATTESTED_ARTIFACT),
    ),
)
SYNTHETIC_ARTIFACT_BYTES = serialize_provider_artifact(SYNTHETIC_VIDEO_ARTIFACT)

SYNTHETIC_FACTORY_BINDING = ProviderAdapterFactoryBinding(
    binding_id=SYNTHETIC_BINDING_ID,
    provider_key=VIDEO_PACKAGE.provider_key,
    adapter_kind=ProviderAdapterKind.VIDEO_METADATA,
    operations=VIDEO_PACKAGE.approval.capabilities,
    factory=FixtureVideoMetadataProvider,
)
SYNTHETIC_FACTORY_REGISTRY = ProviderAdapterFactoryRegistry(
    (SYNTHETIC_FACTORY_BINDING,)
)


def read_synthetic_artifact_bytes() -> bytes:
    return SYNTHETIC_ARTIFACT_PATH.read_bytes()


__all__ = [
    "SYNTHETIC_ARTIFACT_BYTES",
    "SYNTHETIC_ARTIFACT_ID",
    "SYNTHETIC_ARTIFACT_PATH",
    "SYNTHETIC_BINDING_ID",
    "SYNTHETIC_FACTORY_BINDING",
    "SYNTHETIC_FACTORY_REGISTRY",
    "SYNTHETIC_VIDEO_ARTIFACT",
    "read_synthetic_artifact_bytes",
]
