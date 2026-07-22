"""Opt-in production-shaped catalogs (does not mutate v1.3 empty defaults).

Environment:
  NSFWTRACK_ENABLE_OPT_IN_PROVIDERS=1  include builders when constructing services
  NSFWTRACK_JAVDB_SESSION_COOKIE / _FILE  required for live JavDB fetch/download

Default ``build_production_search_service`` / acquisition registry stay empty.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime

from app.acquisition.contracts import AcquisitionPackage
from app.acquisition.registry import AcquisitionRegistry
from app.providers.comic.package_build import (
    build_comic_acquisition_package,
    build_comic_fixture_package,
)
from app.providers.javdb.package_build import (
    build_javdb_acquisition_package,
    build_javdb_production_package,
)
from app.providers.javdb.session import SessionCookieError
from app.source_adapters.package import ProviderPackage
from app.source_search.service import ProviderSearchService, _utc_now


def opt_in_enabled(env: dict[str, str] | None = None) -> bool:
    environ = env if env is not None else os.environ
    return (environ.get("NSFWTRACK_ENABLE_OPT_IN_PROVIDERS") or "").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }


def build_opt_in_search_packages(
    *,
    env: dict[str, str] | None = None,
    include_javdb: bool = True,
    include_comic_fixture: bool = True,
) -> tuple[ProviderPackage, ...]:
    packages: list[ProviderPackage] = []
    if include_javdb:
        packages.append(build_javdb_production_package(validate=True))
    if include_comic_fixture:
        packages.append(build_comic_fixture_package(validate=True))
    return tuple(packages)


def build_opt_in_acquisition_packages(
    *,
    env: dict[str, str] | None = None,
    include_javdb: bool = True,
    include_comic: bool = True,
) -> tuple[AcquisitionPackage, ...]:
    packages: list[AcquisitionPackage] = []
    if include_javdb:
        try:
            packages.append(build_javdb_acquisition_package())
        except SessionCookieError:
            # Without cookie, still allow static test construction by caller.
            pass
    if include_comic:
        packages.append(build_comic_acquisition_package())
    return tuple(packages)


def build_opt_in_search_service(
    clock: Callable[[], datetime] = _utc_now,
    *,
    env: dict[str, str] | None = None,
) -> ProviderSearchService:
    if not opt_in_enabled(env):
        return ProviderSearchService((), clock)
    return ProviderSearchService(build_opt_in_search_packages(env=env), clock)


def build_opt_in_acquisition_registry(
    *,
    env: dict[str, str] | None = None,
) -> AcquisitionRegistry:
    if not opt_in_enabled(env):
        return AcquisitionRegistry(())
    return AcquisitionRegistry(build_opt_in_acquisition_packages(env=env))
