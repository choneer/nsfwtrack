from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media, media_upload_residue_cleanup
from app.services.data_health import build_data_health_report
from app.services.media_upload_residue_cleanup import (
    MediaUploadResidueCleanupError,
    build_media_upload_residue_cleanup_preview,
    execute_media_upload_residue_cleanup,
)
from app.services.settings import save_app_settings


def _write_residue(media_root: Path, relative_path: str, content: bytes) -> Path:
    path = media_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _snapshot(preview: object) -> dict[str, str]:
    residue = preview.residue
    return {
        "residue_path": residue.residue_path,
        "expected_size": str(residue.size),
        "expected_device": str(residue.device),
        "expected_inode": str(residue.inode),
        "expected_modified_ns": str(residue.modified_ns),
        "expected_changed_ns": str(residue.changed_ns),
    }


def _database_snapshot() -> tuple[
    tuple[tuple[int, str | None], ...],
    tuple[tuple[int, str | None], ...],
]:
    with SessionLocal() as db:
        return (
            tuple(
                (row.id, row.cover_path)
                for row in db.query(Item).order_by(Item.id)
            ),
            tuple(
                (row.id, row.avatar_path)
                for row in db.query(Creator).order_by(Creator.id)
            ),
        )


def test_preview_is_authenticated_complete_zero_write_and_never_reads_content(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_residue(
        media_root,
        "library/.upload-preview.tmp",
        b"arbitrary partial upload content",
    )
    near_name = _write_residue(
        media_root,
        "library/.upload-preview.tmp.extra",
        b"must remain",
    )
    outside = _write_residue(tmp_path, "outside/.upload-outside.tmp", b"outside")
    symlink = media_root / "library/.upload-link.tmp"
    symlink.symlink_to(outside)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    before_db = _database_snapshot()
    before_stat = target.stat(follow_symlinks=False)
    before_content = target.read_bytes()

    with TestClient(auth_client.app) as anonymous:
        denied = anonymous.get(
            "/data-health/upload-residue/delete-preview",
            params={"residue_path": "library/.upload-preview.tmp"},
            follow_redirects=False,
        )

    with monkeypatch.context() as no_read:
        def reject_read_bytes(path: Path) -> bytes:
            raise AssertionError(f"temporary content read: {path}")

        def reject_os_read(file_descriptor: int, length: int) -> bytes:
            del file_descriptor, length
            raise AssertionError("temporary content read through os.read")

        no_read.setattr(Path, "read_bytes", reject_read_bytes)
        no_read.setattr(media_upload_residue_cleanup.os, "read", reject_os_read)
        health = auth_client.get("/data-health")
        preview = auth_client.get(
            "/data-health/upload-residue/delete-preview",
            params={"residue_path": "library/.upload-preview.tmp"},
        )

    after_stat = target.stat(follow_symlinks=False)
    assert denied.status_code == 303
    assert health.status_code == 200
    assert health.text.count("预览删除残留") == 1
    assert "library%2F.upload-preview.tmp" in health.text
    assert ".upload-preview.tmp.extra" not in health.text
    assert ".upload-link.tmp" not in health.text
    assert preview.status_code == 200
    assert "data-upload-residue-preview" in preview.text
    assert "library/.upload-preview.tmp" in preview.text
    assert str(before_stat.st_size) in preview.text
    assert str(before_stat.st_dev) in preview.text
    assert str(before_stat.st_ino) in preview.text
    assert str(before_stat.st_mtime_ns) in preview.text
    assert str(before_stat.st_ctime_ns) in preview.text
    assert "BEGIN IMMEDIATE" in preview.text
    assert "不会读取、解析、恢复或复制临时文件内容" in preview.text
    assert 'action="/data-health/upload-residue/delete"' in preview.text
    assert auth_client.get("/data-health/upload-residue/delete").status_code == 405
    assert _database_snapshot() == before_db
    assert target.read_bytes() == before_content
    assert target.stat(follow_symlinks=False) == after_stat == before_stat
    assert near_name.read_bytes() == b"must remain"
    assert symlink.is_symlink()


def test_confirmed_delete_removes_only_target_and_fsyncs_directory(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_residue(media_root, "library/.upload-delete.tmp", b"delete")
    other = _write_residue(media_root, "library/.upload-keep.tmp", b"keep")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    synced_directories: list[int] = []
    original_fsync = media_upload_residue_cleanup.os.fsync

    def track_fsync(file_descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(file_descriptor).st_mode):
            synced_directories.append(file_descriptor)
        original_fsync(file_descriptor)

    monkeypatch.setattr(media_upload_residue_cleanup.os, "fsync", track_fsync)
    with SessionLocal() as db:
        preview = build_media_upload_residue_cleanup_preview(
            db,
            residue_path="library/.upload-delete.tmp",
        )
    before_db = _database_snapshot()

    rejected = auth_client.post(
        "/data-health/upload-residue/delete",
        data=_snapshot(preview),
        follow_redirects=True,
    )
    assert "危险操作已拒绝" in rejected.text
    assert target.exists()

    response = auth_client.post(
        "/data-health/upload-residue/delete",
        data={**_snapshot(preview), "confirm": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "已永久删除上传残留" in response.text
    assert not target.exists()
    assert other.read_bytes() == b"keep"
    assert synced_directories
    assert _database_snapshot() == before_db
    with SessionLocal() as db:
        issue_ids = {issue.object_id for issue in build_data_health_report(db).issues}
    assert "library/.upload-delete.tmp" not in issue_ids
    assert "library/.upload-keep.tmp" in issue_ids


def test_strict_delete_requires_exact_confirm(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_residue(media_root, ".upload-strict.tmp", b"strict")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})
        preview = build_media_upload_residue_cleanup_preview(
            db,
            residue_path=".upload-strict.tmp",
        )
    page = auth_client.get(
        "/data-health/upload-residue/delete-preview",
        params={"residue_path": ".upload-strict.tmp"},
    )
    assert "data-strict-confirm-message" in page.text

    rejected = auth_client.post(
        "/data-health/upload-residue/delete",
        data={
            **_snapshot(preview),
            "confirm": "1",
            "confirmation_text": "confirm",
        },
        follow_redirects=True,
    )
    assert "CONFIRM" in rejected.text
    assert target.exists()

    accepted = auth_client.post(
        "/data-health/upload-residue/delete",
        data={
            **_snapshot(preview),
            "confirm": "1",
            "confirmation_text": "CONFIRM",
        },
        follow_redirects=True,
    )
    assert accepted.status_code == 200
    assert not target.exists()


@pytest.mark.parametrize(
    ("relative_path", "kind", "expected_code"),
    [
        (".upload-.tmp", "file", "not_residue"),
        ("upload-near.tmp", "file", "not_residue"),
        (".Upload-near.tmp", "file", "not_residue"),
        (".upload-near.TMP", "file", "not_residue"),
        (".upload-near.tmp.extra", "file", "not_residue"),
        (".upload-directory.tmp", "directory", "residue_invalid"),
        (".upload-symlink.tmp", "symlink", "residue_invalid"),
        (".upload-fifo.tmp", "fifo", "residue_invalid"),
        (".upload-missing.tmp", "missing", "residue_not_found"),
        ("../.upload-escape.tmp", "missing", "invalid_request"),
        ("/media/.upload-absolute.tmp", "missing", "invalid_request"),
    ],
)
def test_preview_rejects_near_names_illegal_types_missing_and_forged_paths(
    relative_path: str,
    kind: str,
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    target = media_root / relative_path
    if kind == "file":
        target.write_bytes(b"near name")
    elif kind == "directory":
        target.mkdir()
    elif kind == "symlink":
        outside = tmp_path / "outside.tmp"
        outside.write_bytes(b"outside")
        target.symlink_to(outside)
    elif kind == "fifo":
        target.parent.mkdir(parents=True, exist_ok=True)
        os.mkfifo(target)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    before_db = _database_snapshot()

    with SessionLocal() as db, pytest.raises(
        MediaUploadResidueCleanupError,
    ) as exc_info:
        build_media_upload_residue_cleanup_preview(
            db,
            residue_path=relative_path,
        )

    assert exc_info.value.code == expected_code
    assert _database_snapshot() == before_db
    if kind != "missing":
        assert target.exists() or target.is_symlink()


def test_referenced_residue_requires_c1_and_forged_post_is_rejected(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_residue(media_root, "library/.upload-referenced.tmp", b"ref")
    relative_path = "library/.upload-referenced.tmp"
    media_path = f"/media/{relative_path}"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Referenced Item", cover_path=media_path),
                Creator(
                    name="Referenced Creator",
                    type="person",
                    avatar_path=relative_path,
                ),
            ]
        )
        db.commit()
        preview = build_media_upload_residue_cleanup_preview(
            db,
            residue_path=relative_path,
        )
    before_db = _database_snapshot()
    page = auth_client.get(
        "/data-health/upload-residue/delete-preview",
        params={"residue_path": relative_path},
    )
    response = auth_client.post(
        "/data-health/upload-residue/delete",
        data={**_snapshot(preview), "confirm": "1"},
        follow_redirects=True,
    )

    assert preview.reference_count == 2
    assert page.status_code == 200
    assert "目标仍有数据库引用，不能删除" in page.text
    assert "C1 单项修复" in page.text
    assert 'action="/data-health/upload-residue/delete"' not in page.text
    assert "写锁内发现条目封面或创作者头像引用" in response.text
    assert target.read_bytes() == b"ref"
    assert _database_snapshot() == before_db


def test_forged_stale_replaced_and_missing_requests_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_residue(media_root, ".upload-stale.tmp", b"initial")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_upload_residue_cleanup_preview(
            db,
            residue_path=".upload-stale.tmp",
        )
        forged = _snapshot(preview)
        forged["expected_inode"] = str(preview.residue.inode + 1)
        with pytest.raises(MediaUploadResidueCleanupError) as forged_error:
            execute_media_upload_residue_cleanup(db, **forged)
        assert forged_error.value.code == "stale_residue"

        oversized = _snapshot(preview)
        oversized["expected_size"] = "9" * 31
        with pytest.raises(MediaUploadResidueCleanupError) as oversized_error:
            execute_media_upload_residue_cleanup(db, **oversized)
        assert oversized_error.value.code == "invalid_request"

        target.write_bytes(b"changed content and identity")
        with pytest.raises(MediaUploadResidueCleanupError) as changed_error:
            execute_media_upload_residue_cleanup(db, **_snapshot(preview))
        assert changed_error.value.code == "stale_residue"

        target.unlink()
        target.write_bytes(b"replacement inode")
        with pytest.raises(MediaUploadResidueCleanupError) as replaced_error:
            execute_media_upload_residue_cleanup(db, **_snapshot(preview))
        assert replaced_error.value.code == "stale_residue"

        target.unlink()
        with pytest.raises(MediaUploadResidueCleanupError) as missing_error:
            execute_media_upload_residue_cleanup(db, **_snapshot(preview))
        assert missing_error.value.code == "residue_not_found"

    assert _database_snapshot() == ((), ())


def test_reference_race_is_rejected_under_begin_immediate_without_file_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_residue(media_root, ".upload-reference-race.tmp", b"race")
    relative_path = ".upload-reference-race.tmp"
    media_path = f"/media/{relative_path}"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        initial = build_media_upload_residue_cleanup_preview(
            db,
            residue_path=relative_path,
        )

    original_build = (
        media_upload_residue_cleanup.build_media_upload_residue_cleanup_preview
    )
    injected = False

    def build_then_add_reference(db: object, **values: object) -> object:
        nonlocal injected
        preview = original_build(db, **values)
        if not injected:
            db.rollback()
            with SessionLocal() as racing_db:
                racing_db.add(Item(title="Racing Reference", cover_path=media_path))
                racing_db.commit()
            injected = True
        return preview

    monkeypatch.setattr(
        media_upload_residue_cleanup,
        "build_media_upload_residue_cleanup_preview",
        build_then_add_reference,
    )
    begin_immediate_seen = False
    with SessionLocal() as db:
        original_execute = db.execute

        def track_execute(statement: object, *args: object, **kwargs: object) -> object:
            nonlocal begin_immediate_seen
            if str(statement) == "BEGIN IMMEDIATE":
                begin_immediate_seen = True
            return original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(db, "execute", track_execute)
        with pytest.raises(MediaUploadResidueCleanupError) as exc_info:
            execute_media_upload_residue_cleanup(db, **_snapshot(initial))

    assert exc_info.value.code == "residue_referenced"
    assert begin_immediate_seen is True
    assert target.read_bytes() == b"race"
    with SessionLocal() as db:
        assert db.query(Item).filter(Item.cover_path == media_path).count() == 1


def test_identity_race_after_locked_reference_check_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_residue(media_root, ".upload-identity-race.tmp", b"before")
    relative_path = ".upload-identity-race.tmp"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        initial = build_media_upload_residue_cleanup_preview(
            db,
            residue_path=relative_path,
        )

    original_load = media_upload_residue_cleanup._load_references
    calls = 0

    def replace_after_locked_check(db: object, residue: object) -> object:
        nonlocal calls
        result = original_load(db, residue)
        calls += 1
        if calls == 2:
            target.unlink()
            target.write_bytes(b"replacement")
        return result

    monkeypatch.setattr(
        media_upload_residue_cleanup,
        "_load_references",
        replace_after_locked_check,
    )
    with SessionLocal() as db, pytest.raises(
        MediaUploadResidueCleanupError,
    ) as exc_info:
        execute_media_upload_residue_cleanup(db, **_snapshot(initial))

    assert exc_info.value.code == "stale_residue"
    assert target.read_bytes() == b"replacement"
    assert _database_snapshot() == ((), ())


def test_parent_symlink_race_never_unlinks_external_hardlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    parent = media_root / "nested"
    target = _write_residue(
        media_root,
        "nested/.upload-parent-race.tmp",
        b"same inode must remain",
    )
    external = tmp_path / "external"
    external.mkdir()
    external_target = external / target.name
    os.link(target, external_target)
    moved = media_root / "moved"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_upload_residue_cleanup_preview(
            db,
            residue_path="nested/.upload-parent-race.tmp",
        )

    original_verify = media_upload_residue_cleanup._verify_residue_mapping
    verifications = 0

    def replace_parent_before_final_mapping_check(residue: object) -> None:
        nonlocal verifications
        verifications += 1
        if verifications == 2:
            parent.rename(moved)
            parent.symlink_to(external, target_is_directory=True)
        original_verify(residue)

    monkeypatch.setattr(
        media_upload_residue_cleanup,
        "_verify_residue_mapping",
        replace_parent_before_final_mapping_check,
    )

    with pytest.raises(media_upload_residue_cleanup._ResidueDeleteError) as error:
        media_upload_residue_cleanup._delete_residue(preview.residue)

    assert error.value.code == "changed"
    assert verifications == 2
    assert parent.is_symlink()
    assert (moved / target.name).exists()
    assert external_target.exists()


def test_unlink_failure_retains_file_and_database_with_clear_reason(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_residue(media_root, ".upload-unlink-failure.tmp", b"retain")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_upload_residue_cleanup_preview(
            db,
            residue_path=".upload-unlink-failure.tmp",
        )
    before_db = _database_snapshot()

    def fail_unlink(path: str, *, dir_fd: int | None = None) -> None:
        del path, dir_fd
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(media_upload_residue_cleanup.os, "unlink", fail_unlink)
    response = auth_client.post(
        "/data-health/upload-residue/delete",
        data={**_snapshot(preview), "confirm": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "unlink 未成功" in response.text
    assert target.read_bytes() == b"retain"
    assert _database_snapshot() == before_db


def test_directory_fsync_failure_reports_removed_warning_without_database_change(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_residue(media_root, ".upload-sync-warning.tmp", b"remove")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_upload_residue_cleanup_preview(
            db,
            residue_path=".upload-sync-warning.tmp",
        )
    before_db = _database_snapshot()
    original_fsync = media_upload_residue_cleanup.os.fsync

    def fail_directory_fsync(file_descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(file_descriptor).st_mode):
            raise OSError("simulated directory sync failure")
        original_fsync(file_descriptor)

    monkeypatch.setattr(
        media_upload_residue_cleanup.os,
        "fsync",
        fail_directory_fsync,
    )
    response = auth_client.post(
        "/data-health/upload-residue/delete",
        data={**_snapshot(preview), "confirm": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "已永久删除上传残留" in response.text
    assert "sync_failed" in response.text
    assert "已经删除" in response.text
    assert not target.exists()
    assert _database_snapshot() == before_db


@pytest.mark.parametrize("failure", ["lock", "query"])
def test_write_lock_and_locked_reference_query_fail_closed_before_unlink(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_residue(media_root, f".upload-{failure}-failure.tmp", b"safe")
    relative_path = f".upload-{failure}-failure.tmp"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_upload_residue_cleanup_preview(
            db,
            residue_path=relative_path,
        )

        if failure == "lock":
            original_execute = db.execute

            def fail_begin(
                statement: object,
                *args: object,
                **kwargs: object,
            ) -> object:
                if str(statement) == "BEGIN IMMEDIATE":
                    raise RuntimeError("simulated lock failure")
                return original_execute(statement, *args, **kwargs)

            monkeypatch.setattr(db, "execute", fail_begin)
        else:
            original_load = media_upload_residue_cleanup._load_references
            calls = 0

            def fail_second_load(db: object, residue: object) -> object:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("simulated reference query failure")
                return original_load(db, residue)

            monkeypatch.setattr(
                media_upload_residue_cleanup,
                "_load_references",
                fail_second_load,
            )

        with pytest.raises(MediaUploadResidueCleanupError) as exc_info:
            execute_media_upload_residue_cleanup(db, **_snapshot(preview))

    assert exc_info.value.code == "reference_check_failed"
    assert target.read_bytes() == b"safe"
    assert _database_snapshot() == ((), ())
