from __future__ import annotations

import asyncio
import logging
import ssl
from collections.abc import AsyncIterator, Callable
from dataclasses import FrozenInstanceError
from pathlib import Path

import httpcore2
import httpx2
import pytest

from app.request_context import request_id_context
from app.source_adapters.contracts import (
    MetadataCapabilities,
    ProviderCapabilities,
    ProviderOperation,
)
from app.source_adapters.registry import (
    BusinessParameter,
    EndpointOperation,
    EndpointRegistry,
    JsonTopLevel,
    ProviderEndpoint,
)
from app.services.outbound_http import (
    ConnectionPlan,
    FrozenJsonObject,
    OutboundErrorCode,
    OutboundHttpClient,
    OutboundHttpError,
    OutboundRequest,
    PinnedAsyncTransport,
)

SAFE_IPV4 = "8.8.8.8"
SAFE_IPV6 = "2606:4700:4700::1111"
HOSTNAME = "metadata.example"


class FakeResolver:
    def __init__(
        self,
        addresses: tuple[str, ...] = (SAFE_IPV4,),
        error: Exception | None = None,
    ) -> None:
        self.addresses = addresses
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        self.calls.append((hostname, port))
        if self.error is not None:
            raise self.error
        return self.addresses


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def monotonic(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class ChunkStream(httpx2.AsyncByteStream):
    def __init__(
        self,
        chunks: tuple[bytes, ...],
        *,
        error: BaseException | None = None,
    ) -> None:
        self.chunks = chunks
        self.error = error
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class MockTransportFactory:
    def __init__(
        self,
        handler: Callable[[httpx2.Request], httpx2.Response],
    ) -> None:
        self.handler = handler
        self.plans: list[ConnectionPlan] = []
        self.requests: list[httpx2.Request] = []

    def __call__(self, plan: ConnectionPlan) -> httpx2.AsyncBaseTransport:
        self.plans.append(plan)

        async def handle(request: httpx2.Request) -> httpx2.Response:
            self.requests.append(request)
            return self.handler(request)

        return httpx2.MockTransport(handle)


def _operation(
    *,
    expected_top_level: JsonTopLevel = JsonTopLevel.OBJECT,
    response_limit_bytes: int = 1024 * 1024,
) -> EndpointOperation:
    return EndpointOperation(
        operation=ProviderOperation.SEARCH,
        path_template="/v1/search",
        expected_top_level=expected_top_level,
        query_parameters=(
            (BusinessParameter.QUERY, "q"),
            (BusinessParameter.PAGE, "page"),
            (BusinessParameter.PAGE_SIZE, "limit"),
        ),
        required_parameters=(BusinessParameter.QUERY,),
        response_limit_bytes=response_limit_bytes,
        page_size_limit=50,
    )


def _registry(
    *,
    providers: int = 1,
    operation: EndpointOperation | None = None,
) -> EndpointRegistry:
    selected_operation = operation or _operation()
    return EndpointRegistry(
        tuple(
            ProviderEndpoint(
                provider_key=f"unit_test_{index}",
                hostname=HOSTNAME,
                capabilities=ProviderCapabilities(
                    provider_key=f"unit_test_{index}",
                    display_name="Unit Test",
                    content_scope="synthetic test records",
                    metadata=MetadataCapabilities((selected_operation.operation,)),
                ),
                operations=(selected_operation,),
            )
            for index in range(providers)
        )
    )


def _response(
    body: bytes = b'{"ok":true}',
    *,
    status: int = 200,
    content_type: str = "application/json",
    headers: dict[str, str] | None = None,
    chunks: tuple[bytes, ...] | None = None,
) -> httpx2.Response:
    response_headers = {"Content-Type": content_type}
    if headers:
        response_headers.update(headers)
    return httpx2.Response(
        status,
        headers=response_headers,
        stream=ChunkStream(chunks or (body,)),
    )


def _client(
    factory: MockTransportFactory,
    *,
    resolver: FakeResolver | None = None,
    clock: FakeClock | None = None,
    registry: EndpointRegistry | None = None,
) -> OutboundHttpClient:
    return OutboundHttpClient(
        registry=registry or _registry(),
        resolver=resolver or FakeResolver(),
        transport_factory=factory,
        clock=clock or FakeClock(),
    )


def _fetch(
    client: OutboundHttpClient,
    request: OutboundRequest | None = None,
) -> object:
    return asyncio.run(
        client.fetch_json(
            request
            or OutboundRequest(
                "unit_test_0",
                "search",
                query="example",
                page=1,
                page_size=20,
            )
        )
    )


def _error_code(
    client: OutboundHttpClient,
    request: OutboundRequest | None = None,
) -> OutboundHttpError:
    with pytest.raises(OutboundHttpError) as exc_info:
        _fetch(client, request)
    return exc_info.value


def test_success_builds_only_the_fixed_url_and_returns_immutable_json() -> None:
    factory = MockTransportFactory(lambda _: _response())
    resolver = FakeResolver((SAFE_IPV4, SAFE_IPV6))
    result = _fetch(_client(factory, resolver=resolver))

    assert result.status_code == 200
    assert isinstance(result.data, FrozenJsonObject)
    assert result.data["ok"] is True
    assert factory.plans == [
        ConnectionPlan(HOSTNAME, 443, (SAFE_IPV4, SAFE_IPV6), SAFE_IPV4)
    ]
    assert str(factory.requests[0].url) == (
        "https://metadata.example/v1/search?q=example&page=1&limit=20"
    )
    assert factory.requests[0].headers["Host"] == HOSTNAME
    assert factory.requests[0].headers["Accept-Encoding"] == "identity"
    assert "Authorization" not in factory.requests[0].headers
    assert "Cookie" not in factory.requests[0].headers
    with pytest.raises(FrozenInstanceError):
        result.status_code = 201  # type: ignore[misc]


def test_ipv6_only_resolution_is_approved_and_selected() -> None:
    factory = MockTransportFactory(lambda _: _response())
    _fetch(_client(factory, resolver=FakeResolver((SAFE_IPV6,))))
    assert factory.plans == [
        ConnectionPlan(HOSTNAME, 443, (SAFE_IPV6,), SAFE_IPV6)
    ]


def test_unknown_provider_operation_and_invalid_input_do_not_resolve() -> None:
    factory = MockTransportFactory(lambda _: _response())
    resolver = FakeResolver()
    client = _client(factory, resolver=resolver)

    assert _error_code(
        client,
        OutboundRequest("missing", "search", query="example"),
    ).error.code is OutboundErrorCode.PROVIDER_NOT_ALLOWED
    assert _error_code(
        client,
        OutboundRequest("unit_test_0", "missing", query="example"),
    ).error.code is OutboundErrorCode.OPERATION_NOT_ALLOWED
    assert _error_code(
        client,
        OutboundRequest("unit_test_0", "search", query=" "),
    ).error.code is OutboundErrorCode.INVALID_REQUEST
    assert resolver.calls == []
    assert factory.plans == []


def test_default_production_client_cannot_reach_any_provider() -> None:
    factory = MockTransportFactory(lambda _: _response())
    resolver = FakeResolver()
    client = OutboundHttpClient(
        resolver=resolver,
        transport_factory=factory,
        clock=FakeClock(),
    )
    error = _error_code(
        client,
        OutboundRequest("unit_test_0", "search", query="example"),
    )
    assert error.error.code is OutboundErrorCode.PROVIDER_NOT_ALLOWED
    assert resolver.calls == []
    assert factory.plans == []


@pytest.mark.parametrize(
    "outbound_request",
    [
        OutboundRequest("unit_test_0", "search", query="x" * 201),
        OutboundRequest("unit_test_0", "search", query=1),  # type: ignore[arg-type]
        OutboundRequest("unit_test_0", "search", query="x", page=0),
        OutboundRequest("unit_test_0", "search", query="x", page=True),
        OutboundRequest("unit_test_0", "search", query="x", page_size=0),
        OutboundRequest("unit_test_0", "search", query="x", page_size=51),
        OutboundRequest("unit_test_0", "search", query="x", external_id="extra"),
    ],
)
def test_request_parameter_boundaries_fail_before_dns(
    outbound_request: OutboundRequest,
) -> None:
    resolver = FakeResolver()
    error = _error_code(
        _client(MockTransportFactory(lambda _: _response()), resolver=resolver),
        outbound_request,
    )
    assert error.error.code is OutboundErrorCode.INVALID_REQUEST
    assert resolver.calls == []


def test_detail_external_id_is_encoded_as_one_path_segment() -> None:
    detail = EndpointOperation(
        ProviderOperation.DETAIL,
        "/v1/items/{external_id}",
        JsonTopLevel.OBJECT,
        path_parameter=BusinessParameter.EXTERNAL_ID,
        required_parameters=(BusinessParameter.EXTERNAL_ID,),
    )
    registry = EndpointRegistry(
        (
            ProviderEndpoint(
                "unit_test_0",
                HOSTNAME,
                ProviderCapabilities(
                    provider_key="unit_test_0",
                    display_name="Unit Test",
                    content_scope="synthetic test records",
                    metadata=MetadataCapabilities((ProviderOperation.DETAIL,)),
                ),
                (detail,),
            ),
        )
    )
    factory = MockTransportFactory(lambda _: _response())
    _fetch(
        _client(factory, registry=registry),
        OutboundRequest("unit_test_0", "detail", external_id="a/b ?#"),
    )
    assert str(factory.requests[0].url) == (
        "https://metadata.example/v1/items/a%2Fb%20%3F%23"
    )


@pytest.mark.parametrize(
    "addresses",
    [
        ("127.0.0.1",),
        ("10.0.0.1",),
        ("169.254.1.1",),
        ("224.0.0.1",),
        ("192.0.2.1",),
        ("0.0.0.0",),
        ("::1",),
        ("fe80::1",),
        ("ff02::1",),
        ("::",),
        ("::ffff:127.0.0.1",),
        (SAFE_IPV4, "127.0.0.1"),
        ("not-an-ip",),
        (1,),  # type: ignore[list-item]
    ],
)
def test_unsafe_or_mixed_dns_results_are_rejected_as_a_whole(
    addresses: tuple[str, ...],
) -> None:
    factory = MockTransportFactory(lambda _: _response())
    error = _error_code(_client(factory, resolver=FakeResolver(addresses)))
    assert error.error.code is OutboundErrorCode.UNSAFE_ADDRESS
    assert factory.plans == []


def test_empty_and_failed_dns_have_stable_errors() -> None:
    factory = MockTransportFactory(lambda _: _response())
    empty = _error_code(_client(factory, resolver=FakeResolver(())))
    failed = _error_code(
        _client(factory, resolver=FakeResolver(error=OSError("secret topology")))
    )
    assert empty.error.code is OutboundErrorCode.DNS_RESOLUTION_FAILED
    assert failed.error.code is OutboundErrorCode.DNS_RESOLUTION_FAILED
    assert "secret topology" not in str(failed)


def test_dns_timeout_is_part_of_the_total_request_deadline() -> None:
    error = _error_code(
        _client(
            MockTransportFactory(lambda _: _response()),
            resolver=FakeResolver(error=TimeoutError()),
        )
    )
    assert error.error.code is OutboundErrorCode.REQUEST_TIMEOUT


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (302, OutboundErrorCode.REDIRECT_BLOCKED),
        (401, OutboundErrorCode.UNAUTHORIZED),
        (403, OutboundErrorCode.FORBIDDEN),
        (404, OutboundErrorCode.NOT_FOUND),
        (429, OutboundErrorCode.RATE_LIMITED),
        (500, OutboundErrorCode.PROVIDER_SERVER_ERROR),
        (599, OutboundErrorCode.PROVIDER_SERVER_ERROR),
        (418, OutboundErrorCode.UNEXPECTED_STATUS),
    ],
)
def test_http_statuses_use_stable_errors(status: int, code: OutboundErrorCode) -> None:
    error = _error_code(
        _client(MockTransportFactory(lambda _: _response(status=status)))
    )
    assert error.error.code is code
    assert error.error.status_code == status


