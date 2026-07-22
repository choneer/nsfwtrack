"""Reviewed Provider identities and fail-closed production catalogs.

The package builders in :mod:`app.providers` remain available for offline
validation with explicitly injected test doubles.  They are not production
activation: no default package is registered until its network transport is
implemented through the shared controlled outbound boundary.

CookieCloud and HLS are control/playback helpers, not Providers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.acquisition.contracts import AcquisitionPackage
    from app.source_adapters.package import ProviderPackage
    from app.source_adapters.registry import EndpointRegistry, ProviderEndpoint


NSFWPRO_FACTORY_KEY_MAP: dict[str, str] = {
    "javdb-metadata": "javdb_metadata",
    "jiuse-vod": "jiuse_vod",
    "zuidapi-vod": "zuidapi_vod",
}


def build_production_endpoints() -> tuple["ProviderEndpoint", ...]:
    """Return activated endpoints; none are activated in Application 1.5.0."""

    return ()


def build_production_search_packages() -> tuple["ProviderPackage", ...]:
    """Return activated search packages; TEST_FIXTURE is never a fallback."""

    return ()


def build_production_acquisition_packages() -> tuple["AcquisitionPackage", ...]:
    """Return activated acquisition packages; none are activated by default."""

    return ()


def build_production_endpoint_registry() -> "EndpointRegistry":
    from app.source_adapters.registry import EndpointRegistry

    return EndpointRegistry(build_production_endpoints())


def nsfwpro_factory_provider_keys() -> frozenset[str]:
    return frozenset(NSFWPRO_FACTORY_KEY_MAP.values())
