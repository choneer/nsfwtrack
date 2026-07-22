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


class _LazyProductionAcquisitionPackages:
    """Resolve acquisition packages on first access."""

    __slots__ = ("_cached",)

    def __init__(self) -> None:
        object.__setattr__(self, "_cached", None)

    def _packages(self) -> tuple[AcquisitionPackage, ...]:
        cached = object.__getattribute__(self, "_cached")
        if cached is None:
            from app.providers.production_catalog import (
                build_production_acquisition_packages,
            )

            cached = build_production_acquisition_packages()
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

    def __getitem__(self, index: int) -> AcquisitionPackage:
        return self._packages()[index]


PRODUCTION_ACQUISITION_PACKAGES = _LazyProductionAcquisitionPackages()


def build_production_acquisition_registry() -> AcquisitionRegistry:
    return AcquisitionRegistry(tuple(PRODUCTION_ACQUISITION_PACKAGES))
