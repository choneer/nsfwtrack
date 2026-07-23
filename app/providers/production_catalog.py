"""Compatibility accessors for the runtime-backed production catalog.

The active catalog is constructed from one database Runtime snapshot in
``app.provider_runtime.catalog``.  A caller without that snapshot receives an
empty fail-closed compatibility result; application routes always pass through
the Runtime builder instead of using a process-global provider list.

CookieCloud and HLS are control/playback helpers, not Providers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.acquisition.contracts import AcquisitionPackage
    from app.source_adapters.package import ProviderPackage
    from app.source_adapters.registry import EndpointRegistry, ProviderEndpoint
    from sqlalchemy.orm import Session


NSFWPRO_FACTORY_KEY_MAP: dict[str, str] = {
    "javdb-metadata": "javdb_metadata",
    "jiuse-vod": "jiuse_vod",
    "zuidapi-vod": "zuidapi_vod",
}


def build_production_endpoints(
    db: "Session | None" = None,
) -> tuple["ProviderEndpoint", ...]:
    """Return endpoints active in the supplied Runtime state snapshot."""

    if db is None:
        return ()
    from app.provider_runtime.catalog import build_runtime_catalog

    return tuple(package.endpoint for package in build_runtime_catalog(db).packages)


def build_production_search_packages(
    db: "Session | None" = None,
) -> tuple["ProviderPackage", ...]:
    """Return active Search/Detail packages; TEST_FIXTURE is never a fallback."""

    if db is None:
        return ()
    from app.provider_runtime.catalog import build_runtime_catalog

    return build_runtime_catalog(db).packages


def build_production_acquisition_packages() -> tuple["AcquisitionPackage", ...]:
    """Return activated acquisition packages; none are activated by default."""

    return ()


def build_production_endpoint_registry(
    db: "Session | None" = None,
) -> "EndpointRegistry":
    from app.source_adapters.registry import EndpointRegistry

    return EndpointRegistry(build_production_endpoints(db))


def nsfwpro_factory_provider_keys() -> frozenset[str]:
    return frozenset(NSFWPRO_FACTORY_KEY_MAP.values())
