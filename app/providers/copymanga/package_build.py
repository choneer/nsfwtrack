"""Build PRODUCTION CopyManga package + acquisition download package."""

from __future__ import annotations

from datetime import UTC, datetime

from app.acquisition.contracts import AcquisitionPackage, AssetDownloadDescriptor
from app.providers.copymanga.adapter import CopymangaVideoMetadataAdapter, JsonFetcher
from app.providers.copymanga.approval import (
    COPYMANGA_APPROVAL,
    COPYMANGA_CAPABILITIES,
    COPYMANGA_ENDPOINT,
    COPYMANGA_PROVIDER_KEY,
)
from app.providers.copymanga.acquisition_adapter import CopymangaAcquisitionAdapter
from app.source_adapters.approval import ProviderApprovalScope
from app.source_adapters.contracts import ProviderOperation, SourceAssetKind
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


_SEARCH_FIXTURE_SHA256 = "656a4887e7cf528846bd00daf7c2581ad4d4580411443b7af67028de724100f6"
_DETAIL_FIXTURE_SHA256 = "84472edb834eb84104e53cbed19ec0f2b168a126df2633268072fd17a0371dca"
_CHAPTERS_FIXTURE_SHA256 = "29a25b03df24942a70c2a1a7f0b52555c0e18aec5cfd7a95897cf06d236166b2"


def build_copymanga_production_package(
    *,
    fetcher: JsonFetcher | None = None,
    validate: bool = True,
) -> ProviderPackage:
    if fetcher is None:
        raise ValueError("controlled CopyManga fetcher is not configured")
    adapter = CopymangaVideoMetadataAdapter(fetcher)
    digests = (
        ("copymanga_search", _SEARCH_FIXTURE_SHA256),
        ("copymanga_detail", _DETAIL_FIXTURE_SHA256),
        ("copymanga_chapters", _CHAPTERS_FIXTURE_SHA256),
    )
    evidence = ProviderEvidenceManifest(
        provider_key=COPYMANGA_PROVIDER_KEY,
        scope=ProviderApprovalScope.PRODUCTION,
        display_name=COPYMANGA_CAPABILITIES.display_name,
        content_scope=COPYMANGA_CAPABILITIES.content_scope,
        approval_id=COPYMANGA_APPROVAL.approval_id,
        review_revision="copymanga_production_v1",
        reviewed_at=datetime(2026, 7, 22, tzinfo=UTC),
        reviewed_operations=COPYMANGA_CAPABILITIES.operations,
        fixture_evidence=(
            ProviderFixtureEvidence(
                ProviderOperation.SEARCH,
                "copymanga_search",
                digests[0][1],
                ProviderEvidenceKind.SUCCESS,
                ProviderFixtureOutcome.SUCCESS,
            ),
            ProviderFixtureEvidence(
                ProviderOperation.DETAIL,
                "copymanga_detail",
                digests[1][1],
                ProviderEvidenceKind.SUCCESS,
                ProviderFixtureOutcome.SUCCESS,
            ),
            ProviderFixtureEvidence(
                ProviderOperation.ASSET_LIST,
                "copymanga_chapters",
                digests[2][1],
                ProviderEvidenceKind.SUCCESS,
                ProviderFixtureOutcome.SUCCESS,
            ),
        ),
        license_conclusion="operator_lawful_access_only",
        terms_conclusion="fixed_hosts_venera_style",
        lawful_access_conclusion="no_vip_bypass_no_js_runtime",
        notes="real_site_comic_copymanga",
    )
    package = ProviderPackage(
        scope=ProviderApprovalScope.PRODUCTION,
        approval=COPYMANGA_APPROVAL,
        capabilities=COPYMANGA_CAPABILITIES,
        endpoint=COPYMANGA_ENDPOINT,
        binding=ProviderAdapterBinding(
            provider_key=COPYMANGA_PROVIDER_KEY,
            display_name=COPYMANGA_CAPABILITIES.display_name,
            content_scope=COPYMANGA_CAPABILITIES.content_scope,
            operations=COPYMANGA_CAPABILITIES.operations,
            adapter=adapter,
            adapter_kind=ProviderAdapterKind.VIDEO_METADATA,
        ),
        evidence=evidence,
        fixture_digests=digests,
    )
    if validate:
        validate_provider_package(package)
    return package


def build_copymanga_acquisition_package(
    *,
    static_pages: dict[str, bytes] | None = None,
    static_lists: dict[str, tuple[AssetDownloadDescriptor, ...]] | None = None,
) -> AcquisitionPackage:
    return AcquisitionPackage(
        provider_key=COPYMANGA_PROVIDER_KEY,
        adapter=CopymangaAcquisitionAdapter(
            static_bodies=static_pages,
            static_lists=static_lists,
        ),
        approved_asset_list=True,
        approved_download=True,
    )
