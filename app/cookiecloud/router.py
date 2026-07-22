"""Authenticated CookieCloud import API (control plane, not a Provider)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import require_api_auth
from app.cookiecloud.client import (
    CookieCloudConfig,
    CookieCloudError,
    CookieCloudImporter,
    default_cookie_store_path,
)
from app.providers.javdb.production import JAVDB_PRODUCTION_HOST
from app.providers.javdb.session import load_javdb_session_cookie, SessionCookieError


router = APIRouter(prefix="/api/cookiecloud", tags=["cookiecloud"])


class CookieCloudImportBody(BaseModel):
    host: str = Field(..., min_length=8, max_length=512)
    uuid: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=512)
    provider_key: str = Field(default="javdb_metadata", max_length=64)
    cookie_names: list[str] | None = None
    save: bool = True


@router.post("/import", dependencies=[Depends(require_api_auth)])
def cookiecloud_import(body: CookieCloudImportBody) -> JSONResponse:
    """Import cookies for an approved provider host; optionally persist header."""

    hosts = _hosts_for_provider(body.provider_key)
    names = set(body.cookie_names) if body.cookie_names else None
    # JavDB common session cookie names when allowlist not provided
    if names is None and body.provider_key in {"javdb_metadata", "javdb"}:
        names = {"_jdb_session", "list_lang", "theme", "locale", "over18"}

    try:
        config = CookieCloudConfig(host=body.host, uuid=body.uuid)
        importer = CookieCloudImporter(
            config,
            proxy=os.environ.get("NSFWTRACK_HTTP_PROXY")
            or os.environ.get("NSFW_HTTP_PROXY"),
        )
        save_path = (
            default_cookie_store_path(body.provider_key) if body.save else None
        )
        header, matched = importer.import_cookie_header(
            body.password,
            hosts=hosts,
            cookie_names=names,
            save_path=save_path,
        )
        # Never return cookie values — only names + count + save path.
        return JSONResponse(
            {
                "ok": True,
                "provider_key": body.provider_key,
                "matched_cookie_names": list(matched),
                "matched_count": len(matched),
                "saved": bool(save_path),
                "save_path": str(save_path) if save_path else None,
                "header_length": len(header),
            },
            headers={"Cache-Control": "no-store"},
        )
    except CookieCloudError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc)},
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )


@router.get("/status", dependencies=[Depends(require_api_auth)])
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


def _hosts_for_provider(provider_key: str) -> set[str]:
    key = (provider_key or "").strip().lower()
    if key in {"javdb_metadata", "javdb"}:
        return {JAVDB_PRODUCTION_HOST, "www.javdb.com"}
    if key in {"zuidapi_vod", "zuidapi"}:
        return {"api.zuidapi.com"}
    if key in {"jiuse_vod", "jiuse"}:
        return {"jiuse.io", "cdn2.jiuse2.cloud"}
    raise CookieCloudError(f"unsupported provider_key for CookieCloud: {provider_key}")
