"""Offline comic fixture adapter (async VideoMetadataAdapter shape)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.providers.comic.approval import COMIC_PROVIDER_KEY
from app.source_adapters.contracts import (
    ProviderAdapterError,
    ProviderError,
    ProviderErrorCode,
    ProviderOperation,
)
from app.video_metadata.contracts import (
    VideoAsset,
    VideoAssetKind,
    VideoConfidence,
    VideoDetail,
    VideoIdentifier,
    VideoMetadataProvenance,
    VideoProvenanceOperation,
    VideoSearchPage,
    VideoSearchResult,
)


class ComicFixtureVideoMetadataAdapter:
    """Maps local comic fixture directory into metadata + page assets."""

    key = COMIC_PROVIDER_KEY

    def __init__(self, fixture_root: Path) -> None:
        self._root = fixture_root

    async def search(self, query: str, *, page: int, page_size: int) -> VideoSearchPage:
        if not query.strip() or page < 1 or page_size < 1:
            raise _error(ProviderOperation.SEARCH)
        comics = _list_comics(self._root)
        q = query.strip().casefold()
        if q not in {"*", "__all__"}:
            comics = [c for c in comics if q in c.casefold()]
        start = (page - 1) * page_size
        window = comics[start : start + page_size]
        observed = datetime.now(tz=UTC)
        items = tuple(
            VideoSearchResult(
                identifier=VideoIdentifier(
                    provider_key=COMIC_PROVIDER_KEY,
                    external_id=comic_id,
                    catalog_number=None,
                    canonical_url=None,
                ),
                title=comic_id,
                provenance=(
                    VideoMetadataProvenance(
                        provider_key=COMIC_PROVIDER_KEY,
                        external_id=comic_id,
                        operation=VideoProvenanceOperation.SEARCH,
                        field_name="title",
                        observed_at=observed,
                        confidence=VideoConfidence.MEDIUM,
                    ),
                ),
            )
            for comic_id in window
        )
        return VideoSearchPage(
            items=items,
            page=page,
            page_size=page_size,
            has_next=start + page_size < len(comics),
            total=len(comics),
            query=query,
        )

    async def detail(self, external_id: str) -> VideoDetail:
        comic_id = _require_id(external_id, ProviderOperation.DETAIL)
        if comic_id not in _list_comics(self._root):
            raise _error(ProviderOperation.DETAIL)
        observed = datetime.now(tz=UTC)
        return VideoDetail(
            identifier=VideoIdentifier(
                provider_key=COMIC_PROVIDER_KEY,
                external_id=comic_id,
            ),
            title=comic_id,
            provenance=(
                VideoMetadataProvenance(
                    provider_key=COMIC_PROVIDER_KEY,
                    external_id=comic_id,
                    operation=VideoProvenanceOperation.DETAIL,
                    field_name="title",
                    observed_at=observed,
                    confidence=VideoConfidence.HIGH,
                ),
            ),
        )

    async def asset_list(self, external_id: str) -> tuple[VideoAsset, ...]:
        comic_id = _require_id(external_id, ProviderOperation.ASSET_LIST)
        pages = _list_pages(self._root, comic_id)
        return tuple(
            VideoAsset(
                provider_key=COMIC_PROVIDER_KEY,
                asset_id=page_id,
                kind=VideoAssetKind.PREVIEW_IMAGE,
                display_name=page_id,
                mime_type="image/jpeg",
                requires_auth=False,
                downloadable=False,
            )
            for page_id in pages
        )


def _list_comics(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


def _list_pages(root: Path, comic_id: str) -> list[str]:
    folder = root / comic_id
    if not folder.is_dir():
        return []
    return sorted(
        path.name
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )


def _require_id(external_id: str, operation: ProviderOperation) -> str:
    if not isinstance(external_id, str) or not external_id.strip():
        raise _error(operation)
    value = external_id.strip()
    if ".." in value or "/" in value or "\\" in value:
        raise _error(operation)
    return value


def _error(operation: ProviderOperation) -> ProviderAdapterError:
    return ProviderAdapterError(
        ProviderError(
            code=ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            provider_key=COMIC_PROVIDER_KEY,
            operation=operation,
        )
    )
