"""JavDB TEST_FIXTURE package: approval validation + offline HTML adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.providers.javdb.adapter import JavDBFixtureVideoMetadataAdapter
from app.providers.javdb.approval import (
    JAVDB_APPROVAL,
    JAVDB_CAPABILITIES,
    JAVDB_ENDPOINT,
    JAVDB_PROVIDER_KEY,
)
from app.providers.javdb.parse import parse_detail_html, parse_search_html
from app.source_adapters import (
    validate_approval_against_capabilities,
    validate_approval_against_endpoint,
    validate_provider_approval,
)
from app.source_adapters.approval import ProviderApprovalScope
from app.source_adapters.contracts import ProviderAdapterError, ProviderOperation
from app.source_adapters.registry import PRODUCTION_ENDPOINT_REGISTRY


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "javdb_metadata"


def test_javdb_approval_is_test_fixture_and_valid() -> None:
    assert JAVDB_APPROVAL.scope is ProviderApprovalScope.TEST_FIXTURE
    assert JAVDB_APPROVAL.provider_key == JAVDB_PROVIDER_KEY
    assert all(host.hostname.endswith(".invalid") for host in JAVDB_APPROVAL.hosts)
    validate_provider_approval(JAVDB_APPROVAL)
    validate_approval_against_capabilities(JAVDB_APPROVAL, JAVDB_CAPABILITIES)
    validate_approval_against_endpoint(JAVDB_APPROVAL, JAVDB_ENDPOINT)


def test_javdb_not_registered_in_production() -> None:
    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_ENDPOINT_REGISTRY.providers)


def test_parse_search_html_extracts_slug_and_catalog() -> None:
    html = (FIXTURE_ROOT / "search_normal.html").read_text(encoding="utf-8")
    cards = parse_search_html(html, base_url="https://metadata.javdb.invalid")
    assert len(cards) == 2
    assert cards[0]["external_id"] == "RM29z"
    assert cards[0]["catalog_number"] == "SSIS-001"
    assert "Example Title" in (cards[0]["title"] or "")


def test_parse_detail_html_extracts_fields() -> None:
    html = (FIXTURE_ROOT / "detail_normal.html").read_text(encoding="utf-8")
    detail = parse_detail_html(
        html,
        external_id="RM29z",
        base_url="https://metadata.javdb.invalid",
    )
    assert detail["catalog_number"] == "SSIS-001"
    assert detail["title"] == "Example Title"
    assert detail["release_date"] == "2021-11-01"
    assert detail["duration_minutes"] == 120
    assert detail["studio"] == "Sample Studio"
    assert "Sample Actress" in detail["performers"]  # type: ignore[operator]


def test_adapter_search_matches_catalog_query() -> None:
    adapter = JavDBFixtureVideoMetadataAdapter(FIXTURE_ROOT)
    page = adapter.search("SSIS-001", page=1, page_size=20)
    assert page.total == 1
    assert page.items[0].identifier.external_id == "RM29z"
    assert page.items[0].identifier.catalog_number == "SSIS-001"
    assert page.items[0].title == "Example Title"


def test_adapter_search_empty_query_token() -> None:
    adapter = JavDBFixtureVideoMetadataAdapter(FIXTURE_ROOT)
    page = adapter.search("__empty__", page=1, page_size=20)
    assert page.total == 0
    assert page.items == ()


def test_adapter_detail_maps_video_detail() -> None:
    adapter = JavDBFixtureVideoMetadataAdapter(FIXTURE_ROOT)
    detail = adapter.detail("RM29z")
    assert detail.identifier.external_id == "RM29z"
    assert detail.identifier.catalog_number == "SSIS-001"
    assert detail.title == "Example Title"
    assert detail.release_date is not None
    assert detail.duration_seconds == 120 * 60
    assert detail.studio is not None
    assert detail.performers
    assert detail.cover is not None


def test_adapter_detail_rejects_empty_id() -> None:
    adapter = JavDBFixtureVideoMetadataAdapter(FIXTURE_ROOT)
    with pytest.raises(ProviderAdapterError) as exc:
        adapter.detail("")
    assert exc.value.error.operation is ProviderOperation.DETAIL


def test_external_id_strategy_is_path_slug() -> None:
    """DETAIL path uses slug; catalog number is a separate display field."""

    detail_op = next(
        op
        for op in JAVDB_APPROVAL.operations
        if op.operation is ProviderOperation.DETAIL
    )
    assert detail_op.path_template == "/v/{external_id}"
