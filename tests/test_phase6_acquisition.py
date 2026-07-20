from __future__ import annotations

import hashlib
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.acquisition import (
    AcquisitionPackage,
    AcquisitionRegistry,
    AssetDownloadDescriptor,
    DownloadOpenResult,
    DownloadServiceError,
)
from app.acquisition.downloader import SafeDownloadExecutor, cleanup_stale_download_temps
from app.acquisition.service import (
    build_download_preview,
    confirm_download_plan,
    discover_assets,
    sign_download_plan,
    validate_relative_target,
    verify_download_token,
)
from app.database import SessionLocal
from app.models import DiscoveredAssetFact, DownloadTaskFact, Item, ItemLocalAsset, ItemSource, OperationTask
from app.services import local_media
from app.source_adapters.contracts import SourceAssetKind
from app.tasks import PersistentTaskService, TaskState


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"synthetic-phase-six-image"


class SyntheticAcquisitionAdapter:
    provider_key = "synthetic"

    def __init__(self, payload: bytes = PNG_BYTES) -> None:
        self.payload = payload
        self.list_calls = 0
        self.open_calls = 0
        self.last_offset = -1

    def descriptor(self, asset_id: str = "cover-1", filename: str = "cover.png") -> AssetDownloadDescriptor:
        return AssetDownloadDescriptor(
            provider_key=self.provider_key,
            external_id="item-1",
            asset_id=asset_id,
            kind=SourceAssetKind.COVER,
            display_name="Synthetic cover",
            suggested_filename=filename,
            mime_type="image/png",
            expected_bytes=len(self.payload),
            expected_sha256=hashlib.sha256(self.payload).hexdigest(),
            resume_supported=True,
        )

    async def list_assets(self, external_id: str) -> tuple[AssetDownloadDescriptor, ...]:
        assert external_id == "item-1"
        self.list_calls += 1
        return (self.descriptor(),)

    async def _chunks(self, offset: int):
        remaining = self.payload[offset:]
        for start in range(0, len(remaining), 8):
            yield remaining[start : start + 8]

    async def open_asset(
        self,
        external_id: str,
        asset_id: str,
        *,
        offset: int,
        timeout_seconds: int,
    ) -> DownloadOpenResult:
        assert external_id == "item-1"
        assert asset_id.startswith("cover-")
        assert timeout_seconds == 30
        self.open_calls += 1
        self.last_offset = offset
        return DownloadOpenResult(
            chunks=self._chunks(offset),
            status_code=206 if offset else 200,
            mime_type="image/png",
            content_length=len(self.payload) - offset,
            range_start=offset if offset else None,
            range_end=len(self.payload) - 1 if offset else None,
            range_total=len(self.payload) if offset else None,
        )


def _registry(adapter: SyntheticAcquisitionAdapter) -> AcquisitionRegistry:
    return AcquisitionRegistry(
        (
            AcquisitionPackage(
                provider_key="synthetic",
                adapter=adapter,
                approved_asset_list=True,
                approved_download=True,
            ),
        )
    )


def _source() -> tuple[int, int]:
    with SessionLocal() as db:
        item = Item(title="Local title", summary="Local summary")
        db.add(item)
        db.flush()
        source = ItemSource(
            item_id=item.id,
            url="https://synthetic.invalid/item-1",
            normalized_url="https://synthetic.invalid/item-1",
            title="Source title",
            provider_key="synthetic",
            external_id="item-1",
        )
        db.add(source)
        db.commit()
        return item.id, source.id


def test_preview_is_pure_token_is_session_bound_and_confirm_replay_is_single_task() -> None:
    adapter = SyntheticAcquisitionAdapter()
    item_id, source_id = _source()
    with SessionLocal() as db:
        preview = build_download_preview(
            db,
            item_id=item_id,
            source_id=source_id,
            descriptor=adapter.descriptor(),
            relative_target="library/cover.png",
            max_bytes=1_000_000,
        )
        assert preview.confirmable and preview.plan is not None
        assert adapter.list_calls == adapter.open_calls == 0
        assert db.query(OperationTask).count() == 0
        secret = b"s" * 32
        issued = datetime.now(UTC)
        token = sign_download_plan(
            preview.plan,
            secret=secret,
            context="session-a",
            now=issued,
        )
        plan = verify_download_token(
            token,
            secret=secret,
            context="session-a",
            now=issued,
        )
        with pytest.raises(DownloadServiceError):
            verify_download_token(
                token,
                secret=secret,
                context="session-b",
                now=issued,
            )
        with pytest.raises(DownloadServiceError):
            verify_download_token(
                token,
                secret=secret,
                context="session-a",
                now=issued + timedelta(hours=1),
            )
        task, created = confirm_download_plan(db, plan=plan, max_concurrency=2)
        replay, replay_created = confirm_download_plan(db, plan=plan, max_concurrency=2)
        db.commit()
        assert created and not replay_created and replay.id == task.id
        assert db.query(OperationTask).count() == 1
        assert db.get(DownloadTaskFact, task.id) is not None
        assert adapter.open_calls == 0


