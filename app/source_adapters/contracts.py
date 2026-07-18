from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
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
MAX_CONTENT_SCOPE_LENGTH = 500
MAX_ASSET_ID_LENGTH = 512
MAX_ASSET_DISPLAY_NAME_LENGTH = 500
MAX_MIME_TYPE_LENGTH = 255
MAX_PROVIDER_ERROR_RETRY_SECONDS = 3600

_PROVIDER_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_MIME_TYPE_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/"
    r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}"
)


class ProviderCapabilityLayer(str, Enum):
    METADATA = "metadata"
    AUTH = "auth"
    DISCOVERY = "discovery"
    ASSET = "asset"
    DOWNLOAD = "download"


class ProviderOperation(str, Enum):
    SEARCH = "search"
    DETAIL = "detail"
    AUTH_TEST = "auth_test"
    AUTH_LOGIN = "auth_login"
    AUTH_REFRESH = "auth_refresh"
    AUTH_REVOKE = "auth_revoke"
    AUTH_LOGOUT = "auth_logout"
    DISCOVER = "discover"
    ASSET_LIST = "asset_list"
    ASSET_RESOLVE = "asset_resolve"
    DOWNLOAD = "download"

    @property
    def layer(self) -> ProviderCapabilityLayer:
        if self in {ProviderOperation.SEARCH, ProviderOperation.DETAIL}:
            return ProviderCapabilityLayer.METADATA
        if self in {
            ProviderOperation.AUTH_TEST,
            ProviderOperation.AUTH_LOGIN,
            ProviderOperation.AUTH_REFRESH,
            ProviderOperation.AUTH_REVOKE,
            ProviderOperation.AUTH_LOGOUT,
        }:
            return ProviderCapabilityLayer.AUTH
        if self is ProviderOperation.DISCOVER:
            return ProviderCapabilityLayer.DISCOVERY
        if self in {ProviderOperation.ASSET_LIST, ProviderOperation.ASSET_RESOLVE}:
            return ProviderCapabilityLayer.ASSET
        return ProviderCapabilityLayer.DOWNLOAD


class ProviderAuthMode(str, Enum):
    NONE = "none"
    API_TOKEN = "api_token"
    OAUTH = "oauth"
    USERNAME_PASSWORD = "username_password"
    SESSION_COOKIE = "session_cookie"


class ProviderAuthState(str, Enum):
    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"
    REVOKED = "revoked"
    UNKNOWN = "unknown"


class SourceAssetKind(str, Enum):
    COVER = "cover"
    PREVIEW = "preview"
    MEDIA = "media"
    ATTACHMENT = "attachment"


class SourceAssetChecksumAlgorithm(str, Enum):
    SHA256 = "sha256"
    SHA512 = "sha512"


class ProviderErrorCode(str, Enum):
    CAPABILITY_NOT_SUPPORTED = "capability_not_supported"
    INVALID_CAPABILITY_MANIFEST = "invalid_capability_manifest"
    AUTH_NOT_CONFIGURED = "auth_not_configured"
    AUTH_INVALID = "auth_invalid"
    AUTH_EXPIRED = "auth_expired"
    AUTH_REVOKED = "auth_revoked"
    AUTH_FAILED = "auth_failed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "rate_limited"
    INVALID_PROVIDER_PAYLOAD = "invalid_provider_payload"
    ASSET_NOT_FOUND = "asset_not_found"
    ASSET_NOT_DOWNLOADABLE = "asset_not_downloadable"
    ASSET_LOCATOR_INVALID = "asset_locator_invalid"
    ASSET_HOST_NOT_ALLOWED = "asset_host_not_allowed"
    DOWNLOAD_TOO_LARGE = "download_too_large"
    DOWNLOAD_TYPE_REJECTED = "download_type_rejected"
    DOWNLOAD_INTEGRITY_FAILED = "download_integrity_failed"
    DOWNLOAD_CANCELLED = "download_cancelled"
    DOWNLOAD_PUBLISH_FAILED = "download_publish_failed"
    DOWNLOAD_LINK_FAILED = "download_link_failed"
    DOWNLOAD_CLEANUP_FAILED = "download_cleanup_failed"
    DOWNLOAD_OUTCOME_UNKNOWN = "download_outcome_unknown"


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


