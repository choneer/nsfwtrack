from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
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
from app.models import Creator, Item, Tag
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
from app.services.backup_validator import validate_backup_payload
from app.services.bulk_actions import (
    BulkActionError,
    add_items_collection,
    add_items_tag,
    delete_items,
    remove_items_collection,
    remove_items_tag,
    set_items_rating,
    set_items_status,
)
from app.services.collections import (
    CollectionError,
    add_item_to_collection,
    create_collection,
    delete_collection,
    get_collection,
    list_available_collections_for_item,
    list_available_items_for_collection,
    list_collection_rows,
    remove_item_from_collection,
    update_collection,
)
from app.services.data_health import build_data_health_report
from app.services.duplicates import (
    DuplicateError,
    find_duplicate_candidates,
    get_duplicate_comparison,
    merge_duplicate_items,
)
from app.services.importer import (
    IMPORT_FIELDS,
    TARGET_FIELDS,
    ImportDataError,
    build_mapping,
    import_valid_rows,
    preview_csv_import,
    preview_csv_rows,
    preview_json_import,
    preview_json_rows,
)
from app.services.item_detail import (
    ItemDetailError,
    add_existing_creator,
    add_existing_tag,
    list_available_creators,
    list_available_tags,
    remove_existing_creator,
    remove_existing_tag,
    save_item_state,
)
from app.services.item_query import (
    STATUS_OPTIONS,
    build_item_list_url,
    list_item_filter_options,
    query_items,
)
from app.services.metadata_cleanup import (
    MetadataCleanupError,
    find_metadata_cleanup_candidates,
    get_metadata_comparison,
    merge_metadata_objects,
)
from app.services.saved_views import (
    MAX_SAVED_VIEW_NAME_LENGTH,
    SavedViewError,
    create_saved_view,
    delete_saved_view,
    get_saved_view,
    list_saved_views,
    normalize_saved_view_query_string,
    saved_view_items_url,
    update_saved_view,
)
from app.services.activity import (
    ACTIVITY_PAGE_LIMIT,
    clear_item_activity,
    count_item_activity,
    get_item_activity,
    list_recently_edited,
    list_recently_viewed,
    safe_record_item_edit,
    safe_record_item_edits,
    safe_record_item_view,
)
from app.services.stats import build_stats_dashboard

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _safe_next_url(next_url: str | None) -> str:
    if not next_url or not next_url.startswith("/") or next_url.startswith("//"):
        return "/items"
    return next_url


def _item_detail_url(item_id: int, next_url: str | None = None) -> str:
    target = _safe_next_url(next_url)
    if target == "/items":
        return f"/items/{item_id}"
    return f"/items/{item_id}?next={quote(target, safe='')}"


def _item_edit_url(item_id: int, next_url: str | None = None) -> str:
    target = _safe_next_url(next_url)
    if target == "/items":
        return f"/items/{item_id}/edit"
    return f"/items/{item_id}/edit?next={quote(target, safe='')}"


def _base_context(request: Request, **values: Any) -> dict[str, Any]:
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
        _base_context(
            request,
            recent_items=recent_items,
            recent_viewed=list_recently_viewed(db, limit=4),
            recent_edited=list_recently_edited(db, limit=4),
            saved_views=list_saved_views(db)[:4],
            totals=totals,
        ),
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


def _duplicate_action_label(request: Request, action: str) -> str:
    return translate(get_language(request), f"duplicates.action_{action}")


def _cleanup_type_label(request: Request, metadata_type: str) -> str:
    return translate(get_language(request), f"cleanup.type_{metadata_type}")


def _cleanup_action_label(request: Request, action: str) -> str:
    return translate(get_language(request), f"cleanup.action_{action}")


def _saved_view_error_flash(request: Request, exc: SavedViewError) -> None:
    add_flash(request, "error", f"flash.saved_view_{exc.code}")


@router.get(
    "/items",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def items_page(
    request: Request,
    q: str | None = None,
    tag: str | None = None,
    creator: str | None = None,
    collection: str | None = None,
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
        collection=collection,
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
            saved_views=list_saved_views(db),
            saved_view_query_string=normalize_saved_view_query_string(
                request.query_params
            ),
            saved_view_max_name_length=MAX_SAVED_VIEW_NAME_LENGTH,
        ),
    )


