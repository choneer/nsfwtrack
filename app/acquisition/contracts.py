from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from app.source_adapters.contracts import SourceAssetKind

_PROVIDER_KEY = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_OPAQUE_ID = re.compile(r"[A-Za-z0-9_~-](?:[A-Za-z0-9._~-]{0,510}[A-Za-z0-9_~-])?\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MIME = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*\Z")


class DownloadServiceErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    PROVIDER_NOT_AVAILABLE = "provider_not_available"
    OPERATION_NOT_APPROVED = "operation_not_approved"
    AUTH_REQUIRED = "auth_required"
    ASSET_NOT_FOUND = "asset_not_found"
    SNAPSHOT_CHANGED = "snapshot_changed"
    TARGET_INVALID = "target_invalid"
    TARGET_EXISTS = "target_exists"
    TOO_LARGE = "too_large"
    TYPE_REJECTED = "type_rejected"
    INTEGRITY_FAILED = "integrity_failed"
    RANGE_INVALID = "range_invalid"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    LEASE_LOST = "lease_lost"
    LEASE_CONFLICT = "lease_conflict"
    STORAGE_UNSAFE = "storage_unsafe"
    PUBLISH_FAILED = "publish_failed"
    LINK_FAILED = "link_failed"
    WRITE_FAILED = "write_failed"
    OUTCOME_UNKNOWN = "outcome_unknown"
    PROVIDER_ERROR = "provider_error"


class DownloadServiceError(RuntimeError):
    def __init__(self, code: DownloadServiceErrorCode) -> None:
        if not isinstance(code, DownloadServiceErrorCode):
            raise TypeError("code must be DownloadServiceErrorCode")
        self.code = code
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"DownloadServiceError(code={self.code.value!r})"


def _opaque(value: str, *, maximum: int = 512) -> str:
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or _OPAQUE_ID.fullmatch(value) is None
        or ".." in value
    ):
        raise ValueError("identity must be opaque")
    return value


@dataclass(frozen=True, slots=True, repr=False)
class AssetDownloadDescriptor:
    provider_key: str
    external_id: str
    asset_id: str
    kind: SourceAssetKind
    display_name: str
    suggested_filename: str
    mime_type: str
    expected_bytes: int | None = None
    expected_sha256: str | None = None
    requires_auth: bool = False
    resume_supported: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.provider_key, str) or _PROVIDER_KEY.fullmatch(self.provider_key) is None:
            raise ValueError("provider_key is invalid")
        _opaque(self.external_id)
        _opaque(self.asset_id)
        if not isinstance(self.kind, SourceAssetKind):
            raise TypeError("kind is invalid")
        for name, value, maximum in (
            ("display_name", self.display_name, 500),
            ("suggested_filename", self.suggested_filename, 255),
        ):
            if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > maximum:
                raise ValueError(f"{name} is invalid")
            if any(ord(character) < 32 or ord(character) == 127 for character in value):
                raise ValueError(f"{name} contains control characters")
        if (
            self.suggested_filename in {".", ".."}
            or "/" in self.suggested_filename
            or "\\" in self.suggested_filename
            or "%" in self.suggested_filename
            or "\x00" in self.suggested_filename
        ):
            raise ValueError("suggested_filename is not a basename")
        if not isinstance(self.mime_type, str) or _MIME.fullmatch(self.mime_type) is None:
            raise ValueError("mime_type is invalid")
        if self.expected_bytes is not None and (
            not isinstance(self.expected_bytes, int)
            or isinstance(self.expected_bytes, bool)
            or self.expected_bytes < 1
        ):
            raise ValueError("expected_bytes is invalid")
        if self.expected_sha256 is not None and (
            not isinstance(self.expected_sha256, str)
            or _SHA256.fullmatch(self.expected_sha256) is None
        ):
            raise ValueError("expected_sha256 is invalid")
        if not isinstance(self.requires_auth, bool) or not isinstance(self.resume_supported, bool):
            raise TypeError("capability facts must be boolean")

    def __repr__(self) -> str:
        return "AssetDownloadDescriptor()"


@dataclass(frozen=True, slots=True, repr=False)
class DownloadOpenResult:
    chunks: AsyncIterator[bytes]
    status_code: int
    mime_type: str
    content_length: int | None = None
    range_start: int | None = None
    range_end: int | None = None
    range_total: int | None = None

    def __post_init__(self) -> None:
        if not hasattr(self.chunks, "__aiter__"):
            raise TypeError("chunks must be an async iterator")
        if self.status_code not in {200, 206}:
            raise ValueError("status_code is invalid")
        if not isinstance(self.mime_type, str) or _MIME.fullmatch(self.mime_type) is None:
            raise ValueError("mime_type is invalid")
        for value in (self.content_length, self.range_start, self.range_end, self.range_total):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError("response size fact is invalid")

    def __repr__(self) -> str:
        return "DownloadOpenResult()"


@runtime_checkable
class AcquisitionAdapter(Protocol):
    provider_key: str

    async def list_assets(self, external_id: str) -> tuple[AssetDownloadDescriptor, ...]: ...

    async def open_asset(
        self,
        external_id: str,
        asset_id: str,
        *,
        offset: int,
        timeout_seconds: int,
    ) -> DownloadOpenResult: ...


@dataclass(frozen=True, slots=True)
class AcquisitionPackage:
    provider_key: str
    adapter: AcquisitionAdapter
    approved_asset_list: bool
    approved_download: bool

    def __post_init__(self) -> None:
        if _PROVIDER_KEY.fullmatch(self.provider_key) is None:
            raise ValueError("provider_key is invalid")
        if not isinstance(self.adapter, AcquisitionAdapter):
            raise TypeError("adapter does not satisfy AcquisitionAdapter")
        if self.adapter.provider_key != self.provider_key:
            raise ValueError("adapter provider mismatch")
        if not isinstance(self.approved_asset_list, bool) or not isinstance(self.approved_download, bool):
            raise TypeError("approval facts must be boolean")
