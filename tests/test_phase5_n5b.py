from __future__ import annotations

import asyncio
import importlib
import socket
from collections.abc import Callable, Generator
from dataclasses import replace
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast

import httpx2
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.routers.source_search import (
    get_provider_search_service,
    source_search_detail_page,
    source_search_results_page,
)
from app.security_headers import SECURITY_HEADERS
from app.services.exporter import BACKUP_SCHEMA_V2
from app.services.outbound_http import OutboundHttpClient
from app.services.schema_version import CURRENT_SCHEMA_VERSION
from app.source_adapters import (
    PRODUCTION_ENDPOINT_REGISTRY,
    ProviderErrorCode,
    ProviderOperation,
)
from app.source_search import (
    PRODUCTION_SEARCH_PACKAGES,
    ProviderSearchService,
    ProviderSearchServiceError,
    ProviderSearchServiceErrorCode,
    SearchProviderDescriptor,
    VideoDetailEnvelope,
    VideoDetailRequest,
    VideoSearchEnvelope,
    VideoSearchRequest,
    build_production_search_service,
)
from app.video_metadata.contracts import (
    VideoAsset,
    VideoAssetKind,
    VideoDetail,
    VideoIdentifier,
    VideoOrganization,
    VideoOrganizationType,
    VideoPerson,
    VideoPersonRole,
    VideoRating,
    VideoSearchPage,
    VideoSearchResult,
    VideoSeries,
    VideoTag,
)
from tests.provider_package_fixture import VIDEO_PACKAGE


NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
PROVIDER_KEY = VIDEO_PACKAGE.provider_key
CANONICAL_MARKER = "https://metadata.invalid/canonical-marker"


def _identifier(external_id: str = "video-001") -> VideoIdentifier:
    return VideoIdentifier(
        provider_key=PROVIDER_KEY,
        external_id=external_id,
        catalog_number="CAT-001",
        canonical_url=CANONICAL_MARKER,
    )


def _performer() -> VideoPerson:
    return VideoPerson(
        PROVIDER_KEY,
        "person-001",
        "Synthetic Performer",
        VideoPersonRole.PERFORMER,
        ("Performer Alias",),
    )


def _director() -> VideoPerson:
    return VideoPerson(
        PROVIDER_KEY,
        "person-002",
        "Synthetic Director",
        VideoPersonRole.DIRECTOR,
    )


def _studio() -> VideoOrganization:
    return VideoOrganization(
        PROVIDER_KEY,
        "studio-001",
        "Synthetic Studio",
        VideoOrganizationType.STUDIO,
    )


def _publisher() -> VideoOrganization:
    return VideoOrganization(
        PROVIDER_KEY,
        "publisher-001",
        "Synthetic Publisher",
        VideoOrganizationType.PUBLISHER,
    )


def _tag() -> VideoTag:
    return VideoTag(PROVIDER_KEY, "tag-001", "Synthetic Tag", "synthetic-tag")


def _asset(
    asset_id: str,
    kind: VideoAssetKind,
    display_name: str,
    *,
    mime_type: str,
    width: int | None = None,
    height: int | None = None,
    duration_seconds: int | None = None,
) -> VideoAsset:
    return VideoAsset(
        provider_key=PROVIDER_KEY,
        asset_id=asset_id,
        kind=kind,
        display_name=display_name,
        mime_type=mime_type,
        width=width,
        height=height,
        duration_seconds=duration_seconds,
    )


def _search_result(title: str = "Synthetic Search Result") -> VideoSearchResult:
    return VideoSearchResult(
        identifier=_identifier(),
        title=title,
        alternate_titles=("Synthetic Alias",),
        release_date=date(2026, 7, 1),
        performers=(_performer(),),
        studio=_studio(),
        tags=(_tag(),),
        cover=_asset(
            "cover-secret-marker",
            VideoAssetKind.COVER,
            "Synthetic Search Cover",
            mime_type="image/jpeg",
            width=640,
            height=480,
        ),
        summary="Synthetic search summary",
    )


