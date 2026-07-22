"""Build PRODUCTION CopyManga package + acquisition download package."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from app.acquisition.contracts import AcquisitionPackage, AssetDownloadDescriptor
from app.providers.copymanga.adapter import (
    CopymangaVideoMetadataAdapter,
    StaticJsonFetcher,
)
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


def default_copymanga_fixture_root() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "copymanga"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_copymanga_production_package(
    *,
    fetcher: object | None = None,
    fixture_root: Path | None = None,
    validate: bool = True,
) -> ProviderPackage:
    root = fixture_root or default_copymanga_fixture_root()
    search_body = (root / "search.json").read_bytes()
    detail_body = (root / "detail.json").read_bytes()
    chapters_body = (root / "chapters.json").read_bytes()
    if fetcher is None:
        fetcher = StaticJsonFetcher(
            {
                "/api/v3/search/comic": json.loads(search_body),
                "/api/v3/comic2/demo-comic": json.loads(detail_body),
                "/api/v3/comic/demo-comic/group/default/chapters": json.loads(
                    chapters_body
                ),
            }
        )
    adapter = CopymangaVideoMetadataAdapter(fetcher)  # type: ignore[arg-type]
    digests = (
        ("copymanga_search", _sha256_bytes(search_body)),
        ("copymanga_detail", _sha256_bytes(detail_body)),
        ("copymanga_chapters", _sha256_bytes(chapters_body)),
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
