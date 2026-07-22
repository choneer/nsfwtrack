"""CookieCloud operator UI + API (authenticated, no secrets)."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest


def _evp_bytes_to_key(
    password: bytes, salt: bytes, key_length: int, iv_length: int
) -> tuple[bytes, bytes]:
    output = b""
    previous = b""
    while len(output) < key_length + iv_length:
        previous = hashlib.md5(previous + password + salt).digest()
        output += previous
    return output[:key_length], output[key_length : key_length + iv_length]


def _encrypt_cookiecloud(uuid: str, password: str, payload: dict[str, Any]) -> str:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.padding import PKCS7

    passphrase = (
        hashlib.md5((uuid + "-" + password).encode("utf-8")).hexdigest()[:16].encode("ascii")
    )
    salt = b"\x11\x22\x33\x44\x55\x66\x77\x88"
    key, iv = _evp_bytes_to_key(passphrase, salt, 32, 16)
    plain = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    padder = PKCS7(128).padder()
    padded = padder.update(plain) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(b"Salted__" + salt + ciphertext).decode("ascii")


def test_cookiecloud_page_requires_auth(client) -> None:
    r = client.get("/cookiecloud", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location") == "/login"


def test_cookiecloud_page_authenticated_shows_readiness_not_secrets(
    auth_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("NSFWTRACK_JAVDB_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("NSFWTRACK_JAVDB_SESSION_COOKIE_FILE", raising=False)
    monkeypatch.setattr(
        "app.providers.readiness.default_cookie_store_path",
        lambda key="javdb": tmp_path / f"{key}.cookie",
    )
    monkeypatch.setattr(
        "app.cookiecloud.client.default_cookie_store_path",
        lambda key="javdb": tmp_path / f"{key}.cookie",
    )
    r = auth_client.get("/cookiecloud")
    assert r.status_code == 200
    text = r.text
    assert "cookiecloud" in text.lower() or "CookieCloud" in text
    assert "javdb_metadata" in text
    assert "fixture_fallback" in text or "live_capable" in text
    assert 'name="password"' in text
    assert 'action="/cookiecloud/import"' in text
    # Password field must be empty; no cookie values
    assert "value=\"secret" not in text
    assert "session=abc" not in text
    assert "fake-secret" not in text


def test_cookiecloud_api_import_with_mock_opener(
    auth_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    uuid = "ui-uuid"
    password = "ui-pass"
    encrypted = _encrypt_cookiecloud(
        uuid,
        password,
        {
            "cookie_data": {
                "javdb.com": [
                    {
                        "name": "_jdb_session",
                        "value": "super-secret-session-token",
                        "expirationDate": 9_999_999_999,
                    }
                ]
            }
        },
    )
    envelope = json.dumps({"encrypted": encrypted}).encode("utf-8")

    class _Resp:
        status = 200

        def read(self, n: int) -> bytes:
            return envelope[:n]

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class _Opener:
        def open(self, request: object, timeout: float = 0) -> _Resp:
            return _Resp()

    save_dir = tmp_path / "cookies"
    save_dir.mkdir()
    monkeypatch.setattr(
        "app.cookiecloud.client.default_cookie_store_path",
        lambda key="javdb": save_dir / f"{key}.cookie",
    )
    monkeypatch.setattr(
        "app.cookiecloud.router.default_cookie_store_path",
        lambda key="javdb": save_dir / f"{key}.cookie",
    )

    from app.cookiecloud.client import CookieCloudImporter

    real_init = CookieCloudImporter.__init__

    def _init(self, config, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["opener"] = _Opener()
        real_init(self, config, **kwargs)

    monkeypatch.setattr(CookieCloudImporter, "__init__", _init)

    r = auth_client.post(
        "/api/cookiecloud/import",
        json={
            "host": "http://127.0.0.1:9",
            "uuid": uuid,
            "password": password,
            "provider_key": "javdb_metadata",
            "save": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["matched_count"] >= 1
    assert "_jdb_session" in body["matched_cookie_names"]
    assert "super-secret-session-token" not in r.text
    assert "password" not in body
    saved = save_dir / "javdb_metadata.cookie"
    assert saved.is_file()
    # File may contain the value (local drop zone) but API must not echo it
    assert "super-secret-session-token" in saved.read_text(encoding="utf-8")
