from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from app.source_adapters.contracts import (
    ProviderAuthMode,
    ProviderCapabilities,
    ProviderCapabilityLayer,
    ProviderOperation,
    SourceAssetKind,
    _validate_provider_key,
)
from app.source_adapters.registry import (
    MAX_PAGE_SIZE,
    MAX_RESPONSE_BYTES,
    BusinessParameter,
    CookiePolicy,
    HttpMethod,
    JsonTopLevel,
    ProviderEndpoint,
    RedirectPolicy,
    RequestEncoding,
    ResponseKind,
    _validate_content_types,
    _validate_hostname,
    _validate_identifier,
    _validate_parameter_mapping,
    _validate_path_template,
)

APPROVAL_FORMAT_VERSION = 1
MAX_APPROVAL_ID_LENGTH = 128
MAX_APPROVAL_TEXT_LENGTH = 2_000
MAX_APPROVAL_HOSTS = 64
MAX_APPROVAL_OPERATIONS = len(ProviderOperation)
MAX_APPROVAL_PAYLOAD_DEPTH = 16
MAX_APPROVAL_PAYLOAD_NODES = 4_096
MAX_APPROVED_DOWNLOAD_BYTES = 1024 * 1024 * 1024
APPROVED_CONNECT_TIMEOUT_SECONDS = 3.0
APPROVED_TOTAL_TIMEOUT_SECONDS = 10.0
MAX_APPROVED_CONNECT_TIMEOUT_SECONDS = 60.0
MAX_APPROVED_TOTAL_TIMEOUT_SECONDS = 300.0
MAX_APPROVED_HEADER_VALUE_LENGTH = 512

_APPROVAL_ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,127}")
_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "authorization",
        "client_secret",
        "cookie",
        "cookie_jar",
        "cookie_value",
        "password",
        "password_value",
        "secret",
        "secret_value",
        "session_cookie",
        "token",
        "token_value",
        "access_token",
        "refresh_token",
    }
)
_SENSITIVE_FIELD_SUFFIXES = (
    "_cookie_value",
    "_password_value",
    "_secret_value",
    "_token_value",
)
_HEADER_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,63}")
_FORBIDDEN_APPROVED_HEADER_NAMES = frozenset(
    {
        "accept",
        "accept-encoding",
        "authorization",
        "connection",
        "content-length",
        "content-type",
        "cookie",
        "host",
        "proxy-authorization",
        "set-cookie",
        "transfer-encoding",
    }
)
_CREDENTIAL_HEADER_NAME_MARKERS = (
    "api-key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "session",
    "token",
)
_AUTHENTICATED_HEADER_VALUE_PATTERN = re.compile(
    r"^(?:bearer|basic|token|apikey)(?:\s|$)",
    re.IGNORECASE,
)
_ACTIVATION_SUPPORTED_OPERATIONS = frozenset(
    {
        ProviderOperation.SEARCH,
        ProviderOperation.DETAIL,
        ProviderOperation.ASSET_LIST,
    }
)


class ProviderApprovalScope(str, Enum):
    PRODUCTION = "production"
    TEST_FIXTURE = "test_fixture"


class ApprovedHostPurpose(str, Enum):
    METADATA = "metadata"
    AUTH = "auth"
    ASSET = "asset"


class ApprovalAttributionPolicy(str, Enum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"


class ApprovedErrorMappingProfile(str, Enum):
    SHARED_OUTBOUND_V1 = "shared_outbound_v1"


class ApprovedRawPayloadRetention(str, Enum):
    DISCARD = "discard"
    TEST_FIXTURE_ONLY = "test_fixture_only"


class ApprovalValidationErrorCode(str, Enum):
    INVALID = "approval_invalid"
    INCOMPLETE = "approval_incomplete"
    PROVIDER_MISMATCH = "approval_provider_mismatch"
    CAPABILITY_MISMATCH = "approval_capability_mismatch"
    OPERATION_MISMATCH = "approval_operation_mismatch"
    HOST_MISMATCH = "approval_host_mismatch"
    AUTH_MISMATCH = "approval_auth_mismatch"
    ASSET_POLICY_MISMATCH = "approval_asset_policy_mismatch"
    DOWNLOAD_POLICY_MISMATCH = "approval_download_policy_mismatch"
    CONTAINS_SECRET = "approval_contains_secret"


class ApprovalValidationError(ValueError):
    def __init__(self, code: ApprovalValidationErrorCode) -> None:
        if not isinstance(code, ApprovalValidationErrorCode):
            raise TypeError("code must be ApprovalValidationErrorCode")
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class ApprovedFixedHeader:
    name: str
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or _HEADER_NAME_PATTERN.fullmatch(self.name) is None
        ):
            raise ValueError("approved fixed header name is invalid")
        normalized = self.name.casefold()
        if (
            normalized in _FORBIDDEN_APPROVED_HEADER_NAMES
            or any(
                marker in normalized for marker in _CREDENTIAL_HEADER_NAME_MARKERS
            )
            or any(
                segment in {"auth", "authentication"}
                for segment in normalized.split("-")
            )
        ):
            raise ValueError("approved fixed header name is credential-like or forbidden")
        if (
            not isinstance(self.value, str)
            or not self.value
            or len(self.value) > MAX_APPROVED_HEADER_VALUE_LENGTH
            or any(not 32 <= ord(character) <= 126 for character in self.value)
        ):
            raise ValueError("approved fixed header value is invalid")
        if _AUTHENTICATED_HEADER_VALUE_PATTERN.match(self.value):
            raise ValueError("approved fixed header value must not carry authentication")


