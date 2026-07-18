from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import math
import re
import socket
import ssl
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from urllib.parse import urlencode

# httpx2==2.5.0 pins and publicly exports the matching httpcore2==2.5.0
# transport/backend interfaces used below. No private module or attribute is used.
import httpcore2
import httpx2

from app.request_context import is_valid_request_id, request_id_context
from app.source_adapters.registry import (
    BusinessParameter,
    EndpointOperation,
    EndpointRegistry,
    JsonTopLevel,
    MAX_PAGE_SIZE,
    MAX_RESPONSE_BYTES,
    PRODUCTION_ENDPOINT_REGISTRY,
    ProviderEndpoint,
)

CONNECT_TIMEOUT_SECONDS = 3.0
TOTAL_TIMEOUT_SECONDS = 10.0
MAX_QUERY_LENGTH = 200
MAX_EXTERNAL_ID_LENGTH = 512
GLOBAL_CONCURRENCY_LIMIT = 4
PROVIDER_CONCURRENCY_LIMIT = 1
MAX_RETRY_AFTER_SECONDS = 3600

_SAFE_IDENTIFIER_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_JSON_CONTENT_TYPE_PATTERN = re.compile(
    r"application/(?:json|[a-z0-9!#$&^_.+-]+\+json)",
    re.IGNORECASE,
)

logger = logging.getLogger("uvicorn.error.nsfwtrack.outbound")


class OutboundErrorCode(str, Enum):
    PROVIDER_NOT_ALLOWED = "provider_not_allowed"
    OPERATION_NOT_ALLOWED = "operation_not_allowed"
    INVALID_REQUEST = "invalid_request"
    DNS_RESOLUTION_FAILED = "dns_resolution_failed"
    UNSAFE_ADDRESS = "unsafe_address"
    PEER_ADDRESS_MISMATCH = "peer_address_mismatch"
    CONNECT_TIMEOUT = "connect_timeout"
    REQUEST_TIMEOUT = "request_timeout"
    TLS_FAILED = "tls_failed"
    CONNECTION_FAILED = "connection_failed"
    REDIRECT_BLOCKED = "redirect_blocked"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    PROVIDER_SERVER_ERROR = "provider_server_error"
    UNEXPECTED_STATUS = "unexpected_status"
    UNEXPECTED_CONTENT_TYPE = "unexpected_content_type"
    UNEXPECTED_CONTENT_ENCODING = "unexpected_content_encoding"
    RESPONSE_TOO_LARGE = "response_too_large"
    MALFORMED_JSON = "malformed_json"
    INVALID_PAYLOAD = "invalid_payload"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class OutboundError:
    code: OutboundErrorCode
    provider_key: str
    operation: str
    request_id: str
    status_code: int | None = None
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, OutboundErrorCode):
            raise TypeError("code must be OutboundErrorCode")
        if _SAFE_IDENTIFIER_PATTERN.fullmatch(self.provider_key) is None:
            raise ValueError("provider_key must be sanitized")
        if _SAFE_IDENTIFIER_PATTERN.fullmatch(self.operation) is None:
            raise ValueError("operation must be sanitized")
        if not is_valid_request_id(self.request_id):
            raise ValueError("request_id must be a valid request identifier")
        if self.status_code is not None and not 100 <= self.status_code <= 599:
            raise ValueError("status_code is outside the HTTP range")
        if self.retry_after_seconds is not None and not (
            0 <= self.retry_after_seconds <= MAX_RETRY_AFTER_SECONDS
        ):
            raise ValueError("retry_after_seconds is outside the safe range")


class OutboundHttpError(RuntimeError):
    def __init__(self, error: OutboundError) -> None:
        self.error = error
        super().__init__(error.code.value)


@dataclass(frozen=True, slots=True)
class OutboundRequest:
    provider_key: str
    operation: str
    query: str | None = None
    external_id: str | None = None
    page: int | None = None
    page_size: int | None = None


@dataclass(frozen=True, slots=True)
class FrozenJsonObject(Mapping[str, object]):
    entries: tuple[tuple[str, object], ...]

    def __getitem__(self, key: str) -> object:
        for item_key, value in self.entries:
            if item_key == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self.entries)

    def __len__(self) -> int:
        return len(self.entries)


@dataclass(frozen=True, slots=True)
class OutboundJsonResponse:
    status_code: int
    data: FrozenJsonObject | tuple[object, ...]


