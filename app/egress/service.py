"""Egress snapshot assembly and config path resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.egress.client import proxy_host_for_log
from app.egress.myip import enrich_ipify_with_ipsb, javdb_compat, probe_myip_multi
from app.egress.pool import EgressError, ProxyPool


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def pool_config_path() -> Path:
    """Resolve proxy-pool.json path (env override, then data/, then .local/)."""

    raw = os.environ.get("NSFW_PROXY_POOL_CONFIG", "").strip()
    if raw:
        return Path(raw)
    root = _repo_root()
    for candidate in (
        root / "data" / "proxy-pool.json",
        root / ".local" / "proxy-pool.json",
    ):
        if candidate.is_file():
            return candidate
    return root / "data" / "proxy-pool.json"


def resolve_proxy_url(explicit: str | None = None) -> str | None:
    """Proxy URL from argument, env, or pool select (host logged without userinfo)."""

    if explicit and explicit.strip():
        return explicit.strip()
    for key in (
        "NSFW_HTTP_PROXY",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()
    path = pool_config_path()
    if not path.is_file():
        return None
    try:
        pool = ProxyPool.load(path)
        return pool.select().url
    except EgressError:
        return None


def load_pool() -> ProxyPool | None:
    path = pool_config_path()
    if not path.is_file():
        return None
    return ProxyPool.load(path)


def build_snapshot(*, with_quality: bool = False) -> dict[str, Any]:
    """Multi-source direct/proxy identity + optional pool probe + JavDB hint."""

    path = pool_config_path()
    config_exists = path.is_file()
    direct = enrich_ipify_with_ipsb(probe_myip_multi(proxy=None, timeout=5.0))
    proxy_url = resolve_proxy_url()
    via_proxy = None
    if proxy_url:
        via_proxy = enrich_ipify_with_ipsb(
            probe_myip_multi(proxy=proxy_url, timeout=8.0)
        )

    pool: ProxyPool | None = None
    pool_error: str | None = None
    if config_exists:
        try:
            pool = ProxyPool.load(path)
            if with_quality:
                pool.probe_all(timeout=20.0, with_quality=True)
                pool.save(path)
        except EgressError as exc:
            pool_error = str(exc)

    pool_summary = pool.summary() if pool else []
    selected = None
    if pool:
        try:
            chosen = pool.select(require_probed=False)
            selected = {
                "id": chosen.id,
                "url_host": proxy_host_for_log(chosen.url),
                "priority": chosen.priority,
            }
        except EgressError as exc:
            selected = {"error": str(exc)}

    via_dict = via_proxy.to_dict() if via_proxy else None
    return {
        "ok": True,
        "config_path": str(path),
        "config_exists": config_exists,
        "direct": direct.to_dict(),
        "via_proxy": via_dict,
        "resolved_proxy": proxy_host_for_log(proxy_url),
        "pool": pool_summary,
        "selected": selected,
        "pool_error": pool_error,
        "javdb": javdb_compat(via_proxy),
        "policy": asdict_policy(pool) if pool else {
            "deny_countries": ["JP", "KR"],
            "prefer_countries": [],
            "max_risk_score": 90,
        },
    }


def asdict_policy(pool: ProxyPool) -> dict[str, Any]:
    p = pool.policy
    return {
        "deny_countries": list(p.deny_countries),
        "prefer_countries": list(p.prefer_countries),
        "max_risk_score": p.max_risk_score,
        "geo_provider": p.geo_provider,
    }
