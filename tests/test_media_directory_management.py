from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.database import SessionLocal
from app.flash import FLASH_SESSION_KEY
from app.models import Creator, Item
from app.routers import pages
from app.services import local_media
from app.services import media_operation_lock
from app.services import media_write_coordination
from app.services import media_directory_management as directory_management
from app.services.media_index import get_media_index_status
from app.services.media_directory_management import (
    MediaDirectoryError,
    build_directory_snapshot,
    execute_directory_mutation,
)
from app.services.media_write_coordination import (
    MediaFilesystemOutcome,
    MediaIndexCoordinationResult,
    MediaIndexCoordinationStatus,
    MediaMutationExecutionError,
    coordinate_media_mutation,
)


def _gif(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"GIF89a\x01\x00\x01\x00" + b"x" + b";")


def _flash_request() -> Request:
    return Request({"type": "http", "session": {}})


def _flash_keys(request: Request) -> list[str]:
    return [message["key"] for message in request.session[FLASH_SESSION_KEY]]


def test_create_rename_and_delete_directory_with_exact_reference_migration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    root.joinpath("library", "source").mkdir(parents=True)
    _gif(root / "library/source/cover.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add_all([
            Item(title="item", cover_path="/media/library/source/cover.gif"),
            Creator(name="creator", type="person", avatar_path="/media/library/source/cover.gif"),
        ])
        db.commit()
        snapshot, token = build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )
        assert snapshot.manifest is not None and snapshot.manifest.clean
        result = execute_directory_mutation(db, token=token, confirmation="rename")
        assert result.outcome == "committed"
        assert (root / "library/renamed/cover.gif").exists()
        assert not (root / "library/source").exists()
        assert db.query(Item).one().cover_path == "/media/library/renamed/cover.gif"
        assert db.query(Creator).one().avatar_path == "/media/library/renamed/cover.gif"

        create_snapshot, create_token = build_directory_snapshot(
            db, operation="create", source_path=None,
            target_parent_path="/media/library", target_basename="empty",
        )
        assert create_snapshot.source_path is None
        execute_directory_mutation(db, token=create_token, confirmation="create")
        assert (root / "library/empty").is_dir()

        delete_snapshot, delete_token = build_directory_snapshot(
            db, operation="delete", source_path="/media/library/empty",
            target_parent_path="/media/library", target_basename="empty",
        )
        assert delete_snapshot.target_exists is False
        execute_directory_mutation(db, token=delete_token, confirmation="delete")
        assert not (root / "library/empty").exists()