@pytest.mark.parametrize(
    ("value", "expected"),
    [("120", 120), ("0", 0), ("3601", None), ("Wed, 01 Jan 2026", None), ("-1", None)],
)
def test_retry_after_is_bounded_and_numeric_only(
    value: str,
    expected: int | None,
) -> None:
    error = _error_code(
        _client(
            MockTransportFactory(
                lambda _: _response(status=429, headers={"Retry-After": value})
            )
        )
    )
    assert error.error.retry_after_seconds == expected


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "application/problem+json", "application/json; charset=utf-8"],
)
def test_expected_json_content_types_are_accepted(content_type: str) -> None:
    result = _fetch(
        _client(MockTransportFactory(lambda _: _response(content_type=content_type)))
    )
    assert result.data["ok"] is True


def test_content_type_encoding_json_and_payload_failures_are_distinct() -> None:
    not_json = _error_code(
        _client(MockTransportFactory(lambda _: _response(content_type="text/plain")))
    )
    compressed = _error_code(
        _client(
            MockTransportFactory(
                lambda _: _response(headers={"Content-Encoding": "gzip"})
            )
        )
    )
    malformed = _error_code(
        _client(MockTransportFactory(lambda _: _response(body=b"{")))
    )
    invalid_payload = _error_code(
        _client(MockTransportFactory(lambda _: _response(body=b"[]")))
    )
    assert not_json.error.code is OutboundErrorCode.UNEXPECTED_CONTENT_TYPE
    assert compressed.error.code is OutboundErrorCode.UNEXPECTED_CONTENT_ENCODING
    assert malformed.error.code is OutboundErrorCode.MALFORMED_JSON
    assert invalid_payload.error.code is OutboundErrorCode.INVALID_PAYLOAD