@pytest.mark.anyio
async def test_asset_discovery_calls_only_the_synthetic_adapter_once() -> None:
    adapter = SyntheticAcquisitionAdapter()
    item_id, source_id = _source()
    with SessionLocal() as db:
        task = await discover_assets(
            db,
            _registry(adapter),
            item_id=item_id,
            source_id=source_id,
            max_concurrency=2,
        )
        facts = db.query(DiscoveredAssetFact).filter_by(task_id=task.id).all()
        assert task.state == TaskState.SUCCEEDED.value
        assert len(facts) == 1
        assert adapter.list_calls == 1
        assert adapter.open_calls == 0


@pytest.mark.anyio
async def test_safe_download_streams_validates_publishes_links_and_indexes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SyntheticAcquisitionAdapter()
    item_id, source_id = _source()
    media_root = tmp_path / "media"
    (media_root / "library").mkdir(parents=True, mode=0o700)
    temp_root = tmp_path / "download-temp"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_download_preview(
            db,
            item_id=item_id,
            source_id=source_id,
            descriptor=adapter.descriptor(),
            relative_target="library/cover.png",
            max_bytes=1_000_000,
        )
        assert preview.plan is not None
        task, _ = confirm_download_plan(db, plan=preview.plan, max_concurrency=2)
        tasks = PersistentTaskService(db, max_concurrency=2)
        task = tasks.transition(
            task.id,
            TaskState.RUNNING,
            expected_version=task.version,
            event_type="start_requested",
        )
        task = tasks.acquire_lease(
            task.id,
            owner="synthetic-runner",
            expected_version=task.version,
        )
        generation = task.lease_generation
        db.commit()
        executor = SafeDownloadExecutor(
            db,
            _registry(adapter),
            media_root=media_root,
            temp_root=temp_root,
            chunk_bytes=4096,
            timeout_seconds=30,
            max_concurrency=2,
        )
        result = await executor.execute(
            task.id,
            lease_owner="synthetic-runner",
            lease_generation=generation,
        )
        assert result.sha256 == hashlib.sha256(PNG_BYTES).hexdigest()
        assert (media_root / "library" / "cover.png").read_bytes() == PNG_BYTES
        assert tuple(temp_root.iterdir()) == ()
        linked = db.query(ItemLocalAsset).one()
        assert linked.task_id == task.id
        finished = db.get(OperationTask, task.id)
        assert finished is not None
        assert finished.state == TaskState.SUCCEEDED.value
        assert finished.stage == "durable_verified"
        assert adapter.open_calls == 1


def test_target_validation_rejects_traversal_absolute_separator_and_nul() -> None:
    for value in ("../escape.png", "/absolute.png", "library\\file.png", "library/\x00file.png"):
        with pytest.raises(DownloadServiceError):
            validate_relative_target(value)


def test_production_acquisition_registry_is_empty() -> None:
    from app.acquisition.registry import PRODUCTION_ACQUISITION_PACKAGES

    assert PRODUCTION_ACQUISITION_PACKAGES == ()


@pytest.mark.anyio
async def test_existing_target_is_never_overwritten_and_temp_is_cleaned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SyntheticAcquisitionAdapter()
    item_id, source_id = _source()
    media_root = tmp_path / "media"
    library = media_root / "library"
    library.mkdir(parents=True, mode=0o700)
    target = library / "cover.png"
    target.write_bytes(b"preexisting")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    temp_root = tmp_path / "temp"
    with SessionLocal() as db:
        preview = build_download_preview(
            db,
            item_id=item_id,
            source_id=source_id,
            descriptor=adapter.descriptor(asset_id="cover-existing"),
            relative_target="library/cover.png",
            max_bytes=1_000_000,
        )
        assert preview.plan is not None
        task, _ = confirm_download_plan(db, plan=preview.plan, max_concurrency=2)
        tasks = PersistentTaskService(db, max_concurrency=2)
        task = tasks.transition(task.id, TaskState.RUNNING, expected_version=task.version, event_type="start_requested")
        task = tasks.acquire_lease(task.id, owner="existing-target", expected_version=task.version)
        generation = task.lease_generation
        db.commit()
        executor = SafeDownloadExecutor(
            db,
            _registry(adapter),
            media_root=media_root,
            temp_root=temp_root,
            chunk_bytes=4096,
            timeout_seconds=30,
            max_concurrency=2,
        )
        with pytest.raises(DownloadServiceError) as error:
            await executor.execute(task.id, lease_owner="existing-target", lease_generation=generation)
        assert error.value.code.value == "target_exists"
        assert target.read_bytes() == b"preexisting"
        assert tuple(temp_root.iterdir()) == ()
        assert db.query(ItemLocalAsset).count() == 0


