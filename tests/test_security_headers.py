from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.request_context import REQUEST_ID_HEADER, is_valid_request_id
from app.security_headers import SECURITY_HEADERS
from app.services import local_media


def _assert_security_headers(response: object) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert response.headers[name] == value
    assert "Strict-Transport-Security" not in response.headers
    assert "Content-Security-Policy" not in response.headers
    assert is_valid_request_id(response.headers[REQUEST_ID_HEADER])


def test_login_success_html_includes_security_headers(client: TestClient) -> None:
    response = client.get("/login")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    _assert_security_headers(response)


def test_authenticated_page_includes_security_headers(auth_client: TestClient) -> None:
    response = auth_client.get("/items")

    assert response.status_code == 200
    _assert_security_headers(response)


def test_json_api_success_includes_security_headers(auth_client: TestClient) -> None:
    response = auth_client.get("/api/items")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    _assert_security_headers(response)


def test_redirect_response_includes_security_headers(client: TestClient) -> None:
    response = client.get("/items", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    _assert_security_headers(response)


def test_not_found_html_includes_security_headers(client: TestClient) -> None:
    response = client.get("/missing-page-for-security-headers")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    _assert_security_headers(response)


def test_validation_error_json_includes_security_headers(
    auth_client: TestClient,
) -> None:
    response = auth_client.post("/api/items", json={})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    _assert_security_headers(response)
    payload = response.json()
    assert "request_id" in payload
    assert "error" in payload


def test_method_not_allowed_preserves_allow_and_security_headers(
    client: TestClient,
) -> None:
    response = client.get("/api/auth/logout")

    assert response.status_code == 405
    assert "POST" in response.headers.get("allow", "").upper()
    _assert_security_headers(response)


def test_local_media_response_includes_security_headers(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    cover = media_root / "covers" / "header.png"
    cover.parent.mkdir(parents=True)
    cover.write_bytes(b"security-header-image")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    created = auth_client.post(
        "/api/items",
        json={
            "title": "Security Header Media",
            "cover_path": "/media/covers/header.png",
        },
    )
    assert created.status_code == 201
    response = auth_client.get("/media/covers/header.png")

    assert response.status_code == 200
    assert response.content == b"security-header-image"
    _assert_security_headers(response)


def test_login_form_post_still_works_with_security_headers(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/auth/login",
        json={"password": "test-password"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    _assert_security_headers(response)