def test_duplicate_json_object_keys_are_rejected() -> None:
    error = _error_code(
        _client(
            MockTransportFactory(
                lambda _: _response(body=b'{"value":1,"value":2}')
            )
        )
    )
    assert error.error.code is OutboundErrorCode.MALFORMED_JSON


@pytest.mark.parametrize(
    "body",
    [b'{"value":NaN}', b'{"value":1e10000}'],
)
def test_non_finite_json_numbers_are_rejected(body: bytes) -> None:
    error = _error_code(
        _client(MockTransportFactory(lambda _: _response(body=body)))
    )
    assert error.error.code is OutboundErrorCode.MALFORMED_JSON


def test_deeply_nested_json_is_rejected_with_a_stable_error() -> None:
    depth = 700
    body = b'{"value":' + (b"[" * depth) + b"0" + (b"]" * depth) + b"}"
    error = _error_code(
        _client(MockTransportFactory(lambda _: _response(body=body)))
    )
    assert error.error.code is OutboundErrorCode.MALFORMED_JSON


def test_identity_content_encoding_is_case_insensitive() -> None:
    result = _fetch(
        _client(
            MockTransportFactory(
                lambda _: _response(headers={"Content-Encoding": " Identity "})
            )
        )
    )
    assert result.data["ok"] is True


