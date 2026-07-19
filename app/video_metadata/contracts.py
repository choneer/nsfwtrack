"""Provider-neutral, immutable contracts for video metadata.

This module deliberately stops at typed metadata.  It does not know how a
provider is reached and it never stores a provider response, URL locator, or
credential.  The fixture adapter in ``tests`` is the only parser in this
phase.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from numbers import Real
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit


MAX_PROVIDER_KEY_LENGTH = 64
MAX_EXTERNAL_ID_LENGTH = 512
MAX_CATALOG_NUMBER_LENGTH = 128
MAX_CANONICAL_URL_LENGTH = 2_048
MAX_TEXT_LENGTH = 20_000
MAX_TITLE_LENGTH = 500
MAX_NAME_LENGTH = 500
MAX_SUMMARY_LENGTH = 20_000
MAX_ALTERNATE_TITLES = 50
MAX_ALTERNATE_NAMES = 50
MAX_PEOPLE = 100
MAX_ORGANIZATIONS = 50
MAX_TAGS = 200
MAX_PREVIEW_IMAGES = 32
MAX_AVAILABLE_FIELDS = 64
MAX_FIELD_NAME_LENGTH = 64
MAX_ASSET_ID_LENGTH = 512
MAX_ASSET_DISPLAY_NAME_LENGTH = 500
MAX_MIME_TYPE_LENGTH = 255
MAX_PAGE_SIZE = 50
MAX_QUERY_LENGTH = 200

_PROVIDER_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_ASSET_ID_PATTERN = re.compile(
    r"[A-Za-z0-9_~-](?:[A-Za-z0-9._~-]{0,510}[A-Za-z0-9_~-])?\Z"
)
_FIELD_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_MIME_TYPE_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/"
    r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}\Z"
)


class VideoMetadataError(ValueError):
    """Stable validation error that never includes an input value."""


class VideoPersonRole(str, Enum):
    PERFORMER = "performer"
    DIRECTOR = "director"


class VideoOrganizationType(str, Enum):
    STUDIO = "studio"
    PUBLISHER = "publisher"
    LABEL = "label"
    AGENCY = "agency"
    OTHER = "other"


class VideoTagCategory(str, Enum):
    GENERAL = "general"
    GENRE = "genre"
    THEME = "theme"
    CONTENT = "content"
    OTHER = "other"


class VideoAssetKind(str, Enum):
    COVER = "cover"
    PREVIEW_IMAGE = "preview_image"
    PREVIEW_VIDEO = "preview_video"


class VideoProvenanceOperation(str, Enum):
    SEARCH = "search"
    DETAIL = "detail"
    ASSET_LIST = "asset_list"


class VideoConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Short aliases make the contracts convenient without creating a second set of
# enum values.  The descriptive names remain the canonical public API.
PersonRole = VideoPersonRole
OrganizationType = VideoOrganizationType
TagCategory = VideoTagCategory
AssetKind = VideoAssetKind
ProvenanceOperation = VideoProvenanceOperation
Confidence = VideoConfidence


def bounded_text(
    value: str,
    maximum: int = MAX_TEXT_LENGTH,
    *,
    field: str = "value",
    allow_blank: bool = False,
) -> str:
    """Trim and validate text without echoing the supplied value in errors."""

    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        raise ValueError(f"{field} has an invalid bound")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise VideoMetadataError(f"{field} contains control characters")
    normalized = value.strip()
    if not allow_blank and not normalized:
        raise VideoMetadataError(f"{field} must not be blank")
    if len(normalized) > maximum:
        raise VideoMetadataError(f"{field} is too long")
    return normalized


def optional_bounded_text(
    value: str | None,
    maximum: int = MAX_TEXT_LENGTH,
    *,
    field: str = "value",
) -> str | None:
    if value is None:
        return None
    return bounded_text(value, maximum, field=field)


def bounded_text_tuple(
    values: tuple[str, ...],
    maximum_items: int = MAX_AVAILABLE_FIELDS,
    maximum_length: int = MAX_TEXT_LENGTH,
    *,
    field: str = "values",
) -> tuple[str, ...]:
    """Validate a tuple and deduplicate it in first-seen order."""

    if not isinstance(values, tuple):
        raise TypeError(f"{field} must be a tuple")
    if (
        not isinstance(maximum_items, int)
        or isinstance(maximum_items, bool)
        or maximum_items < 0
    ):
        raise ValueError(f"{field} has an invalid item bound")
    if len(values) > maximum_items:
        raise VideoMetadataError(f"{field} has too many values")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = bounded_text(value, maximum_length, field=field)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


def timezone_aware_utc(value: datetime, *, field: str = "datetime") -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise VideoMetadataError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def finite_number(
    value: Real,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    field: str = "value",
) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field} must be a number")
    converted = float(value)
    if not math.isfinite(converted):
        raise VideoMetadataError(f"{field} must be finite")
    if minimum is not None and converted < minimum:
        raise VideoMetadataError(f"{field} is below its range")
    if maximum is not None and converted > maximum:
        raise VideoMetadataError(f"{field} is above its range")
    return converted


def provider_scoped_identity(provider_key: str, external_id: str) -> tuple[str, str]:
    key = bounded_text(provider_key, MAX_PROVIDER_KEY_LENGTH, field="provider_key")
    if _PROVIDER_KEY_PATTERN.fullmatch(key) is None:
        raise VideoMetadataError("provider_key has an invalid format")
    identifier = bounded_text(
        external_id,
        MAX_EXTERNAL_ID_LENGTH,
        field="external_id",
    )
    return key, identifier


def _optional_datetime(value: datetime | None, *, field: str) -> datetime | None:
    return None if value is None else timezone_aware_utc(value, field=field)


def _optional_date(value: date | None, *, field: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{field} must be a date")
    return value


def _validate_canonical_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = bounded_text(
        value,
        MAX_CANONICAL_URL_LENGTH,
        field="canonical_url",
    )
    try:
        parsed = urlsplit(normalized)
        _ = parsed.port
    except ValueError as exc:
        raise VideoMetadataError("canonical_url is invalid") from exc
    if (
        any(character.isspace() for character in normalized)
        or "\\" in normalized
        or parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.fragment)
    ):
        raise VideoMetadataError("canonical_url must be credential-free HTTP/HTTPS")
    return normalized


def _require_enum(value: object, enum_type: type[Enum], *, field: str) -> Enum:
    if not isinstance(value, enum_type):
        raise TypeError(f"{field} has an invalid value")
    return value


def _validate_tuple_of(
    values: object,
    value_type: type[object],
    *,
    field: str,
    maximum: int,
) -> tuple[object, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field} must be a tuple")
    if len(values) > maximum or not all(isinstance(value, value_type) for value in values):
        raise VideoMetadataError(f"{field} is invalid")
    return values


def _reject_duplicate_identities(values: tuple[object, ...], *, field: str) -> None:
    identities: list[object] = []
    for value in values:
        identity = getattr(value, "identity", None)
        if identity is None:
            identity = getattr(value, "asset_identity", None)
        if identity in identities:
            raise VideoMetadataError(f"{field} contains duplicate identity")
        identities.append(identity)


def _present(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, tuple):
        return bool(value)
    return True


def _derived_available_fields(
    values: Mapping[str, object],
    order: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(name for name in order if name in values and _present(values[name]))


def available_field_set(
    values: Mapping[str, object] | tuple[str, ...],
    actual_fields: tuple[str, ...] | None = None,
    *,
    field_order: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Return a stable field set, optionally checking it against actual data."""

    if isinstance(values, Mapping):
        order = field_order or tuple(str(key) for key in values)
        result = _derived_available_fields(values, order)
    elif isinstance(values, tuple):
        result = bounded_text_tuple(
            values,
            MAX_AVAILABLE_FIELDS,
            MAX_FIELD_NAME_LENGTH,
            field="available_fields",
        )
        if any(_FIELD_NAME_PATTERN.fullmatch(value) is None for value in result):
            raise VideoMetadataError("available_fields contains an invalid name")
    else:
        raise TypeError("available_fields must be a mapping or tuple")
    if actual_fields is not None:
        expected = available_field_set(actual_fields)
        if result != expected:
            raise VideoMetadataError("available_fields does not match actual fields")
    return result


