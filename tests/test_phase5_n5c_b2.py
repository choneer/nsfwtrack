from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable, Generator
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import app.provider_apply.web as provider_apply_web
import app.routers.source_search as source_search_router
from app.auth import SESSION_AUTH_KEY, SESSION_GENERATION_KEY
from app.config import Settings
from app.database import SessionLocal
from app.main import app
from app.models import Item, ItemSource
from app.provider_apply.contracts import (
    PROVIDER_APPLY_RESULT_FORMAT,
    PROVIDER_APPLY_RESULT_VERSION,
    ProviderApplyAction,
    ProviderApplyCommitStatus,
    ProviderApplyError,
    ProviderApplyErrorCode,
    ProviderApplyResult,
)
from app.provider_apply.service import compute_provider_apply_projection_hash
from app.provider_apply.web import (
    PROVIDER_APPLY_SESSION_NONCE_KEY,
    ProviderApplyWebError,
    ProviderApplyWebErrorCode,
    ProviderApplyWebMaterial,
    ensure_provider_apply_web_material,
    get_provider_apply_web_material,
)
from app.routers.source_search import get_provider_search_service
from app.services.exporter import BACKUP_SCHEMA_V2
from app.services.schema_version import CURRENT_SCHEMA_VERSION
from app.source_adapters import PRODUCTION_ENDPOINT_REGISTRY
from app.source_search import (
    PRODUCTION_SEARCH_PACKAGES,
    VideoDetailEnvelope,
    VideoDetailRequest,
    build_production_search_service,
)
from tests.test_phase5_n5b import (
    CANONICAL_MARKER,
    NOW,
    PROVIDER_KEY,
    ServiceProbe,
    _descriptor,
    _detail,
    _service,
)


_TOKEN_INPUT = re.compile(
    r'<input type="hidden" name="token" value="([^"]+)" autocomplete="off">'
)
_HASH_MARKER = "v1:sha256:"


class _ApplyFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_apply_form = False
        self.fields: list[dict[str, str | None]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("action") == "/source-search/apply":
            self.in_apply_form = True
        elif self.in_apply_form and tag == "input":
            self.fields.append(values)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self.in_apply_form:
            self.in_apply_form = False


def _token(response: Any) -> str:
    match = _TOKEN_INPUT.search(response.text)
    assert match is not None
    return match.group(1)


def _database_snapshot() -> tuple[tuple[object, ...], tuple[object, ...]]:
    with SessionLocal() as db:
        items = tuple(
            db.execute(
                select(
                    Item.id,
                    Item.title,
                    Item.summary,
                    Item.release_date,
                    Item.cover_path,
                    Item.extra,
                ).order_by(Item.id)
            ).all()
        )
        sources = tuple(
            db.execute(
                select(
                    ItemSource.id,
                    ItemSource.item_id,
                    ItemSource.url,
                    ItemSource.normalized_url,
                    ItemSource.title,
                    ItemSource.provider_key,
                    ItemSource.external_id,
                    ItemSource.last_checked_at,
                    ItemSource.metadata_hash,
                ).order_by(ItemSource.id)
            ).all()
        )
    return items, sources


def _request(
    *,
    generation: str = "g" * 64,
    nonce: str | None = None,
) -> tuple[Request, dict[str, object]]:
    session: dict[str, object] = {
        SESSION_AUTH_KEY: True,
        SESSION_GENERATION_KEY: generation,
    }
    if nonce is not None:
        session[PROVIDER_APPLY_SESSION_NONCE_KEY] = nonce
    state = SimpleNamespace(session_generation=generation)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/source-search/detail",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "app": SimpleNamespace(state=state),
            "session": session,
        }
    )
    return request, session


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


def _preview(
    client: TestClient,
    probe: ServiceProbe,
) -> Any:
    client.app.dependency_overrides[get_provider_search_service] = lambda: probe
    return client.post(
        "/source-search/detail",
        data={"provider_key": PROVIDER_KEY, "external_id": "video-001"},
    )


