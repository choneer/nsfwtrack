from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import importlib
import json
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2
import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

import app.provider_apply.service as provider_apply_service
from app.database import SessionLocal, engine
from app.models import Item, ItemSource
from app.provider_apply import (
    CREATE_FIELD_NAMES,
    DEFAULT_PROVIDER_APPLY_TOKEN_TTL_SECONDS,
    MAX_PROVIDER_APPLY_DUPLICATE_HINTS,
    MAX_PROVIDER_APPLY_PLAN_BYTES,
    MAX_PROVIDER_APPLY_PLAN_DEPTH,
    MAX_PROVIDER_APPLY_STRING_LENGTH,
    MAX_PROVIDER_APPLY_TOKEN_LENGTH,
    MAX_PROVIDER_APPLY_TOKEN_TTL_SECONDS,
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
    build_provider_apply_plan,
    compute_provider_apply_projection_hash,
    parse_provider_apply_plan,
    serialize_provider_apply_plan,
    sign_provider_apply_plan,
    verify_provider_apply_token,
)
from app.services.outbound_http import OutboundHttpClient
from app.services.sources import normalize_source_url
from app.source_adapters import PRODUCTION_ENDPOINT_REGISTRY, ProviderOperation
from app.source_search import (
    PRODUCTION_SEARCH_PACKAGES,
    ProviderSearchService,
    SearchProviderDescriptor,
    VideoDetailEnvelope,
    VideoDetailRequest,
    build_production_search_service,
)
from app.video_metadata.contracts import VideoDetail, VideoIdentifier


NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
PROVIDER_KEY = "fixture_video"
EXTERNAL_ID = "video-001"
CANONICAL_URL = "https://provider.invalid/video/001"
SECRET = b"signed-provider-apply-secret-key!"
CONTEXT = "provider-apply:n5c-b"
OLD_HASH = "v1:sha256:" + ("a" * 64)


def _envelope(
    *,
    provider_key: str = PROVIDER_KEY,
    external_id: str = EXTERNAL_ID,
    canonical_url: str | None = CANONICAL_URL,
    title: str = "Provider Title",
    summary: str | None = "Provider summary",
    release_date_value: date | None = date(2026, 7, 1),
    received_at: datetime = NOW,
    source_updated_at: datetime | None = datetime(2026, 7, 19, tzinfo=UTC),
) -> VideoDetailEnvelope:
    descriptor = SearchProviderDescriptor(
        provider_key,
        "Synthetic Video",
        "Synthetic records",
        (ProviderOperation.DETAIL,),
    )
    request = VideoDetailRequest(provider_key, external_id)
    detail = VideoDetail(
        identifier=VideoIdentifier(
            provider_key,
            external_id,
            canonical_url=canonical_url,
        ),
        title=title,
        summary=summary,
        release_date=release_date_value,
        source_updated_at=source_updated_at,
    )
    return VideoDetailEnvelope(descriptor, request, detail, received_at)