def provenance_field_set(
    provenance: tuple["VideoMetadataProvenance", ...],
    available_fields: tuple[str, ...],
) -> tuple[str, ...]:
    if not isinstance(provenance, tuple):
        raise TypeError("provenance must be a tuple")
    available = available_field_set(available_fields)
    result: list[str] = []
    for item in provenance:
        if not isinstance(item, VideoMetadataProvenance):
            raise TypeError("provenance contains an invalid value")
        if item.field_name not in available:
            raise VideoMetadataError("provenance references an unavailable field")
        if item.field_name not in result:
            result.append(item.field_name)
    return tuple(result)


def _validate_provenance(
    values: tuple["VideoMetadataProvenance", ...],
    *,
    identifier: "VideoIdentifier",
    available: tuple[str, ...],
    expected_operation: VideoProvenanceOperation | None = None,
) -> tuple["VideoMetadataProvenance", ...]:
    if not isinstance(values, tuple):
        raise TypeError("provenance must be a tuple")
    if len(values) > MAX_AVAILABLE_FIELDS:
        raise VideoMetadataError("provenance has too many values")
    seen: set[tuple[str, str, str]] = set()
    for item in values:
        if not isinstance(item, VideoMetadataProvenance):
            raise TypeError("provenance contains an invalid value")
        if item.provider_key != identifier.provider_key or item.external_id != identifier.external_id:
            raise VideoMetadataError("provenance identity does not match metadata")
        if expected_operation is not None and item.operation is not expected_operation:
            raise VideoMetadataError("provenance operation does not match metadata")
        identity = (item.provider_key, item.external_id, item.field_name)
        if identity in seen:
            raise VideoMetadataError("provenance contains duplicates")
        seen.add(identity)
    provenance_field_set(values, available)
    return values


