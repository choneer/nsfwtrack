from __future__ import annotations

import base64
import importlib
import json
import socket
import sqlite3
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2
import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

import app.provider_apply.service as provider_apply_service
import app.provider_apply.transaction as provider_apply_transaction
from app.database import SessionLocal, engine
from app.models import (
    Collection,
    Creator,
    Item,
    ItemActivity,
    ItemCollection,
    ItemCreator,
    ItemSource,
    ItemTag,
    Tag,
    UserItemState,
)
from app.provider_apply import (
    PROVIDER_APPLY_RESULT_FORMAT,
    PROVIDER_APPLY_RESULT_VERSION,
    ProviderApplyAction,
    ProviderApplyCommitStatus,
    ProviderApplyError,
    ProviderApplyErrorCode,
    ProviderApplyPlan,
    ProviderApplyResult,
    apply_provider_apply_token,
    build_provider_apply_plan,
    compute_provider_apply_projection_hash,
    sign_provider_apply_plan,
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
PROVIDER_KEY = "transaction_fixture"
EXTERNAL_ID = "transaction-001"
CANONICAL_URL = "https://transaction.invalid/video/001"
SECRET = b"transactional-provider-apply-secret"
CONTEXT = "provider-apply:n5c-b1"
OLD_HASH = "v1:sha256:" + ("a" * 64)


def _envelope(
    *,
    title: str = "Transactional Provider Title",
    summary: str | None = "Transactional provider summary",
    release_date_value: date | None = date(2026, 7, 1),
    received_at: datetime = NOW,
    canonical_url: str = CANONICAL_URL,
) -> VideoDetailEnvelope:
    descriptor = SearchProviderDescriptor(
        PROVIDER_KEY,
        "Synthetic transactional Provider",
        "Synthetic records only",
        (ProviderOperation.DETAIL,),
    )
    request = VideoDetailRequest(PROVIDER_KEY, EXTERNAL_ID)
    detail = VideoDetail(
        identifier=VideoIdentifier(
            PROVIDER_KEY,
            EXTERNAL_ID,
            canonical_url=canonical_url,
        ),
        title=title,
        summary=summary,
        release_date=release_date_value,
        source_updated_at=NOW - timedelta(hours=1),
    )
    return VideoDetailEnvelope(descriptor, request, detail, received_at)


def _seed_item(
    *,
    title: str = "Local title",
    summary: str | None = None,
    release_date_value: str | None = None,
    cover_path: str | None = None,
    extra: str | None = None,
) -> int:
    with SessionLocal() as db:
        item = Item(
            title=title,
            summary=summary,
            release_date=release_date_value,
            cover_path=cover_path,
            extra=extra,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item.id


def _seed_source(
    item_id: int,
    *,
    url: str = CANONICAL_URL,
    provider_key: str = PROVIDER_KEY,
    external_id: str = EXTERNAL_ID,
    title: str | None = "Preserved source title",
    last_checked_at: datetime | None = NOW - timedelta(days=1),
    metadata_hash: str | None = OLD_HASH,
) -> int:
    normalized = normalize_source_url(url)
    with SessionLocal() as db:
        source = ItemSource(
            item_id=item_id,
            url=normalized,
            normalized_url=normalized,
            title=title,
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


def _token(plan: ProviderApplyPlan) -> str:
    return sign_provider_apply_plan(
        plan,
        secret=SECRET,
        context=CONTEXT,
        now=NOW,
    )


def _apply(
    token: str,
    *,
    verification_session_factory: Any = SessionLocal,
    now: datetime = NOW,
) -> ProviderApplyResult:
    with SessionLocal() as db:
        return apply_provider_apply_token(
            db,
            token,
            secret=SECRET,
            context=CONTEXT,
            now=now,
            verification_session_factory=verification_session_factory,
        )


def _error_code(call: Any) -> ProviderApplyErrorCode:
    with pytest.raises(ProviderApplyError) as exc_info:
        call()
    return exc_info.value.code


def _database_counts() -> tuple[int, ...]:
    models = (
        Item,
        ItemSource,
        Tag,
        Creator,
        Collection,
        ItemTag,
        ItemCreator,
        ItemCollection,
        UserItemState,
        ItemActivity,
    )
    with SessionLocal() as db:
        return tuple(
            int(db.scalar(select(func.count()).select_from(model)) or 0)
            for model in models
        )


def _forbidden(*args: object, **kwargs: object) -> None:
    del args, kwargs
    raise AssertionError("forbidden side effect")


class _ForbiddenDatabase:
    def __getattribute__(self, name: str) -> object:
        raise AssertionError(f"database accessed: {name}")


def _no_change_plan() -> ProviderApplyPlan:
    envelope = _envelope()
    projection_hash = compute_provider_apply_projection_hash(
        envelope,
        normalize_source_url(CANONICAL_URL),
    )
    item_id = _seed_item(
        title="Local preserved title",
        summary="Local summary",
        release_date_value="2025-01-02",
    )
    _seed_source(
        item_id,
        last_checked_at=NOW,
        metadata_hash=projection_hash,
    )
    return _build(envelope)


def _forge_executable_token(plan: ProviderApplyPlan) -> str:
    document = {
        "format": provider_apply_service.PROVIDER_APPLY_TOKEN_FORMAT,
        "version": provider_apply_service.PROVIDER_APPLY_TOKEN_VERSION,
        "issued_at": provider_apply_service._datetime_text(NOW),
        "expires_at": provider_apply_service._datetime_text(
            NOW + timedelta(seconds=600)
        ),
        "plan": provider_apply_service._plan_raw(plan),
    }
    payload = provider_apply_service._canonical_json_bytes(document)
    payload_segment = provider_apply_service._base64url_encode(payload)
    binding = provider_apply_service._context_binding(SECRET, CONTEXT.encode())
    signature = binding + provider_apply_service._token_mac(
        SECRET,
        binding,
        payload_segment,
    )
    return "nspap1." + payload_segment + "." + base64.urlsafe_b64encode(
        signature
    ).rstrip(b"=").decode("ascii")


def test_result_contract_and_new_error_codes_are_fixed_redacted_and_immutable() -> None:
    result = ProviderApplyResult(
        format=PROVIDER_APPLY_RESULT_FORMAT,
        version=PROVIDER_APPLY_RESULT_VERSION,
        action=ProviderApplyAction.UPDATE_ITEM,
        item_id=1,
        source_id=2,
        written_fields=("item.summary",),
        commit_status=ProviderApplyCommitStatus.COMMITTED,
    )

    assert PROVIDER_APPLY_RESULT_FORMAT == "nsfwtrack.provider-apply-result"
    assert PROVIDER_APPLY_RESULT_VERSION == 1
    assert {value.value for value in ProviderApplyCommitStatus} == {
        "committed",
        "committed_verified_after_exception",
    }
    assert ProviderApplyErrorCode.WRITE_CONFLICT.value == "write_conflict"
    assert ProviderApplyErrorCode.WRITE_FAILED.value == "write_failed"
    assert ProviderApplyErrorCode.COMMIT_STATE_UNKNOWN.value == "commit_state_unknown"
    assert not hasattr(result, "__dict__")
    assert repr(result) == "ProviderApplyResult()"
    assert str(result) == "ProviderApplyResult"
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.item_id = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    "case",
    ["malformed", "expired", "wrong_context", "wrong_secret"],
)
def test_token_failure_precedes_every_database_and_factory_access(case: str) -> None:
    plan = _build()
    token = _token(plan)
    secret = SECRET
    context = CONTEXT
    now = NOW
    expected = ProviderApplyErrorCode.TOKEN_INVALID
    if case == "malformed":
        token = "not-a-token"
    elif case == "expired":
        now = NOW + timedelta(seconds=600)
        expected = ProviderApplyErrorCode.TOKEN_EXPIRED
    elif case == "wrong_context":
        context = "provider-apply:wrong-context"
        expected = ProviderApplyErrorCode.TOKEN_CONTEXT_MISMATCH
    else:
        secret = b"wrong-transaction-secret-32bytes!"
        expected = ProviderApplyErrorCode.TOKEN_SIGNATURE_INVALID

    code = _error_code(
        lambda: apply_provider_apply_token(
            _ForbiddenDatabase(),  # type: ignore[arg-type]
            token,
            secret=secret,
            context=context,
            now=now,
            verification_session_factory=_forbidden,
        )
    )

    assert code is expected


def test_forged_noop_token_is_rejected_before_database_access() -> None:
    plan = _no_change_plan()
    assert not plan.has_writes
    token = _forge_executable_token(plan)

    assert _error_code(
        lambda: apply_provider_apply_token(
            _ForbiddenDatabase(),  # type: ignore[arg-type]
            token,
            secret=SECRET,
            context=CONTEXT,
            now=NOW,
            verification_session_factory=_forbidden,
        )
    ) is ProviderApplyErrorCode.NOTHING_TO_APPLY


def test_pending_or_existing_session_state_is_rejected_without_sql_or_cleanup() -> None:
    token = _token(_build())
    statements: list[str] = []

    def record(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        statements.append(statement)

    with SessionLocal() as db:
        pending = Item(title="Pending caller state")
        db.add(pending)
        event.listen(engine, "before_cursor_execute", record)
        try:
            code = _error_code(
                lambda: apply_provider_apply_token(
                    db,
                    token,
                    secret=SECRET,
                    context=CONTEXT,
                    now=NOW,
                    verification_session_factory=SessionLocal,
                )
            )
        finally:
            event.remove(engine, "before_cursor_execute", record)
        assert pending in db.new
        assert pending.id is None

    assert code is ProviderApplyErrorCode.INVALID_REQUEST
    assert statements == []

    with SessionLocal() as db:
        db.begin()
        assert _error_code(
            lambda: apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=SessionLocal,
            )
        ) is ProviderApplyErrorCode.INVALID_REQUEST
        assert db.in_transaction()


def test_invalid_verification_factory_is_rejected_before_begin_immediate() -> None:
    token = _token(_build())
    statements: list[str] = []

    def record(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        with SessionLocal() as db:
            code = _error_code(
                lambda: apply_provider_apply_token(
                    db,
                    token,
                    secret=SECRET,
                    context=CONTEXT,
                    now=NOW,
                    verification_session_factory=None,  # type: ignore[arg-type]
                )
            )
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert code is ProviderApplyErrorCode.INVALID_REQUEST
    assert statements == []


def test_begin_immediate_is_first_sql_and_precedes_select_insert_and_commit() -> None:
    token = _token(_build())
    events: list[str] = []

    def record_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        events.append(" ".join(statement.strip().upper().split()))

    def record_commit(connection: object) -> None:
        del connection
        events.append("<COMMIT>")

    event.listen(engine, "before_cursor_execute", record_statement)
    event.listen(engine, "commit", record_commit)
    try:
        result = _apply(token)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)
        event.remove(engine, "commit", record_commit)

    assert result.commit_status is ProviderApplyCommitStatus.COMMITTED
    assert events[0] == "BEGIN IMMEDIATE"
    first_select = next(index for index, value in enumerate(events) if value.startswith("SELECT"))
    first_insert = next(index for index, value in enumerate(events) if value.startswith("INSERT"))
    commit = events.index("<COMMIT>")
    assert 0 < first_select < first_insert < commit
    assert any(value.startswith("SELECT") for value in events[commit + 1 :])


def test_create_sql_writes_only_approved_columns_and_attempts_one_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _build(_envelope(summary=None, release_date_value=None))
    token = _token(plan)
    statements: list[str] = []

    def record(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        statements.append(" ".join(statement.strip().upper().split()))

    with SessionLocal() as db:
        original_commit = db.commit
        commit_attempts = 0

        def counted_commit() -> None:
            nonlocal commit_attempts
            commit_attempts += 1
            original_commit()

        monkeypatch.setattr(db, "commit", counted_commit)
        event.listen(engine, "before_cursor_execute", record)
        try:
            result = apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=SessionLocal,
            )
        finally:
            event.remove(engine, "before_cursor_execute", record)

    inserts = [value for value in statements if value.startswith("INSERT")]
    assert len(inserts) == 2
    item_insert = next(value for value in inserts if value.startswith("INSERT INTO ITEMS "))
    source_insert = next(
        value for value in inserts if value.startswith("INSERT INTO ITEM_SOURCES ")
    )
    assert "(TITLE)" in item_insert
    for forbidden in ("COVER_PATH", "EXTRA", "SUMMARY", "RELEASE_DATE"):
        assert forbidden not in item_insert
    for required in (
        "ITEM_ID",
        "URL",
        "NORMALIZED_URL",
        "TITLE",
        "PROVIDER_KEY",
        "EXTERNAL_ID",
        "LAST_CHECKED_AT",
        "METADATA_HASH",
    ):
        assert required in source_insert
    assert not any(
        value.startswith(("DELETE", "CREATE", "DROP", "ALTER"))
        for value in statements
    )
    assert commit_attempts == 1
    assert result.written_fields == tuple(
        change.field_name for change in plan.field_changes if change.will_write
    )


def test_all_source_and_duplicate_queries_are_stably_ordered_and_sql_bounded() -> None:
    item_id = _seed_item(summary=None)
    _seed_source(item_id)
    token = _token(_build())
    statements: list[tuple[str, object]] = []

    def record(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, context, executemany
        statements.append((" ".join(statement.strip().upper().split()), parameters))

    event.listen(engine, "before_cursor_execute", record)
    try:
        _apply(token)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    source_selects = [
        (statement, parameters)
        for statement, parameters in statements
        if statement.startswith("SELECT") and "FROM ITEM_SOURCES" in statement
    ]
    duplicate_selects = [
        (statement, parameters)
        for statement, parameters in statements
        if statement.startswith("SELECT")
        and "FROM ITEMS" in statement
        and "WHERE ITEMS.TITLE =" in statement
    ]
    assert len(source_selects) >= 6
    assert len(duplicate_selects) >= 3
    for statement, parameters in source_selects:
        assert "ORDER BY ITEM_SOURCES.ID ASC" in statement
        assert "LIMIT" in statement
        assert 2 in tuple(parameters)
    for statement, parameters in duplicate_selects:
        assert "ORDER BY ITEMS.ID ASC" in statement
        assert "LIMIT" in statement
        assert 32 in tuple(parameters)


def test_create_success_is_exact_independently_verified_and_replay_is_stale() -> None:
    plan = _build()
    token = _token(plan)
    before = _database_counts()

    result = _apply(token)

    expected_written = tuple(
        change.field_name for change in plan.field_changes if change.will_write
    )
    assert result.action is ProviderApplyAction.CREATE_ITEM
    assert result.written_fields == expected_written
    assert result.commit_status is ProviderApplyCommitStatus.COMMITTED
    with SessionLocal() as db:
        item = db.get(Item, result.item_id)
        source = db.get(ItemSource, result.source_id)
        assert item is not None
        assert source is not None
        assert (item.title, item.summary, item.release_date) == (
            "Transactional Provider Title",
            "Transactional provider summary",
            "2026-07-01",
        )
        assert item.cover_path is None and item.extra is None
        assert source.item_id == item.id
        assert source.url == source.normalized_url == CANONICAL_URL
        assert source.title == item.title
        assert source.provider_key == PROVIDER_KEY
        assert source.external_id == EXTERNAL_ID
        assert source.last_checked_at == NOW
        assert source.metadata_hash == plan.apply_projection_hash
    after = _database_counts()
    assert after[0] == before[0] + 1
    assert after[1] == before[1] + 1
    assert after[2:] == before[2:]

    assert _error_code(lambda: _apply(token)) is ProviderApplyErrorCode.STALE_PLAN
    assert _database_counts() == after


def test_create_duplicate_title_is_only_a_hint_and_never_an_link_target() -> None:
    existing_item_id = _seed_item(title="Transactional Provider Title")
    plan = _build()
    assert plan.duplicate_title_item_ids == (existing_item_id,)

    result = _apply(_token(plan))

    assert result.item_id != existing_item_id
    with SessionLocal() as db:
        assert tuple(
            db.scalars(
                select(Item.id)
                .where(Item.title == "Transactional Provider Title")
                .order_by(Item.id)
            ).all()
        ) == (existing_item_id, result.item_id)


def test_fill_blank_update_preserves_forbidden_fields_and_replay_is_stale() -> None:
    item_id = _seed_item(
        title="Local title must remain",
        summary=None,
        release_date_value=None,
        cover_path="media/local-cover.jpg",
        extra='{"local":true}',
    )
    source_id = _seed_source(item_id)
    with SessionLocal() as db:
        original_updated_at = db.get(Item, item_id).updated_at  # type: ignore[union-attr]
    plan = _build()
    token = _token(plan)
    updates: list[str] = []

    def record(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        normalized = " ".join(statement.strip().upper().split())
        if normalized.startswith("UPDATE"):
            updates.append(normalized)

    event.listen(engine, "before_cursor_execute", record)
    try:
        result = _apply(token)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert result.item_id == item_id
    assert result.source_id == source_id
    assert result.written_fields == tuple(
        change.field_name for change in plan.field_changes if change.will_write
    )
    with SessionLocal() as db:
        item = db.get(Item, item_id)
        source = db.get(ItemSource, source_id)
        assert item is not None and source is not None
        assert item.title == "Local title must remain"
        assert item.summary == "Transactional provider summary"
        assert item.release_date == "2026-07-01"
        assert item.cover_path == "media/local-cover.jpg"
        assert item.extra == '{"local":true}'
        assert item.updated_at == original_updated_at
        assert source.url == source.normalized_url == CANONICAL_URL
        assert source.title == "Preserved source title"
        assert source.provider_key == PROVIDER_KEY
        assert source.external_id == EXTERNAL_ID
        assert source.last_checked_at == NOW
        assert source.metadata_hash == plan.apply_projection_hash

    assert len(updates) == 2
    item_update = next(value for value in updates if value.startswith("UPDATE ITEMS "))
    source_update = next(
        value for value in updates if value.startswith("UPDATE ITEM_SOURCES ")
    )
    for forbidden in ("TITLE", "COVER_PATH", "EXTRA", "UPDATED_AT"):
        assert forbidden not in item_update
    for forbidden in (
        "URL",
        "NORMALIZED_URL",
        "TITLE",
        "PROVIDER_KEY",
        "EXTERNAL_ID",
    ):
        assert forbidden not in source_update

    assert _error_code(lambda: _apply(token)) is ProviderApplyErrorCode.STALE_PLAN
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ItemSource)) == 1


def test_tracking_only_update_does_not_issue_item_update() -> None:
    item_id = _seed_item(
        title="Local title",
        summary="Local summary",
        release_date_value="2025-01-02",
    )
    _seed_source(item_id)
    plan = _build()
    assert tuple(
        change.field_name for change in plan.field_changes if change.will_write
    ) == (
        "item_source.last_checked_at",
        "item_source.metadata_hash",
    )
    updates: list[str] = []

    def record(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        normalized = " ".join(statement.strip().upper().split())
        if normalized.startswith("UPDATE"):
            updates.append(normalized)

    event.listen(engine, "before_cursor_execute", record)
    try:
        result = _apply(_token(plan))
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert result.written_fields == (
        "item_source.last_checked_at",
        "item_source.metadata_hash",
    )
    assert len(updates) == 1
    assert updates[0].startswith("UPDATE ITEM_SOURCES ")


@pytest.mark.parametrize(
    "mutation",
    [
        "source_id",
        "source_item_id",
        "source_url",
        "source_normalized_url",
        "source_identity",
        "source_last_checked",
        "source_metadata_hash",
        "item_title",
        "item_summary",
        "item_release_date",
        "item_missing",
        "duplicate_title_ids",
    ],
)
def test_update_snapshot_change_is_stale_with_zero_apply_writes(mutation: str) -> None:
    item_id = _seed_item(title="Local title", summary=None, release_date_value=None)
    other_item_id = _seed_item(title="Unrelated local item")
    source_id = _seed_source(item_id)
    token = _token(_build())

    with SessionLocal() as db:
        if mutation == "source_id":
            db.execute(
                text("UPDATE item_sources SET id = id + 100 WHERE id = :source_id"),
                {"source_id": source_id},
            )
        elif mutation == "source_item_id":
            db.execute(
                text("UPDATE item_sources SET item_id = :item_id WHERE id = :source_id"),
                {"item_id": other_item_id, "source_id": source_id},
            )
        elif mutation == "source_url":
            db.execute(
                text("UPDATE item_sources SET url = :url WHERE id = :source_id"),
                {"url": "https://transaction.invalid/video/changed", "source_id": source_id},
            )
        elif mutation == "source_normalized_url":
            db.execute(
                text(
                    "UPDATE item_sources SET url = :url, normalized_url = :url "
                    "WHERE id = :source_id"
                ),
                {"url": "https://transaction.invalid/video/changed", "source_id": source_id},
            )
        elif mutation == "source_identity":
            db.execute(
                text(
                    "UPDATE item_sources SET provider_key = :provider_key "
                    "WHERE id = :source_id"
                ),
                {"provider_key": "transaction_changed", "source_id": source_id},
            )
        elif mutation == "source_last_checked":
            source = db.get(ItemSource, source_id)
            assert source is not None
            source.last_checked_at = NOW - timedelta(hours=2)
        elif mutation == "source_metadata_hash":
            source = db.get(ItemSource, source_id)
            assert source is not None
            source.metadata_hash = "v1:sha256:" + ("b" * 64)
        elif mutation == "item_title":
            item = db.get(Item, item_id)
            assert item is not None
            item.title = "Changed local title"
        elif mutation == "item_summary":
            item = db.get(Item, item_id)
            assert item is not None
            item.summary = "Changed local summary"
        elif mutation == "item_release_date":
            item = db.get(Item, item_id)
            assert item is not None
            item.release_date = "2024-01-01"
        elif mutation == "item_missing":
            db.execute(text("DELETE FROM items WHERE id = :item_id"), {"item_id": item_id})
        else:
            db.add(Item(title="Transactional Provider Title"))
        db.commit()

    before = _database_counts()
    assert _error_code(lambda: _apply(token)) is ProviderApplyErrorCode.STALE_PLAN
    assert _database_counts() == before


@pytest.mark.parametrize("mutation", ["identity", "url", "duplicate_title_ids"])
def test_create_snapshot_change_is_stale_with_zero_apply_writes(mutation: str) -> None:
    token = _token(_build())
    item_id = _seed_item(title="Intervening item")
    if mutation == "identity":
        _seed_source(item_id, url="https://transaction.invalid/video/other")
    elif mutation == "url":
        _seed_source(
            item_id,
            provider_key="transaction_other",
            external_id="other-001",
        )
    else:
        with SessionLocal() as db:
            db.add(Item(title="Transactional Provider Title"))
            db.commit()

    before = _database_counts()
    assert _error_code(lambda: _apply(token)) is ProviderApplyErrorCode.STALE_PLAN
    assert _database_counts() == before


def test_multiple_bounded_identity_rows_are_database_state_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = _seed_item()
    _seed_source(item_id)
    token = _token(_build())
    original = provider_apply_transaction._query_sources

    def duplicate_identity(*args: object, **kwargs: object) -> object:
        values = original(*args, **kwargs)
        if kwargs.get("normalized_url") is None and values:
            return (values[0], values[0])
        return values

    monkeypatch.setattr(
        provider_apply_transaction,
        "_query_sources",
        duplicate_identity,
    )
    before = _database_counts()

    assert _error_code(lambda: _apply(token)) is (
        ProviderApplyErrorCode.DATABASE_STATE_INVALID
    )
    assert _database_counts() == before


def test_item_flush_integrity_error_is_conflict_only_after_independent_preproof(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = _token(_build())
    marker = "sensitive-item-integrity-marker"
    with SessionLocal() as db:
        monkeypatch.setattr(
            db,
            "flush",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                IntegrityError("sensitive SQL", {}, sqlite3.IntegrityError(marker))
            ),
        )
        code = _error_code(
            lambda: apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=SessionLocal,
            )
        )

    assert code is ProviderApplyErrorCode.WRITE_CONFLICT
    assert _database_counts()[:2] == (0, 0)
    assert marker not in caplog.text


def test_source_flush_unique_error_rolls_back_item_and_reports_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _token(_build())
    with SessionLocal() as db:
        original_flush = db.flush
        calls = 0

        def fail_second_flush(*args: object, **kwargs: object) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise IntegrityError(
                    "sensitive SQL",
                    {},
                    sqlite3.IntegrityError("sensitive-source-marker"),
                )
            original_flush(*args, **kwargs)

        monkeypatch.setattr(db, "flush", fail_second_flush)
        code = _error_code(
            lambda: apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=SessionLocal,
            )
        )

    assert code is ProviderApplyErrorCode.WRITE_CONFLICT
    assert calls == 2
    assert _database_counts()[:2] == (0, 0)


def test_non_integrity_flush_failure_with_exact_prestate_is_write_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _token(_build())
    with SessionLocal() as db:
        monkeypatch.setattr(db, "flush", _forbidden)
        code = _error_code(
            lambda: apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=SessionLocal,
            )
        )

    assert code is ProviderApplyErrorCode.WRITE_FAILED
    assert _database_counts()[:2] == (0, 0)


