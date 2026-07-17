from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.main import create_app
from app.models import Item
from app.request_context import REQUEST_ID_HEADER, is_valid_request_id
from app.routers import auth, backup, creators, importer, items, pages, search, stats, tags
from app.security import safe_local_path

ROUTERS = (auth, backup, creators, importer, items, pages, search, stats, tags)
PUBLIC_ROUTES = {
    ("POST", "/api/auth/login"),
    ("GET", "/login"),
    ("GET", "/set-language"),
}


def test_application_metadata_matches_current_release() -> None:
    assert create_app().version == "1.1.0"


def test_every_non_public_route_declares_authentication_dependency() -> None:
    uncovered: list[str] = []
    for router_module in ROUTERS:
        for route in router_module.router.routes:
            dependency_names = {
                getattr(dependency.call, "__name__", "")
                for dependency in route.dependant.dependencies
            }
            for method in route.methods:
                if (method, route.path) in PUBLIC_ROUTES:
                    continue
                if not dependency_names & {"require_api_auth", "require_page_auth"}:
                    uncovered.append(f"{method} {route.path}")
    assert uncovered == []


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/auth/login", "post"),
        ("/api/items/1", "put"),
        ("/api/items/1", "delete"),
        ("/logout", "post"),
        ("/items/1/view", "post"),
    ],
)
def test_cross_origin_state_changes_are_rejected(
    client: TestClient,
    path: str,
    method: str,
) -> None:
    response = getattr(client, method)(
        path,
        headers={"Origin": "https://attacker.invalid"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert is_valid_request_id(response.headers[REQUEST_ID_HEADER])
    if path.startswith("/api/"):
        assert response.json()["error"] == "forbidden"
    else:
        assert response.headers["content-type"].startswith("text/html")


def test_same_origin_and_non_browser_login_requests_remain_compatible(
    client: TestClient,
) -> None:
    same_origin = client.post(
        "/api/auth/login",
        json={"password": "test-password"},
        headers={"Origin": "http://testserver"},
    )
    assert same_origin.status_code == 200

    client.post("/api/auth/logout")
    no_origin = client.post(
        "/api/auth/login",
        json={"password": "test-password"},
    )
    assert no_origin.status_code == 200


def test_cross_origin_referer_and_null_origin_are_rejected(client: TestClient) -> None:
    bad_referer = client.post(
        "/api/auth/login",
        json={"password": "test-password"},
        headers={"Referer": "http://attacker.invalid/form"},
    )
    null_origin = client.post(
        "/api/auth/login",
        json={"password": "test-password"},
        headers={"Origin": "null"},
    )
    safe_get = client.get(
        "/login",
        headers={"Origin": "https://attacker.invalid"},
    )

    assert bad_referer.status_code == 403
    assert null_origin.status_code == 403
    assert safe_get.status_code == 200


def test_login_rotates_session_state_and_logout_invalidates_old_cookie() -> None:
    test_app = create_app()

    @test_app.get("/testing/session/seed")
    def seed_session(request: Request) -> dict[str, bool]:
        request.session["untrusted_pre_auth"] = "remove-me"
        request.session["ui_language"] = "en"
        return {"ok": True}

    @test_app.get("/testing/session/state")
    def session_state(request: Request) -> dict[str, object]:
        return dict(request.session)

    with TestClient(test_app) as session_client:
        session_client.get("/testing/session/seed")
        login = session_client.post(
            "/api/auth/login",
            json={"password": "test-password"},
        )
        assert login.status_code == 200
        state = session_client.get("/testing/session/state").json()
        assert "untrusted_pre_auth" not in state
        assert state["ui_language"] == "en"
        assert state["is_authenticated"] is True
        authenticated_cookie = session_client.cookies.get("session")
        assert authenticated_cookie

        logout = session_client.post("/api/auth/logout")
        assert logout.status_code == 200
        assert session_client.get("/api/items").status_code == 401

    with TestClient(test_app) as replay_client:
        replay_client.cookies.set("session", authenticated_cookie)
        assert replay_client.get("/api/items").status_code == 401


def test_default_session_cookie_is_httponly_and_lax(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"password": "test-password"},
    )
    cookie = response.headers["set-cookie"].casefold()

    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "; secure" not in cookie


def test_https_session_cookie_can_enable_secure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    get_settings.cache_clear()
    try:
        secure_app = create_app()
        with TestClient(secure_app, base_url="https://testserver") as secure_client:
            response = secure_client.post(
                "/api/auth/login",
                json={"password": "test-password"},
            )
            assert response.status_code == 200
            assert "; secure" in response.headers["set-cookie"].casefold()
    finally:
        monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "value",
    [
        "https://attacker.invalid/path",
        "//attacker.invalid/path",
        "/\\attacker.invalid/path",
        "/%5cattacker.invalid/path",
        "/\nlocation:https://attacker.invalid",
    ],
)
def test_redirect_targets_reject_external_or_ambiguous_paths(
    client: TestClient,
    value: str,
) -> None:
    assert safe_local_path(value, fallback="/") == "/"
    response = client.get(
        "/set-language",
        params={"lang": "en", "next": value},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_local_redirect_target_keeps_query_string() -> None:
    assert (
        safe_local_path("/items?state=wish&page=2", fallback="/")
        == "/items?state=wish&page=2"
    )


def test_authenticated_cookie_is_invalid_after_application_restart() -> None:
    first_app = create_app()
    with TestClient(first_app) as first_client:
        response = first_client.post(
            "/api/auth/login",
            json={"password": "test-password"},
        )
        assert response.status_code == 200
        old_cookie = first_client.cookies.get("session")
        assert old_cookie

    second_app = create_app()
    with TestClient(second_app) as second_client:
        second_client.cookies.set("session", old_cookie)
        assert second_client.get("/api/items").status_code == 401


def test_html_templates_escape_user_content(auth_client: TestClient) -> None:
    title = '<script>alert("release-review")</script>'
    create_response = auth_client.post(
        "/api/items",
        json={"title": title},
    )
    assert create_response.status_code == 201

    page = auth_client.get("/items")
    assert title not in page.text
    assert "&lt;script&gt;" in page.text


def test_login_rejects_malformed_or_non_object_json(client: TestClient) -> None:
    malformed = client.post(
        "/api/auth/login",
        content="{",
        headers={"Content-Type": "application/json"},
    )
    non_object = client.post(
        "/api/auth/login",
        json=["test-password"],
    )

    assert malformed.status_code == 400
    assert non_object.status_code == 400
    assert "Traceback" not in malformed.text
    assert "test-password" not in non_object.text


def test_import_upload_limit_rejects_before_parse_or_write(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SessionLocal() as db:
        before_count = db.query(Item).count()
    oversized = b"title\n" + (b"x" * (1024 * 1024 + 1))

    monkeypatch.setenv("MAX_IMPORT_UPLOAD_MB", "1")
    get_settings.cache_clear()
    try:
        api_response = auth_client.post(
            "/api/import/csv",
            files={"file": ("large.csv", oversized, "text/csv")},
        )
        page_response = auth_client.post(
            "/import/json",
            files={"file": ("large.json", oversized, "application/json")},
        )
    finally:
        monkeypatch.delenv("MAX_IMPORT_UPLOAD_MB", raising=False)
        get_settings.cache_clear()

    assert api_response.status_code == 413
    assert api_response.json()["detail"] == "file_too_large"
    assert page_response.status_code == 200
    assert "导入文件超过大小限制" in page_response.text
    with SessionLocal() as db:
        assert db.query(Item).count() == before_count