def _detail(external_id: str = "video-001") -> VideoDetail:
    return VideoDetail(
        identifier=_identifier(external_id),
        title="Synthetic Detail",
        alternate_titles=("Detail Alias",),
        summary="Synthetic detail summary",
        release_date=date(2026, 7, 2),
        duration_seconds=360,
        performers=(_performer(),),
        director=_director(),
        studio=_studio(),
        publisher=_publisher(),
        series=VideoSeries(PROVIDER_KEY, "series-001", "Synthetic Series"),
        tags=(_tag(),),
        rating=VideoRating(4.5, 0, 5, 42),
        cover=_asset(
            "detail-cover-secret-marker",
            VideoAssetKind.COVER,
            "Detail Cover Fact",
            mime_type="image/jpeg",
            width=1280,
            height=720,
        ),
        preview_images=(
            _asset(
                "preview-image-secret-marker",
                VideoAssetKind.PREVIEW_IMAGE,
                "Preview Image Fact",
                mime_type="image/webp",
                width=800,
                height=450,
            ),
        ),
        preview_video=_asset(
            "preview-video-secret-marker",
            VideoAssetKind.PREVIEW_VIDEO,
            "Preview Video Fact",
            mime_type="video/mp4",
            duration_seconds=30,
        ),
        source_updated_at=NOW,
    )


class CountingAdapter:
    key = PROVIDER_KEY

    def __init__(self) -> None:
        self.calls = {"search": 0, "detail": 0, "asset_list": 0}
        self.items: tuple[VideoSearchResult, ...] = (_search_result(),)
        self.has_next = False
        self.total: int | None = 1
        self.detail_result = _detail()
        self.search_error: BaseException | None = None
        self.detail_error: BaseException | None = None

    async def search(self, query: str, *, page: int, page_size: int) -> VideoSearchPage:
        self.calls["search"] += 1
        if self.search_error is not None:
            raise self.search_error
        return VideoSearchPage(
            items=self.items,
            page=page,
            page_size=page_size,
            has_next=self.has_next,
            total=self.total,
            query=query,
        )

    async def detail(self, external_id: str) -> VideoDetail:
        self.calls["detail"] += 1
        if self.detail_error is not None:
            raise self.detail_error
        if external_id == self.detail_result.external_id:
            return self.detail_result
        return _detail(external_id)

    async def asset_list(self, external_id: str) -> tuple[VideoAsset, ...]:
        self.calls["asset_list"] += 1
        return ()


def _service(adapter: CountingAdapter | None = None) -> tuple[ProviderSearchService, CountingAdapter]:
    adapter = adapter or CountingAdapter()
    package = replace(
        VIDEO_PACKAGE,
        binding=replace(VIDEO_PACKAGE.binding, adapter=adapter),
    )
    return ProviderSearchService((package,), clock=lambda: NOW), adapter


class ServiceProbe:
    def __init__(
        self,
        delegate: ProviderSearchService | None = None,
        *,
        providers: tuple[SearchProviderDescriptor, ...] | None = None,
        search_outcome: object | BaseException | None = None,
        detail_outcome: object | BaseException | None = None,
    ) -> None:
        self.delegate = delegate
        self.providers = providers if providers is not None else ()
        self.search_outcome = search_outcome
        self.detail_outcome = detail_outcome
        self.calls = {"list_providers": 0, "search": 0, "detail": 0, "asset_list": 0}

    def list_providers(self) -> tuple[SearchProviderDescriptor, ...]:
        self.calls["list_providers"] += 1
        if self.delegate is not None:
            return self.delegate.list_providers()
        return self.providers

    async def search(self, request: VideoSearchRequest) -> VideoSearchEnvelope:
        self.calls["search"] += 1
        if isinstance(self.search_outcome, BaseException):
            raise self.search_outcome
        if self.search_outcome is not None:
            return cast(VideoSearchEnvelope, self.search_outcome)
        if self.delegate is None:
            raise AssertionError("search must not be called")
        return await self.delegate.search(request)

    async def detail(self, request: VideoDetailRequest) -> VideoDetailEnvelope:
        self.calls["detail"] += 1
        if isinstance(self.detail_outcome, BaseException):
            raise self.detail_outcome
        if self.detail_outcome is not None:
            return cast(VideoDetailEnvelope, self.detail_outcome)
        if self.delegate is None:
            raise AssertionError("detail must not be called")
        return await self.delegate.detail(request)

    async def asset_list(self, request: object) -> object:
        self.calls["asset_list"] += 1
        raise AssertionError("asset_list must not be called")


