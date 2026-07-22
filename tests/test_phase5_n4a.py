from __future__ import annotations

import asyncio
import logging
import ssl
from collections.abc import AsyncIterator, Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import httpcore2
import httpx2
import pytest

from app.request_context import request_id_context
from app.source_adapters.contracts import (
    AssetCapabilities,
    AuthCapabilities,
    DiscoveryCapabilities,
    DownloadCapabilities,
    MetadataCapabilities,
    ProviderAdapterError,
    ProviderAssetAdapter,
    ProviderAuthAdapter,
    ProviderAuthMode,
    ProviderAuthState,
    ProviderAuthStatus,
    ProviderCapabilities,
    ProviderDiscoveryAdapter,
    ProviderDownloadAdapter,
    ProviderError,
    ProviderErrorCode,
    ProviderOperation,
    SourceAsset,
    SourceAssetChecksumAlgorithm,
    SourceAssetKind,
    SourceMetadataAdapter,
)
from app.source_adapters.registry import (
    BusinessParameter,
    CookiePolicy,
    EndpointOperation,
    EndpointRegistry,
    HttpMethod,
    JsonTopLevel,
    PRODUCTION_ENDPOINT_REGISTRY,
    ProviderEndpoint,
    RedirectPolicy,
    RequestEncoding,
    ResponseKind,
)
from app.services.outbound_http import (
    ConnectionPlan,
    OutboundErrorCode,
    OutboundHttpClient,
    OutboundHttpError,
    OutboundRequest,
    PinnedAsyncTransport,
)
from tests.fixture_provider import (
    FIXTURE_ASSET_HOST,
    FIXTURE_CAPABILITIES,
    FIXTURE_ENDPOINT,
    FIXTURE_ENDPOINT_REGISTRY,
    FIXTURE_METADATA_HOST,
    FIXTURE_PROVIDER_KEY,
    FixtureReferenceProvider,
)


SAFE_IP = "8.8.8.8"
FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "reference_provider"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURE_DIRECTORY / name).read_bytes()


def _body_for_path(path: str) -> bytes:
    if path == "/fixture/search":
        return _fixture_bytes("search.json")
    if path == "/fixture/records/fixture-record-1":
        return _fixture_bytes("detail.json")
    if path == "/fixture/records/fixture-record-1/assets":
        return _fixture_bytes("assets.json")
    raise AssertionError(f"unexpected synthetic fixture path: {path}")


class FakeResolver:
    def __init__(self, addresses: tuple[str, ...] = (SAFE_IP,)) -> None:
        self.addresses = addresses
        self.calls: list[tuple[str, int]] = []

    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        self.calls.append((hostname, port))
        return self.addresses


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def monotonic(self) -> float:
        return self.value


class StaticByteStream(httpx2.AsyncByteStream):
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self.body

    async def aclose(self) -> None:
        self.closed = True


def _json_response(body: bytes) -> httpx2.Response:
    return httpx2.Response(
        200,
        headers={"Content-Type": "application/json"},
        stream=StaticByteStream(body),
    )


class FixtureMockTransportFactory:
    def __init__(
        self,
        handler: Callable[[httpx2.Request], httpx2.Response] | None = None,
    ) -> None:
        self.handler = handler or self._fixture_response
        self.plans: list[ConnectionPlan] = []
        self.requests: list[httpx2.Request] = []

    @staticmethod
    def _fixture_response(request: httpx2.Request) -> httpx2.Response:
        return _json_response(_body_for_path(request.url.path))

    def __call__(self, plan: ConnectionPlan) -> httpx2.AsyncBaseTransport:
        self.plans.append(plan)

        async def handle(request: httpx2.Request) -> httpx2.Response:
            self.requests.append(request)
            return self.handler(request)

        return httpx2.MockTransport(handle)


def _client(
    factory: FixtureMockTransportFactory,
    *,
    resolver: FakeResolver | None = None,
    registry: EndpointRegistry = FIXTURE_ENDPOINT_REGISTRY,
) -> OutboundHttpClient:
    return OutboundHttpClient(
        registry=registry,
        resolver=resolver or FakeResolver(),
        transport_factory=factory,
        clock=FakeClock(),
    )