@dataclass(frozen=True, slots=True)
class VideoIdentifier:
    provider_key: str
    external_id: str
    catalog_number: str | None = None
    canonical_url: str | None = None

    def __post_init__(self) -> None:
        key, external_id = provider_scoped_identity(self.provider_key, self.external_id)
        object.__setattr__(self, "provider_key", key)
        object.__setattr__(self, "external_id", external_id)
        object.__setattr__(
            self,
            "catalog_number",
            optional_bounded_text(
                self.catalog_number,
                MAX_CATALOG_NUMBER_LENGTH,
                field="catalog_number",
            ),
        )
        object.__setattr__(self, "canonical_url", _validate_canonical_url(self.canonical_url))

    @property
    def identity(self) -> tuple[str, str]:
        return self.provider_key, self.external_id


@dataclass(frozen=True, slots=True)
class VideoPerson:
    provider_key: str
    external_id: str
    display_name: str
    role: VideoPersonRole
    alternate_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        key, external_id = provider_scoped_identity(self.provider_key, self.external_id)
        object.__setattr__(self, "provider_key", key)
        object.__setattr__(self, "external_id", external_id)
        object.__setattr__(self, "display_name", bounded_text(self.display_name, MAX_NAME_LENGTH, field="display_name"))
        _require_enum(self.role, VideoPersonRole, field="role")
        object.__setattr__(
            self,
            "alternate_names",
            bounded_text_tuple(
                self.alternate_names,
                MAX_ALTERNATE_NAMES,
                MAX_NAME_LENGTH,
                field="alternate_names",
            ),
        )

    @property
    def identity(self) -> tuple[str, str]:
        return self.provider_key, self.external_id


