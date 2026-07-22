"""Authenticated egress diagnostics page + JSON APIs."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.auth import is_authenticated, require_api_auth, require_page_auth
from app.config import get_settings
from app.i18n import get_language, translator
from app.egress.service import build_snapshot, pool_config_path


router = APIRouter(tags=["egress"])
templates = Jinja2Templates(directory="app/templates")


def _page_context(request: Request, **values: Any) -> dict[str, Any]:
    language = get_language(request)
    current_path = request.url.path
    if request.url.query:
        current_path = f"{current_path}?{request.url.query}"
    context = {
        "request": request,
        "authenticated": is_authenticated(request),
        "lang": language,
        "current_url_path": current_path,
        "current_path": quote(current_path, safe="/"),
        "t": translator(language),
        "flash_messages": [],
        "max_backup_upload_mb": get_settings().max_backup_upload_mb,
        "max_import_upload_mb": get_settings().max_import_upload_mb,
    }
    context.update(values)
    return context


@router.get(
    "/egress",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def egress_page(request: Request) -> HTMLResponse:
    path = pool_config_path()
    return templates.TemplateResponse(
        request,
        "egress.html",
        _page_context(
            request,
            config_path=str(path),
            config_exists=path.is_file(),
        ),
    )


@router.get(
    "/api/egress/status",
    dependencies=[Depends(require_api_auth)],
)
def egress_status() -> JSONResponse:
    try:
        payload = build_snapshot(with_quality=False)
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})
    except Exception:  # noqa: BLE001 - return a stable redacted failure
        return JSONResponse(
            {"ok": False, "error": "egress status failed"},
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )


@router.post(
    "/api/egress/probe-quality",
    dependencies=[Depends(require_api_auth)],
)
def egress_probe_quality() -> JSONResponse:
    try:
        payload = build_snapshot(with_quality=True)
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})
    except Exception:  # noqa: BLE001 - return a stable redacted failure
        return JSONResponse(
            {"ok": False, "error": "egress probe failed"},
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )
