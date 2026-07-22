"""Build PRODUCTION ZuidAPI MacCMS package (nsfwpro factory key zuidapi-vod)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from app.providers.zuidapi.adapter import StaticJsonFetcher, ZuidapiLiveVideoMetadataAdapter
from app.providers.zuidapi.approval import (
    ZUIDAPI_APPROVAL,
    ZUIDAPI_CAPABILITIES,
    ZUIDAPI_ENDPOINT,
    ZUIDAPI_PROVIDER_KEY,
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


def default_zuidapi_fixture_root() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "zuidapi"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_zuidapi_production_package(
    *,
    fetcher: object | None = None,
    fixture_root: Path | None = None,
    validate: bool = True,
) -> ProviderPackage:
    root = fixture_root or default_zuidapi_fixture_root()
    search_body = (root / "search-normal.json").read_bytes()
    detail_body = (root / "detail-normal.json").read_bytes()
    search_sha = _sha256_bytes(search_body)
    detail_sha = _sha256_bytes(detail_body)
    if fetcher is None:
        fetcher = StaticJsonFetcher(
            {
                "/api.php/provide/vod": json.loads(search_body.decode("utf-8")),
                "/api.php/provide/vod?ac=list&limit=20&pg=1&wd=TEST": json.loads(
                    search_body.decode("utf-8")
                ),
                "/api.php/provide/vod?ac=detail&ids=TEST-001": json.loads(
                    detail_body.decode("utf-8")
                ),
            }
        )
    adapter = ZuidapiLiveVideoMetadataAdapter(fetcher)  # type: ignore[arg-type]
    digests = (
        ("zuidapi_search_normal", search_sha),
        ("zuidapi_detail_normal", detail_sha),
    )
    evidence = ProviderEvidenceManifest(
        provider_key=ZUIDAPI_PROVIDER_KEY,
        scope=ProviderApprovalScope.PRODUCTION,
        display_name=ZUIDAPI_CAPABILITIES.display_name,
        content_scope=ZUIDAPI_CAPABILITIES.content_scope,
        approval_id=ZUIDAPI_APPROVAL.approval_id,
        review_revision="zuidapi_production_v1",
        reviewed_at=datetime(2026, 7, 22, tzinfo=UTC),
        reviewed_operations=ZUIDAPI_CAPABILITIES.operations,
        fixture_evidence=(
            ProviderFixtureEvidence(
                ProviderOperation.SEARCH,
                "zuidapi_search_normal",
                search_sha,
                ProviderEvidenceKind.SUCCESS,
                ProviderFixtureOutcome.SUCCESS,
            ),
            ProviderFixtureEvidence(
                ProviderOperation.DETAIL,
                "zuidapi_detail_normal",
                detail_sha,
                ProviderEvidenceKind.SUCCESS,
                ProviderFixtureOutcome.SUCCESS,
            ),
        ),
        license_conclusion="operator_lawful_access_only",
        terms_conclusion="unauthenticated_collect_api_operator_terms",
        lawful_access_conclusion="no_vip_bypass_metadata_only",
        notes="nsfwpro_factory_zuidapi_vod",
    )
    package = ProviderPackage(
        scope=ProviderApprovalScope.PRODUCTION,
        approval=ZUIDAPI_APPROVAL,
        capabilities=ZUIDAPI_CAPABILITIES,
        endpoint=ZUIDAPI_ENDPOINT,
        binding=ProviderAdapterBinding(
            provider_key=ZUIDAPI_PROVIDER_KEY,
            display_name=ZUIDAPI_CAPABILITIES.display_name,
            content_scope=ZUIDAPI_CAPABILITIES.content_scope,
            operations=ZUIDAPI_CAPABILITIES.operations,
            adapter=adapter,
            adapter_kind=ProviderAdapterKind.VIDEO_METADATA,
        ),
        evidence=evidence,
        fixture_digests=digests,
    )
    if validate:
        validate_provider_package(package)
    return package
