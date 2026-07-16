from __future__ import annotations

import multiprocessing
import os
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Item, MediaIndexState
from app.services import local_media, media_operation_lock, media_write_coordination
from app.services.media_index import (
    MediaIndexError,
    get_media_index_status,
    load_preferred_media_snapshot,
    refresh_media_index,
)
from app.services.media_operation_lock import MediaOperationLockError
from app.services.media_write_coordination import (
    MediaFilesystemOutcome,
    MediaIndexCoordinationStatus,
    classify_alias_result,
    classify_batch_result,
    classify_rename_result,
    coordinate_media_mutation,
    synchronize_media_index_after_mutation,
)


GIF_BYTES = b"GIF89a\x01\x00\x01\x00;"


def _hold_process_lock(
    directory: str,
    ready: multiprocessing.synchronize.Event,
    release: multiprocessing.synchronize.Event,
) -> None:
    from app.services import media_operation_lock as process_lock

    process_lock.MEDIA_OPERATION_LOCK_DIRECTORY = Path(directory)
    with process_lock.media_operation_lock(timeout_seconds=1.0):
        ready.set()
        release.wait(5)


def _valid_index(media_root: Path) -> None:
    media_root.mkdir(mode=0o700, exist_ok=True)
    (media_root / "indexed.gif").write_bytes(GIF_BYTES)
    with SessionLocal() as db:
        refresh_media_index(db, full=True)
        assert get_media_index_status(db).usable is True


def test_media_operation_lock_is_regular_private_and_cross_process(
    tmp_path: Path,
) -> None:
    lock_path = media_operation_lock.media_operation_lock_path()
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_process_lock,
        args=(str(lock_path.parent), ready, release),
    )
    process.start()
    try:
        assert ready.wait(5)
        with pytest.raises(MediaOperationLockError) as captured:
            with media_operation_lock.media_operation_lock(timeout_seconds=0.05):
                raise AssertionError("contended lock entered")
        assert captured.value.code == "media_busy"
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)
    assert process.exitcode == 0
    lock_stat = lock_path.stat(follow_symlinks=False)
    assert stat.S_ISREG(lock_stat.st_mode)
    assert stat.S_IMODE(lock_stat.st_mode) == 0o600
    assert lock_stat.st_uid == os.geteuid()


@pytest.mark.parametrize("object_kind", ["symlink", "directory", "fifo"])
def test_media_operation_lock_rejects_unsafe_objects(
    tmp_path: Path,
    object_kind: str,
) -> None:
    lock_path = media_operation_lock.media_operation_lock_path()
    if object_kind == "symlink":
        target = tmp_path / "outside-lock"
        target.write_text("outside", encoding="ascii")
        lock_path.symlink_to(target)
    elif object_kind == "directory":
        lock_path.mkdir()
    else:
        os.mkfifo(lock_path, mode=0o600)

    with pytest.raises(MediaOperationLockError) as captured:
        with media_operation_lock.media_operation_lock(timeout_seconds=0):
            raise AssertionError("unsafe lock entered")
    assert captured.value.code == "media_lock_unsafe"


def test_media_operation_lock_detects_object_replacement_before_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = media_operation_lock.media_operation_lock_path()
    opened = threading.Event()
    original_open = media_operation_lock._open_lock_objects

    with media_operation_lock.media_operation_lock(timeout_seconds=1.0):
        def recording_open() -> tuple[object, ...]:
            result = original_open()
            opened.set()
            return result

        monkeypatch.setattr(
            media_operation_lock,
            "_open_lock_objects",
            recording_open,
        )
        result: dict[str, str] = {}

        def wait_for_lock() -> None:
            try:
                with media_operation_lock.media_operation_lock(timeout_seconds=1.0):
                    result["code"] = "entered"
            except MediaOperationLockError as exc:
                result["code"] = exc.code

        waiter = threading.Thread(target=wait_for_lock)
        waiter.start()
        assert opened.wait(2)
        lock_path.unlink()
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
    waiter.join(2)
    assert not waiter.is_alive()
    assert result == {"code": "media_lock_changed"}


