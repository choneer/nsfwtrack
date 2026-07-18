"""Provider-neutral source adapter contracts and endpoint registry."""

from app.source_adapters.contracts import (
    SourceAdapter,
    SourceCreator,
    SourceDetail,
    SourceSearchPage,
    SourceSearchResult,
    SourceTag,
)
from app.source_adapters.registry import (
    BusinessParameter,
    EndpointOperation,
    EndpointRegistry,
    JsonTopLevel,
    PRODUCTION_ENDPOINT_REGISTRY,
    ProviderEndpoint,
)

__all__ = [
    "BusinessParameter",
    "EndpointOperation",
    "EndpointRegistry",
    "JsonTopLevel",
    "PRODUCTION_ENDPOINT_REGISTRY",
    "ProviderEndpoint",
    "SourceAdapter",
    "SourceCreator",
    "SourceDetail",
    "SourceSearchPage",
    "SourceSearchResult",
    "SourceTag",
]