def test_transaction_postcheck_mismatch_rolls_back_and_is_independently_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = _seed_item(summary=None)
    _seed_source(item_id)
    token = _token(_build())
    original = provider_apply_transaction._matches_expected_state

    with SessionLocal() as db:
        def mismatch_write_session(*args: object, **kwargs: object) -> bool:
            if args[0] is db:
                return False
            return original(*args, **kwargs)

        monkeypatch.setattr(
            provider_apply_transaction,
            "_matches_expected_state",
            mismatch_write_session,
        )
        code = _error_code(
            lambda: apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=SessionLocal,
            )
        )

    assert code is ProviderApplyErrorCode.WRITE_FAILED
    with SessionLocal() as verification_db:
        item = verification_db.get(Item, item_id)
        assert item is not None and item.summary is None


def test_commit_exception_after_real_commit_returns_verified_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _build()
    token = _token(plan)
    with SessionLocal() as db:
        original_commit = db.commit

        def commit_then_raise() -> None:
            original_commit()
            raise RuntimeError("sensitive-post-commit-marker")

        monkeypatch.setattr(db, "commit", commit_then_raise)
        result = apply_provider_apply_token(
            db,
            token,
            secret=SECRET,
            context=CONTEXT,
            now=NOW,
            verification_session_factory=SessionLocal,
        )

    assert result.commit_status is (
        ProviderApplyCommitStatus.COMMITTED_VERIFIED_AFTER_EXCEPTION
    )
    with SessionLocal() as verification_db:
        assert verification_db.get(Item, result.item_id) is not None
        assert verification_db.get(ItemSource, result.source_id) is not None


