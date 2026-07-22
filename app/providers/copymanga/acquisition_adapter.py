"""CopyManga chapter page download (allowlisted image hosts only)."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import AsyncIterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from app.acquisition.contracts import AssetDownloadDescriptor, DownloadOpenResult
from app.providers.copymanga.approval import (
    COPYMANGA_IMAGE_HOSTS,
    COPYMANGA_PROVIDER_KEY,
)
from app.source_adapters.contracts import SourceAssetKind

MAX_CHUNK = 64 * 1024
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class CopymangaAcquisitionAdapter:
    provider_key = COPYMANGA_PROVIDER_KEY

    def __init__(
        self,
        *,
        proxy_url: str | None = None,
        static_bodies: dict[str, bytes] | None = None,
        static_lists: dict[str, tuple[AssetDownloadDescriptor, ...]] | None = None,
        url_index: dict[str, str] | None = None,
        approved_hosts: tuple[str, ...] = COPYMANGA_IMAGE_HOSTS,
    ) -> None:
        self._proxy = proxy_url.strip() if proxy_url else None
        self._static_bodies = static_bodies or {}
        self._static_lists = static_lists or {}
        self._url_index = url_index or {}
        self._allowed = {h.lower() for h in approved_hosts}
        self._known: dict[str, AssetDownloadDescriptor] = {}

    async def list_assets(self, external_id: str) -> tuple[AssetDownloadDescriptor, ...]:
        if external_id in self._static_lists:
            items = self._static_lists[external_id]
            for item in items:
                self._known[f"{external_id}:{item.asset_id}"] = item
            return items
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
        if asset_id in self._static_bodies:
            full = self._static_bodies[asset_id]
            body = full[offset:]

            async def chunks() -> AsyncIterator[bytes]:
                view = memoryview(body)
                for start in range(0, len(view), MAX_CHUNK):
                    yield bytes(view[start : start + MAX_CHUNK])

            return DownloadOpenResult(
                chunks=chunks(),
                status_code=206 if offset else 200,
                mime_type="image/jpeg",
                content_length=len(body),
                range_start=offset if offset else None,
                range_end=(offset + len(body) - 1) if body else None,
                range_total=len(full),
            )
        key = f"{external_id}:{asset_id}"
        url = self._url_index.get(key) or self._url_index.get(asset_id)
        if not url:
            raise ValueError("asset url not bound")
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.hostname.lower() not in self._allowed
        ):
            raise ValueError("asset host not approved")
        body = await asyncio.to_thread(self._fetch_bytes, url, offset, timeout_seconds)

        async def live_chunks() -> AsyncIterator[bytes]:
            view = memoryview(body)
            for start in range(0, len(view), MAX_CHUNK):
                yield bytes(view[start : start + MAX_CHUNK])

        return DownloadOpenResult(
            chunks=live_chunks(),
            status_code=206 if offset else 200,
            mime_type="image/jpeg",
            content_length=len(body),
            range_start=offset if offset else None,
            range_end=(offset + len(body) - 1) if body else None,
            range_total=None,
        )

    def _fetch_bytes(self, url: str, offset: int, timeout: int) -> bytes:
        headers = {"User-Agent": DEFAULT_UA, "Accept": "image/*,*/*"}
        if offset > 0:
            headers["Range"] = f"bytes={offset}-"
        request = Request(url, headers=headers, method="GET")
        handlers: list[Any] = [HTTPSHandler(context=ssl.create_default_context())]
        if self._proxy:
            handlers.insert(
                0, ProxyHandler({"http": self._proxy, "https": self._proxy})
            )
        opener = build_opener(*handlers)
        try:
            with opener.open(request, timeout=timeout) as response:
                return response.read(20 * 1024 * 1024)
        except (HTTPError, URLError, TimeoutError, OSError) as exp:
            raise ValueError("page image fetch failed") from exp