@router.post("/saved-views", dependencies=[Depends(require_page_auth)])
def create_saved_view_page(
    request: Request,
    name: str = Form(default=""),
    query_string: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = saved_view_items_url(query_string)
    try:
        create_saved_view(db, name=name, query_string=query_string)
    except SavedViewError as exc:
        _saved_view_error_flash(request, exc)
        return _redirect(target)
    add_flash(request, "success", "flash.saved_view_saved")
    return _redirect(target)


@router.post(
    "/saved-views/{saved_view_id}/update",
    dependencies=[Depends(require_page_auth)],
)
def update_saved_view_page(
    request: Request,
    saved_view_id: int,
    query_string: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = saved_view_items_url(query_string)
    try:
        update_saved_view(db, saved_view_id, query_string=query_string)
    except SavedViewError as exc:
        _saved_view_error_flash(request, exc)
        return _redirect(target)
    add_flash(request, "success", "flash.saved_view_updated")
    return _redirect(target)


@router.post(
    "/saved-views/{saved_view_id}/delete",
    dependencies=[Depends(require_page_auth)],
)
def delete_saved_view_page(
    request: Request,
    saved_view_id: int,
    query_string: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = saved_view_items_url(query_string)
    try:
        delete_saved_view(db, saved_view_id)
    except SavedViewError as exc:
        _saved_view_error_flash(request, exc)
        return _redirect(target)
    add_flash(request, "success", "flash.saved_view_deleted")
    return _redirect(target)


@router.get(
    "/saved-views/{saved_view_id}/apply",
    dependencies=[Depends(require_page_auth)],
)
def apply_saved_view_page(
    request: Request,
    saved_view_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        saved_view = get_saved_view(db, saved_view_id)
    except SavedViewError as exc:
        _saved_view_error_flash(request, exc)
        return _redirect("/items")
    return _redirect(saved_view_items_url(saved_view.query_string))


@router.get(
    "/activity",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def activity_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "activity.html",
        _base_context(
            request,
            recent_viewed=list_recently_viewed(db, limit=ACTIVITY_PAGE_LIMIT),
            recent_edited=list_recently_edited(db, limit=ACTIVITY_PAGE_LIMIT),
            activity_total=count_item_activity(db),
        ),
    )


@router.get(
    "/data-health",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def data_health_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "data_health.html",
        _base_context(request, report=build_data_health_report(db)),
    )


@router.post("/activity/clear", dependencies=[Depends(require_page_auth)])
def clear_activity_page(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    deleted_count = clear_item_activity(db)
    add_flash(
        request,
        "success",
        "flash.activity_cleared",
        count=deleted_count,
    )
    return _redirect("/activity")


@router.get(
    "/duplicates",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def duplicates_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "duplicates.html",
        _base_context(request, candidate_groups=find_duplicate_candidates(db)),
    )


@router.get(
    "/duplicates/compare",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def duplicate_compare_page(
    request: Request,
    primary_id: str | None = None,
    duplicate_id: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    try:
        comparison = get_duplicate_comparison(db, primary_id, duplicate_id)
    except DuplicateError as exc:
        add_flash(request, "error", f"flash.duplicate_{exc.code}")
        return _redirect("/duplicates")
    return templates.TemplateResponse(
        request,
        "duplicate_compare.html",
        _base_context(request, comparison=comparison),
    )


@router.post("/duplicates/merge", dependencies=[Depends(require_page_auth)])
def duplicate_merge_page(
    request: Request,
    primary_id: str = Form(...),
    duplicate_id: str = Form(...),
    use_duplicate_summary: str | None = Form(default=None),
    use_duplicate_status: str | None = Form(default=None),
    use_duplicate_rating: str | None = Form(default=None),
    use_duplicate_review: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        result = merge_duplicate_items(
            db,
            primary_id=primary_id,
            duplicate_id=duplicate_id,
            use_duplicate_summary=bool(use_duplicate_summary),
            use_duplicate_status=bool(use_duplicate_status),
            use_duplicate_rating=bool(use_duplicate_rating),
            use_duplicate_review=bool(use_duplicate_review),
        )
    except DuplicateError as exc:
        add_flash(request, "error", f"flash.duplicate_{exc.code}")
        return _redirect("/duplicates")

    add_flash(
        request,
        "success",
        "flash.duplicate_merge_success",
        primary_title=result.primary_title,
        duplicate_title=result.duplicate_title,
    )
    add_flash(
        request,
        "info",
        "flash.duplicate_merge_result",
        tags=result.tags_transferred,
        creators=result.creators_transferred,
        collections=result.collections_transferred,
        summary=_duplicate_action_label(request, result.summary_action),
        status=_duplicate_action_label(request, result.status_action),
        rating=_duplicate_action_label(request, result.rating_action),
        review=_duplicate_action_label(request, result.review_action),
        extra_keys=result.extra_keys_merged,
        extra_conflicts=result.extra_conflicts_kept,
        duplicate_deleted=translate(get_language(request), "duplicates.deleted_yes"),
    )
    return _redirect(f"/items/{result.primary_id}")


@router.get(
    "/cleanup",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def cleanup_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    sections = find_metadata_cleanup_candidates(db)
    return templates.TemplateResponse(
        request,
        "cleanup.html",
        _base_context(
            request,
            candidate_sections=sections,
            has_candidates=any(section.groups for section in sections),
        ),
    )


@router.get(
    "/cleanup/compare",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def cleanup_compare_page(
    request: Request,
    cleanup_type: str | None = Query(default=None, alias="type"),
    primary_id: str | None = None,
    duplicate_id: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    try:
        comparison = get_metadata_comparison(
            db,
            metadata_type=cleanup_type,
            primary_id=primary_id,
            duplicate_id=duplicate_id,
        )
    except MetadataCleanupError as exc:
        add_flash(request, "error", f"flash.cleanup_{exc.code}")
        return _redirect("/cleanup")
    return templates.TemplateResponse(
        request,
        "cleanup_compare.html",
        _base_context(request, comparison=comparison),
    )


@router.post("/cleanup/merge", dependencies=[Depends(require_page_auth)])
def cleanup_merge_page(
    request: Request,
    cleanup_type: str = Form(..., alias="type"),
    primary_id: str = Form(...),
    duplicate_id: str = Form(...),
    use_duplicate_description: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        result = merge_metadata_objects(
            db,
            metadata_type=cleanup_type,
            primary_id=primary_id,
            duplicate_id=duplicate_id,
            use_duplicate_description=bool(use_duplicate_description),
        )
    except MetadataCleanupError as exc:
        add_flash(request, "error", f"flash.cleanup_{exc.code}")
        return _redirect("/cleanup")

    add_flash(
        request,
        "success",
        "flash.cleanup_merge_success",
        metadata_type=_cleanup_type_label(request, result.metadata_type),
        duplicate_name=result.duplicate_name,
        primary_name=result.primary_name,
    )
    add_flash(
        request,
        "info",
        "flash.cleanup_merge_result",
        metadata_type=_cleanup_type_label(request, result.metadata_type),
        primary_name=result.primary_name,
        duplicate_name=result.duplicate_name,
        transferred=result.transferred_relations,
        skipped=result.skipped_relations,
        description=_cleanup_action_label(request, result.description_action),
        duplicate_deleted=translate(get_language(request), "cleanup.deleted_yes"),
    )
    return _redirect("/cleanup")


@router.post("/items/bulk", dependencies=[Depends(require_page_auth)])
def bulk_items_page(
    request: Request,
    bulk_action: str = Form(...),
    item_ids: list[str] | None = Form(default=None),
    status_value: str | None = Form(default=None),
    add_tag_id: str | None = Form(default=None),
    remove_tag_id: str | None = Form(default=None),
    add_collection_id: str | None = Form(default=None),
    remove_collection_id: str | None = Form(default=None),
    rating: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _safe_next_url(next_url)
    try:
        if bulk_action == "status":
            result = set_items_status(db, item_ids, status_value)
        elif bulk_action == "add_tag":
            result = add_items_tag(db, item_ids, add_tag_id)
        elif bulk_action == "remove_tag":
            result = remove_items_tag(db, item_ids, remove_tag_id)
        elif bulk_action == "add_collection":
            result = add_items_collection(db, item_ids, add_collection_id)
        elif bulk_action == "remove_collection":
            result = remove_items_collection(db, item_ids, remove_collection_id)
        elif bulk_action == "rating":
            result = set_items_rating(db, item_ids, rating)
        elif bulk_action == "delete":
            result = delete_items(db, item_ids)
        else:
            raise BulkActionError("invalid_action")
    except BulkActionError as exc:
        add_flash(request, "error", f"flash.bulk_{exc.code}")
        return _redirect(target)

    add_flash(
        request,
        "success",
        "flash.bulk_action_success",
        processed=result.processed,
        skipped=result.skipped,
    )
    if bulk_action != "delete":
        safe_record_item_edits(db, result.item_ids)
    return _redirect(target)


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
    safe_record_item_view(db, item.id)
    item = get_item_or_404(db, item_id)
    return_list_url = _safe_next_url(request.query_params.get("next"))
    return templates.TemplateResponse(
        request,
        "detail.html",
        _base_context(
            request,
            item=item,
            item_activity=get_item_activity(db, item.id),
            extra=parse_extra(item.extra),
            available_tags=list_available_tags(db, item.id),
            available_creators=list_available_creators(db, item.id),
            available_collections=list_available_collections_for_item(db, item.id),
            return_list_url=return_list_url,
            return_list_url_quoted=quote(return_list_url, safe=""),
            detail_url=_item_detail_url(item.id, return_list_url),
            edit_url=_item_edit_url(item.id, return_list_url),
        ),
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
    return_list_url = _safe_next_url(request.query_params.get("next"))
    return templates.TemplateResponse(
        request,
        "item_form.html",
        _base_context(
            request,
            item=item,
            action=_item_edit_url(item.id, return_list_url),
            mode_key="items.edit_title",
            extra=parse_extra(item.extra),
            return_list_url=return_list_url,
            return_list_url_quoted=quote(return_list_url, safe=""),
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
    return_list_url = _safe_next_url(request.query_params.get("next"))
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
        return _redirect(_item_edit_url(item_id, return_list_url))
    safe_record_item_edit(db, item_id)
    add_flash(request, "success", "flash.item_updated")
    return _redirect(_item_detail_url(item_id, return_list_url))


@router.post("/items/{item_id}/delete", dependencies=[Depends(require_page_auth)])
def delete_item_page(
    request: Request,
    item_id: int,
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _safe_next_url(next_url)
    item = db.get(Item, item_id)
    if item is None:
        add_flash(request, "error", "flash.item_delete_failed")
        return _redirect(target)
    db.delete(item)
    db.commit()
    add_flash(request, "success", "flash.item_deleted")
    return _redirect(target)


@router.post("/items/{item_id}/state", dependencies=[Depends(require_page_auth)])
def set_item_state_page(
    request: Request,
    item_id: int,
    status_value: str | None = Form(default=None),
    rating: str | None = Form(default=None),
    review: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    try:
        save_item_state(db, item_id, status_value, rating, review)
    except ItemDetailError as exc:
        add_flash(request, "error", f"flash.detail_{exc.code}")
        return _redirect(target)
    safe_record_item_edit(db, item_id)
    add_flash(request, "success", "flash.detail_state_updated")
    return _redirect(target)


@router.post("/items/{item_id}/state/delete", dependencies=[Depends(require_page_auth)])
def delete_item_state_page(
    request: Request,
    item_id: int,
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    item = get_item_or_404(db, item_id)
    delete_state(db, item)
    safe_record_item_edit(db, item_id)
    add_flash(request, "info", "flash.state_cleared")
    return _redirect(_item_detail_url(item_id, next_url))


@router.post("/items/{item_id}/tags", dependencies=[Depends(require_page_auth)])
def add_item_tag_page(
    request: Request,
    item_id: int,
    tag_id: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    try:
        add_existing_tag(db, item_id, tag_id)
    except ItemDetailError as exc:
        add_flash(request, "error", f"flash.detail_{exc.code}")
        return _redirect(target)
    safe_record_item_edit(db, item_id)
    add_flash(request, "success", "flash.detail_tag_added")
    return _redirect(target)


@router.post("/items/{item_id}/tags/{tag_id}/delete", dependencies=[Depends(require_page_auth)])
def remove_item_tag_page(
    request: Request,
    item_id: int,
    tag_id: int,
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    try:
        remove_existing_tag(db, item_id, tag_id)
    except ItemDetailError as exc:
        add_flash(request, "error", f"flash.detail_{exc.code}")
        return _redirect(target)
    safe_record_item_edit(db, item_id)
    add_flash(request, "success", "flash.detail_tag_removed")
    return _redirect(target)


@router.post("/items/{item_id}/creators", dependencies=[Depends(require_page_auth)])
def add_item_creator_page(
    request: Request,
    item_id: int,
    creator_id: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    try:
        add_existing_creator(db, item_id, creator_id)
    except ItemDetailError as exc:
        add_flash(request, "error", f"flash.detail_{exc.code}")
        return _redirect(target)
    safe_record_item_edit(db, item_id)
    add_flash(request, "success", "flash.detail_creator_added")
    return _redirect(target)


@router.post(
    "/items/{item_id}/creators/{creator_id}/delete",
    dependencies=[Depends(require_page_auth)],
)
def remove_item_creator_page(
    request: Request,
    item_id: int,
    creator_id: int,
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    try:
        remove_existing_creator(db, item_id, creator_id)
    except ItemDetailError as exc:
        add_flash(request, "error", f"flash.detail_{exc.code}")
        return _redirect(target)
    safe_record_item_edit(db, item_id)
    add_flash(request, "success", "flash.detail_creator_removed")
    return _redirect(target)


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


@router.get(
    "/collections",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def collections_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "collections.html",
        _base_context(request, collection_rows=list_collection_rows(db)),
    )


@router.get(
    "/collections/new",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def new_collection_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "collection_form.html",
        _base_context(
            request,
            collection=None,
            action="/collections",
            mode_key="collections.create_title",
        ),
    )


@router.post("/collections", dependencies=[Depends(require_page_auth)])
def create_collection_page(
    request: Request,
    name: str | None = Form(default=None),
    description: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        collection = create_collection(db, name=name, description=description)
    except CollectionError as exc:
        add_flash(request, "error", f"flash.collection_{exc.code}")
        return _redirect("/collections/new")
    add_flash(request, "success", "flash.collection_created")
    return _redirect(f"/collections/{collection.id}")


@router.get(
    "/collections/{collection_id}/edit",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def edit_collection_page(
    request: Request,
    collection_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        collection = get_collection(db, collection_id)
    except CollectionError as exc:
        raise HTTPException(status_code=404, detail="Collection not found") from exc
    return templates.TemplateResponse(
        request,
        "collection_form.html",
        _base_context(
            request,
            collection=collection,
            action=f"/collections/{collection.id}/edit",
            mode_key="collections.edit_title",
        ),
    )


@router.post("/collections/{collection_id}/edit", dependencies=[Depends(require_page_auth)])
def update_collection_page(
    request: Request,
    collection_id: int,
    name: str | None = Form(default=None),
    description: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        collection = update_collection(
            db,
            collection_id,
            name=name,
            description=description,
        )
    except CollectionError as exc:
        add_flash(request, "error", f"flash.collection_{exc.code}")
        return _redirect(f"/collections/{collection_id}/edit")
    add_flash(request, "success", "flash.collection_updated")
    return _redirect(f"/collections/{collection.id}")


@router.post("/collections/{collection_id}/delete", dependencies=[Depends(require_page_auth)])
def delete_collection_page(
    request: Request,
    collection_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        delete_collection(db, collection_id)
    except CollectionError as exc:
        add_flash(request, "error", f"flash.collection_{exc.code}")
    else:
        add_flash(request, "success", "flash.collection_deleted")
    return _redirect("/collections")


@router.get(
    "/collections/{collection_id}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def collection_detail_page(
    request: Request,
    collection_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        collection = get_collection(db, collection_id)
        available_items = list_available_items_for_collection(db, collection_id)
    except CollectionError as exc:
        raise HTTPException(status_code=404, detail="Collection not found") from exc
    return templates.TemplateResponse(
        request,
        "collection_detail.html",
        _base_context(
            request,
            collection=collection,
            available_items=available_items,
        ),
    )


@router.post("/collections/{collection_id}/items", dependencies=[Depends(require_page_auth)])
def add_collection_item_page(
    request: Request,
    collection_id: int,
    item_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        add_item_to_collection(db, item_id=item_id, collection_id=collection_id)
    except CollectionError as exc:
        add_flash(request, "error", f"flash.collection_{exc.code}")
    else:
        safe_record_item_edit(db, item_id)
        add_flash(request, "success", "flash.collection_item_added")
    return _redirect(f"/collections/{collection_id}")


@router.post(
    "/collections/{collection_id}/items/{item_id}/delete",
    dependencies=[Depends(require_page_auth)],
)
def remove_collection_item_page(
    request: Request,
    collection_id: int,
    item_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        remove_item_from_collection(db, item_id=item_id, collection_id=collection_id)
    except CollectionError as exc:
        add_flash(request, "error", f"flash.collection_{exc.code}")
    else:
        safe_record_item_edit(db, item_id)
        add_flash(request, "success", "flash.collection_item_removed")
    return _redirect(f"/collections/{collection_id}")


@router.post("/items/{item_id}/collections", dependencies=[Depends(require_page_auth)])
def add_item_collection_page(
    request: Request,
    item_id: int,
    collection_id: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    try:
        add_item_to_collection(db, item_id=item_id, collection_id=collection_id)
    except CollectionError as exc:
        add_flash(request, "error", f"flash.collection_{exc.code}")
        return _redirect(target)
    safe_record_item_edit(db, item_id)
    add_flash(request, "success", "flash.collection_item_added")
    return _redirect(target)


@router.post(
    "/items/{item_id}/collections/{collection_id}/delete",
    dependencies=[Depends(require_page_auth)],
)
def remove_item_collection_page(
    request: Request,
    item_id: int,
    collection_id: int,
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    try:
        remove_item_from_collection(db, item_id=item_id, collection_id=collection_id)
    except CollectionError as exc:
        add_flash(request, "error", f"flash.collection_{exc.code}")
        return _redirect(target)
    safe_record_item_edit(db, item_id)
    add_flash(request, "success", "flash.collection_item_removed")
    return _redirect(target)


@router.get("/stats", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def stats_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "stats.html",
        _base_context(request, stats=build_stats_dashboard(db)),
    )


@router.get(
    "/import",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def import_page(request: Request) -> HTMLResponse:
    return _import_template(request)


def _import_field_specs() -> list[dict[str, Any]]:
    return [
        {"name": "title", "required": True},
        {"name": "summary", "required": False},
        {"name": "status", "required": False},
        {"name": "rating", "required": False},
        {"name": "note", "required": False},
        {"name": "tags", "required": False},
        {"name": "creators", "required": False},
        {"name": "collections", "required": False},
        {"name": "extra", "required": False},
    ]


def _import_error_message(request: Request, code: str) -> str:
    return translate(get_language(request), f"import.error_{code}")


def _import_template(
    request: Request,
    result: dict[str, Any] | None = None,
    preview: dict[str, Any] | None = None,
    import_error: str | None = None,
) -> HTMLResponse:
    raw_rows = preview["raw_rows"] if preview else []
    return templates.TemplateResponse(
        request,
        "import.html",
        _base_context(
            request,
            result=result,
            preview=preview,
            payload_json=json.dumps(raw_rows, ensure_ascii=False),
            import_fields=IMPORT_FIELDS,
            target_fields=TARGET_FIELDS,
            import_field_specs=_import_field_specs(),
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
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    if file is None:
        return _import_template(
            request,
            import_error=_import_error_message(request, "missing_file"),
        )
    if not (file.filename or "").lower().endswith(".csv"):
        return _import_template(
            request,
            import_error=_import_error_message(request, "unsupported_file_type"),
        )
    try:
        preview = preview_csv_import(db, await file.read())
        return _import_template(request, preview=preview)
    except ImportDataError as exc:
        return _import_template(
            request,
            import_error=_import_error_message(request, exc.code),
        )


@router.post(
    "/import/json",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
async def import_json_page(
    request: Request,
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    if file is None:
        return _import_template(
            request,
            import_error=_import_error_message(request, "missing_file"),
        )
    if not (file.filename or "").lower().endswith(".json"):
        return _import_template(
            request,
            import_error=_import_error_message(request, "unsupported_file_type"),
        )
    try:
        preview = preview_json_import(db, await file.read())
        return _import_template(request, preview=preview)
    except ImportDataError as exc:
        return _import_template(
            request,
            import_error=_import_error_message(request, exc.code),
        )


@router.post(
    "/import/confirm",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def import_confirm_page(
    request: Request,
    payload_json: str = Form(...),
    source_type: str = Form(default="json"),
    source_header: list[str] | None = Form(default=None),
    target_field: list[str] | None = Form(default=None),
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

    if source_type == "csv":
        headers = source_header or []
        targets = target_field or []
        mapping = build_mapping(headers, targets)
        preview = preview_csv_rows(db, clean_rows, headers, mapping)
    else:
        preview = preview_json_rows(db, clean_rows)

    if not preview["valid_rows"]:
        return _import_template(
            request,
            preview=preview,
            import_error=_import_error_message(request, "no_importable_rows"),
        )

    result = import_valid_rows(db, preview["valid_rows"], preview["errors"])
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
    validation_report: dict[str, Any] | None = None,
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
            validation_report=validation_report,
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
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        payload = await _read_backup_upload_for_page(request, file)
        report = validate_backup_payload(payload, db).to_dict()
        preview_result = None
        if report["error_count"] == 0:
            try:
                preview_result = preview_backup_data(payload, db)
            except BackupError as exc:
                return _backup_template(
                    request,
                    validation_report=report,
                    preview_error=_backup_error_message(request, exc.code),
                )
        return _backup_template(
            request,
            preview_result=preview_result,
            validation_report=report,
        )
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