def test_capability_manifest_is_layered_frozen_and_test_only() -> None:
    provider = FixtureReferenceProvider(
        _client(FixtureMockTransportFactory())
    )

    assert any(p.provider_key == "javdb_metadata" for p in PRODUCTION_ENDPOINT_REGISTRY.providers)
    assert FIXTURE_ENDPOINT_REGISTRY.providers == (FIXTURE_ENDPOINT,)
    assert FIXTURE_CAPABILITIES.operations == (
        ProviderOperation.SEARCH,
        ProviderOperation.DETAIL,
        ProviderOperation.ASSET_LIST,
    )
    assert FIXTURE_CAPABILITIES.auth_modes == (ProviderAuthMode.NONE,)
    assert isinstance(provider, SourceMetadataAdapter)
    assert isinstance(provider, ProviderAssetAdapter)
    assert not isinstance(provider, ProviderAuthAdapter)
    assert not isinstance(provider, ProviderDiscoveryAdapter)
    assert not isinstance(provider, ProviderDownloadAdapter)
    with pytest.raises(FrozenInstanceError):
        FIXTURE_CAPABILITIES.content_scope = "changed"  # type: ignore[misc]

    with pytest.raises(ProviderAdapterError) as exc_info:
        FIXTURE_CAPABILITIES.require(ProviderOperation.DISCOVER)
    assert exc_info.value.error.code is ProviderErrorCode.CAPABILITY_NOT_SUPPORTED
    assert exc_info.value.error.operation is ProviderOperation.DISCOVER
    assert str(exc_info.value) == "capability_not_supported"


def test_manifest_rejects_cross_layer_and_endpoint_mismatches() -> None:
    with pytest.raises(ValueError, match="another layer"):
        MetadataCapabilities((ProviderOperation.ASSET_LIST,))
    with pytest.raises(ValueError, match="credentialed"):
        AuthCapabilities(
            (ProviderAuthMode.NONE,),
            (ProviderOperation.AUTH_TEST,),
        )

    search_only = ProviderCapabilities(
        provider_key="mismatch_fixture",
        display_name="Mismatch Fixture",
        content_scope="synthetic mismatch only",
        metadata=MetadataCapabilities((ProviderOperation.SEARCH,)),
    )
    with pytest.raises(ValueError, match="exactly match"):
        ProviderEndpoint(
            provider_key="mismatch_fixture",
            hostname="metadata.mismatch.invalid",
            capabilities=search_only,
            operations=(
                EndpointOperation(
                    ProviderOperation.DETAIL,
                    "/fixture/detail/{external_id}",
                    JsonTopLevel.OBJECT,
                    path_parameter=BusinessParameter.EXTERNAL_ID,
                    required_parameters=(BusinessParameter.EXTERNAL_ID,),
                ),
            ),
        )


def test_auth_status_and_provider_errors_are_typed_and_redacted() -> None:
    status = ProviderAuthStatus(
        provider_key="auth_fixture",
        state=ProviderAuthState.EXPIRED,
        mode=ProviderAuthMode.API_TOKEN,
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert status.state is ProviderAuthState.EXPIRED
    with pytest.raises(ValueError, match="timezone-aware"):
        ProviderAuthStatus(
            provider_key="auth_fixture",
            state=ProviderAuthState.UNKNOWN,
            mode=ProviderAuthMode.API_TOKEN,
            checked_at=datetime(2026, 1, 1),
        )

    error = ProviderAdapterError(
        ProviderError(
            ProviderErrorCode.AUTH_EXPIRED,
            "auth_fixture",
            ProviderOperation.AUTH_TEST,
            ProviderAuthState.EXPIRED,
        )
    )
    assert str(error) == "auth_expired"
    assert "auth_fixture" not in str(error)


def test_source_asset_is_typed_immutable_and_never_accepts_a_url_as_id() -> None:
    asset = SourceAsset(
        provider_key=FIXTURE_PROVIDER_KEY,
        external_id="fixture-record-1",
        asset_id="fixture-cover-1",
        kind=SourceAssetKind.COVER,
        mime_type="image/png",
        size_bytes=68,
        checksum_algorithm=SourceAssetChecksumAlgorithm.SHA256,
        checksum_value="0" * 64,
        downloadable=False,
    )
    assert asset.kind is SourceAssetKind.COVER
    with pytest.raises(FrozenInstanceError):
        asset.asset_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="opaque"):
        SourceAsset(
            provider_key=FIXTURE_PROVIDER_KEY,
            external_id="fixture-record-1",
            asset_id="https://response-controlled.invalid/asset",
            kind=SourceAssetKind.COVER,
        )
    with pytest.raises(ValueError, match="length"):
        SourceAsset(
            provider_key=FIXTURE_PROVIDER_KEY,
            external_id="fixture-record-1",
            asset_id="fixture-cover-2",
            kind=SourceAssetKind.COVER,
            checksum_algorithm=SourceAssetChecksumAlgorithm.SHA256,
            checksum_value="0" * 63,
        )