def _validate_operation_tuple(
    values: tuple[ProviderOperation, ...],
    *,
    layer: ProviderCapabilityLayer,
    field: str,
) -> None:
    if not isinstance(values, tuple) or not all(
        isinstance(value, ProviderOperation) for value in values
    ):
        raise TypeError(f"{field} must be a tuple of ProviderOperation")
    if len(set(values)) != len(values):
        raise ValueError(f"{field} contains duplicates")
    if any(value.layer is not layer for value in values):
        raise ValueError(f"{field} contains an operation from another layer")


def _validate_enum_tuple(
    values: tuple[Enum, ...],
    *,
    enum_type: type[Enum],
    field: str,
) -> None:
    if not isinstance(values, tuple) or not all(
        isinstance(value, enum_type) for value in values
    ):
        raise TypeError(f"{field} has invalid values")
    if len(set(values)) != len(values):
        raise ValueError(f"{field} contains duplicates")


@dataclass(frozen=True, slots=True)
class ProviderError:
    code: ProviderErrorCode
    provider_key: str
    operation: ProviderOperation | None = None
    auth_state: ProviderAuthState | None = None
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ProviderErrorCode):
            raise TypeError("code must be ProviderErrorCode")
        _validate_provider_key(self.provider_key)
        if self.operation is not None and not isinstance(
            self.operation,
            ProviderOperation,
        ):
            raise TypeError("operation must be ProviderOperation")
        if self.auth_state is not None and not isinstance(
            self.auth_state,
            ProviderAuthState,
        ):
            raise TypeError("auth_state must be ProviderAuthState")
        if self.retry_after_seconds is not None and (
            not isinstance(self.retry_after_seconds, int)
            or isinstance(self.retry_after_seconds, bool)
            or not 0
            <= self.retry_after_seconds
            <= MAX_PROVIDER_ERROR_RETRY_SECONDS
        ):
            raise ValueError("retry_after_seconds is outside the safe range")


class ProviderAdapterError(RuntimeError):
    def __init__(self, error: ProviderError) -> None:
        self.error = error
        super().__init__(error.code.value)


@dataclass(frozen=True, slots=True)
class MetadataCapabilities:
    operations: tuple[ProviderOperation, ...] = ()

    def __post_init__(self) -> None:
        _validate_operation_tuple(
            self.operations,
            layer=ProviderCapabilityLayer.METADATA,
            field="metadata.operations",
        )


@dataclass(frozen=True, slots=True)
class AuthCapabilities:
    modes: tuple[ProviderAuthMode, ...] = (ProviderAuthMode.NONE,)
    operations: tuple[ProviderOperation, ...] = ()

    def __post_init__(self) -> None:
        _validate_enum_tuple(
            self.modes,
            enum_type=ProviderAuthMode,
            field="auth.modes",
        )
        if not self.modes:
            raise ValueError("auth.modes must not be empty")
        _validate_operation_tuple(
            self.operations,
            layer=ProviderCapabilityLayer.AUTH,
            field="auth.operations",
        )
        if self.operations and self.modes == (ProviderAuthMode.NONE,):
            raise ValueError("auth operations require a credentialed auth mode")


@dataclass(frozen=True, slots=True)
class DiscoveryCapabilities:
    operations: tuple[ProviderOperation, ...] = ()

    def __post_init__(self) -> None:
        _validate_operation_tuple(
            self.operations,
            layer=ProviderCapabilityLayer.DISCOVERY,
            field="discovery.operations",
        )


@dataclass(frozen=True, slots=True)
class AssetCapabilities:
    operations: tuple[ProviderOperation, ...] = ()
    kinds: tuple[SourceAssetKind, ...] = ()

    def __post_init__(self) -> None:
        _validate_operation_tuple(
            self.operations,
            layer=ProviderCapabilityLayer.ASSET,
            field="assets.operations",
        )
        _validate_enum_tuple(
            self.kinds,
            enum_type=SourceAssetKind,
            field="assets.kinds",
        )
        if bool(self.operations) != bool(self.kinds):
            raise ValueError("asset operations and kinds must be declared together")


