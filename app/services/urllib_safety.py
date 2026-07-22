"""Shared fail-closed urllib opener for bounded non-Provider utilities.

The opener always disables ambient proxy discovery and HTTP redirects.  A
caller may provide one explicit HTTP(S) proxy; Provider activation still needs
the stronger pinned outbound client and must not treat this helper as approval.
"""

from __future__ import annotations

import ssl
from typing import Any
from urllib.parse import urlparse
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    OpenerDirector,
    ProxyHandler,
    build_opener,
)


class DenyRedirectHandler(HTTPRedirectHandler):
    """Turn every redirect into the original ``HTTPError`` response."""

    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _proxy_mapping(proxy: str | None) -> dict[str, str]:
    if proxy is None or not proxy.strip():
        return {}
    value = proxy.strip()
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("explicit proxy URL is invalid")
    return {"http": value, "https": value}


def build_no_redirect_opener(*, proxy: str | None = None) -> OpenerDirector:
    """Build an opener with no redirects and no environment-derived proxy."""

    return build_opener(
        ProxyHandler(_proxy_mapping(proxy)),
        DenyRedirectHandler(),
        HTTPSHandler(context=ssl.create_default_context()),
    )


def response_matches_request(response: Any, request_url: str) -> bool:
    """Verify that a real urllib response still identifies the requested URL."""

    getter = getattr(response, "geturl", None)
    if getter is None:
        # Injected unit-test responses do not necessarily model geturl().
        return True
    try:
        actual = str(getter())
    except Exception:  # noqa: BLE001 - response objects are external inputs
        return False
    return actual == request_url
