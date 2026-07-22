"""Controlled, provider-neutral asset acquisition."""

from __future__ import annotations

from typing import Any

from app.acquisition.contracts import (
    AcquisitionAdapter,
    AcquisitionPackage,
    AssetDownloadDescriptor,
    DownloadOpenResult,
    DownloadServiceError,
    DownloadServiceErrorCode,
)

__all__ = [
    "AcquisitionAdapter",
    "AcquisitionPackage",
    "AcquisitionRegistry",
    "AssetDownloadDescriptor",
    "DownloadOpenResult",
    "DownloadServiceError",
    "DownloadServiceErrorCode",
    "PRODUCTION_ACQUISITION_PACKAGES",
]


def __getattr__(name: str) -> Any:
    if name == "AcquisitionRegistry":
        from app.acquisition.registry import AcquisitionRegistry

        return AcquisitionRegistry
    if name == "PRODUCTION_ACQUISITION_PACKAGES":
        from app.acquisition.registry import PRODUCTION_ACQUISITION_PACKAGES

        return PRODUCTION_ACQUISITION_PACKAGES
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
