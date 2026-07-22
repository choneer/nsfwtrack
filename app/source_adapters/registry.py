from __future__ import annotations

import ipaddress
import re
import string
from dataclasses import dataclass
from enum import Enum
from urllib.parse import quote

from app.source_adapters.contracts import (
    ProviderAuthMode,
    ProviderCapabilityLayer,
    ProviderCapabilities,
    ProviderOperation,
)

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_PAGE_SIZE = 50
MAX_PROVIDER_KEY_LENGTH = 64
MAX_OPERATION_LENGTH = 64

_IDENTIFIER_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_QUERY_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")
_HOST_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_HEADER_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,63}")
_CONTENT_TYPE_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/"
    r"(?:\*\+)?[a-z0-9][a-z0-9!#$&^_.+-]{0,126}"
)

_FORBIDDEN_FIXED_HEADERS = {
    "accept",
    "accept-encoding",
    "authorization",
    "connection",
    "content-length",
    "content-type",
    "cookie",
    "host",
    "proxy-authorization",
    "transfer-encoding",
}

DEFAULT_JSON_CONTENT_TYPES = ("application/json", "application/*+json")


class BusinessParameter(str, Enum):
    QUERY = "query"
    EXTERNAL_ID = "external_id"
    PAGE = "page"
    PAGE_SIZE = "page_size"


class JsonTopLevel(str, Enum):
    OBJECT = "object"
    ARRAY = "array"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"


class RequestEncoding(str, Enum):
    NONE = "none"
    JSON = "json"
    FORM = "form"


class ResponseKind(str, Enum):
    JSON = "json"
    HTML = "html"
    FILE = "file"


class CookiePolicy(str, Enum):
    NONE = "none"
    PROVIDER_SESSION = "provider_session"


class RedirectPolicy(str, Enum):
    DENY = "deny"
    EXACT_ALLOWLIST = "exact_allowlist"


def _validate_identifier(value: str, *, field: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} has an invalid format")


def _validate_hostname(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.casefold():
        raise ValueError("hostname must be a lowercase ASCII hostname")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("hostname must be ASCII") from exc
    if len(value) > 253 or value.endswith(".") or ".." in value:
        raise ValueError("hostname has an invalid format")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValueError("hostname must not be an IP literal")
    labels = value.split(".")
    if len(labels) < 2 or any(
        _HOST_LABEL_PATTERN.fullmatch(label) is None for label in labels
    ):
        raise ValueError("hostname has an invalid format")


def _path_fields(path_template: str) -> tuple[str, ...]:
    fields: list[str] = []
    try:
        parsed = tuple(string.Formatter().parse(path_template))
    except ValueError as exc:
        raise ValueError("path_template has invalid placeholders") from exc
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if format_spec or conversion:
            raise ValueError("path_template formatting is not allowed")
        fields.append(field_name)
    return tuple(fields)


def _validate_path_template(
    path_template: str,
    path_parameter: BusinessParameter | None,
) -> None:
    if (
        not isinstance(path_template, str)
        or not path_template.startswith("/")
        or "//" in path_template
        or "\\" in path_template
        or "%" in path_template
        or "?" in path_template
        or "#" in path_template
        or "://" in path_template
        or any(not 33 <= ord(character) <= 126 for character in path_template)
    ):
        raise ValueError("path_template must be a fixed absolute path")
    if any(segment in {".", ".."} for segment in path_template.split("/")):
        raise ValueError("path_template contains a traversal segment")
    fields = _path_fields(path_template)
    expected = () if path_parameter is None else (path_parameter.value,)
    if fields != expected:
        raise ValueError("path_template placeholders do not match path_parameter")


def _validate_parameter_mapping(
    values: tuple[tuple[BusinessParameter, str], ...],
    *,
    field: str,
) -> tuple[set[BusinessParameter], set[str]]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field} must be a tuple")
    business_parameters: set[BusinessParameter] = set()
    names: set[str] = set()
    for item in values:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError(f"{field} entries must be pairs")
        business_parameter, name = item
        if not isinstance(business_parameter, BusinessParameter):
            raise TypeError(f"{field} key must be BusinessParameter")
        if not isinstance(name, str) or _QUERY_NAME_PATTERN.fullmatch(name) is None:
            raise ValueError(f"{field} name is invalid")
        if business_parameter in business_parameters or name in names:
            raise ValueError(f"{field} mapping is duplicated")
        business_parameters.add(business_parameter)
        names.add(name)
    return business_parameters, names