def test_endpoint_operation_policies_are_typed_and_code_owned() -> None:
    search = FIXTURE_ENDPOINT.operation(ProviderOperation.SEARCH)
    assets = FIXTURE_ENDPOINT.operation(ProviderOperation.ASSET_LIST)
    assert search is not None and assets is not None
    assert search.method is HttpMethod.GET
    assert search.request_encoding is RequestEncoding.NONE
    assert search.auth_requirement is ProviderAuthMode.NONE
    assert search.cookie_policy is CookiePolicy.NONE
    assert search.response_kind is ResponseKind.JSON
    assert search.redirect_policy is RedirectPolicy.DENY
    assert search.fixed_headers == (("X-Fixture-Contract", "n4a"),)
    assert assets.allowed_asset_hosts == (FIXTURE_ASSET_HOST,)
    exact_json = EndpointOperation(
        ProviderOperation.SEARCH,
        "/fixture/problem",
        JsonTopLevel.OBJECT,
        allowed_content_types=("application/problem+json",),
    )
    assert exact_json.accepts_content_type("application/problem+json")
    assert not exact_json.accepts_content_type("application/other+json")

    with pytest.raises(ValueError, match="GET operations"):
        EndpointOperation(
            ProviderOperation.SEARCH,
            "/fixture/search",
            JsonTopLevel.OBJECT,
            body_parameters=((BusinessParameter.QUERY, "query"),),
            method=HttpMethod.GET,
            request_encoding=RequestEncoding.JSON,
        )
    with pytest.raises(ValueError, match="fixed header"):
        EndpointOperation(
            ProviderOperation.SEARCH,
            "/fixture/search",
            JsonTopLevel.OBJECT,
            fixed_headers=(("Authorization", "forbidden"),),
        )
    with pytest.raises(ValueError, match="hostname"):
        EndpointOperation(
            ProviderOperation.ASSET_LIST,
            "/fixture/assets/{external_id}",
            JsonTopLevel.OBJECT,
            path_parameter=BusinessParameter.EXTERNAL_ID,
            allowed_asset_hosts=("*.fixture.invalid",),
        )


def test_fixture_provider_search_detail_and_asset_list_use_static_mock_data() -> None:
    resolver = FakeResolver()
    factory = FixtureMockTransportFactory()
    provider = FixtureReferenceProvider(
        _client(factory, resolver=resolver)
    )

    page = asyncio.run(provider.search("synthetic query", page=1, page_size=10))
    detail = asyncio.run(provider.fetch_detail("fixture-record-1"))
    assets = asyncio.run(provider.list_assets("fixture-record-1"))

    assert page.total == 1
    assert page.results[0].title == "Synthetic Fixture Record"
    assert detail.stable_detail_id == "fixture-detail-1"
    assert detail.available_fields == ("title", "summary")
    assert len(assets) == 1
    assert assets[0].asset_id == "fixture-cover-1"
    assert assets[0].kind is SourceAssetKind.COVER
    assert assets[0].downloadable is False
    assert resolver.calls == [(FIXTURE_METADATA_HOST, 443)] * 3
    assert [request.method for request in factory.requests] == ["GET"] * 3
    assert factory.requests[0].headers["X-Fixture-Contract"] == "n4a"


