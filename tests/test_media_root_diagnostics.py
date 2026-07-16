from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import SessionLocal, engine
from app.models import Creator, Item
from app.services import local_media, media_root_diagnostics
from app.services.data_health import build_data_health_report
from app.services.media_index import load_preferred_media_snapshot
from app.services.media_root_diagnostics import (
    MediaRootDiagnosticError,
    build_media_root_diagnostic,
    execute_media_root_initialization,
)
from app.services.settings import save_app_settings


@pytest.fixture
def configured_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[tuple[Path, Path], None, None]:
    base = Path(f".nsfwtrack-root-test-{tmp_path.name}")
    if base.exists() or base.is_symlink():
        if base.is_symlink():
            base.unlink()
        else:
            shutil.rmtree(base)
    parent = base / "parent"
    parent.mkdir(parents=True)
    root = parent / "media"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    try:
        yield base, root
    finally:
        if base.is_symlink():
            base.unlink()
        elif base.exists():
            shutil.rmtree(base)


def _database_snapshot() -> tuple[
    tuple[tuple[int, str, str | None], ...],
    tuple[tuple[int, str, str | None], ...],
]:
    with SessionLocal() as db:
        return (
            tuple(
                (row.id, row.title, row.cover_path)
                for row in db.query(Item).order_by(Item.id)
            ),
            tuple(
                (row.id, row.name, row.avatar_path)
                for row in db.query(Creator).order_by(Creator.id)
            ),
        )


def _snapshot(diagnostic: object) -> dict[str, str]:
    parent = diagnostic.parent_identity
    assert parent is not None
    return {
        "expected_size": str(parent.size),
        "expected_device": str(parent.device),
        "expected_inode": str(parent.inode),
        "expected_modified_ns": str(parent.modified_ns),
        "expected_changed_ns": str(parent.changed_ns),
    }


def test_missing_diagnostic_is_authenticated_complete_and_zero_write(
    auth_client: TestClient,
    configured_root: tuple[Path, Path],
) -> None:
    base, root = configured_root
    sentinel = root.parent / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Missing Cover", cover_path="/media/missing.gif"),
                Creator(
                    name="Missing Avatar",
                    type="person",
                    avatar_path="/media/missing-avatar.png",
                ),
            ]
        )
        db.commit()
        diagnostic = build_media_root_diagnostic(db)
    before_db = _database_snapshot()
    before_parent = root.parent.stat()
    before_sentinel = sentinel.read_bytes()

    with TestClient(auth_client.app) as anonymous:
        denied = anonymous.get(
            "/data-health/media-root",
            follow_redirects=False,
        )
    write_statements: list[str] = []

    def capture_write_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        keyword = statement.lstrip().partition(" ")[0].upper()
        if keyword in {
            "ALTER",
            "CREATE",
            "DELETE",
            "DROP",
            "INSERT",
            "REPLACE",
            "UPDATE",
        }:
            write_statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture_write_statement)
    try:
        page = auth_client.get("/data-health/media-root")
    finally:
        event.remove(engine, "before_cursor_execute", capture_write_statement)
    health = auth_client.get("/data-health")

    assert diagnostic.status == "missing"
    assert diagnostic.can_initialize is True
    assert diagnostic.logical_path == "/media/"
    assert diagnostic.item_reference_count == 1
    assert diagnostic.creator_reference_count == 1
    assert diagnostic.reference_count == 2
    assert diagnostic.parent_identity is not None
    assert diagnostic.parent_identity.kind == "directory"
    assert diagnostic.root_identity is None
    assert denied.status_code == 303
    assert page.status_code == 200
    assert 'data-media-root-logical-path>/media/<' in page.text
    assert "目录缺失" in page.text
    assert "配置父目录身份" in page.text
    assert "媒体根目录身份" in page.text
    assert "条目封面引用数" in page.text
    assert "创作者头像引用数" in page.text
    assert 'action="/data-health/media-root/initialize"' in page.text
    assert "诊断媒体根目录" in health.text
    assert str(Path.cwd()) not in page.text
    assert str(base.resolve()) not in page.text
    assert auth_client.get("/data-health/media-root/initialize").status_code == 405
    after_parent = root.parent.stat()
    assert after_parent.st_mtime_ns == before_parent.st_mtime_ns
    assert after_parent.st_ctime_ns == before_parent.st_ctime_ns
    assert sentinel.read_bytes() == before_sentinel
    assert not root.exists()
    assert _database_snapshot() == before_db
    assert write_statements == []


