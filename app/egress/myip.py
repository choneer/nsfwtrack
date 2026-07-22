"""OpenClash-style multi-source concurrent public-IP identity probe."""

from __future__ import annotations

import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any, Callable
from urllib.parse import urlparse

from app.egress.client import fetch_text, proxy_host_for_log


_IP_RE = re.compile(
    r"(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)"
)


@dataclass(frozen=True, slots=True)
class MyIPSourceResult:
    name: str
    ok: bool
    latency_ms: int | None
    ip: str | None
    geo: str | None
    country_code: str | None
    isp: str | None
    error: str | None
    url_host: str


@dataclass(frozen=True, slots=True)
class MyIPSnapshot:
    mode: str  # direct | proxy
    proxy_url_host: str | None
    consensus_ip: str | None
    agreement: int
    sources: tuple[MyIPSourceResult, ...]
    checked_at_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "proxy_url_host": self.proxy_url_host,
            "consensus_ip": self.consensus_ip,
            "agreement": self.agreement,
            "checked_at_ms": self.checked_at_ms,
            "sources": [asdict(s) for s in self.sources],
        }


def _nonce() -> int:
    return random.randint(100_000_000, 999_999_999)


def _host(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or url


def _parse_upaiyun(data: str) -> tuple[str | None, str | None, str | None, str | None]:
    payload = json.loads(data)
    ip = payload.get("remote_addr")
    if not isinstance(ip, str):
        return None, None, None, None
    geo_parts: list[str] = []
    loc = payload.get("remote_addr_location") or {}
    country = None
    isp = None
    if isinstance(loc, dict):
        for key in ("country", "province", "city"):
            value = loc.get(key)
            if isinstance(value, str) and value:
                geo_parts.append(value)
                if key == "country":
                    country = value
        isp_val = loc.get("isp")
        if isinstance(isp_val, str) and isp_val:
            isp = isp_val
            geo_parts.append(isp_val)
    return ip, " ".join(geo_parts) or None, None, isp


def _parse_ipip_text(data: str) -> tuple[str | None, str | None, str | None, str | None]:
    ip_match = re.search(r"当前\s*IP[：:]\s*([0-9a-fA-F:\.]+)", data)
    geo_match = re.search(r"来自于[：:]\s*(.+)", data)
    ip = ip_match.group(1) if ip_match else None
    geo = geo_match.group(1).strip() if geo_match else None
    if geo:
        geo = re.sub(r"\s+", " ", geo)
    return ip, geo, None, None


def _parse_ipsb(data: str) -> tuple[str | None, str | None, str | None, str | None]:
    payload = json.loads(data)
    ip = payload.get("ip")
    if not isinstance(ip, str):
        return None, None, None, None
    parts: list[str] = []
    country = payload.get("country")
    country_code = payload.get("country_code")
    isp = payload.get("isp") or payload.get("organization")
    if isinstance(country, str) and country:
        parts.append(country)
    if isinstance(isp, str) and isp:
        parts.append(isp)
    cc = country_code.upper() if isinstance(country_code, str) else None
    return ip, " ".join(parts) or None, cc, isp if isinstance(isp, str) else None


def _parse_ipify(data: str) -> tuple[str | None, str | None, str | None, str | None]:
    payload = json.loads(data)
    ip = payload.get("ip")
    return (ip if isinstance(ip, str) else None), None, None, None


def _parse_ip_api(data: str) -> tuple[str | None, str | None, str | None, str | None]:
    payload = json.loads(data)
    if str(payload.get("status", "")).lower() != "success":
        return None, None, None, None
    ip = payload.get("query")
    parts = [
        str(payload[k])
        for k in ("country", "regionName", "city", "isp")
        if payload.get(k)
    ]
    cc = str(payload["countryCode"]).upper() if payload.get("countryCode") else None
    isp = str(payload["isp"]) if payload.get("isp") else None
    return (ip if isinstance(ip, str) else None), " ".join(parts) or None, cc, isp


@dataclass(frozen=True, slots=True)
class _Source:
    name: str
    url_factory: Callable[[], str]
    parser: Callable[[str], tuple[str | None, str | None, str | None, str | None]]


def _default_sources() -> tuple[_Source, ...]:
    z = _nonce()
    return (
        _Source("ipsb", lambda: f"https://api.ip.sb/geoip/?z={z}", _parse_ipsb),
        _Source("ipsb-ipv4", lambda: f"https://api-ipv4.ip.sb/geoip?z={z}", _parse_ipsb),
        _Source("ipify", lambda: f"https://api.ipify.org/?format=json&z={z}", _parse_ipify),
        _Source("ip-api", lambda: f"http://ip-api.com/json/?lang=zh-CN&z={z}", _parse_ip_api),
        _Source("ipip", lambda: f"http://myip.ipip.net?z={z}", _parse_ipip_text),
        _Source(
            "upaiyun",
            lambda: f"https://pubstatic.b0.upaiyun.com/?_upnode&z={z}",
            _parse_upaiyun,
        ),
    )


def _normalize_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    candidate = ip.split("%")[0].strip()
    if _IP_RE.fullmatch(candidate):
        return candidate
    found = _IP_RE.search(candidate)
    return found.group(0) if found else None


def _fetch_one(source: _Source, *, proxy: str | None, timeout: float) -> MyIPSourceResult:
    url = source.url_factory()
    result = fetch_text(url, proxy=proxy, timeout=timeout)
    if not result.ok:
        return MyIPSourceResult(
            name=source.name,
            ok=False,
            latency_ms=result.latency_ms,
            ip=None,
            geo=None,
            country_code=None,
            isp=None,
            error=result.error or "fetch failed",
            url_host=_host(url),
        )
    try:
        ip, geo, cc, isp = source.parser(result.body)
    except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
        return MyIPSourceResult(
            name=source.name,
            ok=False,
            latency_ms=result.latency_ms,
            ip=None,
            geo=None,
            country_code=None,
            isp=None,
            error=f"parse: {exc}"[:160],
            url_host=_host(url),
        )
    ip = _normalize_ip(ip)
    if not ip:
        return MyIPSourceResult(
            name=source.name,
            ok=False,
            latency_ms=result.latency_ms,
            ip=None,
            geo=geo,
            country_code=cc,
            isp=isp,
            error="no ipv4 in response",
            url_host=_host(url),
        )
    return MyIPSourceResult(
        name=source.name,
        ok=True,
        latency_ms=result.latency_ms,
        ip=ip,
        geo=geo,
        country_code=cc,
        isp=isp,
        error=None,
        url_host=_host(url),
    )


def probe_myip_multi(
    *,
    proxy: str | None = None,
    timeout: float = 5.0,
    max_workers: int = 6,
) -> MyIPSnapshot:
    sources = _default_sources()
    results: list[MyIPSourceResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_fetch_one, source, proxy=proxy, timeout=timeout): source.name
            for source in sources
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: item.name)
    votes: dict[str, int] = {}
    for item in results:
        if item.ok and item.ip:
            votes[item.ip] = votes.get(item.ip, 0) + 1
    consensus_ip = None
    agreement = 0
    if votes:
        consensus_ip, agreement = max(votes.items(), key=lambda kv: (kv[1], kv[0]))

    return MyIPSnapshot(
        mode="proxy" if proxy else "direct",
        proxy_url_host=proxy_host_for_log(proxy),
        consensus_ip=consensus_ip,
        agreement=agreement,
        sources=tuple(results),
        checked_at_ms=int(time.time() * 1000),
    )


