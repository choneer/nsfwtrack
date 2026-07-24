"""Catalog readiness snapshot — no secrets, honest live/fixture modes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.providers.readiness import (
    DEFAULT_CATALOG_KEYS,
    build_catalog_readiness,
)


def test_readiness_without_cookie_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("NSFWTRACK_JAVDB_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("NSFWTRACK_JAVDB_SESSION_COOKIE_FILE", raising=False)
    monkeypatch.delenv("NSFWTRACK_HTTP_PROXY", raising=False)
    monkeypatch.delenv("NSFW_HTTP_PROXY", raising=False)
    # Point cookie store away from any real drop-zone file.
    monkeypatch.setattr(
        "app.providers.readiness.default_cookie_store_path",
        lambda key="javdb": tmp_path / f"{key}.cookie",
    )
    monkeypatch.setattr(
        "app.cookiecloud.client.default_cookie_store_path",
        lambda key="javdb": tmp_path / f"{key}.cookie",
    )

    snap = build_catalog_readiness(application_version="1.5.0")
    payload = snap.to_dict()
    text = json.dumps(payload)

    assert payload["application_version"] == "1.5.0"
    assert payload["proxy_configured"] is False
    assert [p["provider_key"] for p in payload["providers"]] == list(
        DEFAULT_CATALOG_KEYS
    )

    by_key = {p["provider_key"]: p for p in payload["providers"]}
    assert by_key["javdb_metadata"]["mode"] == "not_configured"
    assert by_key["javdb_metadata"]["cookie_loadable"] is False
    assert by_key["jiuse_vod"]["mode"] == "not_configured"
    assert by_key["jiuse_vod"]["scope"] == "TEST_FIXTURE"
    assert by_key["zuidapi_vod"]["mode"] == "not_configured"
    assert by_key["copymanga"]["mode"] == "not_configured"
    assert by_key["comic_local_fixture"]["scope"] == "TEST_FIXTURE"

    # Never leak cookie-like values
    assert "session=" not in text
    assert "password" not in text.lower()
    assert "secret-cookie" not in text


def test_readiness_with_cookie_file_remains_not_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cookie_file = tmp_path / "javdb_metadata.cookie"
    cookie_file.write_text("session=fake-secret-value-xyz; theme=dark\n", encoding="utf-8")
    monkeypatch.delenv("NSFWTRACK_JAVDB_SESSION_COOKIE", raising=False)
    monkeypatch.setenv("NSFWTRACK_JAVDB_SESSION_COOKIE_FILE", str(cookie_file))
    monkeypatch.setenv("NSFWTRACK_HTTP_PROXY", "http://127.0.0.1:6123")

    snap = build_catalog_readiness()
    payload = snap.to_dict()
    by_key = {p["provider_key"]: p for p in payload["providers"]}

    assert by_key["javdb_metadata"]["mode"] == "not_configured"
    assert by_key["javdb_metadata"]["cookie_loadable"] is True
    assert payload["proxy_configured"] is True
    assert "NSFWTRACK_HTTP_PROXY" in payload["proxy_env_keys"]

    dumped = json.dumps(payload)
    assert "fake-secret-value-xyz" not in dumped
    assert "session=" not in dumped


def test_readiness_rechecks_cookie_without_cached_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cookie_path = tmp_path / "javdb_metadata.cookie"
    monkeypatch.delenv("NSFWTRACK_JAVDB_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("NSFWTRACK_JAVDB_SESSION_COOKIE_FILE", raising=False)
    monkeypatch.setattr(
        "app.providers.readiness.default_cookie_store_path",
        lambda key="javdb": cookie_path,
    )
    monkeypatch.setattr(
        "app.cookiecloud.client.default_cookie_store_path",
        lambda key="javdb": cookie_path,
    )

    before = build_catalog_readiness().providers[0]
    cookie_path.write_text("session=changed-after-first-read\n", encoding="utf-8")
    after = build_catalog_readiness().providers[0]

    assert before.cookie_loadable is False
    assert after.cookie_loadable is True
    assert before.mode == after.mode == "not_configured"


def test_readiness_api_requires_auth(client) -> None:
    # Do not also request auth_client (shared session would log this client in).
    assert client.get("/api/providers/readiness").status_code == 401


def test_readiness_api_authenticated_hides_secrets(
    auth_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("NSFWTRACK_JAVDB_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("NSFWTRACK_JAVDB_SESSION_COOKIE_FILE", raising=False)
    monkeypatch.setattr(
        "app.providers.readiness.default_cookie_store_path",
        lambda key="javdb": tmp_path / f"{key}.cookie",
    )

    r = auth_client.get("/api/providers/readiness")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["application_version"] == "1.7.0"
    assert any(p["provider_key"] == "javdb_metadata" for p in body["providers"])
    assert "fake-secret" not in r.text
    assert "session=" not in r.text
