from __future__ import annotations

import ipaddress
import re
import string
from dataclasses import dataclass
from enum import Enum
from urllib.parse import quote

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_PAGE_SIZE = 50
MAX_PROVIDER_KEY_LENGTH = 64
MAX_OPERATION_LENGTH = 64

_IDENTIFIER_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_QUERY_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")
_HOST_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class BusinessParameter(str, Enum):
    QUERY = "query"
    EXTERNAL_ID = "external_id"
    PAGE = "page"
    PAGE_SIZE = "page_size"


class JsonTopLevel(str, Enum):
    OBJECT = "object"
    ARRAY = "array"


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


@dataclass(frozen=True, slots=True)
class EndpointOperation:
    name: str
    path_template: str
    expected_top_level: JsonTopLevel
    path_parameter: BusinessParameter | None = None
    query_parameters: tuple[tuple[BusinessParameter, str], ...] = ()
    required_parameters: tuple[BusinessParameter, ...] = ()
    response_limit_bytes: int = MAX_RESPONSE_BYTES
    page_size_limit: int = MAX_PAGE_SIZE

    def __post_init__(self) -> None:
        _validate_identifier(self.name, field="operation")
        _validate_path_template(self.path_template, self.path_parameter)
        if not isinstance(self.expected_top_level, JsonTopLevel):
            raise TypeError("expected_top_level must be JsonTopLevel")
        if not isinstance(self.query_parameters, tuple):
            raise TypeError("query_parameters must be a tuple")
        seen_business: set[BusinessParameter] = set()
        seen_names: set[str] = set()
        for business_parameter, query_name in self.query_parameters:
            if not isinstance(business_parameter, BusinessParameter):
                raise TypeError("query parameter key must be BusinessParameter")
            if _QUERY_NAME_PATTERN.fullmatch(query_name) is None:
                raise ValueError("query parameter name is invalid")
            if business_parameter in seen_business or query_name in seen_names:
                raise ValueError("query parameter mapping is duplicated")
            seen_business.add(business_parameter)
            seen_names.add(query_name)
        if not isinstance(self.required_parameters, tuple) or not all(
            isinstance(value, BusinessParameter) for value in self.required_parameters
        ):
            raise TypeError("required_parameters must be BusinessParameter values")
        available = set(seen_business)
        if self.path_parameter is not None:
            available.add(self.path_parameter)
        if len(set(self.required_parameters)) != len(self.required_parameters):
            raise ValueError("required_parameters contains duplicates")
        if not set(self.required_parameters).issubset(available):
            raise ValueError("required parameter is not mapped by the operation")
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


@dataclass(frozen=True, slots=True)
class ProviderEndpoint:
    provider_key: str
    hostname: str
    operations: tuple[EndpointOperation, ...]
    port: int = 443

    def __post_init__(self) -> None:
        _validate_identifier(self.provider_key, field="provider_key")
        if len(self.provider_key) > MAX_PROVIDER_KEY_LENGTH:
            raise ValueError("provider_key is too long")
        _validate_hostname(self.hostname)
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

    def operation(self, name: str) -> EndpointOperation | None:
        for operation in self.operations:
            if operation.name == name:
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
