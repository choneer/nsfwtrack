from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

MAX_PROVIDER_KEY_LENGTH = 64
MAX_EXTERNAL_ID_LENGTH = 512
MAX_CANONICAL_URL_LENGTH = 2048
MAX_TITLE_LENGTH = 500
MAX_SUMMARY_LENGTH = 20_000
MAX_NAME_LENGTH = 500
MAX_RESULT_TYPE_LENGTH = 64
MAX_ALTERNATE_TITLES = 50
MAX_CREATORS = 100
MAX_TAGS = 200
MAX_AVAILABLE_FIELDS = 64

_PROVIDER_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")


def _validate_text(
    value: str,
    *,
    field: str,
    maximum: int,
    allow_blank: bool = False,
) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not allow_blank and not value.strip():
        raise ValueError(f"{field} must not be blank")
    if len(value) > maximum:
        raise ValueError(f"{field} is too long")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field} contains control characters")


def _validate_optional_text(
    value: str | None,
    *,
    field: str,
    maximum: int,
) -> None:
    if value is not None:
        _validate_text(value, field=field, maximum=maximum)


def _validate_provider_key(value: str) -> None:
    _validate_text(
        value,
        field="provider_key",
        maximum=MAX_PROVIDER_KEY_LENGTH,
    )
    if _PROVIDER_KEY_PATTERN.fullmatch(value) is None:
        raise ValueError("provider_key has an invalid format")


def _validate_canonical_url(value: str) -> None:
    _validate_text(
        value,
        field="canonical_url",
        maximum=MAX_CANONICAL_URL_LENGTH,
    )
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("canonical_url is invalid") from exc
    if (
        value != value.strip()
        or any(character.isspace() for character in value)
        or "\\" in value
        or parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.fragment)
    ):
        raise ValueError("canonical_url must be credential-free HTTP/HTTPS")


def _validate_string_tuple(
    values: tuple[str, ...],
    *,
    field: str,
    maximum_items: int,
    maximum_length: int,
) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field} must be a tuple")
    if len(values) > maximum_items:
        raise ValueError(f"{field} has too many values")
    for value in values:
        _validate_text(value, field=field, maximum=maximum_length)


