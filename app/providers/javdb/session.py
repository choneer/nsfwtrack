"""Operator session cookie loader for JavDB (no secrets in code).

Sources (first match wins):
1. ``NSFWTRACK_JAVDB_SESSION_COOKIE`` env (raw Cookie header value)
2. File path in ``NSFWTRACK_JAVDB_SESSION_COOKIE_FILE`` (single line)

Never logs cookie values.
"""

from __future__ import annotations

import os
from pathlib import Path


class SessionCookieError(RuntimeError):
    """Cookie missing or invalid for operator configuration."""


def load_javdb_session_cookie(
    *,
    explicit: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Return a non-empty Cookie header value (name=value pairs)."""

    if explicit is not None:
        value = explicit.strip()
        if not value:
            raise SessionCookieError("explicit session cookie is empty")
        _reject_control_chars(value)
        return value

    environ = env if env is not None else os.environ
    raw = (environ.get("NSFWTRACK_JAVDB_SESSION_COOKIE") or "").strip()
    if raw:
        _reject_control_chars(raw)
        return raw

    path_raw = (environ.get("NSFWTRACK_JAVDB_SESSION_COOKIE_FILE") or "").strip()
    if path_raw:
        path = Path(path_raw)
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SessionCookieError("session cookie file unreadable") from exc
        if not text:
            raise SessionCookieError("session cookie file is empty")
        # First non-empty line only
        line = next((part.strip() for part in text.splitlines() if part.strip()), "")
        if not line:
            raise SessionCookieError("session cookie file is empty")
        _reject_control_chars(line)
        return line

    # CookieCloud / manual import drop zone (never logged).
    from app.cookiecloud.client import default_cookie_store_path

    for candidate in (
        default_cookie_store_path("javdb_metadata"),
        default_cookie_store_path("javdb"),
    ):
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            line = next(
                (part.strip() for part in text.splitlines() if part.strip()), ""
            )
            if line:
                _reject_control_chars(line)
                return line

    raise SessionCookieError(
        "set NSFWTRACK_JAVDB_SESSION_COOKIE, "
        "NSFWTRACK_JAVDB_SESSION_COOKIE_FILE, or import via CookieCloud"
    )


def _reject_control_chars(value: str) -> None:
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise SessionCookieError("session cookie contains control characters")
