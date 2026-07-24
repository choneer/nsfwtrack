from __future__ import annotations

import errno
import struct
import zlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.database import SessionLocal
from app.local_workflow.service import (
    LocalWorkflowError,
    build_local_import_preview,
    confirm_local_import,
    create_index_task,
    create_integrity_task,
    create_recovery_task,
    effective_task_state,
    execute_local_task,
    sign_local_import_plan,
    verify_local_import_token,
)
from app.models import Item, ItemLocalAsset, MediaIndexEntry, MediaIndexState, OperationTask
from app.provider_runtime.service import (
    ProviderRuntimeError,
    ProviderRuntimeErrorCode,
    ProviderRuntimeRegistry,
    egress_profile_statuses,
)
from app.services import local_media
from app.tasks import PersistentTaskService, TaskState, TaskType


def _png_bytes(red: int = 0) -> bytes:
    def chunk(name: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + name
            + payload
            + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(bytes((0, red, 0, 0)))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", pixels)
        + chunk(b"IEND", b"")
    )


def _item() -> int:
    with SessionLocal() as db:
        item = Item(title="Local workflow")
        db.add(item)
        db.commit()
        return item.id


def _media_file(relative: str, *, red: int = 1) -> Path:
    path = local_media.LOCAL_MEDIA_ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png_bytes(red))
    return path


def test_preview_is_zero_write_signed_and_rejects_traversal_and_symlink(
    tmp_path: Path,
) -> None:
    item_id = _item()
    _media_file("library/cover.png")
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png_bytes(2))
    (local_media.LOCAL_MEDIA_ROOT / "escape.png").symlink_to(outside)
    with SessionLocal() as db:
        preview = build_local_import_preview(
            db,
            item_id=item_id,
            source_id=None,
            path="/media/library/cover.png",
        )
        assert db.scalar(select(func.count()).select_from(OperationTask)) == 0
        token = sign_local_import_plan(
            preview.plan,
            secret=b"s" * 32,
            context="phase8",
            now=datetime.now(UTC),
        )
        assert (
            verify_local_import_token(
                token,
                secret=b"s" * 32,
                context="phase8",
                now=datetime.now(UTC),
            )
            == preview.plan
        )
        with pytest.raises(LocalWorkflowError):
            build_local_import_preview(
                db, item_id=item_id, source_id=None, path="/media/../outside.png"
            )
        with pytest.raises(LocalWorkflowError):
            build_local_import_preview(
                db, item_id=item_id, source_id=None, path="/media/escape.png"
            )


def test_single_import_confirm_execute_independent_verification_and_idempotency() -> None:
    item_id = _item()
    path = _media_file("library/one.png", red=3)
    with SessionLocal() as db:
        preview = build_local_import_preview(
            db, item_id=item_id, source_id=None, path="/media/library/one.png"
        )
        tasks = confirm_local_import(db, plan=preview.plan, max_concurrency=2)
        replay = confirm_local_import(db, plan=preview.plan, max_concurrency=2)
        assert replay[0].id == tasks[0].id
        result = execute_local_task(db, task_id=tasks[0].id, max_concurrency=2)
        assert result.state == "succeeded"
        assert result.stage == "durable_verified"
        completed_replay = confirm_local_import(
            db, plan=preview.plan, max_concurrency=2
        )
        assert completed_replay[0].id == result.id
        assert completed_replay[0].state == "succeeded"

    with SessionLocal() as independent:
        links = tuple(independent.scalars(select(ItemLocalAsset)).all())
        assert len(links) == 1
        assert links[0].relative_path == "library/one.png"
        assert links[0].size_bytes == path.stat().st_size
        assert independent.get(MediaIndexState, 1).valid is True
        indexed = independent.scalar(
            select(MediaIndexEntry).where(
                MediaIndexEntry.media_path == "/media/library/one.png"
            )
        )
        assert indexed is not None and indexed.sha256 == links[0].sha256


