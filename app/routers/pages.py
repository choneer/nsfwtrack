from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import is_authenticated, logout_user, require_page_auth
from app.database import get_db
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
from app.services.importer import import_rows, parse_csv_rows, parse_json_rows

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")

STATUS_OPTIONS = ["wish", "watching", "watched", "like", "dislike", "ignore"]


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _base_context(request: Request, **values: Any) -> dict[str, Any]:
    context = {
        "request": request,
        "authenticated": is_authenticated(request),
        "status_options": STATUS_OPTIONS,
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
    return _redirect("/login")


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


@router.get("/items", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def items_page(
    request: Request,
    q: str | None = None,
    tag: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    stmt = select(Item)
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q.strip()}%"))
    if tag:
        stmt = stmt.join(Item.tags).where(Tag.name == tag.strip())
    if state:
        stmt = stmt.join(Item.state).where(UserItemState.status == state.strip())
    items = db.scalars(
        stmt.options(
            selectinload(Item.tags),
            selectinload(Item.creators),
            selectinload(Item.state),
        )
        .distinct()
        .order_by(Item.created_at.desc(), Item.id.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "items.html",
        _base_context(
            request,
            items=items,
            q=q or "",
            tag=tag or "",
            selected_state=state or "",
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
        _base_context(request, item=None, action="/items", mode="Create"),
    )


@router.post("/items", dependencies=[Depends(require_page_auth)])
def create_item_page(
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
            mode="Edit",
            extra=parse_extra(item.extra),
        ),
    )


@router.post("/items/{item_id}/edit", dependencies=[Depends(require_page_auth)])
def update_item_page(
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
    return _redirect(f"/items/{item_id}")


@router.post("/items/{item_id}/delete", dependencies=[Depends(require_page_auth)])
def delete_item_page(item_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    item = get_item_or_404(db, item_id)
    db.delete(item)
    db.commit()
    return _redirect("/items")


@router.post("/items/{item_id}/state", dependencies=[Depends(require_page_auth)])
def set_item_state_page(
    item_id: int,
    status_value: str = Form(...),
    rating: int | None = Form(default=None),
    review: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    item = get_item_or_404(db, item_id)
    set_state(db, item, StateCreate(status=status_value, rating=rating, review=review))
    return _redirect(f"/items/{item_id}")


@router.post("/items/{item_id}/state/delete", dependencies=[Depends(require_page_auth)])
def delete_item_state_page(
    item_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    item = get_item_or_404(db, item_id)
    delete_state(db, item)
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
    return _redirect("/tags")


@router.post("/tags/{tag_id}/delete", dependencies=[Depends(require_page_auth)])
def delete_tag_page(tag_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    db.delete(tag)
    db.commit()
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
    creator_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    db.delete(creator)
    db.commit()
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
    return _import_template(request, preview_rows=parse_csv_rows(await file.read()))


@router.post(
    "/import/json",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
async def import_json_page(
    request: Request,
    file: UploadFile = File(...),
) -> HTMLResponse:
    return _import_template(request, preview_rows=parse_json_rows(await file.read()))


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
    payload = json.loads(payload_json)
    rows = payload if isinstance(payload, list) else []
    clean_rows = [row for row in rows if isinstance(row, dict)]
    result = import_rows(db, clean_rows)
    return _import_template(request, result=result)