def _validate_content_types(
    values: tuple[str, ...],
    *,
    response_kind: ResponseKind,
) -> None:
    if not isinstance(values, tuple) or not values:
        raise ValueError("allowed_content_types must be a non-empty tuple")
    if len(set(values)) != len(values):
        raise ValueError("allowed_content_types contains duplicates")
    for value in values:
        if (
            not isinstance(value, str)
            or value != value.casefold()
            or len(value) > 255
            or _CONTENT_TYPE_PATTERN.fullmatch(value) is None
        ):
            raise ValueError("allowed_content_types contains an invalid media type")
    if response_kind is ResponseKind.JSON and any(
        value != "application/json"
        and value != "application/*+json"
        and not (value.startswith("application/") and value.endswith("+json"))
        for value in values
    ):
        raise ValueError("JSON operations require JSON content types")
    if response_kind is not ResponseKind.JSON and any("*" in value for value in values):
        raise ValueError("non-JSON content types must be exact")


def _validate_fixed_headers(values: tuple[tuple[str, str], ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError("fixed_headers must be a tuple")
    names: set[str] = set()
    for item in values:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("fixed_headers entries must be pairs")
        name, value = item
        if not isinstance(name, str) or _HEADER_NAME_PATTERN.fullmatch(name) is None:
            raise ValueError("fixed header name is invalid")
        normalized = name.casefold()
        if normalized in _FORBIDDEN_FIXED_HEADERS or normalized in names:
            raise ValueError("fixed header name is forbidden or duplicated")
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 512
            or any(not 32 <= ord(character) <= 126 for character in value)
        ):
            raise ValueError("fixed header value is invalid")
        names.add(normalized)


def _validate_host_tuple(values: tuple[str, ...], *, field: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field} must be a tuple")
    if len(set(values)) != len(values):
        raise ValueError(f"{field} contains duplicates")
    for value in values:
        _validate_hostname(value)


@dataclass(frozen=True, slots=True)
class EndpointOperation:
    operation: ProviderOperation
    path_template: str
    expected_top_level: JsonTopLevel | None
    path_parameter: BusinessParameter | None = None
    query_parameters: tuple[tuple[BusinessParameter, str], ...] = ()
    body_parameters: tuple[tuple[BusinessParameter, str], ...] = ()
    required_parameters: tuple[BusinessParameter, ...] = ()
    response_limit_bytes: int = MAX_RESPONSE_BYTES
    page_size_limit: int = MAX_PAGE_SIZE
    method: HttpMethod = HttpMethod.GET
    request_encoding: RequestEncoding = RequestEncoding.NONE
    auth_requirement: ProviderAuthMode = ProviderAuthMode.NONE
    cookie_policy: CookiePolicy = CookiePolicy.NONE
    response_kind: ResponseKind = ResponseKind.JSON
    allowed_content_types: tuple[str, ...] = DEFAULT_JSON_CONTENT_TYPES
    fixed_headers: tuple[tuple[str, str], ...] = ()
    redirect_policy: RedirectPolicy = RedirectPolicy.DENY
    redirect_hosts: tuple[str, ...] = ()
    max_redirects: int = 0
    allowed_asset_hosts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.operation, ProviderOperation):
            raise TypeError("operation must be ProviderOperation")
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
        _validate_fixed_headers(self.fixed_headers)
        if not isinstance(self.redirect_policy, RedirectPolicy):
            raise TypeError("redirect_policy must be RedirectPolicy")
        _validate_host_tuple(self.redirect_hosts, field="redirect_hosts")
        if (
            not isinstance(self.max_redirects, int)
            or isinstance(self.max_redirects, bool)
            or not 0 <= self.max_redirects <= 3
        ):
            raise ValueError("max_redirects is outside the supported limit")
        if self.redirect_policy is RedirectPolicy.DENY and (
            self.redirect_hosts or self.max_redirects
        ):
            raise ValueError("denied redirects cannot define redirect targets")
        if self.redirect_policy is RedirectPolicy.EXACT_ALLOWLIST and (
            not self.redirect_hosts or self.max_redirects < 1
        ):
            raise ValueError("redirect allowlist requires exact hosts and a hop limit")
        _validate_host_tuple(
            self.allowed_asset_hosts,
            field="allowed_asset_hosts",
        )
        if self.allowed_asset_hosts and self.operation.layer not in {
            ProviderCapabilityLayer.ASSET,
            ProviderCapabilityLayer.DOWNLOAD,
        }:
            raise ValueError("asset hosts are limited to asset/download operations")
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

    @property
    def name(self) -> str:
        return self.operation.value

    def render_path(self, external_id: str | None) -> str:
        if self.path_parameter is None:
            return self.path_template
        if self.path_parameter is not BusinessParameter.EXTERNAL_ID:
            raise ValueError("unsupported path parameter")
        if external_id is None:
            raise ValueError("external_id is required")
        return self.path_template.format(
            external_id=quote(external_id, safe="", encoding="utf-8", errors="strict")
        )

    def accepts_content_type(self, media_type: str) -> bool:
        normalized = media_type.casefold()
        return normalized in self.allowed_content_types or (
            "application/*+json" in self.allowed_content_types
            and normalized.startswith("application/")
            and normalized.endswith("+json")
        )


