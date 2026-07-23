from __future__ import annotations

import secrets
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.acquisition import (
    AcquisitionRegistry,
    AssetDownloadDescriptor,
    DownloadServiceError,
)
from app.acquisition.downloader import SafeDownloadExecutor
from app.acquisition.registry import build_production_acquisition_registry
from app.acquisition.service import (
    build_download_preview,
    confirm_download_plan,
    discover_assets,
    sign_download_plan,
    verify_download_token,
)
from app.auth import is_authenticated, require_page_auth
from app.config import get_settings
from app.database import get_db
from app.flash import add_flash, pop_flash_messages
from app.i18n import get_language, translator
from app.models import (
    DiscoveredAssetFact,
    DownloadTaskFact,
    Item,
    ItemSource,
    OperationTask,
    SourceCheckFact,
    TaskEvent,
)
from app.provider_apply.web import (
    ProviderApplyWebError,
    ensure_provider_apply_web_material,
    get_provider_apply_web_material,
)
from app.routers.source_search import get_provider_search_service
from app.services import local_media
from app.source_adapters.contracts import SourceAssetKind
from app.source_search import ProviderSearchService
from app.source_update import (
    ManualUpdateError,
    apply_manual_update,
    build_manual_update_plan,
    execute_source_check,
    sign_manual_update_plan,
    verify_manual_update_token,
)
from app.tasks import PersistentTaskService, TaskState, TaskTransitionError

router = APIRouter(tags=["tasks"])
templates = Jinja2Templates(directory="app/templates")
_PAGE_SIZE = 25
_VISIBLE_STATES = {state.value for state in TaskState}


def get_acquisition_registry() -> AcquisitionRegistry:
    return build_production_acquisition_registry()


def _render(request: Request, template: str, context: dict[str, object], *, no_store: bool = False) -> HTMLResponse:
    language = get_language(request)
    response = templates.TemplateResponse(
        request=request,
        name=template,
        context={
            **context,
            "t": translator(language),
            "authenticated": is_authenticated(request),
            "lang": language,
            "current_path": quote(request.url.path, safe="/"),
            "flash_messages": pop_flash_messages(request, language),
        },
    )
    if no_store:
        response.headers["Cache-Control"] = "no-store"
    return response


def _failure(request: Request, location: str = "/tasks") -> RedirectResponse:
    add_flash(request, "error", "flash.task_action_failed")
    return RedirectResponse(location, status_code=303)


