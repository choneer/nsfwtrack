"""Allowlisted HTML fetch for JavDB host only (stdlib, optional proxy).

Does not use the production Outbound JSON client. Only ``javdb.com`` HTTPS
paths under approved templates are requested. Cookie is never logged.
"""

from __future__ import annotations

import asyncio
import ssl
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from app.providers.javdb.production import JAVDB_PRODUCTION_HOST

MAX_HTML_BYTES = 1024 * 1024
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class HtmlFetcher(Protocol):
    async def get_html(self, path: str, *, query: dict[str, str] | None = None) -> str:
        ...


class JavdbHtmlFetcher:
    """Fetch HTML from javdb.com with operator cookie and optional HTTP proxy."""

    def __init__(
        self,
        *,
        cookie: str,
        proxy_url: str | None = None,
        timeout: float = 20.0,
        host: str = JAVDB_PRODUCTION_HOST,
    ) -> None:
        if not cookie or not cookie.strip():
            raise ValueError("cookie is required")
        self._cookie = cookie.strip()
        self._proxy = proxy_url.strip() if proxy_url else None
        self._timeout = timeout
        self._host = host.casefold()

    async def get_html(self, path: str, *, query: dict[str, str] | None = None) -> str:
        return await asyncio.to_thread(self._get_html_sync, path, query)

    def _get_html_sync(self, path: str, query: dict[str, str] | None) -> str:
        if not path.startswith("/"):
            raise ValueError("path must be absolute on host")
        if ".." in path or "\\" in path:
            raise ValueError("path is unsafe")
        # Only allow known path shapes
        if not (
            path == "/search"
            or path.startswith("/v/")
        ):
            raise ValueError("path is not on the approved allowlist")
        suffix = ""
        if query:
            suffix = "?" + urlencode(
                {k: v for k, v in query.items() if v is not None},
                doseq=False,
                safe="",
            )
        # Encode path segments except slashes
        parts = path.split("/")
        encoded = "/".join(quote(part, safe="") if part else "" for part in parts)
        url = f"https://{self._host}{encoded}{suffix}"
        parsed = urlparse(url)
        if parsed.hostname != self._host or parsed.scheme != "https":
            raise ValueError("url host mismatch")
        request = Request(
            url,
            headers={
                "User-Agent": DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cookie": self._cookie,
            },
            method="GET",
        )
        handlers: list[object] = [HTTPSHandler(context=ssl.create_default_context())]
        if self._proxy:
            handlers.insert(
                0,
                ProxyHandler({"http": self._proxy, "https": self._proxy}),
            )
        opener = build_opener(*handlers)
        try:
            with opener.open(request, timeout=self._timeout) as response:
                raw = response.read(MAX_HTML_BYTES + 1)
                if len(raw) > MAX_HTML_BYTES:
                    raise ValueError("html response too large")
                status = getattr(response, "status", 200)
                if status >= 400:
                    raise ValueError(f"http {status}")
                return raw.decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise ValueError(f"http {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ValueError("transport failed") from exc


class StaticHtmlFetcher:
    """Test double: map path+query -> HTML body."""

    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages

    async def get_html(self, path: str, *, query: dict[str, str] | None = None) -> str:
        key = path
        if query:
            key = path + "?" + urlencode(sorted(query.items()))
        if key not in self._pages and path not in self._pages:
            raise ValueError("fixture page missing")
        return self._pages.get(key) or self._pages[path]