def _seed_item(
    *,
    title: str = "Local Title",
    summary: str | None = None,
    release_date_value: str | None = None,
) -> int:
    with SessionLocal() as db:
        item = Item(
            title=title,
            summary=summary,
            release_date=release_date_value,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item.id


def _seed_source(
    *,
    item_id: int,
    url: str = CANONICAL_URL,
    provider_key: str = PROVIDER_KEY,
    external_id: str = EXTERNAL_ID,
    last_checked_at: datetime | None = NOW - timedelta(days=1),
    metadata_hash: str | None = OLD_HASH,
) -> int:
    normalized = normalize_source_url(url)
    with SessionLocal() as db:
        source = ItemSource(
            item_id=item_id,
            url=normalized,
            normalized_url=normalized,
            title="Source title",
            provider_key=provider_key,
            external_id=external_id,
            last_checked_at=last_checked_at,
            metadata_hash=metadata_hash,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return source.id


def _build(envelope: VideoDetailEnvelope | None = None) -> ProviderApplyPlan:
    with SessionLocal() as db:
        return build_provider_apply_plan(db, envelope or _envelope())


def _error_code(call: Any) -> ProviderApplyErrorCode:
    with pytest.raises(ProviderApplyError) as exc_info:
        call()
    return exc_info.value.code


def _raw_plan(plan: ProviderApplyPlan) -> dict[str, object]:
    return json.loads(serialize_provider_apply_plan(plan))


def _json_bytes(value: object, *, pretty: bool = False) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=not pretty,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _database_snapshot() -> tuple[tuple[object, ...], tuple[object, ...]]:
    with SessionLocal() as db:
        items = tuple(
            db.execute(
                select(Item.id, Item.title, Item.summary, Item.release_date).order_by(
                    Item.id
                )
            ).all()
        )
        sources = tuple(
            db.execute(
                select(
                    ItemSource.id,
                    ItemSource.item_id,
                    ItemSource.url,
                    ItemSource.normalized_url,
                    ItemSource.title,
                    ItemSource.provider_key,
                    ItemSource.external_id,
                    ItemSource.last_checked_at,
                    ItemSource.metadata_hash,
                ).order_by(ItemSource.id)
            ).all()
        )
    return items, sources


def _forbidden(*args: object, **kwargs: object) -> None:
    raise AssertionError("forbidden side effect")


class _ScalarValues:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values = values

    def all(self) -> tuple[object, ...]:
        return self._values


def _no_change_update_plan() -> ProviderApplyPlan:
    envelope = _envelope()
    projection_hash = compute_provider_apply_projection_hash(
        envelope,
        normalize_source_url(CANONICAL_URL),
    )
    item_id = _seed_item(
        title="Local title",
        summary="Local summary",
        release_date_value="2025-01-02",
    )
    _seed_source(
        item_id=item_id,
        last_checked_at=envelope.received_at,
        metadata_hash=projection_hash,
    )
    return _build(envelope)


def _forge_executable_token(plan: ProviderApplyPlan) -> str:
    envelope = {
        "format": PROVIDER_APPLY_TOKEN_FORMAT,
        "version": PROVIDER_APPLY_TOKEN_VERSION,
        "issued_at": provider_apply_service._datetime_text(NOW),
        "expires_at": provider_apply_service._datetime_text(
            NOW + timedelta(seconds=600)
        ),
        "plan": provider_apply_service._plan_raw(plan),
    }
    payload = provider_apply_service._canonical_json_bytes(envelope)
    payload_segment = provider_apply_service._base64url_encode(payload)
    binding = provider_apply_service._context_binding(SECRET, CONTEXT.encode())
    signature_segment = provider_apply_service._base64url_encode(
        binding
        + provider_apply_service._token_mac(
            SECRET,
            binding,
            payload_segment,
        )
    )
    return f"nspap1.{payload_segment}.{signature_segment}"


def test_public_constants_and_enums_are_fixed_and_deny_unsafe_policies() -> None:
    assert PROVIDER_APPLY_PLAN_FORMAT == "nsfwtrack.provider-apply-plan"
    assert PROVIDER_APPLY_PLAN_VERSION == 1
    assert PROVIDER_APPLY_TOKEN_FORMAT == "nsfwtrack.provider-apply-token"
    assert PROVIDER_APPLY_TOKEN_VERSION == 1
    assert DEFAULT_PROVIDER_APPLY_TOKEN_TTL_SECONDS == 600
    assert MAX_PROVIDER_APPLY_TOKEN_TTL_SECONDS == 900
    assert {value.value for value in ProviderApplyAction} == {
        "create_item",
        "update_item",
    }
    policies = {value.value for value in ProviderApplyFieldPolicy}
    assert policies == {"create_value", "fill_blank", "keep_local", "refresh_tracking"}
    assert not policies & {"overwrite_local", "force", "merge_by_title", "silent_update"}
    assert ProviderApplyErrorCode.NOTHING_TO_APPLY.value == "nothing_to_apply"


def test_dtos_are_frozen_slotted_tuple_only_and_repr_is_redacted() -> None:
    plan = _build()
    values = (
        plan,
        plan.item_snapshot,
        plan.source_snapshot,
        *plan.field_changes,
    )
    for value in values:
        assert not hasattr(value, "__dict__")
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            value.extra = "forbidden"  # type: ignore[attr-defined]
        rendered = f"{value!s} {value!r}"
        assert EXTERNAL_ID not in rendered
        assert CANONICAL_URL not in rendered
        assert "Provider Title" not in rendered
    with pytest.raises(TypeError):
        replace(plan, field_changes=list(plan.field_changes))  # type: ignore[arg-type]


def test_error_str_and_repr_contain_only_stable_code() -> None:
    error = ProviderApplyError(ProviderApplyErrorCode.TOKEN_SIGNATURE_INVALID)
    assert str(error) == "token_signature_invalid"
    assert repr(error) == "ProviderApplyError(code='token_signature_invalid')"
    assert ProviderApplyError.__slots__ == ("code",)
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        error.extra = "forbidden"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ProviderApplyFieldChange(
            "item.title", ProviderApplyFieldPolicy.KEEP_LOCAL, "x", "y", True
        ),
        lambda: ProviderApplyFieldChange(
            "item.title", ProviderApplyFieldPolicy.CREATE_VALUE, "x", "y", True
        ),
        lambda: ProviderApplyFieldChange(
            "item.summary", ProviderApplyFieldPolicy.FILL_BLANK, "local", "new", True
        ),
        lambda: ProviderApplyFieldChange(
            "item.summary", ProviderApplyFieldPolicy.FILL_BLANK, None, None, False
        ),
        lambda: ProviderApplyFieldChange(
            "item.title", ProviderApplyFieldPolicy.CREATE_VALUE, None, "x", 1  # type: ignore[arg-type]
        ),
        lambda: ProviderApplyFieldChange(
            "unknown", ProviderApplyFieldPolicy.CREATE_VALUE, None, "x", True
        ),
    ],
)
def test_field_change_rejects_invalid_policy_type_and_state(factory: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_snapshots_require_exact_ids_utc_and_canonical_values() -> None:
    with pytest.raises(ValueError):
        ProviderApplyItemSnapshot(True, "Title", None, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ProviderApplyItemSnapshot(None, "Unexpected", None, None)
    with pytest.raises(ValueError):
        ProviderApplySourceSnapshot(
            1,
            1,
            PROVIDER_KEY,
            EXTERNAL_ID,
            CANONICAL_URL,
            datetime(2026, 7, 20),
            OLD_HASH,
        )
    with pytest.raises(ValueError):
        ProviderApplySourceSnapshot(
            None,
            None,
            PROVIDER_KEY,
            EXTERNAL_ID,
            "HTTPS://PROVIDER.INVALID:443/video/001",
            None,
            None,
        )


def test_plan_rejects_unsorted_duplicate_or_excess_title_hints() -> None:
    plan = _build()
    with pytest.raises(ValueError):
        replace(plan, duplicate_title_item_ids=(2, 1))
    with pytest.raises(ValueError):
        replace(plan, duplicate_title_item_ids=(1, 1))
    with pytest.raises(ValueError):
        replace(
            plan,
            duplicate_title_item_ids=tuple(
                range(1, MAX_PROVIDER_APPLY_DUPLICATE_HINTS + 2)
            ),
        )


def test_create_plan_normalizes_url_and_maps_only_allowed_create_fields() -> None:
    raw_url = "HTTPS://PROVIDER.INVALID:443/video/%7e001?name=%7evalue"
    plan = _build(_envelope(canonical_url=raw_url, summary="Unicode 摘要"))

    assert plan.action is ProviderApplyAction.CREATE_ITEM
    assert plan.has_writes
    assert plan.normalized_source_url == (
        "https://provider.invalid/video/~001?name=~value"
    )
    assert plan.item_snapshot == ProviderApplyItemSnapshot(None, None, None, None)
    assert plan.source_snapshot.source_id is None
    assert plan.source_snapshot.item_id is None
    assert tuple(change.field_name for change in plan.field_changes) == CREATE_FIELD_NAMES
    assert all(
        change.policy is ProviderApplyFieldPolicy.CREATE_VALUE
        for change in plan.field_changes
    )
    changes = {change.field_name: change for change in plan.field_changes}
    assert changes["item.title"].proposed_value == "Provider Title"
    assert changes["item.summary"].proposed_value == "Unicode 摘要"
    assert changes["item.release_date"].proposed_value == "2026-07-01"
    assert changes["item_source.url"].proposed_value == plan.normalized_source_url
    assert changes["item_source.normalized_url"].proposed_value == plan.normalized_source_url
    assert changes["item_source.last_checked_at"].proposed_value == "2026-07-20T12:00:00.000000Z"
    assert changes["item_source.metadata_hash"].proposed_value == plan.apply_projection_hash
    payload = serialize_provider_apply_plan(plan)
    assert raw_url.encode() not in payload


def test_same_title_never_auto_links_and_is_only_a_bounded_sorted_hint() -> None:
    ids = [_seed_item(title="Provider Title") for _ in range(35)]

    plan = _build()

    assert plan.action is ProviderApplyAction.CREATE_ITEM
    assert plan.item_snapshot.item_id is None
    assert plan.duplicate_title_item_ids == tuple(ids[:32])


def test_update_plan_requires_exact_source_and_preserves_local_title() -> None:
    item_id = _seed_item(
        title="Local title must win",
        summary=None,
        release_date_value="2025-01-02",
    )
    source_id = _seed_source(item_id=item_id)

    plan = _build()

    assert plan.action is ProviderApplyAction.UPDATE_ITEM
    assert plan.item_snapshot.item_id == item_id
    assert plan.item_snapshot.title == "Local title must win"
    assert plan.source_snapshot.source_id == source_id
    assert plan.source_snapshot.item_id == item_id
    assert tuple(change.field_name for change in plan.field_changes) == UPDATE_FIELD_NAMES
    changes = {change.field_name: change for change in plan.field_changes}
    assert changes["item.title"].policy is ProviderApplyFieldPolicy.KEEP_LOCAL
    assert not changes["item.title"].will_write
    assert changes["item.title"].proposed_value == "Provider Title"
    assert changes["item.summary"].policy is ProviderApplyFieldPolicy.FILL_BLANK
    assert changes["item.summary"].will_write
    assert changes["item.release_date"].policy is ProviderApplyFieldPolicy.KEEP_LOCAL
    assert not changes["item.release_date"].will_write
    assert changes["item_source.last_checked_at"].policy is ProviderApplyFieldPolicy.REFRESH_TRACKING
    assert changes["item_source.metadata_hash"].proposed_value == plan.apply_projection_hash
    assert plan.has_writes


def test_no_change_update_plan_round_trips_but_cannot_be_signed_or_verified(
    caplog: pytest.LogCaptureFixture,
) -> None:
    plan = _no_change_update_plan()

    assert plan.action is ProviderApplyAction.UPDATE_ITEM
    assert not plan.has_writes
    assert not any(change.will_write for change in plan.field_changes)
    parsed = parse_provider_apply_plan(serialize_provider_apply_plan(plan))
    assert parsed == plan
    assert not parsed.has_writes
    assert _error_code(
        lambda: sign_provider_apply_plan(
            plan,
            secret=SECRET,
            context=CONTEXT,
            now=NOW,
        )
    ) is ProviderApplyErrorCode.NOTHING_TO_APPLY
    forged = _forge_executable_token(plan)
    assert _error_code(
        lambda: verify_provider_apply_token(
            forged,
            secret=SECRET,
            context=CONTEXT,
            now=NOW,
        )
    ) is ProviderApplyErrorCode.NOTHING_TO_APPLY
    rendered = f"{ProviderApplyError(ProviderApplyErrorCode.NOTHING_TO_APPLY)!r}"
    for marker in (
        "Local title",
        CANONICAL_URL,
        EXTERNAL_ID,
        forged,
        SECRET.decode(),
        "sensitive-nothing-marker",
    ):
        assert marker not in rendered
        assert marker not in caplog.text


def test_fill_blank_update_plan_still_signs_and_verifies() -> None:
    item_id = _seed_item(title="Local title", summary=None, release_date_value=None)
    _seed_source(item_id=item_id, last_checked_at=NOW, metadata_hash=OLD_HASH)
    plan = _build()

    assert plan.has_writes
    assert any(
        change.policy is ProviderApplyFieldPolicy.FILL_BLANK
        and change.will_write
        for change in plan.field_changes
    )
    token = sign_provider_apply_plan(
        plan,
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    )
    assert verify_provider_apply_token(
        token,
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    ) == plan


def test_tracking_only_update_plan_still_signs_and_verifies() -> None:
    item_id = _seed_item(
        title="Local title",
        summary="Local summary",
        release_date_value="2025-01-02",
    )
    _seed_source(
        item_id=item_id,
        last_checked_at=NOW - timedelta(seconds=1),
        metadata_hash=OLD_HASH,
    )
    plan = _build()

    assert plan.has_writes
    writes = tuple(change.field_name for change in plan.field_changes if change.will_write)
    assert writes == (
        "item_source.last_checked_at",
        "item_source.metadata_hash",
    )
    token = sign_provider_apply_plan(
        plan,
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    )
    assert verify_provider_apply_token(
        token,
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    ) == plan


@pytest.mark.parametrize("local_summary", ["Local summary", " "])
def test_update_never_overwrites_nonempty_local_summary(local_summary: str) -> None:
    item_id = _seed_item(title="Local", summary=local_summary)
    _seed_source(item_id=item_id)

    plan = _build()
    change = next(
        value for value in plan.field_changes if value.field_name == "item.summary"
    )

    assert change.policy is ProviderApplyFieldPolicy.KEEP_LOCAL
    assert change.current_value == local_summary
    assert not change.will_write


def test_update_blank_release_date_fills_and_provider_blank_keeps_local() -> None:
    item_id = _seed_item(title="Local", summary=None, release_date_value=None)
    _seed_source(item_id=item_id)
    filled = _build()
    fill_change = next(
        value
        for value in filled.field_changes
        if value.field_name == "item.release_date"
    )
    assert fill_change.policy is ProviderApplyFieldPolicy.FILL_BLANK
    assert fill_change.will_write

    no_provider_value = _build(
        _envelope(summary=None, release_date_value=None)
    )
    for field in ("item.summary", "item.release_date"):
        change = next(
            value for value in no_provider_value.field_changes if value.field_name == field
        )
        assert change.policy is ProviderApplyFieldPolicy.KEEP_LOCAL
        assert not change.will_write


def test_url_without_identity_is_a_stable_conflict() -> None:
    item_id = _seed_item()
    _seed_source(
        item_id=item_id,
        provider_key="fixture_other",
        external_id="other-001",
    )

    assert _error_code(_build) is ProviderApplyErrorCode.SOURCE_URL_CONFLICT


def test_existing_identity_url_change_is_rejected() -> None:
    item_id = _seed_item()
    _seed_source(item_id=item_id, url="https://provider.invalid/video/old")

    assert _error_code(_build) is ProviderApplyErrorCode.SOURCE_IDENTITY_CONFLICT


def test_identity_and_url_pointing_to_different_sources_is_rejected() -> None:
    first = _seed_item(title="First")
    second = _seed_item(title="Second")
    _seed_source(item_id=first, url="https://provider.invalid/video/old")
    _seed_source(
        item_id=second,
        provider_key="fixture_other",
        external_id="other-001",
    )

    assert _error_code(_build) is ProviderApplyErrorCode.SOURCE_URL_CONFLICT


def test_source_pointing_to_missing_item_is_rejected() -> None:
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.execute(
            ItemSource.__table__.insert().values(
                item_id=999,
                url=CANONICAL_URL,
                normalized_url=CANONICAL_URL,
                provider_key=PROVIDER_KEY,
                external_id=EXTERNAL_ID,
                last_checked_at=NOW,
                metadata_hash=OLD_HASH,
            )
        )
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")

    assert _error_code(_build) is ProviderApplyErrorCode.SOURCE_ITEM_MISSING


def test_canonical_url_is_required_and_invalid_normalization_is_rejected() -> None:
    assert _error_code(lambda: _build(_envelope(canonical_url=None))) is (
        ProviderApplyErrorCode.CANONICAL_URL_REQUIRED
    )
    assert _error_code(
        lambda: _build(_envelope(canonical_url="https://provider.invalid/%ZZ"))
    ) is ProviderApplyErrorCode.SOURCE_URL_INVALID


def test_envelope_identity_is_explicitly_revalidated() -> None:
    envelope = _envelope()
    object.__setattr__(
        envelope,
        "request",
        VideoDetailRequest(PROVIDER_KEY, "tampered-id"),
    )

    assert _error_code(lambda: _build(envelope)) is ProviderApplyErrorCode.DETAIL_MISMATCH


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (lambda envelope, marker: object.__setattr__(envelope, "provider", marker), ProviderApplyErrorCode.INVALID_REQUEST),
        (lambda envelope, marker: object.__setattr__(envelope, "request", marker), ProviderApplyErrorCode.INVALID_REQUEST),
        (lambda envelope, marker: object.__setattr__(envelope, "detail", marker), ProviderApplyErrorCode.INVALID_REQUEST),
        (lambda envelope, marker: object.__setattr__(envelope.provider, "operations", [ProviderOperation.DETAIL]), ProviderApplyErrorCode.INVALID_REQUEST),
        (lambda envelope, marker: object.__setattr__(envelope.provider, "operations", (ProviderOperation.SEARCH,)), ProviderApplyErrorCode.DETAIL_MISMATCH),
        (lambda envelope, marker: object.__setattr__(envelope.provider, "provider_key", "fixture_other"), ProviderApplyErrorCode.DETAIL_MISMATCH),
        (lambda envelope, marker: object.__setattr__(envelope.request, "external_id", "video-other"), ProviderApplyErrorCode.DETAIL_MISMATCH),
    ],
)
def test_nested_envelope_type_authority_and_identity_fail_before_url_or_database(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mutation: Any,
    expected: ProviderApplyErrorCode,
) -> None:
    marker_text = "tampered-envelope-marker"

    class Marker:
        def __repr__(self) -> str:
            return marker_text

    envelope = _envelope()
    mutation(envelope, Marker())
    with SessionLocal() as db:
        monkeypatch.setattr(db, "scalars", _forbidden)
        monkeypatch.setattr(db, "execute", _forbidden)
        monkeypatch.setattr(provider_apply_service, "normalize_source_url", _forbidden)
        monkeypatch.setattr(OutboundHttpClient, "__init__", _forbidden)
        monkeypatch.setattr(ProviderSearchService, "search", _forbidden)
        monkeypatch.setattr(ProviderSearchService, "detail", _forbidden)
        monkeypatch.setattr(ProviderSearchService, "asset_list", _forbidden)

        code = _error_code(lambda: build_provider_apply_plan(db, envelope))

    assert code is expected
    assert marker_text not in caplog.text
    assert marker_text not in repr(ProviderApplyError(code))