def _seed_noop_state() -> int:
    envelope = VideoDetailEnvelope(
        _descriptor(),
        VideoDetailRequest(PROVIDER_KEY, "video-001"),
        _detail(),
        NOW,
    )
    projection_hash = compute_provider_apply_projection_hash(envelope, CANONICAL_MARKER)
    with SessionLocal() as db:
        item = Item(
            title="Preserved local title",
            summary="Preserved local summary",
            release_date="2026-07-03",
        )
        db.add(item)
        db.flush()
        source = ItemSource(
            item_id=item.id,
            url=CANONICAL_MARKER,
            normalized_url=CANONICAL_MARKER,
            title="Preserved local source title",
            provider_key=PROVIDER_KEY,
            external_id="video-001",
            last_checked_at=NOW,
            metadata_hash=projection_hash,
        )
        db.add(source)
        db.commit()
        return item.id


def _seed_update_state(
    *,
    summary: str | None,
    release_date: str | None,
) -> tuple[int, int]:
    with SessionLocal() as db:
        item = Item(
            title="Preserved local title",
            summary=summary,
            release_date=release_date,
            cover_path="/media/preserved-cover.jpg",
            extra='{"preserved":true}',
        )
        db.add(item)
        db.flush()
        source = ItemSource(
            item_id=item.id,
            url=CANONICAL_MARKER,
            normalized_url=CANONICAL_MARKER,
            title="Preserved local source title",
            provider_key=PROVIDER_KEY,
            external_id="video-001",
            last_checked_at=NOW - timedelta(days=1),
            metadata_hash="v1:sha256:" + "a" * 64,
        )
        db.add(source)
        db.commit()
        return item.id, source.id


def test_web_material_is_frozen_slotted_redacted_canonical_and_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        database_url="sqlite:///:memory:",
        app_password="password",
        secret_key="root-secret-one",
        max_backup_upload_mb=5,
        max_import_upload_mb=5,
        session_cookie_secure=False,
    )
    monkeypatch.setattr(provider_apply_web, "get_settings", lambda: settings)
    request, session = _request()

    first = ensure_provider_apply_web_material(request)
    second = get_provider_apply_web_material(request)

    assert first == second
    assert type(first.secret) is bytes and len(first.secret) == 32
    assert re.fullmatch(r"provider-apply:web:v1:[0-9a-f]{64}", first.context)
    assert str(first) == "ProviderApplyWebMaterial"
    assert repr(first) == "ProviderApplyWebMaterial()"
    assert hasattr(first, "__dict__") is False
    with pytest.raises(FrozenInstanceError):
        first.context = "changed"  # type: ignore[misc]
    nonce = cast(str, session[PROVIDER_APPLY_SESSION_NONCE_KEY])
    assert re.fullmatch(r"[0-9a-f]{64}", nonce)

    message = ("g" * 64).encode() + b"\0" + nonce.encode()
    expected_secret = hmac.new(
        b"root-secret-one",
        b"nsfwtrack.provider-apply.web-secret.v1\0" + message,
        hashlib.sha256,
    ).digest()
    expected_context = hmac.new(
        b"root-secret-one",
        b"nsfwtrack.provider-apply.web-context.v1\0" + message,
        hashlib.sha256,
    ).hexdigest()
    assert first.secret == expected_secret
    assert first.context == "provider-apply:web:v1:" + expected_context
    assert first.secret.hex() != expected_context


