"""Authenticated Provider Runtime Registry pages and explicit POST controls."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import is_authenticated, require_page_auth
from app.database import get_db
from app.flash import add_flash, pop_flash_messages
from app.i18n import get_language, translator
from app.provider_runtime.service import (
    ProviderRuntimeError,
    ProviderRuntimeRegistry,
    ProviderRuntimeView,
)
from app.provider_runtime.catalog import run_runtime_health_check


router = APIRouter(tags=["provider-runtime"])
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


def _registry(db: Session) -> ProviderRuntimeRegistry:
    return ProviderRuntimeRegistry(db)


def _failure(request: Request, provider_key: str, error: ProviderRuntimeError | None = None) -> RedirectResponse:
    del error
    add_flash(request, "error", "flash.provider_runtime_failed")
    return RedirectResponse(f"/providers/{quote(provider_key, safe='_-')}", status_code=303)


@router.get(
    "/providers",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def providers_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "providers.html",
        _context(request, providers=_registry(db).list()),
    )


@router.get(
    "/providers/{provider_key}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def provider_detail_page(
    request: Request,
    provider_key: str,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        provider = _registry(db).get(provider_key)
    except ProviderRuntimeError:
        raise HTTPException(status_code=404, detail="provider not found") from None
    return templates.TemplateResponse(
        request,
        "provider_detail.html",
        _context(request, provider=provider, egress_profiles=("default", "direct", "proxy_pool")),
    )


def _parse_version(value: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


@router.post(
    "/providers/{provider_key}/configuration",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
def save_provider_configuration(
    request: Request,
    provider_key: str,
    egress_profile: str = Form(default=""),
    optimistic_version: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        _registry(db).save_configuration(
            provider_key,
            egress_profile=egress_profile,
            expected_version=_parse_version(optimistic_version),
        )
        db.commit()
    except ProviderRuntimeError as error:
        db.rollback()
        return _failure(request, provider_key, error)
    add_flash(request, "success", "flash.provider_runtime_saved")
    return RedirectResponse(f"/providers/{quote(provider_key, safe='_-')}", status_code=303)


def _set_provider_enabled(
    request: Request,
    provider_key: str,
    optimistic_version: str,
    *,
    enabled: bool,
    db: Session,
) -> RedirectResponse:
    try:
        _registry(db).set_enabled(
            provider_key,
            enabled=enabled,
            expected_version=_parse_version(optimistic_version),
        )
        db.commit()
    except ProviderRuntimeError as error:
        db.rollback()
        return _failure(request, provider_key, error)
    add_flash(request, "success", "flash.provider_runtime_saved")
    return RedirectResponse(f"/providers/{quote(provider_key, safe='_-')}", status_code=303)


@router.post(
    "/providers/{provider_key}/enable",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
def enable_provider(
    request: Request,
    provider_key: str,
    optimistic_version: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return _set_provider_enabled(
        request, provider_key, optimistic_version, enabled=True, db=db
    )


@router.post(
    "/providers/{provider_key}/disable",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
def disable_provider(
    request: Request,
    provider_key: str,
    optimistic_version: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return _set_provider_enabled(
        request, provider_key, optimistic_version, enabled=False, db=db
    )


@router.post(
    "/providers/{provider_key}/health-check",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
async def provider_health_check(
    request: Request,
    provider_key: str,
    optimistic_version: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        await run_runtime_health_check(
            db,
            provider_key, expected_version=_parse_version(optimistic_version)
        )
        db.commit()
    except ProviderRuntimeError as error:
        db.rollback()
        return _failure(request, provider_key, error)
    add_flash(request, "success", "flash.provider_runtime_health_checked")
    return RedirectResponse(f"/providers/{quote(provider_key, safe='_-')}", status_code=303)


@router.post(
    "/providers/{provider_key}/clear-error",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
def clear_provider_error(
    request: Request,
    provider_key: str,
    optimistic_version: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        _registry(db).clear_error(
            provider_key, expected_version=_parse_version(optimistic_version)
        )
        db.commit()
    except ProviderRuntimeError as error:
        db.rollback()
        return _failure(request, provider_key, error)
    add_flash(request, "success", "flash.provider_runtime_error_cleared")
    return RedirectResponse(f"/providers/{quote(provider_key, safe='_-')}", status_code=303)


def provider_runtime_views(db: Session) -> tuple[ProviderRuntimeView, ...]:
    """Small read-only dependency for diagnostics and other pages."""

    return _registry(db).list()
