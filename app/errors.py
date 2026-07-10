from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import SESSION_AUTH_KEY
from app.i18n import LANG_SESSION_KEY, normalize_language, translate, translator
from app.request_context import REQUEST_ID_HEADER, get_request_id

templates = Jinja2Templates(directory="app/templates")

_STATUS_CODES = {
    400: "bad_request",
    401: "authentication_required",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    500: "internal_server_error",
}
_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_TRACEBACK_PATTERN = re.compile(r"Traceback \(most recent call last\)|File \".+\", line \d+")
_SERVER_PATH_PATTERN = re.compile(
    r"(?:^|\s)(?:/home/|/root/|/app/|/tmp/|/var/|/etc/|[A-Za-z]:\\)"
)
_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(?:authorization|cookie|database_url|password|secret|session|token)"
    r"\s*[:=]\s*\S+"
)
_TOKEN_PATTERN = re.compile(r"(?:github_pat_|ghp_)[A-Za-z0-9_]+")
_SQL_PATTERN = re.compile(
    r"(?is)\b(?:select\s+.+\s+from|insert\s+into|update\s+.+\s+set|"
    r"delete\s+from|pragma\s+)\b"
)


def wants_json_response(request: Request) -> bool:
    path = request.url.path
    if path == "/api" or path.startswith("/api/"):
        return True
    accept = request.headers.get("accept", "").casefold()
    accepts_json = "application/json" in accept or "+json" in accept
    return accepts_json and "text/html" not in accept


def _error_code(status_code: int) -> str:
    return _STATUS_CODES.get(status_code, "http_error")


def _language(request: Request) -> str:
    session = request.scope.get("session")
    if isinstance(session, dict):
        value = session.get(LANG_SESSION_KEY)
        return normalize_language(str(value) if value is not None else None)
    return normalize_language(None)


def _generic_message(request: Request, status_code: int) -> str:
    return translate(_language(request), f"error.{_error_code(status_code)}.message")


def _safe_public_message(detail: Any, fallback: str) -> str:
    if not isinstance(detail, str):
        return fallback
    message = detail.strip()
    if not message or len(message) > 512:
        return fallback
    if _CONTROL_CHARACTER_PATTERN.search(message):
        return fallback
    if any(
        pattern.search(message)
        for pattern in (
            _TRACEBACK_PATTERN,
            _SERVER_PATH_PATTERN,
            _CREDENTIAL_PATTERN,
            _TOKEN_PATTERN,
            _SQL_PATTERN,
        )
    ):
        return fallback
    return message


def _response_headers(
    request_id: str,
    headers: dict[str, str] | None = None,
) -> dict[str, str]:
    response_headers = dict(headers or {})
    response_headers[REQUEST_ID_HEADER] = request_id
    return response_headers


def _json_error_response(
    request: Request,
    *,
    status_code: int,
    message: str,
    detail: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = get_request_id(request.scope)
    content: dict[str, Any] = {
        "error": _error_code(status_code),
        "message": message,
        "request_id": request_id,
    }
    if detail is not None:
        content["detail"] = detail
    return JSONResponse(
        content,
        status_code=status_code,
        headers=_response_headers(request_id, headers),
    )


def _html_error_response(
    request: Request,
    *,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    request_id = get_request_id(request.scope)
    language = _language(request)
    session = request.scope.get("session")
    authenticated = bool(
        isinstance(session, dict) and session.get(SESSION_AUTH_KEY)
    )
    current_path = quote(request.url.path, safe="/")
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "authenticated": authenticated,
            "lang": language,
            "current_path": current_path,
            "flash_messages": [],
            "t": translator(language),
            "status_code": status_code,
            "error_code": _error_code(status_code),
            "request_id": request_id,
        },
        status_code=status_code,
        headers=_response_headers(request_id, headers),
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> Response:
    headers = dict(exc.headers or {})
    if 300 <= exc.status_code < 400:
        request_id = get_request_id(request.scope)
        return Response(
            status_code=exc.status_code,
            headers=_response_headers(request_id, headers),
        )

    if wants_json_response(request):
        generic_message = _generic_message(request, exc.status_code)
        message = _safe_public_message(exc.detail, generic_message)
        return _json_error_response(
            request,
            status_code=exc.status_code,
            message=message,
            detail=message,
            headers=headers,
        )
    return _html_error_response(
        request,
        status_code=exc.status_code,
        headers=headers,
    )


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    safe_errors: list[dict[str, Any]] = []
    for error in exc.errors():
        safe_error: dict[str, Any] = {}
        for key in ("type", "loc", "msg"):
            value = error.get(key)
            if value is not None:
                safe_error[key] = value
        safe_errors.append(safe_error)
    return safe_errors


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> Response:
    if wants_json_response(request):
        return _json_error_response(
            request,
            status_code=422,
            message=_generic_message(request, 422),
            detail=_safe_validation_errors(exc),
        )
    return _html_error_response(request, status_code=422)


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    del exc
    if wants_json_response(request):
        return _json_error_response(
            request,
            status_code=500,
            message=_generic_message(request, 500),
        )
    return _html_error_response(request, status_code=500)


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