@dataclass(frozen=True, slots=True)
class ApprovedTimeoutPolicy:
    connect_timeout_seconds: float = APPROVED_CONNECT_TIMEOUT_SECONDS
    total_timeout_seconds: float = APPROVED_TOTAL_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        for value, field, maximum in (
            (
                self.connect_timeout_seconds,
                "connect_timeout_seconds",
                MAX_APPROVED_CONNECT_TIMEOUT_SECONDS,
            ),
            (
                self.total_timeout_seconds,
                "total_timeout_seconds",
                MAX_APPROVED_TOTAL_TIMEOUT_SECONDS,
            ),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{field} must be a finite number")
            if not math.isfinite(float(value)) or not 0 < float(value) <= maximum:
                raise ValueError(f"{field} is outside the safe range")
        if float(self.total_timeout_seconds) < float(self.connect_timeout_seconds):
            raise ValueError("total timeout must not be less than connect timeout")


def _bounded_text(value: str, *, field: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not value.strip():
        raise ValueError(f"{field} must not be blank")
    if len(value) > MAX_APPROVAL_TEXT_LENGTH:
        raise ValueError(f"{field} is too long")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field} contains control characters")


def _validate_identifier_tuple(values: tuple[str, ...], *, field: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field} must be a tuple")
    if len(set(values)) != len(values):
        raise ValueError(f"{field} contains duplicates")
    for value in values:
        _validate_identifier(value, field=field)


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
class ApprovedHost:
    host_id: str
    hostname: str
    purpose: ApprovedHostPurpose
    credential_allowed: bool = False
    port: int = 443

    def __post_init__(self) -> None:
        _validate_identifier(self.host_id, field="host_id")
        _validate_hostname(self.hostname)
        if not isinstance(self.purpose, ApprovedHostPurpose):
            raise TypeError("purpose must be ApprovedHostPurpose")
        if not isinstance(self.credential_allowed, bool):
            raise TypeError("credential_allowed must be a boolean")
        if self.port != 443:
            raise ValueError("approved hosts require port 443")


@dataclass(frozen=True, slots=True)
class ApprovedRatePolicy:
    provider_concurrency_limit: int = 1
    automatic_retry_limit: int = 0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provider_concurrency_limit, int)
            or isinstance(self.provider_concurrency_limit, bool)
            or self.provider_concurrency_limit != 1
        ):
            raise ValueError("provider_concurrency_limit must remain one")
        if (
            not isinstance(self.automatic_retry_limit, int)
            or isinstance(self.automatic_retry_limit, bool)
            or self.automatic_retry_limit != 0
        ):
            raise ValueError("automatic retries are not approved")