@dataclass(frozen=True, slots=True)
class VideoOrganization:
    provider_key: str
    external_id: str
    display_name: str
    organization_type: VideoOrganizationType

    def __post_init__(self) -> None:
        key, external_id = provider_scoped_identity(self.provider_key, self.external_id)
        object.__setattr__(self, "provider_key", key)
        object.__setattr__(self, "external_id", external_id)
        object.__setattr__(self, "display_name", bounded_text(self.display_name, MAX_NAME_LENGTH, field="display_name"))
        _require_enum(self.organization_type, VideoOrganizationType, field="organization_type")

    @property
    def identity(self) -> tuple[str, str]:
        return self.provider_key, self.external_id


@dataclass(frozen=True, slots=True)
class VideoSeries:
    provider_key: str
    external_id: str
    display_name: str

    def __post_init__(self) -> None:
        key, external_id = provider_scoped_identity(self.provider_key, self.external_id)
        object.__setattr__(self, "provider_key", key)
        object.__setattr__(self, "external_id", external_id)
        object.__setattr__(self, "display_name", bounded_text(self.display_name, MAX_NAME_LENGTH, field="display_name"))

    @property
    def identity(self) -> tuple[str, str]:
        return self.provider_key, self.external_id


@dataclass(frozen=True, slots=True)
class VideoTag:
    provider_key: str
    external_id: str
    raw_name: str
    normalized_name: str
    category: VideoTagCategory = VideoTagCategory.GENERAL

    def __post_init__(self) -> None:
        key, external_id = provider_scoped_identity(self.provider_key, self.external_id)
        object.__setattr__(self, "provider_key", key)
        object.__setattr__(self, "external_id", external_id)
        object.__setattr__(self, "raw_name", bounded_text(self.raw_name, MAX_NAME_LENGTH, field="raw_name"))
        object.__setattr__(self, "normalized_name", bounded_text(self.normalized_name, MAX_NAME_LENGTH, field="normalized_name"))
        _require_enum(self.category, VideoTagCategory, field="category")

    @property
    def identity(self) -> tuple[str, str]:
        return self.provider_key, self.external_id


@dataclass(frozen=True, slots=True)
class VideoRating:
    value: float
    scale_min: float
    scale_max: float
    vote_count: int | None = None

    def __post_init__(self) -> None:
        scale_min = finite_number(self.scale_min, field="scale_min")
        scale_max = finite_number(self.scale_max, field="scale_max")
        value = finite_number(self.value, minimum=scale_min, maximum=scale_max, field="value")
        if scale_max <= scale_min:
            raise VideoMetadataError("scale_max must be greater than scale_min")
        object.__setattr__(self, "scale_min", scale_min)
        object.__setattr__(self, "scale_max", scale_max)
        object.__setattr__(self, "value", value)
        if self.vote_count is not None and (
            not isinstance(self.vote_count, int)
            or isinstance(self.vote_count, bool)
            or self.vote_count < 0
        ):
            raise VideoMetadataError("vote_count must be non-negative")