@dataclass(frozen=True, slots=True)
class DownloadCapabilities:
    operations: tuple[ProviderOperation, ...] = ()
    kinds: tuple[SourceAssetKind, ...] = ()

    def __post_init__(self) -> None:
        _validate_operation_tuple(
            self.operations,
            layer=ProviderCapabilityLayer.DOWNLOAD,
            field="downloads.operations",
        )
        _validate_enum_tuple(
            self.kinds,
            enum_type=SourceAssetKind,
            field="downloads.kinds",
        )
        if bool(self.operations) != bool(self.kinds):
            raise ValueError("download operations and kinds must be declared together")


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider_key: str
    display_name: str
    content_scope: str
    metadata: MetadataCapabilities = MetadataCapabilities()
    auth: AuthCapabilities = AuthCapabilities()
    discovery: DiscoveryCapabilities = DiscoveryCapabilities()
    assets: AssetCapabilities = AssetCapabilities()
    downloads: DownloadCapabilities = DownloadCapabilities()
    attribution_required: bool = False

    def __post_init__(self) -> None:
        _validate_provider_key(self.provider_key)
        _validate_text(
            self.display_name,
            field="display_name",
            maximum=MAX_NAME_LENGTH,
        )
        _validate_text(
            self.content_scope,
            field="content_scope",
            maximum=MAX_CONTENT_SCOPE_LENGTH,
        )
        for value, expected, field in (
            (self.metadata, MetadataCapabilities, "metadata"),
            (self.auth, AuthCapabilities, "auth"),
            (self.discovery, DiscoveryCapabilities, "discovery"),
            (self.assets, AssetCapabilities, "assets"),
            (self.downloads, DownloadCapabilities, "downloads"),
        ):
            if not isinstance(value, expected):
                raise TypeError(f"{field} has an invalid capability type")
        if not isinstance(self.attribution_required, bool):
            raise TypeError("attribution_required must be a boolean")
        if not self.operations:
            raise ValueError("provider must declare at least one operation")

    @property
    def operations(self) -> tuple[ProviderOperation, ...]:
        return (
            *self.metadata.operations,
            *self.auth.operations,
            *self.discovery.operations,
            *self.assets.operations,
            *self.downloads.operations,
        )

    @property
    def auth_modes(self) -> tuple[ProviderAuthMode, ...]:
        return self.auth.modes

    def supports(self, operation: ProviderOperation) -> bool:
        if not isinstance(operation, ProviderOperation):
            return False
        return operation in self.operations

    def require(self, operation: ProviderOperation) -> None:
        if self.supports(operation):
            return
        checked_operation = (
            operation if isinstance(operation, ProviderOperation) else None
        )
        raise ProviderAdapterError(
            ProviderError(
                ProviderErrorCode.CAPABILITY_NOT_SUPPORTED,
                self.provider_key,
                checked_operation,
            )
        )