@dataclass(frozen=True, slots=True)
class ApprovedAuth:
    modes: tuple[ProviderAuthMode, ...] = (ProviderAuthMode.NONE,)
    credential_host_ids: tuple[str, ...] = ()
    oauth_state_required: bool = False
    oauth_pkce_required: bool = False
    password_storage_allowed: bool = False

    def __post_init__(self) -> None:
        _validate_enum_tuple(
            self.modes,
            enum_type=ProviderAuthMode,
            field="auth.modes",
        )
        if not self.modes:
            raise ValueError("auth.modes must not be empty")
        _validate_identifier_tuple(
            self.credential_host_ids,
            field="auth.credential_host_ids",
        )
        for value, field in (
            (self.oauth_state_required, "oauth_state_required"),
            (self.oauth_pkce_required, "oauth_pkce_required"),
            (self.password_storage_allowed, "password_storage_allowed"),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{field} must be a boolean")
        if ProviderAuthMode.OAUTH in self.modes:
            if not self.oauth_state_required or not self.oauth_pkce_required:
                raise ValueError("OAuth approval requires state and PKCE")
        elif self.oauth_state_required or self.oauth_pkce_required:
            raise ValueError("OAuth policy requires the OAuth mode")
        if (
            ProviderAuthMode.USERNAME_PASSWORD not in self.modes
            and self.password_storage_allowed
        ):
            raise ValueError("password storage requires username/password mode")
        if self.modes == (ProviderAuthMode.NONE,) and self.credential_host_ids:
            raise ValueError("public-only approval cannot declare credential hosts")


@dataclass(frozen=True, slots=True)
class ApprovedAssetPolicy:
    allowed_kinds: tuple[SourceAssetKind, ...] = ()
    asset_host_ids: tuple[str, ...] = ()
    max_assets_per_item: int = 0
    locator_resolution_allowed: bool = False

    def __post_init__(self) -> None:
        _validate_enum_tuple(
            self.allowed_kinds,
            enum_type=SourceAssetKind,
            field="asset_policy.allowed_kinds",
        )
        _validate_identifier_tuple(
            self.asset_host_ids,
            field="asset_policy.asset_host_ids",
        )
        if (
            not isinstance(self.max_assets_per_item, int)
            or isinstance(self.max_assets_per_item, bool)
            or not 0 <= self.max_assets_per_item <= MAX_PAGE_SIZE
        ):
            raise ValueError("max_assets_per_item is outside the safe range")
        if not isinstance(self.locator_resolution_allowed, bool):
            raise TypeError("locator_resolution_allowed must be a boolean")
        if bool(self.allowed_kinds) != bool(self.max_assets_per_item):
            raise ValueError("asset kinds and limit must be declared together")
        if self.locator_resolution_allowed and not self.asset_host_ids:
            raise ValueError("asset resolution requires approved asset hosts")


@dataclass(frozen=True, slots=True)
class ApprovedDownloadPolicy:
    enabled: bool = False
    allowed_kinds: tuple[SourceAssetKind, ...] = ()
    asset_host_ids: tuple[str, ...] = ()
    max_files_per_request: int = 0
    max_total_bytes: int = 0
    checksum_required: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a boolean")
        _validate_enum_tuple(
            self.allowed_kinds,
            enum_type=SourceAssetKind,
            field="download_policy.allowed_kinds",
        )
        _validate_identifier_tuple(
            self.asset_host_ids,
            field="download_policy.asset_host_ids",
        )
        if (
            not isinstance(self.max_files_per_request, int)
            or isinstance(self.max_files_per_request, bool)
            or not 0 <= self.max_files_per_request <= MAX_PAGE_SIZE
        ):
            raise ValueError("max_files_per_request is outside the safe range")
        if (
            not isinstance(self.max_total_bytes, int)
            or isinstance(self.max_total_bytes, bool)
            or not 0 <= self.max_total_bytes <= MAX_APPROVED_DOWNLOAD_BYTES
        ):
            raise ValueError("max_total_bytes is outside the safe range")
        if not isinstance(self.checksum_required, bool):
            raise TypeError("checksum_required must be a boolean")
        if self.enabled:
            if (
                not self.allowed_kinds
                or not self.asset_host_ids
                or self.max_files_per_request < 1
                or self.max_total_bytes < 1
                or not self.checksum_required
            ):
                raise ValueError("enabled download policy is incomplete")
        elif (
            self.allowed_kinds
            or self.asset_host_ids
            or self.max_files_per_request
            or self.max_total_bytes
            or self.checksum_required
        ):
            raise ValueError("disabled download policy must not grant authority")


@dataclass(frozen=True, slots=True)
class ApprovedOperation:
    operation: ProviderOperation
    layer: ProviderCapabilityLayer
    host_id: str
    path_template: str
    method: HttpMethod
    request_encoding: RequestEncoding
    auth_requirement: ProviderAuthMode
    cookie_policy: CookiePolicy
    response_kind: ResponseKind
    expected_top_level: JsonTopLevel | None
    allowed_content_types: tuple[str, ...]
    response_limit_bytes: int
    page_size_limit: int
    redirect_policy: RedirectPolicy
    rate_policy: ApprovedRatePolicy
    fixed_headers: tuple[ApprovedFixedHeader, ...] = ()
    timeout_policy: ApprovedTimeoutPolicy = ApprovedTimeoutPolicy()
    error_mapping_profile: ApprovedErrorMappingProfile = (
        ApprovedErrorMappingProfile.SHARED_OUTBOUND_V1
    )
    raw_payload_retention: ApprovedRawPayloadRetention = (
        ApprovedRawPayloadRetention.DISCARD
    )
    path_parameter: BusinessParameter | None = None
    query_parameters: tuple[tuple[BusinessParameter, str], ...] = ()
    body_parameters: tuple[tuple[BusinessParameter, str], ...] = ()
    required_parameters: tuple[BusinessParameter, ...] = ()
    redirect_host_ids: tuple[str, ...] = ()
    max_redirects: int = 0
    asset_host_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.operation, ProviderOperation):
            raise TypeError("operation must be ProviderOperation")
        if not isinstance(self.layer, ProviderCapabilityLayer):
            raise TypeError("layer must be ProviderCapabilityLayer")
        if self.operation.layer is not self.layer:
            raise ValueError("operation is assigned to another capability layer")
        _validate_identifier(self.host_id, field="host_id")
        _validate_path_template(self.path_template, self.path_parameter)
        query_business, query_names = _validate_parameter_mapping(
            self.query_parameters,
            field="query_parameters",
        )
        body_business, body_names = _validate_parameter_mapping(
            self.body_parameters,
            field="body_parameters",
        )
        if query_business & body_business or query_names & body_names:
            raise ValueError("query and body parameter mappings overlap")
        if self.path_parameter is not None:
            if not isinstance(self.path_parameter, BusinessParameter):
                raise TypeError("path_parameter must be BusinessParameter")
            if self.path_parameter in query_business | body_business:
                raise ValueError("path parameter must not be mapped twice")
        if not isinstance(self.required_parameters, tuple) or not all(
            isinstance(value, BusinessParameter) for value in self.required_parameters
        ):
            raise TypeError("required_parameters must be BusinessParameter values")
        available = query_business | body_business
        if self.path_parameter is not None:
            available.add(self.path_parameter)
        if len(set(self.required_parameters)) != len(self.required_parameters):
            raise ValueError("required_parameters contains duplicates")
        if not set(self.required_parameters).issubset(available):
            raise ValueError("required parameter is not mapped by the operation")
        if not isinstance(self.method, HttpMethod):
            raise TypeError("method must be HttpMethod")
        if not isinstance(self.request_encoding, RequestEncoding):
            raise TypeError("request_encoding must be RequestEncoding")
        if self.method is HttpMethod.GET and (
            self.request_encoding is not RequestEncoding.NONE or self.body_parameters
        ):
            raise ValueError("GET operations cannot define a request body")
        if self.body_parameters and self.request_encoding is RequestEncoding.NONE:
            raise ValueError("body parameters require a request encoding")
        if (
            not self.body_parameters
            and self.request_encoding is not RequestEncoding.NONE
        ):
            raise ValueError("request encoding requires typed body parameters")
        if not isinstance(self.auth_requirement, ProviderAuthMode):
            raise TypeError("auth_requirement must be ProviderAuthMode")
        if not isinstance(self.cookie_policy, CookiePolicy):
            raise TypeError("cookie_policy must be CookiePolicy")
        if not isinstance(self.response_kind, ResponseKind):
            raise TypeError("response_kind must be ResponseKind")
        if self.response_kind is ResponseKind.JSON:
            if not isinstance(self.expected_top_level, JsonTopLevel):
                raise TypeError("JSON operations require expected_top_level")
        elif self.expected_top_level is not None:
            raise ValueError("non-JSON operations cannot define expected_top_level")
        _validate_content_types(
            self.allowed_content_types,
            response_kind=self.response_kind,
        )
        if (
            not isinstance(self.response_limit_bytes, int)
            or isinstance(self.response_limit_bytes, bool)
            or not 1 <= self.response_limit_bytes <= MAX_RESPONSE_BYTES
        ):
            raise ValueError("response_limit_bytes is outside the global limit")
        if (
            not isinstance(self.page_size_limit, int)
            or isinstance(self.page_size_limit, bool)
            or not 1 <= self.page_size_limit <= MAX_PAGE_SIZE
        ):
            raise ValueError("page_size_limit is outside the global limit")
        if not isinstance(self.redirect_policy, RedirectPolicy):
            raise TypeError("redirect_policy must be RedirectPolicy")
        _validate_identifier_tuple(
            self.redirect_host_ids,
            field="redirect_host_ids",
        )
        if (
            not isinstance(self.max_redirects, int)
            or isinstance(self.max_redirects, bool)
            or not 0 <= self.max_redirects <= 3
        ):
            raise ValueError("max_redirects is outside the supported limit")
        if self.redirect_policy is RedirectPolicy.DENY and (
            self.redirect_host_ids or self.max_redirects
        ):
            raise ValueError("denied redirects cannot define redirect targets")
        if self.redirect_policy is RedirectPolicy.EXACT_ALLOWLIST and (
            not self.redirect_host_ids or self.max_redirects < 1
        ):
            raise ValueError("redirect allowlist requires exact hosts and a hop limit")
        if not isinstance(self.rate_policy, ApprovedRatePolicy):
            raise TypeError("rate_policy must be ApprovedRatePolicy")
        if not isinstance(self.fixed_headers, tuple) or not all(
            type(header) is ApprovedFixedHeader for header in self.fixed_headers
        ):
            raise TypeError("fixed_headers must be an immutable ApprovedFixedHeader tuple")
        header_names = tuple(header.name.casefold() for header in self.fixed_headers)
        if len(set(header_names)) != len(header_names):
            raise ValueError("fixed_headers contains duplicate names")
        if not isinstance(self.timeout_policy, ApprovedTimeoutPolicy):
            raise TypeError("timeout_policy must be ApprovedTimeoutPolicy")
        if not isinstance(self.error_mapping_profile, ApprovedErrorMappingProfile):
            raise TypeError(
                "error_mapping_profile must be ApprovedErrorMappingProfile"
            )
        if not isinstance(self.raw_payload_retention, ApprovedRawPayloadRetention):
            raise TypeError(
                "raw_payload_retention must be ApprovedRawPayloadRetention"
            )
        _validate_identifier_tuple(self.asset_host_ids, field="asset_host_ids")
        if self.asset_host_ids and self.layer not in {
            ProviderCapabilityLayer.ASSET,
            ProviderCapabilityLayer.DOWNLOAD,
        }:
            raise ValueError("asset hosts are limited to asset/download operations")