def test_missing_nested_field_is_stable_before_url_or_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = _envelope()
    object.__delattr__(envelope.provider, "operations")
    with SessionLocal() as db:
        monkeypatch.setattr(db, "scalars", _forbidden)
        monkeypatch.setattr(provider_apply_service, "normalize_source_url", _forbidden)
        assert _error_code(
            lambda: build_provider_apply_plan(db, envelope)
        ) is ProviderApplyErrorCode.INVALID_REQUEST


def test_item_title_and_plan_string_bounds_are_enforced() -> None:
    assert _error_code(lambda: _build(_envelope(title="x" * 256))) is (
        ProviderApplyErrorCode.INVALID_REQUEST
    )
    assert _error_code(
        lambda: _build(_envelope(summary="x" * (MAX_PROVIDER_APPLY_STRING_LENGTH + 1)))
    ) is ProviderApplyErrorCode.PLAN_TOO_LARGE


def test_projection_hash_is_deterministic_and_change_sensitive() -> None:
    envelope = _envelope()
    normalized = normalize_source_url(CANONICAL_URL)
    first = compute_provider_apply_projection_hash(envelope, normalized)
    second = compute_provider_apply_projection_hash(envelope, normalized)
    changed_summary = compute_provider_apply_projection_hash(
        _envelope(summary="Changed"),
        normalized,
    )
    changed_time = compute_provider_apply_projection_hash(
        _envelope(received_at=NOW + timedelta(seconds=1)),
        normalized,
    )

    assert first == second
    assert first.startswith("v1:sha256:") and len(first) == 74
    assert len({first, changed_summary, changed_time}) == 3
    assert first == _build(envelope).apply_projection_hash


