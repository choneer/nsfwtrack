"""Immutable contracts for Provider-neutral video search orchestration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.source_adapters.contracts import ProviderErrorCode, ProviderOperation
from app.source_adapters.package import ProviderPackageErrorCode
from app.video_metadata.contracts import (
    MAX_PAGE_SIZE,
    MAX_QUERY_LENGTH,
    VideoAsset,
    VideoDetail,
    VideoSearchPage,
    bounded_text,
    provider_scoped_identity,
    timezone_aware_utc,
)


MAX_SEARCH_PROVIDER_TEXT_LENGTH = 2_000
MAX_ASSET_LIST_ITEMS = 64

SEARCH_OPERATIONS = (
    ProviderOperation.SEARCH,
    ProviderOperation.DETAIL,
    ProviderOperation.ASSET_LIST,
)
_SEARCH_OPERATION_SET = frozenset(SEARCH_OPERATIONS)
_URL_SCHEME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")


def _provider_key(value: str) -> str:
    key, _ = provider_scoped_identity(value, "request")
    return key


def _external_identity(provider_key: str, external_id: str) -> tuple[str, str]:
    key, normalized = provider_scoped_identity(provider_key, external_id)
    if (
        "/" in normalized
        or "\\" in normalized
        or ".." in normalized
        or _URL_SCHEME_PATTERN.match(normalized) is not None
    ):
        raise ValueError("external_id must be an opaque identifier")
    return key, normalized


def _operation_authority(values: tuple[ProviderOperation, ...]) -> None:
    if type(values) is not tuple or not all(
        isinstance(value, ProviderOperation) for value in values
    ):
        raise TypeError("operations must be a ProviderOperation tuple")
    if (
        not values
        or len(set(values)) != len(values)
        or any(value not in _SEARCH_OPERATION_SET for value in values)
    ):
        raise ValueError("operations contain invalid search authority")


def _positive_int(value: int, *, field: str, maximum: int | None = None) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field} exceeds the safe limit")


@dataclass(frozen=True, slots=True)
class SearchProviderDescriptor:
    provider_key: str
    display_name: str
    content_scope: str
    operations: tuple[ProviderOperation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_key", _provider_key(self.provider_key))
        object.__setattr__(
            self,
            "display_name",
            bounded_text(
                self.display_name,
                MAX_SEARCH_PROVIDER_TEXT_LENGTH,
                field="display_name",
            ),
        )
        object.__setattr__(
            self,
            "content_scope",
            bounded_text(
                self.content_scope,
                MAX_SEARCH_PROVIDER_TEXT_LENGTH,
                field="content_scope",
            ),
        )
        _operation_authority(self.operations)


@dataclass(frozen=True, slots=True)
class VideoSearchRequest:
    provider_key: str
    query: str
    page: int
    page_size: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_key", _provider_key(self.provider_key))
        object.__setattr__(
            self,
            "query",
            bounded_text(self.query, MAX_QUERY_LENGTH, field="query"),
        )
        _positive_int(self.page, field="page")
        _positive_int(self.page_size, field="page_size", maximum=MAX_PAGE_SIZE)


@dataclass(frozen=True, slots=True)
class VideoDetailRequest:
    provider_key: str
    external_id: str

    def __post_init__(self) -> None:
        key, external_id = _external_identity(self.provider_key, self.external_id)
        object.__setattr__(self, "provider_key", key)
        object.__setattr__(self, "external_id", external_id)


@dataclass(frozen=True, slots=True)
class VideoAssetListRequest:
    provider_key: str
    external_id: str

    def __post_init__(self) -> None:
        key, external_id = _external_identity(self.provider_key, self.external_id)
        object.__setattr__(self, "provider_key", key)
        object.__setattr__(self, "external_id", external_id)


class ProviderSearchServiceErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    PROVIDER_NOT_AVAILABLE = "provider_not_available"
    OPERATION_NOT_APPROVED = "operation_not_approved"
    ADAPTER_MISMATCH = "adapter_mismatch"
    INVALID_RESULT = "invalid_result"
    PROVIDER_ERROR = "provider_error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


ProviderSearchCauseCode = ProviderErrorCode | ProviderPackageErrorCode


@dataclass(frozen=True, slots=True)
class ProviderSearchServiceError(RuntimeError):
    code: ProviderSearchServiceErrorCode
    cause_code: ProviderSearchCauseCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ProviderSearchServiceErrorCode):
            raise TypeError("code must be ProviderSearchServiceErrorCode")
        if self.cause_code is not None and not isinstance(
            self.cause_code,
            (ProviderErrorCode, ProviderPackageErrorCode),
        ):
            raise TypeError("cause_code must be a stable Provider error code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        if self.cause_code is None:
            return f"ProviderSearchServiceError(code={self.code.value!r})"
        return (
            "ProviderSearchServiceError("
            f"code={self.code.value!r}, cause_code={self.cause_code.value!r})"
        )


def _received_at(value: datetime) -> datetime:
    return timezone_aware_utc(value, field="received_at")


@dataclass(frozen=True, slots=True)
class VideoSearchEnvelope:
    provider: SearchProviderDescriptor
    request: VideoSearchRequest
    page: VideoSearchPage
    received_at: datetime

    def __post_init__(self) -> None:
        if type(self.provider) is not SearchProviderDescriptor:
            raise TypeError("provider must be SearchProviderDescriptor")
        if type(self.request) is not VideoSearchRequest:
            raise TypeError("request must be VideoSearchRequest")
        if type(self.page) is not VideoSearchPage:
            raise TypeError("page must be VideoSearchPage")
        if self.provider.provider_key != self.request.provider_key:
            raise ValueError("provider does not match request")
        if ProviderOperation.SEARCH not in self.provider.operations:
            raise ValueError("provider does not approve search")
        if (
            self.page.page != self.request.page
            or self.page.page_size != self.request.page_size
            or self.page.query != self.request.query
        ):
            raise ValueError("page does not match request")
        if any(
            item.provider_key != self.request.provider_key
            for item in self.page.items
        ):
            raise ValueError("search result provider does not match request")
        object.__setattr__(self, "received_at", _received_at(self.received_at))


@dataclass(frozen=True, slots=True)
class VideoDetailEnvelope:
    provider: SearchProviderDescriptor
    request: VideoDetailRequest
    detail: VideoDetail
    received_at: datetime

    def __post_init__(self) -> None:
        if type(self.provider) is not SearchProviderDescriptor:
            raise TypeError("provider must be SearchProviderDescriptor")
        if type(self.request) is not VideoDetailRequest:
            raise TypeError("request must be VideoDetailRequest")
        if type(self.detail) is not VideoDetail:
            raise TypeError("detail must be VideoDetail")
        if self.provider.provider_key != self.request.provider_key:
            raise ValueError("provider does not match request")
        if ProviderOperation.DETAIL not in self.provider.operations:
            raise ValueError("provider does not approve detail")
        if (
            self.detail.provider_key != self.request.provider_key
            or self.detail.external_id != self.request.external_id
        ):
            raise ValueError("detail identity does not match request")
        object.__setattr__(self, "received_at", _received_at(self.received_at))


@dataclass(frozen=True, slots=True)
class VideoAssetListEnvelope:
    provider: SearchProviderDescriptor
    request: VideoAssetListRequest
    assets: tuple[VideoAsset, ...]
    received_at: datetime

    def __post_init__(self) -> None:
        if type(self.provider) is not SearchProviderDescriptor:
            raise TypeError("provider must be SearchProviderDescriptor")
        if type(self.request) is not VideoAssetListRequest:
            raise TypeError("request must be VideoAssetListRequest")
        if type(self.assets) is not tuple or not all(
            type(asset) is VideoAsset for asset in self.assets
        ):
            raise TypeError("assets must be a VideoAsset tuple")
        if len(self.assets) > MAX_ASSET_LIST_ITEMS:
            raise ValueError("assets exceed the safe limit")
        if self.provider.provider_key != self.request.provider_key:
            raise ValueError("provider does not match request")
        if ProviderOperation.ASSET_LIST not in self.provider.operations:
            raise ValueError("provider does not approve asset_list")
        if any(
            asset.provider_key != self.request.provider_key
            for asset in self.assets
        ):
            raise ValueError("asset provider does not match request")
        identities = tuple(asset.identity for asset in self.assets)
        if len(identities) != len(set(identities)):
            raise ValueError("assets contain duplicate identities")
        object.__setattr__(self, "received_at", _received_at(self.received_at))


__all__ = [
    "MAX_ASSET_LIST_ITEMS",
    "ProviderSearchCauseCode",
    "ProviderSearchServiceError",
    "ProviderSearchServiceErrorCode",
    "SEARCH_OPERATIONS",
    "SearchProviderDescriptor",
    "VideoAssetListEnvelope",
    "VideoAssetListRequest",
    "VideoDetailEnvelope",
    "VideoDetailRequest",
    "VideoSearchEnvelope",
    "VideoSearchRequest",
]
