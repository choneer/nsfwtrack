"""Deprecated opt-in catalog compatibility helpers.

Environment flags no longer activate Provider runtimes. A reviewed identity
is not an outbound-network approval, so every compatibility builder remains
fail-closed until a separately reviewed runtime injection boundary exists.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime

from app.acquisition.contracts import AcquisitionPackage
from app.acquisition.registry import AcquisitionRegistry
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
    return ()


def build_opt_in_acquisition_packages(
    *,
    env: dict[str, str] | None = None,
    include_javdb: bool = True,
    include_comic: bool = True,
) -> tuple[AcquisitionPackage, ...]:
    return ()


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
