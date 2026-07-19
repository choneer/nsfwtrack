"""Static, tests-only Video Metadata adapter.

The provider deliberately has no HTTP dependencies.  Its parser is an
explicit boundary around synthetic JSON and maps failures to the existing
stable ``ProviderAdapterError`` contract without retaining or echoing payloads.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

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
    VideoMetadataAdapter,
    VideoMetadataProvenance,
    VideoOrganization,
    VideoOrganizationType,
    VideoPerson,
    VideoPersonRole,
    VideoProvenanceOperation,
    VideoRating,
    VideoSearchPage,
    VideoSearchResult,
    VideoSeries,
    VideoTag,
    VideoTagCategory,
    bounded_text,
    optional_bounded_text,
)


FIXTURE_PROVIDER_KEY = "fixture_video"
FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "video_metadata"
MAX_FIXTURE_ASSETS = 64


class _PayloadFailure(Exception):
    pass


def _provider_error(operation: ProviderOperation) -> ProviderAdapterError:
    return ProviderAdapterError(
        ProviderError(
            code=ProviderErrorCode.INVALID_PROVIDER_PAYLOAD,
            provider_key=FIXTURE_PROVIDER_KEY,
            operation=operation,
        )
    )


def _object(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _PayloadFailure
    return value


def _required(mapping: Mapping[str, object], name: str) -> object:
    if name not in mapping:
        raise _PayloadFailure
    return mapping[name]


def _text(mapping: Mapping[str, object], name: str, *, optional: bool = False) -> str | None:
    value = mapping.get(name)
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise _PayloadFailure
    try:
        return bounded_text(value, field=name)
    except (TypeError, ValueError):
        raise _PayloadFailure from None


def _date(mapping: Mapping[str, object], name: str) -> date | None:
    value = mapping.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _PayloadFailure
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _PayloadFailure from None


def _datetime(mapping: Mapping[str, object], name: str) -> datetime | None:
    value = mapping.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _PayloadFailure
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _PayloadFailure from None


def _tuple_values(mapping: Mapping[str, object], name: str) -> tuple[object, ...]:
    value = mapping.get(name, ())
    if not isinstance(value, list):
        raise _PayloadFailure
    return tuple(value)


def _string_tuple(mapping: Mapping[str, object], name: str) -> tuple[str, ...]:
    values = _tuple_values(mapping, name)
    if not all(isinstance(value, str) for value in values):
        raise _PayloadFailure
    return tuple(value for value in values)


def _identifier(payload: Mapping[str, object]) -> VideoIdentifier:
    try:
        return VideoIdentifier(
            provider_key=FIXTURE_PROVIDER_KEY,
            external_id=_text(payload, "external_id") or "",
            catalog_number=_text(payload, "catalog_number", optional=True),
            canonical_url=_text(payload, "canonical_url", optional=True),
        )
    except (TypeError, ValueError):
        raise _PayloadFailure from None


def _person(payload: object) -> VideoPerson:
    data = _object(payload)
    try:
        return VideoPerson(
            provider_key=FIXTURE_PROVIDER_KEY,
            external_id=_text(data, "external_id") or "",
            display_name=_text(data, "display_name") or "",
            role=VideoPersonRole(_text(data, "role") or ""),
            alternate_names=_string_tuple(data, "alternate_names"),
        )
    except (TypeError, ValueError):
        raise _PayloadFailure from None


def _organization(payload: object) -> VideoOrganization:
    data = _object(payload)
    try:
        return VideoOrganization(
            provider_key=FIXTURE_PROVIDER_KEY,
            external_id=_text(data, "external_id") or "",
            display_name=_text(data, "display_name") or "",
            organization_type=VideoOrganizationType(_text(data, "organization_type") or ""),
        )
    except (TypeError, ValueError):
        raise _PayloadFailure from None


def _series(payload: object) -> VideoSeries:
    data = _object(payload)
    try:
        return VideoSeries(
            provider_key=FIXTURE_PROVIDER_KEY,
            external_id=_text(data, "external_id") or "",
            display_name=_text(data, "display_name") or "",
        )
    except (TypeError, ValueError):
        raise _PayloadFailure from None


def _tag(payload: object) -> VideoTag:
    data = _object(payload)
    try:
        return VideoTag(
            provider_key=FIXTURE_PROVIDER_KEY,
            external_id=_text(data, "external_id") or "",
            raw_name=_text(data, "raw_name") or "",
            normalized_name=_text(data, "normalized_name") or "",
            category=VideoTagCategory(_text(data, "category") or ""),
        )
    except (TypeError, ValueError):
        raise _PayloadFailure from None


def _asset(payload: object) -> VideoAsset:
    data = _object(payload)
    try:
        width = data.get("width")
        height = data.get("height")
        duration = data.get("duration_seconds")
        if any(value is not None and (not isinstance(value, int) or isinstance(value, bool)) for value in (width, height, duration)):
            raise _PayloadFailure
        return VideoAsset(
            provider_key=FIXTURE_PROVIDER_KEY,
            asset_id=_text(data, "asset_id") or "",
            kind=VideoAssetKind(_text(data, "kind") or ""),
            display_name=_text(data, "display_name", optional=True),
            mime_type=_text(data, "mime_type", optional=True),
            width=width,
            height=height,
            duration_seconds=duration,
            requires_auth=data.get("requires_auth", False),
            downloadable=data.get("downloadable", False),
        )
    except (TypeError, ValueError):
        raise _PayloadFailure from None


def _provenance(payload: object) -> VideoMetadataProvenance:
    data = _object(payload)
    try:
        return VideoMetadataProvenance(
            provider_key=FIXTURE_PROVIDER_KEY,
            external_id=_text(data, "external_id") or "",
            operation=VideoProvenanceOperation(_text(data, "operation") or ""),
            field_name=_text(data, "field_name") or "",
            observed_at=_datetime(data, "observed_at"),  # type: ignore[arg-type]
            source_updated_at=_datetime(data, "source_updated_at"),
            confidence=VideoConfidence(_text(data, "confidence") or ""),
        )
    except (TypeError, ValueError):
        raise _PayloadFailure from None


def _rating(payload: object) -> VideoRating:
    data = _object(payload)
    try:
        value = _required(data, "value")
        scale_min = _required(data, "scale_min")
        scale_max = _required(data, "scale_max")
        vote_count = data.get("vote_count")
        return VideoRating(
            value=value,  # type: ignore[arg-type]
            scale_min=scale_min,  # type: ignore[arg-type]
            scale_max=scale_max,  # type: ignore[arg-type]
            vote_count=vote_count,  # type: ignore[arg-type]
        )
    except (TypeError, ValueError):
        raise _PayloadFailure from None


def _available(data: Mapping[str, object]) -> tuple[str, ...] | None:
    value = data.get("available_fields")
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _PayloadFailure
    return tuple(value)


def _search_result(payload: object) -> VideoSearchResult:
    data = _object(payload)
    try:
        identifier = _identifier(data)
        return VideoSearchResult(
            identifier=identifier,
            title=_text(data, "title") or "",
            alternate_titles=_string_tuple(data, "alternate_titles"),
            release_date=_date(data, "release_date"),
            performers=tuple(_person(value) for value in _tuple_values(data, "performers")),
            studio=_organization(data["studio"]) if data.get("studio") is not None else None,
            tags=tuple(_tag(value) for value in _tuple_values(data, "tags")),
            cover=_asset(data["cover"]) if data.get("cover") is not None else None,
            summary=_text(data, "summary", optional=True),
            available_fields=_available(data),
            provenance=tuple(_provenance(value) for value in _tuple_values(data, "provenance")),
        )
    except (TypeError, ValueError):
        raise _PayloadFailure from None


def _detail(payload: object) -> VideoDetail:
    data = _object(payload)
    try:
        identifier = _identifier(data)
        return VideoDetail(
            identifier=identifier,
            title=_text(data, "title") or "",
            alternate_titles=_string_tuple(data, "alternate_titles"),
            summary=_text(data, "summary", optional=True),
            release_date=_date(data, "release_date"),
            duration_seconds=data.get("duration_seconds"),  # type: ignore[arg-type]
            performers=tuple(_person(value) for value in _tuple_values(data, "performers")),
            director=_person(data["director"]) if data.get("director") is not None else None,
            studio=_organization(data["studio"]) if data.get("studio") is not None else None,
            publisher=_organization(data["publisher"]) if data.get("publisher") is not None else None,
            series=_series(data["series"]) if data.get("series") is not None else None,
            tags=tuple(_tag(value) for value in _tuple_values(data, "tags")),
            rating=_rating(data["rating"]) if data.get("rating") is not None else None,
            cover=_asset(data["cover"]) if data.get("cover") is not None else None,
            preview_images=tuple(_asset(value) for value in _tuple_values(data, "preview_images")),
            preview_video=_asset(data["preview_video"]) if data.get("preview_video") is not None else None,
            source_updated_at=_datetime(data, "source_updated_at"),
            available_fields=_available(data),
            provenance=tuple(_provenance(value) for value in _tuple_values(data, "provenance")),
        )
    except (TypeError, ValueError):
        raise _PayloadFailure from None


class FixtureVideoMetadataProvider:
    """A static JSON implementation used only by tests."""

    key = FIXTURE_PROVIDER_KEY
    provider_key = FIXTURE_PROVIDER_KEY
    supports_asset_list = True

    def __init__(self, fixture_directory: Path | None = None) -> None:
        self.fixture_directory = fixture_directory or FIXTURE_DIRECTORY

    def _load(self, filename: str, operation: ProviderOperation) -> Mapping[str, object]:
        try:
            path = self.fixture_directory / filename
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _object(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
            raise _provider_error(operation) from None

    async def search(self, query: str, *, page: int, page_size: int) -> VideoSearchPage:
        operation = ProviderOperation.SEARCH
        try:
            if not isinstance(query, str):
                raise _PayloadFailure
            filename = "search_empty.json" if query.casefold().strip() in {"empty", "none"} else "search_success.json"
            data = self._load(filename, operation)
            results_value = _required(data, "results")
            if not isinstance(results_value, list):
                raise _PayloadFailure
            page_value = _required(data, "page")
            page_size_value = _required(data, "page_size")
            has_next = _required(data, "has_next")
            total = _required(data, "total")
            if page_value != page or page_size_value != page_size or not isinstance(has_next, bool):
                raise _PayloadFailure
            if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                raise _PayloadFailure
            return VideoSearchPage(
                items=tuple(_search_result(value) for value in results_value),
                page=page,
                page_size=page_size,
                has_next=has_next,
                total=total,
                query=query,
            )
        except ProviderAdapterError:
            raise
        except (TypeError, ValueError, _PayloadFailure):
            raise _provider_error(operation) from None

    async def detail(self, external_id: str) -> VideoDetail:
        operation = ProviderOperation.DETAIL
        filename = {
            "video-001": "detail_complete.json",
            "video-002": "detail_partial.json",
            "invalid-payload": "invalid_payload.json",
        }.get(external_id)
        if filename is None:
            raise _provider_error(operation)
        try:
            result = _detail(self._load(filename, operation))
            if result.external_id != external_id:
                raise _PayloadFailure
            return result
        except ProviderAdapterError:
            raise
        except (TypeError, ValueError, _PayloadFailure):
            raise _provider_error(operation) from None

    async def asset_list(self, external_id: str) -> tuple[VideoAsset, ...]:
        operation = ProviderOperation.ASSET_LIST
        if external_id != "video-001":
            raise _provider_error(operation)
        try:
            data = self._load("assets_success.json", operation)
            value = _required(data, "assets")
            if not isinstance(value, list):
                raise _PayloadFailure
            if len(value) > MAX_FIXTURE_ASSETS:
                raise _PayloadFailure
            assets = tuple(_asset(item) for item in value)
            identities = tuple(asset.identity for asset in assets)
            if len(identities) != len(set(identities)):
                raise _PayloadFailure
            return assets
        except ProviderAdapterError:
            raise
        except (TypeError, ValueError, _PayloadFailure):
            raise _provider_error(operation) from None


assert isinstance(FixtureVideoMetadataProvider(), VideoMetadataAdapter)


__all__ = [
    "FIXTURE_DIRECTORY",
    "FIXTURE_PROVIDER_KEY",
    "FixtureVideoMetadataProvider",
]