def test_lock_replacement_after_media_change_invalidates_without_guessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media_root = local_media.LOCAL_MEDIA_ROOT
    _valid_index(media_root)
    lock_path = media_operation_lock.media_operation_lock_path()
    refresh_calls = 0

    def unexpected_refresh(*_args: object, **_kwargs: object) -> None:
        nonlocal refresh_calls
        refresh_calls += 1

    monkeypatch.setattr(
        media_write_coordination,
        "refresh_media_index",
        unexpected_refresh,
    )

    def replace_lock_after_change() -> str:
        (media_root / "changed.gif").write_bytes(GIF_BYTES)
        lock_path.unlink()
        replacement = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.close(replacement)
        return "business-result"

    with SessionLocal() as db:
        coordinated = coordinate_media_mutation(
            db,
            source="post_upload",
            operation=replace_lock_after_change,
            classify_result=lambda _result: (
                MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN
            ),
            classify_error=lambda _error: (
                MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
            ),
        )
        state = db.get(MediaIndexState, 1)
        assert state is not None
        assert state.valid is False
        assert state.stale_reason == "filesystem_outcome_unknown"
    assert coordinated.result == "business-result"
    assert coordinated.outcome == MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    assert coordinated.index.status == MediaIndexCoordinationStatus.INVALIDATED
    assert refresh_calls == 0


def test_lock_replacement_without_media_change_preserves_result_and_invalidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _valid_index(local_media.LOCAL_MEDIA_ROOT)
    lock_path = media_operation_lock.media_operation_lock_path()
    refresh_calls = 0

    def unexpected_refresh(*_args: object, **_kwargs: object) -> None:
        nonlocal refresh_calls
        refresh_calls += 1

    monkeypatch.setattr(
        media_write_coordination,
        "refresh_media_index",
        unexpected_refresh,
    )

    def replace_lock() -> str:
        lock_path.unlink()
        replacement = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.close(replacement)
        return "business-result"

    with SessionLocal() as db:
        coordinated = coordinate_media_mutation(
            db,
            source="post_cleanup",
            operation=replace_lock,
            classify_result=lambda _result: (
                MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE
            ),
            classify_error=lambda _error: (
                MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
            ),
        )
        state = db.get(MediaIndexState, 1)
        assert state is not None
        assert state.valid is False
        assert state.stale_reason == "filesystem_outcome_unknown"
    assert coordinated.result == "business-result"
    assert coordinated.outcome == MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    assert coordinated.index.status == MediaIndexCoordinationStatus.INVALIDATED
    assert refresh_calls == 0


def test_two_coordinated_media_writes_do_not_overlap() -> None:
    active = 0
    maximum_active = 0
    state_lock = threading.Lock()

    def run_operation(label: str) -> str:
        nonlocal active, maximum_active
        with SessionLocal() as db:
            def operation() -> str:
                nonlocal active, maximum_active
                with state_lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                time.sleep(0.08)
                with state_lock:
                    active -= 1
                return label

            coordinated = coordinate_media_mutation(
                db,
                source="post_cleanup",
                operation=operation,
                classify_result=lambda result: MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE,
                classify_error=lambda error: MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN,
            )
            return coordinated.result

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run_operation, "first")
        second = executor.submit(run_operation, "second")
        values = sorted((first.result(), second.result()))
    assert values == ["first", "second"]
    assert maximum_active == 1


def test_manual_scan_and_media_write_share_the_same_lock() -> None:
    scan_entered = threading.Event()
    release_scan = threading.Event()
    write_entered = threading.Event()

    def manual_scan() -> None:
        with media_operation_lock.media_operation_lock():
            scan_entered.set()
            assert release_scan.wait(2)

    def media_write() -> None:
        with SessionLocal() as db:
            coordinate_media_mutation(
                db,
                source="post_upload",
                operation=lambda: write_entered.set(),
                classify_result=lambda result: MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE,
                classify_error=lambda error: MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN,
            )

    scan_thread = threading.Thread(target=manual_scan)
    write_thread = threading.Thread(target=media_write)
    scan_thread.start()
    assert scan_entered.wait(2)
    write_thread.start()
    time.sleep(0.08)
    assert not write_entered.is_set()
    release_scan.set()
    scan_thread.join(2)
    write_thread.join(2)
    assert not scan_thread.is_alive()
    assert not write_thread.is_alive()
    assert write_entered.is_set()


