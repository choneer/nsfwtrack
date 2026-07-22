"""Local comic page DOWNLOAD from fixture directory (phase D)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from app.acquisition.contracts import AssetDownloadDescriptor, DownloadOpenResult
from app.providers.comic.approval import COMIC_PROVIDER_KEY
from app.source_adapters.contracts import SourceAssetKind

MAX_CHUNK = 64 * 1024


class ComicFixtureAcquisitionAdapter:
    provider_key = COMIC_PROVIDER_KEY

    def __init__(self, fixture_root: Path) -> None:
        self._root = fixture_root
        self._known: dict[str, Path] = {}

    async def list_assets(self, external_id: str) -> tuple[AssetDownloadDescriptor, ...]:
        folder = self._root / external_id.strip()
        if not folder.is_dir() or ".." in external_id:
            return ()
        items: list[AssetDownloadDescriptor] = []
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            if path.suffix.lower() == ".webp":
                mime = "image/webp"
            desc = AssetDownloadDescriptor(
                provider_key=COMIC_PROVIDER_KEY,
                external_id=external_id.strip(),
                asset_id=path.name,
                kind=SourceAssetKind.MEDIA,
                display_name=path.name,
                suggested_filename=path.name,
                mime_type=mime,
                expected_bytes=path.stat().st_size,
                expected_sha256=None,
                requires_auth=False,
                resume_supported=True,
            )
            items.append(desc)
            self._known[f"{external_id.strip()}:{path.name}"] = path
        return tuple(items)

    async def open_asset(
        self,
        external_id: str,
        asset_id: str,
        *,
        offset: int,
        timeout_seconds: int,
    ) -> DownloadOpenResult:
        del timeout_seconds  # local open
        key = f"{external_id.strip()}:{asset_id}"
        path = self._known.get(key)
        if path is None:
            # try resolve once
            candidate = self._root / external_id.strip() / asset_id
            if candidate.is_file() and ".." not in asset_id:
                path = candidate
                self._known[key] = path
        if path is None or not path.is_file():
            raise ValueError("asset not found")
        data = path.read_bytes()[offset:]
        mime = "image/jpeg"
        if path.suffix.lower() == ".png":
            mime = "image/png"
        elif path.suffix.lower() == ".webp":
            mime = "image/webp"

        async def chunks() -> AsyncIterator[bytes]:
            view = memoryview(data)
            for start in range(0, len(view), MAX_CHUNK):
                yield bytes(view[start : start + MAX_CHUNK])

        total = path.stat().st_size
        return DownloadOpenResult(
            chunks=chunks(),
            status_code=206 if offset else 200,
            mime_type=mime,
            content_length=len(data),
            range_start=offset if offset else None,
            range_end=(offset + len(data) - 1) if data else None,
            range_total=total,
        )
