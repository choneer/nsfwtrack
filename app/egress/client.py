"""stdlib HTTP fetch helpers with optional HTTP(S) proxy.

Uses urllib only so egress probes stay independent of Provider outbound_http
allowlists and httpx2 pinning.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request

from app.services.urllib_safety import (
    build_no_redirect_opener,
    response_matches_request,
)


DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MAX_BODY_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class FetchResult:
    ok: bool
    status_code: int | None
    body: str
    latency_ms: int
    error: str | None = None


def proxy_host_for_log(proxy_url: str | None) -> str | None:
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url.strip())
    if not parsed.hostname:
        return proxy_url.split("@")[-1] if "@" in proxy_url else proxy_url
    host = parsed.hostname
    port = parsed.port
    return f"{host}:{port}" if port else host


def fetch_text(
    url: str,
    *,
    proxy: str | None = None,
    timeout: float = 8.0,
    headers: dict[str, str] | None = None,
    accept: str = "application/json,text/plain,*/*",
) -> FetchResult:
    """GET ``url`` optionally through an HTTP/HTTPS proxy; return text body."""

    started = time.perf_counter()
    req_headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": accept,
    }
    if headers:
        req_headers.update(headers)
    request = Request(url, headers=req_headers, method="GET")
    try:
        opener = build_no_redirect_opener(proxy=proxy)
    except ValueError:
        return FetchResult(
            ok=False,
            status_code=None,
            body="",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error="invalid explicit proxy",
        )
    try:
        with opener.open(request, timeout=timeout) as response:
            if not response_matches_request(response, url):
                return FetchResult(
                    ok=False,
                    status_code=getattr(response, "status", None),
                    body="",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error="redirect blocked",
                )
            raw = response.read(MAX_BODY_BYTES + 1)
            if len(raw) > MAX_BODY_BYTES:
                latency = int((time.perf_counter() - started) * 1000)
                return FetchResult(
                    ok=False,
                    status_code=getattr(response, "status", None),
                    body="",
                    latency_ms=latency,
                    error="response too large",
                )
            body = raw.decode("utf-8", errors="replace")
            status_code = getattr(response, "status", 200)
            latency = int((time.perf_counter() - started) * 1000)
            if status_code >= 400:
                return FetchResult(
                    ok=False,
                    status_code=status_code,
                    body=body,
                    latency_ms=latency,
                    error=f"HTTP {status_code}",
                )
            return FetchResult(
                ok=True,
                status_code=status_code,
                body=body,
                latency_ms=latency,
            )
    except HTTPError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        try:
            body = exc.read(MAX_BODY_BYTES).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body = ""
        return FetchResult(
            ok=False,
            status_code=exc.code,
            body=body,
            latency_ms=latency,
            error=f"HTTP {exc.code}",
        )
    except (URLError, TimeoutError, OSError, ValueError):
        latency = int((time.perf_counter() - started) * 1000)
        return FetchResult(
            ok=False,
            status_code=None,
            body="",
            latency_ms=latency,
            error="transport failed",
        )


def fetch_json(
    url: str,
    *,
    proxy: str | None = None,
    timeout: float = 8.0,
    headers: dict[str, str] | None = None,
) -> tuple[FetchResult, Any | None]:
    result = fetch_text(url, proxy=proxy, timeout=timeout, headers=headers)
    if not result.ok:
        return result, None
    text = result.body.strip()
    if not text:
        return result, None
    try:
        return result, json.loads(text)
    except json.JSONDecodeError:
        return (
            FetchResult(
                ok=False,
                status_code=result.status_code,
                body=result.body,
                latency_ms=result.latency_ms,
                error="invalid json",
            ),
            None,
        )
