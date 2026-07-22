"""Local egress diagnostics: multi-source MyIP + proxy pool quality.

Self-contained admin tooling for Provider outbound (e.g. avoid JP/KR for JavDB).
Does not touch production Provider registries or outbound allowlists.
"""

from __future__ import annotations

from app.egress.service import build_snapshot, pool_config_path, resolve_proxy_url

__all__ = [
    "build_snapshot",
    "pool_config_path",
    "resolve_proxy_url",
]