def _descriptor(
    *,
    provider_key: str = PROVIDER_KEY,
    display_name: str = "Synthetic Video",
    content_scope: str = "Synthetic records",
    operations: tuple[ProviderOperation, ...] = (
        ProviderOperation.SEARCH,
        ProviderOperation.DETAIL,
    ),
) -> SearchProviderDescriptor:
    return SearchProviderDescriptor(
        provider_key,
        display_name,
        content_scope,
        operations,
    )


@pytest.fixture
def override_service(
    auth_client: TestClient,
) -> Generator[Callable[[object], TestClient], None, None]:
    previous = auth_client.app.dependency_overrides.get(get_provider_search_service)

    def apply(service: object) -> TestClient:
        auth_client.app.dependency_overrides[get_provider_search_service] = lambda: service
        return auth_client

    yield apply
    if previous is None:
        auth_client.app.dependency_overrides.pop(get_provider_search_service, None)
    else:
        auth_client.app.dependency_overrides[get_provider_search_service] = previous


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, object]] = []
        self._current: dict[str, object] | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        if tag == "form":
            self._current = {
                "action": values.get("action"),
                "method": values.get("method"),
                "fields": [],
                "hidden": [],
            }
            self.forms.append(self._current)
        elif self._current is not None and tag in {"input", "select", "textarea"}:
            name = values.get("name")
            if name:
                cast(list[str], self._current["fields"]).append(name)
                if tag == "input" and values.get("type") == "hidden":
                    cast(list[str], self._current["hidden"]).append(name)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._current = None


def _forms(html: str, action: str) -> list[dict[str, object]]:
    parser = FormParser()
    parser.feed(html)
    return [form for form in parser.forms if form["action"] == action]


def _assert_security_headers(response: object) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value


def _forbidden(*args: object, **kwargs: object) -> None:
    raise AssertionError("forbidden side effect")


def test_source_search_routes_require_page_auth(client: TestClient) -> None:
    get_response = client.get("/source-search", follow_redirects=False)
    search_response = client.post(
        "/source-search/search",
        data={"provider_key": "x", "query": "x", "page": "1", "page_size": "10"},
        follow_redirects=False,
    )
    detail_response = client.post(
        "/source-search/detail",
        data={"provider_key": "x", "external_id": "x"},
        follow_redirects=False,
    )

    for response in (get_response, search_response, detail_response):
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_production_page_is_safe_empty_state(auth_client: TestClient) -> None:
    response = auth_client.get("/source-search")

    assert response.status_code == 200
    assert "暂无可用外部来源" in response.text
    assert "这不是系统错误" in response.text
    assert PROVIDER_KEY not in response.text
    assert "Synthetic" not in response.text
    assert 'action="/source-search/search"' not in response.text
    _assert_security_headers(response)


def test_get_only_lists_providers_and_runs_no_operation(
    override_service: Callable[[object], TestClient],
) -> None:
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)

    response = client.get("/source-search")

    assert response.status_code == 200
    assert probe.calls == {
        "list_providers": 1,
        "search": 0,
        "detail": 0,
        "asset_list": 0,
    }
    assert adapter.calls == {"search": 0, "detail": 0, "asset_list": 0}