def test_outcome_classifiers_cover_known_partial_unknown_and_no_change() -> None:
    class Value:
        pass

    rename = Value()
    rename.warning_code = None
    rename.source_removed = True
    assert classify_rename_result(rename) == MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN
    rename.source_removed = False
    assert (
        classify_rename_result(rename)
        == MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN
    )
    rename.warning_code = "commit_outcome_unknown"
    assert classify_rename_result(rename) == MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN

    success = Value()
    success.status = "success"
    success.code = None
    failed = Value()
    failed.status = "failed"
    failed.code = "stale_preview"
    batch = Value()
    batch.items = (success, failed)
    assert (
        classify_batch_result(batch)
        == MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN
    )
    batch.items = (failed,)
    assert classify_batch_result(batch) == MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE
    failed.code = "unexpected_failure"
    assert classify_batch_result(batch) == MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN

    alias = Value()
    alias.database_outcome = "committed"
    alias.paths = ()
    assert classify_alias_result(alias) == MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE
    alias.database_outcome = "unknown"
    assert classify_alias_result(alias) == MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN


def test_known_and_partial_changes_refresh_once_but_unknown_only_invalidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def record_refresh(db: object, *, full: bool, refresh_source: str) -> None:
        del db
        assert full is False
        calls.append(("refresh", refresh_source))

    def record_invalidate(db: object, *, reason: str) -> None:
        del db
        calls.append(("invalidate", reason))

    monkeypatch.setattr(media_write_coordination, "refresh_media_index", record_refresh)
    monkeypatch.setattr(media_write_coordination, "invalidate_media_index", record_invalidate)
    with SessionLocal() as db:
        known = synchronize_media_index_after_mutation(
            db,
            outcome=MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN,
            source="post_upload",
        )
        partial = synchronize_media_index_after_mutation(
            db,
            outcome=MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN,
            source="post_batch",
        )
        unknown = synchronize_media_index_after_mutation(
            db,
            outcome=MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN,
            source="post_rename",
        )
        unchanged = synchronize_media_index_after_mutation(
            db,
            outcome=MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE,
            source="post_cleanup",
        )
    assert known.status == MediaIndexCoordinationStatus.SYNCHRONIZED
    assert partial.status == MediaIndexCoordinationStatus.SYNCHRONIZED
    assert unknown.status == MediaIndexCoordinationStatus.INVALIDATED
    assert unchanged.status == MediaIndexCoordinationStatus.NOT_NEEDED
    assert calls == [
        ("refresh", "post_upload"),
        ("refresh", "post_batch"),
        ("invalidate", "filesystem_outcome_unknown"),
    ]


def test_refresh_starts_only_after_business_transaction_is_committed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations: list[tuple[bool, tuple[str, ...]]] = []

    with SessionLocal() as db:
        def operation() -> str:
            db.add(Item(title="Committed before refresh"))
            db.commit()
            return "committed"

        def inspect_refresh(
            index_db: object,
            *,
            full: bool,
            refresh_source: str,
        ) -> None:
            assert full is False
            assert refresh_source == "post_upload"
            with SessionLocal() as verifier:
                titles = tuple(row.title for row in verifier.query(Item).all())
            observations.append((bool(index_db.in_transaction()), titles))

        monkeypatch.setattr(
            media_write_coordination,
            "refresh_media_index",
            inspect_refresh,
        )
        coordinated = coordinate_media_mutation(
            db,
            source="post_upload",
            operation=operation,
            classify_result=lambda _result: (
                MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN
            ),
            classify_error=lambda _error: (
                MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
            ),
        )

    assert coordinated.result == "committed"
    assert observations == [(False, ("Committed before refresh",))]