def test_stream_limit_accepts_exact_limit_and_rejects_one_extra_byte() -> None:
    exact_body = b"[0,0,0]"
    operation = _operation(
        expected_top_level=JsonTopLevel.ARRAY,
        response_limit_bytes=len(exact_body),
    )
    array_body = exact_body
    accepted = _fetch(
        _client(
            MockTransportFactory(
                lambda _: _response(body=array_body, chunks=(array_body[:5], array_body[5:]))
            ),
            registry=_registry(operation=operation),
        )
    )
    assert isinstance(accepted.data, tuple)

    too_large = array_body + b" "
    error = _error_code(
        _client(
            MockTransportFactory(
                lambda _: _response(chunks=(too_large[:-1], too_large[-1:]))
            ),
            registry=_registry(operation=operation),
        )
    )
    assert error.error.code is OutboundErrorCode.RESPONSE_TOO_LARGE


def test_content_length_over_limit_is_rejected_before_streaming() -> None:
    stream = ChunkStream((b'{"ok":true}',))

    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(1024 * 1024 + 1),
            },
            stream=stream,
        )

    error = _error_code(_client(MockTransportFactory(handler)))
    assert error.error.code is OutboundErrorCode.RESPONSE_TOO_LARGE
    assert stream.closed is True


@pytest.mark.parametrize(
    ("transport_error", "code"),
    [
        (httpx2.ConnectTimeout("hidden"), OutboundErrorCode.CONNECT_TIMEOUT),
        (httpx2.ReadTimeout("hidden"), OutboundErrorCode.REQUEST_TIMEOUT),
        (httpx2.ConnectError("hidden"), OutboundErrorCode.CONNECTION_FAILED),
    ],
)
def test_transport_failures_are_stable_and_never_retried(
    transport_error: Exception,
    code: OutboundErrorCode,
) -> None:
    calls = 0

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        raise transport_error

    error = _error_code(_client(MockTransportFactory(handler)))
    assert error.error.code is code
    assert calls == 1
    assert "hidden" not in str(error)


