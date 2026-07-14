from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urlencode

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
from sqlalchemy.orm import Session, noload, selectinload

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
    get_collection_detail_page,
    list_available_collections_for_item,
    list_collection_rows,
    remove_item_from_collection,
    update_collection,
)
from app.services.data_health import build_data_health_report
from app.services.data_health_fixes import (
    DataHealthFixError,
    apply_data_health_fix,
    build_data_health_fix_options,
)
from app.services.danger import (
    DangerConfirmationError,
    DangerPolicy,
    danger_policy_from_settings,
    get_danger_policy,
    require_danger_confirmation,
)
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
    read_import_upload,
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
from app.services.local_media import (
    MAX_MEDIA_UPLOAD_BYTES,
    MAX_MEDIA_UPLOAD_FILES,
    LocalMediaPathError,
    LocalMediaScan,
    LocalMediaUploadError,
    is_cleanup_anchor_filename,
    local_media_url,
    normalize_local_media_path,
    read_local_media_file,
    resolve_local_media_file,
    scan_local_media,
    store_media_uploads,
)
from app.services.media_item_candidates import (
    MediaItemCandidateError,
    create_items_from_media_candidates,
    find_media_item_candidates,
    paginate_media_item_candidates,
)
from app.services.media_duplicate_groups import (
    MEDIA_DUPLICATE_SORT_OPTIONS,
    media_duplicate_filter_query_params,
    query_media_duplicate_groups,
)
from app.services.media_duplicate_cleanup import (
    MediaDuplicateCleanupError,
    build_media_duplicate_cleanup_preview,
    execute_media_duplicate_cleanup,
)
from app.services.media_damaged_cleanup import (
    MediaDamagedCleanupError,
    build_media_damaged_cleanup_preview,
    execute_media_damaged_cleanup,
)
from app.services.media_root_diagnostics import (
    MediaRootDiagnosticError,
    build_media_root_diagnostic,
    execute_media_root_initialization,
)
from app.services.media_cleanup_recovery import (
    MEDIA_RECOVERY_SORT_OPTIONS,
    MEDIA_RECOVERY_STATUS_OPTIONS,
    media_recovery_filter_query_params,
    query_media_cleanup_recovery,
)
from app.services.media_cleanup_delete import (
    MediaCleanupDeleteError,
    build_media_cleanup_delete_preview,
    execute_media_cleanup_delete,
)
from app.services.media_cleanup_restore import (
    MediaCleanupRestoreError,
    build_media_cleanup_restore_preview,
    execute_media_cleanup_restore,
)
from app.services.media_library_query import (
    MEDIA_SORT_OPTIONS,
    MEDIA_STATUS_OPTIONS,
    media_filter_query_params,
    normalize_media_list_filters,
    query_media_library,
)
from app.services.media_matching import (
    MediaMatchError,
    apply_local_media_matches,
    match_local_media,
    paginate_media_matches,
)
from app.services.media_reference_repair import (
    MediaReferenceRepairError,
    build_media_reference_repair_preview,
    execute_media_reference_repair,
    is_repairable_media_reference_issue,
)
from app.services.media_scan_skips import (
    MEDIA_SCAN_SKIP_SORT_OPTIONS,
    MEDIA_SCAN_SKIP_TYPE_OPTIONS,
    media_scan_skip_filter_query_params,
    query_media_scan_skips,
)
from app.services.media_upload_residue_cleanup import (
    MediaUploadResidueCleanupError,
    build_media_upload_residue_cleanup_preview,
    execute_media_upload_residue_cleanup,
)
from app.services.metadata_cleanup import (
    MetadataCleanupError,
    find_metadata_cleanup_candidates,
    get_metadata_comparison,
    merge_metadata_objects,
)
from app.services.metadata_lists import list_creator_page, list_tag_page
from app.services.pagination import PageInfo, parse_page
from app.services.migrations import (
    MIGRATION_REGISTRY,
    MigrationError,
    UpgradeDryRun,
    apply_upgrade,
    build_upgrade_plan,
    preview_upgrade,
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
from app.services.schema_version import get_schema_status
from app.services.settings import (
    AppSettings,
    AppSettingsError,
    SETTING_OPTIONS,
    get_app_settings,
    reset_app_settings,
    save_app_settings,
)
from app.services.sources import (
    SourceError,
    add_item_source,
    build_source_preview,
    delete_item_source,
    import_source_rows,
    list_item_sources,
    parse_bookmarks_html,
    parse_source_text,
    source_feature_available,
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
from app.security import safe_local_path

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _safe_next_url(next_url: str | None) -> str:
    return safe_local_path(next_url, fallback="/items")


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


def _base_context(
    request: Request,
    db: Session | None = None,
    settings: AppSettings | None = None,
    **values: Any,
) -> dict[str, Any]:
    resolved_settings = settings
    if resolved_settings is None:
        value_settings = values.get("app_settings")
        if isinstance(value_settings, AppSettings):
            resolved_settings = value_settings
        elif db is not None:
            resolved_settings = get_app_settings(db)
    default_language = (
        resolved_settings.default_language if resolved_settings is not None else None
    )
    language = get_language(request, default_language=default_language)
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
        "local_media_url": local_media_url,
        "max_backup_upload_mb": get_settings().max_backup_upload_mb,
        "max_import_upload_mb": get_settings().max_import_upload_mb,
        "danger_policy": (
            danger_policy_from_settings(resolved_settings)
            if resolved_settings is not None
            else DangerPolicy()
        ),
        "flash_messages": pop_flash_messages(request, language),
    }
    context.update(values)
    return context


def _danger_confirmation_is_valid(
    request: Request,
    policy: DangerPolicy,
    *,
    confirmation_text: str | None,
    base_confirmation_valid: bool,
) -> bool:
    try:
        require_danger_confirmation(
            policy,
            confirmation_text=confirmation_text,
            base_confirmation_valid=base_confirmation_valid,
        )
    except DangerConfirmationError as exc:
        add_flash(request, "error", f"flash.danger_{exc.code}")
        return False
    return True


def _parse_extra_json(value: str | None) -> dict[str, Any] | None:
    if value is None or not value.strip():
        return None
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("extra must be a JSON object")
    return payload


@router.get(
    "/media/{media_path:path}",
    response_class=Response,
    dependencies=[Depends(require_page_auth)],
)
def local_media_file_page(media_path: str) -> Response:
    try:
        content, media_type = read_local_media_file(media_path)
    except LocalMediaPathError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    return Response(content=content, media_type=media_type)


@router.get(
    "/media-library",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_library_page(
    request: Request,
    match_page: str | None = Query(default=None),
    create_page: str | None = Query(default=None),
    media_page: str | None = Query(default=None),
    media_q: str | None = Query(default=None),
    media_status: str | None = Query(default=None),
    media_sort: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    error_key = None
    try:
        scan = scan_local_media()
    except LocalMediaPathError:
        scan = LocalMediaScan((), 0, 0, 0)
        error_key = "media.error_storage_unavailable"
    items = list(db.scalars(select(Item).order_by(Item.title, Item.id)).all())
    creators = list(db.scalars(select(Creator).order_by(Creator.name, Creator.id)).all())
    item_references: dict[str, list[Item]] = {}
    creator_references: dict[str, list[Creator]] = {}
    for item in items:
        if item.cover_path:
            item_references.setdefault(item.cover_path, []).append(item)
    for creator in creators:
        if creator.avatar_path:
            creator_references.setdefault(creator.avatar_path, []).append(creator)
    used_media_paths = {*item_references, *creator_references}
    match_scan = match_local_media(scan, items, creators)
    candidate_page = paginate_media_matches(match_scan, match_page)
    item_candidate_scan = find_media_item_candidates(scan, items, creators)
    item_candidate_page = paginate_media_item_candidates(
        item_candidate_scan,
        create_page,
    )
    media_result = query_media_library(
        scan,
        used_media_paths,
        q=media_q,
        status=media_status,
        sort=media_sort,
        page=media_page,
    )
    damaged_cleanup_preview_urls = {
        row.entry.media_path: (
            "/data-health/damaged-media/delete-preview?"
            + urlencode(
                {
                    "media_path": row.entry.media_path,
                    "sha256": row.entry.sha256,
                }
            )
        )
        for row in media_result.rows
        if not row.entry.available
        and bool(row.entry.sha256)
        and not row.entry.is_cleanup_anchor
    }
    media_params = {
        **media_filter_query_params(media_result.filters),
        "media_page": media_result.page_info.page,
    }
    return templates.TemplateResponse(
        request,
        "media_library.html",
        _base_context(
            request,
            db=db,
            scan=scan,
            items=items,
            creators=creators,
            item_references=item_references,
            creator_references=creator_references,
            match_scan=match_scan,
            match_candidates=candidate_page.rows,
            match_pagination=_page_context(
                candidate_page.page_info,
                "/media-library",
                page_param="match_page",
                params={
                    **media_params,
                    "create_page": item_candidate_page.page_info.page,
                },
            ),
            item_candidate_scan=item_candidate_scan,
            item_candidates=item_candidate_page.rows,
            item_candidate_pagination=_page_context(
                item_candidate_page.page_info,
                "/media-library",
                page_param="create_page",
                params={
                    **media_params,
                    "match_page": candidate_page.page_info.page,
                },
            ),
            media_rows=media_result.rows,
            media_filters=media_result.filters,
            media_duplicate_summary=media_result.duplicate_summary,
            media_status_options=MEDIA_STATUS_OPTIONS,
            media_sort_options=MEDIA_SORT_OPTIONS,
            media_pagination=_page_context(
                media_result.page_info,
                "/media-library",
                page_param="media_page",
                params={
                    **media_filter_query_params(media_result.filters),
                    "match_page": candidate_page.page_info.page,
                    "create_page": item_candidate_page.page_info.page,
                },
            ),
            damaged_cleanup_preview_urls=damaged_cleanup_preview_urls,
            max_media_upload_mb=MAX_MEDIA_UPLOAD_BYTES // (1024 * 1024),
            max_media_upload_files=MAX_MEDIA_UPLOAD_FILES,
            error_key=error_key,
        ),
    )


@router.get(
    "/media-library/skipped",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_scan_skips_page(
    request: Request,
    skip_page: str | None = Query(default=None),
    skip_q: str | None = Query(default=None),
    skip_type: str | None = Query(default=None),
    skip_sort: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    error_key = None
    try:
        scan = scan_local_media()
    except LocalMediaPathError:
        scan = LocalMediaScan((), 0, 0, 0)
        error_key = "media.error_storage_unavailable"
    result = query_media_scan_skips(
        scan,
        q=skip_q,
        skip_type=skip_type,
        sort=skip_sort,
        page=skip_page,
    )
    return templates.TemplateResponse(
        request,
        "media_scan_skips.html",
        _base_context(
            request,
            db=db,
            skip_result=result,
            skip_type_options=MEDIA_SCAN_SKIP_TYPE_OPTIONS,
            skip_sort_options=MEDIA_SCAN_SKIP_SORT_OPTIONS,
            skip_pagination=_page_context(
                result.page_info,
                "/media-library/skipped",
                page_param="skip_page",
                params=media_scan_skip_filter_query_params(result.filters),
            ),
            error_key=error_key,
        ),
    )


@router.get(
    "/media-library/recovery",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_cleanup_recovery_page(
    request: Request,
    recovery_page: str | None = Query(default=None),
    recovery_q: str | None = Query(default=None),
    recovery_status: str | None = Query(default=None),
    recovery_sort: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    error_key = None
    try:
        scan = scan_local_media(include_cleanup_anchors=True)
    except LocalMediaPathError:
        scan = LocalMediaScan((), 0, 0, 0)
        error_key = "media.error_storage_unavailable"
    result = query_media_cleanup_recovery(
        db,
        scan,
        q=recovery_q,
        status=recovery_status,
        sort=recovery_sort,
        page=recovery_page,
    )
    recovery_preview_urls = {
        row.entry.media_path: (
            "/media-library/recovery/preview?"
            + urlencode(
                {
                    "media_path": row.entry.media_path,
                    "sha256": row.entry.sha256,
                }
            )
        )
        for row in result.rows
        if row.entry.is_cleanup_anchor
        and row.entry.available
        and row.entry.sha256
    }
    cleanup_delete_preview_urls = {
        row.entry.media_path: (
            "/media-library/recovery/delete-preview?"
            + urlencode(
                {
                    "media_path": row.entry.media_path,
                    "sha256": row.entry.sha256,
                }
            )
        )
        for row in result.rows
        if row.status == "anchor_unreferenced"
        and row.entry.available
        and row.entry.sha256
    }
    return templates.TemplateResponse(
        request,
        "media_cleanup_recovery.html",
        _base_context(
            request,
            db=db,
            recovery_result=result,
            recovery_status_options=MEDIA_RECOVERY_STATUS_OPTIONS,
            recovery_sort_options=MEDIA_RECOVERY_SORT_OPTIONS,
            recovery_preview_urls=recovery_preview_urls,
            cleanup_delete_preview_urls=cleanup_delete_preview_urls,
            recovery_pagination=_page_context(
                result.page_info,
                "/media-library/recovery",
                page_param="recovery_page",
                params=media_recovery_filter_query_params(result.filters),
            ),
            error_key=error_key,
        ),
    )


def _media_cleanup_restore_preview_url(
    media_path: str | None,
    sha256: str | None,
) -> str:
    return "/media-library/recovery/preview?" + urlencode(
        {"media_path": media_path or "", "sha256": sha256 or ""}
    )


@router.get(
    "/media-library/recovery/preview",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_cleanup_restore_preview_page(
    request: Request,
    media_path: str | None = Query(default=None),
    sha256: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    preview = None
    error_key = None
    try:
        preview = build_media_cleanup_restore_preview(
            db,
            media_path=media_path,
            sha256=sha256,
        )
    except MediaCleanupRestoreError as exc:
        error_key = f"media_cleanup_restore.error_{exc.code}"
    return templates.TemplateResponse(
        request,
        "media_cleanup_restore_preview.html",
        _base_context(
            request,
            db=db,
            restore_preview=preview,
            error_key=error_key,
        ),
        status_code=200 if preview is not None else 400,
    )


@router.post(
    "/media-library/recovery/restore",
    dependencies=[Depends(require_page_auth)],
)
def media_cleanup_restore_page(
    request: Request,
    media_path: str = Form(...),
    sha256: str = Form(...),
    expected_size: str = Form(...),
    expected_device: str = Form(...),
    expected_inode: str = Form(...),
    expected_modified_ns: str = Form(...),
    expected_changed_ns: str = Form(...),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    preview_url = _media_cleanup_restore_preview_url(media_path, sha256)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(preview_url)
    try:
        result = execute_media_cleanup_restore(
            db,
            media_path=media_path,
            sha256=sha256,
            expected_size=expected_size,
            expected_device=expected_device,
            expected_inode=expected_inode,
            expected_modified_ns=expected_modified_ns,
            expected_changed_ns=expected_changed_ns,
        )
    except MediaCleanupRestoreError as exc:
        add_flash(
            request,
            "error",
            f"flash.media_cleanup_restore_{exc.code}",
        )
        return _redirect("/media-library/recovery")
    add_flash(
        request,
        "success",
        "flash.media_cleanup_restore_success",
        recovered_path=result.recovered_path,
        items=result.migrated_items,
        creators=result.migrated_creators,
    )
    if not result.anchor_removed:
        add_flash(
            request,
            "info",
            "flash.media_cleanup_restore_anchor_retained",
            anchor_path=result.anchor_retained_path or result.anchor_path,
            code=result.anchor_removal_code or "delete_failed",
        )
    elif result.anchor_removal_code:
        add_flash(
            request,
            "info",
            "flash.media_cleanup_restore_anchor_warning",
            code=result.anchor_removal_code,
        )
    return _redirect("/media-library/recovery")


def _media_cleanup_delete_preview_url(
    media_path: str | None,
    sha256: str | None,
) -> str:
    return "/media-library/recovery/delete-preview?" + urlencode(
        {"media_path": media_path or "", "sha256": sha256 or ""}
    )


@router.get(
    "/media-library/recovery/delete-preview",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_cleanup_delete_preview_page(
    request: Request,
    media_path: str | None = Query(default=None),
    sha256: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    preview = None
    error_key = None
    try:
        preview = build_media_cleanup_delete_preview(
            db,
            media_path=media_path,
            sha256=sha256,
        )
    except MediaCleanupDeleteError as exc:
        error_key = f"media_cleanup_delete.error_{exc.code}"
    return templates.TemplateResponse(
        request,
        "media_cleanup_delete_preview.html",
        _base_context(
            request,
            db=db,
            delete_preview=preview,
            error_key=error_key,
        ),
        status_code=200 if preview is not None else 400,
    )


@router.post(
    "/media-library/recovery/delete",
    dependencies=[Depends(require_page_auth)],
)
def media_cleanup_delete_page(
    request: Request,
    media_path: str = Form(...),
    sha256: str = Form(...),
    expected_size: str = Form(...),
    expected_device: str = Form(...),
    expected_inode: str = Form(...),
    expected_modified_ns: str = Form(...),
    expected_changed_ns: str = Form(...),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    preview_url = _media_cleanup_delete_preview_url(media_path, sha256)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(preview_url)
    try:
        result = execute_media_cleanup_delete(
            db,
            media_path=media_path,
            sha256=sha256,
            expected_size=expected_size,
            expected_device=expected_device,
            expected_inode=expected_inode,
            expected_modified_ns=expected_modified_ns,
            expected_changed_ns=expected_changed_ns,
        )
    except MediaCleanupDeleteError as exc:
        add_flash(
            request,
            "error",
            f"flash.media_cleanup_delete_{exc.code}",
        )
        return _redirect("/media-library/recovery")
    add_flash(
        request,
        "success",
        "flash.media_cleanup_delete_success",
        deleted_path=result.deleted_path,
        size=result.size,
    )
    if result.warning_code:
        add_flash(
            request,
            "info",
            "flash.media_cleanup_delete_warning",
            code=result.warning_code,
        )
    return _redirect("/media-library/recovery")


@router.get(
    "/media-library/duplicates",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_duplicate_groups_page(
    request: Request,
    duplicate_page: str | None = Query(default=None),
    duplicate_q: str | None = Query(default=None),
    duplicate_sort: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    error_key = None
    try:
        scan = scan_local_media()
    except LocalMediaPathError:
        scan = LocalMediaScan((), 0, 0, 0)
        error_key = "media.error_storage_unavailable"
    result = query_media_duplicate_groups(
        scan,
        q=duplicate_q,
        sort=duplicate_sort,
        page=duplicate_page,
    )
    media_paths = {
        entry.media_path
        for group in result.groups
        for entry in group.entries
    }
    item_references: dict[str, list[Any]] = {}
    creator_references: dict[str, list[Any]] = {}
    if media_paths:
        item_rows = db.execute(
            select(Item.id, Item.title, Item.cover_path)
            .where(Item.cover_path.in_(media_paths))
            .order_by(Item.title, Item.id)
        ).all()
        creator_rows = db.execute(
            select(Creator.id, Creator.name, Creator.avatar_path)
            .where(Creator.avatar_path.in_(media_paths))
            .order_by(Creator.name, Creator.id)
        ).all()
        for item in item_rows:
            item_references.setdefault(item.cover_path, []).append(item)
        for creator in creator_rows:
            creator_references.setdefault(creator.avatar_path, []).append(creator)
    library_urls = {
        group.sha256: "/media-library?"
        + urlencode(
            {
                "media_q": group.sha256,
                "media_status": "duplicate",
            }
        )
        + "#media-files"
        for group in result.groups
    }
    return templates.TemplateResponse(
        request,
        "media_duplicate_groups.html",
        _base_context(
            request,
            db=db,
            duplicate_groups=result.groups,
            duplicate_filters=result.filters,
            duplicate_sort_options=MEDIA_DUPLICATE_SORT_OPTIONS,
            duplicate_total_groups=result.total_groups,
            duplicate_pagination=_page_context(
                result.page_info,
                "/media-library/duplicates",
                page_param="duplicate_page",
                params=media_duplicate_filter_query_params(result.filters),
            ),
            item_references=item_references,
            creator_references=creator_references,
            media_library_urls=library_urls,
            error_key=error_key,
        ),
    )


def _media_duplicate_cleanup_preview_url(
    sha256: str | None,
    keeper_path: str | None,
) -> str:
    return "/media-library/duplicates/organize?" + urlencode(
        {
            "sha256": sha256 or "",
            "keeper_path": keeper_path or "",
        }
    )


def _media_duplicate_cleanup_error_flash(
    request: Request,
    exc: MediaDuplicateCleanupError,
) -> None:
    add_flash(request, "error", f"flash.media_duplicate_cleanup_{exc.code}")


@router.get(
    "/media-library/duplicates/organize",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_duplicate_cleanup_preview_page(
    request: Request,
    sha256: str | None = Query(default=None),
    keeper_path: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Response:
    try:
        preview = build_media_duplicate_cleanup_preview(
            db,
            sha256=sha256,
            keeper_path=keeper_path,
        )
    except MediaDuplicateCleanupError as exc:
        _media_duplicate_cleanup_error_flash(request, exc)
        return _redirect("/media-library/duplicates")
    return templates.TemplateResponse(
        request,
        "media_duplicate_cleanup_preview.html",
        _base_context(request, db=db, preview=preview),
    )


@router.post(
    "/media-library/duplicates/organize/apply",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_duplicate_cleanup_apply_page(
    request: Request,
    sha256: str = Form(...),
    keeper_path: str = Form(...),
    member_path: list[str] | None = Form(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> Response:
    danger_policy = get_danger_policy(db)
    preview_url = _media_duplicate_cleanup_preview_url(sha256, keeper_path)
    if not _danger_confirmation_is_valid(
        request,
        danger_policy,
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(preview_url)
    try:
        result = execute_media_duplicate_cleanup(
            db,
            sha256=sha256,
            keeper_path=keeper_path,
            expected_member_paths=member_path,
        )
    except MediaDuplicateCleanupError as exc:
        _media_duplicate_cleanup_error_flash(request, exc)
        return _redirect("/media-library/duplicates")
    return templates.TemplateResponse(
        request,
        "media_duplicate_cleanup_result.html",
        _base_context(
            request,
            db=db,
            result=result,
            show_detailed_results=danger_policy.show_detailed_results,
        ),
    )


@router.post("/media-library/upload", dependencies=[Depends(require_page_auth)])
async def media_library_upload_page(
    request: Request,
    files: list[UploadFile] | None = File(default=None),
    match_page: str | None = Form(default=None),
    create_page: str | None = Form(default=None),
    media_page: str | None = Form(default=None),
    media_q: str | None = Form(default=None),
    media_status: str | None = Form(default=None),
    media_sort: str | None = Form(default=None),
) -> RedirectResponse:
    try:
        result = await store_media_uploads(files or [])
    except LocalMediaUploadError as exc:
        add_flash(request, "error", f"flash.media_{exc.code}")
    else:
        add_flash(
            request,
            "success",
            "flash.media_uploaded",
            uploaded=result.uploaded,
            duplicate=result.duplicate,
        )
    return _media_library_redirect(
        match_page=match_page,
        create_page=create_page,
        media_page=media_page,
        media_q=media_q,
        media_status=media_status,
        media_sort=media_sort,
    )


def _media_library_redirect(
    *,
    match_page: str | int | None,
    create_page: str | int | None,
    media_page: str | int | None,
    media_q: str | None,
    media_status: str | None,
    media_sort: str | None,
) -> RedirectResponse:
    filters = normalize_media_list_filters(
        q=media_q,
        status=media_status,
        sort=media_sort,
    )
    return _redirect(
        "/media-library?"
        + urlencode(
            {
                "match_page": parse_page(match_page),
                "create_page": parse_page(create_page),
                "media_page": parse_page(media_page),
                **media_filter_query_params(filters),
            }
        )
    )


def _apply_media_match_candidates(
    request: Request,
    db: Session,
    candidate_ids: list[str],
    *,
    match_page: str | None,
    create_page: str | None,
    media_page: str | None,
    media_q: str | None,
    media_status: str | None,
    media_sort: str | None,
    confirm: str | None,
    confirmation_text: str | None,
) -> RedirectResponse:
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _media_library_redirect(
            match_page=match_page,
            create_page=create_page,
            media_page=media_page,
            media_q=media_q,
            media_status=media_status,
            media_sort=media_sort,
        )
    try:
        result = apply_local_media_matches(
            db,
            candidate_ids,
            current_page=match_page,
        )
    except MediaMatchError as exc:
        add_flash(request, "error", f"flash.media_match_{exc.code}")
    else:
        add_flash(
            request,
            "success",
            "flash.media_match_applied",
            applied=result.applied,
        )
    return _media_library_redirect(
        match_page=match_page,
        create_page=create_page,
        media_page=media_page,
        media_q=media_q,
        media_status=media_status,
        media_sort=media_sort,
    )


@router.post(
    "/media-library/matches/apply",
    dependencies=[Depends(require_page_auth)],
)
def media_library_apply_match_page(
    request: Request,
    candidate_id: str = Form(...),
    match_page: str = Form(...),
    create_page: str | None = Form(default=None),
    media_page: str | None = Form(default=None),
    media_q: str | None = Form(default=None),
    media_status: str | None = Form(default=None),
    media_sort: str | None = Form(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return _apply_media_match_candidates(
        request,
        db,
        [candidate_id],
        match_page=match_page,
        create_page=create_page,
        media_page=media_page,
        media_q=media_q,
        media_status=media_status,
        media_sort=media_sort,
        confirm=confirm,
        confirmation_text=confirmation_text,
    )


@router.post(
    "/media-library/matches/apply-bulk",
    dependencies=[Depends(require_page_auth)],
)
def media_library_apply_matches_bulk_page(
    request: Request,
    candidate_ids: list[str] | None = Form(default=None),
    match_page: str = Form(...),
    create_page: str | None = Form(default=None),
    media_page: str | None = Form(default=None),
    media_q: str | None = Form(default=None),
    media_status: str | None = Form(default=None),
    media_sort: str | None = Form(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return _apply_media_match_candidates(
        request,
        db,
        candidate_ids or [],
        match_page=match_page,
        create_page=create_page,
        media_page=media_page,
        media_q=media_q,
        media_status=media_status,
        media_sort=media_sort,
        confirm=confirm,
        confirmation_text=confirmation_text,
    )


def _create_media_items_from_candidates(
    request: Request,
    db: Session,
    candidate_ids: list[str],
    titles: list[str],
    *,
    match_page: str | None,
    create_page: str,
    media_page: str | None,
    media_q: str | None,
    media_status: str | None,
    media_sort: str | None,
    confirm: str | None,
    confirmation_text: str | None,
) -> RedirectResponse:
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _media_library_redirect(
            match_page=match_page,
            create_page=create_page,
            media_page=media_page,
            media_q=media_q,
            media_status=media_status,
            media_sort=media_sort,
        )
    try:
        result = create_items_from_media_candidates(
            db,
            candidate_ids,
            titles,
            current_page=create_page,
        )
    except MediaItemCandidateError as exc:
        add_flash(request, "error", f"flash.media_item_candidate_{exc.code}")
    else:
        add_flash(
            request,
            "success",
            "flash.media_item_candidate_created",
            created=result.created,
        )
    return _media_library_redirect(
        match_page=match_page,
        create_page=create_page,
        media_page=media_page,
        media_q=media_q,
        media_status=media_status,
        media_sort=media_sort,
    )


@router.post(
    "/media-library/item-candidates/create",
    dependencies=[Depends(require_page_auth)],
)
def media_library_create_item_candidate_page(
    request: Request,
    candidate_id: str = Form(...),
    title: str = Form(...),
    create_page: str = Form(...),
    match_page: str | None = Form(default=None),
    media_page: str | None = Form(default=None),
    media_q: str | None = Form(default=None),
    media_status: str | None = Form(default=None),
    media_sort: str | None = Form(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return _create_media_items_from_candidates(
        request,
        db,
        [candidate_id],
        [title],
        match_page=match_page,
        create_page=create_page,
        media_page=media_page,
        media_q=media_q,
        media_status=media_status,
        media_sort=media_sort,
        confirm=confirm,
        confirmation_text=confirmation_text,
    )


@router.post(
    "/media-library/item-candidates/create-bulk",
    dependencies=[Depends(require_page_auth)],
)
def media_library_create_item_candidates_bulk_page(
    request: Request,
    candidate_ids: list[str] | None = Form(default=None),
    candidate_titles: list[str] | None = Form(default=None),
    create_page: str = Form(...),
    match_page: str | None = Form(default=None),
    media_page: str | None = Form(default=None),
    media_q: str | None = Form(default=None),
    media_status: str | None = Form(default=None),
    media_sort: str | None = Form(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return _create_media_items_from_candidates(
        request,
        db,
        candidate_ids or [],
        candidate_titles or [],
        match_page=match_page,
        create_page=create_page,
        media_page=media_page,
        media_q=media_q,
        media_status=media_status,
        media_sort=media_sort,
        confirm=confirm,
        confirmation_text=confirmation_text,
    )


def _validated_library_media_path(media_path: str) -> str:
    normalized = normalize_local_media_path(media_path)
    if normalized is None:
        raise LocalMediaPathError("invalid local media path")
    if is_cleanup_anchor_filename(normalized):
        raise LocalMediaPathError("cleanup anchors are internal media")
    resolve_local_media_file(normalized.removeprefix("/media/"))
    return normalized


@router.post(
    "/media-library/set-item-cover",
    dependencies=[Depends(require_page_auth)],
)
def media_library_set_item_cover_page(
    request: Request,
    item_id: int = Form(...),
    media_path: str = Form(...),
    match_page: str | None = Form(default=None),
    create_page: str | None = Form(default=None),
    media_page: str | None = Form(default=None),
    media_q: str | None = Form(default=None),
    media_status: str | None = Form(default=None),
    media_sort: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    item = db.get(Item, item_id)
    try:
        normalized = _validated_library_media_path(media_path)
        if item is None:
            raise LocalMediaPathError("item not found")
        item.cover_path = normalized
        db.commit()
    except (LocalMediaPathError, OSError):
        db.rollback()
        add_flash(request, "error", "flash.media_assignment_failed")
    else:
        add_flash(request, "success", "flash.media_cover_set")
    return _media_library_redirect(
        match_page=match_page,
        create_page=create_page,
        media_page=media_page,
        media_q=media_q,
        media_status=media_status,
        media_sort=media_sort,
    )


@router.post(
    "/media-library/set-creator-avatar",
    dependencies=[Depends(require_page_auth)],
)
def media_library_set_creator_avatar_page(
    request: Request,
    creator_id: int = Form(...),
    media_path: str = Form(...),
    match_page: str | None = Form(default=None),
    create_page: str | None = Form(default=None),
    media_page: str | None = Form(default=None),
    media_q: str | None = Form(default=None),
    media_status: str | None = Form(default=None),
    media_sort: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    creator = db.get(Creator, creator_id)
    try:
        normalized = _validated_library_media_path(media_path)
        if creator is None:
            raise LocalMediaPathError("creator not found")
        creator.avatar_path = normalized
        db.commit()
    except (LocalMediaPathError, OSError):
        db.rollback()
        add_flash(request, "error", "flash.media_assignment_failed")
    else:
        add_flash(request, "success", "flash.media_avatar_set")
    return _media_library_redirect(
        match_page=match_page,
        create_page=create_page,
        media_page=media_page,
        media_q=media_q,
        media_status=media_status,
        media_sort=media_sort,
    )


@router.post("/items/{item_id}/cover/clear", dependencies=[Depends(require_page_auth)])
def clear_item_cover_page(
    request: Request,
    item_id: int,
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    item = db.get(Item, item_id)
    if item is None:
        add_flash(request, "error", "flash.media_assignment_failed")
        return _redirect("/items")
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(f"/items/{item_id}")
    item.cover_path = None
    db.commit()
    add_flash(request, "success", "flash.media_cover_cleared")
    return _redirect(f"/items/{item_id}")


@router.post(
    "/creators/{creator_id}/avatar/clear",
    dependencies=[Depends(require_page_auth)],
)
def clear_creator_avatar_page(
    request: Request,
    creator_id: int,
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    creator = db.get(Creator, creator_id)
    if creator is None:
        add_flash(request, "error", "flash.media_assignment_failed")
        return _redirect("/creators")
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(f"/creators/{creator_id}")
    creator.avatar_path = None
    db.commit()
    add_flash(request, "success", "flash.media_avatar_cleared")
    return _redirect(f"/creators/{creator_id}")


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
def login_page(request: Request, db: Session = Depends(get_db)) -> Response:
    if is_authenticated(request):
        return _redirect("/")
    return templates.TemplateResponse(
        request,
        "login.html",
        _base_context(request, db=db, error=request.query_params.get("error")),
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
    target = safe_local_path(next, fallback="/")
    return _redirect(target)


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def index_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    app_settings = get_app_settings(db)
    recent_items = db.scalars(
        select(Item)
        .options(
            selectinload(Item.tags).noload(Tag.items),
            selectinload(Item.creators).noload(Creator.items),
            selectinload(Item.state),
            noload(Item.collections),
            noload(Item.activity),
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
            db=db,
            recent_items=recent_items,
            recent_viewed=list_recently_viewed(db, limit=4),
            recent_edited=list_recently_edited(db, limit=4),
            saved_views=list_saved_views(db, limit=4),
            totals=totals,
            settings=app_settings,
            default_home=app_settings.default_home,
            default_home_url=app_settings.default_home_url,
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


def _page_context(
    page_info: PageInfo,
    base_path: str,
    *,
    page_param: str = "page",
    params: dict[str, str | int | None] | None = None,
) -> dict[str, Any]:
    base_params = {
        key: str(value)
        for key, value in (params or {}).items()
        if value not in {None, ""}
    }

    def page_url(page_number: int) -> str:
        query = {**base_params, page_param: str(page_number)}
        return f"{base_path}?{urlencode(query)}"

    return {
        "page": page_info.page,
        "page_size": page_info.page_size,
        "total": page_info.total,
        "total_pages": page_info.total_pages,
        "start": page_info.start,
        "end": page_info.end,
        "has_prev": page_info.has_prev,
        "has_next": page_info.has_next,
        "prev_url": page_url(page_info.page - 1),
        "next_url": page_url(page_info.page + 1),
        "page_urls": [
            {"page": page_number, "url": page_url(page_number)}
            for page_number in page_info.page_numbers
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
    app_settings = get_app_settings(db)
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
        sort=sort if sort is not None else app_settings.item_list_sort,
        page=page,
        page_size=(
            page_size if page_size is not None else str(app_settings.default_page_size)
        ),
    )
    return templates.TemplateResponse(
        request,
        "items.html",
        _base_context(
            request,
            db=db,
            settings=app_settings,
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


@router.get(
    "/settings",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def settings_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "settings.html",
        _base_context(
            request,
            db=db,
            app_settings=get_app_settings(db),
            schema_status=get_schema_status(db.get_bind()),
            setting_options=SETTING_OPTIONS,
        ),
    )


def _schema_upgrade_response(
    request: Request,
    db: Session,
    *,
    dry_run: UpgradeDryRun | None = None,
) -> HTMLResponse:
    danger_policy = get_danger_policy(db)
    return templates.TemplateResponse(
        request,
        "schema_upgrade.html",
        _base_context(
            request,
            db=None,
            danger_policy=danger_policy,
            upgrade_plan=build_upgrade_plan(db.get_bind(), MIGRATION_REGISTRY),
            dry_run=dry_run,
        ),
    )


@router.get(
    "/schema-upgrade",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def schema_upgrade_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return _schema_upgrade_response(request, db)


@router.post(
    "/schema-upgrade/preview",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def schema_upgrade_preview_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    dry_run = preview_upgrade(db.get_bind(), MIGRATION_REGISTRY)
    return _schema_upgrade_response(request, db, dry_run=dry_run)


_SCHEMA_UPGRADE_FLASH_CODES = {
    "apply_failed",
    "backup_confirmation_required",
    "downgrade_not_supported",
    "invalid_postcheck",
    "invalid_precheck",
    "missing_path",
    "no_upgrade_needed",
    "postcheck_failed",
    "precheck_failed",
    "version_record_failed",
    "version_unknown",
}


@router.post(
    "/schema-upgrade/apply",
    dependencies=[Depends(require_page_auth)],
)
def schema_upgrade_apply_page(
    request: Request,
    confirm: str | None = Form(default=None),
    backup_confirmed: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    danger_policy = get_danger_policy(db)
    if not _danger_confirmation_is_valid(
        request,
        danger_policy,
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect("/schema-upgrade")
    if backup_confirmed != "1":
        add_flash(
            request,
            "error",
            "flash.schema_upgrade_backup_confirmation_required",
        )
        return _redirect("/schema-upgrade")

    db.rollback()
    try:
        result = apply_upgrade(
            db.get_bind(),
            MIGRATION_REGISTRY,
            backup_confirmed=True,
        )
    except MigrationError as exc:
        code = exc.code if exc.code in _SCHEMA_UPGRADE_FLASH_CODES else "apply_failed"
        add_flash(request, "error", f"flash.schema_upgrade_{code}")
        return _redirect("/schema-upgrade")

    add_flash(
        request,
        "success",
        "flash.schema_upgrade_applied",
        from_version=result.from_version,
        to_version=result.to_version,
        count=len(result.applied_steps),
    )
    return _redirect("/schema-upgrade")


@router.post("/settings", dependencies=[Depends(require_page_auth)])
async def save_settings_page(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    form = await request.form()
    values = {str(key): str(value) for key, value in form.multi_items()}
    try:
        save_app_settings(db, values)
    except AppSettingsError as exc:
        add_flash(request, "error", f"flash.settings_{exc.code}")
        return _redirect("/settings")
    add_flash(request, "success", "flash.settings_saved")
    return _redirect("/settings")


@router.post("/settings/reset", dependencies=[Depends(require_page_auth)])
def reset_settings_page(
    request: Request,
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    danger_policy = get_danger_policy(db)
    if not _danger_confirmation_is_valid(
        request,
        danger_policy,
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect("/settings")
    try:
        reset_count = reset_app_settings(db, confirm=True)
    except AppSettingsError as exc:
        add_flash(request, "error", f"flash.settings_{exc.code}")
        return _redirect("/settings")
    add_flash(request, "success", "flash.settings_reset")
    if danger_policy.show_detailed_results:
        add_flash(request, "info", "flash.settings_reset_detail", count=reset_count)
    return _redirect("/settings")


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
    confirm: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = saved_view_items_url(query_string)
    if not _danger_confirmation_is_valid(
        request,
        DangerPolicy(),
        confirmation_text=None,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(target)
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
            db=db,
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
    report = build_data_health_report(db)
    media_reference_repair_urls = {
        (issue.object_type, issue.object_id, issue.code): (
            "/data-health/media-reference/repair?"
            + urlencode(
                {
                    "object_type": issue.object_type,
                    "object_id": issue.object_id,
                }
            )
        )
        for issue in report.issues
        if is_repairable_media_reference_issue(
            object_type=issue.object_type,
            issue_code=issue.code,
        )
    }
    upload_residue_cleanup_urls = {
        issue.object_id: (
            "/data-health/upload-residue/delete-preview?"
            + urlencode({"residue_path": issue.object_id})
        )
        for issue in report.issues
        if issue.code == "media_upload_residue"
        and issue.object_type == "media_file"
    }
    damaged_media_cleanup_urls = {
        issue.object_id: (
            "/data-health/damaged-media/delete-preview?"
            + urlencode({"media_path": issue.object_id})
        )
        for issue in report.issues
        if issue.code == "media_damaged_file"
        and issue.object_type == "media_file"
    }
    media_duplicate_group_urls = {
        issue.object_id: (
            "/media-library/duplicates?"
            + urlencode({"duplicate_q": issue.object_id})
        )
        for issue in report.issues
        if issue.code == "media_duplicate_content"
        and issue.object_type == "media_content"
    }
    media_scan_skip_urls = {
        "media_scan_skipped_symlinks": (
            "/media-library/skipped?skip_type=symlink"
        ),
        "media_scan_skipped_unsupported": (
            "/media-library/skipped?skip_type=unsupported"
        ),
    }
    media_root_diagnostic_url = (
        "/data-health/media-root"
        if any(
            issue.code == "media_root_unavailable"
            and issue.object_type == "media_root"
            for issue in report.issues
        )
        else None
    )
    return templates.TemplateResponse(
        request,
        "data_health.html",
        _base_context(
            request,
            db=db,
            report=report,
            fix_options=build_data_health_fix_options(report),
            media_reference_repair_urls=media_reference_repair_urls,
            upload_residue_cleanup_urls=upload_residue_cleanup_urls,
            damaged_media_cleanup_urls=damaged_media_cleanup_urls,
            media_duplicate_group_urls=media_duplicate_group_urls,
            media_scan_skip_urls=media_scan_skip_urls,
            media_root_diagnostic_url=media_root_diagnostic_url,
        ),
    )


@router.get(
    "/data-health/media-root",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_root_diagnostic_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    diagnostic = None
    error_key = None
    try:
        candidate = build_media_root_diagnostic(db)
        if candidate.status == "ready":
            error_key = "media_root_diagnostic.error_root_available"
        else:
            diagnostic = candidate
    except MediaRootDiagnosticError as exc:
        error_key = f"media_root_diagnostic.error_{exc.code}"
    return templates.TemplateResponse(
        request,
        "media_root_diagnostic.html",
        _base_context(
            request,
            db=db,
            media_root_diagnostic=diagnostic,
            error_key=error_key,
        ),
        status_code=200 if diagnostic is not None else 400,
    )


@router.post(
    "/data-health/media-root/initialize",
    dependencies=[Depends(require_page_auth)],
)
def media_root_initialize_page(
    request: Request,
    expected_size: str = Form(...),
    expected_device: str = Form(...),
    expected_inode: str = Form(...),
    expected_modified_ns: str = Form(...),
    expected_changed_ns: str = Form(...),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect("/data-health/media-root")
    try:
        result = execute_media_root_initialization(
            db,
            expected_size=expected_size,
            expected_device=expected_device,
            expected_inode=expected_inode,
            expected_modified_ns=expected_modified_ns,
            expected_changed_ns=expected_changed_ns,
        )
    except MediaRootDiagnosticError as exc:
        add_flash(
            request,
            "info" if exc.created else "error",
            (
                "flash.media_root_initialization_created_warning"
                if exc.created
                else f"flash.media_root_initialization_{exc.code}"
            ),
            code=exc.code,
        )
        return _redirect("/data-health/media-root")
    add_flash(
        request,
        "success",
        "flash.media_root_initialization_success",
        logical_path=result.logical_path,
    )
    if result.warning_code:
        add_flash(
            request,
            "info",
            "flash.media_root_initialization_warning",
            code=result.warning_code,
        )
    return _redirect("/data-health")


def _damaged_media_delete_preview_url(
    media_path: str | None,
    sha256: str | None,
) -> str:
    params = {"media_path": media_path or ""}
    if sha256:
        params["sha256"] = sha256
    return "/data-health/damaged-media/delete-preview?" + urlencode(params)


@router.get(
    "/data-health/damaged-media/delete-preview",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_damaged_cleanup_preview_page(
    request: Request,
    media_path: str | None = Query(default=None),
    sha256: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    preview = None
    error_key = None
    try:
        preview = build_media_damaged_cleanup_preview(
            db,
            media_path=media_path,
            sha256=sha256,
        )
    except MediaDamagedCleanupError as exc:
        error_key = f"media_damaged_cleanup.error_{exc.code}"
    return templates.TemplateResponse(
        request,
        "media_damaged_cleanup_preview.html",
        _base_context(
            request,
            db=db,
            damaged_preview=preview,
            error_key=error_key,
        ),
        status_code=200 if preview is not None else 400,
    )


@router.post(
    "/data-health/damaged-media/delete",
    dependencies=[Depends(require_page_auth)],
)
def media_damaged_cleanup_page(
    request: Request,
    media_path: str = Form(...),
    sha256: str = Form(...),
    expected_size: str = Form(...),
    expected_device: str = Form(...),
    expected_inode: str = Form(...),
    expected_modified_ns: str = Form(...),
    expected_changed_ns: str = Form(...),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    preview_url = _damaged_media_delete_preview_url(media_path, sha256)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(preview_url)
    try:
        result = execute_media_damaged_cleanup(
            db,
            media_path=media_path,
            sha256=sha256,
            expected_size=expected_size,
            expected_device=expected_device,
            expected_inode=expected_inode,
            expected_modified_ns=expected_modified_ns,
            expected_changed_ns=expected_changed_ns,
        )
    except MediaDamagedCleanupError as exc:
        add_flash(
            request,
            "error",
            f"flash.media_damaged_cleanup_{exc.code}",
        )
        return _redirect("/data-health")
    add_flash(
        request,
        "success",
        "flash.media_damaged_cleanup_success",
        deleted_path=result.deleted_path,
        size=result.size,
    )
    if result.warning_code:
        add_flash(
            request,
            "info",
            "flash.media_damaged_cleanup_warning",
            code=result.warning_code,
        )
    return _redirect("/data-health")


def _upload_residue_delete_preview_url(residue_path: str | None) -> str:
    return "/data-health/upload-residue/delete-preview?" + urlencode(
        {"residue_path": residue_path or ""}
    )


@router.get(
    "/data-health/upload-residue/delete-preview",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_upload_residue_cleanup_preview_page(
    request: Request,
    residue_path: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    preview = None
    error_key = None
    try:
        preview = build_media_upload_residue_cleanup_preview(
            db,
            residue_path=residue_path,
        )
    except MediaUploadResidueCleanupError as exc:
        error_key = f"media_upload_residue_cleanup.error_{exc.code}"
    return templates.TemplateResponse(
        request,
        "media_upload_residue_cleanup_preview.html",
        _base_context(
            request,
            db=db,
            residue_preview=preview,
            error_key=error_key,
        ),
        status_code=200 if preview is not None else 400,
    )


@router.post(
    "/data-health/upload-residue/delete",
    dependencies=[Depends(require_page_auth)],
)
def media_upload_residue_cleanup_page(
    request: Request,
    residue_path: str = Form(...),
    expected_size: str = Form(...),
    expected_device: str = Form(...),
    expected_inode: str = Form(...),
    expected_modified_ns: str = Form(...),
    expected_changed_ns: str = Form(...),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    preview_url = _upload_residue_delete_preview_url(residue_path)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(preview_url)
    try:
        result = execute_media_upload_residue_cleanup(
            db,
            residue_path=residue_path,
            expected_size=expected_size,
            expected_device=expected_device,
            expected_inode=expected_inode,
            expected_modified_ns=expected_modified_ns,
            expected_changed_ns=expected_changed_ns,
        )
    except MediaUploadResidueCleanupError as exc:
        add_flash(
            request,
            "error",
            f"flash.media_upload_residue_cleanup_{exc.code}",
        )
        return _redirect("/data-health")
    add_flash(
        request,
        "success",
        "flash.media_upload_residue_cleanup_success",
        deleted_path=result.deleted_path,
        size=result.size,
    )
    if result.warning_code:
        add_flash(
            request,
            "info",
            "flash.media_upload_residue_cleanup_warning",
            code=result.warning_code,
        )
    return _redirect("/data-health")


def _media_reference_repair_preview_url(
    object_type: str | None,
    object_id: str | int | None,
    *,
    q: str | None = None,
    page: str | int | None = None,
) -> str:
    params: dict[str, str] = {
        "object_type": object_type or "",
        "object_id": str(object_id or ""),
    }
    if q:
        params["q"] = q
    if page not in {None, "", 1, "1"}:
        params["page"] = str(page)
    return "/data-health/media-reference/repair?" + urlencode(params)


@router.get(
    "/data-health/media-reference/repair",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_reference_repair_preview_page(
    request: Request,
    object_type: str | None = Query(default=None),
    object_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    page: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    preview = None
    error_key = None
    try:
        preview = build_media_reference_repair_preview(
            db,
            object_type=object_type,
            object_id=object_id,
            q=q,
            page=page,
        )
    except MediaReferenceRepairError as exc:
        error_key = f"media_reference_repair.error_{exc.code}"
    pagination = None
    if preview is not None:
        pagination = _page_context(
            preview.page_info,
            "/data-health/media-reference/repair",
            params={
                "object_type": preview.target.object_type,
                "object_id": preview.target.object_id,
                "q": preview.query,
            },
        )
    return templates.TemplateResponse(
        request,
        "media_reference_repair.html",
        _base_context(
            request,
            db=db,
            repair_preview=preview,
            replacement_pagination=pagination,
            error_key=error_key,
        ),
        status_code=200 if preview is not None else 400,
    )


@router.post(
    "/data-health/media-reference/repair",
    dependencies=[Depends(require_page_auth)],
)
def media_reference_repair_page(
    request: Request,
    object_type: str = Form(...),
    object_id: str = Form(...),
    expected_object_token: str = Form(...),
    expected_original_path: str = Form(...),
    expected_issue_code: str = Form(...),
    mode: str = Form(...),
    replacement_path: str | None = Form(default=None),
    replacement_sha256: str | None = Form(default=None),
    expected_size: str | None = Form(default=None),
    expected_device: str | None = Form(default=None),
    expected_inode: str | None = Form(default=None),
    expected_modified_ns: str | None = Form(default=None),
    expected_changed_ns: str | None = Form(default=None),
    q: str | None = Form(default=None),
    page: str | None = Form(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    preview_url = _media_reference_repair_preview_url(
        object_type,
        object_id,
        q=q,
        page=page,
    )
    danger_policy = get_danger_policy(db)
    if not _danger_confirmation_is_valid(
        request,
        danger_policy,
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(preview_url)
    try:
        result = execute_media_reference_repair(
            db,
            object_type=object_type,
            object_id=object_id,
            expected_object_token=expected_object_token,
            expected_original_path=expected_original_path,
            expected_issue_code=expected_issue_code,
            mode=mode,
            replacement_path=replacement_path,
            replacement_sha256=replacement_sha256,
            expected_size=expected_size,
            expected_device=expected_device,
            expected_inode=expected_inode,
            expected_modified_ns=expected_modified_ns,
            expected_changed_ns=expected_changed_ns,
        )
    except MediaReferenceRepairError as exc:
        add_flash(
            request,
            "error",
            f"flash.media_reference_repair_{exc.code}",
        )
        return _redirect(preview_url)

    flash_key = (
        "flash.media_reference_repair_replaced"
        if result.mode == "replace"
        else "flash.media_reference_repair_cleared"
    )
    add_flash(
        request,
        "success",
        flash_key,
        object_name=result.object_name,
        old_path=result.old_path,
        new_path=result.new_path or "",
    )
    return _redirect("/data-health")


@router.post("/data-health/fix", dependencies=[Depends(require_page_auth)])
def data_health_fix_page(
    request: Request,
    fix_type: str = Form(...),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    danger_policy = get_danger_policy(db)
    if not _danger_confirmation_is_valid(
        request,
        danger_policy,
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect("/data-health")
    try:
        result = apply_data_health_fix(
            db,
            fix_type=fix_type,
            confirm=True,
        )
    except DataHealthFixError as exc:
        add_flash(request, "error", f"flash.data_health_fix_{exc.code}")
        return _redirect("/data-health")

    if danger_policy.show_detailed_results:
        add_flash(
            request,
            "success",
            "flash.data_health_fix_success",
            fix_type=translate(
                get_language(request),
                f"data_health.fix_label_{result.fix_type}",
            ),
            deleted=result.deleted_count,
            updated=result.updated_count,
            skipped=result.skipped_count,
        )
    else:
        add_flash(
            request,
            "success",
            "flash.data_health_fix_summary",
            affected=result.deleted_count + result.updated_count,
        )
    return _redirect("/data-health")


@router.post("/activity/clear", dependencies=[Depends(require_page_auth)])
def clear_activity_page(
    request: Request,
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    danger_policy = get_danger_policy(db)
    if not _danger_confirmation_is_valid(
        request,
        danger_policy,
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect("/activity")
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
def duplicates_page(
    request: Request,
    page: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    candidate_page = find_duplicate_candidates(db, page=page)
    return templates.TemplateResponse(
        request,
        "duplicates.html",
        _base_context(
            request,
            db=db,
            candidate_groups=candidate_page.groups,
            pagination=_page_context(candidate_page.page_info, "/duplicates"),
        ),
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
        _base_context(request, db=db, comparison=comparison),
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
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    danger_policy = get_danger_policy(db)
    if not _danger_confirmation_is_valid(
        request,
        danger_policy,
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect("/duplicates")
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
    if danger_policy.show_detailed_results:
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
def cleanup_page(
    request: Request,
    page: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    candidate_page = find_metadata_cleanup_candidates(db, page=page)
    return templates.TemplateResponse(
        request,
        "cleanup.html",
        _base_context(
            request,
            db=db,
            candidate_sections=candidate_page.sections,
            has_candidates=candidate_page.page_info.total > 0,
            pagination=_page_context(candidate_page.page_info, "/cleanup"),
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
        _base_context(request, db=db, comparison=comparison),
    )


@router.post("/cleanup/merge", dependencies=[Depends(require_page_auth)])
def cleanup_merge_page(
    request: Request,
    cleanup_type: str = Form(..., alias="type"),
    primary_id: str = Form(...),
    duplicate_id: str = Form(...),
    use_duplicate_description: str | None = Form(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    danger_policy = get_danger_policy(db)
    if not _danger_confirmation_is_valid(
        request,
        danger_policy,
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect("/cleanup")
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
    if danger_policy.show_detailed_results:
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
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _safe_next_url(next_url)
    supported_actions = {
        "status",
        "add_tag",
        "remove_tag",
        "add_collection",
        "remove_collection",
        "rating",
        "delete",
    }
    if bulk_action not in supported_actions:
        add_flash(request, "error", "flash.bulk_invalid_action")
        return _redirect(target)
    danger_policy = get_danger_policy(db)
    if not _danger_confirmation_is_valid(
        request,
        danger_policy,
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(target)
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
    "/items/bulk",
    include_in_schema=False,
    dependencies=[Depends(require_page_auth)],
)
def bulk_items_get_not_allowed() -> None:
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        headers={"Allow": "POST"},
    )


@router.get(
    "/items/new",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def new_item_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "item_form.html",
        _base_context(
            request,
            db=db,
            item=None,
            action="/items",
            mode_key="items.create_title",
        ),
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
    return_list_url = _safe_next_url(request.query_params.get("next"))
    return templates.TemplateResponse(
        request,
        "detail.html",
        _base_context(
            request,
            db=db,
            item=item,
            item_sources=list_item_sources(db, item.id),
            sources_available=source_feature_available(db),
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


@router.post("/items/{item_id}/sources", dependencies=[Depends(require_page_auth)])
def add_item_source_page(
    request: Request,
    item_id: int,
    url: str = Form(...),
    title: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    try:
        add_item_source(db, item_id, url, title)
    except SourceError as exc:
        add_flash(request, "error", f"flash.source_{exc.code}")
        return _redirect(target)
    add_flash(request, "success", "flash.source_added")
    return _redirect(target)


@router.post(
    "/items/{item_id}/sources/{source_id}/delete",
    dependencies=[Depends(require_page_auth)],
)
def delete_item_source_page(
    request: Request,
    item_id: int,
    source_id: int,
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(target)
    try:
        delete_item_source(db, item_id, source_id)
    except SourceError as exc:
        add_flash(request, "error", f"flash.source_{exc.code}")
        return _redirect(target)
    add_flash(request, "success", "flash.source_deleted")
    return _redirect(target)


@router.get(
    "/sources/import",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def source_import_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "sources_import.html",
        _base_context(
            request,
            db=db,
            preview=None,
            source_text="",
            sources_available=source_feature_available(db),
        ),
    )


@router.post(
    "/sources/import/preview",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
async def source_import_preview_page(
    request: Request,
    source_text: str = Form(default=""),
    bookmarks_file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    preview = None
    error_key = None
    rendered_text = source_text
    try:
        if bookmarks_file is not None and bookmarks_file.filename:
            max_bytes = get_settings().max_import_upload_mb * 1024 * 1024
            content = await bookmarks_file.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise SourceError("file_too_large")
            rows = parse_bookmarks_html(content)
            rendered_text = ""
        else:
            if len(source_text.encode("utf-8")) > (
                get_settings().max_import_upload_mb * 1024 * 1024
            ):
                raise SourceError("file_too_large")
            rows = parse_source_text(source_text)
        preview = build_source_preview(db, rows)
    except SourceError as exc:
        error_key = f"sources.error_{exc.code}"
    return templates.TemplateResponse(
        request,
        "sources_import.html",
        _base_context(
            request,
            db=db,
            preview=preview,
            source_text=rendered_text,
            sources_available=source_feature_available(db),
            error_key=error_key,
        ),
    )


@router.post("/sources/import/apply", dependencies=[Depends(require_page_auth)])
def source_import_apply_page(
    request: Request,
    payload: str = Form(...),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect("/sources/import")
    try:
        if len(payload.encode("utf-8")) > (
            get_settings().max_import_upload_mb * 1024 * 1024
        ):
            raise SourceError("file_too_large")
        preview = import_source_rows(db, parse_source_text(payload))
    except SourceError as exc:
        add_flash(request, "error", f"flash.source_{exc.code}")
        return _redirect("/sources/import")
    add_flash(
        request,
        "success",
        "flash.source_imported",
        created=preview.new,
        duplicate=preview.duplicate,
        invalid=preview.invalid,
        conflict=preview.conflict,
    )
    return _redirect("/sources/import")


@router.post(
    "/items/{item_id}/view",
    dependencies=[Depends(require_page_auth)],
)
def record_item_view_page(
    item_id: int,
    db: Session = Depends(get_db),
) -> Response:
    get_item_or_404(db, item_id)
    safe_record_item_view(db, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
            db=db,
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
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _safe_next_url(next_url)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(target)
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
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(target)
    item = get_item_or_404(db, item_id)
    delete_state(db, item)
    safe_record_item_edit(db, item_id)
    add_flash(request, "info", "flash.state_cleared")
    return _redirect(target)


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
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(target)
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
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(target)
    try:
        remove_existing_creator(db, item_id, creator_id)
    except ItemDetailError as exc:
        add_flash(request, "error", f"flash.detail_{exc.code}")
        return _redirect(target)
    safe_record_item_edit(db, item_id)
    add_flash(request, "success", "flash.detail_creator_removed")
    return _redirect(target)


@router.get("/tags", response_class=HTMLResponse, dependencies=[Depends(require_page_auth)])
def tags_page(
    request: Request,
    page: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    tag_page = list_tag_page(db, page=page)
    return templates.TemplateResponse(
        request,
        "tags.html",
        _base_context(
            request,
            db=db,
            tags=tag_page.rows,
            pagination=_page_context(tag_page.page_info, "/tags"),
        ),
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
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect("/tags")
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
def creators_page(
    request: Request,
    page: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    creator_page = list_creator_page(db, page=page)
    return templates.TemplateResponse(
        request,
        "creators.html",
        _base_context(
            request,
            db=db,
            creators=creator_page.rows,
            pagination=_page_context(creator_page.page_info, "/creators"),
        ),
    )


@router.post("/creators", dependencies=[Depends(require_page_auth)])
def create_creator_page(
    request: Request,
    name: str = Form(...),
    type_value: str = Form(default="other"),
    avatar_path: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        payload = CreatorCreate(name=name, type=type_value, avatar_path=avatar_path)
    except ValueError:
        add_flash(request, "error", "flash.creator_create_failed")
        return _redirect("/creators")
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
        _base_context(request, db=db, creator=creator),
    )


@router.post("/creators/{creator_id}/delete", dependencies=[Depends(require_page_auth)])
def delete_creator_page(
    request: Request,
    creator_id: int,
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect("/creators")
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
def collections_page(
    request: Request,
    page: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    collection_page = list_collection_rows(db, page=page)
    return templates.TemplateResponse(
        request,
        "collections.html",
        _base_context(
            request,
            db=db,
            collection_rows=collection_page.rows,
            pagination=_page_context(collection_page.page_info, "/collections"),
        ),
    )


@router.get(
    "/collections/new",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def new_collection_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "collection_form.html",
        _base_context(
            request,
            db=db,
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
            db=db,
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
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect("/collections")
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
    item_page: str | None = None,
    available_page: str | None = None,
    available_q: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        detail = get_collection_detail_page(
            db,
            collection_id,
            item_page=item_page,
            available_page=available_page,
            available_query=available_q,
        )
    except CollectionError as exc:
        raise HTTPException(status_code=404, detail="Collection not found") from exc
    return templates.TemplateResponse(
        request,
        "collection_detail.html",
        _base_context(
            request,
            db=db,
            collection=detail.collection,
            collection_items=detail.items,
            collection_item_total=detail.items_page_info.total,
            available_items=detail.available_items,
            available_query=detail.available_query,
            item_pagination=_page_context(
                detail.items_page_info,
                f"/collections/{collection_id}",
                page_param="item_page",
                params={
                    "available_page": detail.available_page_info.page,
                    "available_q": detail.available_query,
                },
            ),
            available_pagination=_page_context(
                detail.available_page_info,
                f"/collections/{collection_id}",
                page_param="available_page",
                params={
                    "item_page": detail.items_page_info.page,
                    "available_q": detail.available_query,
                },
            ),
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
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = f"/collections/{collection_id}"
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(target)
    try:
        remove_item_from_collection(db, item_id=item_id, collection_id=collection_id)
    except CollectionError as exc:
        add_flash(request, "error", f"flash.collection_{exc.code}")
    else:
        safe_record_item_edit(db, item_id)
        add_flash(request, "success", "flash.collection_item_removed")
    return _redirect(target)


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
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    next_url: str = Form(default="/items", alias="next"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = _item_detail_url(item_id, next_url)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(target)
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
        _base_context(request, db=db, stats=build_stats_dashboard(db)),
    )


@router.get(
    "/import",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def import_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return _import_template(request, db=db)


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
    db: Session | None = None,
) -> HTMLResponse:
    raw_rows = preview["raw_rows"] if preview else []
    return templates.TemplateResponse(
        request,
        "import.html",
        _base_context(
            request,
            db=db,
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
            db=db,
        )
    if not (file.filename or "").lower().endswith(".csv"):
        return _import_template(
            request,
            import_error=_import_error_message(request, "unsupported_file_type"),
            db=db,
        )
    try:
        preview = preview_csv_import(db, await read_import_upload(file))
        return _import_template(request, preview=preview, db=db)
    except ImportDataError as exc:
        return _import_template(
            request,
            import_error=_import_error_message(request, exc.code),
            db=db,
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
            db=db,
        )
    if not (file.filename or "").lower().endswith(".json"):
        return _import_template(
            request,
            import_error=_import_error_message(request, "unsupported_file_type"),
            db=db,
        )
    try:
        preview = preview_json_import(db, await read_import_upload(file))
        return _import_template(request, preview=preview, db=db)
    except ImportDataError as exc:
        return _import_template(
            request,
            import_error=_import_error_message(request, exc.code),
            db=db,
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
            db=db,
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
            db=db,
        )

    result = import_valid_rows(db, preview["valid_rows"], preview["errors"])
    return _import_template(request, result=result, db=db)


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
    db: Session | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "backup.html",
        _base_context(
            request,
            db=db,
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
def backup_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return _backup_template(request, db=db)


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
                    db=db,
                )
        return _backup_template(
            request,
            preview_result=preview_result,
            validation_report=report,
            db=db,
        )
    except BackupError as exc:
        return _backup_template(
            request,
            preview_error=_backup_error_message(request, exc.code),
            db=db,
        )


@router.post(
    "/backup/restore",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
async def backup_restore_page(
    request: Request,
    file: UploadFile | None = File(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    restore_result: dict[str, int] | None = None
    restore_error: str | None = None
    danger_policy = get_danger_policy(db)
    db.rollback()
    try:
        require_danger_confirmation(
            danger_policy,
            confirmation_text=confirmation_text,
            base_confirmation_valid=confirm == "1",
        )
        payload = await _read_backup_upload_for_page(request, file)
        preview_backup_data(payload)
        restore_result = restore_backup_data(db, payload)
    except BackupError as exc:
        restore_error = _backup_error_message(request, exc.code)
    except DangerConfirmationError as exc:
        restore_error = translate(
            get_language(request),
            f"danger.error_{exc.code}",
        )
    except ValueError:
        restore_error = _backup_error_message(request, "restore_failed")
    return _backup_template(
        request,
        restore_result=restore_result,
        restore_error=restore_error,
        db=db,
    )