def _operation_host_purpose(operation: ProviderOperation) -> ApprovedHostPurpose:
    if operation.layer is ProviderCapabilityLayer.AUTH:
        return ApprovedHostPurpose.AUTH
    if operation.layer is ProviderCapabilityLayer.DOWNLOAD:
        return ApprovedHostPurpose.ASSET
    return ApprovedHostPurpose.METADATA


@dataclass(frozen=True, slots=True)
class ProviderApproval:
    approval_id: str
    approval_version: int
    scope: ProviderApprovalScope
    provider_key: str
    display_name: str
    content_scope: str
    product_fit: str
    lawful_access_basis: str
    terms_basis: str
    attribution_policy: ApprovalAttributionPolicy
    capabilities: tuple[ProviderOperation, ...]
    hosts: tuple[ApprovedHost, ...]
    operations: tuple[ApprovedOperation, ...]
    auth: ApprovedAuth
    asset_policy: ApprovedAssetPolicy
    download_policy: ApprovedDownloadPolicy
    explicit_exclusions: tuple[ProviderOperation, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.approval_id, str)
            or len(self.approval_id) > MAX_APPROVAL_ID_LENGTH
            or _APPROVAL_ID_PATTERN.fullmatch(self.approval_id) is None
        ):
            raise ValueError("approval_id has an invalid format")
        if (
            not isinstance(self.approval_version, int)
            or isinstance(self.approval_version, bool)
            or self.approval_version != APPROVAL_FORMAT_VERSION
        ):
            raise ValueError("approval_version is not supported")
        if not isinstance(self.scope, ProviderApprovalScope):
            raise TypeError("scope must be ProviderApprovalScope")
        _validate_provider_key(self.provider_key)
        for value, field in (
            (self.display_name, "display_name"),
            (self.content_scope, "content_scope"),
            (self.product_fit, "product_fit"),
            (self.lawful_access_basis, "lawful_access_basis"),
            (self.terms_basis, "terms_basis"),
        ):
            _bounded_text(value, field=field)
        if not isinstance(self.attribution_policy, ApprovalAttributionPolicy):
            raise TypeError("attribution_policy must be ApprovalAttributionPolicy")
        _validate_enum_tuple(
            self.capabilities,
            enum_type=ProviderOperation,
            field="capabilities",
        )
        if not self.capabilities:
            raise ValueError("approval must declare capabilities")
        if not any(
            operation.layer is ProviderCapabilityLayer.METADATA
            for operation in self.capabilities
        ):
            raise ValueError("approval requires a metadata operation")
        if (
            not isinstance(self.hosts, tuple)
            or not self.hosts
            or len(self.hosts) > MAX_APPROVAL_HOSTS
            or not all(type(host) is ApprovedHost for host in self.hosts)
        ):
            raise TypeError("hosts must be an immutable ApprovedHost tuple")
        if (
            not isinstance(self.operations, tuple)
            or not self.operations
            or len(self.operations) > MAX_APPROVAL_OPERATIONS
            or not all(type(operation) is ApprovedOperation for operation in self.operations)
        ):
            raise TypeError("operations must be an immutable ApprovedOperation tuple")
        if not isinstance(self.auth, ApprovedAuth):
            raise TypeError("auth must be ApprovedAuth")
        if not isinstance(self.asset_policy, ApprovedAssetPolicy):
            raise TypeError("asset_policy must be ApprovedAssetPolicy")
        if not isinstance(self.download_policy, ApprovedDownloadPolicy):
            raise TypeError("download_policy must be ApprovedDownloadPolicy")
        _validate_enum_tuple(
            self.explicit_exclusions,
            enum_type=ProviderOperation,
            field="explicit_exclusions",
        )

        host_ids = tuple(host.host_id for host in self.hosts)
        if len(set(host_ids)) != len(host_ids):
            raise ValueError("host_id is duplicated")
        operation_ids = tuple(operation.operation for operation in self.operations)
        if len(set(operation_ids)) != len(operation_ids):
            raise ValueError("operation is duplicated")
        if set(operation_ids) != set(self.capabilities):
            raise ValueError("operations must exactly match capabilities")
        if set(self.capabilities) & set(self.explicit_exclusions):
            raise ValueError("explicit exclusion conflicts with capabilities")

        host_map = {host.host_id: host for host in self.hosts}
        used_host_ids = set(self.auth.credential_host_ids)
        used_auth_modes: set[ProviderAuthMode] = set()
        asset_operation_host_ids: set[str] = set()
        for operation in self.operations:
            host = host_map.get(operation.host_id)
            if host is None:
                raise ValueError("operation references an unapproved host")
            if host.purpose is not _operation_host_purpose(operation.operation):
                raise ValueError("operation host purpose does not match its layer")
            used_host_ids.add(operation.host_id)
            if operation.auth_requirement not in self.auth.modes:
                raise ValueError("operation auth mode is not approved")
            if (
                operation.layer is ProviderCapabilityLayer.AUTH
                and operation.auth_requirement is ProviderAuthMode.NONE
            ):
                raise ValueError("auth operations require a credentialed mode")
            if operation.auth_requirement is not ProviderAuthMode.NONE:
                used_auth_modes.add(operation.auth_requirement)
                if not host.credential_allowed:
                    raise ValueError("credentialed operation uses an unapproved host")
            if (
                operation.cookie_policy is CookiePolicy.PROVIDER_SESSION
                and ProviderAuthMode.SESSION_COOKIE not in self.auth.modes
            ):
                raise ValueError("session cookie policy is not approved")
            if operation.cookie_policy is CookiePolicy.PROVIDER_SESSION:
                used_auth_modes.add(ProviderAuthMode.SESSION_COOKIE)
            for host_id in (*operation.redirect_host_ids, *operation.asset_host_ids):
                referenced = host_map.get(host_id)
                if referenced is None:
                    raise ValueError("operation references an unapproved host")
                used_host_ids.add(host_id)
            if operation.asset_host_ids:
                for host_id in operation.asset_host_ids:
                    if host_map[host_id].purpose is not ApprovedHostPurpose.ASSET:
                        raise ValueError("asset host reference has the wrong purpose")
                asset_operation_host_ids.update(operation.asset_host_ids)
            if operation.auth_requirement is not ProviderAuthMode.NONE or (
                operation.cookie_policy is CookiePolicy.PROVIDER_SESSION
            ):
                for host_id in operation.redirect_host_ids:
                    if not host_map[host_id].credential_allowed:
                        raise ValueError("credentialed redirect target is not approved")

        for host_id in self.auth.credential_host_ids:
            host = host_map.get(host_id)
            if (
                host is None
                or not host.credential_allowed
                or host.purpose is ApprovedHostPurpose.ASSET
            ):
                raise ValueError("auth references an unapproved credential host")
        unused_modes = {
            mode
            for mode in self.auth.modes
            if mode is not ProviderAuthMode.NONE and mode not in used_auth_modes
        }
        if unused_modes:
            raise ValueError("approval contains an unused credential mode")

        asset_operations = {
            operation
            for operation in self.capabilities
            if operation.layer is ProviderCapabilityLayer.ASSET
        }
        if bool(asset_operations) != bool(self.asset_policy.allowed_kinds):
            raise ValueError("asset policy does not match asset capabilities")
        if self.asset_policy.locator_resolution_allowed != (
            ProviderOperation.ASSET_RESOLVE in asset_operations
        ):
            raise ValueError("asset resolution policy does not match capabilities")
        if set(self.asset_policy.asset_host_ids) != asset_operation_host_ids:
            raise ValueError("asset policy hosts do not match operations")
        for host_id in self.asset_policy.asset_host_ids:
            host = host_map.get(host_id)
            if host is None or host.purpose is not ApprovedHostPurpose.ASSET:
                raise ValueError("asset policy references an unapproved host")
            used_host_ids.add(host_id)

        download_enabled = ProviderOperation.DOWNLOAD in self.capabilities
        if self.download_policy.enabled != download_enabled:
            raise ValueError("download policy does not match capabilities")
        for host_id in self.download_policy.asset_host_ids:
            host = host_map.get(host_id)
            if host is None or host.purpose is not ApprovedHostPurpose.ASSET:
                raise ValueError("download policy references an unapproved host")
            used_host_ids.add(host_id)
        if download_enabled:
            download_operation = next(
                operation
                for operation in self.operations
                if operation.operation is ProviderOperation.DOWNLOAD
            )
            if set(download_operation.asset_host_ids) != set(
                self.download_policy.asset_host_ids
            ):
                raise ValueError("download hosts do not match the operation")

        if used_host_ids != set(host_ids):
            raise ValueError("approval contains an unused host")
        if self.scope is ProviderApprovalScope.TEST_FIXTURE:
            if any(not host.hostname.endswith(".invalid") for host in self.hosts):
                raise ValueError("test fixture approval requires .invalid hosts")
        elif any(host.hostname.endswith(".invalid") for host in self.hosts):
            raise ValueError("production approval cannot use fixture hosts")

    def host(self, host_id: str) -> ApprovedHost | None:
        for host in self.hosts:
            if host.host_id == host_id:
                return host
        return None

    def operation(self, operation: ProviderOperation) -> ApprovedOperation | None:
        for approved in self.operations:
            if approved.operation is operation:
                return approved
        return None


