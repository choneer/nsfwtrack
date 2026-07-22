"""Unit tests for app.egress (no live network)."""

from __future__ import annotations

from pathlib import Path
import stat

import pytest

from app.egress import pool as pool_mod
from app.egress.client import FetchResult, proxy_host_for_log
from app.egress.myip import MyIPSnapshot, MyIPSourceResult, javdb_compat
from app.egress.pool import EgressError, ProxyPool
from app.egress.service import build_snapshot, pool_config_path, resolve_proxy_url


def test_proxy_host_strips_userinfo() -> None:
    assert proxy_host_for_log("http://user:pass@127.0.0.1:6123") == "127.0.0.1:6123"
    assert proxy_host_for_log("http://127.0.0.1:6123") == "127.0.0.1:6123"
    assert proxy_host_for_log(None) is None


def test_pool_from_dict_and_select(tmp_path: Path) -> None:
    payload = {
        "policy": {
            "deny_countries": ["JP", "KR"],
            "prefer_countries": ["US"],
            "max_risk_score": 90,
        },
        "proxies": [
            {
                "id": "a",
                "url": "http://127.0.0.1:6123",
                "enabled": True,
                "priority": 20,
            },
            {
                "id": "b",
                "url": "http://127.0.0.1:7890",
                "enabled": True,
                "priority": 10,
            },
        ],
        "health": {
            "b": {
                "proxy_id": "b",
                "ok": True,
                "checked_at": "2026-01-01T00:00:00Z",
                "latency_ms": 100,
                "exit_ip": "1.2.3.4",
                "country_code": "US",
                "risk_score": 20,
            }
        },
    }
    pool = ProxyPool.from_dict(payload)
    chosen = pool.select(require_probed=True)
    assert chosen.id == "b"
    path = tmp_path / "pool.json"
    pool.save(path)
    reloaded = ProxyPool.load(path)
    assert reloaded.get("a") is not None
    assert reloaded.summary()[0]["url_host"] == "127.0.0.1:6123"


def test_pool_rejects_socks() -> None:
    with pytest.raises(EgressError, match="socks"):
        ProxyPool.from_dict(
            {
                "proxies": [
                    {"id": "s", "url": "socks5://127.0.0.1:1080"},
                ]
            }
        )


def test_policy_denies_jp_country() -> None:
    pool = ProxyPool.from_dict(
        {
            "policy": {"deny_countries": ["JP", "KR"], "max_risk_score": 90},
            "proxies": [{"id": "x", "url": "http://127.0.0.1:1"}],
            "health": {
                "x": {
                    "proxy_id": "x",
                    "ok": True,
                    "checked_at": "t",
                    "exit_ip": "9.9.9.9",
                    "country_code": "JP",
                    "risk_score": 10,
                }
            },
        }
    )
    proxy = pool.get("x")
    assert proxy is not None
    reason = pool._policy_reject_reason(proxy, pool.health["x"])
    assert reason is not None
    assert "JP" in reason


def test_javdb_compat() -> None:
    snap = MyIPSnapshot(
        mode="proxy",
        proxy_url_host="127.0.0.1:6123",
        consensus_ip="1.1.1.1",
        agreement=2,
        sources=(
            MyIPSourceResult(
                name="a",
                ok=True,
                latency_ms=10,
                ip="1.1.1.1",
                geo="US",
                country_code="US",
                isp=None,
                error=None,
                url_host="x",
            ),
            MyIPSourceResult(
                name="b",
                ok=True,
                latency_ms=10,
                ip="1.1.1.1",
                geo="US",
                country_code="US",
                isp=None,
                error=None,
                url_host="y",
            ),
        ),
        checked_at_ms=0,
    )
    assert javdb_compat(snap)["ok"] is True

    bad = MyIPSnapshot(
        mode="proxy",
        proxy_url_host="h",
        consensus_ip="2.2.2.2",
        agreement=1,
        sources=(
            MyIPSourceResult(
                name="a",
                ok=True,
                latency_ms=1,
                ip="2.2.2.2",
                geo="JP",
                country_code="JP",
                isp=None,
                error=None,
                url_host="x",
            ),
        ),
        checked_at_ms=0,
    )
    assert javdb_compat(bad)["ok"] is False
    assert javdb_compat(None)["ok"] is None


