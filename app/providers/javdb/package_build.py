"""Build a reviewed JavDB package around an explicitly injected fetcher."""

from __future__ import annotations

import os
from datetime import UTC, datetime

from app.acquisition.contracts import AcquisitionPackage
from app.providers.javdb.acquisition_adapter import JavDBAcquisitionAdapter
from app.providers.javdb.fetch import HtmlFetcher
from app.providers.javdb.live_adapter import JavDBLiveVideoMetadataAdapter
from app.providers.javdb.production import (
    JAVDB_PRODUCTION_APPROVAL,
    JAVDB_PRODUCTION_CAPABILITIES,
    JAVDB_PRODUCTION_ENDPOINT,
    JAVDB_PRODUCTION_PROVIDER_KEY,
)
from app.providers.javdb.session import SessionCookieError, load_javdb_session_cookie
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


_SEARCH_FIXTURE_SHA256 = "25457903e74769900073077e21dc314ba4e725c79d59c97fc60d1a23a74708fb"
_DETAIL_FIXTURE_SHA256 = "9a4f8362aae6e06893ebe203b75694a3c0b2fa490a7777c6e497e6087ae22c77"


def _evidence_and_digests() -> tuple[
    ProviderEvidenceManifest,
    tuple[tuple[str, str], ...],
]:
    search_id = "search_normal_html"
    detail_id = "detail_normal_html"
    asset_id = "detail_asset_list_html"
    search_sha = _SEARCH_FIXTURE_SHA256
    detail_sha = _DETAIL_FIXTURE_SHA256
    # ASSET_LIST reuses detail HTML evidence
    digests = (
        (search_id, search_sha),
        (detail_id, detail_sha),
        (asset_id, detail_sha),
    )
    evidence = ProviderEvidenceManifest(
        provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
        scope=ProviderApprovalScope.PRODUCTION,
        display_name=JAVDB_PRODUCTION_CAPABILITIES.display_name,
        content_scope=JAVDB_PRODUCTION_CAPABILITIES.content_scope,
        approval_id=JAVDB_PRODUCTION_APPROVAL.approval_id,
        review_revision="javdb_production_v2",
        reviewed_at=datetime(2026, 7, 22, tzinfo=UTC),
        reviewed_operations=JAVDB_PRODUCTION_CAPABILITIES.operations,
        fixture_evidence=(
            ProviderFixtureEvidence(
                operation=ProviderOperation.SEARCH,
                fixture_id=search_id,
                fixture_sha256=search_sha,
                fixture_kind=ProviderEvidenceKind.SUCCESS,
                expected_outcome=ProviderFixtureOutcome.SUCCESS,
            ),
            ProviderFixtureEvidence(
                operation=ProviderOperation.DETAIL,
                fixture_id=detail_id,
                fixture_sha256=detail_sha,
                fixture_kind=ProviderEvidenceKind.SUCCESS,
                expected_outcome=ProviderFixtureOutcome.SUCCESS,
            ),
            ProviderFixtureEvidence(
                operation=ProviderOperation.ASSET_LIST,
                fixture_id=asset_id,
                fixture_sha256=detail_sha,
                fixture_kind=ProviderEvidenceKind.SUCCESS,
                expected_outcome=ProviderFixtureOutcome.SUCCESS,
            ),
        ),
        license_conclusion="operator_lawful_session_only",
        terms_conclusion="operator_terms_compliance_required",
        lawful_access_conclusion="operator_session_cookie_no_vip_bypass",
        notes="phase_b_c_javdb_metadata_and_link_assets",
    )
    return evidence, digests


def build_javdb_production_package(
    *,
    fetcher: HtmlFetcher | None = None,
    validate: bool = True,
) -> ProviderPackage:
    """Build an offline-validated package around an explicit controlled fetcher.

    A production network fetcher is deliberately not created here.  Activation
    must inject a fetcher implemented by the shared outbound boundary; missing
    configuration fails closed instead of substituting fixture responses.
    """

    if fetcher is None:
        raise SessionCookieError("controlled JavDB fetcher is not configured")

    adapter = JavDBLiveVideoMetadataAdapter(fetcher)
    evidence, digests = _evidence_and_digests()
    binding = ProviderAdapterBinding(
        provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
        display_name=JAVDB_PRODUCTION_CAPABILITIES.display_name,
        content_scope=JAVDB_PRODUCTION_CAPABILITIES.content_scope,
        operations=JAVDB_PRODUCTION_CAPABILITIES.operations,
        adapter=adapter,
        adapter_kind=ProviderAdapterKind.VIDEO_METADATA,
    )
    package = ProviderPackage(
        scope=ProviderApprovalScope.PRODUCTION,
        approval=JAVDB_PRODUCTION_APPROVAL,
        capabilities=JAVDB_PRODUCTION_CAPABILITIES,
        endpoint=JAVDB_PRODUCTION_ENDPOINT,
        binding=binding,
        evidence=evidence,
        fixture_digests=digests,
    )
    if validate:
        validate_provider_package(package)
    return package


def build_javdb_acquisition_package(
    *,
    cookie: str | None = None,
    proxy_url: str | None = None,
    static_bodies: dict[str, bytes] | None = None,
    static_lists: dict | None = None,
) -> AcquisitionPackage:
    """Optional local download package (approved_download=True when built)."""

    if static_bodies is not None:
        session = cookie or "test=1"
    else:
        session = load_javdb_session_cookie(explicit=cookie)
    env_proxy = (
        proxy_url
        or os.environ.get("NSFWTRACK_HTTP_PROXY")
        or os.environ.get("NSFW_HTTP_PROXY")
        or None
    )
    adapter = JavDBAcquisitionAdapter(
        cookie=session,
        proxy_url=env_proxy,
        static_bodies=static_bodies,
        static_lists=static_lists,
    )
    return AcquisitionPackage(
        provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
        adapter=adapter,
        approved_asset_list=True,
        approved_download=True,
    )