def test_response_cannot_expand_operations_or_hosts() -> None:
    resolver = FakeResolver()
    factory = FixtureMockTransportFactory()
    provider = FixtureReferenceProvider(
        _client(factory, resolver=resolver)
    )

    asyncio.run(provider.search("response expansion", page=1, page_size=10))
    asyncio.run(provider.fetch_detail("fixture-record-1"))
    assets = asyncio.run(provider.list_assets("fixture-record-1"))

    assert not provider.capabilities.supports(ProviderOperation.DISCOVER)
    assert not provider.capabilities.supports(ProviderOperation.ASSET_RESOLVE)
    assert not provider.capabilities.supports(ProviderOperation.DOWNLOAD)
    assert FIXTURE_ENDPOINT.operation("discover") is None
    assert FIXTURE_ENDPOINT.operation("asset_resolve") is None
    asset_operation = FIXTURE_ENDPOINT.operation(ProviderOperation.ASSET_LIST)
    assert asset_operation is not None
    assert asset_operation.allowed_asset_hosts == (FIXTURE_ASSET_HOST,)
    assert all(request.url.host == FIXTURE_METADATA_HOST for request in factory.requests)
    assert all(call == (FIXTURE_METADATA_HOST, 443) for call in resolver.calls)
    assert assets[0].downloadable is False


def test_response_downloadable_flag_cannot_add_download_capability() -> None:
    expanded = _fixture_bytes("assets.json").replace(
        b'"downloadable": false',
        b'"downloadable": true',
    )

    def expanded_response(_: httpx2.Request) -> httpx2.Response:
        return _json_response(expanded)

    provider = FixtureReferenceProvider(
        _client(FixtureMockTransportFactory(expanded_response))
    )
    with pytest.raises(ProviderAdapterError) as exc_info:
        asyncio.run(provider.list_assets("fixture-record-1"))
    assert exc_info.value.error.code is ProviderErrorCode.INVALID_PROVIDER_PAYLOAD
    assert not provider.capabilities.supports(ProviderOperation.DOWNLOAD)


def test_fixture_provider_logs_exclude_query_payload_hosts_and_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    query_marker = "private-query-marker"
    factory = FixtureMockTransportFactory()
    provider = FixtureReferenceProvider(_client(factory))
    token = request_id_context.set("12345678123456781234567812345678")
    try:
        with caplog.at_level(
            logging.INFO,
            logger="uvicorn.error.nsfwtrack.outbound",
        ):
            asyncio.run(provider.search(query_marker, page=1, page_size=10))
    finally:
        request_id_context.reset(token)

    text = caplog.text
    assert f"provider={FIXTURE_PROVIDER_KEY}" in text
    assert "operation=search" in text
    assert "outcome=success" in text
    assert query_marker not in text
    assert "fixture-payload-must-not-be-logged" not in text
    assert "response-controlled.invalid" not in text
    assert FIXTURE_METADATA_HOST not in text
    assert SAFE_IP not in text
    assert "https://" not in text


def test_fixture_provider_maps_invalid_payload_to_a_stable_error() -> None:
    marker = "raw-provider-payload-must-not-escape"

    def invalid_response(_: httpx2.Request) -> httpx2.Response:
        return _json_response(
            ('{"assets":[{"asset_id":"' + marker + '"}]}').encode("ascii")
        )

    provider = FixtureReferenceProvider(
        _client(FixtureMockTransportFactory(invalid_response))
    )
    with pytest.raises(ProviderAdapterError) as exc_info:
        asyncio.run(provider.list_assets("fixture-record-1"))
    assert exc_info.value.error.code is ProviderErrorCode.INVALID_PROVIDER_PAYLOAD
    assert str(exc_info.value) == "invalid_provider_payload"
    assert marker not in str(exc_info.value)


@pytest.mark.parametrize(
    ("encoding", "expected_content_type", "expected_body"),
    [
        (
            RequestEncoding.JSON,
            "application/json",
            b'{"page":2,"query":"typed-value"}',
        ),
        (
            RequestEncoding.FORM,
            "application/x-www-form-urlencoded",
            b"query=typed-value&page=2",
        ),
    ],
)
def test_typed_post_body_is_built_only_from_business_parameters(
    encoding: RequestEncoding,
    expected_content_type: str,
    expected_body: bytes,
) -> None:
    capabilities = ProviderCapabilities(
        provider_key="typed_fixture",
        display_name="Typed Fixture",
        content_scope="synthetic typed request only",
        metadata=MetadataCapabilities((ProviderOperation.SEARCH,)),
    )
    operation = EndpointOperation(
        ProviderOperation.SEARCH,
        "/fixture/typed-search",
        JsonTopLevel.OBJECT,
        body_parameters=(
            (BusinessParameter.QUERY, "query"),
            (BusinessParameter.PAGE, "page"),
        ),
        required_parameters=(BusinessParameter.QUERY,),
        method=HttpMethod.POST,
        request_encoding=encoding,
    )
    registry = EndpointRegistry(
        (
            ProviderEndpoint(
                "typed_fixture",
                "typed.fixture.invalid",
                capabilities,
                (operation,),
            ),
        )
    )
    factory = FixtureMockTransportFactory(
        lambda _: _json_response(b'{"ok":true}')
    )
    client = _client(factory, registry=registry)

    asyncio.run(
        client.fetch_json(
            OutboundRequest(
                "typed_fixture",
                "search",
                query="typed-value",
                page=2,
            )
        )
    )

    request = factory.requests[0]
    assert request.method == "POST"
    assert request.headers["Content-Type"] == expected_content_type
    assert request.content == expected_body


