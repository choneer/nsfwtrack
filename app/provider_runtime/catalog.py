"""Runtime-backed, fail-closed production Provider catalog.

This module is the only bridge from persisted Provider Runtime state to an
active Search/Detail package.  Catalog construction never performs network
I/O.  Network is possible only when a logged-in user submits Search, Detail,
or the explicit Provider health-check POST, and only through the shared
pinned outbound client with code-owned endpoints.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.providers.copymanga.approval import COPYMANGA_ENDPOINT
from app.providers.copymanga.package_build import build_copymanga_production_package
from app.providers.javdb.package_build import build_javdb_production_package
from app.providers.javdb.production import JAVDB_PRODUCTION_ENDPOINT
from app.providers.javdb.session import SessionCookieError, load_javdb_session_cookie
from app.providers.zuidapi.approval import ZUIDAPI_ENDPOINT
from app.providers.zuidapi.package_build import build_zuidapi_production_package
from app.provider_runtime.service import ProviderRuntimeRegistry, ProviderRuntimeView
from app.services.outbound_http import (
    FrozenJsonObject,
    OutboundErrorCode,
    OutboundHttpClient,
    OutboundHttpError,
    OutboundRequest,
)
from app.source_adapters.contracts import ProviderOperation
from app.source_adapters.package import ProviderPackage
from app.source_adapters.registry import EndpointRegistry, ProviderEndpoint
from app.source_search.contracts import ProviderSearchServiceError, VideoSearchRequest
from app.source_search.service import ProviderSearchService, _utc_now


class ProviderRuntimeCatalogError(RuntimeError):
    """Stable, secret-free classification for runtime package/probe failures."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class RuntimeProviderPackage:
    provider_key: str
    package: ProviderPackage
    health_probe: Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RuntimeCatalogSnapshot:
    packages: tuple[ProviderPackage, ...]
    excluded_provider_keys: tuple[str, ...]


ControlledClientFactory = Callable[[ProviderEndpoint, str], OutboundHttpClient]
RuntimePackageFactory = Callable[[ProviderRuntimeView], RuntimeProviderPackage]


def build_controlled_client(
    endpoint: ProviderEndpoint,
    egress_profile: str,
) -> OutboundHttpClient:
    """Create a per-Provider pinned client without ambient proxy authority.

    ``default`` and ``direct`` are both direct, TLS-pinned egress.  A pool
    proxy is intentionally fail-closed here: the existing pool diagnostics are
    not an authorization to tunnel Provider credentials through an unreviewed
    proxy transport.
    """

    if egress_profile not in {"default", "direct"}:
        raise ProviderRuntimeCatalogError("egress_profile_unavailable")
    return OutboundHttpClient(registry=EndpointRegistry((endpoint,)))


def _thaw_json(value: object) -> Any:
    if isinstance(value, FrozenJsonObject):
        return {key: _thaw_json(item) for key, item in value.entries}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


class _RuntimeJsonFetcher:
    def __init__(self, client: OutboundHttpClient, provider_key: str) -> None:
        self._client = client
        self._provider_key = provider_key
        self.last_outbound_error_code: str | None = None

    async def _fetch(self, request: OutboundRequest) -> dict[str, Any]:
        try:
            response = await self._client.fetch_json(request)
        except OutboundHttpError as error:
            self.last_outbound_error_code = error.error.code.value
            raise
        payload = _thaw_json(response.data)
        if not isinstance(payload, dict):
            raise ValueError("approved JSON operation returned a non-object")
        return payload