def test_material_changes_with_nonce_generation_and_root_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def settings(secret: str) -> Settings:
        return Settings("sqlite:///:memory:", "p", secret, 5, 5, False)

    monkeypatch.setattr(provider_apply_web, "get_settings", lambda: settings("root-a"))
    request_a, _ = _request(nonce="a" * 64)
    request_b, _ = _request(nonce="b" * 64)
    request_generation, _ = _request(generation="h" * 64, nonce="a" * 64)
    material_a = get_provider_apply_web_material(request_a)
    material_b = get_provider_apply_web_material(request_b)
    material_generation = get_provider_apply_web_material(request_generation)
    monkeypatch.setattr(provider_apply_web, "get_settings", lambda: settings("root-b"))
    material_root = get_provider_apply_web_material(request_a)

    assert len({
        material_a.secret,
        material_b.secret,
        material_generation.secret,
        material_root.secret,
    }) == 4
    assert len({
        material_a.context,
        material_b.context,
        material_generation.context,
        material_root.context,
    }) == 4


@pytest.mark.parametrize("nonce", [None, "", "A" * 64, "g" * 64, "0" * 63])
def test_confirm_material_never_creates_or_repairs_nonce(nonce: str | None) -> None:
    request, session = _request(nonce=nonce)
    before = dict(session)

    with pytest.raises(ProviderApplyWebError) as raised:
        get_provider_apply_web_material(request)

    assert raised.value.code is ProviderApplyWebErrorCode.SESSION_INVALID
    assert session == before


def test_preview_material_replaces_malformed_nonce_only_after_valid_session() -> None:
    request, session = _request(nonce="malformed")

    material = ensure_provider_apply_web_material(request)

    assert len(material.secret) == 32
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        cast(str, session[PROVIDER_APPLY_SESSION_NONCE_KEY]),
    )

    bad_request, bad_session = _request(nonce="malformed")
    bad_request.app.state.session_generation = "different"
    before = dict(bad_session)
    with pytest.raises(ProviderApplyWebError):
        ensure_provider_apply_web_material(bad_request)
    assert bad_session == before


def test_production_get_remains_empty_zero_apply_and_does_not_mutate_session(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before_cookie = auth_client.cookies.get("session")
    monkeypatch.setattr(
        source_search_router,
        "apply_provider_apply_token",
        lambda *args, **kwargs: pytest.fail("GET must not call apply"),
    )
    monkeypatch.setattr(
        source_search_router,
        "ensure_provider_apply_web_material",
        lambda *args, **kwargs: pytest.fail("GET must not create material"),
    )
    monkeypatch.setattr(
        source_search_router,
        "get_provider_apply_web_material",
        lambda *args, **kwargs: pytest.fail("GET must not derive material"),
    )

    response = auth_client.get("/source-search")

    assert response.status_code == 200
    assert "暂无可用外部来源" in response.text
    assert 'action="/source-search/apply"' not in response.text
    assert auth_client.cookies.get("session") == before_cookie


def test_preview_calls_detail_once_is_read_only_and_renders_one_hidden_token(
    override_service: Callable[[object], TestClient],
) -> None:
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)
    before = _database_snapshot()

    response = _preview(client, probe)
    after = _database_snapshot()
    token = _token(response)
    parser = _ApplyFormParser()
    parser.feed(response.text)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert before == after == ((), ())
    assert probe.calls == {
        "list_providers": 1,
        "search": 0,
        "detail": 1,
        "asset_list": 0,
    }
    assert adapter.calls == {"search": 0, "detail": 1, "asset_list": 0}
    assert len(parser.fields) == 2
    assert parser.fields[0] == {
        "type": "hidden",
        "name": "token",
        "value": token,
        "autocomplete": "off",
    }
    assert parser.fields[1]["name"] == "confirmation"
    assert parser.fields[1]["value"] == "apply"
    assert "创建新条目" in response.text
    assert "10 分钟" in response.text
    assert "不会再次访问外部来源" in response.text
    assert "将写入" in response.text
    for forbidden in (
        CANONICAL_MARKER,
        "video-001",
        _HASH_MARKER,
        "provider-apply:web:v1:",
        PROVIDER_APPLY_SESSION_NONCE_KEY,
    ):
        assert forbidden not in response.text