@dataclass(frozen=True, slots=True)
class VideoAsset:
    provider_key: str
    asset_id: str
    kind: VideoAssetKind
    display_name: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: int | None = None
    requires_auth: bool = False
    downloadable: bool = False

    def __post_init__(self) -> None:
        key = bounded_text(self.provider_key, MAX_PROVIDER_KEY_LENGTH, field="provider_key")
        if _PROVIDER_KEY_PATTERN.fullmatch(key) is None:
            raise VideoMetadataError("provider_key has an invalid format")
        asset_id = bounded_text(self.asset_id, MAX_ASSET_ID_LENGTH, field="asset_id")
        if _ASSET_ID_PATTERN.fullmatch(asset_id) is None or ".." in asset_id:
            raise VideoMetadataError("asset_id must be an opaque identifier")
        object.__setattr__(self, "provider_key", key)
        object.__setattr__(self, "asset_id", asset_id)
        _require_enum(self.kind, VideoAssetKind, field="kind")
        object.__setattr__(self, "display_name", optional_bounded_text(self.display_name, MAX_ASSET_DISPLAY_NAME_LENGTH, field="display_name"))
        if self.mime_type is not None:
            mime_type = bounded_text(self.mime_type, MAX_MIME_TYPE_LENGTH, field="mime_type")
            if mime_type != mime_type.casefold() or _MIME_TYPE_PATTERN.fullmatch(mime_type) is None:
                raise VideoMetadataError("mime_type is invalid")
            object.__setattr__(self, "mime_type", mime_type)
        for field_name, value in (("width", self.width), ("height", self.height), ("duration_seconds", self.duration_seconds)):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value <= 0):
                raise VideoMetadataError(f"{field_name} must be a positive integer")
        if not isinstance(self.requires_auth, bool) or self.requires_auth:
            raise VideoMetadataError("requires_auth must be false")
        if not isinstance(self.downloadable, bool) or self.downloadable:
            raise VideoMetadataError("downloadable must be false")

    @property
    def identity(self) -> tuple[str, str]:
        return self.provider_key, self.asset_id

    @property
    def asset_identity(self) -> tuple[str, str]:
        return self.identity


@dataclass(frozen=True, slots=True)
class VideoMetadataProvenance:
    provider_key: str
    external_id: str
    operation: VideoProvenanceOperation
    field_name: str
    observed_at: datetime
    source_updated_at: datetime | None = None
    confidence: VideoConfidence = VideoConfidence.HIGH

    def __post_init__(self) -> None:
        key, external_id = provider_scoped_identity(self.provider_key, self.external_id)
        object.__setattr__(self, "provider_key", key)
        object.__setattr__(self, "external_id", external_id)
        _require_enum(self.operation, VideoProvenanceOperation, field="operation")
        field_name = bounded_text(self.field_name, MAX_FIELD_NAME_LENGTH, field="field_name")
        if _FIELD_NAME_PATTERN.fullmatch(field_name) is None:
            raise VideoMetadataError("field_name has an invalid format")
        object.__setattr__(self, "field_name", field_name)
        object.__setattr__(self, "observed_at", timezone_aware_utc(self.observed_at, field="observed_at"))
        object.__setattr__(self, "source_updated_at", _optional_datetime(self.source_updated_at, field="source_updated_at"))
        _require_enum(self.confidence, VideoConfidence, field="confidence")


_SEARCH_FIELD_ORDER = (
    "identifier",
    "title",
    "alternate_titles",
    "release_date",
    "performers",
    "studio",
    "tags",
    "cover",
    "summary",
)
_DETAIL_FIELD_ORDER = (
    "identifier",
    "title",
    "alternate_titles",
    "summary",
    "release_date",
    "duration_seconds",
    "performers",
    "director",
    "studio",
    "publisher",
    "series",
    "tags",
    "rating",
    "cover",
    "preview_images",
    "preview_video",
    "source_updated_at",
)