def test_directory_import_duplicate_detection_and_integrity_task() -> None:
    item_id = _item()
    _media_file("batch/a.png", red=4)
    _media_file("batch/b.png", red=5)
    with SessionLocal() as db:
        preview = build_local_import_preview(
            db,
            item_id=item_id,
            source_id=None,
            path="/media/batch",
            directory=True,
        )
        assert {fact.relative_path for fact in preview.plan.files} == {
            "batch/a.png",
            "batch/b.png",
        }
        tasks = confirm_local_import(db, plan=preview.plan, max_concurrency=2)
        first = execute_local_task(db, task_id=tasks[0].id, max_concurrency=2)
        asset = db.scalar(
            select(ItemLocalAsset).where(ItemLocalAsset.task_id == first.id)
        )
        check = create_integrity_task(db, asset_id=asset.id, max_concurrency=2)
        checked = execute_local_task(db, task_id=check.id, max_concurrency=2)
        assert checked.state == "succeeded"
        duplicate_preview = build_local_import_preview(
            db,
            item_id=item_id,
            source_id=None,
            path="/media/batch",
            directory=True,
        )
        assert duplicate_preview.duplicates == ("batch/a.png",)
        assert tuple(f.relative_path for f in duplicate_preview.plan.files) == ("batch/b.png",)


def test_directory_preview_deduplicates_equal_content_before_task_creation() -> None:
    item_id = _item()
    _media_file("same/a.png", red=15)
    _media_file("same/b.png", red=15)
    with SessionLocal() as db:
        preview = build_local_import_preview(
            db,
            item_id=item_id,
            source_id=None,
            path="/media/same",
            directory=True,
        )
        assert tuple(f.relative_path for f in preview.plan.files) == ("same/a.png",)
        assert preview.duplicates == ("same/b.png",)
        tasks = confirm_local_import(db, plan=preview.plan, max_concurrency=2)
        assert len(tasks) == 1


def test_snapshot_change_and_independent_session_failure_never_claim_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = _item()
    file_path = _media_file("changed.png", red=6)
    with SessionLocal() as db:
        plan = build_local_import_preview(
            db, item_id=item_id, source_id=None, path="/media/changed.png"
        ).plan
        file_path.write_bytes(_png_bytes(7))
        with pytest.raises(LocalWorkflowError, match="snapshot_changed"):
            confirm_local_import(db, plan=plan, max_concurrency=2)

    file_path.write_bytes(_png_bytes(8))
    with SessionLocal() as db:
        plan = build_local_import_preview(
            db, item_id=item_id, source_id=None, path="/media/changed.png"
        ).plan
        task = confirm_local_import(db, plan=plan, max_concurrency=2)[0]

        def broken_session():
            raise OSError("private database path")

        with pytest.raises(OSError):
            execute_local_task(
                db,
                task_id=task.id,
                max_concurrency=2,
                independent_session_factory=broken_session,
            )
        db.expire_all()
        final = db.get(OperationTask, task.id)
        assert final.state == "outcome_unknown"
        assert final.error_detail is None


def test_execution_snapshot_change_is_failed_and_retryable() -> None:
    item_id = _item()
    file_path = _media_file("retry.png", red=11)
    with SessionLocal() as db:
        plan = build_local_import_preview(
            db, item_id=item_id, source_id=None, path="/media/retry.png"
        ).plan
        task = confirm_local_import(db, plan=plan, max_concurrency=2)[0]
        file_path.write_bytes(_png_bytes(12))
        with pytest.raises(LocalWorkflowError, match="snapshot_changed"):
            execute_local_task(db, task_id=task.id, max_concurrency=2)
        db.expire_all()
        failed = db.get(OperationTask, task.id)
        assert failed.state == "failed"
        assert failed.error_code == "snapshot_changed"
        assert effective_task_state(failed) == "retryable"
        retried = PersistentTaskService(db).retry(
            failed.id, expected_version=failed.version
        )
        assert retried.state == "queued"


def test_confirm_independent_session_failure_blocks_created_task() -> None:
    item_id = _item()
    _media_file("confirm-failure.png", red=13)
    with SessionLocal() as db:
        plan = build_local_import_preview(
            db,
            item_id=item_id,
            source_id=None,
            path="/media/confirm-failure.png",
        ).plan

        def broken_session():
            raise OSError("private path")

        with pytest.raises(LocalWorkflowError, match="confirmation_unverified"):
            confirm_local_import(
                db,
                plan=plan,
                max_concurrency=2,
                independent_session_factory=broken_session,
            )
        task = db.scalar(
            select(OperationTask).where(
                OperationTask.relative_target == "confirm-failure.png"
            )
        )
        assert task.state == "blocked"
        assert task.error_code == "confirmation_unverified"
        assert task.error_detail is None


