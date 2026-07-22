"""Local proxy pool: load, probe, score, and select egress proxies."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.egress.client import fetch_json, fetch_text, proxy_host_for_log


_IP_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)


class EgressError(Exception):
    """User-facing egress/pool error (no secrets)."""


@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    id: str
    url: str
    enabled: bool = True
    priority: int = 100
    tags: tuple[str, ...] = ()
    expected_country: str | None = None
    notes: str = ""


@dataclass(slots=True)
class ProxyHealth:
    proxy_id: str
    ok: bool
    checked_at: str
    latency_ms: int | None = None
    exit_ip: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    risk_score: int | None = None
    ip_type: str | None = None
    isp: str | None = None
    error: str | None = None
    geo_source: str | None = None
    quality_score: int | None = None
    quality_grade: str | None = None
    quality_passed: int | None = None
    quality_failed: int | None = None
    fail_count: int = 0
    cooldown_until: float = 0.0

    def in_cooldown(self, now: float | None = None) -> bool:
        ts = time.time() if now is None else now
        return self.cooldown_until > ts


@dataclass(frozen=True, slots=True)
class ProxyPoolPolicy:
    deny_countries: tuple[str, ...] = ("JP", "KR")
    prefer_countries: tuple[str, ...] = ()
    max_risk_score: int = 90
    require_exit_ip: bool = True
    cooldown_seconds: int = 300
    max_fail_count_before_disable: int = 5
    probe_url: str = ""
    geo_provider: str = "ip_sb"


@dataclass(frozen=True, slots=True)
class QualityItem:
    target: str
    ok: bool
    latency_ms: int | None
    status_code: int | None
    message: str


@dataclass(frozen=True, slots=True)
class QualityReport:
    proxy_id: str
    score: int
    grade: str
    passed: int
    failed: int
    base_latency_ms: int | None
    items: tuple[QualityItem, ...]


@dataclass(frozen=True, slots=True)
class GeoResult:
    ip: str
    country_code: str | None
    country_name: str | None
    isp: str | None
    risk_score: int
    ip_type: str | None
    source: str


DEFAULT_QUALITY_TARGETS: tuple[tuple[str, str, int], ...] = (
    ("cloudflare-trace", "https://www.cloudflare.com/cdn-cgi/trace", 2),
    ("ipify", "https://api.ipify.org?format=json", 2),
    ("ipsb-geoip", "https://api.ip.sb/geoip/", 2),
    ("example", "https://example.com/", 1),
)

_EXIT_PROBE_URLS = (
    "https://api.ipify.org?format=json",
    "http://ip-api.com/json/?fields=query,status",
    "https://ifconfig.me/ip",
)


def _clamp_score(value: float | int) -> int:
    return max(0, min(100, int(value)))


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _validate_proxy_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"}:
        raise EgressError("proxy url scheme must be http, https, socks5, or socks5h")
    if not parsed.hostname:
        raise EgressError("proxy url must include a hostname")
    if parsed.fragment:
        raise EgressError("proxy url must not include a fragment")
    # stdlib urllib only supports HTTP(S) proxies for HTTPS targets
    if parsed.scheme in {"socks5", "socks5h"}:
        raise EgressError(
            "socks proxies need extra deps; use a local HTTP proxy (e.g. Clash :6123)"
        )


def probe_exit_ip(proxy_url: str, *, probe_url: str | None = None, timeout: float = 20.0) -> str:
    urls = (probe_url,) if probe_url else _EXIT_PROBE_URLS
    errors: list[str] = []
    for url in urls:
        if not url:
            continue
        result = fetch_text(url, proxy=proxy_url, timeout=timeout)
        if not result.ok:
            errors.append(f"{url}: {result.error}")
            continue
        text = result.body.strip()
        try:
            if text.startswith("{"):
                data = json.loads(text)
                if isinstance(data, dict):
                    for key in ("ip", "query", "origin"):
                        if isinstance(data.get(key), str):
                            candidate = data[key].split(",")[0].strip()
                            if _IP_RE.match(candidate):
                                return candidate
            candidate = text.strip().strip('"')
            if _IP_RE.match(candidate):
                return candidate
            found = _IP_RE.search(candidate)
            if found:
                return found.group(0)
            errors.append(f"{url}: no ipv4")
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{url}: {exc}")
    raise EgressError(
        "exit-ip probe failed: " + (errors[-1] if errors else "no probe url")
    )


def resolve_geo(ip: str, *, provider: str = "ip_sb", timeout: float = 12.0) -> GeoResult:
    if not _IP_RE.match(ip):
        raise EgressError(f"invalid ip: {ip}")
    name = (provider or "ip_sb").strip().lower()
    if name in {"ip_api", "ip-api", "ipapi"}:
        return _geo_ip_api(ip, timeout=timeout)
    # default / ip_sb / composite → try ip.sb then ip-api
    try:
        return _geo_ip_sb(ip, timeout=timeout)
    except EgressError:
        if name in {"ip_sb", "ipsb", "ip.sb", "api.ip.sb"}:
            raise
        return _geo_ip_api(ip, timeout=timeout)


def _geo_ip_sb(ip: str, *, timeout: float) -> GeoResult:
    result, data = fetch_json(f"https://api.ip.sb/geoip/{ip}", timeout=timeout)
    if not result.ok or not isinstance(data, dict):
        raise EgressError(result.error or "api.ip.sb failed")
    country_code = data.get("country_code")
    if isinstance(country_code, str):
        country_code = country_code.upper()
    else:
        country_code = None
    org = str(data.get("organization") or data.get("asn_organization") or "") or None
    isp = str(data.get("isp") or "") or None
    blob = " ".join(x for x in (org, isp) if x).lower()
    hosting_tokens = (
        "google", "amazon", "aws", "azure", "digitalocean", "cloud", "vps",
        "hosting", "server", "colo", "ovh", "hetzner", "linode", "vultr",
        "oracle", "alibaba", "tencent", "cdn",
    )
    is_hosting = any(token in blob for token in hosting_tokens)
    score = 15 + (40 if is_hosting else 0)
    if any(token in blob for token in ("vpn", "proxy", "tor")):
        score += 30
    resolved = data.get("ip")
    if not isinstance(resolved, str) or not _IP_RE.match(resolved):
        resolved = ip
    return GeoResult(
        ip=resolved,
        country_code=country_code,
        country_name=str(data["country"]) if data.get("country") else None,
        isp=isp,
        risk_score=_clamp_score(score),
        ip_type="datacenter" if is_hosting else "residential_or_isp",
        source="api.ip.sb",
    )


def _geo_ip_api(ip: str, *, timeout: float) -> GeoResult:
    fields = (
        "status,message,country,countryCode,regionName,city,isp,org,as,"
        "mobile,proxy,hosting,query"
    )
    result, data = fetch_json(
        f"http://ip-api.com/json/{ip}?fields={fields}",
        timeout=timeout,
    )
    if not result.ok or not isinstance(data, dict) or data.get("status") != "success":
        raise EgressError(result.error or "ip-api failed")
    is_hosting = bool(data.get("hosting"))
    is_proxy = bool(data.get("proxy"))
    is_mobile = bool(data.get("mobile"))
    score = 10
    if is_mobile:
        score += 5
    if is_hosting:
        score += 35
    if is_proxy:
        score += 40
    org = str(data.get("org") or "")
    if any(token in org.lower() for token in ("cloud", "vps", "hosting", "server", "colo")):
        score += 10
    ip_type = "unknown"
    if is_mobile:
        ip_type = "mobile"
    elif is_hosting or is_proxy:
        ip_type = "datacenter"
    elif org:
        ip_type = "residential_or_isp"
    return GeoResult(
        ip=str(data.get("query") or ip),
        country_code=(str(data["countryCode"]).upper() if data.get("countryCode") else None),
        country_name=str(data["country"]) if data.get("country") else None,
        isp=str(data["isp"]) if data.get("isp") else None,
        risk_score=_clamp_score(score),
        ip_type=ip_type,
        source="ip-api.com",
    )


def check_proxy_quality(
    proxy_url: str,
    *,
    proxy_id: str = "proxy",
    timeout: float = 8.0,
    max_workers: int = 4,
    base_latency_ms: int | None = None,
) -> QualityReport:
    items: list[QualityItem] = []

    def one(name: str, url: str) -> QualityItem:
        result = fetch_text(url, proxy=proxy_url, timeout=timeout)
        ok = result.ok and (result.status_code or 0) < 400
        # allow redirects as ok for example.com etc.
        if result.status_code in {301, 302, 303, 307, 308}:
            ok = True
        return QualityItem(
            target=name,
            ok=ok,
            latency_ms=result.latency_ms,
            status_code=result.status_code,
            message="ok" if ok else (result.error or "fail")[:160],
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(one, name, url): (name, weight)
            for name, url, weight in DEFAULT_QUALITY_TARGETS
        }
        weight_map: dict[str, int] = {}
        for future in as_completed(futures):
            name, weight = futures[future]
            weight_map[name] = weight
            items.append(future.result())

    items.sort(key=lambda item: item.target)
    total_weight = sum(weight_map.get(i.target, 1) for i in items) or 1
    earned = sum(weight_map.get(i.target, 1) for i in items if i.ok)
    score = int(round(100.0 * earned / total_weight))
    success_lat = [i.latency_ms for i in items if i.ok and i.latency_ms is not None]
    if success_lat:
        avg = sum(success_lat) / len(success_lat)
        if avg > 3000:
            score = max(0, score - 15)
        elif avg > 1500:
            score = max(0, score - 8)
    passed = sum(1 for i in items if i.ok)
    failed = len(items) - passed
    return QualityReport(
        proxy_id=proxy_id,
        score=score,
        grade=_grade(score),
        passed=passed,
        failed=failed,
        base_latency_ms=base_latency_ms,
        items=tuple(items),
    )


@dataclass
class ProxyPool:
    proxies: list[ProxyEndpoint]
    policy: ProxyPoolPolicy = field(default_factory=ProxyPoolPolicy)
    health: dict[str, ProxyHealth] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProxyPool":
        if not isinstance(payload, dict):
            raise EgressError("proxy pool root must be an object")
        raw_policy = payload.get("policy") or {}
        if not isinstance(raw_policy, dict):
            raise EgressError("policy must be an object")
        policy = ProxyPoolPolicy(
            deny_countries=tuple(
                str(c).upper() for c in raw_policy.get("deny_countries", ("JP", "KR"))
            ),
            prefer_countries=tuple(
                str(c).upper() for c in raw_policy.get("prefer_countries", ())
            ),
            max_risk_score=int(raw_policy.get("max_risk_score", 90)),
            require_exit_ip=bool(raw_policy.get("require_exit_ip", True)),
            cooldown_seconds=int(raw_policy.get("cooldown_seconds", 300)),
            max_fail_count_before_disable=int(
                raw_policy.get("max_fail_count_before_disable", 5)
            ),
            probe_url=str(raw_policy["probe_url"]) if raw_policy.get("probe_url") else "",
            geo_provider=str(raw_policy.get("geo_provider", "ip_sb")),
        )
        raw_proxies = payload.get("proxies") or []
        if not isinstance(raw_proxies, list) or not raw_proxies:
            raise EgressError("proxies must be a non-empty list")
        proxies: list[ProxyEndpoint] = []
        seen: set[str] = set()
        for item in raw_proxies:
            if not isinstance(item, dict):
                raise EgressError("proxy entry must be an object")
            proxy_id = str(item.get("id") or "").strip()
            url = str(item.get("url") or "").strip()
            if not proxy_id or proxy_id in seen:
                raise EgressError("proxy id must be unique and non-empty")
            _validate_proxy_url(url)
            seen.add(proxy_id)
            tags = item.get("tags") or []
            if not isinstance(tags, list):
                raise EgressError("tags must be a list")
            expected = item.get("expected_country")
            proxies.append(
                ProxyEndpoint(
                    id=proxy_id,
                    url=url,
                    enabled=bool(item.get("enabled", True)),
                    priority=int(item.get("priority", 100)),
                    tags=tuple(str(t) for t in tags),
                    expected_country=str(expected).upper() if expected else None,
                    notes=str(item.get("notes") or ""),
                )
            )
        health: dict[str, ProxyHealth] = {}
        raw_health = payload.get("health") or {}
        if isinstance(raw_health, dict):
            for proxy_id, value in raw_health.items():
                if not isinstance(value, dict):
                    continue
                health[str(proxy_id)] = ProxyHealth(
                    proxy_id=str(proxy_id),
                    ok=bool(value.get("ok", False)),
                    checked_at=str(value.get("checked_at") or ""),
                    latency_ms=value.get("latency_ms"),
                    exit_ip=value.get("exit_ip"),
                    country_code=value.get("country_code"),
                    country_name=value.get("country_name"),
                    risk_score=value.get("risk_score"),
                    ip_type=value.get("ip_type"),
                    isp=value.get("isp"),
                    error=value.get("error"),
                    geo_source=value.get("geo_source"),
                    quality_score=value.get("quality_score"),
                    quality_grade=value.get("quality_grade"),
                    quality_passed=value.get("quality_passed"),
                    quality_failed=value.get("quality_failed"),
                    fail_count=int(value.get("fail_count") or 0),
                    cooldown_until=float(value.get("cooldown_until") or 0),
                )
        return cls(proxies=proxies, policy=policy, health=health)

    @classmethod
    def load(cls, path: str | Path) -> "ProxyPool":
        file_path = Path(path)
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EgressError(f"cannot load proxy pool: {exc}") from exc
        return cls.from_dict(payload)

    def save(self, path: str | Path) -> None:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # Do not persist raw proxy URLs with credentials into health; proxies stay as configured.
        payload = {
            "policy": asdict(self.policy),
            "proxies": [asdict(p) for p in self.proxies],
            "health": {k: asdict(v) for k, v in self.health.items()},
        }
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{file_path.name}.",
            suffix=".tmp",
            dir=file_path.parent,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = -1
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, file_path)
            directory_descriptor = os.open(file_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def get(self, proxy_id: str) -> ProxyEndpoint | None:
        for proxy in self.proxies:
            if proxy.id == proxy_id:
                return proxy
        return None

    def _policy_reject_reason(
        self, proxy: ProxyEndpoint, health: ProxyHealth
    ) -> str | None:
        if self.policy.require_exit_ip and not health.exit_ip:
            return "missing exit ip"
        cc = (health.country_code or "").upper()
        if cc and cc in self.policy.deny_countries:
            return f"denied country {cc}"
        if proxy.expected_country and cc and cc != proxy.expected_country.upper():
            return f"expected country {proxy.expected_country}, got {cc}"
        if (
            health.risk_score is not None
            and health.risk_score > self.policy.max_risk_score
        ):
            return f"risk_score {health.risk_score} > max {self.policy.max_risk_score}"
        return None

    def probe_one(
        self,
        proxy_id: str,
        *,
        timeout: float = 20.0,
        with_quality: bool = False,
    ) -> ProxyHealth:
        proxy = self.get(proxy_id)
        if proxy is None:
            raise EgressError(f"unknown proxy id: {proxy_id}")
        started = time.perf_counter()
        checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        previous = self.health.get(proxy_id)
        fail_count = previous.fail_count if previous else 0
        quality: QualityReport | None = None
        try:
            exit_ip = probe_exit_ip(
                proxy.url,
                probe_url=self.policy.probe_url or None,
                timeout=timeout,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            geo = resolve_geo(exit_ip, provider=self.policy.geo_provider)
            if with_quality:
                quality = check_proxy_quality(
                    proxy.url,
                    proxy_id=proxy_id,
                    timeout=min(timeout, 8.0),
                    base_latency_ms=latency_ms,
                )
            health = ProxyHealth(
                proxy_id=proxy_id,
                ok=True,
                checked_at=checked_at,
                latency_ms=latency_ms,
                exit_ip=exit_ip,
                country_code=geo.country_code,
                country_name=geo.country_name,
                risk_score=geo.risk_score,
                ip_type=geo.ip_type,
                isp=geo.isp,
                error=None,
                geo_source=geo.source,
                quality_score=quality.score if quality else None,
                quality_grade=quality.grade if quality else None,
                quality_passed=quality.passed if quality else None,
                quality_failed=quality.failed if quality else None,
                fail_count=0,
                cooldown_until=0.0,
            )
            reason = self._policy_reject_reason(proxy, health)
            if reason:
                health.ok = False
                health.error = reason
                health.fail_count = fail_count + 1
                health.cooldown_until = time.time() + self.policy.cooldown_seconds
        except EgressError as exc:
            health = ProxyHealth(
                proxy_id=proxy_id,
                ok=False,
                checked_at=checked_at,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc),
                fail_count=fail_count + 1,
                cooldown_until=time.time() + self.policy.cooldown_seconds,
            )
        self.health[proxy_id] = health
        return health

    def probe_all(
        self, *, timeout: float = 20.0, with_quality: bool = False
    ) -> list[ProxyHealth]:
        return [
            self.probe_one(proxy.id, timeout=timeout, with_quality=with_quality)
            for proxy in self.proxies
            if proxy.enabled
        ]

    def eligible(self, *, now: float | None = None) -> list[ProxyEndpoint]:
        ts = time.time() if now is None else now
        result: list[ProxyEndpoint] = []
        for proxy in self.proxies:
            if not proxy.enabled:
                continue
            health = self.health.get(proxy.id)
            if health is None:
                result.append(proxy)
                continue
            if health.in_cooldown(ts):
                continue
            if health.fail_count >= self.policy.max_fail_count_before_disable:
                continue
            if health.ok and self._policy_reject_reason(proxy, health):
                continue
            if health.ok is False and not health.in_cooldown(ts):
                result.append(proxy)
                continue
            if health.ok:
                result.append(proxy)
        return result

    def select(self, *, require_probed: bool = False) -> ProxyEndpoint:
        candidates = self.eligible()
        if require_probed:
            candidates = [
                p for p in candidates if self.health.get(p.id) and self.health[p.id].ok
            ]
        if not candidates:
            raise EgressError("no eligible proxy in pool")

        def sort_key(proxy: ProxyEndpoint) -> tuple:
            health = self.health.get(proxy.id)
            prefer = 0
            if (
                health
                and health.country_code
                and health.country_code.upper() in self.policy.prefer_countries
            ):
                prefer = -1
            latency = (
                health.latency_ms if health and health.latency_ms is not None else 50_000
            )
            risk = health.risk_score if health and health.risk_score is not None else 50
            quality = (
                -(health.quality_score)
                if health and health.quality_score is not None
                else 0
            )
            return (proxy.priority, prefer, quality, latency, risk, proxy.id)

        return sorted(candidates, key=sort_key)[0]

    def summary(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for proxy in self.proxies:
            health = self.health.get(proxy.id)
            rows.append(
                {
                    "id": proxy.id,
                    "enabled": proxy.enabled,
                    "priority": proxy.priority,
                    "tags": list(proxy.tags),
                    "expected_country": proxy.expected_country,
                    "url_host": proxy_host_for_log(proxy.url),
                    "notes": proxy.notes,
                    "health": None
                    if health is None
                    else {
                        "ok": health.ok,
                        "checked_at": health.checked_at,
                        "latency_ms": health.latency_ms,
                        "exit_ip": health.exit_ip,
                        "country_code": health.country_code,
                        "country_name": health.country_name,
                        "risk_score": health.risk_score,
                        "ip_type": health.ip_type,
                        "isp": health.isp,
                        "error": health.error,
                        "geo_source": health.geo_source,
                        "quality_score": health.quality_score,
                        "quality_grade": health.quality_grade,
                        "quality_passed": health.quality_passed,
                        "quality_failed": health.quality_failed,
                        "fail_count": health.fail_count,
                        "in_cooldown": health.in_cooldown(),
                    },
                }
            )
        return rows
