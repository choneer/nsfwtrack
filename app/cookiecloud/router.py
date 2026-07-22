"""Authenticated CookieCloud UI + import/status APIs (control plane)."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.auth import is_authenticated, require_api_auth, require_page_auth
from app.config import get_settings
from app.cookiecloud.client import (
    CookieCloudConfig,
    CookieCloudError,
    CookieCloudImporter,
    default_cookie_store_path,
)
from app.i18n import get_language, translator
from app.providers.javdb.production import JAVDB_PRODUCTION_HOST
from app.providers.javdb.session import SessionCookieError, load_javdb_session_cookie
from app.providers.readiness import build_catalog_readiness


router = APIRouter(tags=["cookiecloud"])
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


def _flash_list(request: Request) -> list[dict[str, str]]:
    # Session flash optional; page also shows inline result.
    raw = request.session.pop("cookiecloud_flash", None)
    if isinstance(raw, dict) and raw.get("kind") and raw.get("message"):
        return [{"kind": str(raw["kind"]), "message": str(raw["message"])}]
    return []


class CookieCloudImportBody(BaseModel):
    host: str = Field(..., min_length=8, max_length=512)
    uuid: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=512)
    provider_key: str = Field(default="javdb_metadata", max_length=64)
    cookie_names: list[str] | None = None
    save: bool = True


@router.get(
    "/cookiecloud",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def cookiecloud_page(request: Request) -> HTMLResponse:
    """Operator UI: status, readiness, and import form (never shows secrets)."""

    readiness = build_catalog_readiness(application_version="1.5.0")
    path = default_cookie_store_path("javdb_metadata")
    env_set = bool(
        os.environ.get("NSFWTRACK_JAVDB_SESSION_COOKIE")
        or os.environ.get("NSFWTRACK_JAVDB_SESSION_COOKIE_FILE")
    )
    file_ok = path.is_file() and path.stat().st_size > 0
    loadable = False
    try:
        load_javdb_session_cookie()
        loadable = True
    except SessionCookieError:
        loadable = False
    return templates.TemplateResponse(
        request,
        "cookiecloud.html",
        _page_context(
            request,
            flash_messages=_flash_list(request),
            readiness=readiness.to_dict(),
            status={
                "env_configured": env_set,
                "file_configured": file_ok,
                "file_path": str(path),
                "loadable": loadable,
            },
            import_result=None,
            form_defaults={
                "host": "http://127.0.0.1:8088",
                "uuid": "",
                "provider_key": "javdb_metadata",
                "save": True,
            },
        ),
    )


@router.post(
    "/cookiecloud/import",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def cookiecloud_page_import(
    request: Request,
    host: str = Form(...),
    uuid: str = Form(...),
    password: str = Form(...),
    provider_key: str = Form("javdb_metadata"),
    save: str = Form("1"),
) -> HTMLResponse:
    """HTML form import; never renders password or cookie values."""

    save_flag = save in {"1", "true", "on", "yes"}
    result: dict[str, Any]
    try:
        result = _do_import(
            host=host,
            uuid=uuid,
            password=password,
            provider_key=provider_key,
            cookie_names=None,
            save=save_flag,
        )
        kind = "success" if result.get("ok") else "error"
        msg = (
            f"imported {result.get('matched_count', 0)} cookies"
            if result.get("ok")
            else str(result.get("error") or "import failed")
        )
        request.session["cookiecloud_flash"] = {"kind": kind, "message": msg}
    except CookieCloudError as exc:
        result = {"ok": False, "error": str(exc)}
        request.session["cookiecloud_flash"] = {
            "kind": "error",
            "message": str(exc),
        }
    # PRG so refresh does not re-post password
    return RedirectResponse(url="/cookiecloud", status_code=303)


@router.post("/api/cookiecloud/import", dependencies=[Depends(require_api_auth)])
def cookiecloud_import(body: CookieCloudImportBody) -> JSONResponse:
    """Import cookies for an approved provider host; optionally persist header."""

    try:
        payload = _do_import(
            host=body.host,
            uuid=body.uuid,
            password=body.password,
            provider_key=body.provider_key,
            cookie_names=body.cookie_names,
            save=body.save,
        )
        status = 200 if payload.get("ok") else 400
        return JSONResponse(
            payload,
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )
    except CookieCloudError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc)},
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )


@router.get("/api/cookiecloud/status", dependencies=[Depends(require_api_auth)])
def cookiecloud_status(provider_key: str = "javdb_metadata") -> JSONResponse:
    """Whether a local cookie file / env is configured (never returns values)."""

    path = default_cookie_store_path(provider_key)
    env_set = bool(
        os.environ.get("NSFWTRACK_JAVDB_SESSION_COOKIE")
        or os.environ.get("NSFWTRACK_JAVDB_SESSION_COOKIE_FILE")
    )
    file_ok = path.is_file() and path.stat().st_size > 0
    loadable = False
    try:
        load_javdb_session_cookie()
        loadable = True
    except SessionCookieError:
        loadable = False
    return JSONResponse(
        {
            "ok": True,
            "provider_key": provider_key,
            "env_configured": env_set,
            "file_configured": file_ok,
            "file_path": str(path),
            "loadable": loadable,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/providers/readiness", dependencies=[Depends(require_api_auth)])
def providers_readiness() -> JSONResponse:
    """Catalog readiness for default providers (no secrets)."""

    snap = build_catalog_readiness(application_version="1.5.0")
    return JSONResponse(snap.to_dict(), headers={"Cache-Control": "no-store"})


def _do_import(
    *,
    host: str,
    uuid: str,
    password: str,
    provider_key: str,
    cookie_names: list[str] | None,
    save: bool,
) -> dict[str, Any]:
    hosts = _hosts_for_provider(provider_key)
    names = set(cookie_names) if cookie_names else None
    if names is None and provider_key in {"javdb_metadata", "javdb"}:
        names = {"_jdb_session", "list_lang", "theme", "locale", "over18"}

    config = CookieCloudConfig(host=host, uuid=uuid)
    importer = CookieCloudImporter(
        config,
        proxy=os.environ.get("NSFWTRACK_HTTP_PROXY")
        or os.environ.get("NSFW_HTTP_PROXY"),
    )
    save_path = default_cookie_store_path(provider_key) if save else None
    header, matched = importer.import_cookie_header(
        password,
        hosts=hosts,
        cookie_names=names,
        save_path=save_path,
    )
    return {
        "ok": True,
        "provider_key": provider_key,
        "matched_cookie_names": list(matched),
        "matched_count": len(matched),
        "saved": bool(save_path),
        "save_path": str(save_path) if save_path else None,
        "header_length": len(header),
    }


def _hosts_for_provider(provider_key: str) -> set[str]:
    key = (provider_key or "").strip().lower()
    if key in {"javdb_metadata", "javdb"}:
        return {JAVDB_PRODUCTION_HOST, "www.javdb.com"}
    if key in {"zuidapi_vod", "zuidapi"}:
        return {"api.zuidapi.com"}
    if key in {"copymanga"}:
        return {"api.mangacopy.com", "site.mangacopy.com"}
    if key in {"jiuse_vod", "jiuse"}:
        return {"jiuse.io", "cdn2.jiuse2.cloud"}
    raise CookieCloudError(f"unsupported provider_key for CookieCloud: {provider_key}")
