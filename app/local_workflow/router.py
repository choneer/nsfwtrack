from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import is_authenticated, require_page_auth
from app.config import get_settings
from app.database import get_db
from app.flash import add_flash, pop_flash_messages
from app.i18n import get_language, translator
from app.local_workflow.service import (
    LocalWorkflowError,
    build_local_import_preview,
    confirm_local_import,
    create_index_task,
    create_integrity_task,
    create_recovery_task,
    sign_local_import_plan,
    verify_local_import_token,
)
from app.provider_apply.web import (
    ProviderApplyWebError,
    ensure_provider_apply_web_material,
    get_provider_apply_web_material,
)
from app.models import ItemLocalAsset

router = APIRouter(tags=["local-media-workflow"])
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


def _failure(request: Request, location: str, code: str = "operation_failed") -> RedirectResponse:
    del code
    add_flash(request, "error", "flash.local_workflow_failed")
    return RedirectResponse(location, status_code=303)


@router.post(
    "/items/{item_id}/local-media/preview",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def local_media_preview(
    request: Request,
    item_id: int,
    media_path: str = Form(...),
    import_mode: str = Form(default="file"),
    source_id: str = Form(default=""),
    db: Session = Depends(get_db),
) -> Response:
    try:
        parsed_source = int(source_id) if source_id.strip() else None
        preview = build_local_import_preview(
            db,
            item_id=item_id,
            source_id=parsed_source,
            path=media_path,
            directory=import_mode == "directory",
        )
        material = ensure_provider_apply_web_material(request)
        token = sign_local_import_plan(
            preview.plan,
            secret=material.secret,
            context=material.context,
            now=datetime.now(UTC),
        )
        return templates.TemplateResponse(
            request,
            "local_import_preview.html",
            _context(request, preview=preview, token=token),
            headers={"Cache-Control": "no-store"},
        )
    except (LocalWorkflowError, ProviderApplyWebError, ValueError):
        return _failure(request, f"/items/{item_id}")


@router.post(
    "/items/local-media/confirm",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
def local_media_confirm(
    request: Request,
    token: str = Form(default=""),
    confirmation: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if confirmation != "confirm":
        return _failure(request, "/items")
    try:
        material = get_provider_apply_web_material(request)
        plan = verify_local_import_token(
            token,
            secret=material.secret,
            context=material.context,
            now=datetime.now(UTC),
        )
        tasks = confirm_local_import(
            db,
            plan=plan,
            max_concurrency=get_settings().task_max_concurrency,
        )
    except (LocalWorkflowError, ProviderApplyWebError):
        db.rollback()
        return _failure(request, "/items")
    add_flash(request, "success", "flash.local_tasks_created")
    return RedirectResponse(
        f"/tasks/{tasks[0].id}" if len(tasks) == 1 else "/tasks",
        status_code=303,
    )


@router.post(
    "/items/{item_id}/local-assets/{asset_id}/check",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
def local_asset_check(
    request: Request,
    item_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        asset = db.get(ItemLocalAsset, asset_id)
        if asset is None or asset.item_id != item_id:
            raise LocalWorkflowError("item_mismatch")
        task = create_integrity_task(
            db, asset_id=asset_id, max_concurrency=get_settings().task_max_concurrency
        )
    except LocalWorkflowError:
        db.rollback()
        return _failure(request, f"/items/{item_id}")
    return RedirectResponse(f"/tasks/{task.id}", status_code=303)


@router.post(
    "/tasks/media-index/create",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_index_task_create(
    request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    try:
        task = create_index_task(db, max_concurrency=get_settings().task_max_concurrency)
    except LocalWorkflowError:
        db.rollback()
        return _failure(request, "/tasks")
    return RedirectResponse(f"/tasks/{task.id}", status_code=303)


@router.post(
    "/tasks/media-recovery/create",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_recovery_task_create(
    request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    try:
        task = create_recovery_task(
            db, max_concurrency=get_settings().task_max_concurrency
        )
    except LocalWorkflowError:
        db.rollback()
        return _failure(request, "/tasks")
    return RedirectResponse(f"/tasks/{task.id}", status_code=303)
