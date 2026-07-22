"""Default production catalogs for Application 1.5.0+.

nsfwpro factory keys + real-site comic + control planes:
- javdb-metadata → javdb_metadata
- jiuse-vod → jiuse_vod (TEST_FIXTURE offline)
- zuidapi-vod → zuidapi_vod
- copymanga → real-site comic (PRODUCTION)
- comic_local_fixture → local download proof

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
    from app.providers.copymanga.approval import COPYMANGA_ENDPOINT
    from app.providers.javdb.production import JAVDB_PRODUCTION_ENDPOINT
    from app.providers.zuidapi.approval import ZUIDAPI_ENDPOINT

    return (JAVDB_PRODUCTION_ENDPOINT, ZUIDAPI_ENDPOINT, COPYMANGA_ENDPOINT)


def build_production_search_packages() -> tuple["ProviderPackage", ...]:
    from app.providers.comic.package_build import build_comic_fixture_package
    from app.providers.copymanga.package_build import build_copymanga_production_package
    from app.providers.javdb.package_build import build_javdb_production_package
    from app.providers.jiuse.package_build import build_jiuse_fixture_package
    from app.providers.zuidapi.package_build import build_zuidapi_production_package

    return (
        build_javdb_production_package(validate=True),
        build_jiuse_fixture_package(validate=True),
        build_zuidapi_production_package(validate=True),
        build_copymanga_production_package(validate=True),
        build_comic_fixture_package(validate=True),
    )


def build_production_acquisition_packages() -> tuple["AcquisitionPackage", ...]:
    from app.providers.comic.package_build import build_comic_acquisition_package
    from app.providers.copymanga.package_build import build_copymanga_acquisition_package
    from app.providers.javdb.package_build import build_javdb_acquisition_package
    from app.providers.javdb.session import SessionCookieError

    packages: list = [
        build_comic_acquisition_package(),
        build_copymanga_acquisition_package(
            static_pages={"p0001": b"\xff\xd8\xff\xd9"},
            static_lists={},
        ),
    ]
    try:
        packages.insert(0, build_javdb_acquisition_package())
    except SessionCookieError:
        packages.insert(
            0,
            build_javdb_acquisition_package(
                cookie="session=not-configured",
                static_bodies={},
                static_lists={},
            ),
        )
    return tuple(packages)


def build_production_endpoint_registry() -> "EndpointRegistry":
    from app.source_adapters.registry import EndpointRegistry

    return EndpointRegistry(build_production_endpoints())


def nsfwpro_factory_provider_keys() -> frozenset[str]:
    return frozenset(NSFWPRO_FACTORY_KEY_MAP.values())