def test_directory_snapshot_rejects_tampering_and_nonempty_delete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    _gif(root / "library/source/file.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        _, token = build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )
        with pytest.raises(MediaDirectoryError, match="invalid_snapshot"):
            execute_directory_mutation(db, token=token + "0", confirmation="rename")
        with pytest.raises(MediaDirectoryError, match="confirmation_required"):
            execute_directory_mutation(db, token=token, confirmation="move")
        with pytest.raises(MediaDirectoryError):
            build_directory_snapshot(
                db, operation="delete", source_path="/media/library/source",
                target_parent_path="/media/library", target_basename="source",
            )


def test_directory_create_route_get_is_write_free_and_post_refreshes_once(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    (root / "library").mkdir(parents=True)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(mode=0o700)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    monkeypatch.setattr(media_operation_lock, "MEDIA_OPERATION_LOCK_DIRECTORY", lock_dir)

    preview = auth_client.get(
        "/media-library/directories/create",
        params={"target_parent": "/media/library", "target_basename": "new-dir"},
    )
    assert preview.status_code == 200
    assert not media_operation_lock.media_operation_lock_path().exists()
    token = preview.text.split('name="token" value="', 1)[1].split('"', 1)[0]

    response = auth_client.post(
        "/media-library/directories/create",
        data={"token": token, "confirm": "create"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (root / "library/new-dir").is_dir()
    with SessionLocal() as db:
        assert get_media_index_status(db).last_refresh_source == "post_directory"


def test_directory_move_rejects_descendants_and_existing_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library/source/child").mkdir(parents=True)
    (root / "library/target").mkdir(parents=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        with pytest.raises(MediaDirectoryError, match="invalid_target_directory"):
            build_directory_snapshot(
                db, operation="move", source_path="/media/library/source",
                target_parent_path="/media/library/source/child", target_basename="moved",
            )
        with pytest.raises(MediaDirectoryError, match="target_exists"):
            build_directory_snapshot(
                db, operation="move", source_path="/media/library/source",
                target_parent_path="/media/library", target_basename="target",
            )


@pytest.mark.parametrize(
    "relative_path",
    [
        "library/source/.cleanup-anchor-safe.gif",
        "library/source/.upload-safe.tmp",
        "library/source/.hidden/file.gif",
    ],
)
def test_manifest_rejects_cleanup_residue_and_hidden_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, relative_path: str
) -> None:
    root = tmp_path / "media"
    path = root / relative_path
    if path.suffix == ".gif":
        _gif(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"GIF89a\x01\x00\x01\x00x;")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db, pytest.raises(MediaDirectoryError, match="reserved_directory_entry"):
        build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )


@pytest.mark.parametrize(
    ("constant", "value", "setup", "code"),
    [
        ("MAX_DIRECTORY_MANIFEST_DIRECTORIES", 1, "directory", "directory_count_limit"),
        ("MAX_DIRECTORY_MANIFEST_FILES", 0, "file", "media_file_count_limit"),
        ("MAX_DIRECTORY_MANIFEST_TOTAL_BYTES", 1, "file", "media_total_size_limit"),
        ("MAX_DIRECTORY_MANIFEST_FILE_BYTES", 1, "file", "single_file_size_limit"),
        ("MAX_DIRECTORY_MANIFEST_DEPTH", 0, "directory", "directory_depth_limit"),
    ],
)
def test_manifest_enforces_all_explicit_limits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    constant: str,
    value: int,
    setup: str,
    code: str,
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    if setup == "directory":
        (root / "library/source/child").mkdir()
    else:
        _gif(root / "library/source/file.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    monkeypatch.setattr(directory_management, constant, value)
    with SessionLocal() as db, pytest.raises(MediaDirectoryError, match=code):
        build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )


def test_exact_reference_migration_leaves_same_prefix_outside_subtree_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    _gif(root / "library/source/file.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        inside = Item(title="inside", cover_path="/media/library/source/file.gif")
        outside = Item(title="outside", cover_path="/media/library/source-other/file.gif")
        db.add_all([inside, outside])
        db.commit()
        _, token = build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )
        execute_directory_mutation(db, token=token, confirmation="rename")
        db.refresh(inside)
        db.refresh(outside)
        assert inside.cover_path == "/media/library/renamed/file.gif"
        assert outside.cover_path == "/media/library/source-other/file.gif"


def test_directory_unknown_uses_exact_stale_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library").mkdir(parents=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        with pytest.raises(MediaMutationExecutionError):
            coordinate_media_mutation(
                db,
                source="post_directory",
                operation=lambda: (_ for _ in ()).throw(
                    directory_management.MediaDirectoryOutcomeError(
                        "directory_outcome_unknown", outcome="directory_outcome_unknown"
                    )
                ),
                classify_result=lambda _result: MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN,
                classify_error=lambda _error: MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN,
                classify_invalidation_reason=lambda _error: "directory_outcome_unknown",
            )
        assert get_media_index_status(db).stale_reason == "directory_outcome_unknown"


def test_manifest_rejects_file_replacement_between_lstat_and_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    _gif(root / "library/source/file.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    original_open = directory_management.os.open
    replaced = False

    def replacing_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal replaced
        if path == "file.gif" and not replaced:
            replaced = True
            file_path = root / "library/source/file.gif"
            file_path.unlink()
            _gif(file_path)
            file_path.write_bytes(b"GIF89a\x01\x00\x01\x00changed;")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(directory_management.os, "open", replacing_open)
    with SessionLocal() as db, pytest.raises(MediaDirectoryError, match="file_changed"):
        build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )


def test_manifest_rejects_subdirectory_replacement_between_lstat_and_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    child = root / "library/source/child"
    child.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    original_open = directory_management.os.open
    replaced = False

    def replacing_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal replaced
        if path == "child" and not replaced:
            replaced = True
            child.rmdir()
            child.symlink_to(external, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(directory_management.os, "open", replacing_open)
    with SessionLocal() as db, pytest.raises(MediaDirectoryError, match="directory_unreadable"):
        build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )


def test_begin_immediate_precedes_final_manifest_and_reference_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from sqlalchemy import event
    from app.database import engine

    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    _gif(root / "library/source/file.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    events: list[str] = []

    def observe(_connection: object, _cursor: object, statement: str, *_args: object) -> None:
        normalized = statement.strip().upper()
        if normalized == "BEGIN IMMEDIATE" or normalized.startswith("SELECT"):
            events.append(normalized.split()[0])

    event.listen(engine, "before_cursor_execute", observe)
    try:
        with SessionLocal() as db:
            _, token = build_directory_snapshot(
                db, operation="rename", source_path="/media/library/source",
                target_parent_path="/media/library", target_basename="renamed",
            )
            events.clear()
            execute_directory_mutation(db, token=token, confirmation="rename")
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert "BEGIN" in events
    assert events.index("BEGIN") < events.index("SELECT")


def test_commit_error_is_classified_after_precise_independent_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    _gif(root / "library/source/file.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add(Item(title="item", cover_path="/media/library/source/file.gif"))
        db.commit()
        _, token = build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )
        original_commit = db.commit
        state = {"called": False}

        def commit_then_error() -> None:
            if not state["called"]:
                state["called"] = True
                original_commit()
                raise RuntimeError("commit reported an error")
            original_commit()

        monkeypatch.setattr(db, "commit", commit_then_error)
        result = execute_directory_mutation(db, token=token, confirmation="rename")
        assert result.outcome == "committed_after_error"
        assert result.warning_code == "committed_after_error"
        assert (root / "library/renamed/file.gif").exists()


def test_not_committed_commit_error_safely_rolls_directory_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    _gif(root / "library/source/file.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add(Item(title="item", cover_path="/media/library/source/file.gif"))
        db.commit()
        _, token = build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
        with pytest.raises(
            directory_management.MediaDirectoryOutcomeError,
            match="not_committed_rolled_back",
        ) as captured:
            execute_directory_mutation(db, token=token, confirmation="rename")
        assert captured.value.outcome == "not_committed_rolled_back"
        assert (root / "library/source/file.gif").exists()
        assert not (root / "library/renamed").exists()


def test_rollback_failure_becomes_directory_outcome_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    _gif(root / "library/source/file.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    original_rename = directory_management._rename_noreplace
    calls = 0

    def fail_second_rename(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("rollback failed")
        original_rename(*args, **kwargs)

    monkeypatch.setattr(directory_management, "_rename_noreplace", fail_second_rename)
    with SessionLocal() as db:
        db.add(Item(title="item", cover_path="/media/library/source/file.gif"))
        db.commit()
        _, token = build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
        with pytest.raises(directory_management.MediaDirectoryOutcomeError) as captured:
            execute_directory_mutation(db, token=token, confirmation="rename")
        assert captured.value.outcome == "directory_outcome_unknown"


def test_precise_independent_review_rejects_mixed_and_unexpected_target_references(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    _gif(root / "library/source/a.gif")
    _gif(root / "library/source/b.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        first = Item(title="first", cover_path="/media/library/source/a.gif")
        second = Item(title="second", cover_path="/media/library/source/b.gif")
        unexpected = Item(title="unexpected", cover_path="/media/library/renamed/ghost.gif")
        db.add_all([first, second, unexpected])
        db.commit()
        snapshot, _ = build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )
        (root / "library/source").rename(root / "library/renamed")
        first.cover_path = "/media/library/renamed/a.gif"
        db.commit()
    assert directory_management._independent_outcome(
        snapshot, "/media/library/renamed"
    ) == "directory_outcome_unknown"


def test_independent_session_failure_is_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        snapshot, _ = build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )
    monkeypatch.setattr(
        directory_management,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(RuntimeError("query failed")),
    )
    assert directory_management._independent_outcome(
        snapshot, "/media/library/renamed"
    ) == "directory_outcome_unknown"


@pytest.mark.parametrize("operation", ["create", "delete", "rename"])
def test_fsync_failure_is_partial_known_after_directory_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, operation: str
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    if operation == "rename":
        _gif(root / "library/source/file.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        source = None if operation == "create" else "/media/library/source"
        basename = "created" if operation == "create" else ("source" if operation == "delete" else "renamed")
        snapshot, token = build_directory_snapshot(
            db, operation=operation, source_path=source,
            target_parent_path="/media/library", target_basename=basename,
        )
        del snapshot
        monkeypatch.setattr(
            directory_management.os,
            "fsync",
            lambda _fd: (_ for _ in ()).throw(OSError("sync failed")),
        )
        with pytest.raises(directory_management.MediaDirectoryOutcomeError) as captured:
            execute_directory_mutation(db, token=token, confirmation=operation)
        assert captured.value.outcome == "filesystem_changed_partial_known"


def test_directory_route_lock_timeout_happens_before_any_change(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    (root / "library").mkdir(parents=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = auth_client.get(
        "/media-library/directories/create",
        params={"target_parent": "/media/library", "target_basename": "blocked"},
    )
    token = preview.text.split('name="token" value="', 1)[1].split('"', 1)[0]

    @contextmanager
    def busy_lock() -> object:
        raise media_operation_lock.MediaOperationLockError("media_busy")
        yield

    monkeypatch.setattr(media_write_coordination, "media_operation_lock", busy_lock)
    response = auth_client.post(
        "/media-library/directories/create",
        data={"token": token, "confirm": "create"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert not (root / "library/blocked").exists()


def _create_token(root: Path) -> str:
    with SessionLocal() as db:
        _, token = build_directory_snapshot(
            db, operation="create", source_path=None,
            target_parent_path="/media/library", target_basename="created",
        )
    return token


def test_create_open_failure_after_mkdir_is_partial_known(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library").mkdir(parents=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    token = _create_token(root)
    original_open = directory_management.os.open

    def fail_created_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if path == "created":
            raise OSError("open failed")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(directory_management.os, "open", fail_created_open)
    with SessionLocal() as db, pytest.raises(directory_management.MediaDirectoryOutcomeError) as captured:
        execute_directory_mutation(db, token=token, confirmation="create")
    assert captured.value.outcome == "filesystem_changed_partial_known"
    assert captured.value.code == "created_directory_followup_failed"
    assert (root / "library/created").is_dir()


def test_create_replacement_after_mkdir_is_unknown_and_not_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    target = root / "library/created"
    (root / "library").mkdir(parents=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    token = _create_token(root)
    original_open = directory_management.os.open

    def replace_created(path: object, flags: int, *args: object, **kwargs: object) -> int:
        if path == "created" and target.is_dir():
            target.rmdir()
            target.write_bytes(b"replacement")
            raise OSError("replaced")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(directory_management.os, "open", replace_created)
    with SessionLocal() as db, pytest.raises(directory_management.MediaDirectoryOutcomeError) as captured:
        execute_directory_mutation(db, token=token, confirmation="create")
    assert captured.value.outcome == "directory_outcome_unknown"
    assert target.is_file()


def test_create_identity_recheck_failure_is_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from types import SimpleNamespace

    root = tmp_path / "media"
    (root / "library").mkdir(parents=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    token = _create_token(root)
    original_open = directory_management.os.open
    original_fstat = directory_management.os.fstat
    created_fd: int | None = None

    def record_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal created_fd
        fd = original_open(path, flags, *args, **kwargs)
        if path == "created":
            created_fd = fd
        return fd

    def changed_fstat(fd: int) -> object:
        result = original_fstat(fd)
        if created_fd == fd:
            return SimpleNamespace(st_mode=result.st_mode, st_dev=result.st_dev, st_ino=result.st_ino + 1)
        return result

    monkeypatch.setattr(directory_management.os, "open", record_open)
    monkeypatch.setattr(directory_management.os, "fstat", changed_fstat)
    with SessionLocal() as db, pytest.raises(directory_management.MediaDirectoryOutcomeError) as captured:
        execute_directory_mutation(db, token=token, confirmation="create")
    assert captured.value.outcome == "directory_outcome_unknown"


@pytest.mark.parametrize("commit_mode", ["fail", "commit_then_error", "rollback_then_error"])
def test_delete_post_rmdir_transaction_failures_are_partial_known(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, commit_mode: str
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        _, token = build_directory_snapshot(
            db, operation="delete", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="source",
        )
        original_commit = db.commit
        original_rollback = db.rollback
        if commit_mode == "fail":
            monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
        else:
            def commit_then_error() -> None:
                original_commit()
                raise RuntimeError("commit reported error")
            monkeypatch.setattr(db, "commit", commit_then_error)
        if commit_mode == "rollback_then_error":
            def rollback_then_error() -> None:
                original_rollback()
                raise RuntimeError("rollback failed")
            monkeypatch.setattr(db, "rollback", rollback_then_error)
        with pytest.raises(directory_management.MediaDirectoryOutcomeError) as captured:
            execute_directory_mutation(db, token=token, confirmation="delete")
        assert captured.value.outcome == "filesystem_changed_partial_known"
        assert not (root / "library/source").exists()


def test_delete_independent_query_failure_is_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        _, token = build_directory_snapshot(
            db, operation="delete", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="source",
        )
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
        monkeypatch.setattr(
            directory_management,
            "SessionLocal",
            lambda: (_ for _ in ()).throw(RuntimeError("query failed")),
        )
        with pytest.raises(directory_management.MediaDirectoryOutcomeError) as captured:
            execute_directory_mutation(db, token=token, confirmation="delete")
        assert captured.value.outcome == "directory_outcome_unknown"


def test_rename_rollback_failure_does_not_hide_committed_after_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    (root / "library/source").mkdir(parents=True)
    _gif(root / "library/source/file.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add(Item(title="item", cover_path="/media/library/source/file.gif"))
        db.commit()
        _, token = build_directory_snapshot(
            db, operation="rename", source_path="/media/library/source",
            target_parent_path="/media/library", target_basename="renamed",
        )
        original_commit = db.commit
        def commit_then_error() -> None:
            original_commit()
            raise RuntimeError("commit reported error")
        monkeypatch.setattr(db, "commit", commit_then_error)
        monkeypatch.setattr(db, "rollback", lambda: (_ for _ in ()).throw(RuntimeError("rollback failed")))
        result = execute_directory_mutation(db, token=token, confirmation="rename")
        assert result.outcome == "committed_after_error"


def test_result_path_lock_replacement_uses_directory_reason_and_no_success_flash(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    (root / "library").mkdir(parents=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = auth_client.get(
        "/media-library/directories/create",
        params={"target_parent": "/media/library", "target_basename": "created"},
    )
    token = preview.text.split('name="token" value="', 1)[1].split('"', 1)[0]

    class ChangedHandle:
        def verify(self) -> None:
            raise media_operation_lock.MediaOperationLockError("media_lock_changed")

    @contextmanager
    def changed_lock() -> object:
        yield ChangedHandle()

    monkeypatch.setattr(media_write_coordination, "media_operation_lock", changed_lock)
    response = auth_client.post(
        "/media-library/directories/create",
        data={"token": token, "confirm": "create"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "无法安全判断目录操作结果" in response.text
    assert "媒体目录操作已完成" not in response.text
    with SessionLocal() as db:
        assert get_media_index_status(db).stale_reason == "directory_outcome_unknown"


@pytest.mark.parametrize(
    ("outcome", "index_status", "expected", "forbidden"),
    [
        (
            MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN,
            MediaIndexCoordinationStatus.INVALIDATED,
            [
                "flash.media_directory_outcome_unknown",
                "flash.media_index_filesystem_outcome_unknown",
            ],
            ["flash.media_index_invalidation_failed", "flash.media_directory_success"],
        ),
        (
            MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN,
            MediaIndexCoordinationStatus.INVALIDATION_FAILED,
            [
                "flash.media_directory_outcome_unknown",
                "flash.media_index_invalidation_failed",
            ],
            ["flash.media_index_filesystem_outcome_unknown", "flash.media_directory_success"],
        ),
        (
            MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN,
            MediaIndexCoordinationStatus.SYNCHRONIZED,
            [
                "flash.media_directory_partial_known",
                "flash.media_index_post_mutation_synchronized",
            ],
            ["flash.media_index_post_mutation_refresh_failed", "flash.media_directory_success"],
        ),
        (
            MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN,
            MediaIndexCoordinationStatus.POST_MUTATION_REFRESH_FAILED,
            [
                "flash.media_directory_partial_known",
                "flash.media_index_post_mutation_refresh_failed",
            ],
            ["flash.media_index_post_mutation_synchronized", "flash.media_directory_success"],
        ),
        (
            MediaFilesystemOutcome.FILESYSTEM_CHANGED_PARTIAL_KNOWN,
            MediaIndexCoordinationStatus.INVALIDATION_FAILED,
            [
                "flash.media_directory_partial_known",
                "flash.media_index_invalidation_failed",
            ],
            ["flash.media_index_post_mutation_synchronized", "flash.media_directory_success"],
        ),
        (
            MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN,
            MediaIndexCoordinationStatus.POST_MUTATION_REFRESH_FAILED,
            [
                "flash.media_directory_success",
                "flash.media_index_post_mutation_refresh_failed",
            ],
            ["flash.media_index_post_mutation_synchronized"],
        ),
    ],
)
def test_directory_flash_matches_final_outcome_and_index_status(
    outcome: MediaFilesystemOutcome,
    index_status: MediaIndexCoordinationStatus,
    expected: list[str],
    forbidden: list[str],
) -> None:
    request = _flash_request()
    coordinated = SimpleNamespace(
        outcome=outcome,
        result=SimpleNamespace(outcome="committed"),
        index=MediaIndexCoordinationResult(index_status, "post_directory"),
    )
    pages._directory_coordinated_flash(request, coordinated)
    keys = _flash_keys(request)
    assert keys == expected
    assert not set(keys).intersection(forbidden)


def test_exception_upgraded_from_no_change_uses_directory_unknown_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ChangedHandle:
        def verify(self) -> None:
            raise media_operation_lock.MediaOperationLockError("media_lock_changed")

    @contextmanager
    def changed_lock() -> object:
        yield ChangedHandle()

    monkeypatch.setattr(media_write_coordination, "media_operation_lock", changed_lock)
    with SessionLocal() as db, pytest.raises(MediaMutationExecutionError) as captured:
        coordinate_media_mutation(
            db,
            source="post_directory",
            operation=lambda: (_ for _ in ()).throw(MediaDirectoryError("stale_preview")),
            classify_result=lambda _result: MediaFilesystemOutcome.FILESYSTEM_CHANGED_KNOWN,
            classify_error=lambda _error: MediaFilesystemOutcome.NO_FILESYSTEM_CHANGE,
            classify_invalidation_reason=pages._directory_invalidation_reason,
        )
    assert captured.value.outcome == MediaFilesystemOutcome.FILESYSTEM_OUTCOME_UNKNOWN
    assert captured.value.index.status == MediaIndexCoordinationStatus.INVALIDATED
    with SessionLocal() as db:
        assert get_media_index_status(db).stale_reason == "directory_outcome_unknown"
