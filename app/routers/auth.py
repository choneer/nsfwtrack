from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response

from app.auth import login_user, logout_user, require_api_auth, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _read_password(request: Request) -> tuple[str, bool]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
        return str(payload.get("password", "")), False
    form = await request.form()
    return str(form.get("password", "")), True


@router.post("/login")
async def login(request: Request) -> Response:
    password, from_form = await _read_password(request)
    if not verify_password(password):
        if from_form:
            return RedirectResponse("/login?error=1", status_code=status.HTTP_303_SEE_OTHER)
        return JSONResponse(
            {"detail": "Invalid password"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    login_user(request)
    if from_form:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return JSONResponse({"ok": True})


@router.post("/logout", dependencies=[Depends(require_api_auth)])
async def logout(request: Request) -> JSONResponse:
    logout_user(request)
    return JSONResponse({"ok": True})
