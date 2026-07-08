from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import is_authenticated, logout_user, require_page_auth
from app.config import get_settings
from app.database import get_db
from app.flash import add_flash, pop_flash_messages
from app.i18n import get_language, set_language, status_translator, translate, translator
from app.models import Creator, Item, Tag, UserItemState
from app.schemas import CreatorCreate, ItemCreate, ItemUpdate, StateCreate, TagCreate
from app.services.catalog import (
    create_item,
    delete_state,
    get_item_or_404,
    parse_extra,
    set_state,
    split_names,
    update_item,
)
from app.services.backup import BackupError, preview_backup_data, restore_backup_data
from app.services.importer import import_rows, parse_csv_rows, parse_json_rows
from app.services.item_query import (
    STATUS_OPTIONS,
    build_item_list_url,
    list_item_filter_options,
    query_items,
)

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _base_context(request: Request, **values: Any) -> dict[str, Any]:
    language = get_language(request)
    current_path = request.url.path
    if request.url.query:
        current_path = f"{current_path}?{request.url.query}"
    context = {
        "request": request,
        "authenticated": is_authenticated(request),
        "lang": language,
        "current_path": quote(current_path, safe="/"),
        "t": translator(language),
        "status_label": status_translator(language),
        "status_options": STATUS_OPTIONS,
        "max_backup_upload_mb": get_settings().max_backup_upload_mb,
        "flash_messages": pop_flash_messages(request, language),
    }
    context.update(values)
    return context


def _parse_extra_json(value: str | None) -> dict[str, Any] | None:
    if value is None or not value.strip():
        return None
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("extra must be a JSON object")
    return payload


