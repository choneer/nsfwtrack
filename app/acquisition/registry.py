from __future__ import annotations

from app.acquisition.contracts import (
    AcquisitionPackage,
    DownloadServiceError,
    DownloadServiceErrorCode,
)


class AcquisitionRegistry:
    def __init__(self, packages: tuple[AcquisitionPackage, ...] = ()) -> None:
        if not isinstance(packages, tuple) or not all(
            type(package) is AcquisitionPackage for package in packages
        ):
            raise TypeError("packages must be an exact immutable tuple")
        if len({package.provider_key for package in packages}) != len(packages):
            raise ValueError("duplicate provider package")
        self._packages = {package.provider_key: package for package in packages}

    @property
    def packages(self) -> tuple[AcquisitionPackage, ...]:
        return tuple(self._packages.values())

    def require(self, provider_key: str, *, download: bool = False) -> AcquisitionPackage:
        package = self._packages.get(provider_key)
        if package is None:
            raise DownloadServiceError(DownloadServiceErrorCode.PROVIDER_NOT_AVAILABLE)
        approved = package.approved_download if download else package.approved_asset_list
        if not approved:
            raise DownloadServiceError(DownloadServiceErrorCode.OPERATION_NOT_APPROVED)
        return package


PRODUCTION_ACQUISITION_PACKAGES: tuple[AcquisitionPackage, ...] = ()


def build_production_acquisition_registry() -> AcquisitionRegistry:
    return AcquisitionRegistry(PRODUCTION_ACQUISITION_PACKAGES)
