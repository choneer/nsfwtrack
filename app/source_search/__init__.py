"""Provider-neutral video search orchestration."""

from app.source_search.contracts import (
    MAX_ASSET_LIST_ITEMS,
    SEARCH_OPERATIONS,
    ProviderSearchCauseCode,
    ProviderSearchServiceError,
    ProviderSearchServiceErrorCode,
    SearchProviderDescriptor,
    VideoAssetListEnvelope,
    VideoAssetListRequest,
    VideoDetailEnvelope,
    VideoDetailRequest,
    VideoSearchEnvelope,
    VideoSearchRequest,
)
from app.source_search.service import (
    PRODUCTION_SEARCH_PACKAGES,
    ProviderSearchService,
    build_production_search_service,
)

__all__ = [
    "MAX_ASSET_LIST_ITEMS",
    "PRODUCTION_SEARCH_PACKAGES",
    "SEARCH_OPERATIONS",
    "ProviderSearchCauseCode",
    "ProviderSearchService",
    "ProviderSearchServiceError",
    "ProviderSearchServiceErrorCode",
    "SearchProviderDescriptor",
    "VideoAssetListEnvelope",
    "VideoAssetListRequest",
    "VideoDetailEnvelope",
    "VideoDetailRequest",
    "VideoSearchEnvelope",
    "VideoSearchRequest",
    "build_production_search_service",
]