def test_get_empty_state_has_no_network_database_file_or_dynamic_import_side_effect(
    override_service: Callable[[object], TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = ServiceProbe(providers=())
    client = override_service(probe)
    monkeypatch.setattr(socket, "getaddrinfo", _forbidden)
    monkeypatch.setattr(socket, "gethostbyname", _forbidden)
    monkeypatch.setattr(httpx2, "AsyncClient", _forbidden)
    monkeypatch.setattr(OutboundHttpClient, "__init__", _forbidden)
    monkeypatch.setattr(Session, "execute", _forbidden)
    monkeypatch.setattr(Session, "commit", _forbidden)
    monkeypatch.setattr(Path, "read_bytes", _forbidden)
    monkeypatch.setattr(Path, "write_bytes", _forbidden)
    monkeypatch.setattr(importlib, "import_module", _forbidden)

    response = client.get("/source-search")

    assert response.status_code == 200
    assert probe.calls["list_providers"] == 1


def test_provider_catalog_is_stable_minimal_and_xss_escaped(
    override_service: Callable[[object], TestClient],
) -> None:
    providers = (
        _descriptor(
            provider_key="fixture_z",
            display_name='<script id="provider-xss">alert(1)</script>',
            content_scope="Scope <b>marker</b>",
        ),
        _descriptor(provider_key="fixture_a", display_name="Provider A"),
    )
    client = override_service(ServiceProbe(providers=providers))

    first = client.get("/source-search")
    second = client.get("/source-search")

    assert first.status_code == second.status_code == 200
    assert first.text.index("fixture_z") < first.text.index("fixture_a")
    assert first.text.index("fixture_z") == second.text.index("fixture_z")
    assert '<script id="provider-xss">' not in first.text
    assert "&lt;script id=&#34;provider-xss&#34;&gt;" in first.text
    assert "&lt;b&gt;marker&lt;/b&gt;" in first.text
    for forbidden in ("Endpoint", "Authorization", "Cookie", "Approval", "Host"):
        assert forbidden not in first.text


def test_chinese_and_english_navigation_and_page_copy(
    override_service: Callable[[object], TestClient],
) -> None:
    client = override_service(ServiceProbe(providers=(_descriptor(),)))

    zh = client.get("/source-search")
    client.get("/set-language", params={"lang": "en", "next": "/source-search"})
    en = client.get("/source-search")

    assert '<a href="/source-search">外部来源</a>' in zh.text
    assert "搜索词" in zh.text
    assert '<a href="/source-search">External Sources</a>' in en.text
    assert "Search terms" in en.text


def test_search_calls_only_search_once_and_renders_safe_metadata(
    override_service: Callable[[object], TestClient],
) -> None:
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)

    response = client.post(
        "/source-search/search",
        data={
            "provider_key": PROVIDER_KEY,
            "query": "synthetic query",
            "page": "1",
            "page_size": "10",
        },
    )

    assert response.status_code == 200
    assert probe.calls == {
        "list_providers": 1,
        "search": 1,
        "detail": 0,
        "asset_list": 0,
    }
    assert adapter.calls == {"search": 1, "detail": 0, "asset_list": 0}
    for expected in (
        "Synthetic Search Result",
        "Synthetic Alias",
        "2026-07-01",
        "Synthetic Performer",
        "Synthetic Studio",
        "Synthetic Tag",
        "Synthetic search summary",
    ):
        assert expected in response.text
    assert response.request.url.query == b""
    assert CANONICAL_MARKER not in response.text
    assert "cover-secret-marker" not in response.text
    assert "<img" not in response.text
    assert 'src="http' not in response.text


def test_search_result_text_is_escaped(
    override_service: Callable[[object], TestClient],
) -> None:
    service, adapter = _service()
    adapter.items = (_search_result('<img src=x onerror="result-xss">'),)
    client = override_service(ServiceProbe(service))

    response = client.post(
        "/source-search/search",
        data={"provider_key": PROVIDER_KEY, "query": "x", "page": "1", "page_size": "10"},
    )

    assert response.status_code == 200
    assert '<img src=x onerror="result-xss">' not in response.text
    assert "&lt;img src=x onerror=&#34;result-xss&#34;&gt;" in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {"provider_key": "", "query": "query", "page": "1", "page_size": "10"},
        {"provider_key": PROVIDER_KEY, "query": "", "page": "1", "page_size": "10"},
        {"provider_key": PROVIDER_KEY, "query": "query", "page": "0", "page_size": "10"},
        {"provider_key": PROVIDER_KEY, "query": "query", "page": "nope", "page_size": "10"},
        {"provider_key": PROVIDER_KEY, "query": "query", "page": "1", "page_size": "51"},
    ],
)
def test_invalid_search_is_rejected_before_adapter(
    override_service: Callable[[object], TestClient],
    payload: dict[str, str],
) -> None:
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)

    response = client.post("/source-search/search", data=payload)

    assert response.status_code == 400
    assert "输入无效" in response.text
    assert probe.calls["search"] == 0
    assert adapter.calls == {"search": 0, "detail": 0, "asset_list": 0}