@dataclass(frozen=True, slots=True)
class VideoSearchResult:
    identifier: VideoIdentifier
    title: str
    alternate_titles: tuple[str, ...] = ()
    release_date: date | None = None
    performers: tuple[VideoPerson, ...] = ()
    studio: VideoOrganization | None = None
    tags: tuple[VideoTag, ...] = ()
    cover: VideoAsset | None = None
    summary: str | None = None
    available_fields: tuple[str, ...] | None = None
    provenance: tuple[VideoMetadataProvenance, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, VideoIdentifier):
            raise TypeError("identifier must be VideoIdentifier")
        object.__setattr__(self, "title", bounded_text(self.title, MAX_TITLE_LENGTH, field="title"))
        object.__setattr__(self, "alternate_titles", bounded_text_tuple(self.alternate_titles, MAX_ALTERNATE_TITLES, MAX_TITLE_LENGTH, field="alternate_titles"))
        object.__setattr__(self, "release_date", _optional_date(self.release_date, field="release_date"))
        performers = _validate_tuple_of(self.performers, VideoPerson, field="performers", maximum=MAX_PEOPLE)
        tags = _validate_tuple_of(self.tags, VideoTag, field="tags", maximum=MAX_TAGS)
        _reject_duplicate_identities(performers, field="performers")
        if any(person.role is not VideoPersonRole.PERFORMER for person in performers):
            raise VideoMetadataError("performers must use performer role")
        _reject_duplicate_identities(tags, field="tags")
        object.__setattr__(self, "performers", performers)
        object.__setattr__(self, "tags", tags)
        if self.studio is not None and not isinstance(self.studio, VideoOrganization):
            raise TypeError("studio must be VideoOrganization")
        if self.studio is not None and self.studio.identity[0] != self.identifier.provider_key:
            raise VideoMetadataError("studio provider does not match identifier")
        if self.cover is not None:
            if not isinstance(self.cover, VideoAsset):
                raise TypeError("cover must be VideoAsset")
            if self.cover.kind is not VideoAssetKind.COVER:
                raise VideoMetadataError("cover must have cover kind")
            if self.cover.provider_key != self.identifier.provider_key:
                raise VideoMetadataError("cover provider does not match identifier")
        object.__setattr__(self, "summary", optional_bounded_text(self.summary, MAX_SUMMARY_LENGTH, field="summary"))
        for value in (*performers, *tags):
            if value.provider_key != self.identifier.provider_key:
                raise VideoMetadataError("nested identity provider does not match identifier")
        actual = _derived_available_fields(
            {
                "identifier": self.identifier,
                "title": self.title,
                "alternate_titles": self.alternate_titles,
                "release_date": self.release_date,
                "performers": self.performers,
                "studio": self.studio,
                "tags": self.tags,
                "cover": self.cover,
                "summary": self.summary,
            },
            _SEARCH_FIELD_ORDER,
        )
        supplied = actual if self.available_fields is None else available_field_set(self.available_fields)
        if supplied != actual:
            raise VideoMetadataError("available_fields does not match actual fields")
        object.__setattr__(self, "available_fields", supplied)
        object.__setattr__(self, "provenance", _validate_provenance(self.provenance, identifier=self.identifier, available=supplied, expected_operation=VideoProvenanceOperation.SEARCH))

    @property
    def provider_key(self) -> str:
        return self.identifier.provider_key

    @property
    def external_id(self) -> str:
        return self.identifier.external_id


