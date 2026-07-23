"""Async CopyManga-style comic adapter with injectable JSON fetch."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote, urlencode

from app.providers.copymanga.approval import COPYMANGA_HOST, COPYMANGA_PROVIDER_KEY
from app.providers.copymanga.parse import (
    CopymangaParseError,
    parse_chapters_payload,
    parse_detail_payload,
    parse_search_payload,
)
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
    VideoPerson,
    VideoPersonRole,
    VideoProvenanceOperation,
    VideoSearchPage,
    VideoSearchResult,
)


class JsonFetcher(Protocol):
    async def get_json(
        self, path: str, *, query: dict[str, str] | None = None
    ) -> dict[str, Any]:
        ...


class StaticJsonFetcher:
    def __init__(self, pages: dict[str, dict[str, Any]]) -> None:
        self._pages = pages

    async def get_json(
        self, path: str, *, query: dict[str, str] | None = None
    ) -> dict[str, Any]:
        key = path
        if query:
            key = path + "?" + urlencode(sorted(query.items()))
        if key in self._pages:
            return self._pages[key]
        if path in self._pages:
            return self._pages[path]
        raise CopymangaParseError("fixture page missing")


class CopymangaVideoMetadataAdapter:
    """Maps comic JSON into Video* DTOs for Search service compatibility."""

    key = COPYMANGA_PROVIDER_KEY

    def __init__(self, fetcher: JsonFetcher) -> None:
        self._fetcher = fetcher

    async def search(self, query: str, *, page: int, page_size: int) -> VideoSearchPage:
        if not query.strip() or page < 1 or page_size < 1:
            raise _error(ProviderOperation.SEARCH)
        try:
            payload = await self._fetcher.get_json(
                "/api/v3/search/comic",
                query={"q": query.strip(), "offset": str((page - 1) * page_size), "limit": str(page_size)},
            )
            cards = parse_search_payload(payload)
        except (CopymangaParseError, TypeError, ValueError) as exc:
            raise _error(ProviderOperation.SEARCH) from exc
        observed = datetime.now(tz=UTC)
        items = tuple(
            VideoSearchResult(
                identifier=VideoIdentifier(
                    provider_key=COPYMANGA_PROVIDER_KEY,
                    external_id=card["external_id"],
                ),
                title=card["title"],
                provenance=(
                    VideoMetadataProvenance(
                        provider_key=COPYMANGA_PROVIDER_KEY,
                        external_id=card["external_id"],
                        operation=VideoProvenanceOperation.SEARCH,
                        field_name="title",
                        observed_at=observed,
                        confidence=VideoConfidence.MEDIUM,
                    ),
                ),
            )
            for card in cards
        )
        return VideoSearchPage(
            items=items,
            page=page,
            page_size=page_size,
            has_next=len(cards) >= page_size,
            total=len(cards),
            query=query,
        )

    async def detail(self, external_id: str) -> VideoDetail:
        if not external_id or not external_id.strip():
            raise _error(ProviderOperation.DETAIL)
        cid = external_id.strip()
        try:
            payload = await self._fetcher.get_json(f"/api/v3/comic2/{cid}")
            raw = parse_detail_payload(payload, external_id=cid)
        except (CopymangaParseError, TypeError, ValueError) as exc:
            raise _error(ProviderOperation.DETAIL) from exc
        observed = datetime.now(tz=UTC)
        performers = ()
        author = raw.get("author")
        if isinstance(author, list):
            names = [
                a.get("name") if isinstance(a, dict) else a
                for a in author
            ]
            performers = tuple(
                VideoPerson(
                    provider_key=COPYMANGA_PROVIDER_KEY,
                    external_id=f"author:{name}",
                    display_name=str(name),
                    role=VideoPersonRole.PERFORMER,
                )
                for name in names
                if name
            )
        elif isinstance(author, str) and author.strip():
            performers = (
                VideoPerson(
                    provider_key=COPYMANGA_PROVIDER_KEY,
                    external_id=f"author:{author}",
                    display_name=author,
                    role=VideoPersonRole.PERFORMER,
                ),
            )
        return VideoDetail(
        identifier=VideoIdentifier(
            provider_key=COPYMANGA_PROVIDER_KEY,
            external_id=str(raw["external_id"]),
            canonical_url=(
                f"https://{COPYMANGA_HOST}/api/v3/comic2/"
                + quote(str(raw["external_id"]), safe="")
            ),
        ),
            title=str(raw["title"]),
            summary=raw.get("summary"),
            performers=performers,
            provenance=(
                VideoMetadataProvenance(
                    provider_key=COPYMANGA_PROVIDER_KEY,
                    external_id=str(raw["external_id"]),
                    operation=VideoProvenanceOperation.DETAIL,
                    field_name="title",
                    observed_at=observed,
                    confidence=VideoConfidence.HIGH,
                ),
            ),
        )

    async def asset_list(self, external_id: str) -> tuple[VideoAsset, ...]:
        if not external_id or not external_id.strip():
            raise _error(ProviderOperation.ASSET_LIST)
        cid = external_id.strip()
        try:
            payload = await self._fetcher.get_json(
                f"/api/v3/comic/{cid}/group/default/chapters"
            )
            chapters = parse_chapters_payload(payload)
        except (CopymangaParseError, TypeError, ValueError) as exc:
            raise _error(ProviderOperation.ASSET_LIST) from exc
        return tuple(
            VideoAsset(
                provider_key=COPYMANGA_PROVIDER_KEY,
                asset_id=ch["chapter_id"][:200],
                kind=VideoAssetKind.PREVIEW_IMAGE,
                display_name=ch["title"][:200],
                requires_auth=False,
                downloadable=False,
            )
            for ch in chapters
            if ch.get("chapter_id")
        )


def _error(operation: ProviderOperation) -> ProviderAdapterError:
    return ProviderAdapterError(
        ProviderError(
            code=ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            provider_key=COPYMANGA_PROVIDER_KEY,
            operation=operation,
        )
    )
