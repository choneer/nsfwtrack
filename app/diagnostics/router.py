"""Authenticated diagnostic page and no-store redacted JSON export."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import is_authenticated, require_api_auth, require_page_auth
from app.database import get_db
from app.flash import pop_flash_messages
from app.i18n import get_language, translator
from app.diagnostics.service import build_diagnostics_snapshot


router = APIRouter(tags=["diagnostics"])
templates = Jinja2Templates(directory="app/templates")


def _context(request: Request, **values: object) -> dict[str, object]:
    language = get_language(request)
    return {
        "request": request,
        "authenticated": is_authenticated(request),
        "lang": language,
        "current_path": quote(request.url.path, safe="/"),
        "t": translator(language),
        "flash_messages": pop_flash_messages(request, language),
        **values,
    }


@router.get(
    "/diagnostics",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def diagnostics_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    snapshot = build_diagnostics_snapshot(db)
    return templates.TemplateResponse(
        request,
        "diagnostics.html",
        _context(request, snapshot=snapshot.to_dict()),
    )


@router.get(
    "/api/diagnostics/report",
    dependencies=[Depends(require_api_auth)],
)
def diagnostics_report(db: Session = Depends(get_db)) -> JSONResponse:
    return JSONResponse(
        {"ok": True, "report": build_diagnostics_snapshot(db).to_dict()},
        headers={"Cache-Control": "no-store"},
    )