@dataclass(frozen=True, slots=True)
class VideoDetail:
    identifier: VideoIdentifier
    title: str
    alternate_titles: tuple[str, ...] = ()
    summary: str | None = None
    release_date: date | None = None
    duration_seconds: int | None = None
    performers: tuple[VideoPerson, ...] = ()
    director: VideoPerson | None = None
    studio: VideoOrganization | None = None
    publisher: VideoOrganization | None = None
    series: VideoSeries | None = None
    tags: tuple[VideoTag, ...] = ()
    rating: VideoRating | None = None
    cover: VideoAsset | None = None
    preview_images: tuple[VideoAsset, ...] = ()
    preview_video: VideoAsset | None = None
    source_updated_at: datetime | None = None
    available_fields: tuple[str, ...] | None = None
    provenance: tuple[VideoMetadataProvenance, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, VideoIdentifier):
            raise TypeError("identifier must be VideoIdentifier")
        object.__setattr__(self, "title", bounded_text(self.title, MAX_TITLE_LENGTH, field="title"))
        object.__setattr__(self, "alternate_titles", bounded_text_tuple(self.alternate_titles, MAX_ALTERNATE_TITLES, MAX_TITLE_LENGTH, field="alternate_titles"))
        object.__setattr__(self, "summary", optional_bounded_text(self.summary, MAX_SUMMARY_LENGTH, field="summary"))
        object.__setattr__(self, "release_date", _optional_date(self.release_date, field="release_date"))
        if self.duration_seconds is not None and (not isinstance(self.duration_seconds, int) or isinstance(self.duration_seconds, bool) or self.duration_seconds <= 0):
            raise VideoMetadataError("duration_seconds must be a positive integer")
        performers = _validate_tuple_of(self.performers, VideoPerson, field="performers", maximum=MAX_PEOPLE)
        tags = _validate_tuple_of(self.tags, VideoTag, field="tags", maximum=MAX_TAGS)
        preview_images = _validate_tuple_of(self.preview_images, VideoAsset, field="preview_images", maximum=MAX_PREVIEW_IMAGES)
        _reject_duplicate_identities(performers, field="performers")
        _reject_duplicate_identities(tags, field="tags")
        _reject_duplicate_identities(preview_images, field="preview_images")
        object.__setattr__(self, "performers", performers)
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "preview_images", preview_images)
        if self.director is not None and not isinstance(self.director, VideoPerson):
            raise TypeError("director must be VideoPerson")
        if self.director is not None and self.director.role is not VideoPersonRole.DIRECTOR:
            raise VideoMetadataError("director must use director role")
        for field_name, value, expected in (
            ("studio", self.studio, VideoOrganization),
            ("publisher", self.publisher, VideoOrganization),
            ("series", self.series, VideoSeries),
        ):
            if value is not None and not isinstance(value, expected):
                raise TypeError(f"{field_name} has an invalid type")
        if self.studio is not None and self.studio.organization_type is not VideoOrganizationType.STUDIO:
            raise VideoMetadataError("studio must use studio organization type")
        if self.publisher is not None and self.publisher.organization_type is not VideoOrganizationType.PUBLISHER:
            raise VideoMetadataError("publisher must use publisher organization type")
        if self.rating is not None and not isinstance(self.rating, VideoRating):
            raise TypeError("rating must be VideoRating")
        if self.cover is not None:
            if not isinstance(self.cover, VideoAsset) or self.cover.kind is not VideoAssetKind.COVER:
                raise VideoMetadataError("cover must have cover kind")
        if self.preview_video is not None:
            if not isinstance(self.preview_video, VideoAsset) or self.preview_video.kind is not VideoAssetKind.PREVIEW_VIDEO:
                raise VideoMetadataError("preview_video must have preview_video kind")
        if any(asset.kind is not VideoAssetKind.PREVIEW_IMAGE for asset in preview_images):
            raise VideoMetadataError("preview_images must have preview_image kind")
        nested = (*performers, *tags, *preview_images)
        if self.director is not None:
            nested += (self.director,)
        for value in nested:
            if value.provider_key != self.identifier.provider_key:
                raise VideoMetadataError("nested identity provider does not match identifier")
        if self.cover is not None and self.cover.provider_key != self.identifier.provider_key:
            raise VideoMetadataError("cover provider does not match identifier")
        if self.preview_video is not None and self.preview_video.provider_key != self.identifier.provider_key:
            raise VideoMetadataError("preview_video provider does not match identifier")
        for value in (self.studio, self.publisher, self.series):
            if value is not None and value.provider_key != self.identifier.provider_key:
                raise VideoMetadataError("nested identity provider does not match identifier")
        object.__setattr__(self, "source_updated_at", _optional_datetime(self.source_updated_at, field="source_updated_at"))
        actual = _derived_available_fields(
            {
                "identifier": self.identifier,
                "title": self.title,
                "alternate_titles": self.alternate_titles,
                "summary": self.summary,
                "release_date": self.release_date,
                "duration_seconds": self.duration_seconds,
                "performers": self.performers,
                "director": self.director,
                "studio": self.studio,
                "publisher": self.publisher,
                "series": self.series,
                "tags": self.tags,
                "rating": self.rating,
                "cover": self.cover,
                "preview_images": self.preview_images,
                "preview_video": self.preview_video,
                "source_updated_at": self.source_updated_at,
            },
            _DETAIL_FIELD_ORDER,
        )
        supplied = actual if self.available_fields is None else available_field_set(self.available_fields)
        if supplied != actual:
            raise VideoMetadataError("available_fields does not match actual fields")
        object.__setattr__(self, "available_fields", supplied)
        object.__setattr__(self, "provenance", _validate_provenance(self.provenance, identifier=self.identifier, available=supplied, expected_operation=VideoProvenanceOperation.DETAIL))

    @property
    def provider_key(self) -> str:
        return self.identifier.provider_key

    @property
    def external_id(self) -> str:
        return self.identifier.external_id


