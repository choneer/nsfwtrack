"""Server-rendered HLS inspection page; parsing only, never network fetches."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import is_authenticated, require_page_auth
from app.database import get_db
from app.i18n import get_language, translator
from app.playback.hls import PlaybackError, parse_hls_manifest
from app.playback.router import _local_media_association


router = APIRouter(tags=["playback"])
templates = Jinja2Templates(directory="app/templates")


def _context(request: Request, **values: object) -> dict[str, object]:
    language = get_language(request)
    return {
        "request": request,
        "authenticated": is_authenticated(request),
        "lang": language,
        "current_path": quote(request.url.path, safe="/"),
        "t": translator(language),
        **values,
    }


@router.get("/playback", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def playback_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "playback.html",
        _context(request, result=None, error=None, form={}),
    )


@router.post(
    "/playback/hls/inspect",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def playback_hls_inspect_page(
    request: Request,
    manifest_text: str = Form(...),
    base_url: str = Form(...),
    approved_hosts: str = Form(...),
    local_asset_id: str = Form(default=""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Inspect supplied text only; no manifest, variant, key, or segment is fetched."""

    form = {
        "manifest_text": manifest_text,
        "base_url": base_url,
        "approved_hosts": approved_hosts,
        "local_asset_id": local_asset_id,
    }
    try:
        hosts = {host.strip().lower() for host in approved_hosts.split(",") if host.strip()}
        if not hosts:
            raise PlaybackError("at least one approved HLS host is required")
        asset_id = int(local_asset_id) if local_asset_id.strip() else None
        if asset_id is not None and asset_id < 1:
            raise PlaybackError("local media association is invalid")
        manifest = parse_hls_manifest(
            manifest_text,
            base_url=base_url,
            approved_hosts=hosts,
        ).to_dict()
        return templates.TemplateResponse(
            request,
            "playback.html",
            _context(
                request,
                result={
                    "manifest": manifest,
                    "local_media_association": _local_media_association(db, asset_id),
                },
                error=None,
                form=form,
            ),
        )
    except (PlaybackError, ValueError):
        return templates.TemplateResponse(
            request,
            "playback.html",
            _context(request, result=None, error="playback.inspect_failed", form=form),
            status_code=400,
        )