class PausingAdapter(SyntheticAcquisitionAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.task_id: int | None = None
        self.paused_once = False

    async def _chunks(self, offset: int):
        remaining = self.payload[offset:]
        if offset == 0 and not self.paused_once:
            yield remaining[:8]
            assert self.task_id is not None
            with SessionLocal() as control:
                service = PersistentTaskService(control, max_concurrency=2)
                task = service.get(self.task_id)
                service.transition(
                    task.id,
                    TaskState.PAUSED,
                    expected_version=task.version,
                    event_type="pause_requested",
                )
                control.commit()
            self.paused_once = True
            yield remaining[8:16]
            return
        for start in range(0, len(remaining), 8):
            yield remaining[start : start + 8]


@pytest.mark.anyio
async def test_pause_preserves_verified_temp_identity_and_resume_requires_exact_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = PausingAdapter()
    item_id, source_id = _source()
    media_root = tmp_path / "media"
    (media_root / "library").mkdir(parents=True, mode=0o700)
    temp_root = tmp_path / "temp"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_download_preview(
            db,
            item_id=item_id,
            source_id=source_id,
            descriptor=adapter.descriptor(asset_id="cover-resume", filename="resume.png"),
            relative_target="library/resume.png",
            max_bytes=1_000_000,
        )
        task, _ = confirm_download_plan(db, plan=preview.plan, max_concurrency=2)  # type: ignore[arg-type]
        adapter.task_id = task.id
        tasks = PersistentTaskService(db, max_concurrency=2)
        task = tasks.transition(task.id, TaskState.RUNNING, expected_version=task.version, event_type="start_requested")
        task = tasks.acquire_lease(task.id, owner="resume-one", expected_version=task.version)
        first_generation = task.lease_generation
        db.commit()
        executor = SafeDownloadExecutor(
            db,
            _registry(adapter),
            media_root=media_root,
            temp_root=temp_root,
            chunk_bytes=4096,
            timeout_seconds=30,
            max_concurrency=2,
        )
        with pytest.raises(DownloadServiceError) as paused:
            await executor.execute(task.id, lease_owner="resume-one", lease_generation=first_generation)
        assert paused.value.code.value == "paused"
        db.expire_all()
        task = tasks.get(task.id)
        fact = db.get(DownloadTaskFact, task.id)
        assert task.state == TaskState.PAUSED.value
        assert fact is not None and fact.resume_offset == 8 and fact.temp_name is not None

        task = tasks.transition(task.id, TaskState.QUEUED, expected_version=task.version, event_type="resume_requested")
        task = tasks.transition(task.id, TaskState.RUNNING, expected_version=task.version, event_type="start_requested")
        task = tasks.acquire_lease(task.id, owner="resume-two", expected_version=task.version)
        second_generation = task.lease_generation
        db.commit()
        result = await executor.execute(task.id, lease_owner="resume-two", lease_generation=second_generation)
        assert result.size_bytes == len(PNG_BYTES)
        assert adapter.last_offset == 8
        assert (media_root / "library" / "resume.png").read_bytes() == PNG_BYTES


def test_symlinked_target_parent_is_rejected_by_directory_descriptor(
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    outside = tmp_path / "outside"
    media_root.mkdir()
    outside.mkdir()
    (media_root / "library").symlink_to(outside, target_is_directory=True)
    root_fd = None
    try:
        root_fd = __import__("os").open(media_root, __import__("os").O_RDONLY | __import__("os").O_DIRECTORY)
        from app.acquisition.downloader import _open_target_parent

        with pytest.raises(OSError):
            _open_target_parent(root_fd, "library/file.png")
    finally:
        if root_fd is not None:
            __import__("os").close(root_fd)


def test_temp_retention_cleanup_ignores_referenced_recent_and_symlink_entries(
    tmp_path: Path,
) -> None:
    temp_root = tmp_path / "temp"
    temp_root.mkdir(mode=0o700)
    stale = temp_root / (".download-" + "a" * 48 + ".tmp")
    referenced = temp_root / (".download-" + "b" * 48 + ".tmp")
    recent = temp_root / (".download-" + "c" * 48 + ".tmp")
    outside = tmp_path / "outside"
    stale.write_bytes(b"stale")
    referenced.write_bytes(b"referenced")
    recent.write_bytes(b"recent")
    outside.write_bytes(b"outside")
    for path in (stale, referenced, recent):
        path.chmod(0o600)
    now = time.time()
    os.utime(stale, (now - 48 * 3_600, now - 48 * 3_600))
    os.utime(referenced, (now - 48 * 3_600, now - 48 * 3_600))
    (temp_root / (".download-" + "d" * 48 + ".tmp")).symlink_to(outside)
    with SessionLocal() as db:
        task = OperationTask(
            task_type="asset_download",
            state="paused",
            intent_key="test:referenced-temp",
            stage="downloading",
        )
        db.add(task)
        db.flush()
        db.add(
            DownloadTaskFact(
                task_id=task.id,
                asset_id="cover-temp",
                asset_kind="cover",
                suggested_name="cover.png",
                max_bytes=1_000_000,
                temp_name=referenced.name,
            )
        )
        db.commit()
        removed = cleanup_stale_download_temps(
            db,
            temp_root=temp_root,
            retention_hours=24,
            now_timestamp=now,
        )
    assert removed == 1
    assert not stale.exists()
    assert referenced.exists() and recent.exists() and outside.read_bytes() == b"outside"