def test_unavailable_provider_is_rejected_before_adapter_without_echo(
    override_service: Callable[[object], TestClient],
) -> None:
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)
    forged = "forged_provider_marker"

    response = client.post(
        "/source-search/search",
        data={"provider_key": forged, "query": "hidden-query-marker", "page": "1", "page_size": "10"},
    )

    assert response.status_code == 409
    assert "所选外部来源当前不可用" in response.text
    assert forged not in response.text
    assert "hidden-query-marker" not in response.text
    assert probe.calls["search"] == 0
    assert adapter.calls == {"search": 0, "detail": 0, "asset_list": 0}


def test_unapproved_search_is_rejected_before_service_call(
    override_service: Callable[[object], TestClient],
) -> None:
    probe = ServiceProbe(
        providers=(_descriptor(operations=(ProviderOperation.DETAIL,)),)
    )
    client = override_service(probe)

    response = client.post(
        "/source-search/search",
        data={"provider_key": PROVIDER_KEY, "query": "query", "page": "1", "page_size": "10"},
    )

    assert response.status_code == 409
    assert "未获准执行此操作" in response.text
    assert probe.calls["search"] == 0


def test_empty_search_is_success_not_error(
    override_service: Callable[[object], TestClient],
) -> None:
    service, adapter = _service()
    adapter.items = ()
    adapter.total = 0
    client = override_service(ServiceProbe(service))

    response = client.post(
        "/source-search/search",
        data={"provider_key": PROVIDER_KEY, "query": "none", "page": "1", "page_size": "10"},
    )

    assert response.status_code == 200
    assert "没有匹配结果" in response.text
    assert "外部来源操作未完成" not in response.text


def test_pagination_uses_post_and_only_approved_hidden_fields(
    override_service: Callable[[object], TestClient],
) -> None:
    service, adapter = _service()
    adapter.has_next = True
    client = override_service(ServiceProbe(service))

    response = client.post(
        "/source-search/search",
        data={"provider_key": PROVIDER_KEY, "query": "page marker", "page": "2", "page_size": "10"},
    )
    forms = _forms(response.text, "/source-search/search")
    pagination = [
        form
        for form in forms
        if set(cast(list[str], form["hidden"]))
        == {"provider_key", "query", "page", "page_size"}
    ]

    assert response.status_code == 200
    assert len(pagination) == 2
    assert all(form["method"] == "post" for form in pagination)
    assert "上一页" in response.text
    assert "下一页" in response.text


def test_has_next_false_does_not_render_enabled_next_action(
    override_service: Callable[[object], TestClient],
) -> None:
    service, adapter = _service()
    adapter.has_next = False
    client = override_service(ServiceProbe(service))

    response = client.post(
        "/source-search/search",
        data={"provider_key": PROVIDER_KEY, "query": "query", "page": "1", "page_size": "10"},
    )

    assert response.status_code == 200
    assert ">下一页</button>" not in response.text


def test_detail_form_contains_only_provider_and_external_identity(
    override_service: Callable[[object], TestClient],
) -> None:
    service, _ = _service()
    client = override_service(ServiceProbe(service))
    response = client.post(
        "/source-search/search",
        data={"provider_key": PROVIDER_KEY, "query": "query", "page": "1", "page_size": "10"},
    )

    forms = _forms(response.text, "/source-search/detail")

    assert len(forms) == 1
    assert forms[0]["method"] == "post"
    assert set(cast(list[str], forms[0]["fields"])) == {
        "provider_key",
        "external_id",
    }
    assert set(cast(list[str], forms[0]["hidden"])) == {
        "provider_key",
        "external_id",
    }


