from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

import app.source_update.service as source_update_module
from app.database import SessionLocal
from app.models import Item, ItemSource, OperationTask, SourceCheckFact, TaskEvent
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
        assert result.commit_status == "committed_verified"
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
        assert update_task.stage == "committed_verified"
        event_count = db.query(TaskEvent).filter_by(task_id=result.task_id).count()
        replay = apply_manual_update(db, plan=verified, max_concurrency=2)
        assert replay.task_id == result.task_id
        assert replay.commit_status == "already_applied_verified"
        assert db.query(OperationTask).filter_by(
            intent_key=update_task.intent_key
        ).count() == 1
        assert db.query(TaskEvent).filter_by(task_id=result.task_id).count() == event_count
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


@pytest.mark.anyio
async def test_commit_exception_is_proven_and_unselected_identity_remains_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id, source_id = _local_source()
    service, _adapter = _service()
    with SessionLocal() as db:
        item = db.get(Item, item_id)
        source = db.get(ItemSource, source_id)
        item.cover_path = "covers/local.png"
        item.extra = "local-extra"
        db.commit()
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
            selected_fields=("item.summary", "item_source.title"),
            now=NOW,
        )
        original_identity = (
            source.url,
            source.normalized_url,
            source.provider_key,
            source.external_id,
        )
        original_commit = db.commit
        injected = False

        def commit_written_then_raise() -> None:
            nonlocal injected
            metadata_task = db.scalar(
                source_update_module.select(OperationTask).where(
                    OperationTask.task_type == "metadata_update"
                )
            )
            stage = metadata_task.stage if metadata_task is not None else None
            original_commit()
            if stage == "written" and not injected:
                injected = True
                raise RuntimeError("synthetic commit uncertainty")

        monkeypatch.setattr(db, "commit", commit_written_then_raise)
        result = apply_manual_update(db, plan=plan, max_concurrency=2)
        assert result.commit_status == "committed_verified"
        db.expire_all()
        item = db.get(Item, item_id)
        source = db.get(ItemSource, source_id)
        assert item.title == "Locally owned title"
        assert item.cover_path == "covers/local.png"
        assert item.extra == "local-extra"
        assert item.release_date == "2020-01-01"
        assert (
            source.url,
            source.normalized_url,
            source.provider_key,
            source.external_id,
        ) == original_identity


@pytest.mark.anyio
async def test_final_manual_proof_mismatch_downgrades_task_to_outcome_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        plan = build_manual_update_plan(
            db,
            check_task_id=check.id,
            selected_fields=("item.summary",),
            now=NOW,
        )
        original = source_update_module._verify_manual_update_state

        def reject_final(*args, **kwargs):
            if kwargs["expected_state"] is TaskState.SUCCEEDED:
                raise source_update_module._IndependentManualVerificationFailed
            return original(*args, **kwargs)

        monkeypatch.setattr(
            source_update_module,
            "_verify_manual_update_state",
            reject_final,
        )
        with pytest.raises(ManualUpdateError) as failure:
            apply_manual_update(db, plan=plan, max_concurrency=2)
        assert failure.value.code.value == "outcome_unknown"
        db.expire_all()
        metadata_task = db.scalar(
            source_update_module.select(OperationTask).where(
                OperationTask.task_type == "metadata_update"
            )
        )
        assert metadata_task is not None
        assert metadata_task.state == TaskState.OUTCOME_UNKNOWN.value
        assert metadata_task.stage == "verification_unknown"


@pytest.mark.anyio
async def test_manual_pre_state_and_independent_read_failure_are_classified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        plan = build_manual_update_plan(
            db,
            check_task_id=check.id,
            selected_fields=("item.summary",),
            now=NOW,
        )
        original_commit = db.commit
        failed = False

        def fail_before_commit() -> None:
            nonlocal failed
            if not failed:
                failed = True
                raise RuntimeError("synthetic write failure")
            original_commit()

        monkeypatch.setattr(db, "commit", fail_before_commit)
        with pytest.raises(ManualUpdateError) as write_failed:
            apply_manual_update(db, plan=plan, max_concurrency=2)
        assert write_failed.value.code.value == "write_failed"
        db.expire_all()
        assert db.get(Item, item_id).summary == "Local summary"
        assert db.query(OperationTask).filter_by(task_type="metadata_update").count() == 0

    with SessionLocal() as db:
        def unavailable(*args, **kwargs):
            raise source_update_module._IndependentManualVerificationFailed

        monkeypatch.setattr(
            source_update_module,
            "_verify_manual_update_state",
            unavailable,
        )
        monkeypatch.setattr(
            source_update_module,
            "_verify_manual_pre_state",
            unavailable,
        )
        with pytest.raises(ManualUpdateError) as unknown:
            apply_manual_update(db, plan=plan, max_concurrency=2)
        assert unknown.value.code.value == "outcome_unknown"
        assert "metadata.invalid" not in str(unknown.value)
        assert "Local summary" not in str(unknown.value)
