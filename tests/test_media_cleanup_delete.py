from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media, media_cleanup_delete
from app.services.data_health import build_data_health_report
from app.services.media_cleanup_delete import (
    MediaCleanupDeleteError,
    build_media_cleanup_delete_preview,
    execute_media_cleanup_delete,
)
from app.services.settings import save_app_settings


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(media_root: Path, filename: str, *, extra: int = 0) -> Path:
    path = media_root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def _media_path(path: Path, media_root: Path) -> str:
    return f"/media/{path.relative_to(media_root).as_posix()}"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(preview: object) -> dict[str, str]:
    anchor = preview.anchor
    return {
        "media_path": anchor.media_path,
        "sha256": anchor.sha256,
        "expected_size": str(anchor.size),
        "expected_device": str(anchor.device),
        "expected_inode": str(anchor.inode),
        "expected_modified_ns": str(anchor.modified_ns),
        "expected_changed_ns": str(anchor.changed_ns),
    }


def _database_snapshot() -> tuple[tuple[tuple[int, str | None], ...], tuple[tuple[int, str | None], ...]]:
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


def test_delete_preview_is_authenticated_complete_zero_write_and_unreferenced_only(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    unreferenced = _write_gif(
        media_root,
        "Cleanup/.cleanup-anchor-unreferenced.gif",
        extra=1,
    )
    referenced = _write_gif(
        media_root,
        "Cleanup/.cleanup-anchor-referenced.gif",
        extra=2,
    )
    damaged = media_root / "Cleanup/.cleanup-anchor-damaged.gif"
    damaged.write_bytes(b"damaged")
    recovered = _write_gif(media_root, "Cleanup/recovered-normal.gif", extra=3)
    unreferenced_path = _media_path(unreferenced, media_root)
    referenced_path = _media_path(referenced, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add(Item(title="Referenced Anchor", cover_path=referenced_path))
        db.commit()
    before_db = _database_snapshot()
    before_files = {
        path: path.read_bytes()
        for path in (unreferenced, referenced, damaged, recovered)
    }

    with TestClient(auth_client.app) as anonymous:
        denied = anonymous.get(
            "/media-library/recovery/delete-preview",
            params={
                "media_path": unreferenced_path,
                "sha256": _digest(unreferenced),
            },
            follow_redirects=False,
        )
    center = auth_client.get("/media-library/recovery")
    preview = auth_client.get(
        "/media-library/recovery/delete-preview",
        params={
            "media_path": unreferenced_path,
            "sha256": _digest(unreferenced),
        },
    )
    referenced_preview = auth_client.get(
        "/media-library/recovery/delete-preview",
        params={
            "media_path": referenced_path,
            "sha256": _digest(referenced),
        },
    )

    assert denied.status_code == 303
    assert center.status_code == 200
    assert center.text.count("预览永久删除") == 1
    assert preview.status_code == 200
    assert 'data-cleanup-delete-preview' in preview.text
    assert unreferenced_path in preview.text
    assert _digest(unreferenced) in preview.text
    assert "device" in preview.text
    assert "inode" in preview.text
    assert "mtime" in preview.text
    assert "ctime" in preview.text
    assert "永久删除，不可撤销" in preview.text
    assert "不会创建 recovered-*" in preview.text
    assert 'action="/media-library/recovery/delete"' in preview.text
    assert referenced_preview.status_code == 400
    assert "仍被条目封面或创作者头像引用" in referenced_preview.text
    assert auth_client.get("/media-library/recovery/delete").status_code == 405
    assert _database_snapshot() == before_db
    assert {path: path.read_bytes() for path in before_files} == before_files


def test_confirmed_delete_removes_only_target_fsyncs_directory_and_updates_audits(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, ".cleanup-anchor-delete.gif", extra=4)
    other = _write_gif(media_root, ".cleanup-anchor-keep.gif", extra=5)
    target_path = _media_path(target, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    sync_kinds: list[str] = []
    original_fsync = local_media.os.fsync

    def track_fsync(file_descriptor: int) -> None:
        mode = os.fstat(file_descriptor).st_mode
        if stat.S_ISDIR(mode):
            sync_kinds.append("directory")
        original_fsync(file_descriptor)

    monkeypatch.setattr(local_media.os, "fsync", track_fsync)
    with SessionLocal() as db:
        preview = build_media_cleanup_delete_preview(
            db,
            media_path=target_path,
            sha256=_digest(target),
        )
    before_db = _database_snapshot()

    missing_confirm = auth_client.post(
        "/media-library/recovery/delete",
        data=_snapshot(preview),
        follow_redirects=True,
    )
    assert "危险操作已拒绝" in missing_confirm.text
    assert target.exists()

    deleted = auth_client.post(
        "/media-library/recovery/delete",
        data={**_snapshot(preview), "confirm": "1"},
        follow_redirects=True,
    )

    assert deleted.status_code == 200
    assert "已永久删除未引用锚点" in deleted.text
    assert not target.exists()
    assert other.exists()
    assert not list(media_root.rglob("recovered-*"))
    assert "directory" in sync_kinds
    assert _database_snapshot() == before_db
    assert target_path not in auth_client.get("/media-library/recovery").text
    with SessionLocal() as db:
        report = build_data_health_report(db)
    assert target_path not in {issue.object_id for issue in report.issues}
    assert _media_path(other, media_root) in {
        issue.object_id for issue in report.issues
    }


def test_strict_delete_requires_exact_confirm(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, ".cleanup-anchor-strict-delete.gif", extra=6)
    target_path = _media_path(target, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})
        preview = build_media_cleanup_delete_preview(
            db,
            media_path=target_path,
            sha256=_digest(target),
        )
    page = auth_client.get(
        "/media-library/recovery/delete-preview",
        params={"media_path": target_path, "sha256": _digest(target)},
    )
    assert "data-strict-confirm-message" in page.text

    rejected = auth_client.post(
        "/media-library/recovery/delete",
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
        "/media-library/recovery/delete",
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
    ("kind", "expected_code"),
    [
        ("referenced", "anchor_referenced"),
        ("damaged", "anchor_damaged"),
        ("symlink", "anchor_damaged"),
        ("wrong_extension", "invalid_request"),
        ("recovered", "not_anchor"),
        ("ordinary", "not_anchor"),
    ],
)
def test_delete_preview_rejects_ineligible_targets(
    kind: str,
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    ordinary = _write_gif(media_root, "ordinary.gif", extra=7)
    if kind == "referenced":
        target = _write_gif(media_root, ".cleanup-anchor-referenced.gif", extra=8)
    elif kind == "damaged":
        target = media_root / ".cleanup-anchor-damaged.gif"
        target.write_bytes(b"damaged")
    elif kind == "symlink":
        target = media_root / ".cleanup-anchor-symlink.gif"
        target.symlink_to(ordinary)
    elif kind == "wrong_extension":
        target = media_root / ".cleanup-anchor-wrong.tmp"
        target.write_bytes(_gif_bytes(9))
    elif kind == "recovered":
        target = _write_gif(media_root, "recovered-normal.gif", extra=10)
    else:
        target = ordinary
    target_path = _media_path(target, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    if kind == "referenced":
        with SessionLocal() as db:
            db.add(Creator(name="Reference", type="person", avatar_path=target_path))
            db.commit()
    before_db = _database_snapshot()
    before_paths = set(media_root.rglob("*"))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()

    with SessionLocal() as db, pytest.raises(MediaCleanupDeleteError) as exc_info:
        build_media_cleanup_delete_preview(
            db,
            media_path=target_path,
            sha256=digest,
        )
    assert exc_info.value.code == expected_code
    assert set(media_root.rglob("*")) == before_paths
    assert _database_snapshot() == before_db


def test_stale_forged_changed_and_missing_requests_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, ".cleanup-anchor-stale-delete.gif", extra=11)
    target_path = _media_path(target, media_root)
    digest = _digest(target)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_cleanup_delete_preview(
            db,
            media_path=target_path,
            sha256=digest,
        )
        forged = _snapshot(preview)
        forged["expected_inode"] = str(preview.anchor.inode + 1)
        with pytest.raises(MediaCleanupDeleteError) as forged_error:
            execute_media_cleanup_delete(db, **forged)
        assert forged_error.value.code == "stale_anchor"

        os.utime(target, ns=(preview.anchor.modified_ns, preview.anchor.modified_ns + 1))
        with pytest.raises(MediaCleanupDeleteError) as changed_error:
            execute_media_cleanup_delete(db, **_snapshot(preview))
        assert changed_error.value.code == "stale_anchor"

        target.write_bytes(_gif_bytes(12))
        with pytest.raises(MediaCleanupDeleteError) as hash_error:
            execute_media_cleanup_delete(db, **_snapshot(preview))
        assert hash_error.value.code == "stale_anchor"

        target.unlink()
        with pytest.raises(MediaCleanupDeleteError) as missing_error:
            execute_media_cleanup_delete(db, **_snapshot(preview))
        assert missing_error.value.code == "anchor_not_found"

    assert not list(media_root.rglob("recovered-*"))


def test_reference_race_is_rejected_under_begin_immediate_without_file_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, ".cleanup-anchor-reference-race.gif", extra=13)
    target_path = _media_path(target, media_root)
    digest = _digest(target)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        initial = build_media_cleanup_delete_preview(
            db,
            media_path=target_path,
            sha256=digest,
        )

    original_build = media_cleanup_delete.build_media_cleanup_delete_preview
    injected = False

    def build_then_add_reference(db: object, **values: object) -> object:
        nonlocal injected
        preview = original_build(db, **values)
        if not injected:
            db.rollback()
            with SessionLocal() as racing_db:
                racing_db.add(Item(title="Racing Reference", cover_path=target_path))
                racing_db.commit()
            injected = True
        return preview

    monkeypatch.setattr(
        media_cleanup_delete,
        "build_media_cleanup_delete_preview",
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
        with pytest.raises(MediaCleanupDeleteError) as exc_info:
            execute_media_cleanup_delete(db, **_snapshot(initial))

    assert exc_info.value.code == "anchor_referenced"
    assert begin_immediate_seen is True
    assert target.exists()
    assert _digest(target) == digest
    with SessionLocal() as db:
        assert db.query(Item).filter(Item.cover_path == target_path).count() == 1
    assert not list(media_root.rglob("recovered-*"))


def test_delete_failure_keeps_file_and_database_unchanged_with_reason(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, ".cleanup-anchor-delete-failure.gif", extra=14)
    target_path = _media_path(target, media_root)
    digest = _digest(target)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_cleanup_delete_preview(
            db,
            media_path=target_path,
            sha256=digest,
        )
    before_db = _database_snapshot()

    def fail_delete(record: local_media.ValidatedLocalMediaFile) -> None:
        del record
        raise local_media.LocalMediaDeleteError("delete_failed")

    monkeypatch.setattr(local_media, "delete_validated_local_media_file", fail_delete)
    response = auth_client.post(
        "/media-library/recovery/delete",
        data={**_snapshot(preview), "confirm": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "无法按完整身份删除目标" in response.text
    assert target.exists()
    assert _digest(target) == digest
    assert _database_snapshot() == before_db
    assert not list(media_root.rglob("recovered-*"))


def test_directory_sync_failure_reports_removed_warning_without_database_change(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, ".cleanup-anchor-sync-warning.gif", extra=15)
    target_path = _media_path(target, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_cleanup_delete_preview(
            db,
            media_path=target_path,
            sha256=_digest(target),
        )
    before_db = _database_snapshot()
    original_fsync = local_media.os.fsync

    def fail_directory_fsync(file_descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(file_descriptor).st_mode):
            raise OSError("simulated directory sync failure")
        original_fsync(file_descriptor)

    monkeypatch.setattr(local_media.os, "fsync", fail_directory_fsync)
    response = auth_client.post(
        "/media-library/recovery/delete",
        data={**_snapshot(preview), "confirm": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "已永久删除未引用锚点" in response.text
    assert "sync_failed" in response.text
    assert not target.exists()
    assert _database_snapshot() == before_db


def test_write_lock_failure_refuses_before_delete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, ".cleanup-anchor-lock-failure.gif", extra=16)
    target_path = _media_path(target, media_root)
    digest = _digest(target)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_cleanup_delete_preview(
            db,
            media_path=target_path,
            sha256=digest,
        )
        original_execute = db.execute

        def fail_begin(statement: object, *args: object, **kwargs: object) -> object:
            if str(statement) == "BEGIN IMMEDIATE":
                raise RuntimeError("simulated lock failure")
            return original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(db, "execute", fail_begin)
        with pytest.raises(MediaCleanupDeleteError) as exc_info:
            execute_media_cleanup_delete(db, **_snapshot(preview))

    assert exc_info.value.code == "reference_check_failed"
    assert target.exists()
    assert _digest(target) == digest
    assert not list(media_root.rglob("recovered-*"))


def test_locked_reference_query_failure_refuses_before_delete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, ".cleanup-anchor-query-failure.gif", extra=17)
    target_path = _media_path(target, media_root)
    digest = _digest(target)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_cleanup_delete_preview(
            db,
            media_path=target_path,
            sha256=digest,
        )

        def fail_reference_query(*args: object, **kwargs: object) -> object:
            del args, kwargs
            raise RuntimeError("simulated reference query failure")

        monkeypatch.setattr(db, "scalar", fail_reference_query)
        with pytest.raises(MediaCleanupDeleteError) as exc_info:
            execute_media_cleanup_delete(db, **_snapshot(preview))

    assert exc_info.value.code == "reference_check_failed"
    assert target.exists()
    assert _digest(target) == digest
    assert not list(media_root.rglob("recovered-*"))
