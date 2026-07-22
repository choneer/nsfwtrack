"""Build activatable JavDB PRODUCTION ProviderPackage (opt-in, not default catalog)."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

from app.acquisition.contracts import AcquisitionPackage
from app.providers.javdb.acquisition_adapter import JavDBAcquisitionAdapter
from app.providers.javdb.fetch import JavdbHtmlFetcher, StaticHtmlFetcher
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


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "javdb_metadata"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence_and_digests() -> tuple[
    ProviderEvidenceManifest,
    tuple[tuple[str, str], ...],
]:
    root = _fixture_root()
    search_id = "search_normal_html"
    detail_id = "detail_normal_html"
    asset_id = "detail_asset_list_html"
    search_sha = _sha256_file(root / "search_normal.html")
    detail_sha = _sha256_file(root / "detail_normal.html")
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
    fetcher: object | None = None,
    cookie: str | None = None,
    proxy_url: str | None = None,
    validate: bool = True,
) -> ProviderPackage:
    """Build a PRODUCTION package. Default catalogs remain empty (v1.3 freeze)."""

    if fetcher is None:
        try:
            session = load_javdb_session_cookie(explicit=cookie)
        except SessionCookieError:
            # Offline package build for validation: static empty pages
            root = _fixture_root()
            fetcher = StaticHtmlFetcher(
                {
                    "/search": (root / "search_normal.html").read_text(encoding="utf-8"),
                    "/v/RM29z": (root / "detail_RM29z.html").read_text(encoding="utf-8"),
                }
            )
        else:
            env_proxy = (
                proxy_url
                or os.environ.get("NSFWTRACK_HTTP_PROXY")
                or os.environ.get("NSFW_HTTP_PROXY")
                or None
            )
            fetcher = JavdbHtmlFetcher(cookie=session, proxy_url=env_proxy)

    adapter = JavDBLiveVideoMetadataAdapter(fetcher)  # type: ignore[arg-type]
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
