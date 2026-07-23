"""Approved-Provider Search, Detail, signed Preview, and explicit Confirm UI."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import is_authenticated, require_page_auth
from app.database import SessionLocal, get_db
from app.flash import add_flash, pop_flash_messages
from app.i18n import get_language, translate, translator
from app.provider_apply.contracts import (
    ProviderApplyCommitStatus,
    ProviderApplyError,
    ProviderApplyErrorCode,
    ProviderApplyPlan,
    ProviderApplyResult,
)
from app.provider_apply.service import (
    build_provider_apply_plan,
    sign_provider_apply_plan,
)
from app.provider_apply.transaction import apply_provider_apply_token
from app.provider_apply.web import (
    ProviderApplyWebError,
    ensure_provider_apply_web_material,
    get_provider_apply_web_material,
)
from app.provider_runtime.catalog import build_runtime_search_service
from app.provider_runtime.service import ProviderRuntimeRegistry
from app.source_adapters import ProviderOperation
from app.source_search import (
    ProviderSearchService,
    ProviderSearchServiceError,
    ProviderSearchServiceErrorCode,
    SearchProviderDescriptor,
    VideoDetailEnvelope,
    VideoDetailRequest,
    VideoSearchEnvelope,
    VideoSearchRequest,
)
from app.video_metadata.contracts import VideoAsset


router = APIRouter(tags=["source-search"])
templates = Jinja2Templates(directory="app/templates")

_ERROR_STATUS = {
    ProviderSearchServiceErrorCode.INVALID_REQUEST: 400,
    ProviderSearchServiceErrorCode.PROVIDER_NOT_AVAILABLE: 409,
    ProviderSearchServiceErrorCode.PROVIDER_DISABLED: 409,
    ProviderSearchServiceErrorCode.PROVIDER_CONFIGURATION_REQUIRED: 409,
    ProviderSearchServiceErrorCode.PROVIDER_SESSION_REQUIRED: 409,
    ProviderSearchServiceErrorCode.PROVIDER_HEALTH_REQUIRED: 409,
    ProviderSearchServiceErrorCode.OPERATION_NOT_APPROVED: 409,
    ProviderSearchServiceErrorCode.ADAPTER_MISMATCH: 502,
    ProviderSearchServiceErrorCode.INVALID_RESULT: 502,
    ProviderSearchServiceErrorCode.PROVIDER_ERROR: 502,
    ProviderSearchServiceErrorCode.UNKNOWN: 503,
}

_APPLY_ERROR_FLASH = {
    ProviderApplyErrorCode.INVALID_REQUEST: "flash.provider_apply_invalid_request",
    ProviderApplyErrorCode.TOKEN_INVALID: "flash.provider_apply_token_invalid",
    ProviderApplyErrorCode.TOKEN_TOO_LARGE: "flash.provider_apply_token_invalid",
    ProviderApplyErrorCode.TOKEN_SIGNATURE_INVALID: "flash.provider_apply_token_invalid",
    ProviderApplyErrorCode.TOKEN_CONTEXT_MISMATCH: "flash.provider_apply_session_invalid",
    ProviderApplyErrorCode.TOKEN_NOT_YET_VALID: "flash.provider_apply_token_invalid",
    ProviderApplyErrorCode.TOKEN_EXPIRED: "flash.provider_apply_expired",
    ProviderApplyErrorCode.NOTHING_TO_APPLY: "flash.provider_apply_nothing_to_apply",
    ProviderApplyErrorCode.STALE_PLAN: "flash.provider_apply_stale",
    ProviderApplyErrorCode.DATABASE_STATE_INVALID: "flash.provider_apply_database_invalid",
    ProviderApplyErrorCode.WRITE_CONFLICT: "flash.provider_apply_conflict",
    ProviderApplyErrorCode.WRITE_FAILED: "flash.provider_apply_write_failed",
    ProviderApplyErrorCode.COMMIT_STATE_UNKNOWN: "flash.provider_apply_commit_state_unknown",
    ProviderApplyErrorCode.UNKNOWN: "flash.provider_apply_unknown",
}


def get_provider_search_service(
    db: Session = Depends(get_db),
) -> ProviderSearchService:
    """Build the current runtime-backed catalog without performing network I/O."""

    return build_runtime_search_service(db)


def _invalid_result() -> ProviderSearchServiceError:
    return ProviderSearchServiceError(
        ProviderSearchServiceErrorCode.INVALID_RESULT
    )


def _provider_catalog(
    service: ProviderSearchService,
) -> tuple[SearchProviderDescriptor, ...]:
    providers = service.list_providers()
    if type(providers) is not tuple or not all(
        type(provider) is SearchProviderDescriptor for provider in providers
    ):
        raise _invalid_result()
    provider_keys = tuple(provider.provider_key for provider in providers)
    if len(provider_keys) != len(set(provider_keys)):
        raise _invalid_result()
    return providers


def _approved_provider(
    providers: tuple[SearchProviderDescriptor, ...],
    provider_key: str,
    operation: ProviderOperation,
    *,
    unavailable_error: ProviderSearchServiceError | None = None,
) -> SearchProviderDescriptor:
    provider = next(
        (
            candidate
            for candidate in providers
            if candidate.provider_key == provider_key
        ),
        None,
    )
    if provider is None:
        raise unavailable_error or ProviderSearchServiceError(
            ProviderSearchServiceErrorCode.PROVIDER_NOT_AVAILABLE
        )
    if operation not in provider.operations:
        raise ProviderSearchServiceError(
            ProviderSearchServiceErrorCode.OPERATION_NOT_APPROVED
        )
    return provider


def _runtime_unavailable_error(
    db: Session,
    provider_key: str,
) -> ProviderSearchServiceError:
    """Classify a missing catalog entry without exposing Provider internals."""

    try:
        provider = ProviderRuntimeRegistry(db).get(provider_key)
    except Exception:
        return ProviderSearchServiceError(
            ProviderSearchServiceErrorCode.PROVIDER_NOT_AVAILABLE
        )
    if not provider.manageable or provider.scope != "PRODUCTION":
        return ProviderSearchServiceError(
            ProviderSearchServiceErrorCode.PROVIDER_NOT_AVAILABLE
        )
    if not provider.enabled:
        return ProviderSearchServiceError(
            ProviderSearchServiceErrorCode.PROVIDER_DISABLED
        )
    if provider.configuration_status != "valid":
        return ProviderSearchServiceError(
            ProviderSearchServiceErrorCode.PROVIDER_CONFIGURATION_REQUIRED
        )
    if provider.cookie_required and provider.session_status != "available":
        return ProviderSearchServiceError(
            ProviderSearchServiceErrorCode.PROVIDER_SESSION_REQUIRED
        )
    return ProviderSearchServiceError(
        ProviderSearchServiceErrorCode.PROVIDER_HEALTH_REQUIRED
    )


def _detail_assets(envelope: VideoDetailEnvelope) -> tuple[VideoAsset, ...]:
    detail = envelope.detail
    assets: list[VideoAsset] = []
    if detail.cover is not None:
        assets.append(detail.cover)
    assets.extend(detail.preview_images)
    if detail.preview_video is not None:
        assets.append(detail.preview_video)
    return tuple(assets)


def _render(
    request: Request,
    *,
    providers: tuple[SearchProviderDescriptor, ...],
    search_envelope: VideoSearchEnvelope | None = None,
    detail_envelope: VideoDetailEnvelope | None = None,
    apply_plan: ProviderApplyPlan | None = None,
    apply_token: str | None = None,
    apply_error: bool = False,
    error: ProviderSearchServiceError | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    language = get_language(request)
    error_message = None
    if error is not None:
        error_message = translate(
            language,
            f"source_search.error_{error.code.value}",
        )
    response = templates.TemplateResponse(
        request,
        "source_search.html",
        {
            "request": request,
            "authenticated": is_authenticated(request),
            "lang": language,
            "current_path": quote(request.url.path, safe="/"),
            "t": translator(language),
            "providers": providers,
            "has_search_provider": any(
                ProviderOperation.SEARCH in provider.operations
                for provider in providers
            ),
            "search_operation": ProviderOperation.SEARCH,
            "detail_operation": ProviderOperation.DETAIL,
            "search_envelope": search_envelope,
            "detail_envelope": detail_envelope,
            "detail_assets": (
                _detail_assets(detail_envelope)
                if detail_envelope is not None
                else ()
            ),
            "apply_plan": apply_plan,
            "apply_token": apply_token,
            "apply_error": apply_error,
            "error_message": error_message,
            "flash_messages": pop_flash_messages(request, language),
        },
        status_code=status_code,
    )
    if apply_token is not None:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


def _render_error(
    request: Request,
    providers: tuple[SearchProviderDescriptor, ...],
    error: ProviderSearchServiceError,
) -> HTMLResponse:
    if error.code is ProviderSearchServiceErrorCode.CANCELLED:
        raise error
    return _render(
        request,
        providers=providers,
        error=error,
        status_code=_ERROR_STATUS.get(
            error.code,
            _ERROR_STATUS[ProviderSearchServiceErrorCode.UNKNOWN],
        ),
    )


@router.get(
    "/source-search",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
def source_search_page(
    request: Request,
    service: ProviderSearchService = Depends(get_provider_search_service),
) -> HTMLResponse:
    try:
        providers = _provider_catalog(service)
    except ProviderSearchServiceError as error:
        return _render_error(request, (), error)
    return _render(request, providers=providers)


@router.post(
    "/source-search/search",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
async def source_search_results_page(
    request: Request,
    provider_key: str = Form(default=""),
    query: str = Form(default=""),
    page: str = Form(default=""),
    page_size: str = Form(default=""),
    service: ProviderSearchService = Depends(get_provider_search_service),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    providers: tuple[SearchProviderDescriptor, ...] = ()
    try:
        providers = _provider_catalog(service)
        search_request = VideoSearchRequest(
            provider_key=provider_key,
            query=query,
            page=int(page),
            page_size=int(page_size),
        )
        _approved_provider(
            providers,
            search_request.provider_key,
            ProviderOperation.SEARCH,
            unavailable_error=_runtime_unavailable_error(
                db,
                search_request.provider_key,
            ),
        )
        envelope = await service.search(search_request)
        if type(envelope) is not VideoSearchEnvelope:
            raise _invalid_result()
    except (TypeError, ValueError):
        return _render_error(
            request,
            providers,
            ProviderSearchServiceError(
                ProviderSearchServiceErrorCode.INVALID_REQUEST
            ),
        )
    except ProviderSearchServiceError as error:
        return _render_error(request, providers, error)
    return _render(
        request,
        providers=providers,
        search_envelope=envelope,
    )


@router.post(
    "/source-search/detail",
    response_class=HTMLResponse,
    dependencies=[Depends(require_page_auth)],
)
async def source_search_detail_page(
    request: Request,
    provider_key: str = Form(default=""),
    external_id: str = Form(default=""),
    service: ProviderSearchService = Depends(get_provider_search_service),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    providers: tuple[SearchProviderDescriptor, ...] = ()
    try:
        providers = _provider_catalog(service)
        detail_request = VideoDetailRequest(
            provider_key=provider_key,
            external_id=external_id,
        )
        _approved_provider(
            providers,
            detail_request.provider_key,
            ProviderOperation.DETAIL,
            unavailable_error=_runtime_unavailable_error(
                db,
                detail_request.provider_key,
            ),
        )
        envelope = await service.detail(detail_request)
        if type(envelope) is not VideoDetailEnvelope:
            raise _invalid_result()
    except (TypeError, ValueError):
        return _render_error(
            request,
            providers,
            ProviderSearchServiceError(
                ProviderSearchServiceErrorCode.INVALID_REQUEST
            ),
        )
    except ProviderSearchServiceError as error:
        return _render_error(request, providers, error)

    try:
        plan = build_provider_apply_plan(db, envelope)
        token: str | None = None
        if plan.has_writes:
            material = ensure_provider_apply_web_material(request)
            token = sign_provider_apply_plan(
                plan,
                secret=material.secret,
                context=material.context,
                now=datetime.now(UTC),
                ttl_seconds=600,
            )
    except (ProviderApplyError, ProviderApplyWebError):
        return _render(
            request,
            providers=providers,
            detail_envelope=envelope,
            apply_error=True,
        )
    return _render(
        request,
        providers=providers,
        detail_envelope=envelope,
        apply_plan=plan,
        apply_token=token,
    )


def _apply_failure(
    request: Request,
    code: ProviderApplyErrorCode,
) -> RedirectResponse:
    key = _APPLY_ERROR_FLASH.get(code, "flash.provider_apply_unknown")
    add_flash(request, "error", key)
    location = "/items" if code is ProviderApplyErrorCode.COMMIT_STATE_UNKNOWN else "/source-search"
    return RedirectResponse(location, status_code=303)


@router.post(
    "/source-search/apply",
    response_class=RedirectResponse,
    dependencies=[Depends(require_page_auth)],
)
def source_search_apply(
    request: Request,
    token: str = Form(default=""),
    confirmation: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if confirmation != "apply":
        return _apply_failure(request, ProviderApplyErrorCode.INVALID_REQUEST)
    try:
        material = get_provider_apply_web_material(request)
    except ProviderApplyWebError:
        add_flash(request, "error", "flash.provider_apply_session_invalid")
        return RedirectResponse("/source-search", status_code=303)

    try:
        result = apply_provider_apply_token(
            db,
            token,
            secret=material.secret,
            context=material.context,
            now=datetime.now(UTC),
            verification_session_factory=SessionLocal,
        )
    except ProviderApplyError as error:
        return _apply_failure(request, error.code)
    except Exception:
        return _apply_failure(request, ProviderApplyErrorCode.UNKNOWN)

    if type(result) is not ProviderApplyResult:
        return _apply_failure(request, ProviderApplyErrorCode.UNKNOWN)
    if result.commit_status is ProviderApplyCommitStatus.COMMITTED:
        add_flash(request, "success", "flash.provider_apply_committed")
    else:
        add_flash(
            request,
            "info",
            "flash.provider_apply_committed_verified_after_exception",
        )
    return RedirectResponse(f"/items/{result.item_id}", status_code=303)
