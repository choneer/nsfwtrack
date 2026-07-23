"""Phase 7 corrective: runtime state activates only controlled catalogs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx2
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Item, ItemSource
from app.providers.javdb.session import SessionCookieError
from app.provider_apply.service import sign_provider_apply_plan
from app.provider_apply.transaction import apply_provider_apply_token
from app.providers.production_catalog import (
    build_production_endpoints,
    build_production_search_packages,
)
from app.provider_runtime.catalog import (
    ProviderRuntimeCatalogError,
    RuntimeProviderPackage,
    build_runtime_catalog,
    build_runtime_provider,
    build_runtime_search_service,
    run_runtime_health_check,
)
from app.provider_runtime.service import ProviderRuntimeRegistry, ProviderRuntimeView
from app.services.outbound_http import OutboundHttpClient
from app.source_adapters.registry import EndpointRegistry, ProviderEndpoint
from app.source_search.contracts import VideoDetailRequest, VideoSearchRequest


class _PublicResolver:
    async def resolve(self, _hostname: str, _port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)


class _ChunkStream(httpx2.AsyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...], error: BaseException | None = None) -> None:
        self._chunks = chunks
        self._error = error

    async def __aiter__(self):
        if self._error is not None:
            raise self._error
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


def _response(request: httpx2.Request, payload: dict[str, object]) -> httpx2.Response:
    return httpx2.Response(
        200,
        headers={"Content-Type": "application/json"},
        stream=_ChunkStream((json.dumps(payload).encode("utf-8"),)),
    )


def _json_response(request: httpx2.Request) -> httpx2.Response:
    url = str(request.url)
    if request.url.host == "api.zuidapi.com":
        if "ac=list" in url:
            payload = {
                "code": 1,
                "list": [{"vod_id": "runtime-001", "vod_name": "Runtime Result"}],
                "total": 1,
            }
        else:
            payload = {
                "code": 1,
                "list": [{"vod_id": "runtime-001", "vod_name": "Runtime Detail"}],
            }
        return _response(request, payload)
    if request.url.host == "api.mangacopy.com":
        return _response(request, {"results": {"list": []}})
    raise AssertionError(f"unexpected fixed host: {request.url.host}")


def _client_factory(
    handler: Callable[[httpx2.Request], httpx2.Response] = _json_response,
) -> Callable[[ProviderEndpoint, str], OutboundHttpClient]:
    def factory(endpoint: ProviderEndpoint, egress_profile: str) -> OutboundHttpClient:
        assert egress_profile == "direct"
        async def dispatch(request: httpx2.Request) -> httpx2.Response:
            return handler(request)

        return OutboundHttpClient(
            registry=EndpointRegistry((endpoint,)),
            resolver=_PublicResolver(),
            transport_factory=lambda _plan: httpx2.MockTransport(dispatch),
        )

    return factory


def _runtime_factory(
    handler: Callable[[httpx2.Request], httpx2.Response] = _json_response,
) -> Callable[[ProviderRuntimeView], RuntimeProviderPackage]:
    client_factory = _client_factory(handler)
    return lambda view: build_runtime_provider(view, client_factory=client_factory)


@pytest.fixture
def isolated_engine() -> Engine:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _configure_and_enable(
    db: Session,
    provider_key: str = "zuidapi_vod",
) -> ProviderRuntimeView:
    registry = ProviderRuntimeRegistry(db)
    registry.sync_known_states()
    initial = registry.get(provider_key)
    configured = registry.save_configuration(
        provider_key,
        egress_profile="direct",
        expected_version=initial.optimistic_version,
    )
    return registry.set_enabled(
        provider_key,
        enabled=True,
        expected_version=configured.optimistic_version,
    )


def _activate(
    db: Session,
    provider_key: str = "zuidapi_vod",
    *,
    factory: Callable[[ProviderRuntimeView], RuntimeProviderPackage] | None = None,
) -> ProviderRuntimeView:
    enabled = _configure_and_enable(db, provider_key)
    return asyncio.run(
        run_runtime_health_check(
            db,
            provider_key,
            expected_version=enabled.optimistic_version,
            package_factory=factory or _runtime_factory(),
        )
    )


def test_enabled_runtime_enters_catalog_and_search_detail_preview_confirm(
    isolated_engine: Engine,
) -> None:
    with Session(isolated_engine) as db:
        ready = _activate(db)
        db.commit()
        assert ready.in_production_catalog is True
        catalog = build_runtime_catalog(db, package_factory=_runtime_factory())
        assert tuple(package.provider_key for package in catalog.packages) == (
            "zuidapi_vod",
        )
        assert tuple(
            endpoint.provider_key for endpoint in build_production_endpoints(db)
        ) == ("zuidapi_vod",)
        assert tuple(
            package.provider_key for package in build_production_search_packages(db)
        ) == ("zuidapi_vod",)

        service = build_runtime_search_service(db, package_factory=_runtime_factory())
        search = asyncio.run(
            service.search(
                VideoSearchRequest("zuidapi_vod", "runtime", page=1, page_size=10)
            )
        )
        assert search.page.items[0].external_id == "runtime-001"
        detail = asyncio.run(
            service.detail(VideoDetailRequest("zuidapi_vod", "runtime-001"))
        )
        assert detail.detail.title == "Runtime Detail"

        from app.provider_apply.service import build_provider_apply_plan

        plan = build_provider_apply_plan(db, detail)
        assert plan.has_writes is True
        token = sign_provider_apply_plan(
            plan,
            secret=b"r" * 32,
            context="runtime-preview-confirm",
            now=datetime.now(UTC),
        )
        db.commit()
        verify = sessionmaker(bind=isolated_engine, future=True)
        result = apply_provider_apply_token(
            db,
            token,
            secret=b"r" * 32,
            context="runtime-preview-confirm",
            now=datetime.now(UTC),
            verification_session_factory=verify,
        )
        assert result.item_id > 0
        assert db.scalar(select(Item).where(Item.id == result.item_id)) is not None
        source = db.scalar(select(ItemSource).where(ItemSource.item_id == result.item_id))
        assert source is not None
        assert source.provider_key == "zuidapi_vod"
        assert source.external_id == "runtime-001"


def test_disabled_invalid_missing_session_and_fixture_are_excluded(
    isolated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(isolated_engine) as db:
        registry = ProviderRuntimeRegistry(db)
        registry.sync_known_states()
        assert build_runtime_catalog(db).packages == ()

        enabled = _configure_and_enable(db)
        blocked = registry.complete_health_check(
            "zuidapi_vod",
            expected_version=enabled.optimistic_version,
            success=True,
        )
        assert blocked.in_production_catalog is True
        disabled = registry.set_enabled(
            "zuidapi_vod",
            enabled=False,
            expected_version=blocked.optimistic_version,
        )
        assert disabled.in_production_catalog is False
        assert build_runtime_catalog(db).packages == ()

        monkeypatch.setattr(
            "app.provider_runtime.service.load_javdb_session_cookie",
            lambda: (_ for _ in ()).throw(SessionCookieError("session unavailable")),
        )
        assert registry.get("javdb_metadata").session_status == "missing"
        assert registry.get("jiuse_vod").in_production_catalog is False
        assert registry.get("copymanga").configuration_status == "not_configured"
        assert build_runtime_catalog(db).packages == ()


def test_single_runtime_initialization_failure_isolated_from_ready_neighbor(
    isolated_engine: Engine,
) -> None:
    with Session(isolated_engine) as db:
        _activate(db, "zuidapi_vod")
        comic_enabled = _configure_and_enable(db, "copymanga")
        ProviderRuntimeRegistry(db).complete_health_check(
            "copymanga",
            expected_version=comic_enabled.optimistic_version,
            success=True,
        )

        def factory(view: ProviderRuntimeView) -> RuntimeProviderPackage:
            if view.provider_key == "copymanga":
                raise ProviderRuntimeCatalogError("runtime_initialization_failed")
            return _runtime_factory()(view)

        catalog = build_runtime_catalog(db, package_factory=factory)
        assert tuple(package.provider_key for package in catalog.packages) == (
            "zuidapi_vod",
        )
        assert "copymanga" in catalog.excluded_provider_keys


def test_health_timeout_is_stable_redacted_and_does_not_activate_catalog(
    isolated_engine: Engine,
) -> None:
    def timeout(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=_ChunkStream((), httpx2.ReadTimeout("private-token-marker")),
        )

    with Session(isolated_engine) as db:
        enabled = _configure_and_enable(db)
        result = asyncio.run(
            run_runtime_health_check(
                db,
                "zuidapi_vod",
                expected_version=enabled.optimistic_version,
                package_factory=_runtime_factory(timeout),
            )
        )
        assert result.runtime_status == "error"
        assert result.last_error_code == "runtime_timeout"
        assert "private-token-marker" not in repr(result)
        assert build_runtime_catalog(db).packages == ()


def test_runtime_state_persists_across_new_session_and_disable_removes_catalog(
    tmp_path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'runtime.sqlite3'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            _activate(db)
            db.commit()
        with Session(engine) as db:
            persisted = ProviderRuntimeRegistry(db).get("zuidapi_vod")
            assert persisted.runtime_status == "ready"
            assert persisted.in_production_catalog is True
            assert tuple(
                package.provider_key
                for package in build_runtime_catalog(db, package_factory=_runtime_factory()).packages
            ) == ("zuidapi_vod",)
            disabled = ProviderRuntimeRegistry(db).set_enabled(
                "zuidapi_vod",
                enabled=False,
                expected_version=persisted.optimistic_version,
            )
            assert disabled.in_production_catalog is False
            assert build_runtime_catalog(db, package_factory=_runtime_factory()).packages == ()
    finally:
        engine.dispose()