@pytest.mark.parametrize("create", [True, False])
def test_builder_executes_select_only_and_never_calls_session_mutators(
    monkeypatch: pytest.MonkeyPatch,
    create: bool,
) -> None:
    if not create:
        item_id = _seed_item()
        _seed_source(item_id=item_id)
    before = _database_snapshot()
    statements: list[str] = []

    def capture(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with SessionLocal() as db:
            with monkeypatch.context() as guarded:
                for name in ("add", "add_all", "delete", "flush", "commit", "rollback"):
                    guarded.setattr(db, name, _forbidden)
                plan = build_provider_apply_plan(db, _envelope())
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert plan.action is (
        ProviderApplyAction.CREATE_ITEM if create else ProviderApplyAction.UPDATE_ITEM
    )
    assert statements
    assert len(statements) == (3 if create else 4)
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert _database_snapshot() == before


def test_identity_and_url_selects_use_stable_order_and_sql_limit_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered: list[str] = []
    with SessionLocal() as db:
        original_scalars = db.scalars

        def recording(statement: object, *args: object, **kwargs: object) -> object:
            rendered.append(
                str(
                    statement.compile(
                        dialect=engine.dialect,
                        compile_kwargs={"literal_binds": True},
                    )
                )
            )
            return original_scalars(statement, *args, **kwargs)

        monkeypatch.setattr(db, "scalars", recording)
        plan = build_provider_apply_plan(db, _envelope())

    assert plan.action is ProviderApplyAction.CREATE_ITEM
    assert len(rendered) == 3
    for statement in rendered[:2]:
        normalized = " ".join(statement.upper().split())
        assert "ORDER BY ITEM_SOURCES.ID ASC" in normalized
        assert "LIMIT 2" in normalized
    duplicate = " ".join(rendered[2].upper().split())
    assert "ORDER BY ITEMS.ID ASC" in duplicate
    assert f"LIMIT {MAX_PROVIDER_APPLY_DUPLICATE_HINTS}" in duplicate


@pytest.mark.parametrize("conflict_query", ["identity", "url"])
def test_bounded_source_query_two_rows_is_database_state_invalid_without_writes(
    monkeypatch: pytest.MonkeyPatch,
    conflict_query: str,
) -> None:
    before = _database_snapshot()
    first = ItemSource(
        id=1,
        item_id=1,
        url=CANONICAL_URL,
        normalized_url=CANONICAL_URL,
        provider_key=PROVIDER_KEY,
        external_id=EXTERNAL_ID,
    )
    second = ItemSource(
        id=2,
        item_id=2,
        url=CANONICAL_URL,
        normalized_url=CANONICAL_URL,
        provider_key=PROVIDER_KEY,
        external_id=EXTERNAL_ID,
    )
    values = (
        (_ScalarValues((first, second)), _ScalarValues(()))
        if conflict_query == "identity"
        else (_ScalarValues(()), _ScalarValues((first, second)))
    )
    with SessionLocal() as db:
        calls = iter(values)

        def substitute(statement: object, *args: object, **kwargs: object) -> object:
            del statement, args, kwargs
            return next(calls)

        with monkeypatch.context() as guarded:
            guarded.setattr(db, "scalars", substitute)
            for name in ("add", "add_all", "delete", "flush", "commit", "rollback"):
                guarded.setattr(db, name, _forbidden)
            assert _error_code(
                lambda: build_provider_apply_plan(db, _envelope())
            ) is ProviderApplyErrorCode.DATABASE_STATE_INVALID

    assert _database_snapshot() == before


def test_builder_disables_autoflush_for_pending_local_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SessionLocal() as db:
        pending = Item(title="Pending item")
        db.add(pending)
        with monkeypatch.context() as guarded:
            guarded.setattr(db, "flush", _forbidden)
            plan = build_provider_apply_plan(db, _envelope())
        assert pending.id is None
        assert plan.duplicate_title_item_ids == ()


def test_canonical_serialization_round_trip_unicode_and_convergence() -> None:
    plan = _build(_envelope(summary="Unicode 摘要 café"))
    canonical = serialize_provider_apply_plan(plan)
    parsed = parse_provider_apply_plan(canonical)
    pretty = _json_bytes(_raw_plan(plan), pretty=True)

    assert parsed == plan
    assert "摘要".encode() in canonical
    assert serialize_provider_apply_plan(parse_provider_apply_plan(pretty)) == canonical
    assert serialize_provider_apply_plan(parsed) == canonical


@pytest.mark.parametrize("payload", ["not-bytes", bytearray(b"{}"), memoryview(b"{}")])
def test_plan_parser_requires_exact_bytes(payload: object) -> None:
    assert _error_code(lambda: parse_provider_apply_plan(payload)) is (  # type: ignore[arg-type]
        ProviderApplyErrorCode.PLAN_INVALID
    )


def test_plan_parser_rejects_nested_duplicate_unknown_missing_and_invalid_utf8() -> None:
    plan = _build()
    canonical = serialize_provider_apply_plan(plan)
    duplicate = canonical.replace(
        b'"item_id":null',
        b'"item_id":null,"item_id":null',
        1,
    )
    unknown = _raw_plan(plan)
    unknown["unknown"] = "marker"
    missing = _raw_plan(plan)
    del missing["action"]

    for payload in (duplicate, _json_bytes(unknown), _json_bytes(missing), b"\xff"):
        assert _error_code(lambda payload=payload: parse_provider_apply_plan(payload)) is (
            ProviderApplyErrorCode.PLAN_INVALID
        )


def test_plan_parser_rejects_bool_float_nan_and_infinity() -> None:
    raw = _raw_plan(_build())
    bool_version = dict(raw)
    bool_version["version"] = True
    float_version = dict(raw)
    float_version["version"] = 1.0
    canonical = serialize_provider_apply_plan(_build())
    nan = canonical.replace(b'"version":1', b'"version":NaN', 1)
    infinity = canonical.replace(b'"version":1', b'"version":Infinity', 1)

    for payload in (_json_bytes(bool_version), _json_bytes(float_version), nan, infinity):
        assert _error_code(lambda payload=payload: parse_provider_apply_plan(payload)) is (
            ProviderApplyErrorCode.PLAN_INVALID
        )


def test_plan_parser_enforces_byte_depth_node_string_and_array_limits() -> None:
    plan = _build()
    raw = _raw_plan(plan)
    long_string = _raw_plan(plan)
    changes = long_string["field_changes"]
    assert isinstance(changes, list)
    changes[1]["proposed_value"] = "x" * (MAX_PROVIDER_APPLY_STRING_LENGTH + 1)
    long_array = _raw_plan(plan)
    long_array["field_changes"] = [
        long_array["field_changes"][0]
        for _ in range(65)
    ]
    deep: object = "leaf"
    for _ in range(MAX_PROVIDER_APPLY_PLAN_DEPTH + 2):
        deep = {"x": deep}
    deep_document = dict(raw)
    deep_document["unknown"] = deep

    for payload in (
        b"{" + b" " * MAX_PROVIDER_APPLY_PLAN_BYTES,
        _json_bytes(long_string),
        _json_bytes(long_array),
        _json_bytes(deep_document),
    ):
        assert _error_code(lambda payload=payload: parse_provider_apply_plan(payload)) is (
            ProviderApplyErrorCode.PLAN_TOO_LARGE
        )


def test_plan_parity_rejects_valid_shape_with_inconsistent_projection() -> None:
    raw = _raw_plan(_build())
    raw["apply_projection_hash"] = "v1:sha256:" + ("0" * 64)

    assert _error_code(lambda: parse_provider_apply_plan(_json_bytes(raw))) is (
        ProviderApplyErrorCode.PLAN_INVALID
    )


def test_token_sign_verify_round_trip_and_default_ttl() -> None:
    plan = _build()
    assert plan.has_writes
    token = sign_provider_apply_plan(
        plan,
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    )

    assert token.startswith("nspap1.")
    assert verify_provider_apply_token(
        token,
        secret=SECRET,
        context=CONTEXT,
        now=NOW + timedelta(seconds=599),
    ) == plan
    assert _error_code(
        lambda: verify_provider_apply_token(
            token,
            secret=SECRET,
            context=CONTEXT,
            now=NOW + timedelta(seconds=600),
        )
    ) is ProviderApplyErrorCode.TOKEN_EXPIRED


def test_token_is_decodable_integrity_only_and_contains_no_secret_or_context() -> None:
    plan = _build()
    token = sign_provider_apply_plan(
        plan,
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    )
    payload = _b64decode(token.split(".")[1])
    document = json.loads(payload)

    assert document["format"] == PROVIDER_APPLY_TOKEN_FORMAT
    assert document["version"] == PROVIDER_APPLY_TOKEN_VERSION
    assert document["plan"]["external_id"] == EXTERNAL_ID
    assert SECRET not in payload
    assert CONTEXT.encode() not in payload
    assert "algorithm" not in document


def test_wrong_secret_and_context_have_distinct_stable_failures() -> None:
    token = sign_provider_apply_plan(
        _build(),
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    )

    assert _error_code(
        lambda: verify_provider_apply_token(
            token,
            secret=b"wrong-secret-that-is-still-32-bytes!",
            context=CONTEXT,
            now=NOW,
        )
    ) is ProviderApplyErrorCode.TOKEN_SIGNATURE_INVALID
    assert _error_code(
        lambda: verify_provider_apply_token(
            token,
            secret=SECRET,
            context="provider-apply:wrong-context",
            now=NOW,
        )
    ) is ProviderApplyErrorCode.TOKEN_CONTEXT_MISMATCH


def test_payload_and_mac_tamper_are_rejected() -> None:
    token = sign_provider_apply_plan(
        _build(),
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    )
    prefix, payload_segment, signature_segment = token.split(".")
    payload_document = json.loads(_b64decode(payload_segment))
    payload_document["plan"]["duplicate_title_item_ids"] = [999]
    tampered_payload = ".".join(
        (prefix, _b64encode(_json_bytes(payload_document)), signature_segment)
    )
    signature = bytearray(_b64decode(signature_segment))
    signature[-1] ^= 1
    tampered_mac = ".".join(
        (prefix, payload_segment, _b64encode(bytes(signature)))
    )

    for candidate in (tampered_payload, tampered_mac):
        assert _error_code(
            lambda candidate=candidate: verify_provider_apply_token(
                candidate,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
            )
        ) is ProviderApplyErrorCode.TOKEN_SIGNATURE_INVALID


def test_future_time_expiry_and_ttl_bounds_are_enforced() -> None:
    plan = _build()
    token = sign_provider_apply_plan(
        plan,
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
        ttl_seconds=MAX_PROVIDER_APPLY_TOKEN_TTL_SECONDS,
    )
    assert _error_code(
        lambda: verify_provider_apply_token(
            token,
            secret=SECRET,
            context=CONTEXT,
            now=NOW - timedelta(microseconds=1),
        )
    ) is ProviderApplyErrorCode.TOKEN_NOT_YET_VALID
    assert verify_provider_apply_token(
        token,
        secret=SECRET,
        context=CONTEXT,
        now=NOW + timedelta(seconds=899),
    ) == plan
    for ttl in (0, True, MAX_PROVIDER_APPLY_TOKEN_TTL_SECONDS + 1):
        assert _error_code(
            lambda ttl=ttl: sign_provider_apply_plan(
                plan,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                ttl_seconds=ttl,  # type: ignore[arg-type]
            )
        ) is ProviderApplyErrorCode.INVALID_REQUEST


@pytest.mark.parametrize(
    "secret",
    [
        "x" * 32,
        bytearray(b"x" * 32),
        memoryview(b"x" * 32),
        b"x" * (MIN_PROVIDER_APPLY_SECRET_BYTES - 1),
    ],
)
def test_secret_must_be_exact_sufficient_bytes(secret: object) -> None:
    assert _error_code(
        lambda: sign_provider_apply_plan(
            _build(),
            secret=secret,  # type: ignore[arg-type]
            context=CONTEXT,
            now=NOW,
        )
    ) is ProviderApplyErrorCode.INVALID_REQUEST


@pytest.mark.parametrize("context", ["", "bad\ncontext", 123, "x" * 256])
def test_context_must_be_bounded_nonempty_opaque_text(context: object) -> None:
    assert _error_code(
        lambda: sign_provider_apply_plan(
            _build(),
            secret=SECRET,
            context=context,  # type: ignore[arg-type]
            now=NOW,
        )
    ) is ProviderApplyErrorCode.INVALID_REQUEST


@pytest.mark.parametrize(
    "token,code",
    [
        ("", ProviderApplyErrorCode.TOKEN_INVALID),
        ("bad", ProviderApplyErrorCode.TOKEN_INVALID),
        ("nspap1.bad!.bad", ProviderApplyErrorCode.TOKEN_INVALID),
        ("nspap2.YQ.YQ", ProviderApplyErrorCode.TOKEN_INVALID),
        ("x" * (MAX_PROVIDER_APPLY_TOKEN_LENGTH + 1), ProviderApplyErrorCode.TOKEN_TOO_LARGE),
    ],
)
def test_token_type_length_segment_prefix_and_base64_are_bounded(
    token: str,
    code: ProviderApplyErrorCode,
) -> None:
    assert _error_code(
        lambda: verify_provider_apply_token(
            token,
            secret=SECRET,
            context=CONTEXT,
            now=NOW,
        )
    ) is code


def test_token_payload_schema_duplicate_and_nonfinite_values_fail_before_mac() -> None:
    token = sign_provider_apply_plan(
        _build(),
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    )
    prefix, payload_segment, signature_segment = token.split(".")
    payload = _b64decode(payload_segment)
    duplicate = payload.replace(
        b'"format":"nsfwtrack.provider-apply-token"',
        b'"format":"nsfwtrack.provider-apply-token","format":"duplicate"',
        1,
    )
    nonfinite = payload.replace(b'"version":1', b'"version":NaN', 1)
    for raw in (duplicate, nonfinite):
        candidate = ".".join((prefix, _b64encode(raw), signature_segment))
        assert _error_code(
            lambda candidate=candidate: verify_provider_apply_token(
                candidate,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
            )
        ) is ProviderApplyErrorCode.TOKEN_INVALID


def test_verification_uses_constant_time_comparison_for_mac_and_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = sign_provider_apply_plan(
        _build(),
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    )
    original = hmac.compare_digest
    calls: list[tuple[object, object]] = []

    def recording(left: object, right: object) -> bool:
        calls.append((left, right))
        return original(left, right)

    monkeypatch.setattr(hmac, "compare_digest", recording)

    assert verify_provider_apply_token(
        token,
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    ) == _build()
    assert len(calls) == 2


def test_builder_parser_and_token_have_no_external_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _forbidden)
    monkeypatch.setattr(socket, "gethostbyname", _forbidden)
    monkeypatch.setattr(httpx2, "AsyncClient", _forbidden)
    monkeypatch.setattr(OutboundHttpClient, "__init__", _forbidden)
    monkeypatch.setattr(Path, "read_bytes", _forbidden)
    monkeypatch.setattr(Path, "write_bytes", _forbidden)
    monkeypatch.setattr(importlib, "import_module", _forbidden)
    monkeypatch.setattr(ProviderSearchService, "search", _forbidden)
    monkeypatch.setattr(ProviderSearchService, "detail", _forbidden)
    monkeypatch.setattr(ProviderSearchService, "asset_list", _forbidden)

    plan = _build()
    payload = serialize_provider_apply_plan(plan)
    assert parse_provider_apply_plan(payload) == plan
    token = sign_provider_apply_plan(
        plan,
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    )
    assert verify_provider_apply_token(
        token,
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    ) == plan


def test_error_paths_do_not_log_or_render_sensitive_markers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "sensitive-token-marker"
    error = ProviderApplyError(ProviderApplyErrorCode.TOKEN_INVALID)
    rendered = f"{error!s} {error!r}"
    assert marker not in rendered
    assert marker not in caplog.text
    assert CANONICAL_URL not in rendered
    assert EXTERNAL_ID not in rendered


def test_phase_invariants_and_empty_production_catalogs_are_unchanged() -> None:
    from app.main import app
    from app.services.exporter import BACKUP_SCHEMA_V2
    from app.services.schema_version import CURRENT_SCHEMA_VERSION

    assert app.version == "1.6.0"
    assert CURRENT_SCHEMA_VERSION == 6
    assert BACKUP_SCHEMA_V2 == "nsfwtrack.backup.v2"
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    assert PRODUCTION_SEARCH_PACKAGES == ()
    assert build_production_search_service().list_providers() == ()