@dataclass(frozen=True, slots=True)
class ConnectionPlan:
    hostname: str
    port: int
    approved_ips: tuple[str, ...]
    selected_ip: str

    def __post_init__(self) -> None:
        if self.port != 443:
            raise ValueError("connection plans require port 443")
        if not self.approved_ips or self.selected_ip not in self.approved_ips:
            raise ValueError("selected_ip must be approved")


class AddressResolver(Protocol):
    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...


class TransportFactory(Protocol):
    def __call__(self, plan: ConnectionPlan) -> httpx2.AsyncBaseTransport: ...


class SystemAddressResolver:
    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        addresses: list[str] = []
        for _, _, _, _, socket_address in records:
            address = str(socket_address[0])
            if address not in addresses:
                addresses.append(address)
        return tuple(addresses)


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()


class _PeerAddressMismatch(Exception):
    pass


class _UnexpectedConnectionTarget(Exception):
    pass


class _TlsHandshakeFailed(Exception):
    pass


def _extract_peer(stream: httpcore2.AsyncNetworkStream) -> tuple[str, int] | None:
    peer = stream.get_extra_info("server_addr")
    if not isinstance(peer, tuple) or len(peer) < 2:
        return None
    try:
        address = ipaddress.ip_address(str(peer[0])).compressed
        port = int(peer[1])
    except (TypeError, ValueError):
        return None
    return address, port


def _peer_matches(stream: httpcore2.AsyncNetworkStream, plan: ConnectionPlan) -> bool:
    peer = _extract_peer(stream)
    return peer == (plan.selected_ip, plan.port)


class PinnedNetworkStream(httpcore2.AsyncNetworkStream):
    def __init__(
        self,
        stream: httpcore2.AsyncNetworkStream,
        plan: ConnectionPlan,
    ) -> None:
        self._stream = stream
        self._plan = plan

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self._stream.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self._stream.write(buffer, timeout)

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        if server_hostname != self._plan.hostname:
            await self._stream.aclose()
            raise _UnexpectedConnectionTarget()
        try:
            tls_stream = await self._stream.start_tls(
                ssl_context,
                server_hostname=server_hostname,
                timeout=timeout,
            )
        except httpcore2.ConnectTimeout:
            await self._stream.aclose()
            raise
        except asyncio.CancelledError:
            await self._stream.aclose()
            raise
        except Exception as exc:
            await self._stream.aclose()
            raise _TlsHandshakeFailed() from exc
        if not _peer_matches(tls_stream, self._plan):
            await tls_stream.aclose()
            raise _PeerAddressMismatch()
        return PinnedNetworkStream(tls_stream, self._plan)

    def get_extra_info(self, info: str) -> object:
        return self._stream.get_extra_info(info)


class PinnedNetworkBackend(httpcore2.AsyncNetworkBackend):
    def __init__(
        self,
        plan: ConnectionPlan,
        backend: httpcore2.AsyncNetworkBackend,
    ) -> None:
        self._plan = plan
        self._backend = backend
        self._connect_attempts = 0

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object = None,
    ) -> httpcore2.AsyncNetworkStream:
        if host != self._plan.hostname or port != self._plan.port:
            raise _UnexpectedConnectionTarget()
        self._connect_attempts += 1
        if self._connect_attempts != 1:
            raise _UnexpectedConnectionTarget()
        stream = await self._backend.connect_tcp(
            self._plan.selected_ip,
            self._plan.port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )
        if not _peer_matches(stream, self._plan):
            await stream.aclose()
            raise _PeerAddressMismatch()
        return PinnedNetworkStream(stream, self._plan)

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: object = None,
    ) -> httpcore2.AsyncNetworkStream:
        raise _UnexpectedConnectionTarget()

    async def sleep(self, seconds: float) -> None:
        raise _UnexpectedConnectionTarget()


class _CoreResponseStream(httpx2.AsyncByteStream):
    def __init__(self, stream: AsyncIterator[bytes]) -> None:
        self._stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            yield chunk

    async def aclose(self) -> None:
        close = getattr(self._stream, "aclose", None)
        if close is not None:
            await close()


