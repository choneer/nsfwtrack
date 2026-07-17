from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

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
    local_media_directory_identity_token,
    normalize_interactive_local_media_path,
    normalize_local_media_path,
    read_local_media_file,
    resolve_local_media_file,
    scan_local_media,
    scan_local_media_directories,
    store_media_uploads,
)
from app.services.media_directory_browser import (
    media_directory_query_params,
    query_media_directory,
)
from app.services.media_directory_management import (
    MediaDirectoryError,
    MediaDirectoryOutcomeError,
    build_directory_snapshot,
    classify_directory_result,
    execute_directory_mutation,
)
from app.services.media_item_candidates import (
    MediaItemCandidateError,
    create_items_from_media_candidates,
    find_media_item_candidates,
    paginate_media_item_candidates,
)
from app.services.media_index import (
    MediaIndexError,
    get_media_index_status,
    load_preferred_media_snapshot,
    refresh_media_index,
)
from app.services.media_operation_lock import (
    MediaOperationLockError,
    media_operation_lock,
)
from app.services.media_write_coordination import (
    MediaIndexCoordinationResult,
    MediaIndexCoordinationStatus,
    MediaFilesystemOutcome,
    MediaMutationExecutionError,
    classify_alias_result,
    classify_batch_result,
    classify_duplicate_result,
    classify_known_filesystem_change,
    classify_media_operation_error,
    classify_recovery_result,
    classify_rename_result,
    classify_upload_result,
    coordinate_media_mutation,
    coordinate_media_mutation_async,
)
from app.services.media_file_detail import (
    MediaFileDetailError,
    build_media_file_detail,
)
from app.services.media_file_rename import (
    MediaFileRenameError,
    build_media_file_rename_preview,
    execute_media_file_rename,
)
from app.services.media_alias_normalization import (
    MediaAliasNormalizationError,
    build_media_alias_normalization_preview,
    execute_media_alias_normalization,
)
from app.services.media_batch_management import (
    MAX_MEDIA_BATCH_SIZE,
    MediaBatchError,
    build_media_batch_preview,
    execute_media_batch,
)
from app.services.media_hardlink_aliases import (
    MEDIA_HARDLINK_ALIAS_SORT_OPTIONS,
    media_hardlink_alias_query_params,
    query_media_hardlink_aliases,
)
from app.services.media_reference_management import (
    MediaReferenceManagementError,
    build_media_reference_management_preview,
    execute_media_reference_management,
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


_MEDIA_DETAIL_RETURN_PATHS = frozenset(
    {
        "/media-library",
        "/media-library/duplicates",
        "/media-library/directories",
        "/media-library/aliases",
        "/media-library/recovery",
    }
)


def _safe_media_detail_return_url(value: str | None) -> str:
    target = safe_local_path(value, fallback="/media-library")
    try:
        path = urlsplit(target).path
    except ValueError:
        return "/media-library"
    return target if path in _MEDIA_DETAIL_RETURN_PATHS else "/media-library"


def _media_file_detail_url(media_path: str, return_url: str) -> str:
    return "/media-library/detail?" + urlencode(
        {"media_path": media_path, "next": return_url}
    )


def _media_file_rename_preview_url(
    media_path: str,
    target_basename: str,
    return_url: str,
) -> str:
    return "/media-library/detail/rename?" + urlencode(
        {
            "media_path": media_path,
            "target_basename": target_basename,
            "next": return_url,
        }
    )


def _media_file_move_preview_url(
    media_path: str,
    target_directory: str,
    target_basename: str,
    return_url: str,
) -> str:
    return "/media-library/detail/move?" + urlencode(
        {
            "media_path": media_path,
            "target_directory": target_directory,
            "target_basename": target_basename,
            "next": return_url,
        }
    )


def _media_reference_preview_url(
    media_path: str,
    object_type: str,
    object_id: str | int,
    operation: str,
    return_url: str,
) -> str:
    return "/media-library/detail/reference?" + urlencode(
        {
            "media_path": media_path,
            "object_type": object_type,
            "object_id": object_id,
            "operation": operation,
            "next": return_url,
        }
    )


def _media_source_url(
    path: str,
    params: dict[str, str | int],
    *,
    fragment: str = "",
) -> str:
    query = urlencode(params)
    return f"{path}?{query}{fragment}" if query else f"{path}{fragment}"


_MEDIA_BATCH_RETURN_PATHS = frozenset(
    {"/media-library", "/media-library/directories"}
)


def _safe_media_batch_return_url(value: str | None) -> str:
    target = safe_local_path(value, fallback="/media-library")
    try:
        path = urlsplit(target).path
    except ValueError:
        return "/media-library"
    return target if path in _MEDIA_BATCH_RETURN_PATHS else "/media-library"


def _query_value(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    return values[-1] if values else None


def _media_reference_paths(db: Session) -> set[str]:
    return set(
        db.scalars(select(Item.cover_path).where(Item.cover_path.is_not(None))).all()
    ) | set(
        db.scalars(
            select(Creator.avatar_path).where(Creator.avatar_path.is_not(None))
        ).all()
    )


def _media_batch_allowed_paths(db: Session, return_url: str) -> set[str]:
    parsed = urlsplit(return_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    try:
        scan = scan_local_media()
        used_paths = _media_reference_paths(db)
        if parsed.path == "/media-library/directories":
            result = query_media_directory(
                scan,
                scan_local_media_directories(),
                used_paths,
                directory=_query_value(params, "directory"),
                q=_query_value(params, "dir_q"),
                status=_query_value(params, "dir_status"),
                sort=_query_value(params, "dir_sort"),
                page=_query_value(params, "dir_page"),
            )
        else:
            result = query_media_library(
                scan,
                used_paths,
                q=_query_value(params, "media_q"),
                status=_query_value(params, "media_status"),
                sort=_query_value(params, "media_sort"),
                page=_query_value(params, "media_page"),
            )
    except (LocalMediaPathError, OSError) as exc:
        raise MediaBatchError("storage_unavailable") from exc
    return {row.entry.media_path for row in result.rows if row.entry.available}


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
        "local_media_directory_identity_token": local_media_directory_identity_token,
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


def _media_operation_lock_error_flash(
    request: Request,
    error: MediaOperationLockError,
) -> None:
    key = (
        "flash.media_busy"
        if error.code == "media_busy"
        else "flash.media_lock_unavailable"
    )
    add_flash(request, "error", key)


def _classify_directory_error(error: Exception) -> MediaFilesystemOutcome:
    outcome = getattr(error, "outcome", None)
    if outcome == "filesystem_changed_partial_known":
        return MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN
    if outcome == "directory_outcome_unknown":
        return MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    return MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE


def _classify_directory_result(result: object) -> MediaFilesystemOutcome:
    outcome = classify_directory_result(result)
    return {
        "filesystem_changed_known": MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN,
        "filesystem_changed_partial_known": MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN,
        "no_filesystem_change": MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE,
        "directory_outcome_unknown": MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN,
    }[outcome]


def _directory_invalidation_reason(_error: Exception) -> str | None:
    # Lock outcome verification can upgrade an originally non-unknown error.
    return "directory_outcome_unknown"


def _directory_result_invalidation_reason(_result: object) -> str:
    return "directory_outcome_unknown"


def _directory_success_flash(request: Request, result: object) -> None:
    key = (
        "flash.media_directory_committed_after_error"
        if getattr(result, "outcome", None) == "committed_after_error"
        else "flash.media_directory_success"
    )
    add_flash(request, "info" if "after_error" in key else "success", key)


def _directory_coordinated_flash(
    request: Request,
    coordinated: object,
) -> None:
    outcome = getattr(coordinated, "outcome", None)
    index = getattr(coordinated, "index")
    result = getattr(coordinated, "result")
    if outcome == MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN:
        add_flash(request, "error", "flash.media_directory_outcome_unknown")
        _media_index_coordination_flash(request, index)
        return
    if outcome == MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN:
        add_flash(request, "info", "flash.media_directory_partial_known")
        _media_index_coordination_flash(request, index)
        return
    if outcome == MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN:
        _directory_success_flash(request, result)
        _media_index_coordination_flash(request, index)


def _directory_failure_flash(request: Request, error: Exception) -> None:
    outcome = getattr(error, "outcome", None)
    if outcome == "filesystem_changed_partial_known":
        key = (
            "flash.media_directory_created_partial_known"
            if getattr(error, "code", None) == "created_directory_followup_failed"
            else "flash.media_directory_partial_known"
        )
        add_flash(request, "info", key)
    elif outcome == "not_committed_rolled_back":
        add_flash(request, "info", "flash.media_directory_rolled_back")
    elif outcome == "directory_outcome_unknown":
        add_flash(request, "error", "flash.media_directory_outcome_unknown")
    else:
        add_flash(request, "error", "flash.media_directory_failed")


def _directory_execution_error_flash(
    request: Request,
    execution_error: MediaMutationExecutionError,
) -> None:
    _directory_failure_flash(request, execution_error.error)
    _media_index_coordination_flash(request, execution_error.index)


def _media_index_coordination_flash(
    request: Request,
    result: MediaIndexCoordinationResult,
) -> None:
    if result.status == MediaIndexCoordinationStatus.NOT_NEEDED:
        return
    if result.status == MediaIndexCoordinationStatus.SYNCHRONIZED:
        add_flash(
            request,
            "success",
            "flash.media_index_post_mutation_synchronized",
        )
        return
    if result.status == MediaIndexCoordinationStatus.INVALIDATED:
        add_flash(
            request,
            "error",
            "flash.media_index_filesystem_outcome_unknown",
        )
        return
    if result.status == MediaIndexCoordinationStatus.POST_MUTATION_REFRESH_FAILED:
        add_flash(
            request,
            "info",
            "flash.media_index_post_mutation_refresh_failed",
        )
        return
    add_flash(
        request,
        "error",
        "flash.media_index_invalidation_failed",
    )


def _coordinated_service_error(
    request: Request,
    error: MediaMutationExecutionError,
    expected_type: type[Exception],
) -> Exception:
    _media_index_coordination_flash(request, error.index)
    if not isinstance(error.error, expected_type):
        raise error.error
    return error.error


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
        media_snapshot = load_preferred_media_snapshot(db)
        scan = media_snapshot.scan
    except LocalMediaPathError:
        scan = LocalMediaScan((), 0, 0, 0)
        media_snapshot = None
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
    media_return_url = _media_source_url(
        "/media-library",
        {
            **media_params,
            "match_page": candidate_page.page_info.page,
            "create_page": item_candidate_page.page_info.page,
        },
        fragment="#media-files",
    )
    media_detail_urls = {
        row.entry.media_path: _media_file_detail_url(
            row.entry.media_path,
            media_return_url,
        )
        for row in media_result.rows
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
            media_detail_urls=media_detail_urls,
            media_return_url=media_return_url,
            max_media_batch_size=MAX_MEDIA_BATCH_SIZE,
            max_media_upload_mb=MAX_MEDIA_UPLOAD_BYTES // (1024 * 1024),
            max_media_upload_files=MAX_MEDIA_UPLOAD_FILES,
            media_index_status=(
                media_snapshot.status
                if media_snapshot is not None
                else get_media_index_status(db)
            ),
            media_index_source=(
                media_snapshot.source if media_snapshot is not None else "filesystem"
            ),
            error_key=error_key,
        ),
    )


@router.get(
    "/media-library/directories",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_directory_page(
    request: Request,
    directory: str | None = Query(default=None),
    dir_page: str | None = Query(default=None),
    dir_q: str | None = Query(default=None),
    dir_status: str | None = Query(default=None),
    dir_sort: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        media_snapshot = load_preferred_media_snapshot(db)
        scan = media_snapshot.scan
        directories = media_snapshot.directories
        used_paths = set(
            db.scalars(
                select(Item.cover_path).where(Item.cover_path.is_not(None))
            ).all()
        ) | set(
            db.scalars(
                select(Creator.avatar_path).where(Creator.avatar_path.is_not(None))
            ).all()
        )
        result = query_media_directory(
            scan,
            directories,
            used_paths,
            directory=directory,
            q=dir_q,
            status=dir_status,
            sort=dir_sort,
            page=dir_page,
        )
    except (LocalMediaPathError, OSError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None

    params = media_directory_query_params(result)
    current_return_url = _media_source_url(
        "/media-library/directories",
        {**params, "dir_page": result.page_info.page},
    )
    child_urls = {
        child.media_path: _media_source_url(
            "/media-library/directories",
            {**params, "directory": child.media_path, "dir_page": 1},
        )
        for child in result.children
    }
    breadcrumb_urls = {
        breadcrumb.media_path: _media_source_url(
            "/media-library/directories",
            {**params, "directory": breadcrumb.media_path, "dir_page": 1},
        )
        for breadcrumb in result.breadcrumbs
    }
    detail_urls = {
        row.entry.media_path: _media_file_detail_url(
            row.entry.media_path,
            current_return_url,
        )
        for row in result.rows
    }
    current_parent_path = (
        "/media"
        if len(result.current.parts) <= 1
        else f"/media/{PurePosixPath(*result.current.parts[:-1]).as_posix()}"
    )
    directory_move_targets = tuple(
        candidate
        for candidate in directories
        if candidate.media_path not in {"/media"}
        and candidate.parts[: len(result.current.parts)] != result.current.parts
    )
    return templates.TemplateResponse(
        request,
        "media_directories.html",
        _base_context(
            request,
            db=db,
            directory_result=result,
            directory_status_options=MEDIA_STATUS_OPTIONS,
            directory_sort_options=MEDIA_SORT_OPTIONS,
            directory_pagination=_page_context(
                result.page_info,
                "/media-library/directories",
                page_param="dir_page",
                params=params,
            ),
            child_urls=child_urls,
            breadcrumb_urls=breadcrumb_urls,
            detail_urls=detail_urls,
            directory_return_url=current_return_url,
            max_media_batch_size=MAX_MEDIA_BATCH_SIZE,
            directory_parent_path=current_parent_path,
            directory_move_targets=directory_move_targets,
            media_index_status=media_snapshot.status,
            media_index_source=media_snapshot.source,
        ),
    )


def _directory_preview_context(
    request: Request,
    db: Session,
    *,
    snapshot: object,
    token: str,
    operation: str,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "media_directory_operation_preview.html",
        _base_context(
            request,
            db=db,
            directory_snapshot=snapshot,
            directory_token=token,
            directory_operation=operation,
        ),
    )


@router.get(
    "/media-library/directories/create",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_directory_create_preview(
    request: Request,
    target_parent: str = Query(...),
    target_basename: str = Query(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        snapshot, token = build_directory_snapshot(
            db,
            operation="create",
            source_path=None,
            target_parent_path=target_parent,
            target_basename=target_basename,
        )
    except (MediaDirectoryError, LocalMediaPathError, OSError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from None
    return _directory_preview_context(
        request, db, snapshot=snapshot, token=token, operation="create"
    )


@router.post(
    "/media-library/directories/create",
    dependencies=[Depends(require_page_auth)],
)
def media_directory_create_apply(
    request: Request,
    token: str = Form(...),
    confirm: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        coordinated = coordinate_media_mutation(
            db,
            source="post_directory",
            operation=lambda: execute_directory_mutation(db, token=token, confirmation=confirm),
            classify_result=_classify_directory_result,
            classify_error=_classify_directory_error,
            classify_invalidation_reason=_directory_invalidation_reason,
            classify_result_invalidation_reason=_directory_result_invalidation_reason,
        )
        _directory_coordinated_flash(request, coordinated)
    except MediaMutationExecutionError as exc:
        _directory_execution_error_flash(request, exc)
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
    except (MediaDirectoryError, LocalMediaPathError, OSError):
        add_flash(request, "error", "flash.media_directory_failed")
    return _redirect("/media-library/directories")


@router.get(
    "/media-library/directories/rename",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_directory_rename_preview(
    request: Request,
    source: str = Query(...),
    target_parent: str = Query(...),
    target_basename: str = Query(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        snapshot, token = build_directory_snapshot(
            db, operation="rename", source_path=source,
            target_parent_path=target_parent, target_basename=target_basename,
        )
    except (MediaDirectoryError, LocalMediaPathError, OSError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from None
    return _directory_preview_context(request, db, snapshot=snapshot, token=token, operation="rename")


@router.get(
    "/media-library/directories/move",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_directory_move_preview(
    request: Request,
    source: str = Query(...),
    target_parent: str = Query(...),
    target_basename: str = Query(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        snapshot, token = build_directory_snapshot(
            db, operation="move", source_path=source,
            target_parent_path=target_parent, target_basename=target_basename,
        )
    except (MediaDirectoryError, LocalMediaPathError, OSError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from None
    return _directory_preview_context(request, db, snapshot=snapshot, token=token, operation="move")


@router.post(
    "/media-library/directories/{operation}",
    dependencies=[Depends(require_page_auth)],
)
def media_directory_apply(
    request: Request,
    operation: str,
    token: str = Form(...),
    confirm: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if operation not in {"rename", "move", "delete"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        coordinated = coordinate_media_mutation(
            db,
            source="post_directory",
            operation=lambda: execute_directory_mutation(db, token=token, confirmation=confirm),
            classify_result=_classify_directory_result,
            classify_error=_classify_directory_error,
            classify_invalidation_reason=_directory_invalidation_reason,
            classify_result_invalidation_reason=_directory_result_invalidation_reason,
        )
        _directory_coordinated_flash(request, coordinated)
    except MediaMutationExecutionError as exc:
        _directory_execution_error_flash(request, exc)
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
    except (MediaDirectoryError, LocalMediaPathError, OSError):
        add_flash(request, "error", "flash.media_directory_failed")
    return _redirect("/media-library/directories")


@router.get(
    "/media-library/directories/delete",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_directory_delete_preview(
    request: Request,
    source: str = Query(...),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        record = local_media.validate_local_media_directory(source)
        if not record.parts:
            raise MediaDirectoryError("protected_media_root")
        parent = "/media" if len(record.parts) == 1 else f"/media/{PurePosixPath(*record.parts[:-1]).as_posix()}"
        snapshot, token = build_directory_snapshot(
            db, operation="delete", source_path=source,
            target_parent_path=parent, target_basename=record.parts[-1],
        )
    except (MediaDirectoryError, LocalMediaPathError, OSError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from None
    return _directory_preview_context(request, db, snapshot=snapshot, token=token, operation="delete")


@router.get(
    "/media-library/aliases",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_hardlink_alias_page(
    request: Request,
    alias_page: str | None = Query(default=None),
    alias_q: str | None = Query(default=None),
    alias_sort: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        media_snapshot = load_preferred_media_snapshot(db)
        scan = media_snapshot.scan
    except (LocalMediaPathError, OSError):
        scan = LocalMediaScan((), 0, 0, 0)
        media_snapshot = None
        error_key = "media.error_storage_unavailable"
    else:
        error_key = None
    result = query_media_hardlink_aliases(
        db,
        scan,
        q=alias_q,
        sort=alias_sort,
        page=alias_page,
    )
    params = media_hardlink_alias_query_params(result.filters)
    current_return_url = _media_source_url(
        "/media-library/aliases",
        {**params, "alias_page": result.page_info.page},
    )
    entries = {
        entry.media_path: entry
        for group in result.groups
        for entry in (
            *(path.entry for path in group.paths),
            *group.same_sha_independent_paths,
        )
    }
    detail_urls = {
        media_path: _media_file_detail_url(media_path, current_return_url)
        for media_path in entries
    }
    duplicate_urls = {
        group.sha256: _media_source_url(
            "/media-library/duplicates",
            {"duplicate_q": group.sha256},
            fragment=f"#media-duplicate-{group.sha256}",
        )
        for group in result.groups
    }
    return templates.TemplateResponse(
        request,
        "media_hardlink_aliases.html",
        _base_context(
            request,
            db=db,
            alias_result=result,
            alias_sort_options=MEDIA_HARDLINK_ALIAS_SORT_OPTIONS,
            alias_pagination=_page_context(
                result.page_info,
                "/media-library/aliases",
                page_param="alias_page",
                params=params,
            ),
            detail_urls=detail_urls,
            duplicate_urls=duplicate_urls,
            alias_return_url=current_return_url,
            media_index_status=(
                media_snapshot.status
                if media_snapshot is not None
                else get_media_index_status(db)
            ),
            media_index_source=(
                media_snapshot.source if media_snapshot is not None else "filesystem"
            ),
            error_key=error_key,
        ),
    )


def _media_batch_error_flash(request: Request, exc: MediaBatchError) -> None:
    add_flash(request, "error", "flash.media_batch_error", code=exc.code)


@router.get(
    "/media-library/batch/{operation}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_batch_preview_page(
    request: Request,
    operation: str,
    media_path: list[str] | None = Query(default=None),
    target_directory: str | None = Query(default=None),
    target_basename: list[str] | None = Query(default=None),
    prepared: str | None = Query(default=None),
    next_url: str | None = Query(default=None, alias="next"),
    db: Session = Depends(get_db),
) -> Response:
    return_url = _safe_media_batch_return_url(next_url)
    try:
        allowed_paths = _media_batch_allowed_paths(db, return_url)
        preview = build_media_batch_preview(
            db,
            operation=operation,
            media_paths=media_path,
            target_directory=target_directory,
            target_basenames=(target_basename if prepared == "1" else None),
            allowed_paths=allowed_paths,
            secret_key=get_settings().secret_key,
        )
        directories = (
            scan_local_media_directories() if operation == "move" else ()
        )
    except MediaBatchError as exc:
        _media_batch_error_flash(request, exc)
        return _redirect(return_url)
    except (LocalMediaPathError, OSError):
        _media_batch_error_flash(request, MediaBatchError("storage_unavailable"))
        return _redirect(return_url)
    return templates.TemplateResponse(
        request,
        "media_batch_preview.html",
        _base_context(
            request,
            db=db,
            batch_preview=preview,
            batch_directories=directories,
            return_url=return_url,
        ),
    )


@router.post(
    "/media-library/batch/{operation}",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_batch_apply_page(
    request: Request,
    operation: str,
    snapshot_token: list[str] | None = Form(default=None),
    next_url: str | None = Form(default=None, alias="next"),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> Response:
    return_url = _safe_media_batch_return_url(next_url)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(return_url)
    try:
        coordinated = coordinate_media_mutation(
            db,
            source="post_batch",
            operation=lambda: execute_media_batch(
                db,
                operation=operation,
                snapshot_tokens=snapshot_token,
                secret_key=get_settings().secret_key,
            ),
            classify_result=classify_batch_result,
            classify_error=lambda exc: classify_media_operation_error(
                "batch",
                exc,
            ),
        )
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
        return _redirect(return_url)
    except MediaMutationExecutionError as coordinated_error:
        exc = _coordinated_service_error(
            request,
            coordinated_error,
            MediaBatchError,
        )
        assert isinstance(exc, MediaBatchError)
        _media_batch_error_flash(request, exc)
        return _redirect(return_url)
    result = coordinated.result
    _media_index_coordination_flash(request, coordinated.index)
    return templates.TemplateResponse(
        request,
        "media_batch_result.html",
        _base_context(
            request,
            db=db,
            batch_result=result,
            return_url=return_url,
        ),
    )


def _media_alias_normalization_error_flash(
    request: Request,
    exc: MediaAliasNormalizationError,
) -> None:
    add_flash(
        request,
        "error",
        "flash.media_alias_normalization_error",
        code=exc.code,
    )


@router.get(
    "/media-library/aliases/normalize",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_alias_normalization_preview_page(
    request: Request,
    alias_path: list[str] | None = Query(default=None),
    keeper_path: str | None = Query(default=None),
    next_url: str | None = Query(default=None, alias="next"),
    db: Session = Depends(get_db),
) -> Response:
    return_url = _safe_media_detail_return_url(next_url)
    try:
        preview = build_media_alias_normalization_preview(
            db,
            alias_paths=alias_path,
            keeper_path=keeper_path,
            secret_key=get_settings().secret_key,
        )
    except MediaAliasNormalizationError as exc:
        _media_alias_normalization_error_flash(request, exc)
        return _redirect(return_url)
    return templates.TemplateResponse(
        request,
        "media_alias_normalization_preview.html",
        _base_context(
            request,
            db=db,
            alias_normalization_preview=preview,
            return_url=return_url,
        ),
    )


@router.post(
    "/media-library/aliases/normalize",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_alias_normalization_apply_page(
    request: Request,
    snapshot_token: str | None = Form(default=None),
    next_url: str | None = Form(default=None, alias="next"),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> Response:
    return_url = _safe_media_detail_return_url(next_url)
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(return_url)
    if snapshot_token is None:
        _media_alias_normalization_error_flash(
            request,
            MediaAliasNormalizationError("invalid_snapshot"),
        )
        return _redirect(return_url)
    try:
        coordinated = coordinate_media_mutation(
            db,
            source="post_cleanup",
            operation=lambda: execute_media_alias_normalization(
                db,
                snapshot_token=snapshot_token,
                secret_key=get_settings().secret_key,
            ),
            classify_result=classify_alias_result,
            classify_error=lambda exc: classify_media_operation_error(
                "alias",
                exc,
            ),
        )
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
        return _redirect(return_url)
    except MediaMutationExecutionError as coordinated_error:
        exc = _coordinated_service_error(
            request,
            coordinated_error,
            MediaAliasNormalizationError,
        )
        assert isinstance(exc, MediaAliasNormalizationError)
        _media_alias_normalization_error_flash(request, exc)
        return _redirect(return_url)
    result = coordinated.result
    _media_index_coordination_flash(request, coordinated.index)
    return templates.TemplateResponse(
        request,
        "media_alias_normalization_result.html",
        _base_context(
            request,
            db=db,
            alias_normalization_result=result,
            return_url=return_url,
        ),
    )


@router.get(
    "/media-library/detail",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_file_detail_page(
    request: Request,
    media_path: str | None = Query(default=None),
    next_url: str | None = Query(default=None, alias="next"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        detail = build_media_file_detail(db, media_path=media_path)
    except MediaFileDetailError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc

    return_url = _safe_media_detail_return_url(next_url)
    duplicate_group_url = None
    if detail.duplicate_group is not None:
        duplicate_group_url = _media_source_url(
            "/media-library/duplicates",
            {"duplicate_q": detail.duplicate_group.sha256},
            fragment=f"#media-duplicate-{detail.duplicate_group.sha256}",
        )
    damaged_cleanup_url = None
    item_repair_urls: dict[int, str] = {}
    creator_repair_urls: dict[int, str] = {}
    if not detail.entry.available:
        if detail.entry.sha256:
            damaged_cleanup_url = "/data-health/damaged-media/delete-preview?" + urlencode(
                {
                    "media_path": detail.entry.media_path,
                    "sha256": detail.entry.sha256,
                }
            )
        item_repair_urls = {
            reference.id: "/data-health/media-reference/repair?"
            + urlencode(
                {"object_type": "item_cover", "object_id": reference.id}
            )
            for reference in detail.item_references
        }
        creator_repair_urls = {
            reference.id: "/data-health/media-reference/repair?"
            + urlencode(
                {"object_type": "creator_avatar", "object_id": reference.id}
            )
            for reference in detail.creator_references
        }
    move_directories = ()
    reference_items = ()
    reference_creators = ()
    item_reference_clear_urls: dict[int, str] = {}
    creator_reference_clear_urls: dict[int, str] = {}
    if detail.entry.available:
        try:
            source_directory = PurePosixPath(detail.entry.media_path).parent.as_posix()
            move_directories = tuple(
                directory
                for directory in scan_local_media_directories()
                if directory.media_path != source_directory
            )
        except (LocalMediaPathError, OSError):
            move_directories = ()
        reference_items = tuple(
            db.execute(select(Item.id, Item.title).order_by(Item.title, Item.id)).all()
        )
        reference_creators = tuple(
            db.execute(
                select(Creator.id, Creator.name).order_by(Creator.name, Creator.id)
            ).all()
        )
        item_reference_clear_urls = {
            reference.id: _media_reference_preview_url(
                detail.entry.media_path,
                "item_cover",
                reference.id,
                "clear",
                return_url,
            )
            for reference in detail.item_references
        }
        creator_reference_clear_urls = {
            reference.id: _media_reference_preview_url(
                detail.entry.media_path,
                "creator_avatar",
                reference.id,
                "clear",
                return_url,
            )
            for reference in detail.creator_references
        }
    return templates.TemplateResponse(
        request,
        "media_file_detail.html",
        _base_context(
            request,
            db=db,
            media_detail=detail,
            return_url=return_url,
            duplicate_group_url=duplicate_group_url,
            damaged_cleanup_url=damaged_cleanup_url,
            item_repair_urls=item_repair_urls,
            creator_repair_urls=creator_repair_urls,
            rename_enabled=detail.entry.available,
            move_directories=move_directories,
            reference_items=reference_items,
            reference_creators=reference_creators,
            item_reference_clear_urls=item_reference_clear_urls,
            creator_reference_clear_urls=creator_reference_clear_urls,
        ),
    )


def _media_file_rename_error_flash(
    request: Request,
    exc: MediaFileRenameError,
) -> None:
    add_flash(request, "error", f"flash.media_file_rename_{exc.code}")


def _media_file_rename_error_redirect(
    media_path: str | None,
    return_url: str,
) -> RedirectResponse:
    try:
        normalized = normalize_interactive_local_media_path(media_path)
    except LocalMediaPathError:
        normalized = None
    if normalized is None:
        return _redirect("/media-library")
    return _redirect(_media_file_detail_url(normalized, return_url))


@router.get(
    "/media-library/detail/rename",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_file_rename_preview_page(
    request: Request,
    media_path: str | None = Query(default=None),
    target_basename: str | None = Query(default=None),
    next_url: str | None = Query(default=None, alias="next"),
    db: Session = Depends(get_db),
) -> Response:
    return_url = _safe_media_detail_return_url(next_url)
    try:
        preview = build_media_file_rename_preview(
            db,
            media_path=media_path,
            target_basename=target_basename,
        )
    except MediaFileRenameError as exc:
        _media_file_rename_error_flash(request, exc)
        return _media_file_rename_error_redirect(media_path, return_url)
    return templates.TemplateResponse(
        request,
        "media_file_rename_preview.html",
        _base_context(
            request,
            db=db,
            rename_preview=preview,
            return_url=return_url,
            source_detail_url=_media_file_detail_url(
                preview.source.media_path,
                return_url,
            ),
        ),
    )


@router.post(
    "/media-library/detail/rename",
    dependencies=[Depends(require_page_auth)],
)
def media_file_rename_apply_page(
    request: Request,
    media_path: str | None = Form(default=None),
    target_basename: str | None = Form(default=None),
    next_url: str | None = Form(default=None, alias="next"),
    expected_sha256: str | None = Form(default=None),
    expected_mode: str | None = Form(default=None),
    expected_size: str | None = Form(default=None),
    expected_device: str | None = Form(default=None),
    expected_inode: str | None = Form(default=None),
    expected_modified_ns: str | None = Form(default=None),
    expected_changed_ns: str | None = Form(default=None),
    item_reference_id: list[str] | None = Form(default=None),
    creator_reference_id: list[str] | None = Form(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return_url = _safe_media_detail_return_url(next_url)
    danger_policy = get_danger_policy(db)
    preview_url = _media_file_rename_preview_url(
        media_path or "",
        target_basename or "",
        return_url,
    )
    if not _danger_confirmation_is_valid(
        request,
        danger_policy,
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(preview_url)
    try:
        coordinated = coordinate_media_mutation(
            db,
            source="post_rename",
            operation=lambda: execute_media_file_rename(
                db,
                media_path=media_path,
                target_basename=target_basename,
                expected_sha256=expected_sha256,
                expected_mode=expected_mode,
                expected_size=expected_size,
                expected_device=expected_device,
                expected_inode=expected_inode,
                expected_modified_ns=expected_modified_ns,
                expected_changed_ns=expected_changed_ns,
                expected_item_reference_ids=item_reference_id,
                expected_creator_reference_ids=creator_reference_id,
            ),
            classify_result=classify_rename_result,
            classify_error=lambda exc: classify_media_operation_error(
                "rename",
                exc,
            ),
        )
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
        return _media_file_rename_error_redirect(media_path, return_url)
    except MediaMutationExecutionError as coordinated_error:
        exc = _coordinated_service_error(
            request,
            coordinated_error,
            MediaFileRenameError,
        )
        assert isinstance(exc, MediaFileRenameError)
        _media_file_rename_error_flash(request, exc)
        return _media_file_rename_error_redirect(media_path, return_url)
    result = coordinated.result

    if result.warning_code != "commit_outcome_unknown":
        add_flash(
            request,
            "success",
            "flash.media_file_rename_completed",
            source=result.source_path,
            target=result.target_path,
            items=result.migrated_items,
            creators=result.migrated_creators,
        )
    if result.warning_code:
        known_warning_codes = {
            "commit_outcome_unknown",
            "committed_source_retained",
            "delete_failed",
            "link_changed",
            "lock_release_failed",
            "reference_check_failed",
            "references_remaining",
            "source_missing",
            "sync_failed",
            "target_references_changed",
        }
        warning_code = (
            result.warning_code
            if result.warning_code in known_warning_codes
            else "source_retained"
        )
        add_flash(
            request,
            "error" if warning_code == "commit_outcome_unknown" else "info",
            f"flash.media_file_rename_warning_{warning_code}",
            source=result.source_path,
            target=result.target_path,
        )
    _media_index_coordination_flash(request, coordinated.index)
    detail_path = (
        result.source_path
        if result.warning_code == "commit_outcome_unknown"
        else result.target_path
    )
    return _redirect(_media_file_detail_url(detail_path, return_url))


def _media_file_move_error_flash(
    request: Request,
    exc: MediaFileRenameError,
) -> None:
    add_flash(request, "error", f"flash.media_file_move_{exc.code}")


@router.get(
    "/media-library/detail/move",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_file_move_preview_page(
    request: Request,
    media_path: str | None = Query(default=None),
    target_directory: str | None = Query(default=None),
    target_basename: str | None = Query(default=None),
    next_url: str | None = Query(default=None, alias="next"),
    db: Session = Depends(get_db),
) -> Response:
    return_url = _safe_media_detail_return_url(next_url)
    try:
        preview = build_media_file_rename_preview(
            db,
            media_path=media_path,
            target_directory=target_directory,
            target_basename=target_basename,
        )
    except MediaFileRenameError as exc:
        _media_file_move_error_flash(request, exc)
        return _media_file_rename_error_redirect(media_path, return_url)
    return templates.TemplateResponse(
        request,
        "media_file_move_preview.html",
        _base_context(
            request,
            db=db,
            move_preview=preview,
            return_url=return_url,
            source_detail_url=_media_file_detail_url(
                preview.source.media_path,
                return_url,
            ),
        ),
    )


@router.post(
    "/media-library/detail/move",
    dependencies=[Depends(require_page_auth)],
)
def media_file_move_apply_page(
    request: Request,
    media_path: str | None = Form(default=None),
    target_directory: str | None = Form(default=None),
    target_basename: str | None = Form(default=None),
    next_url: str | None = Form(default=None, alias="next"),
    expected_sha256: str | None = Form(default=None),
    expected_mode: str | None = Form(default=None),
    expected_size: str | None = Form(default=None),
    expected_device: str | None = Form(default=None),
    expected_inode: str | None = Form(default=None),
    expected_modified_ns: str | None = Form(default=None),
    expected_changed_ns: str | None = Form(default=None),
    expected_source_directory_token: str | None = Form(default=None),
    expected_target_directory_token: str | None = Form(default=None),
    item_reference_id: list[str] | None = Form(default=None),
    creator_reference_id: list[str] | None = Form(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return_url = _safe_media_detail_return_url(next_url)
    preview_url = _media_file_move_preview_url(
        media_path or "",
        target_directory or "",
        target_basename or "",
        return_url,
    )
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(preview_url)
    try:
        coordinated = coordinate_media_mutation(
            db,
            source="post_move",
            operation=lambda: execute_media_file_rename(
                db,
                media_path=media_path,
                target_directory=target_directory,
                target_basename=target_basename,
                expected_sha256=expected_sha256,
                expected_mode=expected_mode,
                expected_size=expected_size,
                expected_device=expected_device,
                expected_inode=expected_inode,
                expected_modified_ns=expected_modified_ns,
                expected_changed_ns=expected_changed_ns,
                expected_source_directory_token=expected_source_directory_token,
                expected_target_directory_token=expected_target_directory_token,
                expected_item_reference_ids=item_reference_id,
                expected_creator_reference_ids=creator_reference_id,
            ),
            classify_result=classify_rename_result,
            classify_error=lambda exc: classify_media_operation_error(
                "move",
                exc,
            ),
        )
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
        return _media_file_rename_error_redirect(media_path, return_url)
    except MediaMutationExecutionError as coordinated_error:
        exc = _coordinated_service_error(
            request,
            coordinated_error,
            MediaFileRenameError,
        )
        assert isinstance(exc, MediaFileRenameError)
        _media_file_move_error_flash(request, exc)
        return _media_file_rename_error_redirect(media_path, return_url)
    result = coordinated.result

    if result.warning_code != "commit_outcome_unknown":
        add_flash(
            request,
            "success",
            "flash.media_file_move_completed",
            source=result.source_path,
            target=result.target_path,
            items=result.migrated_items,
            creators=result.migrated_creators,
        )
    if result.warning_code:
        known_warning_codes = {
            "commit_outcome_unknown",
            "committed_source_retained",
            "delete_failed",
            "link_changed",
            "lock_release_failed",
            "reference_check_failed",
            "references_remaining",
            "source_missing",
            "sync_failed",
            "target_references_changed",
        }
        warning_code = (
            result.warning_code
            if result.warning_code in known_warning_codes
            else "source_retained"
        )
        add_flash(
            request,
            "error" if warning_code == "commit_outcome_unknown" else "info",
            f"flash.media_file_move_warning_{warning_code}",
            source=result.source_path,
            target=result.target_path,
        )
    _media_index_coordination_flash(request, coordinated.index)
    detail_path = (
        result.source_path
        if result.warning_code == "commit_outcome_unknown"
        else result.target_path
    )
    return _redirect(_media_file_detail_url(detail_path, return_url))


def _media_reference_error_redirect(
    media_path: str | None,
    return_url: str,
) -> RedirectResponse:
    return _media_file_rename_error_redirect(media_path, return_url)


@router.get(
    "/media-library/detail/reference",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_reference_management_preview_page(
    request: Request,
    media_path: str | None = Query(default=None),
    object_type: str | None = Query(default=None),
    object_id: str | None = Query(default=None),
    operation: str | None = Query(default=None),
    next_url: str | None = Query(default=None, alias="next"),
    db: Session = Depends(get_db),
) -> Response:
    return_url = _safe_media_detail_return_url(next_url)
    try:
        preview = build_media_reference_management_preview(
            db,
            media_path=media_path,
            object_type=object_type,
            object_id=object_id,
            operation=operation,
        )
    except MediaReferenceManagementError as exc:
        add_flash(request, "error", f"flash.media_reference_management_{exc.code}")
        return _media_reference_error_redirect(media_path, return_url)
    return templates.TemplateResponse(
        request,
        "media_reference_management_preview.html",
        _base_context(
            request,
            db=db,
            reference_preview=preview,
            return_url=return_url,
            source_detail_url=_media_file_detail_url(
                preview.media.media_path,
                return_url,
            ),
        ),
    )


@router.post(
    "/media-library/detail/reference",
    dependencies=[Depends(require_page_auth)],
)
def media_reference_management_apply_page(
    request: Request,
    media_path: str | None = Form(default=None),
    object_type: str | None = Form(default=None),
    object_id: str | None = Form(default=None),
    operation: str | None = Form(default=None),
    next_url: str | None = Form(default=None, alias="next"),
    expected_object_token: str | None = Form(default=None),
    expected_action: str | None = Form(default=None),
    expected_sha256: str | None = Form(default=None),
    expected_mode: str | None = Form(default=None),
    expected_size: str | None = Form(default=None),
    expected_device: str | None = Form(default=None),
    expected_inode: str | None = Form(default=None),
    expected_modified_ns: str | None = Form(default=None),
    expected_changed_ns: str | None = Form(default=None),
    confirm: str | None = Form(default=None),
    confirmation_text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    return_url = _safe_media_detail_return_url(next_url)
    preview_url = _media_reference_preview_url(
        media_path or "",
        object_type or "",
        object_id or "",
        operation or "",
        return_url,
    )
    if not _danger_confirmation_is_valid(
        request,
        get_danger_policy(db),
        confirmation_text=confirmation_text,
        base_confirmation_valid=confirm == "1",
    ):
        return _redirect(preview_url)
    try:
        result = execute_media_reference_management(
            db,
            media_path=media_path,
            object_type=object_type,
            object_id=object_id,
            operation=operation,
            expected_object_token=expected_object_token,
            expected_action=expected_action,
            expected_sha256=expected_sha256,
            expected_mode=expected_mode,
            expected_size=expected_size,
            expected_device=expected_device,
            expected_inode=expected_inode,
            expected_modified_ns=expected_modified_ns,
            expected_changed_ns=expected_changed_ns,
        )
    except MediaReferenceManagementError as exc:
        add_flash(request, "error", f"flash.media_reference_management_{exc.code}")
        return _media_reference_error_redirect(media_path, return_url)

    if result.warning_code == "commit_outcome_unknown":
        add_flash(
            request,
            "error",
            "flash.media_reference_management_commit_outcome_unknown",
            name=result.target.object_name,
        )
    else:
        add_flash(
            request,
            "success",
            f"flash.media_reference_management_{result.action}_completed",
            name=result.target.object_name,
            path=result.new_path or result.target.original_path or "",
        )
        if result.warning_code == "committed_after_error":
            add_flash(
                request,
                "info",
                "flash.media_reference_management_committed_after_error",
                name=result.target.object_name,
            )
    return _redirect(_media_file_detail_url(media_path or "", return_url))


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
        media_snapshot = load_preferred_media_snapshot(db)
        scan = media_snapshot.scan
    except LocalMediaPathError:
        scan = LocalMediaScan((), 0, 0, 0)
        media_snapshot = None
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
            media_index_status=(
                media_snapshot.status
                if media_snapshot is not None
                else get_media_index_status(db)
            ),
            media_index_source=(
                media_snapshot.source if media_snapshot is not None else "filesystem"
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
    recovery_return_url = _media_source_url(
        "/media-library/recovery",
        {
            **media_recovery_filter_query_params(result.filters),
            "recovery_page": result.page_info.page,
        },
    )
    skipped_media_paths = {
        f"/media/{entry.path}"
        for entry in scan.skipped_entries
    }
    media_detail_urls: dict[str, str] = {}
    for row in result.rows:
        if (
            not row.entry.is_recovered
            or row.entry.is_cleanup_anchor
            or row.entry.media_path in skipped_media_paths
        ):
            continue
        try:
            normalized = normalize_interactive_local_media_path(
                row.entry.media_path
            )
        except LocalMediaPathError:
            continue
        if normalized == row.entry.media_path:
            media_detail_urls[row.entry.media_path] = _media_file_detail_url(
                row.entry.media_path,
                recovery_return_url,
            )
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
            media_detail_urls=media_detail_urls,
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
        coordinated = coordinate_media_mutation(
            db,
            source="post_recovery",
            operation=lambda: execute_media_cleanup_restore(
                db,
                media_path=media_path,
                sha256=sha256,
                expected_size=expected_size,
                expected_device=expected_device,
                expected_inode=expected_inode,
                expected_modified_ns=expected_modified_ns,
                expected_changed_ns=expected_changed_ns,
            ),
            classify_result=classify_recovery_result,
            classify_error=lambda exc: classify_media_operation_error(
                "recovery",
                exc,
            ),
        )
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
        return _redirect("/media-library/recovery")
    except MediaMutationExecutionError as coordinated_error:
        exc = _coordinated_service_error(
            request,
            coordinated_error,
            MediaCleanupRestoreError,
        )
        assert isinstance(exc, MediaCleanupRestoreError)
        add_flash(
            request,
            "error",
            f"flash.media_cleanup_restore_{exc.code}",
        )
        return _redirect("/media-library/recovery")
    result = coordinated.result
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
    _media_index_coordination_flash(request, coordinated.index)
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
        coordinated = coordinate_media_mutation(
            db,
            source="post_cleanup",
            operation=lambda: execute_media_cleanup_delete(
                db,
                media_path=media_path,
                sha256=sha256,
                expected_size=expected_size,
                expected_device=expected_device,
                expected_inode=expected_inode,
                expected_modified_ns=expected_modified_ns,
                expected_changed_ns=expected_changed_ns,
            ),
            classify_result=classify_known_filesystem_change,
            classify_error=lambda exc: classify_media_operation_error(
                "anchor_delete",
                exc,
            ),
        )
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
        return _redirect("/media-library/recovery")
    except MediaMutationExecutionError as coordinated_error:
        exc = _coordinated_service_error(
            request,
            coordinated_error,
            MediaCleanupDeleteError,
        )
        assert isinstance(exc, MediaCleanupDeleteError)
        add_flash(
            request,
            "error",
            f"flash.media_cleanup_delete_{exc.code}",
        )
        return _redirect("/media-library/recovery")
    result = coordinated.result
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
    _media_index_coordination_flash(request, coordinated.index)
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
        media_snapshot = load_preferred_media_snapshot(db)
        scan = media_snapshot.scan
    except LocalMediaPathError:
        scan = LocalMediaScan((), 0, 0, 0)
        media_snapshot = None
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
    duplicate_params = {
        **media_duplicate_filter_query_params(result.filters),
        "duplicate_page": result.page_info.page,
    }
    media_detail_urls = {
        entry.media_path: _media_file_detail_url(
            entry.media_path,
            _media_source_url(
                "/media-library/duplicates",
                duplicate_params,
                fragment=f"#media-duplicate-{group.sha256}",
            ),
        )
        for group in result.groups
        for entry in group.entries
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
            media_detail_urls=media_detail_urls,
            media_index_status=(
                media_snapshot.status
                if media_snapshot is not None
                else get_media_index_status(db)
            ),
            media_index_source=(
                media_snapshot.source if media_snapshot is not None else "filesystem"
            ),
            error_key=error_key,
        ),
    )


def _media_index_response(
    request: Request,
    db: Session,
    *,
    full_preview: bool = False,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "media_index.html",
        _base_context(
            request,
            db=db,
            index_status=get_media_index_status(db),
            full_preview=full_preview,
        ),
    )


@router.get(
    "/media-library/index",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_index_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return _media_index_response(request, db)


@router.post(
    "/media-library/index/refresh",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_index_refresh_page(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        with media_operation_lock() as operation_lock:
            operation_lock.verify()
            result = refresh_media_index(
                db,
                full=False,
                refresh_source="manual_incremental",
            )
            operation_lock.verify()
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
    except MediaIndexError as exc:
        add_flash(request, "error", f"flash.media_index_{exc.code}")
    else:
        add_flash(
            request,
            "success",
            "flash.media_index_incremental_success",
            reused=result.status.reused_count,
            rehashed=result.status.rehashed_count,
            new=result.status.new_count,
            changed=result.status.changed_count,
            removed=result.status.removed_count,
        )
    return _redirect("/media-library/index")


@router.get(
    "/media-library/index/rebuild",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_index_rebuild_preview_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return _media_index_response(request, db, full_preview=True)


@router.post(
    "/media-library/index/rebuild",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def media_index_rebuild_page(
    request: Request,
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
        return _redirect("/media-library/index/rebuild")
    try:
        with media_operation_lock() as operation_lock:
            operation_lock.verify()
            result = refresh_media_index(
                db,
                full=True,
                refresh_source="manual_full",
            )
            operation_lock.verify()
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
    except MediaIndexError as exc:
        add_flash(request, "error", f"flash.media_index_{exc.code}")
    else:
        add_flash(
            request,
            "success",
            "flash.media_index_full_success",
            rehashed=result.status.rehashed_count,
            new=result.status.new_count,
            changed=result.status.changed_count,
            removed=result.status.removed_count,
        )
    return _redirect("/media-library/index")


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
        coordinated = coordinate_media_mutation(
            db,
            source="post_cleanup",
            operation=lambda: execute_media_duplicate_cleanup(
                db,
                sha256=sha256,
                keeper_path=keeper_path,
                expected_member_paths=member_path,
            ),
            classify_result=classify_duplicate_result,
            classify_error=lambda exc: classify_media_operation_error(
                "duplicate",
                exc,
            ),
        )
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
        return _redirect("/media-library/duplicates")
    except MediaMutationExecutionError as coordinated_error:
        exc = _coordinated_service_error(
            request,
            coordinated_error,
            MediaDuplicateCleanupError,
        )
        assert isinstance(exc, MediaDuplicateCleanupError)
        _media_duplicate_cleanup_error_flash(request, exc)
        return _redirect("/media-library/duplicates")
    result = coordinated.result
    _media_index_coordination_flash(request, coordinated.index)
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
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        coordinated = await coordinate_media_mutation_async(
            db,
            source="post_upload",
            operation=lambda: store_media_uploads(files or []),
            classify_result=classify_upload_result,
            classify_error=lambda exc: classify_media_operation_error(
                "upload",
                exc,
            ),
        )
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
    except MediaMutationExecutionError as coordinated_error:
        exc = _coordinated_service_error(
            request,
            coordinated_error,
            LocalMediaUploadError,
        )
        assert isinstance(exc, LocalMediaUploadError)
        add_flash(request, "error", f"flash.media_{exc.code}")
    else:
        result = coordinated.result
        add_flash(
            request,
            "success",
            "flash.media_uploaded",
            uploaded=result.uploaded,
            duplicate=result.duplicate,
        )
        _media_index_coordination_flash(request, coordinated.index)
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
        coordinated = coordinate_media_mutation(
            db,
            source="post_root_init",
            operation=lambda: execute_media_root_initialization(
                db,
                expected_size=expected_size,
                expected_device=expected_device,
                expected_inode=expected_inode,
                expected_modified_ns=expected_modified_ns,
                expected_changed_ns=expected_changed_ns,
            ),
            classify_result=classify_known_filesystem_change,
            classify_error=lambda exc: classify_media_operation_error(
                "root_init",
                exc,
            ),
        )
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
        return _redirect("/data-health/media-root")
    except MediaMutationExecutionError as coordinated_error:
        exc = _coordinated_service_error(
            request,
            coordinated_error,
            MediaRootDiagnosticError,
        )
        assert isinstance(exc, MediaRootDiagnosticError)
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
    result = coordinated.result
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
    _media_index_coordination_flash(request, coordinated.index)
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
        coordinated = coordinate_media_mutation(
            db,
            source="post_cleanup",
            operation=lambda: execute_media_damaged_cleanup(
                db,
                media_path=media_path,
                sha256=sha256,
                expected_size=expected_size,
                expected_device=expected_device,
                expected_inode=expected_inode,
                expected_modified_ns=expected_modified_ns,
                expected_changed_ns=expected_changed_ns,
            ),
            classify_result=classify_known_filesystem_change,
            classify_error=lambda exc: classify_media_operation_error(
                "damaged",
                exc,
            ),
        )
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
        return _redirect("/data-health")
    except MediaMutationExecutionError as coordinated_error:
        exc = _coordinated_service_error(
            request,
            coordinated_error,
            MediaDamagedCleanupError,
        )
        assert isinstance(exc, MediaDamagedCleanupError)
        add_flash(
            request,
            "error",
            f"flash.media_damaged_cleanup_{exc.code}",
        )
        return _redirect("/data-health")
    result = coordinated.result
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
    _media_index_coordination_flash(request, coordinated.index)
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
        coordinated = coordinate_media_mutation(
            db,
            source="post_cleanup",
            operation=lambda: execute_media_upload_residue_cleanup(
                db,
                residue_path=residue_path,
                expected_size=expected_size,
                expected_device=expected_device,
                expected_inode=expected_inode,
                expected_modified_ns=expected_modified_ns,
                expected_changed_ns=expected_changed_ns,
            ),
            classify_result=classify_known_filesystem_change,
            classify_error=lambda exc: classify_media_operation_error(
                "residue_delete",
                exc,
            ),
        )
    except MediaOperationLockError as exc:
        _media_operation_lock_error_flash(request, exc)
        return _redirect("/data-health")
    except MediaMutationExecutionError as coordinated_error:
        exc = _coordinated_service_error(
            request,
            coordinated_error,
            MediaUploadResidueCleanupError,
        )
        assert isinstance(exc, MediaUploadResidueCleanupError)
        add_flash(
            request,
            "error",
            f"flash.media_upload_residue_cleanup_{exc.code}",
        )
        return _redirect("/data-health")
    result = coordinated.result
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
    _media_index_coordination_flash(request, coordinated.index)
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