def _item_form_payload(
    title: str,
    cover_path: str | None,
    summary: str | None,
    release_date: str | None,
    tags: str | None,
    creators: str | None,
    extra_json: str | None,
) -> ItemCreate:
    return ItemCreate(
        title=title,
        cover_path=cover_path,
        summary=summary,
        release_date=release_date,
        extra=_parse_extra_json(extra_json),
        tags=split_names(tags),
        creators=split_names(creators),
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Response:
    if is_authenticated(request):
        return _redirect("/")
    return templates.TemplateResponse(
        request,
        "login.html",
        _base_context(request, error=request.query_params.get("error")),
    )


@router.post("/logout")
def logout_page(
    request: Request,
    authenticated: bool = Depends(require_page_auth),
) -> RedirectResponse:
    del authenticated
    logout_user(request)
    add_flash(request, "info", "flash.logout_success")
    return _redirect("/login")


@router.get("/set-language")
def set_language_page(
    request: Request,
    lang: str = "zh",
    next: str = "/",
) -> RedirectResponse:
    set_language(request, lang)
    target = next if next.startswith("/") and not next.startswith("//") else "/"
    return _redirect(target)


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def index_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    recent_items = db.scalars(
        select(Item)
        .options(
            selectinload(Item.tags),
            selectinload(Item.creators),
            selectinload(Item.state),
        )
        .order_by(Item.created_at.desc(), Item.id.desc())
        .limit(8)
    ).all()
    totals = {
        "items": db.scalar(select(func.count(Item.id))) or 0,
        "tags": db.scalar(select(func.count(Tag.id))) or 0,
        "creators": db.scalar(select(func.count(Creator.id))) or 0,
    }
    return templates.TemplateResponse(
        request,
        "index.html",
        _base_context(request, recent_items=recent_items, totals=totals),
    )


def _pagination_context(result: Any) -> dict[str, Any]:
    filters = result.filters
    total = result.total
    start = ((filters.page - 1) * filters.page_size) + 1 if total else 0
    end = min(filters.page * filters.page_size, total) if total else 0
    return {
        "page": filters.page,
        "page_size": filters.page_size,
        "total": total,
        "total_pages": result.total_pages,
        "start": start,
        "end": end,
        "has_prev": filters.page > 1,
        "has_next": filters.page < result.total_pages,
        "prev_url": build_item_list_url(filters, page=filters.page - 1),
        "next_url": build_item_list_url(filters, page=filters.page + 1),
        "page_urls": [
            {"page": page_number, "url": build_item_list_url(filters, page=page_number)}
            for page_number in result.page_numbers
        ],
    }


@router.get("/items", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def items_page(
    request: Request,
    q: str | None = None,
    tag: str | None = None,
    creator: str | None = None,
    state: str | None = None,
    min_rating: str | None = None,
    time_range: str | None = None,
    date_field: str | None = None,
    sort: str | None = None,
    page: str | None = None,
    page_size: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    result = query_items(
        db,
        q=q,
        tag=tag,
        creator=creator,
        state=state,
        min_rating=min_rating,
        time_range=time_range,
        date_field=date_field,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return templates.TemplateResponse(
        request,
        "items.html",
        _base_context(
            request,
            items=result.items,
            filters=result.filters,
            filter_options=list_item_filter_options(db),
            pagination=_pagination_context(result),
        ),
    )


@router.get(
    "/items/new",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def new_item_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "item_form.html",
        _base_context(request, item=None, action="/items", mode_key="items.create_title"),
    )


@router.post("/items", dependencies=[Depends(require_page_auth)])
def create_item_page(
    request: Request,
    title: str = Form(...),
    cover_path: str | None = Form(default=None),
    summary: str | None = Form(default=None),
    release_date: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    creators: str | None = Form(default=None),
    status_value: str | None = Form(default=None),
    rating: int | None = Form(default=None),
    review: str | None = Form(default=None),
    extra_json: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        item = create_item(
            db,
            _item_form_payload(
                title, cover_path, summary, release_date, tags, creators, extra_json
            ),
        )
        if status_value:
            set_state(
                db,
                item,
                StateCreate(status=status_value, rating=rating, review=review),
            )
    except ValueError:
        add_flash(request, "error", "flash.item_save_failed")
        return _redirect("/items/new")
    add_flash(request, "success", "flash.item_created")
    return _redirect(f"/items/{item.id}")


@router.get(
    "/items/{item_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def item_detail_page(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    item = get_item_or_404(db, item_id)
    return templates.TemplateResponse(
        request,
        "detail.html",
        _base_context(request, item=item, extra=parse_extra(item.extra)),
    )


@router.get(
    "/items/{item_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def edit_item_page(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    item = get_item_or_404(db, item_id)
    return templates.TemplateResponse(
        request,
        "item_form.html",
        _base_context(
            request,
            item=item,
            action=f"/items/{item.id}/edit",
            mode_key="items.edit_title",
            extra=parse_extra(item.extra),
        ),
    )


@router.post("/items/{item_id}/edit", dependencies=[Depends(require_page_auth)])
def update_item_page(
    request: Request,
    item_id: int,
    title: str = Form(...),
    cover_path: str | None = Form(default=None),
    summary: str | None = Form(default=None),
    release_date: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    creators: str | None = Form(default=None),
    extra_json: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    item = get_item_or_404(db, item_id)
    try:
        update_item(
            db,
            item,
            ItemUpdate(
                title=title,
                cover_path=cover_path,
                summary=summary,
                release_date=release_date,
                extra=_parse_extra_json(extra_json),
                tags=split_names(tags),
                creators=split_names(creators),
            ),
        )
    except ValueError:
        add_flash(request, "error", "flash.item_save_failed")
        return _redirect(f"/items/{item_id}/edit")
    add_flash(request, "success", "flash.item_updated")
    return _redirect(f"/items/{item_id}")


@router.post("/items/{item_id}/delete", dependencies=[Depends(require_page_auth)])
def delete_item_page(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    item = db.get(Item, item_id)
    if item is None:
        add_flash(request, "error", "flash.item_delete_failed")
        return _redirect("/items")
    db.delete(item)
    db.commit()
    add_flash(request, "success", "flash.item_deleted")
    return _redirect("/items")


@router.post("/items/{item_id}/state", dependencies=[Depends(require_page_auth)])
def set_item_state_page(
    request: Request,
    item_id: int,
    status_value: str = Form(...),
    rating: int | None = Form(default=None),
    review: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    item = get_item_or_404(db, item_id)
    set_state(db, item, StateCreate(status=status_value, rating=rating, review=review))
    add_flash(request, "success", "flash.state_saved")
    return _redirect(f"/items/{item_id}")


@router.post("/items/{item_id}/state/delete", dependencies=[Depends(require_page_auth)])
def delete_item_state_page(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    item = get_item_or_404(db, item_id)
    delete_state(db, item)
    add_flash(request, "info", "flash.state_cleared")
    return _redirect(f"/items/{item_id}")


@router.get("/tags", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def tags_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    tags = db.scalars(select(Tag).order_by(Tag.name.asc())).all()
    return templates.TemplateResponse(
        request,
        "tags.html",
        _base_context(request, tags=tags),
    )


@router.post("/tags", dependencies=[Depends(require_page_auth)])
def create_tag_page(
    request: Request,
    name: str = Form(...),
    category: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    payload = TagCreate(name=name, category=category)
    tag = Tag(name=payload.name, category=payload.category)
    db.add(tag)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        add_flash(request, "error", "flash.tag_create_failed")
    else:
        add_flash(request, "success", "flash.tag_created")
    return _redirect("/tags")


@router.post("/tags/{tag_id}/delete", dependencies=[Depends(require_page_auth)])
def delete_tag_page(
    request: Request,
    tag_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    tag = db.get(Tag, tag_id)
    if tag is None:
        add_flash(request, "error", "flash.tag_delete_failed")
        return _redirect("/tags")
    db.delete(tag)
    db.commit()
    add_flash(request, "success", "flash.tag_deleted")
    return _redirect("/tags")


@router.get(
    "/creators",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def creators_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    creators = db.scalars(select(Creator).order_by(Creator.name.asc())).all()
    return templates.TemplateResponse(
        request,
        "creators.html",
        _base_context(request, creators=creators),
    )


@router.post("/creators", dependencies=[Depends(require_page_auth)])
def create_creator_page(
    request: Request,
    name: str = Form(...),
    type_value: str = Form(default="other"),
    avatar_path: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    payload = CreatorCreate(name=name, type=type_value, avatar_path=avatar_path)
    creator = Creator(
        name=payload.name,
        type=payload.type or "other",
        avatar_path=payload.avatar_path,
    )
    db.add(creator)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        add_flash(request, "error", "flash.creator_create_failed")
    else:
        add_flash(request, "success", "flash.creator_created")
    return _redirect("/creators")


@router.get(
    "/creators/{creator_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def creator_detail_page(
    request: Request,
    creator_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    creator = db.scalar(
        select(Creator)
        .where(Creator.id == creator_id)
        .options(selectinload(Creator.items))
    )
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    return templates.TemplateResponse(
        request,
        "creator_detail.html",
        _base_context(request, creator=creator),
    )


@router.post("/creators/{creator_id}/delete", dependencies=[Depends(require_page_auth)])
def delete_creator_page(
    request: Request,
    creator_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    creator = db.get(Creator, creator_id)
    if creator is None:
        add_flash(request, "error", "flash.creator_delete_failed")
        return _redirect("/creators")
    db.delete(creator)
    db.commit()
    add_flash(request, "success", "flash.creator_deleted")
    return _redirect("/creators")


@router.get("/stats", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def stats_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    state_rows = db.execute(
        select(UserItemState.status, func.count(UserItemState.id)).group_by(
            UserItemState.status
        )
    ).all()
    timeline = db.execute(
        select(func.date(Item.created_at), func.count(Item.id))
        .group_by(func.date(Item.created_at))
        .order_by(func.date(Item.created_at).asc())
    ).all()
    summary = {
        "total_items": db.scalar(select(func.count(Item.id))) or 0,
        "total_tags": db.scalar(select(func.count(Tag.id))) or 0,
        "total_creators": db.scalar(select(func.count(Creator.id))) or 0,
        "states": dict(state_rows),
    }
    return templates.TemplateResponse(
        request,
        "stats.html",
        _base_context(request, summary=summary, timeline=timeline),
    )


@router.get(
    "/import",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def import_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "import.html",
        _base_context(
            request,
            result=None,
            preview_rows=None,
            preview_headers=[],
            payload_json="",
        ),
    )


def _preview_headers(rows: list[dict[str, Any]]) -> list[str]:
    headers: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                headers.append(key)
    return headers


def _import_template(
    request: Request,
    result: dict[str, Any] | None = None,
    preview_rows: list[dict[str, Any]] | None = None,
    import_error: str | None = None,
) -> HTMLResponse:
    rows = preview_rows or []
    return templates.TemplateResponse(
        request,
        "import.html",
        _base_context(
            request,
            result=result,
            preview_rows=rows[:20],
            preview_headers=_preview_headers(rows[:20]),
            preview_count=len(rows),
            payload_json=json.dumps(rows, ensure_ascii=False),
            import_error=import_error,
        ),
    )


@router.post(
    "/import/csv",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
async def import_csv_page(
    request: Request,
    file: UploadFile = File(...),
) -> HTMLResponse:
    try:
        return _import_template(request, preview_rows=parse_csv_rows(await file.read()))
    except (UnicodeDecodeError, ValueError):
        return _import_template(
            request,
            import_error=translate(get_language(request), "import.preview_error"),
        )


@router.post(
    "/import/json",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
async def import_json_page(
    request: Request,
    file: UploadFile = File(...),
) -> HTMLResponse:
    try:
        return _import_template(request, preview_rows=parse_json_rows(await file.read()))
    except (UnicodeDecodeError, ValueError):
        return _import_template(
            request,
            import_error=translate(get_language(request), "import.preview_error"),
        )


@router.post(
    "/import/confirm",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def import_confirm_page(
    request: Request,
    payload_json: str = Form(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return _import_template(
            request,
            import_error=translate(get_language(request), "import.confirm_error"),
        )
    rows = payload if isinstance(payload, list) else []
    clean_rows = [row for row in rows if isinstance(row, dict)]
    result = import_rows(db, clean_rows)
    return _import_template(request, result=result)


def _backup_error_message(request: Request, code: str) -> str:
    return translate(get_language(request), f"backup.error_{code}")


async def _read_backup_upload_for_page(
    request: Request,
    file: UploadFile | None,
) -> dict[str, Any]:
    if file is None:
        raise BackupError("missing_file")
    if not (file.filename or "").lower().endswith(".json"):
        raise BackupError("json_required")
    max_bytes = get_settings().max_backup_upload_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise BackupError("too_large")
    try:
        payload = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BackupError("invalid_json") from exc
    if not isinstance(payload, dict):
        raise BackupError("invalid_backup")
    return payload


def _backup_template(
    request: Request,
    preview_result: dict[str, int | str] | None = None,
    preview_error: str | None = None,
    restore_result: dict[str, int] | None = None,
    restore_error: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "backup.html",
        _base_context(
            request,
            preview_result=preview_result,
            preview_error=preview_error,
            restore_result=restore_result,
            restore_error=restore_error,
        ),
    )


@router.get(
    "/backup",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def backup_page(request: Request) -> HTMLResponse:
    return _backup_template(request)


@router.post(
    "/backup/preview",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
async def backup_preview_page(
    request: Request,
    file: UploadFile | None = File(default=None),
) -> HTMLResponse:
    try:
        payload = await _read_backup_upload_for_page(request, file)
        return _backup_template(request, preview_result=preview_backup_data(payload))
    except BackupError as exc:
        return _backup_template(
            request,
            preview_error=_backup_error_message(request, exc.code),
        )


@router.post(
    "/backup/restore",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
async def backup_restore_page(
    request: Request,
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    restore_result: dict[str, int] | None = None
    restore_error: str | None = None
    try:
        payload = await _read_backup_upload_for_page(request, file)
        preview_backup_data(payload)
        restore_result = restore_backup_data(db, payload)
    except BackupError as exc:
        restore_error = _backup_error_message(request, exc.code)
    except ValueError:
        restore_error = _backup_error_message(request, "restore_failed")
    return _backup_template(
        request,
        restore_result=restore_result,
        restore_error=restore_error,
    )