@pytest.mark.parametrize(
    ("state", "expected_text"),
    [
        ("symlink", "根路径是符号链接"),
        ("not_directory", "根路径不是目录"),
        ("unreadable", "目录不可安全读取"),
        ("scan_failed", "安全扫描失败"),
    ],
)
def test_non_missing_states_are_diagnostic_only(
    state: str,
    expected_text: str,
    auth_client: TestClient,
    configured_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, root = configured_root
    original_scandir = None
    if state == "symlink":
        outside = base / "outside"
        outside.mkdir()
        root.symlink_to(outside, target_is_directory=True)
    elif state == "not_directory":
        root.write_text("existing object", encoding="utf-8")
    else:
        root.mkdir()
        if state == "unreadable":
            original_scandir = media_root_diagnostics.os.scandir

            def fail_descriptor_scandir(path: object) -> object:
                if isinstance(path, int):
                    raise PermissionError("private raw error must not leak")
                return original_scandir(path)

            monkeypatch.setattr(
                media_root_diagnostics.os,
                "scandir",
                fail_descriptor_scandir,
            )
        else:
            def fail_scan(*args: object, **kwargs: object) -> object:
                del args, kwargs
                raise local_media.LocalMediaPathError("private scan failure")

            monkeypatch.setattr(local_media, "scan_local_media", fail_scan)
    with SessionLocal() as db:
        db.add(Item(title="Root Issue", cover_path="/media/missing.gif"))
        db.commit()
        diagnostic = build_media_root_diagnostic(db)
    before_db = _database_snapshot()

    page = auth_client.get("/data-health/media-root")

    assert diagnostic.status == state
    assert diagnostic.can_initialize is False
    assert page.status_code == 200
    assert expected_text in page.text
    assert 'action="/data-health/media-root/initialize"' not in page.text
    assert "private raw error" not in page.text
    assert "private scan failure" not in page.text
    assert str(base.resolve()) not in page.text
    assert _database_snapshot() == before_db
    if state == "symlink":
        assert root.is_symlink()
    elif state == "not_directory":
        assert root.read_text(encoding="utf-8") == "existing object"
    else:
        assert root.is_dir()
    if original_scandir is not None:
        monkeypatch.setattr(
            media_root_diagnostics.os,
            "scandir",
            original_scandir,
        )


def test_ready_root_unsafe_configuration_and_missing_parent_never_offer_init(
    auth_client: TestClient,
    configured_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base, root = configured_root
    root.mkdir()
    ready = auth_client.get("/data-health/media-root")
    assert ready.status_code == 400
    assert "当前可用" in ready.text
    assert 'action="/data-health/media-root/initialize"' not in ready.text

    root.rmdir()
    outside = tmp_path / "outside-media"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", outside)
    unsafe = auth_client.get("/data-health/media-root")
    assert unsafe.status_code == 400
    assert "配置路径无法从应用工作目录安全验证" in unsafe.text
    assert str(outside) not in unsafe.text
    assert not outside.exists()

    missing_parent_root = base / "absent-parent" / "media"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", missing_parent_root)
    parent_missing = auth_client.get("/data-health/media-root")
    assert parent_missing.status_code == 200
    assert "目录不可安全读取" in parent_missing.text
    assert 'action="/data-health/media-root/initialize"' not in parent_missing.text
    assert not missing_parent_root.parent.exists()
    assert _database_snapshot() == ((), ())


def test_standard_initialization_creates_only_empty_root_and_keeps_references(
    auth_client: TestClient,
    configured_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, root = configured_root
    sentinel = root.parent / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Broken", cover_path="/media/still-missing.gif"),
                Creator(
                    name="Broken Avatar",
                    type="person",
                    avatar_path="/media/still-missing-avatar.png",
                ),
            ]
        )
        db.commit()
        diagnostic = build_media_root_diagnostic(db)
    before_db = _database_snapshot()
    synced_inodes: list[int] = []
    original_fsync = media_root_diagnostics.os.fsync

    def track_fsync(file_descriptor: int) -> None:
        file_stat = os.fstat(file_descriptor)
        if stat.S_ISDIR(file_stat.st_mode):
            synced_inodes.append(file_stat.st_ino)
        original_fsync(file_descriptor)

    def forbid_chmod(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("initialization must not chmod")

    def forbid_chown(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("initialization must not chown")

    monkeypatch.setattr(media_root_diagnostics.os, "fsync", track_fsync)
    monkeypatch.setattr(media_root_diagnostics.os, "chmod", forbid_chmod)
    monkeypatch.setattr(media_root_diagnostics.os, "chown", forbid_chown)

    rejected = auth_client.post(
        "/data-health/media-root/initialize",
        data=_snapshot(diagnostic),
        follow_redirects=True,
    )
    assert rejected.status_code == 200
    assert not root.exists()

    initialized = auth_client.post(
        "/data-health/media-root/initialize",
        data={**_snapshot(diagnostic), "confirm": "1"},
        follow_redirects=True,
    )

    assert initialized.status_code == 200
    assert "已安全创建媒体根目录 /media/" in initialized.text
    assert root.is_dir()
    assert list(root.iterdir()) == []
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert root.stat().st_ino in synced_inodes
    assert root.parent.stat().st_ino in synced_inodes
    assert _database_snapshot() == before_db
    with SessionLocal() as db:
        report = build_data_health_report(db)
        snapshot = load_preferred_media_snapshot(db)
        assert snapshot.source == "index"
        assert snapshot.status.last_refresh_source == "post_root_init"
        assert snapshot.scan.entries == ()
    codes = {issue.code for issue in report.issues}
    assert "media_root_unavailable" not in codes
    assert "media_reference_missing" in codes


def test_strict_initialization_requires_exact_confirm(
    auth_client: TestClient,
    configured_root: tuple[Path, Path],
) -> None:
    _, root = configured_root
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})
        diagnostic = build_media_root_diagnostic(db)
    page = auth_client.get("/data-health/media-root")
    assert "data-strict-confirm-message" in page.text

    wrong = auth_client.post(
        "/data-health/media-root/initialize",
        data={
            **_snapshot(diagnostic),
            "confirm": "1",
            "confirmation_text": "confirm",
        },
        follow_redirects=True,
    )
    assert "CONFIRM" in wrong.text
    assert not root.exists()

    accepted = auth_client.post(
        "/data-health/media-root/initialize",
        data={
            **_snapshot(diagnostic),
            "confirm": "1",
            "confirmation_text": "CONFIRM",
        },
        follow_redirects=True,
    )
    assert "已安全创建媒体根目录" in accepted.text
    assert root.is_dir()


@pytest.mark.parametrize("occupant", ["directory", "file", "symlink"])
def test_target_created_after_preview_is_rejected_without_overwrite(
    occupant: str,
    configured_root: tuple[Path, Path],
) -> None:
    base, root = configured_root
    with SessionLocal() as db:
        diagnostic = build_media_root_diagnostic(db)
    if occupant == "directory":
        root.mkdir()
    elif occupant == "file":
        root.write_text("occupant", encoding="utf-8")
    else:
        outside = base / "outside-target"
        outside.mkdir()
        root.symlink_to(outside, target_is_directory=True)

    with SessionLocal() as db, pytest.raises(MediaRootDiagnosticError) as exc_info:
        execute_media_root_initialization(db, **_snapshot(diagnostic))

    assert exc_info.value.code == "root_not_missing"
    if occupant == "directory":
        assert root.is_dir() and not root.is_symlink()
    elif occupant == "file":
        assert root.read_text(encoding="utf-8") == "occupant"
    else:
        assert root.is_symlink()
        assert (base / "outside-target").is_dir()
    assert _database_snapshot() == ((), ())


def test_parent_replacement_and_post_open_symlink_race_are_rejected(
    configured_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, root = configured_root
    parent = root.parent
    outside = base / "outside"
    outside.mkdir()
    with SessionLocal() as db:
        diagnostic = build_media_root_diagnostic(db)

    moved = base / "moved-parent"
    parent.rename(moved)
    parent.symlink_to(outside, target_is_directory=True)
    with SessionLocal() as db, pytest.raises(MediaRootDiagnosticError) as replaced:
        execute_media_root_initialization(db, **_snapshot(diagnostic))
    assert replaced.value.code == "parent_changed"
    assert not (moved / "media").exists()
    assert not (outside / "media").exists()

    parent.unlink()
    moved.rename(parent)
    with SessionLocal() as db:
        fresh = build_media_root_diagnostic(db)
    original_verify = media_root_diagnostics._verify_parent_chain_mapping
    calls = 0

    def replace_before_final_mapping(chain: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 4:
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)
        original_verify(chain)

    monkeypatch.setattr(
        media_root_diagnostics,
        "_verify_parent_chain_mapping",
        replace_before_final_mapping,
    )
    with SessionLocal() as db, pytest.raises(MediaRootDiagnosticError) as raced:
        execute_media_root_initialization(db, **_snapshot(fresh))

    assert raced.value.code == "parent_changed"
    assert calls >= 4
    assert not (moved / "media").exists()
    assert not (outside / "media").exists()
    assert _database_snapshot() == ((), ())


def test_target_symlink_race_at_atomic_mkdir_is_rejected(
    configured_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, root = configured_root
    outside = base / "outside"
    outside.mkdir()
    with SessionLocal() as db:
        diagnostic = build_media_root_diagnostic(db)
    original_mkdir = media_root_diagnostics.os.mkdir
    injected = False

    def race_mkdir(
        path: str,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal injected
        if path == "media" and dir_fd is not None and not injected:
            os.symlink(outside, path, target_is_directory=True, dir_fd=dir_fd)
            injected = True
        original_mkdir(path, mode=mode, dir_fd=dir_fd)

    monkeypatch.setattr(media_root_diagnostics.os, "mkdir", race_mkdir)
    with SessionLocal() as db, pytest.raises(MediaRootDiagnosticError) as exc_info:
        execute_media_root_initialization(db, **_snapshot(diagnostic))

    assert exc_info.value.code == "root_not_missing"
    assert injected is True
    assert root.is_symlink()
    assert outside.is_dir()
    assert list(outside.iterdir()) == []
    assert _database_snapshot() == ((), ())


def test_parent_replacement_during_atomic_mkdir_is_detected_after_creation(
    configured_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, root = configured_root
    parent = root.parent
    moved = base / "moved-parent"
    outside = base / "outside"
    outside.mkdir()
    with SessionLocal() as db:
        diagnostic = build_media_root_diagnostic(db)
    original_mkdir = media_root_diagnostics.os.mkdir

    def replace_parent_then_mkdir(
        path: str,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        assert path == "media"
        assert dir_fd is not None
        parent.rename(moved)
        parent.symlink_to(outside, target_is_directory=True)
        original_mkdir(path, mode=mode, dir_fd=dir_fd)

    monkeypatch.setattr(
        media_root_diagnostics.os,
        "mkdir",
        replace_parent_then_mkdir,
    )
    with SessionLocal() as db, pytest.raises(MediaRootDiagnosticError) as exc_info:
        execute_media_root_initialization(db, **_snapshot(diagnostic))

    assert exc_info.value.code == "parent_changed"
    assert exc_info.value.created is True
    assert parent.is_symlink()
    assert (moved / "media").is_dir()
    assert list((moved / "media").iterdir()) == []
    assert not (outside / "media").exists()
    assert _database_snapshot() == ((), ())


def test_forged_parent_and_mkdir_failure_leave_everything_unchanged(
    configured_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, root = configured_root
    with SessionLocal() as db:
        diagnostic = build_media_root_diagnostic(db)
        forged = _snapshot(diagnostic)
        forged["expected_inode"] = str(diagnostic.parent_identity.inode + 1)
        with pytest.raises(MediaRootDiagnosticError) as forged_error:
            execute_media_root_initialization(db, **forged)
        assert forged_error.value.code == "parent_changed"

    def fail_mkdir(
        path: str,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        del path, mode, dir_fd
        raise OSError("private mkdir failure")

    monkeypatch.setattr(media_root_diagnostics.os, "mkdir", fail_mkdir)
    with SessionLocal() as db, pytest.raises(MediaRootDiagnosticError) as create_error:
        execute_media_root_initialization(db, **_snapshot(diagnostic))

    assert create_error.value.code == "create_failed"
    assert not root.exists()
    assert _database_snapshot() == ((), ())


def test_fsync_failure_reports_created_warning_without_database_change(
    auth_client: TestClient,
    configured_root: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, root = configured_root
    with SessionLocal() as db:
        db.add(Item(title="Untouched", cover_path="/media/missing.gif"))
        db.commit()
        diagnostic = build_media_root_diagnostic(db)
    before_db = _database_snapshot()
    sync_calls = 0

    def fail_fsync(file_descriptor: int) -> None:
        nonlocal sync_calls
        assert stat.S_ISDIR(os.fstat(file_descriptor).st_mode)
        sync_calls += 1
        raise OSError("private sync failure")

    monkeypatch.setattr(media_root_diagnostics.os, "fsync", fail_fsync)
    response = auth_client.post(
        "/data-health/media-root/initialize",
        data={**_snapshot(diagnostic), "confirm": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "已安全创建媒体根目录" in response.text
    assert "sync_failed" in response.text
    assert "已经创建" in response.text or "已创建" in response.text
    assert sync_calls == 2
    assert root.is_dir()
    assert list(root.iterdir()) == []
    assert _database_snapshot() == before_db