def test_commit_exception_with_exact_prestate_is_write_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _token(_build())
    with SessionLocal() as db:
        monkeypatch.setattr(db, "commit", _forbidden)
        code = _error_code(
            lambda: apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=SessionLocal,
            )
        )

    assert code is ProviderApplyErrorCode.WRITE_FAILED
    assert _database_counts()[:2] == (0, 0)


def test_rollback_exception_does_not_override_independent_prestate_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _token(_build())
    with SessionLocal() as db:
        original_rollback = db.rollback

        def rollback_then_raise() -> None:
            original_rollback()
            raise RuntimeError("sensitive-rollback-marker")

        monkeypatch.setattr(db, "commit", _forbidden)
        monkeypatch.setattr(db, "rollback", rollback_then_raise)
        code = _error_code(
            lambda: apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=SessionLocal,
            )
        )

    assert code is ProviderApplyErrorCode.WRITE_FAILED
    assert _database_counts()[:2] == (0, 0)


@pytest.mark.parametrize("factory_mode", ["raise", "same_session", "wrong_bind"])
def test_unavailable_or_nonindependent_verification_is_commit_state_unknown(
    monkeypatch: pytest.MonkeyPatch,
    factory_mode: str,
) -> None:
    token = _token(_build())
    wrong_engine = None
    wrong_factory = None
    with SessionLocal() as db:
        if factory_mode == "raise":
            factory: Any = _forbidden
        elif factory_mode == "same_session":
            factory = lambda: db
        else:
            wrong_engine = create_engine("sqlite:///:memory:", future=True)
            wrong_factory = sessionmaker(bind=wrong_engine, future=True)
            factory = wrong_factory
        code = _error_code(
            lambda: apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=factory,
            )
        )
    if wrong_engine is not None:
        wrong_engine.dispose()

    assert code is ProviderApplyErrorCode.COMMIT_STATE_UNKNOWN
    assert _database_counts()[:2] == (1, 1)