@dataclass(frozen=True, slots=True)
class ProviderEndpoint:
    provider_key: str
    hostname: str
    capabilities: ProviderCapabilities
    operations: tuple[EndpointOperation, ...]
    port: int = 443

    def __post_init__(self) -> None:
        _validate_identifier(self.provider_key, field="provider_key")
        if len(self.provider_key) > MAX_PROVIDER_KEY_LENGTH:
            raise ValueError("provider_key is too long")
        _validate_hostname(self.hostname)
        if not isinstance(self.capabilities, ProviderCapabilities):
            raise TypeError("capabilities must be ProviderCapabilities")
        if self.capabilities.provider_key != self.provider_key:
            raise ValueError("capability provider_key does not match endpoint")
        if self.port != 443:
            raise ValueError("only port 443 is allowed")
        if not isinstance(self.operations, tuple):
            raise TypeError("operations must be a tuple")
        if not self.operations or not all(
            isinstance(operation, EndpointOperation) for operation in self.operations
        ):
            raise ValueError("provider must define immutable operations")
        names = tuple(operation.name for operation in self.operations)
        if len(set(names)) != len(names):
            raise ValueError("operation names must be unique per provider")
        declared = self.capabilities.operations
        implemented = tuple(operation.operation for operation in self.operations)
        if len(set(implemented)) != len(implemented):
            raise ValueError("operation capabilities must be unique per provider")
        if set(implemented) != set(declared):
            raise ValueError("endpoint operations must exactly match capabilities")
        for operation in self.operations:
            if operation.auth_requirement not in self.capabilities.auth_modes:
                raise ValueError("operation auth requirement is not declared")
            if (
                operation.cookie_policy is CookiePolicy.PROVIDER_SESSION
                and ProviderAuthMode.SESSION_COOKIE
                not in self.capabilities.auth_modes
            ):
                raise ValueError("operation cookie policy is not declared")

    def operation(
        self,
        name: str | ProviderOperation,
    ) -> EndpointOperation | None:
        operation_name = name.value if isinstance(name, ProviderOperation) else name
        for operation in self.operations:
            if operation.name == operation_name:
                return operation
        return None


class EndpointRegistry:
    __slots__ = ("_providers",)

    def __init__(self, providers: tuple[ProviderEndpoint, ...]) -> None:
        if not isinstance(providers, tuple) or not all(
            isinstance(provider, ProviderEndpoint) for provider in providers
        ):
            raise TypeError("providers must be a tuple of ProviderEndpoint")
        keys = tuple(provider.provider_key for provider in providers)
        if len(set(keys)) != len(keys):
            raise ValueError("provider keys must be unique")
        object.__setattr__(self, "_providers", providers)

    @property
    def providers(self) -> tuple[ProviderEndpoint, ...]:
        return self._providers

    def provider(self, provider_key: str) -> ProviderEndpoint | None:
        for provider in self._providers:
            if provider.provider_key == provider_key:
                return provider
        return None

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("EndpointRegistry is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("EndpointRegistry is immutable")


PRODUCTION_ENDPOINT_REGISTRY = EndpointRegistry(())
