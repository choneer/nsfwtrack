from __future__ import annotations

from urllib.parse import unquote, urlsplit

from fastapi import HTTPException, Request, status

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _normalized_origin(value: str, *, allow_path: bool) -> tuple[str, str, int] | None:
    if not value or any(ord(character) < 32 for character in value):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    if (
        scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or (not allow_path and parsed.path not in {"", "/"})
        or (not allow_path and (parsed.query or parsed.fragment))
    ):
        return None
    return scheme, hostname, port or (443 if scheme == "https" else 80)


def require_same_origin(request: Request) -> None:
    if request.method.upper() in SAFE_METHODS:
        return

    expected = _normalized_origin(str(request.base_url), allow_path=True)
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    supplied = origin if origin is not None else referer
    if supplied is None:
        return
    actual = _normalized_origin(supplied, allow_path=origin is None)
    if actual is None or actual != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-origin state-changing request rejected",
        )


def safe_local_path(value: str | None, *, fallback: str) -> str:
    if not value:
        return fallback
    decoded = unquote(value)
    if (
        not decoded.startswith("/")
        or decoded.startswith("//")
        or "\\" in decoded
        or any(ord(character) < 32 for character in decoded)
    ):
        return fallback
    parsed = urlsplit(decoded)
    if parsed.scheme or parsed.netloc:
        return fallback
    return value
