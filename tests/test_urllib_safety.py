"""Regression tests for the shared stdlib HTTP fail-closed boundary."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from app.services.urllib_safety import build_no_redirect_opener


def test_redirect_is_blocked_before_cookie_reaches_second_origin() -> None:
    received: list[str | None] = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            received.append(self.headers.get("Cookie"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return None

    target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
    target_thread = threading.Thread(target=target.serve_forever, daemon=True)
    target_thread.start()

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(302)
            self.send_header(
                "Location", f"http://127.0.0.1:{target.server_port}/capture"
            )
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return None

    redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    redirect_thread = threading.Thread(target=redirect.serve_forever, daemon=True)
    redirect_thread.start()
    try:
        request = Request(
            f"http://127.0.0.1:{redirect.server_port}/start",
            headers={"Cookie": "session=must-not-leak"},
        )
        with pytest.raises(HTTPError) as exc_info:
            build_no_redirect_opener().open(request, timeout=2)
        assert exc_info.value.code == 302
        assert received == []
    finally:
        redirect.shutdown()
        target.shutdown()
        redirect.server_close()
        target.server_close()
        redirect_thread.join(timeout=2)
        target_thread.join(timeout=2)


def test_environment_proxy_discovery_is_never_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "urllib.request.getproxies",
        lambda: (_ for _ in ()).throw(AssertionError("ambient proxy consulted")),
    )
    build_no_redirect_opener()