class PinnedAsyncTransport(httpx2.AsyncBaseTransport):
    def __init__(
        self,
        plan: ConnectionPlan,
        *,
        network_backend: httpcore2.AsyncNetworkBackend | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        backend = network_backend or httpcore2.AnyIOBackend()
        pinned_backend = PinnedNetworkBackend(plan, backend)
        context = ssl_context or ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        self._pool = httpcore2.AsyncConnectionPool(
            ssl_context=context,
            max_connections=1,
            max_keepalive_connections=0,
            keepalive_expiry=0.0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=pinned_backend,
        )

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self._pool.handle_async_request(
            httpcore2.Request(
                request.method,
                str(request.url),
                headers=request.headers.raw,
                content=request.stream,
                extensions=request.extensions,
            )
        )
        return httpx2.Response(
            response.status,
            headers=response.headers,
            stream=_CoreResponseStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


def create_pinned_transport(plan: ConnectionPlan) -> httpx2.AsyncBaseTransport:
    return PinnedAsyncTransport(plan)


def _safe_identifier(value: object) -> str:
    if isinstance(value, str) and _SAFE_IDENTIFIER_PATTERN.fullmatch(value):
        return value
    return "invalid"


def _request_id() -> str:
    current = request_id_context.get()
    return current if is_valid_request_id(current) else uuid.uuid4().hex


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, dict):
        return FrozenJsonObject(
            tuple((str(key), _freeze_json(item)) for key, item in value.items())
        )
    raise ValueError("unsupported JSON value")


def _reject_json_constant(value: str) -> None:
    raise ValueError("non-finite JSON number")


def _parse_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite JSON number")
    return parsed


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _parse_retry_after(value: str | None) -> int | None:
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    seconds = int(value)
    return seconds if 0 <= seconds <= MAX_RETRY_AFTER_SECONDS else None


def _status_error_code(status_code: int) -> OutboundErrorCode | None:
    if 200 <= status_code <= 299:
        return None
    if 300 <= status_code <= 399:
        return OutboundErrorCode.REDIRECT_BLOCKED
    if status_code == 401:
        return OutboundErrorCode.UNAUTHORIZED
    if status_code == 403:
        return OutboundErrorCode.FORBIDDEN
    if status_code == 404:
        return OutboundErrorCode.NOT_FOUND
    if status_code == 429:
        return OutboundErrorCode.RATE_LIMITED
    if 500 <= status_code <= 599:
        return OutboundErrorCode.PROVIDER_SERVER_ERROR
    return OutboundErrorCode.UNEXPECTED_STATUS


def _status_class(status_code: int | None) -> str:
    if status_code is None or not 100 <= status_code <= 599:
        return "none"
    return f"{status_code // 100}xx"


def _latency_bucket(milliseconds: float) -> str:
    if milliseconds < 50:
        return "lt_50ms"
    if milliseconds < 250:
        return "lt_250ms"
    if milliseconds < 1000:
        return "lt_1s"
    if milliseconds < 5000:
        return "lt_5s"
    return "gte_5s"


def _validate_public_addresses(addresses: tuple[str, ...]) -> tuple[str, ...]:
    if not addresses:
        raise ValueError("no addresses")
    approved: list[str] = []
    for raw_address in addresses:
        if not isinstance(raw_address, str):
            raise ValueError("unsafe address")
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise ValueError("unsafe address") from exc
        mapped = getattr(address, "ipv4_mapped", None)
        if mapped is not None and not mapped.is_global:
            raise ValueError("unsafe address")
        if (
            not address.is_global
            or address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ValueError("unsafe address")
        normalized = address.compressed
        if normalized not in approved:
            approved.append(normalized)
    return tuple(approved)


class OutboundHttpClient:
    def __init__(
        self,
        *,
        registry: EndpointRegistry = PRODUCTION_ENDPOINT_REGISTRY,
        resolver: AddressResolver | None = None,
        transport_factory: TransportFactory = create_pinned_transport,
        clock: Clock | None = None,
    ) -> None:
        self._registry = registry
        self._resolver = resolver or SystemAddressResolver()
        self._transport_factory = transport_factory
        self._clock = clock or SystemClock()
        self._global_semaphore = asyncio.Semaphore(GLOBAL_CONCURRENCY_LIMIT)
        self._provider_semaphores = {
            provider.provider_key: asyncio.Semaphore(PROVIDER_CONCURRENCY_LIMIT)
            for provider in registry.providers
        }

    async def fetch_json(self, request: OutboundRequest) -> OutboundJsonResponse:
        request_id = _request_id()
        provider_key = _safe_identifier(request.provider_key)
        operation_name = _safe_identifier(request.operation)
        started_at = self._clock.monotonic()
        deadline = started_at + TOTAL_TIMEOUT_SECONDS
        outcome = OutboundErrorCode.INVALID_REQUEST.value
        status_code: int | None = None
        try:
            provider = self._registry.provider(request.provider_key)
            if provider is None:
                raise self._error(
                    OutboundErrorCode.PROVIDER_NOT_ALLOWED,
                    provider_key,
                    operation_name,
                    request_id,
                )
            operation = provider.operation(request.operation)
            if operation is None:
                raise self._error(
                    OutboundErrorCode.OPERATION_NOT_ALLOWED,
                    provider.provider_key,
                    operation_name,
                    request_id,
                )
            url = self._build_url(provider, operation, request, request_id)
            provider_semaphore = self._provider_semaphores[provider.provider_key]
            async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
                async with self._global_semaphore, provider_semaphore:
                    approved_ips = await self._resolve_addresses(
                        provider,
                        operation,
                        request_id,
                    )
                    if self._clock.monotonic() >= deadline:
                        raise TimeoutError()
                    plan = ConnectionPlan(
                        hostname=provider.hostname,
                        port=provider.port,
                        approved_ips=approved_ips,
                        selected_ip=approved_ips[0],
                    )
                    response = await self._send(
                        provider,
                        operation,
                        url,
                        plan,
                        request_id,
                    )
                    if self._clock.monotonic() >= deadline:
                        raise TimeoutError()
            status_code = response.status_code
            outcome = "success"
            return response
        except asyncio.CancelledError:
            outcome = OutboundErrorCode.CANCELLED.value
            raise
        except TimeoutError:
            outcome = OutboundErrorCode.REQUEST_TIMEOUT.value
            raise self._error(
                OutboundErrorCode.REQUEST_TIMEOUT,
                provider_key,
                operation_name,
                request_id,
            ) from None
        except OutboundHttpError as exc:
            outcome = exc.error.code.value
            status_code = exc.error.status_code
            raise
        finally:
            elapsed_ms = max(0.0, (self._clock.monotonic() - started_at) * 1000)
            logger.info(
                "outbound_request provider=%s operation=%s outcome=%s "
                "status_class=%s latency=%s request_id=%s",
                provider_key,
                operation_name,
                outcome,
                _status_class(status_code),
                _latency_bucket(elapsed_ms),
                request_id,
            )

    async def _resolve_addresses(
        self,
        provider: ProviderEndpoint,
        operation: EndpointOperation,
        request_id: str,
    ) -> tuple[str, ...]:
        try:
            addresses = await self._resolver.resolve(provider.hostname, provider.port)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise
        except Exception:
            raise self._error(
                OutboundErrorCode.DNS_RESOLUTION_FAILED,
                provider.provider_key,
                operation.name,
                request_id,
            ) from None
        if not addresses:
            raise self._error(
                OutboundErrorCode.DNS_RESOLUTION_FAILED,
                provider.provider_key,
                operation.name,
                request_id,
            )
        try:
            return _validate_public_addresses(addresses)
        except (OutboundHttpError, ValueError):
            raise self._error(
                OutboundErrorCode.UNSAFE_ADDRESS,
                provider.provider_key,
                operation.name,
                request_id,
            ) from None

    def _build_url(
        self,
        provider: ProviderEndpoint,
        operation: EndpointOperation,
        request: OutboundRequest,
        request_id: str,
    ) -> str:
        values: dict[BusinessParameter, object | None] = {
            BusinessParameter.QUERY: request.query,
            BusinessParameter.EXTERNAL_ID: request.external_id,
            BusinessParameter.PAGE: request.page,
            BusinessParameter.PAGE_SIZE: request.page_size,
        }
        available = {key for key, _ in operation.query_parameters}
        if operation.path_parameter is not None:
            available.add(operation.path_parameter)
        if any(value is not None and key not in available for key, value in values.items()):
            raise self._error(
                OutboundErrorCode.INVALID_REQUEST,
                provider.provider_key,
                operation.name,
                request_id,
            )
        for required in operation.required_parameters:
            if values[required] is None:
                raise self._error(
                    OutboundErrorCode.INVALID_REQUEST,
                    provider.provider_key,
                    operation.name,
                    request_id,
                )

        query = request.query
        if query is not None:
            if not isinstance(query, str):
                raise self._error(
                    OutboundErrorCode.INVALID_REQUEST,
                    provider.provider_key,
                    operation.name,
                    request_id,
                )
            query = query.strip()
            if (
                not query
                or len(query) > MAX_QUERY_LENGTH
                or any(ord(character) < 32 or ord(character) == 127 for character in query)
            ):
                raise self._error(
                    OutboundErrorCode.INVALID_REQUEST,
                    provider.provider_key,
                    operation.name,
                    request_id,
                )
            values[BusinessParameter.QUERY] = query
        external_id = request.external_id
        if external_id is not None and (
            not isinstance(external_id, str)
            or not external_id
            or len(external_id) > MAX_EXTERNAL_ID_LENGTH
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in external_id
            )
        ):
            raise self._error(
                OutboundErrorCode.INVALID_REQUEST,
                provider.provider_key,
                operation.name,
                request_id,
            )
        for key, value in (
            (BusinessParameter.PAGE, request.page),
            (BusinessParameter.PAGE_SIZE, request.page_size),
        ):
            if value is None:
                continue
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise self._error(
                    OutboundErrorCode.INVALID_REQUEST,
                    provider.provider_key,
                    operation.name,
                    request_id,
                )
            if key is BusinessParameter.PAGE_SIZE and value > min(
                operation.page_size_limit,
                MAX_PAGE_SIZE,
            ):
                raise self._error(
                    OutboundErrorCode.INVALID_REQUEST,
                    provider.provider_key,
                    operation.name,
                    request_id,
                )

        try:
            path = operation.render_path(external_id)
        except (TypeError, ValueError):
            raise self._error(
                OutboundErrorCode.INVALID_REQUEST,
                provider.provider_key,
                operation.name,
                request_id,
            ) from None
        query_items = [
            (query_name, str(values[business_parameter]))
            for business_parameter, query_name in operation.query_parameters
            if values[business_parameter] is not None
        ]
        query_string = urlencode(query_items, doseq=False, safe="")
        suffix = f"?{query_string}" if query_string else ""
        return f"https://{provider.hostname}{path}{suffix}"

    async def _send(
        self,
        provider: ProviderEndpoint,
        operation: EndpointOperation,
        url: str,
        plan: ConnectionPlan,
        request_id: str,
    ) -> OutboundJsonResponse:
        transport = self._transport_factory(plan)
        timeout = httpx2.Timeout(
            TOTAL_TIMEOUT_SECONDS,
            connect=CONNECT_TIMEOUT_SECONDS,
        )
        try:
            async with httpx2.AsyncClient(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
                http1=True,
                http2=False,
                proxy=None,
                auth=None,
                cookies=None,
                timeout=timeout,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                    "Host": provider.hostname,
                },
            ) as client:
                async with client.stream("GET", url) as response:
                    status_code = response.status_code
                    status_error = _status_error_code(status_code)
                    if status_error is not None:
                        retry_after = (
                            _parse_retry_after(response.headers.get("Retry-After"))
                            if status_error is OutboundErrorCode.RATE_LIMITED
                            else None
                        )
                        raise self._error(
                            status_error,
                            provider.provider_key,
                            operation.name,
                            request_id,
                            status_code=status_code,
                            retry_after_seconds=retry_after,
                        )
                    content_encoding = response.headers.get("Content-Encoding")
                    if content_encoding is not None and (
                        content_encoding.strip().casefold() not in {"", "identity"}
                    ):
                        raise self._error(
                            OutboundErrorCode.UNEXPECTED_CONTENT_ENCODING,
                            provider.provider_key,
                            operation.name,
                            request_id,
                            status_code=status_code,
                        )
                    content_type = response.headers.get("Content-Type", "")
                    media_type = content_type.split(";", 1)[0].strip()
                    if _JSON_CONTENT_TYPE_PATTERN.fullmatch(media_type) is None:
                        raise self._error(
                            OutboundErrorCode.UNEXPECTED_CONTENT_TYPE,
                            provider.provider_key,
                            operation.name,
                            request_id,
                            status_code=status_code,
                        )
                    content_length = response.headers.get("Content-Length")
                    if (
                        content_length is not None
                        and content_length.isascii()
                        and content_length.isdecimal()
                        and int(content_length) > operation.response_limit_bytes
                    ):
                        raise self._error(
                            OutboundErrorCode.RESPONSE_TOO_LARGE,
                            provider.provider_key,
                            operation.name,
                            request_id,
                            status_code=status_code,
                        )
                    body = bytearray()
                    async for chunk in response.aiter_raw():
                        if len(body) + len(chunk) > operation.response_limit_bytes:
                            raise self._error(
                                OutboundErrorCode.RESPONSE_TOO_LARGE,
                                provider.provider_key,
                                operation.name,
                                request_id,
                                status_code=status_code,
                            )
                        body.extend(chunk)
                    try:
                        payload = json.loads(
                            bytes(body),
                            parse_constant=_reject_json_constant,
                            parse_float=_parse_json_float,
                            object_pairs_hook=_json_object,
                        )
                    except (
                        RecursionError,
                        UnicodeDecodeError,
                        json.JSONDecodeError,
                        ValueError,
                    ):
                        raise self._error(
                            OutboundErrorCode.MALFORMED_JSON,
                            provider.provider_key,
                            operation.name,
                            request_id,
                            status_code=status_code,
                        ) from None
                    if (
                        operation.expected_top_level is JsonTopLevel.OBJECT
                        and not isinstance(payload, dict)
                    ) or (
                        operation.expected_top_level is JsonTopLevel.ARRAY
                        and not isinstance(payload, list)
                    ):
                        raise self._error(
                            OutboundErrorCode.INVALID_PAYLOAD,
                            provider.provider_key,
                            operation.name,
                            request_id,
                            status_code=status_code,
                        )
                    try:
                        frozen = _freeze_json(payload)
                    except (RecursionError, ValueError):
                        raise self._error(
                            OutboundErrorCode.MALFORMED_JSON,
                            provider.provider_key,
                            operation.name,
                            request_id,
                            status_code=status_code,
                        ) from None
                    if not isinstance(frozen, (FrozenJsonObject, tuple)):
                        raise self._error(
                            OutboundErrorCode.INVALID_PAYLOAD,
                            provider.provider_key,
                            operation.name,
                            request_id,
                            status_code=status_code,
                        )
                    return OutboundJsonResponse(status_code=status_code, data=frozen)
        except asyncio.CancelledError:
            raise
        except OutboundHttpError:
            raise
        except _PeerAddressMismatch:
            raise self._error(
                OutboundErrorCode.PEER_ADDRESS_MISMATCH,
                provider.provider_key,
                operation.name,
                request_id,
            ) from None
        except _TlsHandshakeFailed:
            raise self._error(
                OutboundErrorCode.TLS_FAILED,
                provider.provider_key,
                operation.name,
                request_id,
            ) from None
        except _UnexpectedConnectionTarget:
            raise self._error(
                OutboundErrorCode.CONNECTION_FAILED,
                provider.provider_key,
                operation.name,
                request_id,
            ) from None
        except (httpcore2.ConnectTimeout, httpx2.ConnectTimeout):
            raise self._error(
                OutboundErrorCode.CONNECT_TIMEOUT,
                provider.provider_key,
                operation.name,
                request_id,
            ) from None
        except (
            httpcore2.ReadTimeout,
            httpcore2.WriteTimeout,
            httpcore2.PoolTimeout,
            httpx2.ReadTimeout,
            httpx2.WriteTimeout,
            httpx2.PoolTimeout,
            httpcore2.TimeoutException,
            httpx2.TimeoutException,
        ):
            raise self._error(
                OutboundErrorCode.REQUEST_TIMEOUT,
                provider.provider_key,
                operation.name,
                request_id,
            ) from None
        except (httpcore2.ConnectError, httpx2.ConnectError, OSError):
            raise self._error(
                OutboundErrorCode.CONNECTION_FAILED,
                provider.provider_key,
                operation.name,
                request_id,
            ) from None
        except (httpcore2.ProtocolError, httpx2.ProtocolError):
            raise self._error(
                OutboundErrorCode.CONNECTION_FAILED,
                provider.provider_key,
                operation.name,
                request_id,
            ) from None
        except Exception:
            raise self._error(
                OutboundErrorCode.CONNECTION_FAILED,
                provider.provider_key,
                operation.name,
                request_id,
            ) from None

    @staticmethod
    def _error(
        code: OutboundErrorCode,
        provider_key: str,
        operation: str,
        request_id: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> OutboundHttpError:
        return OutboundHttpError(
            OutboundError(
                code=code,
                provider_key=_safe_identifier(provider_key),
                operation=_safe_identifier(operation),
                request_id=request_id,
                status_code=status_code,
                retry_after_seconds=retry_after_seconds,
            )
        )
