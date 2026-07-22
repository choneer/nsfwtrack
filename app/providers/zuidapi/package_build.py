"""Build PRODUCTION ZuidAPI MacCMS package (nsfwpro factory key zuidapi-vod)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.providers.zuidapi.adapter import JsonFetcher, ZuidapiLiveVideoMetadataAdapter
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


_SEARCH_FIXTURE_SHA256 = "c79de7b4dd10f9032cbc93214eab2c1649c613401d9aeecaa6b010872555b032"
_DETAIL_FIXTURE_SHA256 = "5c6ec84c13d1aae5123a715801a3e2c427365e278d86eb972c6b23e6e0a7b93a"


def build_zuidapi_production_package(
    *,
    fetcher: JsonFetcher | None = None,
    validate: bool = True,
) -> ProviderPackage:
    search_sha = _SEARCH_FIXTURE_SHA256
    detail_sha = _DETAIL_FIXTURE_SHA256
    if fetcher is None:
        raise ValueError("controlled ZuidAPI fetcher is not configured")
    adapter = ZuidapiLiveVideoMetadataAdapter(fetcher)
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