def test_detail_calls_only_detail_once_and_renders_non_locator_asset_facts(
    override_service: Callable[[object], TestClient],
) -> None:
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)

    response = client.post(
        "/source-search/detail",
        data={"provider_key": PROVIDER_KEY, "external_id": "video-001"},
    )

    assert response.status_code == 200
    assert probe.calls == {
        "list_providers": 1,
        "search": 0,
        "detail": 1,
        "asset_list": 0,
    }
    assert adapter.calls == {"search": 0, "detail": 1, "asset_list": 0}
    for expected in (
        "Synthetic Detail",
        "Detail Alias",
        "Synthetic detail summary",
        "Synthetic Performer",
        "Synthetic Director",
        "Synthetic Studio",
        "Synthetic Publisher",
        "Synthetic Series",
        "Synthetic Tag",
        "4.5",
        "42 票",
        "Detail Cover Fact",
        "Preview Image Fact",
        "Preview Video Fact",
        "image/jpeg",
        "1280 × 720",
        "30 秒",
    ):
        assert expected in response.text
    for forbidden in (
        CANONICAL_MARKER,
        "detail-cover-secret-marker",
        "preview-image-secret-marker",
        "preview-video-secret-marker",
        "<img",
        "<video",
        "<source",
        'href="https:',
        'src="http',
        "download=",
    ):
        assert forbidden not in response.text


@pytest.mark.parametrize(
    "provider_key,external_id,expected_status",
    [
        ("forged_provider_marker", "video-001", 409),
        (PROVIDER_KEY, "", 400),
        (PROVIDER_KEY, "../not-opaque", 400),
        (PROVIDER_KEY, "https://not-an-id", 400),
    ],
)
def test_invalid_or_forged_detail_is_rejected_before_adapter(
    override_service: Callable[[object], TestClient],
    provider_key: str,
    external_id: str,
    expected_status: int,
) -> None:
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)

    response = client.post(
        "/source-search/detail",
        data={"provider_key": provider_key, "external_id": external_id},
    )

    assert response.status_code == expected_status
    assert probe.calls["detail"] == 0
    assert adapter.calls == {"search": 0, "detail": 0, "asset_list": 0}
    if external_id:
        assert external_id not in response.text


def test_unapproved_detail_is_rejected_before_service_call(
    override_service: Callable[[object], TestClient],
) -> None:
    probe = ServiceProbe(
        providers=(_descriptor(operations=(ProviderOperation.SEARCH,)),)
    )
    client = override_service(probe)

    response = client.post(
        "/source-search/detail",
        data={"provider_key": PROVIDER_KEY, "external_id": "video-001"},
    )

    assert response.status_code == 409
    assert probe.calls["detail"] == 0


@pytest.mark.parametrize(
    "code,expected_status,expected_text",
    [
        (ProviderSearchServiceErrorCode.INVALID_REQUEST, 400, "输入无效"),
        (ProviderSearchServiceErrorCode.PROVIDER_NOT_AVAILABLE, 409, "当前不可用"),
        (ProviderSearchServiceErrorCode.OPERATION_NOT_APPROVED, 409, "未获准"),
        (ProviderSearchServiceErrorCode.ADAPTER_MISMATCH, 502, "配置校验失败"),
        (ProviderSearchServiceErrorCode.INVALID_RESULT, 502, "无效结果"),
        (ProviderSearchServiceErrorCode.PROVIDER_ERROR, 502, "请求失败"),
        (ProviderSearchServiceErrorCode.UNKNOWN, 503, "暂时不可用"),
    ],
)
def test_service_errors_map_to_stable_safe_status_and_i18n(
    override_service: Callable[[object], TestClient],
    code: ProviderSearchServiceErrorCode,
    expected_status: int,
    expected_text: str,
) -> None:
    probe = ServiceProbe(
        providers=(_descriptor(),),
        search_outcome=ProviderSearchServiceError(
            code,
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
        ),
    )
    client = override_service(probe)

    response = client.post(
        "/source-search/search",
        data={
            "provider_key": PROVIDER_KEY,
            "query": "secret-query-marker",
            "page": "1",
            "page_size": "10",
        },
    )

    assert response.status_code == expected_status
    assert expected_text in response.text
    assert code.value not in response.text
    assert ProviderErrorCode.PROVIDER_UNAVAILABLE.value not in response.text
    assert "secret-query-marker" not in response.text
    assert "没有匹配结果" not in response.text