class _ZuidapiRuntimeFetcher(_RuntimeJsonFetcher):
    async def get_json(
        self,
        path: str,
        *,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        values = query or {}
        if path != "/api.php/provide/vod":
            raise ValueError("unapproved ZuidAPI path")
        if set(values) == {"ac", "wd", "pg", "limit"} and values.get("ac") == "list":
            return await self._fetch(
                OutboundRequest(
                    self._provider_key,
                    ProviderOperation.SEARCH.value,
                    query=values["wd"],
                    page=int(values["pg"]),
                    page_size=int(values["limit"]),
                )
            )
        if set(values) == {"ac", "ids"} and values.get("ac") == "detail":
            return await self._fetch(
                OutboundRequest(
                    self._provider_key,
                    ProviderOperation.DETAIL.value,
                    external_id=values["ids"],
                )
            )
        raise ValueError("unapproved ZuidAPI query")


class _CopymangaRuntimeFetcher(_RuntimeJsonFetcher):
    async def get_json(
        self,
        path: str,
        *,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        values = query or {}
        if path == "/api/v3/search/comic":
            if set(values) != {"q", "offset", "limit"}:
                raise ValueError("unapproved CopyManga query")
            return await self._fetch(
                OutboundRequest(
                    self._provider_key,
                    ProviderOperation.SEARCH.value,
                    query=values["q"],
                    offset=int(values["offset"]),
                    page_size=int(values["limit"]),
                )
            )
        detail_prefix = "/api/v3/comic2/"
        assets_prefix = "/api/v3/comic/"
        assets_suffix = "/group/default/chapters"
        if path.startswith(detail_prefix) and not values:
            external_id = path.removeprefix(detail_prefix)
            if not external_id or "/" in external_id:
                raise ValueError("unapproved CopyManga detail identity")
            return await self._fetch(
                OutboundRequest(
                    self._provider_key,
                    ProviderOperation.DETAIL.value,
                    external_id=external_id,
                )
            )
        if path.startswith(assets_prefix) and path.endswith(assets_suffix) and not values:
            external_id = path[len(assets_prefix) : -len(assets_suffix)]
            if not external_id or "/" in external_id:
                raise ValueError("unapproved CopyManga asset identity")
            return await self._fetch(
                OutboundRequest(
                    self._provider_key,
                    ProviderOperation.ASSET_LIST.value,
                    external_id=external_id,
                )
            )
        raise ValueError("unapproved CopyManga path")


class _JavdbRuntimeFetcher:
    def __init__(self, client: OutboundHttpClient, cookie: str) -> None:
        self._client = client
        self._cookie = cookie
        self.last_outbound_error_code: str | None = None

    async def get_html(
        self,
        path: str,
        *,
        query: dict[str, str] | None = None,
    ) -> str:
        values = query or {}
        if path == "/search" and set(values) == {"q"}:
            request = OutboundRequest(
                "javdb_metadata",
                ProviderOperation.SEARCH.value,
                query=values["q"],
            )
        elif path.startswith("/v/") and not values:
            external_id = path.removeprefix("/v/")
            if not external_id or "/" in external_id:
                raise ValueError("unapproved JavDB detail identity")
            # DETAIL and ASSET_LIST share the same approved fixed endpoint.
            request = OutboundRequest(
                "javdb_metadata",
                ProviderOperation.DETAIL.value,
                external_id=external_id,
            )
        else:
            raise ValueError("unapproved JavDB path")
        try:
            response = await self._client.fetch_html(
                request,
                session_cookie=self._cookie,
            )
        except OutboundHttpError as error:
            self.last_outbound_error_code = error.error.code.value
            raise
        return response.text


def _probe_error_code(fetcher: object) -> str:
    outbound_code = getattr(fetcher, "last_outbound_error_code", None)
    if outbound_code in {
        OutboundErrorCode.CONNECT_TIMEOUT.value,
        OutboundErrorCode.REQUEST_TIMEOUT.value,
    }:
        return "runtime_timeout"
    if outbound_code in {
        OutboundErrorCode.UNAUTHORIZED.value,
        OutboundErrorCode.FORBIDDEN.value,
    }:
        return "runtime_session_rejected"
    if outbound_code is not None:
        return "runtime_request_failed"
    return "runtime_probe_failed"


def _health_probe(
    package: ProviderPackage,
    fetcher: object,
) -> Callable[[], Awaitable[None]]:
    async def probe() -> None:
        service = ProviderSearchService((package,))
        try:
            await service.search(
                VideoSearchRequest(
                    provider_key=package.provider_key,
                    query="nsfwtrack-healthcheck",
                    page=1,
                    page_size=1,
                )
            )
        except (ProviderSearchServiceError, ValueError, TypeError):
            raise ProviderRuntimeCatalogError(_probe_error_code(fetcher)) from None

    return probe


def build_runtime_provider(
    view: ProviderRuntimeView,
    *,
    client_factory: ControlledClientFactory = build_controlled_client,
) -> RuntimeProviderPackage:
    """Build one local-runtime-eligible package without sending a request."""

    if not view.local_runtime_ready:
        raise ProviderRuntimeCatalogError("provider_not_ready")
    try:
        if view.provider_key == "zuidapi_vod":
            fetcher = _ZuidapiRuntimeFetcher(
                client_factory(ZUIDAPI_ENDPOINT, view.egress_profile),
                view.provider_key,
            )
            package = build_zuidapi_production_package(fetcher=fetcher)
        elif view.provider_key == "copymanga":
            fetcher = _CopymangaRuntimeFetcher(
                client_factory(COPYMANGA_ENDPOINT, view.egress_profile),
                view.provider_key,
            )
            package = build_copymanga_production_package(fetcher=fetcher)
        elif view.provider_key == "javdb_metadata":
            try:
                cookie = load_javdb_session_cookie()
            except SessionCookieError:
                raise ProviderRuntimeCatalogError("session_missing") from None
            fetcher = _JavdbRuntimeFetcher(
                client_factory(JAVDB_PRODUCTION_ENDPOINT, view.egress_profile),
                cookie,
            )
            package = build_javdb_production_package(fetcher=fetcher)
        else:
            raise ProviderRuntimeCatalogError("provider_not_approved")
    except ProviderRuntimeCatalogError:
        raise
    except Exception:
        raise ProviderRuntimeCatalogError("runtime_initialization_failed") from None
    return RuntimeProviderPackage(
        provider_key=view.provider_key,
        package=package,
        health_probe=_health_probe(package, fetcher),
    )


def build_runtime_catalog(
    db: Session,
    *,
    package_factory: RuntimePackageFactory = build_runtime_provider,
) -> RuntimeCatalogSnapshot:
    """Build a stable active catalog from one read-only state snapshot."""

    views = ProviderRuntimeRegistry(db).list()
    packages: list[ProviderPackage] = []
    excluded: list[str] = []
    for view in views:
        if not view.local_runtime_ready or view.runtime_status != "ready":
            excluded.append(view.provider_key)
            continue
        try:
            packages.append(package_factory(view).package)
        except Exception:
            # A failed package must not make a neighboring Provider disappear.
            excluded.append(view.provider_key)
    packages.sort(key=lambda package: package.provider_key)
    return RuntimeCatalogSnapshot(tuple(packages), tuple(sorted(excluded)))


def build_runtime_search_service(
    db: Session,
    *,
    clock: Callable[[], datetime] = _utc_now,
    package_factory: RuntimePackageFactory = build_runtime_provider,
) -> ProviderSearchService:
    return ProviderSearchService(
        build_runtime_catalog(db, package_factory=package_factory).packages,
        clock,
    )


async def run_runtime_health_check(
    db: Session,
    provider_key: str,
    *,
    expected_version: int,
    package_factory: RuntimePackageFactory = build_runtime_provider,
) -> ProviderRuntimeView:
    """Run one explicit, bounded runtime probe and atomically record its result."""

    registry = ProviderRuntimeRegistry(db)
    plan = registry.prepare_health_check(
        provider_key,
        expected_version=expected_version,
    )
    if plan.blocker_code is not None:
        return registry.complete_health_check(
            provider_key,
            expected_version=plan.expected_version,
            success=False,
            error_code=plan.blocker_code,
        )
    try:
        runtime_package = package_factory(plan.provider)
        await runtime_package.health_probe()
    except ProviderRuntimeCatalogError as error:
        return registry.complete_health_check(
            provider_key,
            expected_version=plan.expected_version,
            success=False,
            error_code=error.code,
        )
    except asyncio.TimeoutError:
        return registry.complete_health_check(
            provider_key,
            expected_version=plan.expected_version,
            success=False,
            error_code="runtime_timeout",
        )
    except Exception:
        return registry.complete_health_check(
            provider_key,
            expected_version=plan.expected_version,
            success=False,
            error_code="runtime_probe_failed",
        )
    return registry.complete_health_check(
        provider_key,
        expected_version=plan.expected_version,
        success=True,
    )


__all__ = [
    "ProviderRuntimeCatalogError",
    "RuntimeCatalogSnapshot",
    "RuntimeProviderPackage",
    "build_controlled_client",
    "build_runtime_catalog",
    "build_runtime_provider",
    "build_runtime_search_service",
    "run_runtime_health_check",
]