def test_post_mutation_refresh_failure_invalidates_without_rolling_back_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media_root = local_media.LOCAL_MEDIA_ROOT
    _valid_index(media_root)
    completed = {"value": False}

    def operation() -> str:
        completed["value"] = True
        return "business-result"

    def fail_refresh(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise MediaIndexError("scan_failed")

    monkeypatch.setattr(media_write_coordination, "refresh_media_index", fail_refresh)
    with SessionLocal() as db:
        coordinated = coordinate_media_mutation(
            db,
            source="post_cleanup",
            operation=operation,
            classify_result=lambda result: MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN,
            classify_error=lambda error: MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN,
        )
        state = db.get(MediaIndexState, 1)
        assert state is not None
        assert state.valid is False
        assert state.stale_reason == "post_mutation_refresh_failed"
    assert completed["value"] is True
    assert coordinated.result == "business-result"
    assert (
        coordinated.index.status
        == MediaIndexCoordinationStatus.POST_MUTATION_REFRESH_FAILED
    )


def test_upload_refresh_failure_keeps_file_and_read_pages_fall_back(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media_root = local_media.LOCAL_MEDIA_ROOT
    _valid_index(media_root)

    def fail_refresh(*_args: object, **_kwargs: object) -> None:
        raise MediaIndexError("scan_failed")

    monkeypatch.setattr(
        media_write_coordination,
        "refresh_media_index",
        fail_refresh,
    )
    response = auth_client.post(
        "/media-library/upload",
        files={"files": ("new.gif", GIF_BYTES[:-1] + b"x;", "image/gif")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "写后索引刷新失败" in response.text
    with SessionLocal() as db:
        status = get_media_index_status(db)
        assert status.usable is False
        assert status.stale_reason == "post_mutation_refresh_failed"
        fallback = load_preferred_media_snapshot(db)
        assert fallback.source == "filesystem"
        assert len(fallback.scan.entries) == 2
        assert {entry.media_path for entry in fallback.scan.entries} != {
            "/media/indexed.gif"
        }


def test_lock_timeout_stops_upload_and_manual_scan_before_changes(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media_root = local_media.LOCAL_MEDIA_ROOT
    lock_path = media_operation_lock.media_operation_lock_path()
    with SessionLocal() as db:
        before_status = get_media_index_status(db)
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_process_lock,
        args=(str(lock_path.parent), ready, release),
    )
    process.start()
    try:
        assert ready.wait(5)
        monkeypatch.setattr(
            media_operation_lock,
            "MEDIA_OPERATION_LOCK_TIMEOUT_SECONDS",
            0.05,
        )
        upload = auth_client.post(
            "/media-library/upload",
            files={"files": ("blocked.gif", GIF_BYTES, "image/gif")},
            follow_redirects=True,
        )
        scan = auth_client.post(
            "/media-library/index/refresh",
            follow_redirects=True,
        )
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)

    assert process.exitcode == 0
    assert upload.status_code == scan.status_code == 200
    assert "另一个媒体写入或扫描操作正在执行" in upload.text
    assert "另一个媒体写入或扫描操作正在执行" in scan.text
    assert not media_root.exists()
    with SessionLocal() as db:
        assert get_media_index_status(db) == before_status
        assert db.query(Item).count() == 0


def test_upload_refreshes_index_and_duplicate_upload_does_not_rescan(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = auth_client.post(
        "/media-library/upload",
        files={"files": ("first.gif", GIF_BYTES, "image/gif")},
        follow_redirects=True,
    )
    assert first.status_code == 200
    with SessionLocal() as db:
        snapshot = load_preferred_media_snapshot(db)
        assert snapshot.source == "index"
        assert len(snapshot.scan.entries) == 1
        assert snapshot.status.last_refresh_source == "post_upload"

    refresh_calls = 0
    original_refresh = media_write_coordination.refresh_media_index

    def counted_refresh(*args: object, **kwargs: object) -> object:
        nonlocal refresh_calls
        refresh_calls += 1
        return original_refresh(*args, **kwargs)

    monkeypatch.setattr(
        media_write_coordination,
        "refresh_media_index",
        counted_refresh,
    )
    second = auth_client.post(
        "/media-library/upload",
        files={"files": ("same.gif", GIF_BYTES, "image/gif")},
        follow_redirects=True,
    )
    assert second.status_code == 200
    assert refresh_calls == 0


def test_get_does_not_create_media_lock_and_pure_reference_change_does_not_scan(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = media_operation_lock.media_operation_lock_path()
    assert not lock_path.exists()
    page = auth_client.get("/media-library/index")
    assert page.status_code == 200
    assert not lock_path.exists()

    media_root = local_media.LOCAL_MEDIA_ROOT
    media_root.mkdir(mode=0o700)
    media_file = media_root / "cover.gif"
    media_file.write_bytes(GIF_BYTES)
    with SessionLocal() as db:
        item = Item(title="Reference only")
        db.add(item)
        db.commit()
        item_id = item.id

    def unexpected_scan(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("pure reference change triggered index refresh")

    monkeypatch.setattr(
        media_write_coordination,
        "refresh_media_index",
        unexpected_scan,
    )
    response = auth_client.post(
        "/media-library/set-item-cover",
        data={"item_id": item_id, "media_path": "/media/cover.gif"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path == "/media/cover.gif"
