"""Offline VideoMetadataAdapter for JavDB-shaped HTML fixtures.

No HTTP client is used. Fixture files are loaded from a directory supplied at
construction (tests pass the path). Production network activation is out of
scope for this module.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from app.providers.javdb.approval import JAVDB_PROVIDER_KEY
from app.providers.javdb.parse import parse_detail_html, parse_search_html
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


class JavDBFixtureVideoMetadataAdapter:
    """Maps offline HTML fixtures into Video* DTOs."""

    key = JAVDB_PROVIDER_KEY

    def __init__(
        self,
        fixture_root: Path,
        *,
        base_url: str = "https://metadata.javdb.invalid",
    ) -> None:
        if not isinstance(fixture_root, Path):
            raise TypeError("fixture_root must be a Path")
        self._root = fixture_root
        self._base_url = base_url

    def search(self, query: str, *, page: int, page_size: int) -> VideoSearchPage:
        operation = ProviderOperation.SEARCH
        if not isinstance(query, str) or not query.strip():
            raise _error(operation)
        if page < 1 or page_size < 1:
            raise _error(operation)
        try:
            if query.strip().lower() in {"__empty__", "no-results"}:
                html = (self._root / "search_empty.html").read_text(encoding="utf-8")
            else:
                html = (self._root / "search_normal.html").read_text(encoding="utf-8")
            cards = parse_search_html(html, base_url=self._base_url)
        except (OSError, ValueError, UnicodeError) as exc:
            raise _error(operation) from exc

        q = query.strip().upper()
        if query.strip().lower() in {"__empty__", "no-results"}:
            cards = []
        else:
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

    def detail(self, external_id: str) -> VideoDetail:
        operation = ProviderOperation.DETAIL
        if not isinstance(external_id, str) or not external_id.strip():
            raise _error(operation)
        slug = external_id.strip()
        path = self._root / f"detail_{slug}.html"
        if not path.is_file():
            path = self._root / "detail_normal.html"
        try:
            html = path.read_text(encoding="utf-8")
            raw = parse_detail_html(html, external_id=slug, base_url=self._base_url)
        except (OSError, ValueError, UnicodeError) as exc:
            raise _error(operation) from exc
        return _detail(raw)

    def asset_list(self, external_id: str) -> object:
        raise _error(ProviderOperation.ASSET_LIST)


def _error(operation: ProviderOperation) -> ProviderAdapterError:
    return ProviderAdapterError(
        ProviderError(
            code=ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            provider_key=JAVDB_PROVIDER_KEY,
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
        provider_key=JAVDB_PROVIDER_KEY,
        external_id=external_id,
        catalog_number=catalog_number,
        canonical_url=canonical_url,
    )


def _search_result(card: dict[str, str | None]) -> VideoSearchResult:
    external_id = card["external_id"] or ""
    cover = None
    if card.get("cover_asset_id"):
        cover = VideoAsset(
            provider_key=JAVDB_PROVIDER_KEY,
            asset_id=str(card["cover_asset_id"]),
            kind=VideoAssetKind.COVER,
            display_name=None,
            mime_type=None,
            width=None,
            height=None,
            duration_seconds=None,
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
                provider_key=JAVDB_PROVIDER_KEY,
                external_id=external_id,
                operation=VideoProvenanceOperation.SEARCH,
                field_name="title",
                observed_at=observed,
                source_updated_at=None,
                confidence=VideoConfidence.MEDIUM,
            ),
        ),
    )


def _detail(raw: dict[str, object]) -> VideoDetail:
    external_id = str(raw["external_id"])
    observed = datetime.now(tz=UTC)
    performers = tuple(
        VideoPerson(
            provider_key=JAVDB_PROVIDER_KEY,
            external_id=f"performer:{name}",
            display_name=name,
            role=VideoPersonRole.PERFORMER,
            alternate_names=(),
        )
        for name in (raw.get("performers") or ())
        if isinstance(name, str)
    )
    director = None
    if isinstance(raw.get("director"), str) and raw["director"]:
        director = VideoPerson(
            provider_key=JAVDB_PROVIDER_KEY,
            external_id=f"director:{raw['director']}",
            display_name=str(raw["director"]),
            role=VideoPersonRole.DIRECTOR,
            alternate_names=(),
        )
    studio = None
    if isinstance(raw.get("studio"), str) and raw["studio"]:
        studio = VideoOrganization(
            provider_key=JAVDB_PROVIDER_KEY,
            external_id=f"studio:{raw['studio']}",
            display_name=str(raw["studio"]),
            organization_type=VideoOrganizationType.STUDIO,
        )
    publisher = None
    if isinstance(raw.get("publisher"), str) and raw["publisher"]:
        publisher = VideoOrganization(
            provider_key=JAVDB_PROVIDER_KEY,
            external_id=f"publisher:{raw['publisher']}",
            display_name=str(raw["publisher"]),
            organization_type=VideoOrganizationType.PUBLISHER,
        )
    series = None
    if isinstance(raw.get("series"), str) and raw["series"]:
        series = VideoSeries(
            provider_key=JAVDB_PROVIDER_KEY,
            external_id=f"series:{raw['series']}",
            display_name=str(raw["series"]),
        )
    tags = tuple(
        VideoTag(
            provider_key=JAVDB_PROVIDER_KEY,
            external_id=f"tag:{name}",
            raw_name=name,
            normalized_name=name.casefold(),
            category=VideoTagCategory.GENRE,
        )
        for name in (raw.get("tags") or ())
        if isinstance(name, str)
    )
    cover = None
    if isinstance(raw.get("cover_asset_id"), str) and raw["cover_asset_id"]:
        cover = VideoAsset(
            provider_key=JAVDB_PROVIDER_KEY,
            asset_id=str(raw["cover_asset_id"]),
            kind=VideoAssetKind.COVER,
            display_name=None,
            mime_type=None,
            width=None,
            height=None,
            duration_seconds=None,
            requires_auth=False,
            downloadable=False,
        )
    previews = tuple(
        VideoAsset(
            provider_key=JAVDB_PROVIDER_KEY,
            asset_id=asset_id,
            kind=VideoAssetKind.PREVIEW_IMAGE,
            display_name=None,
            mime_type=None,
            width=None,
            height=None,
            duration_seconds=None,
            requires_auth=False,
            downloadable=False,
        )
        for asset_id in (raw.get("preview_asset_ids") or ())
        if isinstance(asset_id, str)
    )
    release = None
    if isinstance(raw.get("release_date"), str):
        try:
            release = date.fromisoformat(str(raw["release_date"]))
        except ValueError:
            release = None
    duration_seconds = None
    if isinstance(raw.get("duration_minutes"), int):
        duration_seconds = int(raw["duration_minutes"]) * 60

    catalog = str(raw["catalog_number"]) if raw.get("catalog_number") else None
    return VideoDetail(
        identifier=_identifier(
            external_id=external_id,
            catalog_number=catalog,
            canonical_url=str(raw["canonical_url"]) if raw.get("canonical_url") else None,
        ),
        title=str(raw["title"]),
        alternate_titles=(),
        summary=None,
        release_date=release,
        duration_seconds=duration_seconds,
        performers=performers,
        director=director,
        studio=studio,
        publisher=publisher,
        series=series,
        tags=tags,
        rating=None,
        cover=cover,
        preview_images=previews,
        preview_video=None,
        source_updated_at=None,
        available_fields=None,
        provenance=(
            VideoMetadataProvenance(
                provider_key=JAVDB_PROVIDER_KEY,
                external_id=external_id,
                operation=VideoProvenanceOperation.DETAIL,
                field_name="title",
                observed_at=observed,
                source_updated_at=None,
                confidence=VideoConfidence.MEDIUM,
            ),
        ),
    )
