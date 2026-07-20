"""Controlled, provider-neutral asset acquisition."""

from app.acquisition.contracts import (
    AcquisitionAdapter,
    AcquisitionPackage,
    AssetDownloadDescriptor,
    DownloadOpenResult,
    DownloadServiceError,
    DownloadServiceErrorCode,
)
from app.acquisition.registry import PRODUCTION_ACQUISITION_PACKAGES, AcquisitionRegistry

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