def _validation_error(code: ApprovalValidationErrorCode) -> ApprovalValidationError:
    return ApprovalValidationError(code)


def _canonical_approved_fixed_headers(
    values: tuple[ApprovedFixedHeader, ...],
) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((header.name.casefold(), header.value) for header in values))


def _canonical_runtime_fixed_headers(
    values: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    # EndpointOperation already applies its own grammar. Re-check only the
    # shape here so malformed replacement objects fail with the stable code.
    if not isinstance(values, tuple) or any(
        not isinstance(item, tuple) or len(item) != 2 for item in values
    ):
        raise _validation_error(ApprovalValidationErrorCode.INVALID)
    try:
        return tuple(sorted((name.casefold(), value) for name, value in values))
    except AttributeError:
        raise _validation_error(ApprovalValidationErrorCode.INVALID) from None


def validate_approval_secret_fields(payload: object) -> None:
    nodes = 0

    def visit(value: object, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > MAX_APPROVAL_PAYLOAD_DEPTH or nodes > MAX_APPROVAL_PAYLOAD_NODES:
            raise _validation_error(ApprovalValidationErrorCode.INVALID)
        if isinstance(value, Mapping):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise _validation_error(ApprovalValidationErrorCode.INVALID)
                normalized = key.casefold().replace("-", "_")
                if normalized in _SENSITIVE_FIELD_NAMES or normalized.endswith(
                    _SENSITIVE_FIELD_SUFFIXES
                ):
                    raise _validation_error(
                        ApprovalValidationErrorCode.CONTAINS_SECRET
                    )
                visit(child, depth + 1)
            return
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for child in value:
                visit(child, depth + 1)
            return
        if isinstance(value, float) and not math.isfinite(value):
            raise _validation_error(ApprovalValidationErrorCode.INVALID)
        if value is None or isinstance(value, (str, int, float, bool)):
            return
        raise _validation_error(ApprovalValidationErrorCode.INVALID)

    visit(payload, 0)


def validate_provider_approval(approval: object) -> None:
    if type(approval) is not ProviderApproval:
        raise _validation_error(ApprovalValidationErrorCode.INVALID)
    if approval.scope is ProviderApprovalScope.PRODUCTION and any(
        operation.raw_payload_retention
        is not ApprovedRawPayloadRetention.DISCARD
        for operation in approval.operations
    ):
        raise _validation_error(ApprovalValidationErrorCode.INCOMPLETE)


def validate_approval_against_capabilities(
    approval: ProviderApproval,
    capabilities: ProviderCapabilities,
) -> None:
    validate_provider_approval(approval)
    if not isinstance(capabilities, ProviderCapabilities):
        raise _validation_error(ApprovalValidationErrorCode.INVALID)
    if capabilities.provider_key != approval.provider_key:
        raise _validation_error(ApprovalValidationErrorCode.PROVIDER_MISMATCH)
    if (
        capabilities.display_name != approval.display_name
        or capabilities.content_scope != approval.content_scope
    ):
        raise _validation_error(ApprovalValidationErrorCode.PROVIDER_MISMATCH)
    if set(capabilities.operations) & set(approval.explicit_exclusions):
        raise _validation_error(ApprovalValidationErrorCode.CAPABILITY_MISMATCH)
    if set(capabilities.operations) != set(approval.capabilities):
        raise _validation_error(ApprovalValidationErrorCode.CAPABILITY_MISMATCH)
    if set(capabilities.auth_modes) != set(approval.auth.modes):
        raise _validation_error(ApprovalValidationErrorCode.AUTH_MISMATCH)
    if set(capabilities.assets.kinds) != set(approval.asset_policy.allowed_kinds):
        raise _validation_error(ApprovalValidationErrorCode.ASSET_POLICY_MISMATCH)
    if set(capabilities.downloads.kinds) != set(
        approval.download_policy.allowed_kinds
    ):
        raise _validation_error(ApprovalValidationErrorCode.DOWNLOAD_POLICY_MISMATCH)
    attribution_required = (
        approval.attribution_policy is ApprovalAttributionPolicy.REQUIRED
    )
    if capabilities.attribution_required != attribution_required:
        raise _validation_error(ApprovalValidationErrorCode.CAPABILITY_MISMATCH)


def validate_approval_against_endpoint(
    approval: ProviderApproval,
    endpoint: ProviderEndpoint,
) -> None:
    from app.services.outbound_http import (
        AUTOMATIC_RETRY_LIMIT,
        CONNECT_TIMEOUT_SECONDS,
        PROVIDER_CONCURRENCY_LIMIT,
        TOTAL_TIMEOUT_SECONDS,
    )

    validate_provider_approval(approval)
    if not isinstance(endpoint, ProviderEndpoint):
        raise _validation_error(ApprovalValidationErrorCode.INVALID)
    if endpoint.provider_key != approval.provider_key:
        raise _validation_error(ApprovalValidationErrorCode.PROVIDER_MISMATCH)
    runtime_operations = {operation.operation for operation in endpoint.operations}
    if runtime_operations & set(approval.explicit_exclusions):
        raise _validation_error(ApprovalValidationErrorCode.OPERATION_MISMATCH)
    if runtime_operations != set(approval.capabilities):
        raise _validation_error(ApprovalValidationErrorCode.OPERATION_MISMATCH)

    runtime_asset_hosts: set[str] = set()
    for runtime in endpoint.operations:
        approved = approval.operation(runtime.operation)
        if approved is None:
            raise _validation_error(ApprovalValidationErrorCode.OPERATION_MISMATCH)
        if (
            approved.rate_policy.provider_concurrency_limit
            != PROVIDER_CONCURRENCY_LIMIT
            or approved.rate_policy.automatic_retry_limit != AUTOMATIC_RETRY_LIMIT
        ):
            raise _validation_error(ApprovalValidationErrorCode.OPERATION_MISMATCH)
        base_host = approval.host(approved.host_id)
        if (
            base_host is None
            or base_host.hostname != endpoint.hostname
            or base_host.port != endpoint.port
        ):
            raise _validation_error(ApprovalValidationErrorCode.HOST_MISMATCH)
        if (
            runtime.path_template != approved.path_template
            or runtime.path_parameter is not approved.path_parameter
            or runtime.query_parameters != approved.query_parameters
            or runtime.body_parameters != approved.body_parameters
            or runtime.required_parameters != approved.required_parameters
            or runtime.method is not approved.method
            or runtime.request_encoding is not approved.request_encoding
            or runtime.response_kind is not approved.response_kind
            or runtime.expected_top_level is not approved.expected_top_level
            or set(runtime.allowed_content_types)
            != set(approved.allowed_content_types)
            or _canonical_runtime_fixed_headers(runtime.fixed_headers)
            != _canonical_approved_fixed_headers(approved.fixed_headers)
        ):
            raise _validation_error(ApprovalValidationErrorCode.OPERATION_MISMATCH)
        if (
            approved.timeout_policy.connect_timeout_seconds != CONNECT_TIMEOUT_SECONDS
            or approved.timeout_policy.total_timeout_seconds != TOTAL_TIMEOUT_SECONDS
            or approved.error_mapping_profile
            is not ApprovedErrorMappingProfile.SHARED_OUTBOUND_V1
        ):
            raise _validation_error(ApprovalValidationErrorCode.OPERATION_MISMATCH)
        if (
            runtime.auth_requirement is not approved.auth_requirement
            or runtime.cookie_policy is not approved.cookie_policy
        ):
            raise _validation_error(ApprovalValidationErrorCode.AUTH_MISMATCH)
        approved_redirect_hosts = {
            host.hostname
            for host_id in approved.redirect_host_ids
            if (host := approval.host(host_id)) is not None
        }
        if (
            runtime.redirect_policy is not approved.redirect_policy
            or set(runtime.redirect_hosts) != approved_redirect_hosts
            or runtime.max_redirects > approved.max_redirects
        ):
            raise _validation_error(ApprovalValidationErrorCode.HOST_MISMATCH)
        approved_asset_hosts = {
            host.hostname
            for host_id in approved.asset_host_ids
            if (host := approval.host(host_id)) is not None
        }
        if set(runtime.allowed_asset_hosts) != approved_asset_hosts:
            raise _validation_error(
                ApprovalValidationErrorCode.ASSET_POLICY_MISMATCH
            )
        runtime_asset_hosts.update(runtime.allowed_asset_hosts)
        if (
            runtime.response_limit_bytes > approved.response_limit_bytes
            or runtime.page_size_limit > approved.page_size_limit
        ):
            raise _validation_error(ApprovalValidationErrorCode.OPERATION_MISMATCH)
        if (
            runtime.operation is ProviderOperation.ASSET_LIST
            and runtime.page_size_limit > approval.asset_policy.max_assets_per_item
        ):
            raise _validation_error(
                ApprovalValidationErrorCode.ASSET_POLICY_MISMATCH
            )
        if (
            runtime.operation is ProviderOperation.DOWNLOAD
            and runtime.response_limit_bytes > approval.download_policy.max_total_bytes
        ):
            raise _validation_error(
                ApprovalValidationErrorCode.DOWNLOAD_POLICY_MISMATCH
            )

    approved_asset_hosts = {
        host.hostname
        for host_id in approval.asset_policy.asset_host_ids
        if (host := approval.host(host_id)) is not None
    }
    if runtime_asset_hosts != approved_asset_hosts:
        raise _validation_error(ApprovalValidationErrorCode.ASSET_POLICY_MISMATCH)
    validate_approval_against_capabilities(approval, endpoint.capabilities)


def validate_approval_for_activation(
    approval: ProviderApproval,
    capabilities: ProviderCapabilities,
    endpoint: ProviderEndpoint,
) -> None:
    validate_approval_against_capabilities(approval, capabilities)
    validate_approval_against_endpoint(approval, endpoint)
    if (
        approval.scope is ProviderApprovalScope.PRODUCTION
        and any(
            operation.raw_payload_retention
            is not ApprovedRawPayloadRetention.DISCARD
            for operation in approval.operations
        )
    ):
        raise _validation_error(ApprovalValidationErrorCode.INCOMPLETE)
    if any(
        operation not in _ACTIVATION_SUPPORTED_OPERATIONS
        for operation in approval.capabilities
    ):
        raise _validation_error(ApprovalValidationErrorCode.INCOMPLETE)
    if approval.auth.modes != (ProviderAuthMode.NONE,):
        raise _validation_error(ApprovalValidationErrorCode.INCOMPLETE)
    for operation in endpoint.operations:
        if (
            operation.auth_requirement is not ProviderAuthMode.NONE
            or operation.cookie_policy is not CookiePolicy.NONE
            or operation.response_kind is not ResponseKind.JSON
            or operation.redirect_policy is not RedirectPolicy.DENY
        ):
            raise _validation_error(ApprovalValidationErrorCode.INCOMPLETE)
    if (
        approval.asset_policy.locator_resolution_allowed
        or approval.download_policy.enabled
    ):
        raise _validation_error(ApprovalValidationErrorCode.INCOMPLETE)
    if approval.scope is not ProviderApprovalScope.PRODUCTION:
        raise _validation_error(ApprovalValidationErrorCode.INVALID)
