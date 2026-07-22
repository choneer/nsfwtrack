"""Build TEST_FIXTURE Jiuse package (nsfwpro factory key jiuse-vod)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from app.providers.jiuse.adapter import JiuseFixtureVideoMetadataAdapter
from app.providers.jiuse.approval import (
    JIUSE_APPROVAL,
    JIUSE_CAPABILITIES,
    JIUSE_ENDPOINT,
    JIUSE_PROVIDER_KEY,
)
from app.source_adapters.approval import ProviderApprovalScope
from app.source_adapters.contracts import ProviderOperation
from app.source_adapters.package import (
    ProviderAdapterBinding,
    ProviderAdapterKind,
    ProviderEvidenceKind,
    ProviderEvidenceManifest,
    ProviderFixtureEvidence,
    ProviderFixtureOutcome,
    ProviderPackage,
    validate_provider_package,
)


def default_jiuse_fixture_root() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "jiuse"


def build_jiuse_fixture_package(
    fixture_root: Path | None = None,
    *,
    validate: bool = True,
) -> ProviderPackage:
    root = fixture_root or default_jiuse_fixture_root()
    adapter = JiuseFixtureVideoMetadataAdapter(root)
    seed = b"jiuse_vod_fixture_v1"
    search_sha = hashlib.sha256(seed + b":search").hexdigest()
    detail_sha = hashlib.sha256(seed + b":detail").hexdigest()
    digests = (
        ("jiuse_search_manifest", search_sha),
        ("jiuse_detail_manifest", detail_sha),
    )
    evidence = ProviderEvidenceManifest(
        provider_key=JIUSE_PROVIDER_KEY,
        scope=ProviderApprovalScope.TEST_FIXTURE,
        display_name=JIUSE_CAPABILITIES.display_name,
        content_scope=JIUSE_CAPABILITIES.content_scope,
        approval_id=JIUSE_APPROVAL.approval_id,
        review_revision="jiuse_fixture_v1",
        reviewed_at=datetime(2026, 7, 22, tzinfo=UTC),
        reviewed_operations=JIUSE_CAPABILITIES.operations,
        fixture_evidence=(
            ProviderFixtureEvidence(
                ProviderOperation.SEARCH,
                "jiuse_search_manifest",
                search_sha,
                ProviderEvidenceKind.SUCCESS,
                ProviderFixtureOutcome.SUCCESS,
            ),
            ProviderFixtureEvidence(
                ProviderOperation.DETAIL,
                "jiuse_detail_manifest",
                detail_sha,
                ProviderEvidenceKind.SUCCESS,
                ProviderFixtureOutcome.SUCCESS,
            ),
        ),
        license_conclusion="fixture_only_pending_endpoint_freeze",
        terms_conclusion="fixture_only",
        lawful_access_conclusion="fixture_only_no_vip_bypass",
        notes="nsfwpro_factory_jiuse_vod",
    )
    package = ProviderPackage(
        scope=ProviderApprovalScope.TEST_FIXTURE,
        approval=JIUSE_APPROVAL,
        capabilities=JIUSE_CAPABILITIES,
        endpoint=JIUSE_ENDPOINT,
        binding=ProviderAdapterBinding(
            provider_key=JIUSE_PROVIDER_KEY,
            display_name=JIUSE_CAPABILITIES.display_name,
            content_scope=JIUSE_CAPABILITIES.content_scope,
            operations=JIUSE_CAPABILITIES.operations,
            adapter=adapter,
            adapter_kind=ProviderAdapterKind.VIDEO_METADATA,
        ),
        evidence=evidence,
        fixture_digests=digests,
    )
    if validate:
        validate_provider_package(package)
    return package