@dataclass(frozen=True, slots=True)
class ProviderAuthStatus:
    provider_key: str
    state: ProviderAuthState
    mode: ProviderAuthMode | None = None
    checked_at: datetime | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        _validate_provider_key(self.provider_key)
        if not isinstance(self.state, ProviderAuthState):
            raise TypeError("state must be ProviderAuthState")
        if self.mode is not None and not isinstance(self.mode, ProviderAuthMode):
            raise TypeError("mode must be ProviderAuthMode")
        if self.mode is None and self.state is not ProviderAuthState.NOT_CONFIGURED:
            raise ValueError("configured auth states require an auth mode")
        if self.mode is ProviderAuthMode.NONE and self.state in {
            ProviderAuthState.CONFIGURED,
            ProviderAuthState.EXPIRED,
            ProviderAuthState.INVALID,
            ProviderAuthState.REVOKED,
        }:
            raise ValueError("credential states require a credentialed auth mode")
        _validate_aware_datetime(self.checked_at, field="checked_at")
        _validate_aware_datetime(self.expires_at, field="expires_at")
        if (
            self.checked_at is not None
            and self.expires_at is not None
            and self.expires_at < self.checked_at
        ):
            raise ValueError("expires_at must not precede checked_at")
        if self.state is ProviderAuthState.VALID and self.checked_at is None:
            raise ValueError("valid auth state requires checked_at")
        if self.state is ProviderAuthState.EXPIRED and self.expires_at is None:
            raise ValueError("expired auth state requires expires_at")


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
class SourceAsset:
    provider_key: str
    external_id: str
    asset_id: str
    kind: SourceAssetKind
    display_name: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    checksum_algorithm: SourceAssetChecksumAlgorithm | None = None
    checksum_value: str | None = None
    requires_auth: bool = False
    downloadable: bool = False

    def __post_init__(self) -> None:
        _validate_provider_key(self.provider_key)
        _validate_text(
            self.external_id,
            field="external_id",
            maximum=MAX_EXTERNAL_ID_LENGTH,
        )
        _validate_text(
            self.asset_id,
            field="asset_id",
            maximum=MAX_ASSET_ID_LENGTH,
        )
        if (
            "://" in self.asset_id
            or self.asset_id.startswith("//")
            or "\\" in self.asset_id
            or any(character.isspace() for character in self.asset_id)
        ):
            raise ValueError("asset_id must be an opaque identifier")
        if not isinstance(self.kind, SourceAssetKind):
            raise TypeError("kind must be SourceAssetKind")
        _validate_optional_text(
            self.display_name,
            field="display_name",
            maximum=MAX_ASSET_DISPLAY_NAME_LENGTH,
        )
        if self.mime_type is not None:
            _validate_text(
                self.mime_type,
                field="mime_type",
                maximum=MAX_MIME_TYPE_LENGTH,
            )
            if (
                self.mime_type != self.mime_type.casefold()
                or _MIME_TYPE_PATTERN.fullmatch(self.mime_type) is None
            ):
                raise ValueError("mime_type is invalid")
        if self.size_bytes is not None and (
            not isinstance(self.size_bytes, int)
            or isinstance(self.size_bytes, bool)
            or self.size_bytes < 0
        ):
            raise ValueError("size_bytes must be a non-negative integer")
        if self.checksum_algorithm is not None and not isinstance(
            self.checksum_algorithm,
            SourceAssetChecksumAlgorithm,
        ):
            raise TypeError("checksum_algorithm is invalid")
        if self.checksum_value is None:
            if self.checksum_algorithm is not None:
                raise ValueError("checksum_value is required with checksum_algorithm")
        else:
            _validate_text(
                self.checksum_value,
                field="checksum_value",
                maximum=128,
            )
            if (
                not self.checksum_value.isascii()
                or self.checksum_value != self.checksum_value.casefold()
                or any(
                    character not in "0123456789abcdef"
                    for character in self.checksum_value
                )
            ):
                raise ValueError("checksum_value must be hexadecimal")
            expected_length = {
                SourceAssetChecksumAlgorithm.SHA256: 64,
                SourceAssetChecksumAlgorithm.SHA512: 128,
            }.get(self.checksum_algorithm)
            if expected_length is None or len(self.checksum_value) != expected_length:
                raise ValueError("checksum_value length does not match its algorithm")
        if not isinstance(self.requires_auth, bool):
            raise TypeError("requires_auth must be a boolean")
        if not isinstance(self.downloadable, bool):
            raise TypeError("downloadable must be a boolean")


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


class ProviderAdapter(Protocol):
    key: str
    display_name: str
    capabilities: ProviderCapabilities


@runtime_checkable
class SourceMetadataAdapter(ProviderAdapter, Protocol):

    async def search(
        self,
        query: str,
        *,
        page: int,
        page_size: int,
    ) -> SourceSearchPage: ...

    async def fetch_detail(self, external_id: str) -> SourceDetail: ...


@runtime_checkable
class ProviderAuthAdapter(ProviderAdapter, Protocol):
    async def get_auth_status(self) -> ProviderAuthStatus: ...


@runtime_checkable
class ProviderDiscoveryAdapter(ProviderAdapter, Protocol):
    async def discover(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[SourceSearchResult, ...]: ...


@runtime_checkable
class ProviderAssetAdapter(ProviderAdapter, Protocol):
    async def list_assets(self, external_id: str) -> tuple[SourceAsset, ...]: ...


@runtime_checkable
class ProviderDownloadAdapter(ProviderAdapter, Protocol):
    def supports_download(self, asset: SourceAsset) -> bool: ...


SourceAdapter = SourceMetadataAdapter
