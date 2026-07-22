"""Build comic TEST_FIXTURE package + acquisition download package."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from app.acquisition.contracts import AcquisitionPackage
from app.providers.comic.adapter import ComicFixtureVideoMetadataAdapter
from app.providers.comic.acquisition_adapter import ComicFixtureAcquisitionAdapter
from app.providers.comic.approval import (
    COMIC_APPROVAL,
    COMIC_CAPABILITIES,
    COMIC_ENDPOINT,
    COMIC_PROVIDER_KEY,
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


def default_comic_fixture_root() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "comic_local"


def build_comic_fixture_package(
    fixture_root: Path | None = None,
    *,
    validate: bool = True,
) -> ProviderPackage:
    root = fixture_root or default_comic_fixture_root()
    adapter = ComicFixtureVideoMetadataAdapter(root)
    # Evidence digests: empty dirs still need opaque fixture ids; use package module hash
    seed = b"comic_local_fixture_v1"
    search_sha = hashlib.sha256(seed + b":search").hexdigest()
    detail_sha = hashlib.sha256(seed + b":detail").hexdigest()
    asset_sha = hashlib.sha256(seed + b":asset").hexdigest()
    digests = (
        ("comic_search_manifest", search_sha),
        ("comic_detail_manifest", detail_sha),
        ("comic_asset_manifest", asset_sha),
    )
    evidence = ProviderEvidenceManifest(
        provider_key=COMIC_PROVIDER_KEY,
        scope=ProviderApprovalScope.TEST_FIXTURE,
        display_name=COMIC_CAPABILITIES.display_name,
        content_scope=COMIC_CAPABILITIES.content_scope,
        approval_id=COMIC_APPROVAL.approval_id,
        review_revision="comic_fixture_v1",
        reviewed_at=datetime(2026, 7, 22, tzinfo=UTC),
        reviewed_operations=COMIC_CAPABILITIES.operations,
        fixture_evidence=(
            ProviderFixtureEvidence(
                ProviderOperation.SEARCH,
                "comic_search_manifest",
                search_sha,
                ProviderEvidenceKind.SUCCESS,
                ProviderFixtureOutcome.SUCCESS,
            ),
            ProviderFixtureEvidence(
                ProviderOperation.DETAIL,
                "comic_detail_manifest",
                detail_sha,
                ProviderEvidenceKind.SUCCESS,
                ProviderFixtureOutcome.SUCCESS,
            ),
            ProviderFixtureEvidence(
                ProviderOperation.ASSET_LIST,
                "comic_asset_manifest",
                asset_sha,
                ProviderEvidenceKind.SUCCESS,
                ProviderFixtureOutcome.SUCCESS,
            ),
        ),
        license_conclusion="fixture_only",
        terms_conclusion="fixture_only",
        lawful_access_conclusion="fixture_only",
        notes="phase_d_comic_local_download",
    )
    package = ProviderPackage(
        scope=ProviderApprovalScope.TEST_FIXTURE,
        approval=COMIC_APPROVAL,
        capabilities=COMIC_CAPABILITIES,
        endpoint=COMIC_ENDPOINT,
        binding=ProviderAdapterBinding(
            provider_key=COMIC_PROVIDER_KEY,
            display_name=COMIC_CAPABILITIES.display_name,
            content_scope=COMIC_CAPABILITIES.content_scope,
            operations=COMIC_CAPABILITIES.operations,
            adapter=adapter,
            adapter_kind=ProviderAdapterKind.VIDEO_METADATA,
        ),
        evidence=evidence,
        fixture_digests=digests,
    )
    if validate:
        validate_provider_package(package)
    return package


def build_comic_acquisition_package(
    fixture_root: Path | None = None,
) -> AcquisitionPackage:
    root = fixture_root or default_comic_fixture_root()
    return AcquisitionPackage(
        provider_key=COMIC_PROVIDER_KEY,
        adapter=ComicFixtureAcquisitionAdapter(root),
        approved_asset_list=True,
        approved_download=True,
    )
