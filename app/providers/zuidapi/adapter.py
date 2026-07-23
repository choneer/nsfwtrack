"""Async MacCMS/ZuidAPI VideoMetadataAdapter with injectable JSON fetch."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlencode

from app.providers.zuidapi.approval import ZUIDAPI_HOST, ZUIDAPI_PROVIDER_KEY
from app.providers.zuidapi.parse import MacCMSParseError, parse_maccms_vod_payload
from app.source_adapters.contracts import (
    ProviderAdapterError,
    ProviderError,
    ProviderErrorCode,
    ProviderOperation,
)
from app.video_metadata.contracts import (
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
    VideoTag,
    VideoTagCategory,
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
        raise MacCMSParseError("fixture page missing")


class ZuidapiLiveVideoMetadataAdapter:
    key = ZUIDAPI_PROVIDER_KEY

    def __init__(self, fetcher: JsonFetcher) -> None:
        self._fetcher = fetcher

    async def search(self, query: str, *, page: int, page_size: int) -> VideoSearchPage:
        if not query.strip() or page < 1 or page_size < 1 or page_size > 20:
            raise _error(ProviderOperation.SEARCH)
        try:
            payload = await self._fetcher.get_json(
                "/api.php/provide/vod",
                query={
                    "ac": "list",
                    "wd": query.strip(),
                    "pg": str(page),
                    "limit": str(min(page_size, 20)),
                },
            )
            normalized = parse_maccms_vod_payload(payload)
        except (MacCMSParseError, TypeError, ValueError) as exc:
            raise _error(ProviderOperation.SEARCH) from exc
        items = tuple(_search_item(item) for item in normalized["items"])
        total = int(normalized["total"] or len(items)) if normalized.get("total") else len(items)
        try:
            total = int(normalized["total"]) if normalized.get("total") is not None else len(items)
        except (TypeError, ValueError):
            total = len(items)
        return VideoSearchPage(
            items=items,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
            total=total,
            query=query,
        )

    async def detail(self, external_id: str) -> VideoDetail:
        if not external_id or not str(external_id).strip():
            raise _error(ProviderOperation.DETAIL)
        vod_id = str(external_id).strip()
        try:
            payload = await self._fetcher.get_json(
                "/api.php/provide/vod",
                query={"ac": "detail", "ids": vod_id},
            )
            normalized = parse_maccms_vod_payload(payload)
        except (MacCMSParseError, TypeError, ValueError) as exc:
            raise _error(ProviderOperation.DETAIL) from exc
        if not normalized["items"]:
            raise _error(ProviderOperation.DETAIL)
        return _detail_item(normalized["items"][0])

    async def asset_list(self, external_id: str) -> tuple:
        raise _error(ProviderOperation.ASSET_LIST)


def _search_item(item: dict[str, Any]) -> VideoSearchResult:
    vod_id = str(item["vod_id"])
    observed = datetime.now(tz=UTC)
    return VideoSearchResult(
        identifier=VideoIdentifier(
            provider_key=ZUIDAPI_PROVIDER_KEY,
            external_id=vod_id,
            canonical_url=(
                f"https://{ZUIDAPI_HOST}/api.php/provide/vod?"
                + urlencode((("ac", "detail"), ("ids", vod_id)))
            ),
        ),
        title=str(item.get("vod_name") or vod_id),
        provenance=(
            VideoMetadataProvenance(
                provider_key=ZUIDAPI_PROVIDER_KEY,
                external_id=vod_id,
                operation=VideoProvenanceOperation.SEARCH,
                field_name="title",
                observed_at=observed,
                confidence=VideoConfidence.MEDIUM,
            ),
        ),
    )


def _detail_item(item: dict[str, Any]) -> VideoDetail:
    vod_id = str(item["vod_id"])
    observed = datetime.now(tz=UTC)
    performers = tuple(
        VideoPerson(
            provider_key=ZUIDAPI_PROVIDER_KEY,
            external_id=f"actor:{name}",
            display_name=name,
            role=VideoPersonRole.PERFORMER,
        )
        for name in (item.get("vod_actor") or [])
        if isinstance(name, str) and name.strip()
    )
    director = None
    if isinstance(item.get("vod_director"), str) and item["vod_director"].strip():
        director = VideoPerson(
            provider_key=ZUIDAPI_PROVIDER_KEY,
            external_id=f"director:{item['vod_director']}",
            display_name=str(item["vod_director"]),
            role=VideoPersonRole.DIRECTOR,
        )
    tags = tuple(
        VideoTag(
            provider_key=ZUIDAPI_PROVIDER_KEY,
            external_id=f"class:{name}",
            raw_name=name,
            normalized_name=name.casefold(),
            category=VideoTagCategory.GENRE,
        )
        for name in (item.get("vod_class") or [])
        if isinstance(name, str) and name.strip()
    )
    return VideoDetail(
        identifier=VideoIdentifier(
            provider_key=ZUIDAPI_PROVIDER_KEY,
            external_id=vod_id,
            canonical_url=(
                f"https://{ZUIDAPI_HOST}/api.php/provide/vod?"
                + urlencode((("ac", "detail"), ("ids", vod_id)))
            ),
        ),
        title=str(item.get("vod_name") or vod_id),
        performers=performers,
        director=director,
        tags=tags,
        provenance=(
            VideoMetadataProvenance(
                provider_key=ZUIDAPI_PROVIDER_KEY,
                external_id=vod_id,
                operation=VideoProvenanceOperation.DETAIL,
                field_name="title",
                observed_at=observed,
                confidence=VideoConfidence.HIGH,
            ),
        ),
    )


def _error(operation: ProviderOperation) -> ProviderAdapterError:
    return ProviderAdapterError(
        ProviderError(
            code=ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            provider_key=ZUIDAPI_PROVIDER_KEY,
            operation=operation,
        )
    )
