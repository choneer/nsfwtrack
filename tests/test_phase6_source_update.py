from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.database import SessionLocal
from app.models import Item, ItemSource, OperationTask, SourceCheckFact
from app.source_update import (
    ManualUpdateError,
    apply_manual_update,
    build_manual_update_plan,
    execute_source_check,
    sign_manual_update_plan,
    verify_manual_update_token,
)
from app.tasks import TaskState
from tests.test_phase5_n5b import NOW, PROVIDER_KEY, _service


def _local_source(*, summary: str | None = "Local summary") -> tuple[int, int]:
    with SessionLocal() as db:
        item = Item(
            title="Locally owned title",
            summary=summary,
            release_date="2020-01-01",
        )
        db.add(item)
        db.flush()
        source = ItemSource(
            item_id=item.id,
            url="https://metadata.invalid/canonical-marker",
            normalized_url="https://metadata.invalid/canonical-marker",
            title="Old source title",
            provider_key=PROVIDER_KEY,
            external_id="video-001",
        )
        db.add(source)
        db.commit()
        return item.id, source.id


@pytest.mark.anyio
async def test_manual_check_calls_exactly_one_detail_and_does_not_mutate_item_or_source() -> None:
    item_id, source_id = _local_source()
    service, adapter = _service()
    with SessionLocal() as db:
        before_item = db.get(Item, item_id)
        before_source = db.get(ItemSource, source_id)
        before = (
            before_item.title,
            before_item.summary,
            before_item.release_date,
            before_source.title,
            before_source.last_checked_at,
            before_source.metadata_hash,
        )
        task = await execute_source_check(
            db,
            service,
            item_id=item_id,
            source_id=source_id,
            max_concurrency=2,
        )
        db.expire_all()
        after_item = db.get(Item, item_id)
        after_source = db.get(ItemSource, source_id)
        after = (
            after_item.title,
            after_item.summary,
            after_item.release_date,
            after_source.title,
            after_source.last_checked_at,
            after_source.metadata_hash,
        )
        assert before == after
        assert task.state == TaskState.SUCCEEDED.value
        assert db.get(SourceCheckFact, task.id) is not None
    assert adapter.calls == {"search": 0, "detail": 1, "asset_list": 0}


@pytest.mark.anyio
async def test_per_field_signed_plan_applies_only_selected_values_and_keeps_item_title() -> None:
    item_id, source_id = _local_source()
    service, adapter = _service()
    with SessionLocal() as db:
        check = await execute_source_check(
            db,
            service,
            item_id=item_id,
            source_id=source_id,
            max_concurrency=2,
        )
        plan = build_manual_update_plan(
            db,
            check_task_id=check.id,
            selected_fields=(
                "item.summary",
                "item_source.title",
                "item_source.last_checked_at",
                "item_source.metadata_hash",
            ),
            now=NOW,
        )
        secret = b"m" * 32
        token = sign_manual_update_plan(
            plan,
            secret=secret,
            context="session-one",
            now=NOW,
        )
        verified = verify_manual_update_token(
            token,
            secret=secret,
            context="session-one",
            now=NOW,
        )
        with pytest.raises(ManualUpdateError):
            verify_manual_update_token(
                token,
                secret=secret,
                context="different-session",
                now=NOW,
            )
        result = apply_manual_update(db, plan=verified, max_concurrency=2)
        assert result.commit_status == "committed"
        db.expire_all()
        item = db.get(Item, item_id)
        source = db.get(ItemSource, source_id)
        assert item.title == "Locally owned title"
        assert item.summary == "Synthetic detail summary"
        assert item.release_date == "2020-01-01"
        assert source.title == "Synthetic Detail"
        assert source.last_checked_at == NOW
        assert source.metadata_hash is not None
        update_task = db.get(OperationTask, result.task_id)
        assert update_task is not None and update_task.state == TaskState.SUCCEEDED.value
    assert adapter.calls == {"search": 0, "detail": 1, "asset_list": 0}


@pytest.mark.anyio
async def test_plan_is_stale_after_any_bound_local_change_and_confirm_never_calls_provider() -> None:
    item_id, source_id = _local_source()
    service, adapter = _service()
    with SessionLocal() as db:
        check = await execute_source_check(
            db,
            service,
            item_id=item_id,
            source_id=source_id,
            max_concurrency=2,
        )
        item = db.get(Item, item_id)
        item.summary = "Changed after check"
        db.commit()
        with pytest.raises(ManualUpdateError) as stale:
            build_manual_update_plan(
                db,
                check_task_id=check.id,
                selected_fields=("item.summary",),
                now=NOW,
            )
        assert stale.value.code.value == "stale_plan"
    assert adapter.calls == {"search": 0, "detail": 1, "asset_list": 0}


@pytest.mark.anyio
async def test_provider_empty_value_cannot_clear_local_and_noop_has_no_plan() -> None:
    item_id, source_id = _local_source(summary="Keep this")
    service, adapter = _service()
    adapter.detail_result = replace(
        adapter.detail_result,
        summary=None,
        available_fields=None,
    )
    with SessionLocal() as db:
        check = await execute_source_check(
            db,
            service,
            item_id=item_id,
            source_id=source_id,
            max_concurrency=2,
        )
        with pytest.raises(ManualUpdateError) as no_op:
            build_manual_update_plan(
                db,
                check_task_id=check.id,
                selected_fields=("item.summary",),
                now=NOW,
            )
        assert no_op.value.code.value == "nothing_to_apply"
        assert db.get(Item, item_id).summary == "Keep this"


@pytest.mark.anyio
async def test_forbidden_field_selection_is_rejected() -> None:
    item_id, source_id = _local_source()
    service, _adapter = _service()
    with SessionLocal() as db:
        check = await execute_source_check(
            db,
            service,
            item_id=item_id,
            source_id=source_id,
            max_concurrency=2,
        )
        with pytest.raises(ManualUpdateError):
            build_manual_update_plan(
                db,
                check_task_id=check.id,
                selected_fields=("item.title",),
                now=datetime.now(UTC),
            )
