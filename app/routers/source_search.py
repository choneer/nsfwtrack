"""Read-only approved-Provider search and detail pages."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import is_authenticated, require_page_auth
from app.i18n import get_language, translate, translator
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
    build_production_search_service,
)
from app.video_metadata.contracts import VideoAsset


router = APIRouter(tags=["source-search"])
templates = Jinja2Templates(directory="app/templates")

_ERROR_STATUS = {
    ProviderSearchServiceErrorCode.INVALID_REQUEST: 400,
    ProviderSearchServiceErrorCode.PROVIDER_NOT_AVAILABLE: 409,
    ProviderSearchServiceErrorCode.OPERATION_NOT_APPROVED: 409,
    ProviderSearchServiceErrorCode.ADAPTER_MISMATCH: 502,
    ProviderSearchServiceErrorCode.INVALID_RESULT: 502,
    ProviderSearchServiceErrorCode.PROVIDER_ERROR: 502,
    ProviderSearchServiceErrorCode.UNKNOWN: 503,
}


def get_provider_search_service() -> ProviderSearchService:
    """Return the side-effect-free production search service."""

    return build_production_search_service()


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
        raise ProviderSearchServiceError(
            ProviderSearchServiceErrorCode.PROVIDER_NOT_AVAILABLE
        )
    if operation not in provider.operations:
        raise ProviderSearchServiceError(
            ProviderSearchServiceErrorCode.OPERATION_NOT_APPROVED
        )
    return provider


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
    return templates.TemplateResponse(
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
            "error_message": error_message,
            "flash_messages": [],
        },
        status_code=status_code,
    )


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
    return _render(
        request,
        providers=providers,
        detail_envelope=envelope,
    )
