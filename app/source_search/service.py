"""Provider-neutral orchestration for independently approved video operations."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from app.source_adapters.contracts import (
    ProviderAdapterError,
    ProviderError,
    ProviderOperation,
)
from app.source_adapters.package import (
    ProviderAdapterBinding,
    ProviderAdapterKind,
    ProviderPackage,
    ProviderPackageError,
    validate_provider_package,
)
from app.source_search.contracts import (
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
from app.video_metadata.contracts import VideoDetail, VideoSearchPage


_Request = TypeVar(
    "_Request",
    VideoSearchRequest,
    VideoDetailRequest,
    VideoAssetListRequest,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _raise_service_error(
    code: ProviderSearchServiceErrorCode,
    cause_code: ProviderSearchCauseCode | None = None,
) -> None:
    raise ProviderSearchServiceError(code, cause_code) from None


def _raise_adapter_error(
    error: ProviderAdapterError,
    entry: _ProviderEntry,
    operation: ProviderOperation,
) -> None:
    provider_error = getattr(error, "error", None)
    if type(provider_error) is not ProviderError:
        _raise_service_error(ProviderSearchServiceErrorCode.UNKNOWN)
    if (
        provider_error.provider_key != entry.descriptor.provider_key
        or provider_error.operation not in {None, operation}
    ):
        _raise_service_error(
            ProviderSearchServiceErrorCode.ADAPTER_MISMATCH,
            provider_error.code,
        )
    _raise_service_error(
        ProviderSearchServiceErrorCode.PROVIDER_ERROR,
        provider_error.code,
    )


@dataclass(frozen=True, slots=True, repr=False)
class _ProviderEntry:
    descriptor: SearchProviderDescriptor
    binding: ProviderAdapterBinding


class ProviderSearchService:
    """Immutable catalog and strict one-operation dispatcher."""

    __slots__ = ("_clock", "_entries", "_sealed")

    def __init__(
        self,
        packages: tuple[ProviderPackage, ...],
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if type(packages) is not tuple or not callable(clock):
            _raise_service_error(ProviderSearchServiceErrorCode.INVALID_REQUEST)
        entries: list[_ProviderEntry] = []
        for package in packages:
            if type(package) is not ProviderPackage:
                _raise_service_error(
                    ProviderSearchServiceErrorCode.INVALID_REQUEST
                )
            try:
                validate_provider_package(package)
            except ProviderPackageError as error:
                _raise_service_error(
                    ProviderSearchServiceErrorCode.ADAPTER_MISMATCH,
                    error.code,
                )
            except Exception:
                _raise_service_error(
                    ProviderSearchServiceErrorCode.ADAPTER_MISMATCH
                )
            binding = package.binding
            if binding.adapter_kind is not ProviderAdapterKind.VIDEO_METADATA:
                _raise_service_error(
                    ProviderSearchServiceErrorCode.ADAPTER_MISMATCH
                )
            if any(operation not in SEARCH_OPERATIONS for operation in binding.operations):
                _raise_service_error(
                    ProviderSearchServiceErrorCode.ADAPTER_MISMATCH
                )
            descriptor = SearchProviderDescriptor(
                provider_key=binding.provider_key,
                display_name=binding.display_name,
                content_scope=binding.content_scope,
                operations=binding.operations,
            )
            entries.append(_ProviderEntry(descriptor, binding))
        provider_keys = tuple(entry.descriptor.provider_key for entry in entries)
        if len(provider_keys) != len(set(provider_keys)):
            _raise_service_error(ProviderSearchServiceErrorCode.ADAPTER_MISMATCH)
        entries.sort(key=lambda entry: entry.descriptor.provider_key)
        object.__setattr__(self, "_entries", tuple(entries))
        object.__setattr__(self, "_clock", clock)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("ProviderSearchService is immutable")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("ProviderSearchService is immutable")
        object.__delattr__(self, name)

    def __repr__(self) -> str:
        return f"ProviderSearchService(provider_count={len(self._entries)})"

    def list_providers(self) -> tuple[SearchProviderDescriptor, ...]:
        return tuple(entry.descriptor for entry in self._entries)

    def _entry(self, provider_key: str) -> _ProviderEntry:
        for entry in self._entries:
            if entry.descriptor.provider_key == provider_key:
                return entry
        _raise_service_error(
            ProviderSearchServiceErrorCode.PROVIDER_NOT_AVAILABLE
        )

    def _prepare(
        self,
        request: object,
        expected_type: type[_Request],
        operation: ProviderOperation,
    ) -> tuple[_Request, _ProviderEntry, Callable[..., object]]:
        if type(request) is not expected_type:
            _raise_service_error(ProviderSearchServiceErrorCode.INVALID_REQUEST)
        typed_request = request
        entry = self._entry(typed_request.provider_key)
        if operation not in entry.binding.operations:
            _raise_service_error(
                ProviderSearchServiceErrorCode.OPERATION_NOT_APPROVED
            )
        try:
            handler = entry.binding.handler_for(operation)
        except ProviderPackageError as error:
            _raise_service_error(
                ProviderSearchServiceErrorCode.ADAPTER_MISMATCH,
                error.code,
            )
        except Exception:
            _raise_service_error(
                ProviderSearchServiceErrorCode.ADAPTER_MISMATCH
            )
        return typed_request, entry, handler

    async def _invoke(
        self,
        entry: _ProviderEntry,
        operation: ProviderOperation,
        handler: Callable[..., object],
        *args: object,
        **kwargs: object,
    ) -> object:
        try:
            awaitable = handler(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except ProviderAdapterError as error:
            _raise_adapter_error(error, entry, operation)
        except Exception:
            _raise_service_error(ProviderSearchServiceErrorCode.UNKNOWN)
        if not inspect.isawaitable(awaitable):
            _raise_service_error(ProviderSearchServiceErrorCode.INVALID_RESULT)
        try:
            return await awaitable  # type: ignore[misc]
        except asyncio.CancelledError:
            raise
        except ProviderAdapterError as error:
            _raise_adapter_error(error, entry, operation)
        except Exception:
            _raise_service_error(ProviderSearchServiceErrorCode.UNKNOWN)

    def _received_at(self) -> datetime:
        try:
            value = self._clock()
        except Exception:
            _raise_service_error(ProviderSearchServiceErrorCode.UNKNOWN)
        if not isinstance(value, datetime):
            _raise_service_error(ProviderSearchServiceErrorCode.INVALID_RESULT)
        return value

    async def search(self, request: VideoSearchRequest) -> VideoSearchEnvelope:
        typed, entry, handler = self._prepare(
            request,
            VideoSearchRequest,
            ProviderOperation.SEARCH,
        )
        result = await self._invoke(
            entry,
            ProviderOperation.SEARCH,
            handler,
            typed.query,
            page=typed.page,
            page_size=typed.page_size,
        )
        if type(result) is not VideoSearchPage:
            _raise_service_error(ProviderSearchServiceErrorCode.INVALID_RESULT)
        try:
            return VideoSearchEnvelope(
                entry.descriptor,
                typed,
                result,
                self._received_at(),
            )
        except ProviderSearchServiceError:
            raise
        except (TypeError, ValueError):
            _raise_service_error(ProviderSearchServiceErrorCode.INVALID_RESULT)

    async def detail(self, request: VideoDetailRequest) -> VideoDetailEnvelope:
        typed, entry, handler = self._prepare(
            request,
            VideoDetailRequest,
            ProviderOperation.DETAIL,
        )
        result = await self._invoke(
            entry,
            ProviderOperation.DETAIL,
            handler,
            typed.external_id,
        )
        if type(result) is not VideoDetail:
            _raise_service_error(ProviderSearchServiceErrorCode.INVALID_RESULT)
        try:
            return VideoDetailEnvelope(
                entry.descriptor,
                typed,
                result,
                self._received_at(),
            )
        except ProviderSearchServiceError:
            raise
        except (TypeError, ValueError):
            _raise_service_error(ProviderSearchServiceErrorCode.INVALID_RESULT)

    async def asset_list(
        self,
        request: VideoAssetListRequest,
    ) -> VideoAssetListEnvelope:
        typed, entry, handler = self._prepare(
            request,
            VideoAssetListRequest,
            ProviderOperation.ASSET_LIST,
        )
        result = await self._invoke(
            entry,
            ProviderOperation.ASSET_LIST,
            handler,
            typed.external_id,
        )
        if type(result) is not tuple:
            _raise_service_error(ProviderSearchServiceErrorCode.INVALID_RESULT)
        try:
            return VideoAssetListEnvelope(
                entry.descriptor,
                typed,
                result,
                self._received_at(),
            )
        except ProviderSearchServiceError:
            raise
        except (TypeError, ValueError):
            _raise_service_error(ProviderSearchServiceErrorCode.INVALID_RESULT)


class _LazyProductionSearchPackages:
    """Resolve search packages on first access (avoids import cycles)."""

    __slots__ = ("_cached",)

    def __init__(self) -> None:
        object.__setattr__(self, "_cached", None)

    def _packages(self) -> tuple[ProviderPackage, ...]:
        cached = object.__getattribute__(self, "_cached")
        if cached is None:
            from app.providers.production_catalog import (
                build_production_search_packages,
            )

            cached = build_production_search_packages()
            object.__setattr__(self, "_cached", cached)
        return cached

    def __iter__(self):
        return iter(self._packages())

    def __len__(self) -> int:
        return len(self._packages())

    def __bool__(self) -> bool:
        return bool(self._packages())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, tuple):
            return self._packages() == other
        return NotImplemented

    def __getitem__(self, index: int) -> ProviderPackage:
        return self._packages()[index]


PRODUCTION_SEARCH_PACKAGES = _LazyProductionSearchPackages()


def build_production_search_service(
    clock: Callable[[], datetime] = _utc_now,
) -> ProviderSearchService:
    return ProviderSearchService(tuple(PRODUCTION_SEARCH_PACKAGES), clock)


__all__ = [
    "PRODUCTION_SEARCH_PACKAGES",
    "ProviderSearchService",
    "build_production_search_service",
]
