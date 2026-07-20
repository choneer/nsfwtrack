"""Immutable contracts for signed Provider apply plans."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum

from app.services.sources import (
    SourceError,
    normalize_source_url,
    validate_source_tracking_metadata,
)


PROVIDER_APPLY_PLAN_FORMAT = "nsfwtrack.provider-apply-plan"
PROVIDER_APPLY_PLAN_VERSION = 1
PROVIDER_APPLY_TOKEN_FORMAT = "nsfwtrack.provider-apply-token"
PROVIDER_APPLY_TOKEN_VERSION = 1
PROVIDER_APPLY_RESULT_FORMAT = "nsfwtrack.provider-apply-result"
PROVIDER_APPLY_RESULT_VERSION = 1

MAX_PROVIDER_APPLY_PLAN_BYTES = 32 * 1024
MAX_PROVIDER_APPLY_PLAN_DEPTH = 12
MAX_PROVIDER_APPLY_PLAN_NODES = 512
MAX_PROVIDER_APPLY_STRING_LENGTH = 4_096
MAX_PROVIDER_APPLY_TUPLE_ITEMS = 64
MAX_PROVIDER_APPLY_DUPLICATE_HINTS = 32
MAX_PROVIDER_APPLY_TOKEN_LENGTH = 50_000
MAX_PROVIDER_APPLY_TOKEN_PAYLOAD_BYTES = 36 * 1024
MAX_PROVIDER_APPLY_CONTEXT_LENGTH = 255
MIN_PROVIDER_APPLY_SECRET_BYTES = 32
MAX_PROVIDER_APPLY_SECRET_BYTES = 4_096
DEFAULT_PROVIDER_APPLY_TOKEN_TTL_SECONDS = 600
MAX_PROVIDER_APPLY_TOKEN_TTL_SECONDS = 900

MAX_ITEM_TITLE_LENGTH = 255
MAX_SOURCE_URL_LENGTH = 2_048
MAX_PROVIDER_KEY_LENGTH = 64
MAX_EXTERNAL_ID_LENGTH = 512
MAX_METADATA_HASH_LENGTH = 96

_PROVIDER_KEY = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_METADATA_HASH = re.compile(r"v1:sha256:[0-9a-f]{64}\Z")
_APPLY_PROJECTION_HASH = _METADATA_HASH

CREATE_FIELD_NAMES = (
    "item.title",
    "item.summary",
    "item.release_date",
    "item_source.url",
    "item_source.normalized_url",
    "item_source.title",
    "item_source.provider_key",
    "item_source.external_id",
    "item_source.last_checked_at",
    "item_source.metadata_hash",
)

UPDATE_FIELD_NAMES = (
    "item.title",
    "item.summary",
    "item.release_date",
    "item_source.last_checked_at",
    "item_source.metadata_hash",
)

_FIELD_NAMES = frozenset((*CREATE_FIELD_NAMES, *UPDATE_FIELD_NAMES))


class ProviderApplyAction(str, Enum):
    CREATE_ITEM = "create_item"
    UPDATE_ITEM = "update_item"


class ProviderApplyCommitStatus(str, Enum):
    COMMITTED = "committed"
    COMMITTED_VERIFIED_AFTER_EXCEPTION = "committed_verified_after_exception"


class ProviderApplyFieldPolicy(str, Enum):
    CREATE_VALUE = "create_value"
    FILL_BLANK = "fill_blank"
    KEEP_LOCAL = "keep_local"
    REFRESH_TRACKING = "refresh_tracking"


class ProviderApplyErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    DETAIL_MISMATCH = "detail_mismatch"
    CANONICAL_URL_REQUIRED = "canonical_url_required"
    SOURCE_URL_INVALID = "source_url_invalid"
    SOURCE_IDENTITY_CONFLICT = "source_identity_conflict"
    SOURCE_URL_CONFLICT = "source_url_conflict"
    SOURCE_ITEM_MISSING = "source_item_missing"
    DATABASE_STATE_INVALID = "database_state_invalid"
    PLAN_INVALID = "plan_invalid"
    PLAN_TOO_LARGE = "plan_too_large"
    TOKEN_INVALID = "token_invalid"
    TOKEN_TOO_LARGE = "token_too_large"
    TOKEN_SIGNATURE_INVALID = "token_signature_invalid"
    TOKEN_CONTEXT_MISMATCH = "token_context_mismatch"
    TOKEN_NOT_YET_VALID = "token_not_yet_valid"
    TOKEN_EXPIRED = "token_expired"
    NOTHING_TO_APPLY = "nothing_to_apply"
    STALE_PLAN = "stale_plan"
    WRITE_CONFLICT = "write_conflict"
    WRITE_FAILED = "write_failed"
    COMMIT_STATE_UNKNOWN = "commit_state_unknown"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True, repr=False)
class ProviderApplyError(RuntimeError):
    code: ProviderApplyErrorCode

    def __post_init__(self) -> None:
        if type(self.code) is not ProviderApplyErrorCode:
            raise TypeError("code must be ProviderApplyErrorCode")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ProviderApplyError(code={self.code.value!r})"


class _RedactedValue:
    __slots__ = ()

    def __str__(self) -> str:
        return type(self).__name__

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


@dataclass(frozen=True, slots=True, repr=False)
class ProviderApplyResult(_RedactedValue):
    format: str
    version: int
    action: ProviderApplyAction
    item_id: int
    source_id: int
    written_fields: tuple[str, ...]
    commit_status: ProviderApplyCommitStatus

    def __post_init__(self) -> None:
        if self.format != PROVIDER_APPLY_RESULT_FORMAT:
            raise ValueError("format is invalid")
        if type(self.version) is not int or self.version != PROVIDER_APPLY_RESULT_VERSION:
            raise ValueError("version is invalid")
        if type(self.action) is not ProviderApplyAction:
            raise TypeError("action must be ProviderApplyAction")
        if type(self.item_id) is not int or self.item_id < 1:
            raise ValueError("item_id must be a positive integer")
        if type(self.source_id) is not int or self.source_id < 1:
            raise ValueError("source_id must be a positive integer")
        if type(self.written_fields) is not tuple or not self.written_fields:
            raise TypeError("written_fields must be a non-empty exact tuple")
        if not all(type(value) is str for value in self.written_fields):
            raise TypeError("written_fields must contain strings")
        field_order = (
            CREATE_FIELD_NAMES
            if self.action is ProviderApplyAction.CREATE_ITEM
            else UPDATE_FIELD_NAMES
        )
        allowed = set(field_order)
        if self.action is ProviderApplyAction.UPDATE_ITEM:
            allowed.remove("item.title")
        if (
            len(self.written_fields) != len(set(self.written_fields))
            or any(value not in allowed for value in self.written_fields)
            or self.written_fields
            != tuple(value for value in field_order if value in self.written_fields)
        ):
            raise ValueError("written_fields are invalid or out of order")
        if type(self.commit_status) is not ProviderApplyCommitStatus:
            raise TypeError("commit_status must be ProviderApplyCommitStatus")


def _optional_text(
    value: str | None,
    *,
    field: str,
    maximum: int = MAX_PROVIDER_APPLY_STRING_LENGTH,
    allow_blank: bool = True,
) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise TypeError(f"{field} must be a string or None")
    if len(value) > maximum or not allow_blank and not value:
        raise ValueError(f"{field} is invalid")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise ValueError(f"{field} is invalid") from None
    return value


def _positive_id(value: int | None, *, field: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 1:
        raise ValueError(f"{field} must be a positive integer or None")
    return value


def _utc(value: datetime | None, *, field: str) -> datetime | None:
    if value is None:
        return None
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _datetime_text(value: datetime) -> str:
    normalized = _utc(value, field="datetime")
    assert normalized is not None
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _optional_datetime_text(value: datetime | None) -> str | None:
    return None if value is None else _datetime_text(value)


def _release_date(value: str | None, *, field: str) -> str | None:
    value = _optional_text(value, field=field, maximum=32)
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must be an ISO calendar date") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be a canonical ISO calendar date")
    return value


def _canonical_url(value: str, *, field: str) -> str:
    if type(value) is not str or not value or len(value) > MAX_SOURCE_URL_LENGTH:
        raise ValueError(f"{field} is invalid")
    try:
        normalized = normalize_source_url(value)
    except SourceError:
        raise ValueError(f"{field} is invalid") from None
    if normalized != value:
        raise ValueError(f"{field} must already be normalized")
    return value


def _provider_identity(provider_key: str, external_id: str) -> tuple[str, str]:
    if (
        type(provider_key) is not str
        or _PROVIDER_KEY.fullmatch(provider_key) is None
        or len(provider_key) > MAX_PROVIDER_KEY_LENGTH
    ):
        raise ValueError("provider_key is invalid")
    if (
        type(external_id) is not str
        or not external_id
        or len(external_id) > MAX_EXTERNAL_ID_LENGTH
        or any(ord(character) < 32 or ord(character) == 127 for character in external_id)
    ):
        raise ValueError("external_id is invalid")
    return provider_key, external_id


def _field_value(value: str | int | None, *, field: str) -> str | int | None:
    if value is None:
        return None
    if type(value) is str:
        return _optional_text(value, field=field)
    if type(value) is int and -(2**63) <= value <= 2**63 - 1:
        return value
    raise TypeError(f"{field} must be a bounded string, integer, or None")


@dataclass(frozen=True, slots=True, repr=False)
class ProviderApplyFieldChange(_RedactedValue):
    field_name: str
    policy: ProviderApplyFieldPolicy
    current_value: str | int | None
    proposed_value: str | int | None
    will_write: bool

    def __post_init__(self) -> None:
        if type(self.field_name) is not str or self.field_name not in _FIELD_NAMES:
            raise ValueError("field_name is not allowed")
        if type(self.policy) is not ProviderApplyFieldPolicy:
            raise TypeError("policy must be ProviderApplyFieldPolicy")
        object.__setattr__(
            self,
            "current_value",
            _field_value(self.current_value, field="current_value"),
        )
        object.__setattr__(
            self,
            "proposed_value",
            _field_value(self.proposed_value, field="proposed_value"),
        )
        if type(self.will_write) is not bool:
            raise TypeError("will_write must be a boolean")

        if self.policy is ProviderApplyFieldPolicy.CREATE_VALUE:
            if self.current_value is not None or self.will_write is not (
                self.proposed_value is not None
            ):
                raise ValueError("create_value has an invalid state")
        elif self.policy is ProviderApplyFieldPolicy.FILL_BLANK:
            if (
                self.field_name not in {"item.summary", "item.release_date"}
                or self.current_value not in {None, ""}
                or type(self.proposed_value) is not str
                or not self.proposed_value
                or not self.will_write
            ):
                raise ValueError("fill_blank has an invalid state")
        elif self.policy is ProviderApplyFieldPolicy.KEEP_LOCAL:
            if self.field_name not in {
                "item.title",
                "item.summary",
                "item.release_date",
            } or self.will_write:
                raise ValueError("keep_local has an invalid state")
        elif self.policy is ProviderApplyFieldPolicy.REFRESH_TRACKING:
            if self.field_name not in {
                "item_source.last_checked_at",
                "item_source.metadata_hash",
            } or self.proposed_value is None or self.will_write is not (
                self.current_value != self.proposed_value
            ):
                raise ValueError("refresh_tracking has an invalid state")


@dataclass(frozen=True, slots=True, repr=False)
class ProviderApplyItemSnapshot(_RedactedValue):
    item_id: int | None
    title: str | None
    summary: str | None
    release_date: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", _positive_id(self.item_id, field="item_id"))
        object.__setattr__(
            self,
            "title",
            _optional_text(
                self.title,
                field="title",
                maximum=MAX_ITEM_TITLE_LENGTH,
                allow_blank=False,
            ),
        )
        object.__setattr__(
            self,
            "summary",
            _optional_text(self.summary, field="summary"),
        )
        object.__setattr__(
            self,
            "release_date",
            _release_date(self.release_date, field="release_date"),
        )
        if self.item_id is None and any(
            value is not None for value in (self.title, self.summary, self.release_date)
        ):
            raise ValueError("missing item snapshot must not contain local values")
        if self.item_id is not None and self.title is None:
            raise ValueError("existing item snapshot requires title")


@dataclass(frozen=True, slots=True, repr=False)
class ProviderApplySourceSnapshot(_RedactedValue):
    source_id: int | None
    item_id: int | None
    provider_key: str
    external_id: str
    normalized_url: str
    last_checked_at: datetime | None
    metadata_hash: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _positive_id(self.source_id, field="source_id"),
        )
        object.__setattr__(self, "item_id", _positive_id(self.item_id, field="item_id"))
        provider_key, external_id = _provider_identity(
            self.provider_key,
            self.external_id,
        )
        object.__setattr__(self, "provider_key", provider_key)
        object.__setattr__(self, "external_id", external_id)
        object.__setattr__(
            self,
            "normalized_url",
            _canonical_url(self.normalized_url, field="normalized_url"),
        )
        object.__setattr__(
            self,
            "last_checked_at",
            _utc(self.last_checked_at, field="last_checked_at"),
        )
        if self.metadata_hash is not None and (
            type(self.metadata_hash) is not str
            or len(self.metadata_hash) > MAX_METADATA_HASH_LENGTH
            or _METADATA_HASH.fullmatch(self.metadata_hash) is None
        ):
            raise ValueError("metadata_hash is invalid")
        try:
            tracking = validate_source_tracking_metadata(
                provider_key=self.provider_key,
                external_id=self.external_id,
                last_checked_at=self.last_checked_at,
                metadata_hash=self.metadata_hash,
            )
        except SourceError:
            raise ValueError("source tracking metadata is invalid") from None
        object.__setattr__(self, "last_checked_at", tracking.last_checked_at)
        if (self.source_id is None) != (self.item_id is None):
            raise ValueError("source and item identity must both exist or both be absent")
        if self.source_id is None and (
            self.last_checked_at is not None or self.metadata_hash is not None
        ):
            raise ValueError("missing source snapshot must not contain tracking state")


@dataclass(frozen=True, slots=True, repr=False)
class ProviderApplyPlan(_RedactedValue):
    format: str
    version: int
    action: ProviderApplyAction
    provider_key: str
    external_id: str
    normalized_source_url: str
    item_snapshot: ProviderApplyItemSnapshot
    source_snapshot: ProviderApplySourceSnapshot
    field_changes: tuple[ProviderApplyFieldChange, ...]
    duplicate_title_item_ids: tuple[int, ...]
    received_at: datetime
    source_updated_at: datetime | None
    apply_projection_hash: str

    @property
    def has_writes(self) -> bool:
        return any(change.will_write for change in self.field_changes)

    def __post_init__(self) -> None:
        if self.format != PROVIDER_APPLY_PLAN_FORMAT:
            raise ValueError("format is invalid")
        if type(self.version) is not int or self.version != PROVIDER_APPLY_PLAN_VERSION:
            raise ValueError("version is invalid")
        if type(self.action) is not ProviderApplyAction:
            raise TypeError("action must be ProviderApplyAction")
        provider_key, external_id = _provider_identity(
            self.provider_key,
            self.external_id,
        )
        object.__setattr__(self, "provider_key", provider_key)
        object.__setattr__(self, "external_id", external_id)
        object.__setattr__(
            self,
            "normalized_source_url",
            _canonical_url(self.normalized_source_url, field="normalized_source_url"),
        )
        if type(self.item_snapshot) is not ProviderApplyItemSnapshot:
            raise TypeError("item_snapshot has an invalid type")
        if type(self.source_snapshot) is not ProviderApplySourceSnapshot:
            raise TypeError("source_snapshot has an invalid type")
        if type(self.field_changes) is not tuple or not all(
            type(change) is ProviderApplyFieldChange for change in self.field_changes
        ):
            raise TypeError("field_changes must be an exact tuple")
        if not self.field_changes or len(self.field_changes) > MAX_PROVIDER_APPLY_TUPLE_ITEMS:
            raise ValueError("field_changes has an invalid size")
        field_names = tuple(change.field_name for change in self.field_changes)
        expected_names = (
            CREATE_FIELD_NAMES
            if self.action is ProviderApplyAction.CREATE_ITEM
            else UPDATE_FIELD_NAMES
        )
        if field_names != expected_names:
            raise ValueError("field_changes are incomplete or out of order")
        if type(self.duplicate_title_item_ids) is not tuple or not all(
            type(value) is int and value > 0
            for value in self.duplicate_title_item_ids
        ):
            raise TypeError("duplicate_title_item_ids must be a positive integer tuple")
        if (
            len(self.duplicate_title_item_ids) > MAX_PROVIDER_APPLY_DUPLICATE_HINTS
            or self.duplicate_title_item_ids
            != tuple(sorted(set(self.duplicate_title_item_ids)))
        ):
            raise ValueError("duplicate_title_item_ids must be sorted and unique")
        object.__setattr__(
            self,
            "received_at",
            _utc(self.received_at, field="received_at"),
        )
        object.__setattr__(
            self,
            "source_updated_at",
            _utc(self.source_updated_at, field="source_updated_at"),
        )
        if (
            type(self.apply_projection_hash) is not str
            or _APPLY_PROJECTION_HASH.fullmatch(self.apply_projection_hash) is None
        ):
            raise ValueError("apply_projection_hash is invalid")
        if (
            self.source_snapshot.provider_key != self.provider_key
            or self.source_snapshot.external_id != self.external_id
            or self.source_snapshot.normalized_url != self.normalized_source_url
        ):
            raise ValueError("source snapshot does not match plan identity")
        changes = {change.field_name: change for change in self.field_changes}
        if self.action is ProviderApplyAction.CREATE_ITEM:
            if self.item_snapshot.item_id is not None or self.source_snapshot.source_id is not None:
                raise ValueError("create_item requires absent snapshots")
            if any(
                change.policy is not ProviderApplyFieldPolicy.CREATE_VALUE
                for change in self.field_changes
            ):
                raise ValueError("create_item requires create_value changes")
            required_values = {
                "item.title": changes["item.title"].proposed_value,
                "item_source.url": changes["item_source.url"].proposed_value,
                "item_source.normalized_url": changes[
                    "item_source.normalized_url"
                ].proposed_value,
                "item_source.title": changes["item_source.title"].proposed_value,
                "item_source.provider_key": changes[
                    "item_source.provider_key"
                ].proposed_value,
                "item_source.external_id": changes[
                    "item_source.external_id"
                ].proposed_value,
                "item_source.last_checked_at": changes[
                    "item_source.last_checked_at"
                ].proposed_value,
                "item_source.metadata_hash": changes[
                    "item_source.metadata_hash"
                ].proposed_value,
            }
            if any(value is None for value in required_values.values()):
                raise ValueError("create_item is missing a required value")
            if (
                required_values["item_source.url"] != self.normalized_source_url
                or required_values["item_source.normalized_url"]
                != self.normalized_source_url
                or required_values["item_source.title"]
                != required_values["item.title"]
                or required_values["item_source.provider_key"] != self.provider_key
                or required_values["item_source.external_id"] != self.external_id
            ):
                raise ValueError("create_item values do not match plan identity")
        else:
            if (
                self.item_snapshot.item_id is None
                or self.source_snapshot.source_id is None
                or self.source_snapshot.item_id != self.item_snapshot.item_id
                or self.item_snapshot.item_id in self.duplicate_title_item_ids
            ):
                raise ValueError("update_item requires matching existing snapshots")
            expected_policies = {
                "item.title": {ProviderApplyFieldPolicy.KEEP_LOCAL},
                "item.summary": {
                    ProviderApplyFieldPolicy.FILL_BLANK,
                    ProviderApplyFieldPolicy.KEEP_LOCAL,
                },
                "item.release_date": {
                    ProviderApplyFieldPolicy.FILL_BLANK,
                    ProviderApplyFieldPolicy.KEEP_LOCAL,
                },
                "item_source.last_checked_at": {
                    ProviderApplyFieldPolicy.REFRESH_TRACKING
                },
                "item_source.metadata_hash": {
                    ProviderApplyFieldPolicy.REFRESH_TRACKING
                },
            }
            if any(
                change.policy not in expected_policies[change.field_name]
                for change in self.field_changes
            ):
                raise ValueError("update_item has an invalid field policy")
            if (
                changes["item.title"].current_value != self.item_snapshot.title
                or changes["item.summary"].current_value
                != self.item_snapshot.summary
                or changes["item.release_date"].current_value
                != self.item_snapshot.release_date
                or changes["item_source.last_checked_at"].current_value
                != _optional_datetime_text(self.source_snapshot.last_checked_at)
                or changes["item_source.metadata_hash"].current_value
                != self.source_snapshot.metadata_hash
            ):
                raise ValueError("update_item changes do not match snapshots")

        if (
            changes["item_source.last_checked_at"].proposed_value
            != _datetime_text(self.received_at)
            or changes["item_source.metadata_hash"].proposed_value
            != self.apply_projection_hash
        ):
            raise ValueError("tracking changes do not match plan projection")
        projection = {
            "provider_key": self.provider_key,
            "external_id": self.external_id,
            "normalized_source_url": self.normalized_source_url,
            "title": changes["item.title"].proposed_value,
            "summary": changes["item.summary"].proposed_value,
            "release_date": changes["item.release_date"].proposed_value,
            "received_at": _datetime_text(self.received_at),
            "source_updated_at": _optional_datetime_text(self.source_updated_at),
        }
        try:
            projection_bytes = json.dumps(
                projection,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8", "strict")
        except (TypeError, ValueError, UnicodeEncodeError):
            raise ValueError("apply projection is invalid") from None
        expected_hash = "v1:sha256:" + hashlib.sha256(projection_bytes).hexdigest()
        if expected_hash != self.apply_projection_hash:
            raise ValueError("apply_projection_hash does not match plan")


__all__ = [
    "CREATE_FIELD_NAMES",
    "DEFAULT_PROVIDER_APPLY_TOKEN_TTL_SECONDS",
    "MAX_PROVIDER_APPLY_CONTEXT_LENGTH",
    "MAX_PROVIDER_APPLY_DUPLICATE_HINTS",
    "MAX_PROVIDER_APPLY_PLAN_BYTES",
    "MAX_PROVIDER_APPLY_PLAN_DEPTH",
    "MAX_PROVIDER_APPLY_PLAN_NODES",
    "MAX_PROVIDER_APPLY_SECRET_BYTES",
    "MAX_PROVIDER_APPLY_STRING_LENGTH",
    "MAX_PROVIDER_APPLY_TOKEN_LENGTH",
    "MAX_PROVIDER_APPLY_TOKEN_PAYLOAD_BYTES",
    "MAX_PROVIDER_APPLY_TOKEN_TTL_SECONDS",
    "MAX_PROVIDER_APPLY_TUPLE_ITEMS",
    "MIN_PROVIDER_APPLY_SECRET_BYTES",
    "PROVIDER_APPLY_PLAN_FORMAT",
    "PROVIDER_APPLY_PLAN_VERSION",
    "PROVIDER_APPLY_RESULT_FORMAT",
    "PROVIDER_APPLY_RESULT_VERSION",
    "PROVIDER_APPLY_TOKEN_FORMAT",
    "PROVIDER_APPLY_TOKEN_VERSION",
    "UPDATE_FIELD_NAMES",
    "ProviderApplyAction",
    "ProviderApplyCommitStatus",
    "ProviderApplyError",
    "ProviderApplyErrorCode",
    "ProviderApplyFieldChange",
    "ProviderApplyFieldPolicy",
    "ProviderApplyItemSnapshot",
    "ProviderApplyPlan",
    "ProviderApplyResult",
    "ProviderApplySourceSnapshot",
]