def test_javdb_country_vote_is_deterministic_and_ties_fail_closed() -> None:
    def snapshot(codes: tuple[str, ...]) -> MyIPSnapshot:
        return MyIPSnapshot(
            mode="proxy",
            proxy_url_host="proxy.example:8080",
            consensus_ip="1.1.1.1",
            agreement=len(codes),
            sources=tuple(
                MyIPSourceResult(
                    name=f"source-{index}",
                    ok=True,
                    latency_ms=1,
                    ip="1.1.1.1",
                    geo=code,
                    country_code=code,
                    isp=None,
                    error=None,
                    url_host="probe.example",
                )
                for index, code in enumerate(codes)
            ),
            checked_at_ms=0,
        )

    majority = javdb_compat(snapshot(("US", "JP", "US")))
    assert majority["ok"] is True
    assert majority["country_code"] == "US"
    tied = javdb_compat(snapshot(("US", "JP")))
    assert tied == {
        "ok": None,
        "deny_countries": ["JP", "KR"],
        "country_code": None,
        "message": "country_conflict",
    }


def test_pool_save_is_atomic_and_private(tmp_path: Path) -> None:
    pool = ProxyPool.from_dict(
        {"proxies": [{"id": "only", "url": "http://127.0.0.1:8080"}]}
    )
    path = tmp_path / "pool.json"
    pool.save(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert ProxyPool.load(path).get("only") is not None


def test_quality_probe_is_post_only_and_authenticated(client) -> None:
    assert client.get("/api/egress/probe-quality").status_code == 405
    assert client.post("/api/egress/probe-quality").status_code == 401


def test_authenticated_quality_probe_rejects_get(auth_client) -> None:
    # Authentication is checked before the probe implementation is reached.
    response = auth_client.get("/api/egress/probe-quality")
    assert response.status_code == 405


def test_build_snapshot_mocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    empty_snap = MyIPSnapshot(
        mode="direct",
        proxy_url_host=None,
        consensus_ip="8.8.8.8",
        agreement=1,
        sources=(
            MyIPSourceResult(
                name="ipify",
                ok=True,
                latency_ms=5,
                ip="8.8.8.8",
                geo=None,
                country_code=None,
                isp=None,
                error=None,
                url_host="api.ipify.org",
            ),
        ),
        checked_at_ms=1,
    )

    def fake_probe(*, proxy=None, timeout=5.0, max_workers=6):  # noqa: ANN001
        if proxy:
            return MyIPSnapshot(
                mode="proxy",
                proxy_url_host="127.0.0.1:6123",
                consensus_ip="9.9.9.9",
                agreement=1,
                sources=(
                    MyIPSourceResult(
                        name="ipify",
                        ok=True,
                        latency_ms=20,
                        ip="9.9.9.9",
                        geo="United States",
                        country_code="US",
                        isp=None,
                        error=None,
                        url_host="api.ipify.org",
                    ),
                ),
                checked_at_ms=2,
            )
        return empty_snap

    monkeypatch.setattr("app.egress.service.probe_myip_multi", fake_probe)
    monkeypatch.setattr(
        "app.egress.service.enrich_ipify_with_ipsb",
        lambda s, **kwargs: s,
    )
    monkeypatch.setenv("NSFW_HTTP_PROXY", "http://127.0.0.1:6123")
    monkeypatch.delenv("NSFW_PROXY_POOL_CONFIG", raising=False)

    # Point config path to missing file under tmp
    monkeypatch.setattr(
        "app.egress.service.pool_config_path",
        lambda: tmp_path / "missing-proxy-pool.json",
    )

    payload = build_snapshot(with_quality=False)
    assert payload["ok"] is True
    assert payload["direct"]["consensus_ip"] == "8.8.8.8"
    assert payload["via_proxy"]["consensus_ip"] == "9.9.9.9"
    assert payload["resolved_proxy"] == "127.0.0.1:6123"
    assert payload["javdb"]["ok"] is True
    assert payload["config_exists"] is False


def test_probe_exit_ip_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(url, *, proxy=None, timeout=8.0, headers=None, accept=None):  # noqa: ANN001
        if "ipify" in url:
            return FetchResult(
                ok=True,
                status_code=200,
                body='{"ip":"203.0.113.10"}',
                latency_ms=12,
            )
        return FetchResult(ok=False, status_code=None, body="", latency_ms=1, error="skip")

    monkeypatch.setattr(pool_mod, "fetch_text", fake_fetch)
    assert pool_mod.probe_exit_ip("http://127.0.0.1:6123") == "203.0.113.10"


def test_pool_config_path_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "custom.json"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("NSFW_PROXY_POOL_CONFIG", str(target))
    assert pool_config_path() == target


def test_resolve_proxy_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSFW_HTTP_PROXY", "http://127.0.0.1:9999")
    assert resolve_proxy_url() == "http://127.0.0.1:9999"
    assert resolve_proxy_url("http://explicit:1") == "http://explicit:1"