def test_independent_verification_session_is_read_only_and_always_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _token(_build())
    verification_db = SessionLocal()
    original_close = verification_db.close
    close_calls = 0
    factory_calls = 0

    def close() -> None:
        nonlocal close_calls
        close_calls += 1
        original_close()

    def factory() -> Session:
        nonlocal factory_calls
        factory_calls += 1
        return verification_db

    monkeypatch.setattr(verification_db, "commit", _forbidden)
    monkeypatch.setattr(verification_db, "close", close)
    result = _apply(token, verification_session_factory=factory)

    assert result.commit_status is ProviderApplyCommitStatus.COMMITTED
    assert factory_calls == 1
    assert close_calls == 1


def test_normal_commit_with_independent_state_mismatch_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _token(_build())
    original = provider_apply_transaction._matches_expected_state
    with SessionLocal() as db:
        def mismatch_verification(*args: object, **kwargs: object) -> bool:
            if args[0] is not db:
                return False
            return original(*args, **kwargs)

        monkeypatch.setattr(
            provider_apply_transaction,
            "_matches_expected_state",
            mismatch_verification,
        )
        code = _error_code(
            lambda: apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=SessionLocal,
            )
        )

    assert code is ProviderApplyErrorCode.COMMIT_STATE_UNKNOWN
    assert _database_counts()[:2] == (1, 1)


