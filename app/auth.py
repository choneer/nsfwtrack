from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from app.config import get_settings


SESSION_AUTH_KEY = "is_authenticated"
SESSION_GENERATION_KEY = "session_generation"


def verify_password(password: str) -> bool:
    settings = get_settings()
    return secrets.compare_digest(password, settings.app_password)


def login_user(request: Request) -> None:
    language = request.session.get("ui_language")
    request.session.clear()
    if language:
        request.session["ui_language"] = language
    request.session[SESSION_AUTH_KEY] = True
    request.session[SESSION_GENERATION_KEY] = request.app.state.session_generation


def logout_user(request: Request) -> None:
    language = request.session.get("ui_language")
    request.app.state.session_generation = secrets.token_hex(32)
    request.session.clear()
    if language:
        request.session["ui_language"] = language


def is_authenticated(request: Request) -> bool:
    session_generation = request.session.get(SESSION_GENERATION_KEY)
    current_generation = getattr(request.app.state, "session_generation", "")
    return (
        bool(request.session.get(SESSION_AUTH_KEY))
        and isinstance(session_generation, str)
        and bool(current_generation)
        and secrets.compare_digest(session_generation, current_generation)
    )


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