def test_total_deadline_includes_response_and_json_processing() -> None:
    clock = FakeClock()

    def handler(_: httpx2.Request) -> httpx2.Response:
        clock.advance(10.1)
        return _response()

    error = _error_code(
        _client(MockTransportFactory(handler), clock=clock)
    )
    assert error.error.code is OutboundErrorCode.REQUEST_TIMEOUT


def test_proxy_environment_cookie_and_set_cookie_do_not_cross_requests(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    netrc_path = tmp_path / "fake.netrc"
    netrc_path.write_text(
        "machine metadata.example login hidden password hidden\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NETRC", str(netrc_path))
    seen_headers: list[httpx2.Headers] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen_headers.append(request.headers)
        return _response(headers={"Set-Cookie": "provider_session=secret"})

    client = _client(MockTransportFactory(handler))
    _fetch(client)
    _fetch(client)
    assert len(seen_headers) == 2
    assert all("Proxy-Authorization" not in headers for headers in seen_headers)
    assert all("Authorization" not in headers for headers in seen_headers)
    assert all("Cookie" not in headers for headers in seen_headers)


def test_logs_are_bounded_and_do_not_include_sensitive_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = request_id_context.set("12345678123456781234567812345678")
    try:
        with caplog.at_level(logging.INFO, logger="uvicorn.error.nsfwtrack.outbound"):
            _fetch(
                _client(MockTransportFactory(lambda _: _response())),
                OutboundRequest(
                    "unit_test_0",
                    "search",
                    query="private search terms",
                    page=1,
                    page_size=20,
                ),
            )
    finally:
        request_id_context.reset(token)
    text = caplog.text
    assert "provider=unit_test_0" in text
    assert "operation=search" in text
    assert "outcome=success" in text
    assert "private search terms" not in text
    assert SAFE_IPV4 not in text
    assert "https://" not in text


class FakeSSLObject:
    def selected_alpn_protocol(self) -> str:
        return "http/1.1"


class FakeNetworkStream(httpcore2.AsyncNetworkStream):
    def __init__(
        self,
        *,
        peer_ip: str = SAFE_IPV4,
        tls_peer_ip: str | None = None,
        tls_error: Exception | None = None,
        read_error: BaseException | None = None,
    ) -> None:
        self.peer_ip = peer_ip
        self.tls_peer_ip = tls_peer_ip or peer_ip
        self.tls_error = tls_error
        self.read_error = read_error
        self.tls_started = False
        self.sni: list[str | None] = []
        self.writes: list[bytes] = []
        self.closed = False
        self.ssl_check_hostname: bool | None = None
        self.ssl_verify_mode: ssl.VerifyMode | None = None
        self.buffer = [
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Length: 11\r\nConnection: close\r\n\r\n{\"ok\":true}"
        ]

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if self.read_error is not None:
            raise self.read_error
        return self.buffer.pop(0) if self.buffer else b""

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.writes.append(buffer)

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        self.sni.append(server_hostname)
        self.ssl_check_hostname = ssl_context.check_hostname
        self.ssl_verify_mode = ssl_context.verify_mode
        if self.tls_error is not None:
            raise self.tls_error
        self.tls_started = True
        return self

    def get_extra_info(self, info: str) -> object:
        if info == "server_addr":
            return (
                self.tls_peer_ip if self.tls_started else self.peer_ip,
                443,
            )
        if info == "ssl_object" and self.tls_started:
            return FakeSSLObject()
        return None


class FakeNetworkBackend(httpcore2.AsyncNetworkBackend):
    def __init__(
        self,
        stream: FakeNetworkStream,
        *,
        connect_error: Exception | None = None,
    ) -> None:
        self.stream = stream
        self.connect_error = connect_error
        self.calls: list[tuple[str, int, float | None]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object = None,
    ) -> httpcore2.AsyncNetworkStream:
        self.calls.append((host, port, timeout))
        if self.connect_error is not None:
            raise self.connect_error
        return self.stream

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: object = None,
    ) -> httpcore2.AsyncNetworkStream:
        raise AssertionError("unix sockets are forbidden")

    async def sleep(self, seconds: float) -> None:
        raise AssertionError("retries are forbidden")


def _pinned_client(
    backend: FakeNetworkBackend,
    *,
    resolver: FakeResolver | None = None,
) -> OutboundHttpClient:
    return OutboundHttpClient(
        registry=_registry(),
        resolver=resolver or FakeResolver(),
        clock=FakeClock(),
        transport_factory=lambda plan: PinnedAsyncTransport(
            plan,
            network_backend=backend,
        ),
    )


def test_connection_is_pinned_while_tls_sni_and_host_keep_the_hostname() -> None:
    stream = FakeNetworkStream()
    backend = FakeNetworkBackend(stream)
    result = _fetch(
        _pinned_client(
            backend,
            resolver=FakeResolver((SAFE_IPV4, SAFE_IPV6)),
        )
    )

    assert result.data["ok"] is True
    assert backend.calls == [(SAFE_IPV4, 443, 3.0)]
    assert stream.sni == [HOSTNAME]
    assert stream.ssl_check_hostname is True
    assert stream.ssl_verify_mode == ssl.CERT_REQUIRED
    request_bytes = b"".join(stream.writes)
    assert b"Host: metadata.example\r\n" in request_bytes
    assert b"Accept-Encoding: identity\r\n" in request_bytes
    assert b"Authorization:" not in request_bytes
    assert b"Cookie:" not in request_bytes
    assert stream.closed is True


@pytest.mark.parametrize(
    ("stream", "expected"),
    [
        (
            FakeNetworkStream(peer_ip="1.1.1.1"),
            OutboundErrorCode.PEER_ADDRESS_MISMATCH,
        ),
        (
            FakeNetworkStream(tls_peer_ip="1.1.1.1"),
            OutboundErrorCode.PEER_ADDRESS_MISMATCH,
        ),
        (
            FakeNetworkStream(tls_error=ssl.SSLError("certificate hidden")),
            OutboundErrorCode.TLS_FAILED,
        ),
        (
            FakeNetworkStream(read_error=httpcore2.ReadTimeout("hidden")),
            OutboundErrorCode.REQUEST_TIMEOUT,
        ),
    ],
)
def test_pinned_transport_peer_tls_and_read_failures_are_stable(
    stream: FakeNetworkStream,
    expected: OutboundErrorCode,
) -> None:
    backend = FakeNetworkBackend(stream)
    error = _error_code(_pinned_client(backend))
    assert error.error.code is expected
    assert len(backend.calls) == 1
    assert stream.closed is True
    assert "hidden" not in str(error)


def test_pinned_transport_connect_timeout_is_not_retried() -> None:
    stream = FakeNetworkStream()
    backend = FakeNetworkBackend(
        stream,
        connect_error=httpcore2.ConnectTimeout("hidden"),
    )
    error = _error_code(_pinned_client(backend))
    assert error.error.code is OutboundErrorCode.CONNECT_TIMEOUT
    assert backend.calls == [(SAFE_IPV4, 443, 3.0)]


def test_cancellation_propagates_and_closes_the_network_stream() -> None:
    stream = FakeNetworkStream(read_error=asyncio.CancelledError())
    backend = FakeNetworkBackend(stream)
    with pytest.raises(asyncio.CancelledError):
        _fetch(_pinned_client(backend))
    assert stream.closed is True


def test_same_provider_concurrency_is_limited_to_one() -> None:
    async def scenario() -> tuple[int, int]:
        active = 0
        maximum = 0
        calls = 0
        first_started = asyncio.Event()
        release = asyncio.Event()

        def factory(plan: ConnectionPlan) -> httpx2.AsyncBaseTransport:
            async def handler(request: httpx2.Request) -> httpx2.Response:
                nonlocal active, maximum, calls
                calls += 1
                active += 1
                maximum = max(maximum, active)
                first_started.set()
                await release.wait()
                active -= 1
                return _response()

            return httpx2.MockTransport(handler)

        client = OutboundHttpClient(
            registry=_registry(),
            resolver=FakeResolver(),
            transport_factory=factory,
            clock=FakeClock(),
        )
        request = OutboundRequest("unit_test_0", "search", query="example")
        tasks = [asyncio.create_task(client.fetch_json(request)) for _ in range(2)]
        await first_started.wait()
        await asyncio.sleep(0)
        observed_calls = calls
        release.set()
        await asyncio.gather(*tasks)
        return observed_calls, maximum

    observed_calls, maximum = asyncio.run(scenario())
    assert observed_calls == 1
    assert maximum == 1


def test_global_concurrency_is_limited_to_four() -> None:
    async def scenario() -> tuple[int, int]:
        active = 0
        maximum = 0
        started = asyncio.Event()
        release = asyncio.Event()

        def factory(plan: ConnectionPlan) -> httpx2.AsyncBaseTransport:
            async def handler(request: httpx2.Request) -> httpx2.Response:
                nonlocal active, maximum
                active += 1
                maximum = max(maximum, active)
                if active == 4:
                    started.set()
                await release.wait()
                active -= 1
                return _response()

            return httpx2.MockTransport(handler)

        client = OutboundHttpClient(
            registry=_registry(providers=5),
            resolver=FakeResolver(),
            transport_factory=factory,
            clock=FakeClock(),
        )
        tasks = [
            asyncio.create_task(
                client.fetch_json(
                    OutboundRequest(f"unit_test_{index}", "search", query="example")
                )
            )
            for index in range(5)
        ]
        await started.wait()
        await asyncio.sleep(0)
        observed = active
        release.set()
        await asyncio.gather(*tasks)
        return observed, maximum

    observed, maximum = asyncio.run(scenario())
    assert observed == 4
    assert maximum == 4