def test_commit_failure_and_verification_failure_are_unknown_not_assumed_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _token(_build())
    with SessionLocal() as db:
        monkeypatch.setattr(db, "commit", _forbidden)
        code = _error_code(
            lambda: apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=_forbidden,
            )
        )

    assert code is ProviderApplyErrorCode.COMMIT_STATE_UNKNOWN
    assert _database_counts()[:2] == (0, 0)


def test_apply_has_no_provider_outbound_network_or_file_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _token(_build())
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

    result = _apply(token)

    assert result.commit_status is ProviderApplyCommitStatus.COMMITTED


def test_errors_results_and_logs_do_not_expose_sensitive_values(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    plan = _build()
    token = _token(plan)
    marker = "sensitive-transaction-exception-marker"
    with SessionLocal() as db:
        monkeypatch.setattr(
            db,
            "flush",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(marker)),
        )
        with pytest.raises(ProviderApplyError) as exc_info:
            apply_provider_apply_token(
                db,
                token,
                secret=SECRET,
                context=CONTEXT,
                now=NOW,
                verification_session_factory=SessionLocal,
            )

    rendered = f"{exc_info.value!s} {exc_info.value!r} {caplog.text}"
    for value in (
        token,
        SECRET.decode(),
        CONTEXT,
        PROVIDER_KEY,
        EXTERNAL_ID,
        CANONICAL_URL,
        "Transactional Provider Title",
        marker,
        "BEGIN IMMEDIATE",
    ):
        assert value not in rendered


def test_phase_invariants_and_production_catalogs_remain_unchanged() -> None:
    from app.main import app
    from app.services.exporter import BACKUP_SCHEMA_V2
    from app.services.schema_version import CURRENT_SCHEMA_VERSION

    assert app.version == "1.3.0"
    assert CURRENT_SCHEMA_VERSION == 5
    assert BACKUP_SCHEMA_V2 == "nsfwtrack.backup.v2"
    assert PRODUCTION_ENDPOINT_REGISTRY.providers == ()
    assert PRODUCTION_SEARCH_PACKAGES == ()
    assert build_production_search_service().list_providers() == ()
