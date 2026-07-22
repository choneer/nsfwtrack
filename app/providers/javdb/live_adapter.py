"""Async live JavDB VideoMetadataAdapter (SEARCH/DETAIL/ASSET_LIST).

Network access is only through an injected ``HtmlFetcher`` allowlisted to the
production host. Operator cookie is required for live fetchers.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from app.providers.javdb.fetch import HtmlFetcher
from app.providers.javdb.parse import parse_detail_html, parse_search_html
from app.providers.javdb.production import (
    JAVDB_PRODUCTION_HOST,
    JAVDB_PRODUCTION_PROVIDER_KEY,
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
    VideoOrganization,
    VideoOrganizationType,
    VideoPerson,
    VideoPersonRole,
    VideoProvenanceOperation,
    VideoSearchPage,
    VideoSearchResult,
    VideoSeries,
    VideoTag,
    VideoTagCategory,
)

_ASSET_ID_SAFE = re.compile(r"^[A-Za-z0-9._~-]{1,200}$")


class JavDBLiveVideoMetadataAdapter:
    """Production-shaped async adapter; fetch is injectable for tests."""

    key = JAVDB_PRODUCTION_PROVIDER_KEY

    def __init__(
        self,
        fetcher: HtmlFetcher,
        *,
        base_url: str = f"https://{JAVDB_PRODUCTION_HOST}",
    ) -> None:
        self._fetcher = fetcher
        self._base_url = base_url.rstrip("/")

    async def search(self, query: str, *, page: int, page_size: int) -> VideoSearchPage:
        operation = ProviderOperation.SEARCH
        if not isinstance(query, str) or not query.strip():
            raise _error(operation)
        if page < 1 or page_size < 1:
            raise _error(operation)
        try:
            html = await self._fetcher.get_html(
                "/search", query={"q": query.strip()}
            )
            cards = parse_search_html(html, base_url=self._base_url)
        except Exception as exc:  # noqa: BLE001
            raise _error(operation) from exc

        q = query.strip().upper()
        matched = [
            card
            for card in cards
            if q in (card.get("catalog_number") or "").upper()
            or q in (card.get("title") or "").upper()
            or q in (card.get("external_id") or "").upper()
        ]
        if matched:
            cards = matched
        start = (page - 1) * page_size
        window = cards[start : start + page_size]
        items = tuple(_search_result(card) for card in window)
        return VideoSearchPage(
            items=items,
            page=page,
            page_size=page_size,
            has_next=start + page_size < len(cards),
            total=len(cards),
            query=query,
        )

    async def detail(self, external_id: str) -> VideoDetail:
        operation = ProviderOperation.DETAIL
        slug = _require_slug(external_id, operation)
        try:
            html = await self._fetcher.get_html(f"/v/{slug}")
            raw = parse_detail_html(
                html, external_id=slug, base_url=self._base_url
            )
        except Exception as exc:  # noqa: BLE001
            raise _error(operation) from exc
        return _detail(raw)

    async def asset_list(self, external_id: str) -> tuple[VideoAsset, ...]:
        """Non-downloadable link descriptors (cover + previews)."""

        operation = ProviderOperation.ASSET_LIST
        slug = _require_slug(external_id, operation)
        try:
            html = await self._fetcher.get_html(f"/v/{slug}")
            raw = parse_detail_html(
                html, external_id=slug, base_url=self._base_url
            )
        except Exception as exc:  # noqa: BLE001
            raise _error(operation) from exc
        assets: list[VideoAsset] = []
        cover = raw.get("cover_asset_id")
        if isinstance(cover, str) and _safe_asset_id(cover):
            assets.append(
                VideoAsset(
                    provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
                    asset_id=_safe_asset_id(cover),
                    kind=VideoAssetKind.COVER,
                    display_name="cover",
                    mime_type=None,
                    requires_auth=False,
                    downloadable=False,
                )
            )
        previews = raw.get("preview_asset_ids") or ()
        if isinstance(previews, (list, tuple)):
            for index, preview in enumerate(previews):
                if not isinstance(preview, str):
                    continue
                aid = _safe_asset_id(preview)
                if not aid:
                    continue
                assets.append(
                    VideoAsset(
                        provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
                        asset_id=aid,
                        kind=VideoAssetKind.PREVIEW_IMAGE,
                        display_name=f"preview-{index + 1}",
                        mime_type=None,
                        requires_auth=False,
                        downloadable=False,
                    )
                )
        return tuple(assets)


def _require_slug(external_id: str, operation: ProviderOperation) -> str:
    if not isinstance(external_id, str) or not external_id.strip():
        raise _error(operation)
    slug = external_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", slug):
        raise _error(operation)
    return slug


def _safe_asset_id(value: str) -> str:
    cleaned = value.strip().split("?")[0].rsplit("/", 1)[-1]
    cleaned = cleaned.replace(" ", "_")
    if not cleaned or ".." in cleaned:
        return ""
    if not _ASSET_ID_SAFE.fullmatch(cleaned):
        # hash-like fallback for opaque ids
        digest = re.sub(r"[^A-Za-z0-9._~-]", "", cleaned)[:64]
        return digest if digest else ""
    return cleaned[:200]


def _error(operation: ProviderOperation) -> ProviderAdapterError:
    return ProviderAdapterError(
        ProviderError(
            code=ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
            operation=operation,
        )
    )


def _identifier(
    *,
    external_id: str,
    catalog_number: str | None,
    canonical_url: str | None,
) -> VideoIdentifier:
    return VideoIdentifier(
        provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
        external_id=external_id,
        catalog_number=catalog_number,
        canonical_url=canonical_url,
    )


def _search_result(card: dict[str, str | None]) -> VideoSearchResult:
    external_id = card["external_id"] or ""
    cover = None
    cover_raw = card.get("cover_asset_id")
    if cover_raw and _safe_asset_id(cover_raw):
        cover = VideoAsset(
            provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
            asset_id=_safe_asset_id(cover_raw),
            kind=VideoAssetKind.COVER,
            requires_auth=False,
            downloadable=False,
        )
    observed = datetime.now(tz=UTC)
    return VideoSearchResult(
        identifier=_identifier(
            external_id=external_id,
            catalog_number=card.get("catalog_number"),
            canonical_url=card.get("canonical_url"),
        ),
        title=card.get("title") or external_id,
        alternate_titles=(),
        release_date=None,
        performers=(),
        studio=None,
        tags=(),
        cover=cover,
        summary=None,
        available_fields=None,
        provenance=(
            VideoMetadataProvenance(
                provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
                external_id=external_id,
                operation=VideoProvenanceOperation.SEARCH,
                field_name="title",
                observed_at=observed,
                confidence=VideoConfidence.MEDIUM,
            ),
        ),
    )


def _detail(raw: dict[str, Any]) -> VideoDetail:
    external_id = str(raw["external_id"])
    observed = datetime.now(tz=UTC)
    performers = tuple(
        VideoPerson(
            provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
            external_id=f"performer:{name}",
            display_name=name,
            role=VideoPersonRole.PERFORMER,
            alternate_names=(),
        )
        for name in (raw.get("performers") or ())
        if isinstance(name, str) and name.strip()
    )
    director = None
    if isinstance(raw.get("director"), str) and raw["director"].strip():
        director = VideoPerson(
            provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
            external_id=f"director:{raw['director']}",
            display_name=str(raw["director"]),
            role=VideoPersonRole.DIRECTOR,
            alternate_names=(),
        )
    tags = tuple(
        VideoTag(
            provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
            external_id=f"tag:{name}",
            raw_name=name,
            normalized_name=name.casefold(),
            category=VideoTagCategory.GENRE,
        )
        for name in (raw.get("tags") or ())
        if isinstance(name, str) and name.strip()
    )
    studio = None
    if isinstance(raw.get("studio"), str) and raw["studio"].strip():
        studio = VideoOrganization(
            provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
            external_id=f"studio:{raw['studio']}",
            display_name=str(raw["studio"]),
            organization_type=VideoOrganizationType.STUDIO,
        )
    series = None
    if isinstance(raw.get("series"), str) and raw["series"].strip():
        series = VideoSeries(
            provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
            external_id=f"series:{raw['series']}",
            display_name=str(raw["series"]),
        )
    release = None
    if isinstance(raw.get("release_date"), str):
        try:
            release = date.fromisoformat(raw["release_date"])
        except ValueError:
            release = None
    cover = None
    if isinstance(raw.get("cover_asset_id"), str) and _safe_asset_id(
        str(raw["cover_asset_id"])
    ):
        cover = VideoAsset(
            provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
            asset_id=_safe_asset_id(str(raw["cover_asset_id"])),
            kind=VideoAssetKind.COVER,
            requires_auth=False,
            downloadable=False,
        )
    previews: list[VideoAsset] = []
    for index, preview in enumerate(raw.get("preview_asset_ids") or ()):
        if not isinstance(preview, str):
            continue
        aid = _safe_asset_id(preview)
        if not aid:
            continue
        previews.append(
            VideoAsset(
                provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
                asset_id=aid,
                kind=VideoAssetKind.PREVIEW_IMAGE,
                display_name=f"preview-{index + 1}",
                requires_auth=False,
                downloadable=False,
            )
        )
    title = str(raw.get("title") or external_id)
    duration_seconds = None
    if isinstance(raw.get("duration_minutes"), int):
        duration_seconds = int(raw["duration_minutes"]) * 60
    return VideoDetail(
        identifier=_identifier(
            external_id=external_id,
            catalog_number=str(raw["catalog_number"])
            if raw.get("catalog_number")
            else None,
            canonical_url=str(raw["canonical_url"])
            if raw.get("canonical_url")
            else None,
        ),
        title=title,
        alternate_titles=(),
        summary=None,
        release_date=release,
        duration_seconds=duration_seconds,
        performers=performers,
        director=director,
        studio=studio,
        series=series,
        tags=tags,
        cover=cover,
        preview_images=tuple(previews),
        available_fields=None,
        provenance=(
            VideoMetadataProvenance(
                provider_key=JAVDB_PRODUCTION_PROVIDER_KEY,
                external_id=external_id,
                operation=VideoProvenanceOperation.DETAIL,
                field_name="title",
                observed_at=observed,
                confidence=VideoConfidence.HIGH,
            ),
        ),
    )
