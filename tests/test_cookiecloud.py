"""CookieCloud control-plane unit tests (no live network)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from app.cookiecloud.client import (
    CookieCloudConfig,
    CookieCloudError,
    CookieCloudImporter,
    cookie_header_from_pairs,
    decrypt_cookiecloud,
    default_cookie_store_path,
    filter_cookies_for_hosts,
    save_cookie_header,
)
from app.providers.javdb.session import load_javdb_session_cookie


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
    salt = b"\x01\x02\x03\x04\x05\x06\x07\x08"
    key, iv = _evp_bytes_to_key(passphrase, salt, 32, 16)
    plain = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    padder = PKCS7(128).padder()
    padded = padder.update(plain) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(b"Salted__" + salt + ciphertext).decode("ascii")


def test_config_rejects_path_and_credentials() -> None:
    with pytest.raises(CookieCloudError):
        CookieCloudConfig(host="https://cc.example/path", uuid="u1").validated_url()
    with pytest.raises(CookieCloudError):
        CookieCloudConfig(host="https://user:pass@cc.example", uuid="u1").validated_url()
    with pytest.raises(CookieCloudError):
        CookieCloudConfig(host="https://cc.example", uuid="bad/uuid").validated_url()
    assert CookieCloudConfig(host="http://127.0.0.1:8088", uuid="abc").validated_url() == (
        "http://127.0.0.1:8088"
    )


def test_decrypt_roundtrip_and_filter() -> None:
    uuid = "test-uuid-1"
    password = "secret-pass"
    cookie_data = {
        "javdb.com": [
            {"name": "_jdb_session", "value": "sess-value", "expirationDate": 9_999_999_999},
            {"name": "theme", "value": "dark", "expirationDate": 9_999_999_999},
            {"name": "expired", "value": "gone", "expirationDate": 1},
        ],
        "other.example": [
            {"name": "x", "value": "y", "expirationDate": 9_999_999_999},
        ],
    }
    encrypted = _encrypt_cookiecloud(
        uuid, password, {"cookie_data": cookie_data}
    )
    plain = decrypt_cookiecloud(uuid, password, encrypted)
    assert "cookie_data" in plain
    pairs = filter_cookies_for_hosts(
        plain["cookie_data"],
        hosts={"javdb.com"},
        cookie_names={"_jdb_session", "theme"},
        now=1_700_000_000,
    )
    assert pairs == {"_jdb_session": "sess-value", "theme": "dark"}
    header = cookie_header_from_pairs(pairs)
    assert "_jdb_session=sess-value" in header
    assert "theme=dark" in header


def test_cookie_filter_rejects_subdomain_scope_and_header_injection() -> None:
    with pytest.raises(CookieCloudError, match="no non-expired"):
        filter_cookies_for_hosts(
            {
                "login.javdb.com": [
                    {"name": "session", "value": "subdomain-only"},
                ],
                "javdb.com": [
                    {"name": "bad", "value": "x; injected=y"},
                ],
            },
            hosts={"javdb.com"},
        )


def test_wrong_password_raises() -> None:
    encrypted = _encrypt_cookiecloud("u", "right", {"cookie_data": {}})
    with pytest.raises(CookieCloudError):
        decrypt_cookiecloud("u", "wrong", encrypted)


def test_save_cookie_header_and_session_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "javdb_metadata.cookie"
    save_cookie_header(path, "a=1; b=2")
    text = path.read_text(encoding="utf-8").strip()
    assert text == "a=1; b=2"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    monkeypatch.delenv("NSFWTRACK_JAVDB_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("NSFWTRACK_JAVDB_SESSION_COOKIE_FILE", raising=False)
    # Point default store path via env file instead of patching package path.
    monkeypatch.setenv("NSFWTRACK_JAVDB_SESSION_COOKIE_FILE", str(path))
    assert load_javdb_session_cookie() == "a=1; b=2"


def test_importer_with_mock_opener(tmp_path: Path) -> None:
    uuid = "import-uuid"
    password = "pw"
    encrypted = _encrypt_cookiecloud(
        uuid,
        password,
        {
            "cookie_data": {
                "javdb.com": [
                    {
                        "name": "_jdb_session",
                        "value": "live-sess",
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

    importer = CookieCloudImporter(
        CookieCloudConfig(host="http://127.0.0.1:9", uuid=uuid),
        opener=_Opener(),
    )
    save_path = tmp_path / "out.cookie"
    header, names = importer.import_cookie_header(
        password,
        hosts={"javdb.com"},
        cookie_names={"_jdb_session"},
        save_path=save_path,
    )
    assert names == ("_jdb_session",)
    assert "live-sess" in header
    assert save_path.is_file()


def test_default_cookie_store_path_under_data() -> None:
    path = default_cookie_store_path("javdb_metadata")
    assert path.name == "javdb_metadata.cookie"
    assert path.parent.name == "cookies"


def test_cookiecloud_api_status_requires_auth(client) -> None:
    # Do not also request auth_client: it logs into the same TestClient session.
    assert client.get("/api/cookiecloud/status").status_code == 401


def test_cookiecloud_api_status_authenticated(auth_client) -> None:
    r = auth_client.get("/api/cookiecloud/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["provider_key"] == "javdb_metadata"
    assert "loadable" in body
    # Never leak cookie values in status body.
    assert "value" not in body
