"""Read-only apply-plan builder, canonical serializer, and HMAC token service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Item, ItemSource
from app.provider_apply.contracts import (
    CREATE_FIELD_NAMES,
    DEFAULT_PROVIDER_APPLY_TOKEN_TTL_SECONDS,
    MAX_ITEM_TITLE_LENGTH,
    MAX_PROVIDER_APPLY_CONTEXT_LENGTH,
    MAX_PROVIDER_APPLY_DUPLICATE_HINTS,
    MAX_PROVIDER_APPLY_PLAN_BYTES,
    MAX_PROVIDER_APPLY_PLAN_DEPTH,
    MAX_PROVIDER_APPLY_PLAN_NODES,
    MAX_PROVIDER_APPLY_SECRET_BYTES,
    MAX_PROVIDER_APPLY_STRING_LENGTH,
    MAX_PROVIDER_APPLY_TOKEN_LENGTH,
    MAX_PROVIDER_APPLY_TOKEN_PAYLOAD_BYTES,
    MAX_PROVIDER_APPLY_TOKEN_TTL_SECONDS,
    MAX_PROVIDER_APPLY_TUPLE_ITEMS,
    MIN_PROVIDER_APPLY_SECRET_BYTES,
    PROVIDER_APPLY_PLAN_FORMAT,
    PROVIDER_APPLY_PLAN_VERSION,
    PROVIDER_APPLY_TOKEN_FORMAT,
    PROVIDER_APPLY_TOKEN_VERSION,
    UPDATE_FIELD_NAMES,
    ProviderApplyAction,
    ProviderApplyError,
    ProviderApplyErrorCode,
    ProviderApplyFieldChange,
    ProviderApplyFieldPolicy,
    ProviderApplyItemSnapshot,
    ProviderApplyPlan,
    ProviderApplySourceSnapshot,
)
from app.services.sources import (
    SourceError,
    normalize_source_url,
    validate_source_tracking_metadata,
)
from app.source_search import VideoDetailEnvelope


_TOKEN_PREFIX = "nspap1"
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+\Z")
_DOMAIN_CONTEXT = b"nsfwtrack.provider-apply-token.context.v1\0"
_DOMAIN_TOKEN = b"nsfwtrack.provider-apply-token.mac.v1\0"


class _DuplicateKeyError(ValueError):
    pass


class _DecodeError(ValueError):
    pass


class _ResourceLimitError(ValueError):
    pass


def _raise(code: ProviderApplyErrorCode) -> None:
    raise ProviderApplyError(code) from None


def _utc(value: datetime, *, code: ProviderApplyErrorCode) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        _raise(code)
    return value.astimezone(UTC)


def _datetime_text(value: datetime) -> str:
    normalized = _utc(value, code=ProviderApplyErrorCode.PLAN_INVALID)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _optional_datetime_text(value: datetime | None) -> str | None:
    return None if value is None else _datetime_text(value)


def _parse_datetime(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise _DecodeError
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise _DecodeError from None
    if _datetime_text(parsed) != value:
        raise _DecodeError
    return parsed


def _parse_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value)


def _release_date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise _DecodeError from None


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise _DecodeError


def _audit_resources(
    value: object,
    *,
    maximum_depth: int = MAX_PROVIDER_APPLY_PLAN_DEPTH,
    maximum_nodes: int = MAX_PROVIDER_APPLY_PLAN_NODES,
) -> None:
    nodes = 0

    def visit(current: object, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > maximum_depth or nodes > maximum_nodes:
            raise _ResourceLimitError
        if type(current) is dict:
            for key, child in current.items():
                nodes += 1
                if (
                    nodes > maximum_nodes
                    or type(key) is not str
                    or len(key) > MAX_PROVIDER_APPLY_STRING_LENGTH
                ):
                    raise _ResourceLimitError
                try:
                    key.encode("utf-8", "strict")
                except UnicodeEncodeError:
                    raise _DecodeError from None
                visit(child, depth + 1)
            return
        if type(current) is list:
            if len(current) > MAX_PROVIDER_APPLY_TUPLE_ITEMS:
                raise _ResourceLimitError
            for child in current:
                visit(child, depth + 1)
            return
        if type(current) is str:
            if len(current) > MAX_PROVIDER_APPLY_STRING_LENGTH:
                raise _ResourceLimitError
            try:
                current.encode("utf-8", "strict")
            except UnicodeEncodeError:
                raise _DecodeError from None
            return
        if current is None or type(current) in {bool, int}:
            return
        raise _DecodeError

    visit(value, 1)


def _decode_json_bytes(
    payload: object,
    *,
    maximum_bytes: int,
    too_large: ProviderApplyErrorCode,
    invalid: ProviderApplyErrorCode,
) -> dict[str, object]:
    if type(payload) is not bytes:
        _raise(invalid)
    if len(payload) > maximum_bytes:
        _raise(too_large)
    try:
        text = payload.decode("utf-8", "strict")
    except UnicodeDecodeError:
        _raise(invalid)
    try:
        document = json.loads(
            text,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except _DuplicateKeyError:
        _raise(invalid)
    except RecursionError:
        _raise(too_large)
    except (json.JSONDecodeError, _DecodeError, ValueError):
        _raise(invalid)
    try:
        _audit_resources(document)
    except _ResourceLimitError:
        _raise(too_large)
    except _DecodeError:
        _raise(invalid)
    if type(document) is not dict:
        _raise(invalid)
    return document


def _expect_keys(value: object, expected: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != expected:
        raise _DecodeError
    return value


_PLAN_KEYS = frozenset(
    {
        "format",
        "version",
        "action",
        "provider_key",
        "external_id",
        "normalized_source_url",
        "item_snapshot",
        "source_snapshot",
        "field_changes",
        "duplicate_title_item_ids",
        "received_at",
        "source_updated_at",
        "apply_projection_hash",
    }
)
_ITEM_SNAPSHOT_KEYS = frozenset({"item_id", "title", "summary", "release_date"})
_SOURCE_SNAPSHOT_KEYS = frozenset(
    {
        "source_id",
        "item_id",
        "provider_key",
        "external_id",
        "normalized_url",
        "last_checked_at",
        "metadata_hash",
    }
)
_FIELD_CHANGE_KEYS = frozenset(
    {"field_name", "policy", "current_value", "proposed_value", "will_write"}
)
_TOKEN_KEYS = frozenset({"format", "version", "issued_at", "expires_at", "plan"})


def _validate_plan_document_shape(value: object) -> dict[str, object]:
    document = _expect_keys(value, _PLAN_KEYS)
    _expect_keys(document["item_snapshot"], _ITEM_SNAPSHOT_KEYS)
    _expect_keys(document["source_snapshot"], _SOURCE_SNAPSHOT_KEYS)
    changes = document["field_changes"]
    if type(changes) is not list:
        raise _DecodeError
    for change in changes:
        _expect_keys(change, _FIELD_CHANGE_KEYS)
    duplicate_ids = document["duplicate_title_item_ids"]
    if type(duplicate_ids) is not list:
        raise _DecodeError
    return document


def _field_change_raw(change: ProviderApplyFieldChange) -> dict[str, object]:
    return {
        "field_name": change.field_name,
        "policy": change.policy.value,
        "current_value": change.current_value,
        "proposed_value": change.proposed_value,
        "will_write": change.will_write,
    }


def _plan_raw(plan: ProviderApplyPlan) -> dict[str, object]:
    if type(plan) is not ProviderApplyPlan:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    return {
        "format": plan.format,
        "version": plan.version,
        "action": plan.action.value,
        "provider_key": plan.provider_key,
        "external_id": plan.external_id,
        "normalized_source_url": plan.normalized_source_url,
        "item_snapshot": {
            "item_id": plan.item_snapshot.item_id,
            "title": plan.item_snapshot.title,
            "summary": plan.item_snapshot.summary,
            "release_date": plan.item_snapshot.release_date,
        },
        "source_snapshot": {
            "source_id": plan.source_snapshot.source_id,
            "item_id": plan.source_snapshot.item_id,
            "provider_key": plan.source_snapshot.provider_key,
            "external_id": plan.source_snapshot.external_id,
            "normalized_url": plan.source_snapshot.normalized_url,
            "last_checked_at": _optional_datetime_text(
                plan.source_snapshot.last_checked_at
            ),
            "metadata_hash": plan.source_snapshot.metadata_hash,
        },
        "field_changes": [_field_change_raw(change) for change in plan.field_changes],
        "duplicate_title_item_ids": list(plan.duplicate_title_item_ids),
        "received_at": _datetime_text(plan.received_at),
        "source_updated_at": _optional_datetime_text(plan.source_updated_at),
        "apply_projection_hash": plan.apply_projection_hash,
    }


def _plan_from_document(value: object) -> ProviderApplyPlan:
    try:
        document = _validate_plan_document_shape(value)
        item_raw = _expect_keys(document["item_snapshot"], _ITEM_SNAPSHOT_KEYS)
        source_raw = _expect_keys(document["source_snapshot"], _SOURCE_SNAPSHOT_KEYS)
        changes_raw = document["field_changes"]
        duplicate_raw = document["duplicate_title_item_ids"]
        if type(changes_raw) is not list or type(duplicate_raw) is not list:
            raise _DecodeError
        changes = tuple(
            ProviderApplyFieldChange(
                field_name=cast_value["field_name"],
                policy=ProviderApplyFieldPolicy(cast_value["policy"]),
                current_value=cast_value["current_value"],
                proposed_value=cast_value["proposed_value"],
                will_write=cast_value["will_write"],
            )
            for cast_value in (
                _expect_keys(change, _FIELD_CHANGE_KEYS) for change in changes_raw
            )
        )
        plan = ProviderApplyPlan(
            format=document["format"],
            version=document["version"],
            action=ProviderApplyAction(document["action"]),
            provider_key=document["provider_key"],
            external_id=document["external_id"],
            normalized_source_url=document["normalized_source_url"],
            item_snapshot=ProviderApplyItemSnapshot(
                item_id=item_raw["item_id"],
                title=item_raw["title"],
                summary=item_raw["summary"],
                release_date=item_raw["release_date"],
            ),
            source_snapshot=ProviderApplySourceSnapshot(
                source_id=source_raw["source_id"],
                item_id=source_raw["item_id"],
                provider_key=source_raw["provider_key"],
                external_id=source_raw["external_id"],
                normalized_url=source_raw["normalized_url"],
                last_checked_at=_parse_optional_datetime(
                    source_raw["last_checked_at"]
                ),
                metadata_hash=source_raw["metadata_hash"],
            ),
            field_changes=changes,
            duplicate_title_item_ids=tuple(duplicate_raw),
            received_at=_parse_datetime(document["received_at"]),
            source_updated_at=_parse_optional_datetime(document["source_updated_at"]),
            apply_projection_hash=document["apply_projection_hash"],
        )
    except ProviderApplyError:
        raise
    except (KeyError, TypeError, ValueError, _DecodeError):
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    if _plan_raw(plan) != document:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    return plan


def serialize_provider_apply_plan(plan: ProviderApplyPlan) -> bytes:
    try:
        payload = _canonical_json_bytes(_plan_raw(plan))
    except _DecodeError:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    if len(payload) > MAX_PROVIDER_APPLY_PLAN_BYTES:
        _raise(ProviderApplyErrorCode.PLAN_TOO_LARGE)
    return payload


def parse_provider_apply_plan(payload: bytes) -> ProviderApplyPlan:
    document = _decode_json_bytes(
        payload,
        maximum_bytes=MAX_PROVIDER_APPLY_PLAN_BYTES,
        too_large=ProviderApplyErrorCode.PLAN_TOO_LARGE,
        invalid=ProviderApplyErrorCode.PLAN_INVALID,
    )
    return _plan_from_document(document)


def _projection_raw(
    envelope: VideoDetailEnvelope,
    normalized_source_url: str,
) -> dict[str, object]:
    detail = envelope.detail
    return {
        "provider_key": envelope.request.provider_key,
        "external_id": envelope.request.external_id,
        "normalized_source_url": normalized_source_url,
        "title": detail.title,
        "summary": detail.summary,
        "release_date": _release_date_text(detail.release_date),
        "received_at": _datetime_text(envelope.received_at),
        "source_updated_at": _optional_datetime_text(detail.source_updated_at),
    }


def compute_provider_apply_projection_hash(
    envelope: VideoDetailEnvelope,
    normalized_source_url: str,
) -> str:
    if type(envelope) is not VideoDetailEnvelope or type(normalized_source_url) is not str:
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)
    try:
        payload = _canonical_json_bytes(
            _projection_raw(envelope, normalized_source_url)
        )
    except _DecodeError:
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)
    return "v1:sha256:" + hashlib.sha256(payload).hexdigest()


def _validate_envelope(envelope: object) -> tuple[VideoDetailEnvelope, str]:
    if type(envelope) is not VideoDetailEnvelope:
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)
    typed = envelope
    if (
        typed.provider.provider_key != typed.request.provider_key
        or typed.detail.provider_key != typed.request.provider_key
        or typed.detail.external_id != typed.request.external_id
    ):
        _raise(ProviderApplyErrorCode.DETAIL_MISMATCH)
    if len(typed.detail.title) > MAX_ITEM_TITLE_LENGTH:
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)
    if typed.detail.summary is not None and len(typed.detail.summary) > MAX_PROVIDER_APPLY_STRING_LENGTH:
        _raise(ProviderApplyErrorCode.PLAN_TOO_LARGE)
    canonical_url = typed.detail.identifier.canonical_url
    if canonical_url is None:
        _raise(ProviderApplyErrorCode.CANONICAL_URL_REQUIRED)
    try:
        normalized_url = normalize_source_url(canonical_url)
    except SourceError:
        _raise(ProviderApplyErrorCode.SOURCE_URL_INVALID)
    return typed, normalized_url


def _single_source(
    values: tuple[ItemSource, ...],
) -> ItemSource | None:
    if len(values) > 1:
        _raise(ProviderApplyErrorCode.DATABASE_STATE_INVALID)
    return values[0] if values else None


def _source_snapshot(
    source: ItemSource,
    *,
    provider_key: str,
    external_id: str,
    normalized_url: str,
) -> ProviderApplySourceSnapshot:
    if (
        type(source.id) is not int
        or source.id < 1
        or type(source.item_id) is not int
        or source.item_id < 1
        or source.provider_key != provider_key
        or source.external_id != external_id
        or source.url != normalized_url
        or source.normalized_url != normalized_url
    ):
        _raise(ProviderApplyErrorCode.SOURCE_IDENTITY_CONFLICT)
    try:
        tracking = validate_source_tracking_metadata(
            provider_key=source.provider_key,
            external_id=source.external_id,
            last_checked_at=source.last_checked_at,
            metadata_hash=source.metadata_hash,
        )
    except SourceError:
        _raise(ProviderApplyErrorCode.DATABASE_STATE_INVALID)
    try:
        return ProviderApplySourceSnapshot(
            source_id=source.id,
            item_id=source.item_id,
            provider_key=provider_key,
            external_id=external_id,
            normalized_url=normalized_url,
            last_checked_at=tracking.last_checked_at,
            metadata_hash=tracking.metadata_hash,
        )
    except (TypeError, ValueError):
        _raise(ProviderApplyErrorCode.DATABASE_STATE_INVALID)


def _item_snapshot(row: object) -> ProviderApplyItemSnapshot:
    if row is None:
        _raise(ProviderApplyErrorCode.SOURCE_ITEM_MISSING)
    try:
        item_id, title, summary, release_date = tuple(row)
        return ProviderApplyItemSnapshot(
            item_id=item_id,
            title=title,
            summary=summary,
            release_date=release_date,
        )
    except ProviderApplyError:
        raise
    except (TypeError, ValueError):
        _raise(ProviderApplyErrorCode.DATABASE_STATE_INVALID)


def _change(
    field_name: str,
    policy: ProviderApplyFieldPolicy,
    current_value: str | int | None,
    proposed_value: str | int | None,
    will_write: bool,
) -> ProviderApplyFieldChange:
    try:
        return ProviderApplyFieldChange(
            field_name,
            policy,
            current_value,
            proposed_value,
            will_write,
        )
    except (TypeError, ValueError):
        _raise(ProviderApplyErrorCode.PLAN_INVALID)


def _create_changes(
    envelope: VideoDetailEnvelope,
    normalized_url: str,
    projection_hash: str,
) -> tuple[ProviderApplyFieldChange, ...]:
    detail = envelope.detail
    release_date = _release_date_text(detail.release_date)
    values = (
        ("item.title", detail.title),
        ("item.summary", detail.summary),
        ("item.release_date", release_date),
        ("item_source.url", normalized_url),
        ("item_source.normalized_url", normalized_url),
        ("item_source.title", detail.title),
        ("item_source.provider_key", envelope.request.provider_key),
        ("item_source.external_id", envelope.request.external_id),
        ("item_source.last_checked_at", _datetime_text(envelope.received_at)),
        ("item_source.metadata_hash", projection_hash),
    )
    if tuple(field for field, _value in values) != CREATE_FIELD_NAMES:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    return tuple(
        _change(
            field,
            ProviderApplyFieldPolicy.CREATE_VALUE,
            None,
            value,
            value is not None,
        )
        for field, value in values
    )


def _protected_item_change(
    field_name: str,
    current_value: str | None,
    proposed_value: str | None,
) -> ProviderApplyFieldChange:
    if current_value in {None, ""} and proposed_value not in {None, ""}:
        return _change(
            field_name,
            ProviderApplyFieldPolicy.FILL_BLANK,
            current_value,
            proposed_value,
            True,
        )
    return _change(
        field_name,
        ProviderApplyFieldPolicy.KEEP_LOCAL,
        current_value,
        proposed_value,
        False,
    )


def _update_changes(
    envelope: VideoDetailEnvelope,
    item_snapshot: ProviderApplyItemSnapshot,
    source_snapshot: ProviderApplySourceSnapshot,
    projection_hash: str,
) -> tuple[ProviderApplyFieldChange, ...]:
    detail = envelope.detail
    proposed_checked = _datetime_text(envelope.received_at)
    current_checked = _optional_datetime_text(source_snapshot.last_checked_at)
    changes = (
        _change(
            "item.title",
            ProviderApplyFieldPolicy.KEEP_LOCAL,
            item_snapshot.title,
            detail.title,
            False,
        ),
        _protected_item_change("item.summary", item_snapshot.summary, detail.summary),
        _protected_item_change(
            "item.release_date",
            item_snapshot.release_date,
            _release_date_text(detail.release_date),
        ),
        _change(
            "item_source.last_checked_at",
            ProviderApplyFieldPolicy.REFRESH_TRACKING,
            current_checked,
            proposed_checked,
            current_checked != proposed_checked,
        ),
        _change(
            "item_source.metadata_hash",
            ProviderApplyFieldPolicy.REFRESH_TRACKING,
            source_snapshot.metadata_hash,
            projection_hash,
            source_snapshot.metadata_hash != projection_hash,
        ),
    )
    if tuple(change.field_name for change in changes) != UPDATE_FIELD_NAMES:
        _raise(ProviderApplyErrorCode.PLAN_INVALID)
    return changes


def build_provider_apply_plan(
    db: Session,
    envelope: VideoDetailEnvelope,
) -> ProviderApplyPlan:
    if not isinstance(db, Session):
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)
    typed, normalized_url = _validate_envelope(envelope)
    provider_key = typed.request.provider_key
    external_id = typed.request.external_id
    projection_hash = compute_provider_apply_projection_hash(typed, normalized_url)

    original_autoflush = db.autoflush
    try:
        db.autoflush = False
        identity_sources = tuple(
            db.scalars(
                select(ItemSource).where(
                    ItemSource.provider_key == provider_key,
                    ItemSource.external_id == external_id,
                )
            ).all()
        )
        url_sources = tuple(
            db.scalars(
                select(ItemSource).where(
                    ItemSource.normalized_url == normalized_url
                )
            ).all()
        )
        identity_source = _single_source(identity_sources)
        url_source = _single_source(url_sources)

        if identity_source is None:
            if url_source is not None:
                _raise(ProviderApplyErrorCode.SOURCE_URL_CONFLICT)
            action = ProviderApplyAction.CREATE_ITEM
            item_snapshot = ProviderApplyItemSnapshot(None, None, None, None)
            source_snapshot = ProviderApplySourceSnapshot(
                None,
                None,
                provider_key,
                external_id,
                normalized_url,
                None,
                None,
            )
            field_changes = _create_changes(
                typed,
                normalized_url,
                projection_hash,
            )
            linked_item_id = None
        else:
            if url_source is None or url_source.id != identity_source.id:
                if url_source is not None:
                    _raise(ProviderApplyErrorCode.SOURCE_URL_CONFLICT)
                _raise(ProviderApplyErrorCode.SOURCE_IDENTITY_CONFLICT)
            source_snapshot = _source_snapshot(
                identity_source,
                provider_key=provider_key,
                external_id=external_id,
                normalized_url=normalized_url,
            )
            item_row = db.execute(
                select(Item.id, Item.title, Item.summary, Item.release_date).where(
                    Item.id == source_snapshot.item_id
                )
            ).one_or_none()
            item_snapshot = _item_snapshot(item_row)
            action = ProviderApplyAction.UPDATE_ITEM
            linked_item_id = item_snapshot.item_id
            field_changes = _update_changes(
                typed,
                item_snapshot,
                source_snapshot,
                projection_hash,
            )

        duplicate_query = select(Item.id).where(Item.title == typed.detail.title)
        if linked_item_id is not None:
            duplicate_query = duplicate_query.where(Item.id != linked_item_id)
        duplicate_ids = tuple(
            db.scalars(
                duplicate_query.order_by(Item.id.asc()).limit(
                    MAX_PROVIDER_APPLY_DUPLICATE_HINTS
                )
            ).all()
        )
    except ProviderApplyError:
        raise
    except Exception:
        _raise(ProviderApplyErrorCode.UNKNOWN)
    finally:
        db.autoflush = original_autoflush

    try:
        return ProviderApplyPlan(
            format=PROVIDER_APPLY_PLAN_FORMAT,
            version=PROVIDER_APPLY_PLAN_VERSION,
            action=action,
            provider_key=provider_key,
            external_id=external_id,
            normalized_source_url=normalized_url,
            item_snapshot=item_snapshot,
            source_snapshot=source_snapshot,
            field_changes=field_changes,
            duplicate_title_item_ids=duplicate_ids,
            received_at=typed.received_at,
            source_updated_at=typed.detail.source_updated_at,
            apply_projection_hash=projection_hash,
        )
    except (TypeError, ValueError):
        _raise(ProviderApplyErrorCode.DATABASE_STATE_INVALID)


def _validate_secret(secret: object) -> bytes:
    if (
        type(secret) is not bytes
        or not MIN_PROVIDER_APPLY_SECRET_BYTES <= len(secret) <= MAX_PROVIDER_APPLY_SECRET_BYTES
    ):
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)
    return secret


def _validate_context(context: object) -> bytes:
    if type(context) is not str or not context or len(context) > MAX_PROVIDER_APPLY_CONTEXT_LENGTH:
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)
    if any(ord(character) < 32 or ord(character) == 127 for character in context):
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)
    try:
        return context.encode("utf-8", "strict")
    except UnicodeEncodeError:
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)


def _validate_ttl(ttl_seconds: object) -> int:
    if (
        type(ttl_seconds) is not int
        or not 1 <= ttl_seconds <= MAX_PROVIDER_APPLY_TOKEN_TTL_SECONDS
    ):
        _raise(ProviderApplyErrorCode.INVALID_REQUEST)
    return ttl_seconds


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: object) -> bytes:
    if type(value) is not str or not value or _BASE64URL.fullmatch(value) is None:
        raise _DecodeError
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError):
        raise _DecodeError from None
    if _base64url_encode(decoded) != value:
        raise _DecodeError
    return decoded


def _context_binding(secret: bytes, context: bytes) -> bytes:
    return hmac.new(secret, _DOMAIN_CONTEXT + context, hashlib.sha256).digest()


def _token_mac(secret: bytes, context_binding: bytes, payload_segment: str) -> bytes:
    return hmac.new(
        secret,
        _DOMAIN_TOKEN + context_binding + b"\0" + payload_segment.encode("ascii"),
        hashlib.sha256,
    ).digest()


def sign_provider_apply_plan(
    plan: ProviderApplyPlan,
    *,
    secret: bytes,
    context: str,
    now: datetime,
    ttl_seconds: int = DEFAULT_PROVIDER_APPLY_TOKEN_TTL_SECONDS,
) -> str:
    secret_bytes = _validate_secret(secret)
    context_bytes = _validate_context(context)
    issued_at = _utc(now, code=ProviderApplyErrorCode.INVALID_REQUEST)
    ttl = _validate_ttl(ttl_seconds)
    serialize_provider_apply_plan(plan)
    envelope = {
        "format": PROVIDER_APPLY_TOKEN_FORMAT,
        "version": PROVIDER_APPLY_TOKEN_VERSION,
        "issued_at": _datetime_text(issued_at),
        "expires_at": _datetime_text(issued_at + timedelta(seconds=ttl)),
        "plan": _plan_raw(plan),
    }
    try:
        payload = _canonical_json_bytes(envelope)
    except _DecodeError:
        _raise(ProviderApplyErrorCode.TOKEN_INVALID)
    if len(payload) > MAX_PROVIDER_APPLY_TOKEN_PAYLOAD_BYTES:
        _raise(ProviderApplyErrorCode.TOKEN_TOO_LARGE)
    payload_segment = _base64url_encode(payload)
    binding = _context_binding(secret_bytes, context_bytes)
    signature_segment = _base64url_encode(
        binding + _token_mac(secret_bytes, binding, payload_segment)
    )
    token = f"{_TOKEN_PREFIX}.{payload_segment}.{signature_segment}"
    if len(token) > MAX_PROVIDER_APPLY_TOKEN_LENGTH:
        _raise(ProviderApplyErrorCode.TOKEN_TOO_LARGE)
    return token


def verify_provider_apply_token(
    token: str,
    *,
    secret: bytes,
    context: str,
    now: datetime,
) -> ProviderApplyPlan:
    secret_bytes = _validate_secret(secret)
    context_bytes = _validate_context(context)
    checked_at = _utc(now, code=ProviderApplyErrorCode.INVALID_REQUEST)
    if type(token) is not str or not token:
        _raise(ProviderApplyErrorCode.TOKEN_INVALID)
    if len(token) > MAX_PROVIDER_APPLY_TOKEN_LENGTH:
        _raise(ProviderApplyErrorCode.TOKEN_TOO_LARGE)
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != _TOKEN_PREFIX:
        _raise(ProviderApplyErrorCode.TOKEN_INVALID)
    payload_segment, signature_segment = parts[1], parts[2]
    try:
        payload = _base64url_decode(payload_segment)
        signature = _base64url_decode(signature_segment)
    except _DecodeError:
        _raise(ProviderApplyErrorCode.TOKEN_INVALID)
    if len(signature) != 64:
        _raise(ProviderApplyErrorCode.TOKEN_INVALID)

    document = _decode_json_bytes(
        payload,
        maximum_bytes=MAX_PROVIDER_APPLY_TOKEN_PAYLOAD_BYTES,
        too_large=ProviderApplyErrorCode.TOKEN_TOO_LARGE,
        invalid=ProviderApplyErrorCode.TOKEN_INVALID,
    )
    try:
        token_raw = _expect_keys(document, _TOKEN_KEYS)
        _validate_plan_document_shape(token_raw["plan"])
        if token_raw["format"] != PROVIDER_APPLY_TOKEN_FORMAT:
            raise _DecodeError
        if (
            type(token_raw["version"]) is not int
            or token_raw["version"] != PROVIDER_APPLY_TOKEN_VERSION
        ):
            raise _DecodeError
        issued_at = _parse_datetime(token_raw["issued_at"])
        expires_at = _parse_datetime(token_raw["expires_at"])
        lifetime = (expires_at - issued_at).total_seconds()
        if not 0 < lifetime <= MAX_PROVIDER_APPLY_TOKEN_TTL_SECONDS:
            raise _DecodeError
    except (KeyError, TypeError, ValueError, _DecodeError):
        _raise(ProviderApplyErrorCode.TOKEN_INVALID)

    if issued_at > checked_at:
        _raise(ProviderApplyErrorCode.TOKEN_NOT_YET_VALID)
    if checked_at >= expires_at:
        _raise(ProviderApplyErrorCode.TOKEN_EXPIRED)

    embedded_binding = signature[:32]
    supplied_mac = signature[32:]
    expected_mac = _token_mac(secret_bytes, embedded_binding, payload_segment)
    if not hmac.compare_digest(supplied_mac, expected_mac):
        _raise(ProviderApplyErrorCode.TOKEN_SIGNATURE_INVALID)
    expected_binding = _context_binding(secret_bytes, context_bytes)
    if not hmac.compare_digest(embedded_binding, expected_binding):
        _raise(ProviderApplyErrorCode.TOKEN_CONTEXT_MISMATCH)

    try:
        plan_payload = _canonical_json_bytes(token_raw["plan"])
        return parse_provider_apply_plan(plan_payload)
    except _DecodeError:
        _raise(ProviderApplyErrorCode.TOKEN_INVALID)
    except ProviderApplyError as error:
        if error.code is ProviderApplyErrorCode.PLAN_TOO_LARGE:
            _raise(ProviderApplyErrorCode.TOKEN_TOO_LARGE)
        _raise(ProviderApplyErrorCode.TOKEN_INVALID)


__all__ = [
    "build_provider_apply_plan",
    "compute_provider_apply_projection_hash",
    "parse_provider_apply_plan",
    "serialize_provider_apply_plan",
    "sign_provider_apply_plan",
    "verify_provider_apply_token",
]
