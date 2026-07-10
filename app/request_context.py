from __future__ import annotations

import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 64

_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_SAFE_METHOD_PATTERN = re.compile(r"[A-Z]{1,16}")
_SENSITIVE_PATH_MARKERS = {
    "authorization",
    "cookie",
    "passwd",
    "password",
    "secret",
    "session",
    "token",
}

request_id_context: ContextVar[str | None] = ContextVar(
    "nsfwtrack_request_id",
    default=None,
)
logger = logging.getLogger("uvicorn.error.nsfwtrack.request")


def configure_request_logging() -> None:
    # Uvicorn's access logger includes the raw query string. The application
    # request log below deliberately records only a sanitized path.
    logging.getLogger("uvicorn.access").disabled = True


def is_valid_request_id(value: str | None) -> bool:
    if value is None or len(value) > MAX_REQUEST_ID_LENGTH:
        return False
    return _REQUEST_ID_PATTERN.fullmatch(value) is not None


def resolve_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    if is_valid_request_id(candidate):
        return candidate
    return uuid.uuid4().hex


def get_request_id(scope: Scope) -> str:
    state = scope.get("state")
    if isinstance(state, dict):
        value = state.get("request_id")
        if isinstance(value, str) and is_valid_request_id(value):
            return value
    return resolve_request_id(None)


def _safe_method(scope: Scope) -> str:
    method = str(scope.get("method", "")).upper()
    if _SAFE_METHOD_PATTERN.fullmatch(method):
        return method
    return "UNKNOWN"


def _redact_path(path: str) -> str:
    segments = path.split("/")
    redact_next = False
    safe_segments: list[str] = []
    for segment in segments:
        if redact_next:
            safe_segments.append("[redacted]")
            redact_next = False
            continue
        marker, separator, _ = segment.partition("=")
        if marker.casefold() in _SENSITIVE_PATH_MARKERS:
            safe_segments.append(f"{marker}=[redacted]" if separator else marker)
            redact_next = not separator
            continue
        if len(segment) > 128:
            safe_segments.append("[redacted]")
            continue
        safe_segments.append(segment)
    return "/".join(safe_segments)


def _safe_log_path(scope: Scope) -> str:
    route = scope.get("route")
    route_path = getattr(route, "path", None)
    path = route_path if isinstance(route_path, str) else str(scope.get("path", "/"))
    cleaned = _CONTROL_CHARACTER_PATTERN.sub("_", path)
    return _redact_path(cleaned)[:512] or "/"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = resolve_request_id(headers.get(REQUEST_ID_HEADER))
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        context_token = request_id_context.set(request_id)
        started_at = time.perf_counter()
        status_code = 500
        exception_type: str | None = None
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                response_headers = MutableHeaders(scope=message)
                response_headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            exception_type = type(exc).__name__
            if response_started:
                raise
            from app.errors import unhandled_exception_handler

            response = await unhandled_exception_handler(Request(scope), exc)
            await response(scope, receive, send_with_request_id)
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            log_method = logger.error if exception_type else logger.info
            message = (
                "request_complete request_id=%s method=%s path=%s "
                "status=%d duration_ms=%.3f"
            )
            values: tuple[object, ...] = (
                request_id,
                _safe_method(scope),
                _safe_log_path(scope),
                status_code,
                duration_ms,
            )
            if exception_type:
                message += " exception_type=%s"
                values += (exception_type,)
            log_method(message, *values)
            request_id_context.reset(context_token)