def enrich_ipify_with_ipsb(
    snapshot: MyIPSnapshot,
    *,
    timeout: float = 5.0,
) -> MyIPSnapshot:
    """If ipify has IP but empty geo, fill via api.ip.sb (OpenClash pattern)."""

    updated: list[MyIPSourceResult] = []
    for item in snapshot.sources:
        if item.name == "ipify" and item.ok and item.ip and not item.geo:
            result = fetch_text(
                f"https://api.ip.sb/geoip/{item.ip}",
                timeout=timeout,
                headers={"Accept": "application/json"},
            )
            if result.ok:
                try:
                    ip, geo, cc, isp = _parse_ipsb(result.body)
                    updated.append(
                        MyIPSourceResult(
                            name=item.name,
                            ok=True,
                            latency_ms=item.latency_ms,
                            ip=ip or item.ip,
                            geo=geo,
                            country_code=cc,
                            isp=isp,
                            error=None,
                            url_host=item.url_host,
                        )
                    )
                    continue
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass
        updated.append(item)
    return MyIPSnapshot(
        mode=snapshot.mode,
        proxy_url_host=snapshot.proxy_url_host,
        consensus_ip=snapshot.consensus_ip,
        agreement=snapshot.agreement,
        sources=tuple(updated),
        checked_at_ms=snapshot.checked_at_ms,
    )


def javdb_compat(snapshot: MyIPSnapshot | None) -> dict[str, Any]:
    """Whether proxy egress looks safe for JavDB (non-JP/KR)."""

    deny = ("JP", "KR")
    if snapshot is None or not snapshot.consensus_ip:
        return {
            "ok": None,
            "deny_countries": list(deny),
            "country_code": None,
            "message": "no_proxy_or_unknown",
        }
    codes = [
        (s.country_code or "").upper()
        for s in snapshot.sources
        if s.ok and s.ip == snapshot.consensus_ip and s.country_code
    ]
    if not codes:
        return {
            "ok": None,
            "deny_countries": list(deny),
            "country_code": None,
            "message": "country_unknown",
        }
    # Prefer majority country among consensus sources
    from collections import Counter

    counted = Counter(codes)
    ranked = counted.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return {
            "ok": None,
            "deny_countries": list(deny),
            "country_code": None,
            "message": "country_conflict",
        }
    country = ranked[0][0]
    blocked = country in deny
    return {
        "ok": not blocked,
        "deny_countries": list(deny),
        "country_code": country,
        "message": "blocked" if blocked else "ok",
    }