def test_noop_preview_has_no_token_form_nonce_or_cache_override(
    override_service: Callable[[object], TestClient],
) -> None:
    _seed_noop_state()
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)
    before_cookie = client.cookies.get("session")
    before = _database_snapshot()

    response = _preview(client, probe)

    assert response.status_code == 200
    assert _TOKEN_INPUT.search(response.text) is None
    assert 'action="/source-search/apply"' not in response.text
    assert "没有可应用的变化" in response.text
    assert response.headers.get("cache-control") != "no-store"
    assert client.cookies.get("session") == before_cookie
    assert _database_snapshot() == before
    assert adapter.calls == {"search": 0, "detail": 1, "asset_list": 0}


def test_confirm_create_is_prg_provider_zero_call_and_replay_is_stale(
    override_service: Callable[[object], TestClient],
) -> None:
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)
    preview = _preview(client, probe)
    token = _token(preview)
    calls_after_preview = dict(probe.calls)
    adapter_after_preview = dict(adapter.calls)

    confirmed = client.post(
        "/source-search/apply",
        data={"token": token, "confirmation": "apply"},
        follow_redirects=False,
    )

    assert confirmed.status_code == 303
    assert re.fullmatch(r"/items/[1-9][0-9]*", confirmed.headers["location"])
    assert token not in confirmed.headers["location"]
    assert probe.calls == calls_after_preview
    assert adapter.calls == adapter_after_preview
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Item)) == 1
        assert db.scalar(select(func.count()).select_from(ItemSource)) == 1
        item = db.scalar(select(Item))
        source = db.scalar(select(ItemSource))
        assert item is not None and source is not None
        assert item.title == "Synthetic Detail"
        assert item.summary == "Synthetic detail summary"
        assert item.release_date == "2026-07-02"
        assert source.item_id == item.id
        assert source.provider_key == PROVIDER_KEY
        assert source.external_id == "video-001"
        assert source.url == CANONICAL_MARKER

    detail = client.get(confirmed.headers["location"])
    assert "已安全应用到本地条目" in detail.text
    assert token not in detail.text

    replay = client.post(
        "/source-search/apply",
        data={"token": token, "confirmation": "apply"},
        follow_redirects=False,
    )
    assert replay.status_code == 303
    assert replay.headers["location"] == "/source-search"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Item)) == 1
        assert db.scalar(select(func.count()).select_from(ItemSource)) == 1


@pytest.mark.parametrize(
    "summary,release_date,expected_summary,expected_release",
    [
        (None, None, "Synthetic detail summary", "2026-07-02"),
        ("Local summary", "2026-07-04", "Local summary", "2026-07-04"),
    ],
)
def test_confirm_update_fills_only_blanks_or_refreshes_tracking(
    override_service: Callable[[object], TestClient],
    summary: str | None,
    release_date: str | None,
    expected_summary: str,
    expected_release: str,
) -> None:
    item_id, source_id = _seed_update_state(
        summary=summary,
        release_date=release_date,
    )
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)
    preview = _preview(client, probe)
    token = _token(preview)
    assert "更新现有条目" in preview.text
    assert "保留本地值，不覆盖" in preview.text

    confirmed = client.post(
        "/source-search/apply",
        data={"token": token, "confirmation": "apply"},
        follow_redirects=False,
    )

    assert confirmed.status_code == 303
    assert confirmed.headers["location"] == f"/items/{item_id}"
    assert adapter.calls == {"search": 0, "detail": 1, "asset_list": 0}
    with SessionLocal() as db:
        item = db.get(Item, item_id)
        source = db.get(ItemSource, source_id)
        assert item is not None and source is not None
        assert item.title == "Preserved local title"
        assert item.summary == expected_summary
        assert item.release_date == expected_release
        assert item.cover_path == "/media/preserved-cover.jpg"
        assert item.extra == '{"preserved":true}'
        assert source.title == "Preserved local source title"
        assert source.url == CANONICAL_MARKER
        assert source.normalized_url == CANONICAL_MARKER
        assert source.provider_key == PROVIDER_KEY
        assert source.external_id == "video-001"
        assert source.last_checked_at == NOW
        assert source.metadata_hash != "v1:sha256:" + "a" * 64


