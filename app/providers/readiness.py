"""Catalog readiness snapshot for operator honesty (no secrets).

Reports whether each default search catalog provider is live-capable,
fixture-fallback, or not-configured for the *current process*, without
leaking cookie values or passwords.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.cookiecloud.client import default_cookie_store_path
from app.providers.javdb.session import SessionCookieError, load_javdb_session_cookie

ReadinessMode = Literal["live_capable", "fixture_fallback", "not_configured"]

# Default catalog keys (Application 1.5.0+); keep aligned with production_catalog.
DEFAULT_CATALOG_KEYS: tuple[str, ...] = (
    "javdb_metadata",
    "jiuse_vod",
    "zuidapi_vod",
    "copymanga",
    "comic_local_fixture",
)


@dataclass(frozen=True, slots=True)
class ProviderReadiness:
    provider_key: str
    mode: ReadinessMode
    scope: str
    reasons: tuple[str, ...]
    cookie_required: bool
    cookie_loadable: bool | None
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CatalogReadinessSnapshot:
    application_version: str
    proxy_configured: bool
    proxy_env_keys: tuple[str, ...]
    providers: tuple[ProviderReadiness, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "application_version": self.application_version,
            "proxy_configured": self.proxy_configured,
            "proxy_env_keys": list(self.proxy_env_keys),
            "providers": [p.to_dict() for p in self.providers],
        }


def _proxy_env() -> tuple[bool, tuple[str, ...]]:
    keys: list[str] = []
    for name in ("NSFWTRACK_HTTP_PROXY", "NSFW_HTTP_PROXY"):
        if (os.environ.get(name) or "").strip():
            keys.append(name)
    return bool(keys), tuple(keys)


def _javdb_cookie_loadable() -> bool:
    try:
        value = load_javdb_session_cookie()
    except SessionCookieError:
        return False
    # Never return the value; only whether a non-empty header loaded.
    return bool(value and value.strip())


def _javdb_readiness() -> ProviderReadiness:
    loadable = _javdb_cookie_loadable()
    env_set = bool(
        (os.environ.get("NSFWTRACK_JAVDB_SESSION_COOKIE") or "").strip()
        or (os.environ.get("NSFWTRACK_JAVDB_SESSION_COOKIE_FILE") or "").strip()
    )
    path = default_cookie_store_path("javdb_metadata")
    file_ok = path.is_file() and path.stat().st_size > 0
    reasons: list[str] = []
    if env_set:
        reasons.append("env_cookie_source")
    if file_ok:
        reasons.append("cookie_file_present")
    if loadable:
        reasons.append("session_cookie_loadable")
        return ProviderReadiness(
            provider_key="javdb_metadata",
            mode="live_capable",
            scope="PRODUCTION",
            reasons=tuple(reasons),
            cookie_required=True,
            cookie_loadable=True,
            notes="live_html_fetch_when_cookie_present",
        )
    reasons.append("no_session_cookie")
    reasons.append("package_uses_static_html_fallback")
    return ProviderReadiness(
        provider_key="javdb_metadata",
        mode="fixture_fallback",
        scope="PRODUCTION",
        reasons=tuple(reasons),
        cookie_required=True,
        cookie_loadable=False,
        notes="catalog_listed_but_search_uses_fixtures_until_cookie",
    )


def _static_default(
    key: str,
    *,
    scope: str,
    notes: str,
    reasons: tuple[str, ...] = ("default_package_static_fetcher",),
) -> ProviderReadiness:
    return ProviderReadiness(
        provider_key=key,
        mode="fixture_fallback",
        scope=scope,
        reasons=reasons,
        cookie_required=False,
        cookie_loadable=None,
        notes=notes,
    )


def build_catalog_readiness(
    *,
    application_version: str = "1.5.0",
) -> CatalogReadinessSnapshot:
    """Pure readiness for default catalog keys (no network, no secrets)."""

    proxy_ok, proxy_keys = _proxy_env()
    providers = (
        _javdb_readiness(),
        _static_default(
            "jiuse_vod",
            scope="TEST_FIXTURE",
            notes="offline_fixture_only_live_unauthorized",
            reasons=("test_fixture_scope", "live_endpoint_not_approved"),
        ),
        _static_default(
            "zuidapi_vod",
            scope="PRODUCTION",
            notes="production_approval_default_static_json_package",
            reasons=("default_package_static_fetcher", "live_fetcher_not_injected"),
        ),
        _static_default(
            "copymanga",
            scope="PRODUCTION",
            notes="production_comic_default_static_json_package",
            reasons=("default_package_static_fetcher", "live_fetcher_not_injected"),
        ),
        _static_default(
            "comic_local_fixture",
            scope="TEST_FIXTURE",
            notes="local_download_proof_only",
            reasons=("test_fixture_scope", "local_pages_only"),
        ),
    )
    # Ensure key order matches DEFAULT_CATALOG_KEYS
    by_key = {p.provider_key: p for p in providers}
    ordered = tuple(by_key[k] for k in DEFAULT_CATALOG_KEYS if k in by_key)
    return CatalogReadinessSnapshot(
        application_version=application_version,
        proxy_configured=proxy_ok,
        proxy_env_keys=proxy_keys,
        providers=ordered,
    )