def _validate_aware_datetime(value: datetime | None, *, field: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SourceCreator:
    name: str
    external_id: str | None = None

    def __post_init__(self) -> None:
        _validate_text(self.name, field="creator.name", maximum=MAX_NAME_LENGTH)
        _validate_optional_text(
            self.external_id,
            field="creator.external_id",
            maximum=MAX_EXTERNAL_ID_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class SourceTag:
    name: str
    external_id: str | None = None

    def __post_init__(self) -> None:
        _validate_text(self.name, field="tag.name", maximum=MAX_NAME_LENGTH)
        _validate_optional_text(
            self.external_id,
            field="tag.external_id",
            maximum=MAX_EXTERNAL_ID_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class SourceSearchResult:
    provider_key: str
    external_id: str
    canonical_url: str
    title: str
    alternate_titles: tuple[str, ...] = ()
    summary: str | None = None
    release_date: date | None = None
    creators: tuple[SourceCreator, ...] = ()
    tags: tuple[SourceTag, ...] = ()
    source_updated_at: datetime | None = None
    result_type: str | None = None
    completeness: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_provider_key(self.provider_key)
        _validate_text(
            self.external_id,
            field="external_id",
            maximum=MAX_EXTERNAL_ID_LENGTH,
        )
        _validate_canonical_url(self.canonical_url)
        _validate_text(self.title, field="title", maximum=MAX_TITLE_LENGTH)
        _validate_string_tuple(
            self.alternate_titles,
            field="alternate_titles",
            maximum_items=MAX_ALTERNATE_TITLES,
            maximum_length=MAX_TITLE_LENGTH,
        )
        _validate_optional_text(
            self.summary,
            field="summary",
            maximum=MAX_SUMMARY_LENGTH,
        )
        if self.release_date is not None and (
            not isinstance(self.release_date, date)
            or isinstance(self.release_date, datetime)
        ):
            raise TypeError("release_date must be a date")
        if not isinstance(self.creators, tuple):
            raise TypeError("creators must be a tuple")
        if len(self.creators) > MAX_CREATORS or not all(
            isinstance(value, SourceCreator) for value in self.creators
        ):
            raise ValueError("creators is invalid")
        if not isinstance(self.tags, tuple):
            raise TypeError("tags must be a tuple")
        if len(self.tags) > MAX_TAGS or not all(
            isinstance(value, SourceTag) for value in self.tags
        ):
            raise ValueError("tags is invalid")
        _validate_aware_datetime(
            self.source_updated_at,
            field="source_updated_at",
        )
        _validate_optional_text(
            self.result_type,
            field="result_type",
            maximum=MAX_RESULT_TYPE_LENGTH,
        )
        _validate_string_tuple(
            self.completeness,
            field="completeness",
            maximum_items=MAX_AVAILABLE_FIELDS,
            maximum_length=MAX_RESULT_TYPE_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class SourceDetail:
    provider_key: str
    external_id: str
    stable_detail_id: str
    canonical_url: str
    title: str
    alternate_titles: tuple[str, ...] = ()
    summary: str | None = None
    release_date: date | None = None
    creators: tuple[SourceCreator, ...] = ()
    tags: tuple[SourceTag, ...] = ()
    source_updated_at: datetime | None = None
    result_type: str | None = None
    completeness: tuple[str, ...] = ()
    available_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        SourceSearchResult(
            provider_key=self.provider_key,
            external_id=self.external_id,
            canonical_url=self.canonical_url,
            title=self.title,
            alternate_titles=self.alternate_titles,
            summary=self.summary,
            release_date=self.release_date,
            creators=self.creators,
            tags=self.tags,
            source_updated_at=self.source_updated_at,
            result_type=self.result_type,
            completeness=self.completeness,
        )
        _validate_text(
            self.stable_detail_id,
            field="stable_detail_id",
            maximum=MAX_EXTERNAL_ID_LENGTH,
        )
        _validate_string_tuple(
            self.available_fields,
            field="available_fields",
            maximum_items=MAX_AVAILABLE_FIELDS,
            maximum_length=MAX_RESULT_TYPE_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class SourceSearchPage:
    provider_key: str
    query: str
    page: int
    page_size: int
    results: tuple[SourceSearchResult, ...]
    total: int | None = None
    has_more: bool | None = None
    warning: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        _validate_provider_key(self.provider_key)
        _validate_text(self.query, field="query", maximum=200)
        if not isinstance(self.page, int) or isinstance(self.page, bool) or self.page < 1:
            raise ValueError("page must be a positive integer")
        if (
            not isinstance(self.page_size, int)
            or isinstance(self.page_size, bool)
            or not 1 <= self.page_size <= 50
        ):
            raise ValueError("page_size must be between 1 and 50")
        if not isinstance(self.results, tuple) or not all(
            isinstance(result, SourceSearchResult) for result in self.results
        ):
            raise TypeError("results must be a tuple of SourceSearchResult")
        if any(result.provider_key != self.provider_key for result in self.results):
            raise ValueError("result provider_key does not match the page")
        if self.total is not None and (
            not isinstance(self.total, int)
            or isinstance(self.total, bool)
            or self.total < 0
        ):
            raise ValueError("total must be a non-negative integer")
        if self.has_more is not None and not isinstance(self.has_more, bool):
            raise TypeError("has_more must be a boolean")
        if self.total is None and self.has_more is None:
            raise ValueError("total or has_more must be provided")
        _validate_optional_text(
            self.warning,
            field="warning",
            maximum=MAX_SUMMARY_LENGTH,
        )
        _validate_optional_text(
            self.error_code,
            field="error_code",
            maximum=MAX_RESULT_TYPE_LENGTH,
        )


@runtime_checkable
class SourceAdapter(Protocol):
    key: str
    display_name: str

    async def search(
        self,
        query: str,
        *,
        page: int,
        page_size: int,
    ) -> SourceSearchPage: ...

    async def fetch_detail(self, external_id: str) -> SourceDetail: ...
