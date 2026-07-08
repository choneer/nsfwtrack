from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from app.config import get_settings


SESSION_AUTH_KEY = "is_authenticated"


def verify_password(password: str) -> bool:
    settings = get_settings()
    return secrets.compare_digest(password, settings.app_password)


def login_user(request: Request) -> None:
    request.session[SESSION_AUTH_KEY] = True


def logout_user(request: Request) -> None:
    language = request.session.get("ui_language")
    request.session.clear()
    if language:
        request.session["ui_language"] = language


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get(SESSION_AUTH_KEY))


def require_api_auth(request: Request) -> bool:
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return True


def require_page_auth(request: Request) -> bool:
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
            detail="Authentication required",
        )
    return True