@dataclass(frozen=True, slots=True)
class VideoSearchPage:
    items: tuple[VideoSearchResult, ...]
    page: int
    page_size: int
    has_next: bool
    total: int | None = None
    query: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or not all(isinstance(item, VideoSearchResult) for item in self.items):
            raise TypeError("items must be a tuple of VideoSearchResult")
        if not isinstance(self.page, int) or isinstance(self.page, bool) or self.page < 1:
            raise VideoMetadataError("page must be positive")
        if not isinstance(self.page_size, int) or isinstance(self.page_size, bool) or not 1 <= self.page_size <= MAX_PAGE_SIZE:
            raise VideoMetadataError("page_size is outside the safe range")
        if len(self.items) > self.page_size:
            raise VideoMetadataError("items exceed page_size")
        if not isinstance(self.has_next, bool):
            raise TypeError("has_next must be a boolean")
        if self.total is not None and (not isinstance(self.total, int) or isinstance(self.total, bool) or self.total < 0):
            raise VideoMetadataError("total must be non-negative")
        object.__setattr__(self, "query", bounded_text(self.query, MAX_QUERY_LENGTH, field="query", allow_blank=True))
        if self.items:
            provider_keys = {item.provider_key for item in self.items}
            if len(provider_keys) != 1:
                raise VideoMetadataError("page items must share a provider")

    @property
    def results(self) -> tuple[VideoSearchResult, ...]:
        return self.items

    @property
    def has_more(self) -> bool:
        return self.has_next


@runtime_checkable
class VideoMetadataAdapter(Protocol):
    async def search(self, query: str, *, page: int, page_size: int) -> VideoSearchPage: ...

    async def detail(self, external_id: str) -> VideoDetail: ...

    async def asset_list(self, external_id: str) -> tuple[VideoAsset, ...]: ...


__all__ = [
    "AssetKind",
    "Confidence",
    "MAX_ALTERNATE_NAMES",
    "MAX_ALTERNATE_TITLES",
    "MAX_ASSET_ID_LENGTH",
    "MAX_AVAILABLE_FIELDS",
    "MAX_EXTERNAL_ID_LENGTH",
    "MAX_PAGE_SIZE",
    "MAX_PREVIEW_IMAGES",
    "MAX_QUERY_LENGTH",
    "MAX_TAGS",
    "OrganizationType",
    "PersonRole",
    "ProvenanceOperation",
    "TagCategory",
    "VideoAsset",
    "VideoAssetKind",
    "VideoConfidence",
    "VideoDetail",
    "VideoIdentifier",
    "VideoMetadataAdapter",
    "VideoMetadataError",
    "VideoMetadataProvenance",
    "VideoOrganization",
    "VideoOrganizationType",
    "VideoPerson",
    "VideoPersonRole",
    "VideoProvenanceOperation",
    "VideoRating",
    "VideoSearchPage",
    "VideoSearchResult",
    "VideoSeries",
    "VideoTag",
    "VideoTagCategory",
    "available_field_set",
    "bounded_text",
    "bounded_text_tuple",
    "finite_number",
    "optional_bounded_text",
    "provider_scoped_identity",
    "provenance_field_set",
    "timezone_aware_utc",
]