def test_unknown_adapter_failure_does_not_leak_or_log_marker(
    override_service: Callable[[object], TestClient],
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, adapter = _service()
    marker = "adapter-secret-marker"
    adapter.search_error = RuntimeError(marker)
    client = override_service(ServiceProbe(service))

    response = client.post(
        "/source-search/search",
        data={"provider_key": PROVIDER_KEY, "query": "query", "page": "1", "page_size": "10"},
    )

    assert response.status_code == 503
    assert marker not in response.text
    assert marker not in caplog.text


@pytest.mark.parametrize("operation", ["search", "detail"])
def test_cancelled_error_propagates_without_rendering(operation: str) -> None:
    providers = (_descriptor(),)
    cancelled = asyncio.CancelledError()
    if operation == "search":
        service = ServiceProbe(providers=providers, search_outcome=cancelled)
        invocation = source_search_results_page(
            request=cast(Request, object()),
            provider_key=PROVIDER_KEY,
            query="query",
            page="1",
            page_size="10",
            service=cast(ProviderSearchService, service),
        )
    else:
        service = ServiceProbe(providers=providers, detail_outcome=cancelled)
        invocation = source_search_detail_page(
            request=cast(Request, object()),
            provider_key=PROVIDER_KEY,
            external_id="video-001",
            service=cast(ProviderSearchService, service),
        )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(invocation)


def test_successful_routes_do_not_use_database_file_outbound_or_asset_list(
    override_service: Callable[[object], TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, adapter = _service()
    client = override_service(ServiceProbe(service))
    monkeypatch.setattr(socket, "getaddrinfo", _forbidden)
    monkeypatch.setattr(socket, "gethostbyname", _forbidden)
    monkeypatch.setattr(httpx2, "AsyncClient", _forbidden)
    monkeypatch.setattr(OutboundHttpClient, "__init__", _forbidden)
    monkeypatch.setattr(Session, "execute", _forbidden)
    monkeypatch.setattr(Session, "commit", _forbidden)
    monkeypatch.setattr(Path, "read_bytes", _forbidden)
    monkeypatch.setattr(Path, "write_bytes", _forbidden)

    search = client.post(
        "/source-search/search",
        data={"provider_key": PROVIDER_KEY, "query": "query", "page": "1", "page_size": "10"},
    )
    detail = client.post(
        "/source-search/detail",
        data={"provider_key": PROVIDER_KEY, "external_id": "video-001"},
    )

    assert search.status_code == detail.status_code == 200
    assert adapter.calls == {"search": 1, "detail": 1, "asset_list": 0}


def test_back_to_get_does_not_repeat_search_or_detail(
    override_service: Callable[[object], TestClient],
) -> None:
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)
    detail = client.post(
        "/source-search/detail",
        data={"provider_key": PROVIDER_KEY, "external_id": "video-001"},
    )

    returned = client.get("/source-search")

    assert detail.status_code == returned.status_code == 200
    assert adapter.calls == {"search": 0, "detail": 1, "asset_list": 0}
    assert probe.calls["list_providers"] == 2


def test_phase5_n5b_preserves_version_schema_backup_and_empty_production_catalogs() -> None:
    assert app.version == "1.3.0"
    assert CURRENT_SCHEMA_VERSION == 5
    assert BACKUP_SCHEMA_V2 == "nsfwtrack.backup.v2"
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    assert PRODUCTION_SEARCH_PACKAGES == ()
    assert build_production_search_service().list_providers() == ()
