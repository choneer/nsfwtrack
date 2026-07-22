"""Optional local DOWNLOAD for JavDB covers/previews (phase C acquisition).

Streams only allowlisted HTTPS assets on ``javdb.com`` using the operator
session cookie. Locators are never accepted from callers — only opaque asset
ids previously listed by this adapter.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request

from app.acquisition.contracts import (
    AssetDownloadDescriptor,
    DownloadOpenResult,
)
from app.providers.javdb.production import (
    JAVDB_PRODUCTION_HOST,
    JAVDB_PRODUCTION_PROVIDER_KEY,
)
from app.services.urllib_safety import (
    build_no_redirect_opener,
    response_matches_request,
)
from app.source_adapters.contracts import SourceAssetKind

_ASSET_ID_RE = re.compile(r"^[A-Za-z0-9._~-]{1,200}$")
MAX_CHUNK = 64 * 1024
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class JavDBAcquisitionAdapter:
    """AcquisitionAdapter: list_assets + open_asset for optional local download."""

    provider_key = JAVDB_PRODUCTION_PROVIDER_KEY

    def __init__(
        self,
        *,
        cookie: str,
        proxy_url: str | None = None,
        host: str = JAVDB_PRODUCTION_HOST,
        # test inject: map asset_id -> bytes
        static_bodies: dict[str, bytes] | None = None,
        # test inject: map external_id -> descriptors
        static_lists: dict[str, tuple[AssetDownloadDescriptor, ...]] | None = None,
    ) -> None:
        if not cookie.strip() and static_bodies is None:
            raise ValueError("cookie is required for live acquisition")
        self._cookie = cookie.strip()
        self._proxy = proxy_url.strip() if proxy_url else None
        self._host = host.casefold()
        self._static_bodies = static_bodies
        self._static_lists = static_lists or {}
        self._known: dict[str, AssetDownloadDescriptor] = {}

    async def list_assets(self, external_id: str) -> tuple[AssetDownloadDescriptor, ...]:
        if not isinstance(external_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", external_id.strip()
        ):
            return ()
        external_id = external_id.strip()
        if external_id in self._static_lists:
            items = self._static_lists[external_id]
            for item in items:
                self._known[item.asset_id] = item
            return items
        # Live path: cover path convention only (opaque id = filename under /covers/)
        # Real sites vary; without HTML parse here we expose no speculative URLs.
        # Callers should use metadata ASSET_LIST for display links; download is
        # enabled only when static test lists or future HTML-bound locators exist.
        return ()

    async def open_asset(
        self,
        external_id: str,
        asset_id: str,
        *,
        offset: int,
        timeout_seconds: int,
    ) -> DownloadOpenResult:
        if offset < 0:
            raise ValueError("offset invalid")
        if not _ASSET_ID_RE.fullmatch(asset_id or ""):
            raise ValueError("asset_id invalid")
        if self._static_bodies is not None and asset_id in self._static_bodies:
            body = self._static_bodies[asset_id]
            data = body[offset:]

            async def chunks() -> AsyncIterator[bytes]:
                view = memoryview(data)
                for start in range(0, len(view), MAX_CHUNK):
                    yield bytes(view[start : start + MAX_CHUNK])

            return DownloadOpenResult(
                chunks=chunks(),
                status_code=206 if offset else 200,
                mime_type="image/jpeg",
                content_length=len(data),
                range_start=offset if offset else None,
                range_end=(offset + len(data) - 1) if data else None,
                range_total=len(body),
            )

        # Live: only fetch if previously listed (bound) or known static
        if asset_id not in self._known and asset_id not in (self._static_bodies or {}):
            raise ValueError("asset not listed")
        url = f"https://{self._host}/covers/{quote(asset_id, safe='')}"
        body = await asyncio.to_thread(
            self._fetch_bytes, url, offset, timeout_seconds
        )

        async def live_chunks() -> AsyncIterator[bytes]:
            view = memoryview(body)
            for start in range(0, len(view), MAX_CHUNK):
                yield bytes(view[start : start + MAX_CHUNK])

        return DownloadOpenResult(
            chunks=live_chunks(),
            status_code=206 if offset else 200,
            mime_type="application/octet-stream",
            content_length=len(body),
            range_start=offset if offset else None,
            range_end=(offset + len(body) - 1) if body else None,
            range_total=None,
        )

    def _fetch_bytes(self, url: str, offset: int, timeout: int) -> bytes:
        headers = {
            "User-Agent": DEFAULT_UA,
            "Cookie": self._cookie,
            "Accept": "*/*",
        }
        if offset > 0:
            headers["Range"] = f"bytes={offset}-"
        request = Request(url, headers=headers, method="GET")
        try:
            opener = build_no_redirect_opener(proxy=self._proxy)
        except ValueError as exc:
            raise ValueError("proxy configuration invalid") from exc
        try:
            with opener.open(request, timeout=timeout) as response:
                if not response_matches_request(response, url):
                    raise ValueError("redirect blocked")
                body = response.read(50 * 1024 * 1024 + 1)
                if len(body) > 50 * 1024 * 1024:
                    raise ValueError("asset response too large")
                return body
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ValueError("asset fetch failed") from exc


def bind_listed_assets(
    adapter: JavDBAcquisitionAdapter,
    items: tuple[AssetDownloadDescriptor, ...],
) -> None:
    """Test/helper: mark descriptors as listable for open_asset."""

    for item in items:
        adapter._known[item.asset_id] = item  # noqa: SLF001
