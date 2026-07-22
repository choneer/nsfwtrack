"""Bounded CookieCloud client: GET /get/{uuid} + OpenSSL AES decrypt.

Upstream: https://github.com/easychen/CookieCloud

- HTTP or HTTPS origin only (LAN self-host often HTTP)
- fixed path /get/{uuid}
- no redirects, size/timeout caps
- decrypt in memory; optional write of filtered Cookie header to local file
- never logs cookie values or passwords
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

MAX_ENVELOPE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT = 20.0


class CookieCloudError(RuntimeError):
    """User-facing CookieCloud failure (no secrets)."""


@dataclass(frozen=True, slots=True)
class CookieCloudConfig:
    host: str
    uuid: str

    def validated_url(self) -> str:
        raw = self.host.rstrip("/")
        parsed = urlparse(raw)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise CookieCloudError(
                "CookieCloud host must be an HTTP or HTTPS origin without credentials, query, or fragment"
            )
        if parsed.path not in {"", "/"}:
            raise CookieCloudError(
                "CookieCloud host must be an origin only (no path); /get/{uuid} is appended by the client"
            )
        if not self.uuid or "/" in self.uuid or any(char.isspace() for char in self.uuid):
            raise CookieCloudError("CookieCloud uuid is invalid")
        return raw


def _evp_bytes_to_key(
    password: bytes, salt: bytes, key_length: int, iv_length: int
) -> tuple[bytes, bytes]:
    output = b""
    previous = b""
    while len(output) < key_length + iv_length:
        previous = hashlib.md5(previous + password + salt).digest()
        output += previous
    return output[:key_length], output[key_length : key_length + iv_length]


def decrypt_cookiecloud(uuid: str, password: str, encrypted: str) -> dict[str, Any]:
    """Decrypt CookieCloud CryptoJS/OpenSSL AES-CBC payload (memory only)."""

    if not uuid or not password or not encrypted:
        raise CookieCloudError("CookieCloud decryption inputs are incomplete")
    try:
        raw = base64.b64decode(encrypted, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise CookieCloudError("CookieCloud encrypted payload is not valid base64") from exc
    if len(raw) < 32 or raw[:8] != b"Salted__":
        raise CookieCloudError("CookieCloud payload has an invalid OpenSSL salt header")
    salt = raw[8:16]
    ciphertext = raw[16:]
    if len(ciphertext) == 0 or len(ciphertext) % 16:
        raise CookieCloudError("CookieCloud ciphertext is not block aligned")
    passphrase = (
        hashlib.md5((uuid + "-" + password).encode("utf-8")).hexdigest()[:16].encode("ascii")
    )
    key, iv = _evp_bytes_to_key(passphrase, salt, 32, 16)
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:
        raise CookieCloudError(
            "cryptography package is required for CookieCloud decrypt"
        ) from exc
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    if not padded:
        raise CookieCloudError("CookieCloud plaintext is empty")
    pad = padded[-1]
    if pad < 1 or pad > 16 or padded[-pad:] != bytes([pad]) * pad:
        raise CookieCloudError(
            "CookieCloud password is incorrect or payload padding is invalid"
        )
    try:
        parsed = json.loads(padded[:-pad].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CookieCloudError("CookieCloud plaintext is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise CookieCloudError("CookieCloud plaintext root must be an object")
    return parsed


def filter_cookies_for_hosts(
    cookie_data: dict[str, Any],
    *,
    hosts: set[str],
    cookie_names: set[str] | None = None,
    now: float | None = None,
) -> dict[str, str]:
    """Select non-expired cookies for approved hosts (and optional name allowlist)."""

    if not isinstance(cookie_data, dict):
        raise CookieCloudError("cookie_data must be an object")
    allowed_hosts = {h.lower().lstrip(".") for h in hosts if h}
    if not allowed_hosts:
        raise CookieCloudError("at least one host is required for cookie filter")
    allowed_names = {n for n in cookie_names} if cookie_names is not None else None
    ts = time.time() if now is None else now
    pairs: dict[str, str] = {}
    for raw_domain, raw_cookies in cookie_data.items():
        domain = str(raw_domain).lstrip(".").lower()
        matched = any(
            domain == host or domain.endswith("." + host) or host.endswith("." + domain)
            for host in allowed_hosts
        )
        if not matched or not isinstance(raw_cookies, list):
            continue
        for raw_cookie in raw_cookies:
            if not isinstance(raw_cookie, dict):
                continue
            name = raw_cookie.get("name")
            value = raw_cookie.get("value")
            if not isinstance(name, str) or not isinstance(value, str) or not value:
                continue
            expiry = raw_cookie.get("expirationDate", raw_cookie.get("expires"))
            if isinstance(expiry, (int, float)) and expiry > 0 and expiry <= ts:
                continue
            if allowed_names is not None and name not in allowed_names:
                continue
            pairs[name] = value
    if not pairs:
        raise CookieCloudError("no non-expired matching cookies for approved hosts")
    return pairs


def cookie_header_from_pairs(pairs: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in sorted(pairs.items()))


def save_cookie_header(path: str | Path, header: str) -> Path:
    """Write Cookie header to a local file (mode 0o600 when supported)."""

    if not header or not header.strip():
        raise CookieCloudError("cookie header is empty")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in header):
        raise CookieCloudError("cookie header contains control characters")
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(header.strip() + "\n", encoding="utf-8")
    try:
        os.chmod(file_path, 0o600)
    except OSError:
        pass
    return file_path


def default_cookie_store_path(provider_key: str = "javdb") -> Path:
    root = Path(__file__).resolve().parents[2]
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in provider_key)
    return root / "data" / "cookies" / f"{safe}.cookie"


class CookieCloudImporter:
    """Fetch, decrypt, filter, and optionally persist Cookie header."""

    def __init__(
        self,
        config: CookieCloudConfig,
        *,
        proxy: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        opener: Any | None = None,
    ) -> None:
        self.config = config
        self.proxy = proxy.strip() if proxy else None
        self.timeout = timeout
        self._opener = opener

    def fetch_envelope(self) -> dict[str, Any]:
        base = self.config.validated_url()
        url = urljoin(base + "/", "get/" + self.config.uuid)
        request = Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "nsfwtrack-cookiecloud/1.5"},
            method="GET",
        )
        handlers: list[Any] = []
        if urlparse(base).scheme == "https":
            handlers.append(HTTPSHandler(context=ssl.create_default_context()))
        if self.proxy:
            handlers.insert(0, ProxyHandler({"http": self.proxy, "https": self.proxy}))
        opener = self._opener or build_opener(*handlers)
        try:
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_ENVELOPE_BYTES + 1)
                status = getattr(response, "status", 200)
                if status >= 400:
                    raise CookieCloudError(f"CookieCloud returned HTTP {status}")
                if len(raw) > MAX_ENVELOPE_BYTES:
                    raise CookieCloudError("CookieCloud response exceeds import limit")
                envelope = json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            raise CookieCloudError(f"CookieCloud returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeError) as exc:
            raise CookieCloudError("CookieCloud request failed") from exc
        if not isinstance(envelope, dict) or not isinstance(envelope.get("encrypted"), str):
            raise CookieCloudError("CookieCloud response has no encrypted payload")
        return envelope

    def import_cookie_header(
        self,
        password: str,
        *,
        hosts: set[str],
        cookie_names: set[str] | None = None,
        save_path: str | Path | None = None,
    ) -> tuple[str, tuple[str, ...]]:
        """Return (cookie_header, matched_names). Optionally save header to disk."""

        if not password:
            raise CookieCloudError("CookieCloud password is required for local decryption")
        envelope = self.fetch_envelope()
        data = decrypt_cookiecloud(self.config.uuid, password, str(envelope["encrypted"]))
        cookie_data = data.get("cookie_data")
        if not isinstance(cookie_data, dict):
            raise CookieCloudError("CookieCloud payload has no cookie_data object")
        pairs = filter_cookies_for_hosts(
            cookie_data, hosts=hosts, cookie_names=cookie_names
        )
        header = cookie_header_from_pairs(pairs)
        names = tuple(sorted(pairs))
        if save_path is not None:
            save_cookie_header(save_path, header)
        return header, names
