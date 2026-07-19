"""Synthetic Provider packages used only by N4D-C tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from app.source_adapters import (
    ProviderAdapterBinding,
    ProviderAdapterKind,
    ProviderEvidenceKind,
    ProviderEvidenceManifest,
    ProviderFixtureEvidence,
    ProviderFixtureOutcome,
    ProviderPackage,
)
from app.source_adapters.approval import ApprovedHost
from app.source_adapters.contracts import ProviderOperation
from tests.fixture_provider import (
    FIXTURE_ASSET_HOST,
    FIXTURE_CAPABILITIES,
    FIXTURE_ENDPOINT,
    FIXTURE_METADATA_HOST,
    FIXTURE_PROVIDER_KEY,
    FixtureReferenceProvider,
)
from tests.test_phase5_n4b import APPROVAL
from tests.video_metadata_fixture_provider import (
    FIXTURE_PROVIDER_KEY as VIDEO_FIXTURE_PROVIDER_KEY,
    FixtureVideoMetadataProvider,
)


REVIEWED_AT = datetime(2026, 7, 19, 0, 0, tzinfo=UTC)
SOURCE_APPROVAL_ID = "fixture_reference_v1"
VIDEO_APPROVAL_ID = "fixture_video_v1"
VIDEO_DISPLAY_NAME = "Fixture Video Metadata Provider"
VIDEO_CONTENT_SCOPE = "synthetic video metadata records only"

SOURCE_FIXTURE_DIGESTS = (
    ("source-search-success", "a6a8341e8495bfe6c54fb16a7a37f3a4bd41ac0f641c2ccbaed0710a243d57fb"),
    ("source-detail-success", "192a360e776dcde6c07d2e9582edc212994eef65fc8866e1bcb8c1ba18a9ec04"),
    ("source-assets-success", "0f53e441d21a0ed8652830bb421b50398d4b7d006b1e8e1e79db3104ac6dd1a6"),
)
VIDEO_FIXTURE_DIGESTS = (
    ("video-search-success", "d757f5ca7c27547fa83f6b0ee19870c4c30f3727d14cfee529cfc855f3920489"),
    ("video-search-empty", "a2c1045cd5fb59a7aadbdd98e120693aa2767dbbd9d925936058a826729314e8"),
    ("video-detail-complete", "89e19186f203b1e25488651382e95246c25a2aff49f6692487a838d1921ca6dd"),
    ("video-detail-partial", "b290b1d3703743427fe2046db9b1875900a057389bad2dd2aa95f8ac92de0031"),
    ("video-assets-success", "0b2bc18b3837ca338249349f0ae02a62c77e89fbc064c1e58bd89abb8e66dcac"),
    ("video-invalid-payload", "3d439a873353ffee8f1e3cee29b3eeca746b26d9dfa40e668525c5bda7dba515"),
)

_FIXTURE_PATHS = {
    "source-search-success": Path(__file__).parent / "fixtures" / "reference_provider" / "search.json",
    "source-detail-success": Path(__file__).parent / "fixtures" / "reference_provider" / "detail.json",
    "source-assets-success": Path(__file__).parent / "fixtures" / "reference_provider" / "assets.json",
    "video-search-success": Path(__file__).parent / "fixtures" / "video_metadata" / "search_success.json",
    "video-search-empty": Path(__file__).parent / "fixtures" / "video_metadata" / "search_empty.json",
    "video-detail-complete": Path(__file__).parent / "fixtures" / "video_metadata" / "detail_complete.json",
    "video-detail-partial": Path(__file__).parent / "fixtures" / "video_metadata" / "detail_partial.json",
    "video-assets-success": Path(__file__).parent / "fixtures" / "video_metadata" / "assets_success.json",
    "video-invalid-payload": Path(__file__).parent / "fixtures" / "video_metadata" / "invalid_payload.json",
}


def actual_fixture_digests(
    fixture_ids: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (fixture_id, sha256(_FIXTURE_PATHS[fixture_id].read_bytes()).hexdigest())
        for fixture_id in fixture_ids
    )


SOURCE_APPROVAL = replace(
    APPROVAL,
    approval_id=SOURCE_APPROVAL_ID,
    provider_key=FIXTURE_PROVIDER_KEY,
    display_name=FIXTURE_CAPABILITIES.display_name,
    content_scope=FIXTURE_CAPABILITIES.content_scope,
    hosts=(
        replace(APPROVAL.hosts[0], hostname=FIXTURE_METADATA_HOST),
        replace(APPROVAL.hosts[1], hostname=FIXTURE_ASSET_HOST),
    ),
)

SOURCE_EVIDENCE = ProviderEvidenceManifest(
    provider_key=FIXTURE_PROVIDER_KEY,
    scope=SOURCE_APPROVAL.scope,
    display_name=FIXTURE_CAPABILITIES.display_name,
    content_scope=FIXTURE_CAPABILITIES.content_scope,
    approval_id=SOURCE_APPROVAL_ID,
    review_revision="n4d-c-source-v1",
    reviewed_at=REVIEWED_AT,
    reviewed_operations=FIXTURE_CAPABILITIES.operations,
    fixture_evidence=(
        ProviderFixtureEvidence(
            ProviderOperation.SEARCH,
            SOURCE_FIXTURE_DIGESTS[0][0],
            SOURCE_FIXTURE_DIGESTS[0][1],
            ProviderEvidenceKind.SUCCESS,
            ProviderFixtureOutcome.SUCCESS,
        ),
        ProviderFixtureEvidence(
            ProviderOperation.DETAIL,
            SOURCE_FIXTURE_DIGESTS[1][0],
            SOURCE_FIXTURE_DIGESTS[1][1],
            ProviderEvidenceKind.SUCCESS,
            ProviderFixtureOutcome.SUCCESS,
        ),
        ProviderFixtureEvidence(
            ProviderOperation.ASSET_LIST,
            SOURCE_FIXTURE_DIGESTS[2][0],
            SOURCE_FIXTURE_DIGESTS[2][1],
            ProviderEvidenceKind.SUCCESS,
            ProviderFixtureOutcome.SUCCESS,
        ),
    ),
    license_conclusion="test fixture only",
    terms_conclusion="not a production provider",
    lawful_access_conclusion="not approved for production",
    notes="synthetic package evidence only",
)

SOURCE_BINDING = ProviderAdapterBinding(
    provider_key=FIXTURE_PROVIDER_KEY,
    display_name=FIXTURE_CAPABILITIES.display_name,
    content_scope=FIXTURE_CAPABILITIES.content_scope,
    operations=FIXTURE_CAPABILITIES.operations,
    adapter=FixtureReferenceProvider(object()),  # type: ignore[arg-type]
    adapter_kind=ProviderAdapterKind.SOURCE_METADATA,
)

SOURCE_PACKAGE = ProviderPackage(
    scope=SOURCE_APPROVAL.scope,
    approval=SOURCE_APPROVAL,
    capabilities=FIXTURE_CAPABILITIES,
    endpoint=FIXTURE_ENDPOINT,
    binding=SOURCE_BINDING,
    evidence=SOURCE_EVIDENCE,
    fixture_digests=SOURCE_FIXTURE_DIGESTS,
)

VIDEO_CAPABILITIES = replace(
    FIXTURE_CAPABILITIES,
    provider_key=VIDEO_FIXTURE_PROVIDER_KEY,
    display_name=VIDEO_DISPLAY_NAME,
    content_scope=VIDEO_CONTENT_SCOPE,
)
VIDEO_ENDPOINT = replace(
    FIXTURE_ENDPOINT,
    provider_key=VIDEO_FIXTURE_PROVIDER_KEY,
    capabilities=VIDEO_CAPABILITIES,
)
VIDEO_APPROVAL = replace(
    SOURCE_APPROVAL,
    approval_id=VIDEO_APPROVAL_ID,
    provider_key=VIDEO_FIXTURE_PROVIDER_KEY,
    display_name=VIDEO_DISPLAY_NAME,
    content_scope=VIDEO_CONTENT_SCOPE,
)
VIDEO_EVIDENCE = ProviderEvidenceManifest(
    provider_key=VIDEO_FIXTURE_PROVIDER_KEY,
    scope=VIDEO_APPROVAL.scope,
    display_name=VIDEO_DISPLAY_NAME,
    content_scope=VIDEO_CONTENT_SCOPE,
    approval_id=VIDEO_APPROVAL_ID,
    review_revision="n4d-c-video-v1",
    reviewed_at=REVIEWED_AT,
    reviewed_operations=VIDEO_CAPABILITIES.operations,
    fixture_evidence=(
        ProviderFixtureEvidence(
            ProviderOperation.SEARCH,
            VIDEO_FIXTURE_DIGESTS[0][0],
            VIDEO_FIXTURE_DIGESTS[0][1],
            ProviderEvidenceKind.SUCCESS,
            ProviderFixtureOutcome.SUCCESS,
        ),
        ProviderFixtureEvidence(
            ProviderOperation.SEARCH,
            VIDEO_FIXTURE_DIGESTS[1][0],
            VIDEO_FIXTURE_DIGESTS[1][1],
            ProviderEvidenceKind.EMPTY,
            ProviderFixtureOutcome.EMPTY,
        ),
        ProviderFixtureEvidence(
            ProviderOperation.DETAIL,
            VIDEO_FIXTURE_DIGESTS[2][0],
            VIDEO_FIXTURE_DIGESTS[2][1],
            ProviderEvidenceKind.SUCCESS,
            ProviderFixtureOutcome.SUCCESS,
        ),
        ProviderFixtureEvidence(
            ProviderOperation.DETAIL,
            VIDEO_FIXTURE_DIGESTS[3][0],
            VIDEO_FIXTURE_DIGESTS[3][1],
            ProviderEvidenceKind.PARTIAL,
            ProviderFixtureOutcome.PARTIAL,
        ),
        ProviderFixtureEvidence(
            ProviderOperation.ASSET_LIST,
            VIDEO_FIXTURE_DIGESTS[4][0],
            VIDEO_FIXTURE_DIGESTS[4][1],
            ProviderEvidenceKind.SUCCESS,
            ProviderFixtureOutcome.SUCCESS,
        ),
        ProviderFixtureEvidence(
            ProviderOperation.DETAIL,
            VIDEO_FIXTURE_DIGESTS[5][0],
            VIDEO_FIXTURE_DIGESTS[5][1],
            ProviderEvidenceKind.INVALID_TYPE,
            ProviderFixtureOutcome.INVALID_PROVIDER_PAYLOAD,
        ),
    ),
    license_conclusion="test fixture only",
    terms_conclusion="not a production provider",
    lawful_access_conclusion="not approved for production",
    notes="synthetic video fixture package only",
)
VIDEO_BINDING = ProviderAdapterBinding(
    provider_key=VIDEO_FIXTURE_PROVIDER_KEY,
    display_name=VIDEO_DISPLAY_NAME,
    content_scope=VIDEO_CONTENT_SCOPE,
    operations=VIDEO_CAPABILITIES.operations,
    adapter=FixtureVideoMetadataProvider(),
    adapter_kind=ProviderAdapterKind.VIDEO_METADATA,
)
VIDEO_PACKAGE = ProviderPackage(
    scope=VIDEO_APPROVAL.scope,
    approval=VIDEO_APPROVAL,
    capabilities=VIDEO_CAPABILITIES,
    endpoint=VIDEO_ENDPOINT,
    binding=VIDEO_BINDING,
    evidence=VIDEO_EVIDENCE,
    fixture_digests=VIDEO_FIXTURE_DIGESTS,
)


__all__ = [
    "SOURCE_PACKAGE",
    "SOURCE_FIXTURE_DIGESTS",
    "VIDEO_PACKAGE",
    "VIDEO_FIXTURE_DIGESTS",
    "actual_fixture_digests",
]