@router.get("/tasks", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def task_list(
    request: Request,
    state: str = "",
    task_type: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    page = max(1, min(page, 100_000))
    query = select(OperationTask)
    count_query = select(func.count()).select_from(OperationTask)
    if state in _VISIBLE_STATES:
        query = query.where(OperationTask.state == state)
        count_query = count_query.where(OperationTask.state == state)
    if task_type in {"asset_download", "source_check", "metadata_update"}:
        query = query.where(OperationTask.task_type == task_type)
        count_query = count_query.where(OperationTask.task_type == task_type)
    total = int(db.scalar(count_query) or 0)
    tasks = tuple(
        db.scalars(
            query.order_by(OperationTask.created_at.desc(), OperationTask.id.desc())
            .offset((page - 1) * _PAGE_SIZE)
            .limit(_PAGE_SIZE)
        ).all()
    )
    return _render(
        request,
        "tasks.html",
        {"tasks": tasks, "state_filter": state, "type_filter": task_type, "page": page, "total": total, "page_size": _PAGE_SIZE},
    )


@router.get("/tasks/{task_id}", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def task_detail(request: Request, task_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    task = db.get(OperationTask, task_id)
    if task is None:
        return _failure(request)
    events = tuple(
        db.scalars(
            select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.version.asc())
        ).all()
    )
    check_fact = db.get(SourceCheckFact, task_id)
    item = db.get(Item, task.item_id) if task.item_id is not None else None
    source = db.get(ItemSource, task.source_id) if task.source_id is not None else None
    download_fact = db.get(DownloadTaskFact, task_id)
    assets = tuple(
        db.scalars(
            select(DiscoveredAssetFact)
            .where(DiscoveredAssetFact.task_id == task_id)
            .order_by(DiscoveredAssetFact.id.asc())
        ).all()
    )
    return _render(
        request,
        "task_detail.html",
        {
            "task": task,
            "events": events,
            "check_fact": check_fact,
            "download_fact": download_fact,
            "assets": assets,
            "item": item,
            "source": source,
        },
    )


@router.post(
    "/items/{item_id}/sources/{source_id}/check",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
async def source_check(
    request: Request,
    item_id: int,
    source_id: int,
    service: ProviderSearchService = Depends(get_provider_search_service),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        task = await execute_source_check(
            db,
            service,
            item_id=item_id,
            source_id=source_id,
            max_concurrency=get_settings().task_max_concurrency,
        )
    except Exception:
        return _failure(request, f"/items/{item_id}")
    return RedirectResponse(f"/tasks/{task.id}", status_code=303)


@router.post(
    "/items/{item_id}/sources/{source_id}/assets/check",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
async def asset_check(
    request: Request,
    item_id: int,
    source_id: int,
    registry: AcquisitionRegistry = Depends(get_acquisition_registry),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        task = await discover_assets(
            db,
            registry,
            item_id=item_id,
            source_id=source_id,
            max_concurrency=get_settings().task_max_concurrency,
        )
    except Exception:
        return _failure(request, f"/items/{item_id}")
    return RedirectResponse(f"/tasks/{task.id}", status_code=303)


@router.post("/tasks/{task_id}/update-preview", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def update_preview(
    request: Request,
    task_id: int,
    selected_fields: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
) -> Response:
    try:
        plan = build_manual_update_plan(db, check_task_id=task_id, selected_fields=tuple(selected_fields))
        material = ensure_provider_apply_web_material(request)
        token = sign_manual_update_plan(
            plan,
            secret=material.secret,
            context=material.context,
            now=datetime.now(UTC),
        )
    except (ManualUpdateError, ProviderApplyWebError):
        return _failure(request, f"/tasks/{task_id}")
    return _render(request, "task_update_preview.html", {"plan": plan, "token": token}, no_store=True)


@router.post("/tasks/update-confirm", response_class=RedirectResponse, dependencies=[Depends(require_page_auth)])
def update_confirm(
    request: Request,
    token: str = Form(default=""),
    confirmation: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if confirmation != "apply":
        return _failure(request)
    try:
        material = get_provider_apply_web_material(request)
        plan = verify_manual_update_token(
            token,
            secret=material.secret,
            context=material.context,
            now=datetime.now(UTC),
        )
        result = apply_manual_update(
            db,
            plan=plan,
            max_concurrency=get_settings().task_max_concurrency,
        )
    except (ManualUpdateError, ProviderApplyWebError):
        return _failure(request)
    add_flash(request, "success", "flash.task_update_applied")
    return RedirectResponse(f"/tasks/{result.task_id}", status_code=303)


@router.post("/tasks/{task_id}/assets/{asset_id}/download-preview", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def download_preview(
    request: Request,
    task_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
) -> Response:
    task = db.get(OperationTask, task_id)
    asset = db.scalar(
        select(DiscoveredAssetFact).where(
            DiscoveredAssetFact.id == asset_id,
            DiscoveredAssetFact.task_id == task_id,
        )
    )
    if task is None or asset is None or task.item_id is None or task.source_id is None or task.provider_key is None:
        return _failure(request, f"/tasks/{task_id}")
    from app.models import ItemSource

    source = db.get(ItemSource, task.source_id)
    if source is None or source.external_id is None:
        return _failure(request, f"/tasks/{task_id}")
    try:
        descriptor = AssetDownloadDescriptor(
            provider_key=task.provider_key,
            external_id=source.external_id,
            asset_id=asset.asset_id,
            kind=SourceAssetKind(asset.asset_kind),
            display_name=asset.display_name,
            suggested_filename=asset.suggested_filename,
            mime_type=asset.mime_type,
            expected_bytes=asset.expected_bytes,
            expected_sha256=asset.expected_sha256,
            requires_auth=asset.requires_auth,
            resume_supported=asset.resume_supported,
        )
        preview = build_download_preview(
            db,
            item_id=task.item_id,
            source_id=task.source_id,
            descriptor=descriptor,
            relative_target=f"library/{asset.suggested_filename}",
            max_bytes=get_settings().download_max_bytes,
        )
        if not preview.confirmable or preview.plan is None:
            return _failure(request, f"/tasks/{task_id}")
        material = ensure_provider_apply_web_material(request)
        token = sign_download_plan(
            preview.plan,
            secret=material.secret,
            context=material.context,
            now=datetime.now(UTC),
        )
    except (DownloadServiceError, ProviderApplyWebError, TypeError, ValueError):
        return _failure(request, f"/tasks/{task_id}")
    return _render(request, "download_preview.html", {"plan": preview.plan, "token": token}, no_store=True)


@router.post("/tasks/download-confirm", response_class=RedirectResponse, dependencies=[Depends(require_page_auth)])
def download_confirm(
    request: Request,
    token: str = Form(default=""),
    confirmation: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if confirmation != "confirm":
        return _failure(request)
    try:
        material = get_provider_apply_web_material(request)
        plan = verify_download_token(
            token,
            secret=material.secret,
            context=material.context,
            now=datetime.now(UTC),
        )
        task, _created = confirm_download_plan(
            db,
            plan=plan,
            max_concurrency=get_settings().task_max_concurrency,
        )
        db.commit()
    except (DownloadServiceError, ProviderApplyWebError, TaskTransitionError):
        db.rollback()
        return _failure(request)
    add_flash(request, "success", "flash.download_task_created")
    return RedirectResponse(f"/tasks/{task.id}", status_code=303)


async def _run_download(
    db: Session,
    registry: AcquisitionRegistry,
    task_id: int,
    *,
    resume: bool,
) -> None:
    settings = get_settings()
    tasks = PersistentTaskService(db, max_concurrency=settings.task_max_concurrency)
    task = tasks.get(task_id)
    if resume:
        task = tasks.transition(task.id, TaskState.QUEUED, expected_version=task.version, event_type="resume_requested")
    task = tasks.transition(task.id, TaskState.RUNNING, expected_version=task.version, event_type="start_requested")
    owner = f"web-{secrets.token_hex(16)}"
    task = tasks.acquire_lease(task.id, owner=owner, expected_version=task.version)
    db.commit()
    executor = SafeDownloadExecutor(
        db,
        registry,
        media_root=local_media.LOCAL_MEDIA_ROOT,
        temp_root=Path("data/.downloads"),
        chunk_bytes=settings.download_chunk_bytes,
        timeout_seconds=settings.download_timeout_seconds,
        max_concurrency=settings.task_max_concurrency,
    )
    await executor.execute(task.id, lease_owner=owner, lease_generation=task.lease_generation)


@router.post("/tasks/{task_id}/start", response_class=RedirectResponse, dependencies=[Depends(require_page_auth)])
async def task_start(
    request: Request,
    task_id: int,
    registry: AcquisitionRegistry = Depends(get_acquisition_registry),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        await _run_download(db, registry, task_id, resume=False)
    except Exception:
        return _failure(request, f"/tasks/{task_id}")
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@router.post("/tasks/{task_id}/resume", response_class=RedirectResponse, dependencies=[Depends(require_page_auth)])
async def task_resume(
    request: Request,
    task_id: int,
    registry: AcquisitionRegistry = Depends(get_acquisition_registry),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        await _run_download(db, registry, task_id, resume=True)
    except Exception:
        return _failure(request, f"/tasks/{task_id}")
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


def _simple_action(request: Request, db: Session, task_id: int, action: str) -> RedirectResponse:
    try:
        settings = get_settings()
        service = PersistentTaskService(db, max_concurrency=settings.task_max_concurrency)
        task = service.get(task_id)
        if action == "pause":
            service.transition(task.id, TaskState.PAUSED, expected_version=task.version, event_type="pause_requested")
        elif action == "cancel":
            service.request_cancel(task.id, expected_version=task.version)
        elif action == "retry":
            service.retry(task.id, expected_version=task.version)
        elif action == "delete":
            service.delete_history(task.id)
        else:
            raise ValueError
        db.commit()
    except Exception:
        db.rollback()
        return _failure(request, f"/tasks/{task_id}")
    return RedirectResponse("/tasks" if action == "delete" else f"/tasks/{task_id}", status_code=303)


@router.post("/tasks/{task_id}/pause", response_class=RedirectResponse, dependencies=[Depends(require_page_auth)])
def task_pause(request: Request, task_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    return _simple_action(request, db, task_id, "pause")


@router.post("/tasks/{task_id}/cancel", response_class=RedirectResponse, dependencies=[Depends(require_page_auth)])
def task_cancel(request: Request, task_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    return _simple_action(request, db, task_id, "cancel")


@router.post("/tasks/{task_id}/retry", response_class=RedirectResponse, dependencies=[Depends(require_page_auth)])
def task_retry(request: Request, task_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    return _simple_action(request, db, task_id, "retry")


@router.post("/tasks/{task_id}/delete-history", response_class=RedirectResponse, dependencies=[Depends(require_page_auth)])
def task_delete_history(request: Request, task_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    return _simple_action(request, db, task_id, "delete")