@pytest.mark.parametrize(
    "policy",
    ["auth", "cookie", "response", "redirect"],
)
def test_unimplemented_operation_policies_fail_before_dns(policy: str) -> None:
    auth_modes = (ProviderAuthMode.NONE,)
    if policy == "auth":
        auth_modes = (ProviderAuthMode.NONE, ProviderAuthMode.API_TOKEN)
    elif policy == "cookie":
        auth_modes = (ProviderAuthMode.NONE, ProviderAuthMode.SESSION_COOKIE)
    capabilities = ProviderCapabilities(
        provider_key="policy_fixture",
        display_name="Policy Fixture",
        content_scope="synthetic unsupported policy only",
        metadata=MetadataCapabilities((ProviderOperation.SEARCH,)),
        auth=AuthCapabilities(auth_modes),
    )
    options: dict[str, object] = {}
    expected = OutboundErrorCode.OPERATION_POLICY_NOT_SUPPORTED
    if policy == "auth":
        options["auth_requirement"] = ProviderAuthMode.API_TOKEN
        expected = OutboundErrorCode.AUTH_NOT_CONFIGURED
    elif policy == "cookie":
        options["cookie_policy"] = CookiePolicy.PROVIDER_SESSION
        expected = OutboundErrorCode.AUTH_NOT_CONFIGURED
    elif policy == "response":
        options["response_kind"] = ResponseKind.HTML
        options["expected_top_level"] = None
        options["allowed_content_types"] = ("text/html",)
    else:
        options["redirect_policy"] = RedirectPolicy.EXACT_ALLOWLIST
        options["redirect_hosts"] = ("redirect.fixture.invalid",)
        options["max_redirects"] = 1
    expected_top_level = options.pop("expected_top_level", JsonTopLevel.OBJECT)
    operation = EndpointOperation(
        ProviderOperation.SEARCH,
        "/fixture/policy",
        expected_top_level,  # type: ignore[arg-type]
        **options,  # type: ignore[arg-type]
    )
    registry = EndpointRegistry(
        (
            ProviderEndpoint(
                "policy_fixture",
                "policy.fixture.invalid",
                capabilities,
                (operation,),
            ),
        )
    )
    resolver = FakeResolver()
    client = _client(
        FixtureMockTransportFactory(),
        resolver=resolver,
        registry=registry,
    )

    with pytest.raises(OutboundHttpError) as exc_info:
        asyncio.run(
            client.fetch_json(
                OutboundRequest("policy_fixture", "search")
            )
        )
    assert exc_info.value.error.code is expected
    assert resolver.calls == []