def test_index_recovery_tasks_restart_projection_and_real_execution() -> None:
    _media_file("index.png", red=9)
    with SessionLocal() as db:
        index_task = create_index_task(db, max_concurrency=2)
        assert execute_local_task(
            db, task_id=index_task.id, max_concurrency=2
        ).state == "succeeded"
        recovery = create_recovery_task(db, max_concurrency=2)
        assert execute_local_task(
            db, task_id=recovery.id, max_concurrency=2
        ).stage == "durable_verified"
        interrupted, _ = PersistentTaskService(db).create(
            task_type=TaskType.METADATA_UPDATE,
            intent_key="phase8:restart-projection",
            initial_state=TaskState.QUEUED,
            provider_key="local_index",
        )
        interrupted = PersistentTaskService(db).transition(
            interrupted.id,
            TaskState.RUNNING,
            expected_version=interrupted.version,
            event_type="start_requested",
        )
        db.commit()
        PersistentTaskService(db).recover_interrupted()
        db.commit()
        db.refresh(interrupted)
        assert effective_task_state(interrupted) == "interrupted"


def test_proxy_pool_is_visible_but_never_misreported_supported() -> None:
    statuses = {row["name"]: row for row in egress_profile_statuses()}
    assert statuses["default"]["supported"] is True
    assert statuses["direct"]["supported"] is True
    assert statuses["proxy_pool"] == {
        "name": "proxy_pool",
        "supported": False,
        "error_code": "egress_profile_unavailable",
    }
    with SessionLocal() as db:
        registry = ProviderRuntimeRegistry(db)
        registry.sync_known_states()
        db.commit()
        provider = registry.get("zuidapi_vod")
        with pytest.raises(ProviderRuntimeError) as error:
            registry.save_configuration(
                "zuidapi_vod",
                egress_profile="proxy_pool",
                expected_version=provider.optimistic_version,
            )
        assert error.value.code is ProviderRuntimeErrorCode.INVALID_EGRESS_PROFILE


def test_local_workflow_web_preview_confirm_start_and_diagnostics(
    auth_client,
) -> None:
    item_id = _item()
    _media_file("web.png", red=10)
    preview = auth_client.post(
        f"/items/{item_id}/local-media/preview",
        data={
            "media_path": "/media/web.png",
            "import_mode": "file",
            "source_id": "",
        },
    )
    assert preview.status_code == 200
    assert "/home/" not in preview.text and "/root/" not in preview.text
    marker = 'name="token" value="'
    token = preview.text.split(marker, 1)[1].split('"', 1)[0]
    confirmed = auth_client.post(
        "/items/local-media/confirm",
        data={"token": token, "confirmation": "confirm"},
        follow_redirects=False,
    )
    assert confirmed.status_code == 303
    task_id = int(confirmed.headers["location"].removeprefix("/tasks/"))
    started = auth_client.post(
        f"/tasks/{task_id}/start", follow_redirects=False
    )
    assert started.status_code == 303
    detail = auth_client.get(f"/tasks/{task_id}")
    item = auth_client.get(f"/items/{item_id}")
    report = auth_client.get("/api/diagnostics/report")
    assert "durable_verified" in detail.text
    assert "web.png" in item.text
    assert report.status_code == 200
    payload = report.json()["report"]
    assert payload["application_version"] == "1.7.0"
    assert payload["media_index"]["linked_local_assets"] == 1
    assert payload["egress"]["network_probe_on_get"] is False
    assert "/home/" not in report.text and "token" not in report.text.casefold()
    with SessionLocal() as db:
        asset_id = db.scalar(select(ItemLocalAsset.id))
    hls = auth_client.post(
        "/api/playback/hls/inspect",
        json={
            "text": "#EXTM3U\n#EXTINF:1.0,\nsegment.ts\n",
            "base_url": "https://local.example.invalid/list.m3u8",
            "approved_hosts": ["local.example.invalid"],
            "local_asset_id": asset_id,
        },
    )
    assert hls.status_code == 200
    association = hls.json()["local_media_association"]
    assert association["found"] is True
    assert association["asset_id"] == asset_id
    assert "relative_path" not in association


def test_atomic_upload_space_failure_leaves_no_temp_or_final(
    auth_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_space(_stream: object) -> None:
        raise OSError(errno.ENOSPC, "device full with private path")

    monkeypatch.setattr(local_media, "_sync_temporary_stream", no_space)
    response = auth_client.post(
        "/media-library/upload",
        files={"files": ("space.png", _png_bytes(14), "image/png")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    library = local_media.LOCAL_MEDIA_ROOT / "library"
    assert not tuple(library.glob(".upload-*.tmp"))
    assert not tuple(library.glob("*.png"))