def test_duplicate_title_is_warning_link_and_never_auto_binds(
    override_service: Callable[[object], TestClient],
) -> None:
    with SessionLocal() as db:
        duplicate = Item(title="Synthetic Detail")
        db.add(duplicate)
        db.commit()
        duplicate_id = duplicate.id
    service, _ = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)

    preview = _preview(client, probe)
    token = _token(preview)

    assert "这只是提示，不会自动关联" in preview.text
    assert f'href="/items/{duplicate_id}"' in preview.text
    confirmed = client.post(
        "/source-search/apply",
        data={"token": token, "confirmation": "apply"},
        follow_redirects=False,
    )
    assert confirmed.status_code == 303
    assert confirmed.headers["location"] != f"/items/{duplicate_id}"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Item)) == 2
        source = db.scalar(select(ItemSource))
        assert source is not None and source.item_id != duplicate_id


@pytest.mark.parametrize("confirmation", ["", "Apply", "true", " apply", "apply "])
def test_exact_confirmation_precedes_material_and_apply(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    confirmation: str,
) -> None:
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("apply must not be called")

    monkeypatch.setattr(source_search_router, "apply_provider_apply_token", forbidden)
    before_cookie = auth_client.cookies.get("session")
    response = auth_client.post(
        "/source-search/apply",
        data={"token": "hidden-token-marker", "confirmation": confirmation},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/source-search"
    assert "hidden-token-marker" not in response.headers["location"]
    assert calls == 0
    assert auth_client.cookies.get("session") != before_cookie


def test_missing_nonce_confirm_rejects_before_apply_without_creating_nonce(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("apply must not be called")

    monkeypatch.setattr(source_search_router, "apply_provider_apply_token", forbidden)
    response = auth_client.post(
        "/source-search/apply",
        data={"token": "hidden-token-marker", "confirmation": "apply"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/source-search"
    assert calls == 0
    page = auth_client.get("/source-search")
    assert "当前会话无法使用此应用计划" in page.text
    assert "hidden-token-marker" not in page.text


def test_token_is_bound_to_browser_session_and_generation(
    override_service: Callable[[object], TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _service()
    probe = ServiceProbe(service)
    client_a = override_service(probe)
    token = _token(_preview(client_a, probe))

    with TestClient(app) as client_b:
        login = client_b.post("/api/auth/login", json={"password": "test-password"})
        assert login.status_code == 200
        cross_session = client_b.post(
            "/source-search/apply",
            data={"token": token, "confirmation": "apply"},
            follow_redirects=False,
        )
        assert cross_session.status_code == 303
        assert cross_session.headers["location"] == "/source-search"

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Item)) == 0

    monkeypatch.setattr(client_a.app.state, "session_generation", "rotated-generation")
    rotated = client_a.post(
        "/source-search/apply",
        data={"token": token, "confirmation": "apply"},
        follow_redirects=False,
    )
    assert rotated.status_code == 303
    assert rotated.headers["location"] == "/login"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Item)) == 0


def test_logout_and_relogin_invalidate_old_token(
    override_service: Callable[[object], TestClient],
) -> None:
    service, _ = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)
    token = _token(_preview(client, probe))

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    login = client.post("/api/auth/login", json={"password": "test-password"})
    assert login.status_code == 200
    response = client.post(
        "/source-search/apply",
        data={"token": token, "confirmation": "apply"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/source-search"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Item)) == 0


@pytest.mark.parametrize(
    "code,location,flash_text",
    [
        (ProviderApplyErrorCode.TOKEN_EXPIRED, "/source-search", "应用计划已过期"),
        (ProviderApplyErrorCode.TOKEN_CONTEXT_MISMATCH, "/source-search", "当前会话无法使用"),
        (ProviderApplyErrorCode.TOKEN_SIGNATURE_INVALID, "/source-search", "应用计划无效"),
        (ProviderApplyErrorCode.NOTHING_TO_APPLY, "/source-search", "没有可应用的变化"),
        (ProviderApplyErrorCode.STALE_PLAN, "/source-search", "原应用计划已失效"),
        (ProviderApplyErrorCode.DATABASE_STATE_INVALID, "/source-search", "数据库状态不满足"),
        (ProviderApplyErrorCode.WRITE_CONFLICT, "/source-search", "当前本地数据冲突"),
        (ProviderApplyErrorCode.WRITE_FAILED, "/source-search", "本地写入失败"),
        (ProviderApplyErrorCode.UNKNOWN, "/source-search", "未自动重试"),
        (
            ProviderApplyErrorCode.COMMIT_STATE_UNKNOWN,
            "/items",
            "最终状态无法确认；请先检查本地条目，禁止直接重复提交",
        ),
    ],
)
def test_confirm_error_mapping_is_stable_redacted_and_never_retries(
    override_service: Callable[[object], TestClient],
    monkeypatch: pytest.MonkeyPatch,
    code: ProviderApplyErrorCode,
    location: str,
    flash_text: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, adapter = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)
    token = _token(_preview(client, probe))
    provider_calls = dict(probe.calls)
    adapter_calls = dict(adapter.calls)
    apply_calls = 0

    def fail(*args: object, **kwargs: object) -> object:
        nonlocal apply_calls
        apply_calls += 1
        raise ProviderApplyError(code)

    monkeypatch.setattr(source_search_router, "apply_provider_apply_token", fail)
    response = client.post(
        "/source-search/apply",
        data={"token": token, "confirmation": "apply"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == location
    assert token not in response.headers["location"]
    assert apply_calls == 1
    assert probe.calls == provider_calls
    assert adapter.calls == adapter_calls
    page = client.get(location)
    assert flash_text in page.text
    assert token not in page.text
    assert token not in caplog.text


def test_verified_after_exception_uses_info_flash_and_item_prg(
    override_service: Callable[[object], TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _service()
    probe = ServiceProbe(service)
    client = override_service(probe)
    token = _token(_preview(client, probe))
    result = ProviderApplyResult(
        PROVIDER_APPLY_RESULT_FORMAT,
        PROVIDER_APPLY_RESULT_VERSION,
        ProviderApplyAction.CREATE_ITEM,
        42,
        43,
        ("item.title",),
        ProviderApplyCommitStatus.COMMITTED_VERIFIED_AFTER_EXCEPTION,
    )
    monkeypatch.setattr(
        source_search_router,
        "apply_provider_apply_token",
        lambda *args, **kwargs: result,
    )

    response = client.post(
        "/source-search/apply",
        data={"token": token, "confirmation": "apply"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/items/42"
    page = client.get("/items")
    assert "独立状态检查已确认本地变化成功提交" in page.text
    assert token not in page.text


def test_apply_route_requires_auth_and_has_no_get_variant(client: TestClient) -> None:
    post = client.post(
        "/source-search/apply",
        data={"token": "marker", "confirmation": "apply"},
        follow_redirects=False,
    )
    get = client.get("/source-search/apply", follow_redirects=False)

    assert post.status_code == 303
    assert post.headers["location"] == "/login"
    assert get.status_code == 405


def test_phase_invariants_and_empty_production_catalogs_are_unchanged() -> None:
    assert app.version == "1.2.0"
    assert CURRENT_SCHEMA_VERSION == 4
    assert BACKUP_SCHEMA_V2 == "nsfwtrack.backup.v2"
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    assert PRODUCTION_SEARCH_PACKAGES == ()
    assert build_production_search_service().list_providers() == ()