@pytest.mark.parametrize(
    "operation",
    [
        ProviderOperation.AUTH_LOGIN,
        ProviderOperation.DISCOVER,
        ProviderOperation.ASSET_RESOLVE,
        ProviderOperation.DOWNLOAD,
    ],
)
def test_unimplemented_capability_operations_fail_before_dns(
    operation: ProviderOperation,
) -> None:
    provider_key = f"unsupported_{operation.value}"
    common = {
        "provider_key": provider_key,
        "display_name": "Unsupported Fixture",
        "content_scope": "synthetic unsupported operation only",
    }
    if operation is ProviderOperation.AUTH_LOGIN:
        capabilities = ProviderCapabilities(
            **common,
            auth=AuthCapabilities(
                (ProviderAuthMode.NONE, ProviderAuthMode.API_TOKEN),
                (operation,),
            ),
        )
    elif operation is ProviderOperation.DISCOVER:
        capabilities = ProviderCapabilities(
            **common,
            discovery=DiscoveryCapabilities((operation,)),
        )
    elif operation is ProviderOperation.ASSET_RESOLVE:
        capabilities = ProviderCapabilities(
            **common,
            assets=AssetCapabilities(
                (operation,),
                (SourceAssetKind.COVER,),
            ),
        )
    else:
        capabilities = ProviderCapabilities(
            **common,
            downloads=DownloadCapabilities(
                (operation,),
                (SourceAssetKind.MEDIA,),
            ),
        )
    endpoint = ProviderEndpoint(
        provider_key=provider_key,
        hostname=f"{operation.value.replace('_', '-')}.fixture.invalid",
        capabilities=capabilities,
        operations=(
            EndpointOperation(
                operation,
                "/fixture/unsupported",
                JsonTopLevel.OBJECT,
            ),
        ),
    )
    resolver = FakeResolver()
    factory = FixtureMockTransportFactory()
    client = _client(
        factory,
        resolver=resolver,
        registry=EndpointRegistry((endpoint,)),
    )

    with pytest.raises(OutboundHttpError) as exc_info:
        asyncio.run(
            client.fetch_json(OutboundRequest(provider_key, operation.value))
        )
    assert (
        exc_info.value.error.code
        is OutboundErrorCode.OPERATION_POLICY_NOT_SUPPORTED
    )
    assert resolver.calls == []
    assert factory.plans == []


class FakeSSLObject:
    def selected_alpn_protocol(self) -> str:
        return "http/1.1"


class FixtureNetworkStream(httpcore2.AsyncNetworkStream):
    def __init__(self) -> None:
        self.tls_started = False
        self.closed = False
        self.sni: list[str | None] = []
        self.writes: list[bytes] = []
        self.response = b""

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if not self.response:
            return b""
        chunk, self.response = self.response[:max_bytes], self.response[max_bytes:]
        return chunk

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.writes.append(buffer)
        request = b"".join(self.writes)
        if self.response or b"\r\n\r\n" not in request:
            return
        request_target = request.split(b" ", 2)[1].decode("ascii")
        path = request_target.split("?", 1)[0]
        body = _body_for_path(path)
        self.response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + body
        )

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        assert ssl_context.check_hostname is True
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        self.sni.append(server_hostname)
        self.tls_started = True
        return self

    def get_extra_info(self, info: str) -> object:
        if info == "server_addr":
            return (SAFE_IP, 443)
        if info == "ssl_object" and self.tls_started:
            return FakeSSLObject()
        return None


class FakeNetworkBackend(httpcore2.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, float | None]] = []
        self.streams: list[FixtureNetworkStream] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object = None,
    ) -> httpcore2.AsyncNetworkStream:
        self.calls.append((host, port, timeout))
        stream = FixtureNetworkStream()
        self.streams.append(stream)
        return stream

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: object = None,
    ) -> httpcore2.AsyncNetworkStream:
        raise AssertionError("unix sockets are forbidden")

    async def sleep(self, seconds: float) -> None:
        raise AssertionError("retries are forbidden")


def test_fixture_provider_uses_only_the_fake_pinned_network_backend() -> None:
    resolver = FakeResolver()
    backend = FakeNetworkBackend()
    client = OutboundHttpClient(
        registry=FIXTURE_ENDPOINT_REGISTRY,
        resolver=resolver,
        clock=FakeClock(),
        transport_factory=lambda plan: PinnedAsyncTransport(
            plan,
            network_backend=backend,
        ),
    )
    provider = FixtureReferenceProvider(client)

    page = asyncio.run(provider.search("pinned fixture", page=1, page_size=10))

    assert page.total == 1
    assert resolver.calls == [(FIXTURE_METADATA_HOST, 443)]
    assert backend.calls == [(SAFE_IP, 443, 3.0)]
    assert len(backend.streams) == 1
    stream = backend.streams[0]
    assert stream.sni == [FIXTURE_METADATA_HOST]
    request_bytes = b"".join(stream.writes)
    assert b"Host: metadata.fixture.invalid\r\n" in request_bytes
    assert b"Authorization:" not in request_bytes
    assert b"Cookie:" not in request_bytes
    assert stream.closed is True
