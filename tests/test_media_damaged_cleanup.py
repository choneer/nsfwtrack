from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media, media_damaged_cleanup
from app.services.data_health import build_data_health_report
from app.services.media_damaged_cleanup import (
    MediaDamagedCleanupError,
    build_media_damaged_cleanup_preview,
    execute_media_damaged_cleanup,
)
from app.services.media_index import load_preferred_media_snapshot
from app.services.settings import save_app_settings


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write(media_root: Path, filename: str, content: bytes) -> Path:
    path = media_root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _media_path(path: Path, media_root: Path) -> str:
    return f"/media/{path.relative_to(media_root).as_posix()}"


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _snapshot(preview: object) -> dict[str, str]:
    media = preview.media
    return {
        "media_path": media.media_path,
        "sha256": media.sha256,
        "expected_size": str(media.size),
        "expected_device": str(media.device),
        "expected_inode": str(media.inode),
        "expected_modified_ns": str(media.modified_ns),
        "expected_changed_ns": str(media.changed_ns),
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


def test_finding_library_preview_and_get_are_complete_authenticated_and_zero_write(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    damaged_content = b"ordinary damaged image bytes"
    recovered_content = b"recovered but still damaged"
    damaged = _write(media_root, "nested/damaged.gif", damaged_content)
    recovered = _write(
        media_root,
        "nested/recovered-damaged.png",
        recovered_content,
    )
    valid = _write(media_root, "valid.gif", _gif_bytes())
    anchor = _write(
        media_root,
        ".cleanup-anchor-damaged.gif",
        b"anchor",
    )
    residue = _write(media_root, ".upload-leftover.tmp", b"residue")
    unsupported = _write(media_root, "notes.txt", b"notes")
    outside = _write(tmp_path, "outside.gif", b"outside damaged")
    symlink = media_root / "linked.gif"
    symlink.symlink_to(outside)
    damaged_path = _media_path(damaged, media_root)
    recovered_path = _media_path(recovered, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    before_db = _database_snapshot()
    before_files = {
        path: path.read_bytes()
        for path in (damaged, recovered, valid, anchor, residue, unsupported, outside)
    }
    path_reads: list[Path] = []
    original_read_bytes = Path.read_bytes

    def reject_target_path_read(path: Path) -> bytes:
        if path in {damaged, recovered}:
            path_reads.append(path)
            raise AssertionError("damaged media must be read through verified FDs")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_target_path_read)

    with SessionLocal() as db:
        report = build_data_health_report(db)
        preview = build_media_damaged_cleanup_preview(
            db,
            media_path=damaged_path,
            sha256=None,
        )
    finding_ids = {
        issue.object_id
        for issue in report.issues
        if issue.code == "media_damaged_file"
    }
    with TestClient(auth_client.app) as anonymous:
        denied = anonymous.get(
            "/data-health/damaged-media/delete-preview",
            params={"media_path": damaged_path},
            follow_redirects=False,
        )
    page = auth_client.get(
        "/data-health/damaged-media/delete-preview",
        params={"media_path": damaged_path},
    )
    library = auth_client.get(
        "/media-library",
        params={"media_status": "damaged"},
    )
    health = auth_client.get("/data-health")
    recovered_page = auth_client.get(
        "/data-health/damaged-media/delete-preview",
        params={"media_path": recovered_path},
    )

    assert finding_ids == {damaged_path, recovered_path}
    assert _media_path(valid, media_root) not in finding_ids
    assert _media_path(anchor, media_root) not in finding_ids
    assert _media_path(residue, media_root) not in finding_ids
    assert _media_path(unsupported, media_root) not in finding_ids
    assert _media_path(symlink, media_root) not in finding_ids
    assert preview.media.sha256 == _digest(damaged_content)
    assert preview.media.size == len(damaged_content)
    assert preview.media.device > 0
    assert preview.media.inode > 0
    assert preview.media.modified_ns > 0
    assert preview.media.changed_ns > 0
    assert denied.status_code == 303
    assert page.status_code == 200
    assert damaged_path in page.text
    assert _digest(damaged_content) in page.text
    assert all(label in page.text for label in ("device", "inode", "mtime", "ctime"))
    assert "永久删除，不可撤销" in page.text
    assert 'action="/data-health/damaged-media/delete"' in page.text
    assert "预览删除损坏媒体" in library.text
    assert "预览删除损坏媒体" in health.text
    assert recovered_page.status_code == 200
    assert "恢复文件" in recovered_page.text
    assert 'action="/data-health/damaged-media/delete"' in recovered_page.text
    assert auth_client.get("/data-health/damaged-media/delete").status_code == 405
    assert path_reads == []
    assert _database_snapshot() == before_db
    assert {
        path: original_read_bytes(path) for path in before_files
    } == before_files


def test_referenced_target_only_shows_c1_guidance_and_cannot_be_forged(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write(media_root, "referenced.gif", b"damaged referenced")
    media_path = _media_path(target, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Referenced Item", cover_path=media_path),
                Creator(
                    name="Referenced Creator",
                    type="person",
                    avatar_path=media_path,
                ),
            ]
        )
        db.commit()
        preview = build_media_damaged_cleanup_preview(
            db,
            media_path=media_path,
            sha256=_digest(b"damaged referenced"),
        )
    before_db = _database_snapshot()

    page = auth_client.get(
        "/data-health/damaged-media/delete-preview",
        params={"media_path": media_path},
    )
    forged = auth_client.post(
        "/data-health/damaged-media/delete",
        data={**_snapshot(preview), "confirm": "1"},
        follow_redirects=True,
    )

    assert preview.reference_count == 2
    assert page.status_code == 200
    assert "Phase 3-C1 修复或清除" in page.text
    assert "Referenced Item" in page.text
    assert "Referenced Creator" in page.text
    assert "/data-health/media-reference/repair?object_type=item_cover" in page.text
    assert "/data-health/media-reference/repair?object_type=creator_avatar" in page.text
    assert 'action="/data-health/damaged-media/delete"' not in page.text
    assert "写锁内发现封面或头像引用" in forged.text
    assert target.read_bytes() == b"damaged referenced"
    assert _database_snapshot() == before_db


@pytest.mark.parametrize(
    ("filename", "kind", "expected_code"),
    [
        ("valid.gif", "valid", "not_damaged"),
        (".cleanup-anchor-invalid.gif", "damaged", "not_damaged"),
        (".upload-invalid.tmp", "damaged", "invalid_request"),
        ("unsupported.txt", "damaged", "invalid_request"),
        ("directory.gif", "directory", "not_damaged"),
        ("linked.gif", "symlink", "not_damaged"),
        ("missing.gif", "missing", "not_damaged"),
    ],
)
def test_preview_rejects_valid_anchor_residue_skips_and_non_files(
    filename: str,
    kind: str,
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    target = media_root / filename
    if kind == "valid":
        target.write_bytes(_gif_bytes())
    elif kind == "damaged":
        target.write_bytes(b"damaged")
    elif kind == "directory":
        target.mkdir()
    elif kind == "symlink":
        outside = _write(tmp_path, "outside.gif", b"outside")
        target.symlink_to(outside)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    with SessionLocal() as db, pytest.raises(MediaDamagedCleanupError) as exc_info:
        build_media_damaged_cleanup_preview(
            db,
            media_path=f"/media/{filename}",
            sha256=None,
        )

    assert exc_info.value.code == expected_code
    assert _database_snapshot() == ((), ())
    if kind != "missing":
        assert target.exists() or target.is_symlink()


def test_standard_and_strict_confirmation_delete_only_the_selected_file(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write(media_root, "delete.gif", b"delete this damaged file")
    other = _write(media_root, "keep.png", b"keep this damaged file")
    valid = _write(media_root, "keep-valid.gif", _gif_bytes(3))
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_damaged_cleanup_preview(
            db,
            media_path=_media_path(target, media_root),
            sha256=_digest(b"delete this damaged file"),
        )
    before_db = _database_snapshot()

    rejected = auth_client.post(
        "/data-health/damaged-media/delete",
        data=_snapshot(preview),
        follow_redirects=True,
    )
    assert rejected.status_code == 200
    assert target.exists()

    accepted = auth_client.post(
        "/data-health/damaged-media/delete",
        data={**_snapshot(preview), "confirm": "1"},
        follow_redirects=True,
    )
    assert "已永久删除损坏媒体" in accepted.text
    assert not target.exists()
    assert other.read_bytes() == b"keep this damaged file"
    assert valid.read_bytes() == _gif_bytes(3)
    assert _database_snapshot() == before_db
    with SessionLocal() as db:
        snapshot = load_preferred_media_snapshot(db)
        assert snapshot.source == "index"
        assert snapshot.status.last_refresh_source == "post_cleanup"
        assert _media_path(target, media_root) not in {
            entry.media_path for entry in snapshot.scan.entries
        }

    strict_target = _write(media_root, "strict.gif", b"strict damaged")
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})
        strict_preview = build_media_damaged_cleanup_preview(
            db,
            media_path=_media_path(strict_target, media_root),
            sha256=_digest(b"strict damaged"),
        )
    wrong = auth_client.post(
        "/data-health/damaged-media/delete",
        data={
            **_snapshot(strict_preview),
            "confirm": "1",
            "confirmation_text": "confirm",
        },
        follow_redirects=True,
    )
    assert "CONFIRM" in wrong.text
    assert strict_target.exists()
    right = auth_client.post(
        "/data-health/damaged-media/delete",
        data={
            **_snapshot(strict_preview),
            "confirm": "1",
            "confirmation_text": "CONFIRM",
        },
        follow_redirects=True,
    )
    assert "已永久删除损坏媒体" in right.text
    assert not strict_target.exists()


def test_forged_identity_sha_change_valid_replacement_and_symlink_are_stale(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write(media_root, "stale.gif", b"initial damaged")
    media_path = _media_path(target, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        initial = build_media_damaged_cleanup_preview(
            db,
            media_path=media_path,
            sha256=_digest(b"initial damaged"),
        )
        forged = _snapshot(initial)
        forged["expected_inode"] = str(initial.media.inode + 1)
        with pytest.raises(MediaDamagedCleanupError) as forged_error:
            execute_media_damaged_cleanup(db, **forged)
        assert forged_error.value.code == "stale_media"

        target.write_bytes(b"changed damaged bytes")
        with pytest.raises(MediaDamagedCleanupError) as changed_error:
            execute_media_damaged_cleanup(db, **_snapshot(initial))
        assert changed_error.value.code == "stale_media"

        target.unlink()
        target.write_bytes(_gif_bytes())
        with pytest.raises(MediaDamagedCleanupError) as valid_error:
            execute_media_damaged_cleanup(db, **_snapshot(initial))
        assert valid_error.value.code == "stale_media"

        target.unlink()
        outside = _write(tmp_path, "external.gif", b"external must remain")
        target.symlink_to(outside)
        with pytest.raises(MediaDamagedCleanupError) as symlink_error:
            execute_media_damaged_cleanup(db, **_snapshot(initial))
        assert symlink_error.value.code == "stale_media"

    assert target.is_symlink()
    assert outside.read_bytes() == b"external must remain"
    assert _database_snapshot() == ((), ())


def test_forged_path_digest_and_parent_replacement_during_fd_read_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write(media_root, "nested/raced.gif", b"original damaged")
    external_dir = tmp_path / "external"
    external = _write(external_dir, "raced.gif", b"external must not be read")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    with SessionLocal() as db:
        with pytest.raises(MediaDamagedCleanupError) as path_error:
            build_media_damaged_cleanup_preview(
                db,
                media_path="/media/../external/raced.gif",
                sha256=None,
            )
        assert path_error.value.code == "invalid_request"
        with pytest.raises(MediaDamagedCleanupError) as digest_error:
            build_media_damaged_cleanup_preview(
                db,
                media_path=_media_path(target, media_root),
                sha256="0" * 64,
            )
        assert digest_error.value.code == "not_damaged"

    original_read = local_media._read_scan_file_descriptor
    replaced = False

    def replace_parent_after_fd_read(file_descriptor: int) -> bytes:
        nonlocal replaced
        content = original_read(file_descriptor)
        if not replaced:
            nested = media_root / "nested"
            nested.rename(media_root / "moved")
            nested.symlink_to(external_dir, target_is_directory=True)
            replaced = True
        return content

    monkeypatch.setattr(
        local_media,
        "_read_scan_file_descriptor",
        replace_parent_after_fd_read,
    )
    with SessionLocal() as db, pytest.raises(MediaDamagedCleanupError) as race_error:
        build_media_damaged_cleanup_preview(
            db,
            media_path="/media/nested/raced.gif",
            sha256=None,
        )

    assert race_error.value.code == "not_damaged"
    assert replaced is True
    assert (media_root / "nested").is_symlink()
    assert (media_root / "moved/raced.gif").read_bytes() == b"original damaged"
    assert external.read_bytes() == b"external must not be read"
    assert _database_snapshot() == ((), ())


def test_reference_race_is_rejected_after_begin_immediate_before_unlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    content = b"reference race damaged"
    target = _write(media_root, "reference-race.gif", content)
    media_path = _media_path(target, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        initial = build_media_damaged_cleanup_preview(
            db,
            media_path=media_path,
            sha256=_digest(content),
        )

    original_build = media_damaged_cleanup.build_media_damaged_cleanup_preview
    injected = False

    def build_then_reference(db: object, **values: object) -> object:
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
        media_damaged_cleanup,
        "build_media_damaged_cleanup_preview",
        build_then_reference,
    )
    begin_seen = False
    with SessionLocal() as db:
        original_execute = db.execute

        def track_begin(statement: object, *args: object, **kwargs: object) -> object:
            nonlocal begin_seen
            if str(statement) == "BEGIN IMMEDIATE":
                begin_seen = True
            return original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(db, "execute", track_begin)
        with pytest.raises(MediaDamagedCleanupError) as exc_info:
            execute_media_damaged_cleanup(db, **_snapshot(initial))

    assert exc_info.value.code == "media_referenced"
    assert begin_seen is True
    assert target.read_bytes() == content
    with SessionLocal() as db:
        assert db.query(Item).filter(Item.cover_path == media_path).count() == 1


def test_identity_race_after_locked_reference_check_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write(media_root, "identity-race.gif", b"before damaged")
    media_path = _media_path(target, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        initial = build_media_damaged_cleanup_preview(
            db,
            media_path=media_path,
            sha256=_digest(b"before damaged"),
        )

    original_load = media_damaged_cleanup._load_references
    calls = 0

    def replace_after_locked_check(db: object, path: str) -> object:
        nonlocal calls
        result = original_load(db, path)
        calls += 1
        if calls == 2:
            target.unlink()
            target.write_bytes(b"replacement damaged")
        return result

    monkeypatch.setattr(media_damaged_cleanup, "_load_references", replace_after_locked_check)
    with SessionLocal() as db, pytest.raises(MediaDamagedCleanupError) as exc_info:
        execute_media_damaged_cleanup(db, **_snapshot(initial))

    assert exc_info.value.code == "stale_media"
    assert target.read_bytes() == b"replacement damaged"
    assert _database_snapshot() == ((), ())


def test_unlink_failure_keeps_target_and_fsync_failure_reports_deleted_warning(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    unlink_target = _write(media_root, "unlink.gif", b"unlink failure")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        unlink_preview = build_media_damaged_cleanup_preview(
            db,
            media_path=_media_path(unlink_target, media_root),
            sha256=_digest(b"unlink failure"),
        )
    before_db = _database_snapshot()
    original_unlink = local_media.os.unlink

    def fail_unlink(path: str, *, dir_fd: int | None = None) -> None:
        del path, dir_fd
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(local_media.os, "unlink", fail_unlink)
    failed = auth_client.post(
        "/data-health/damaged-media/delete",
        data={**_snapshot(unlink_preview), "confirm": "1"},
        follow_redirects=True,
    )
    assert "unlink 未成功" in failed.text
    assert unlink_target.read_bytes() == b"unlink failure"
    assert _database_snapshot() == before_db

    monkeypatch.setattr(local_media.os, "unlink", original_unlink)
    sync_target = _write(media_root, "sync.gif", b"sync warning")
    with SessionLocal() as db:
        sync_preview = build_media_damaged_cleanup_preview(
            db,
            media_path=_media_path(sync_target, media_root),
            sha256=_digest(b"sync warning"),
        )
    original_fsync = local_media.os.fsync

    def fail_directory_fsync(file_descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(file_descriptor).st_mode):
            raise OSError("simulated directory sync failure")
        original_fsync(file_descriptor)

    monkeypatch.setattr(local_media.os, "fsync", fail_directory_fsync)
    warned = auth_client.post(
        "/data-health/damaged-media/delete",
        data={**_snapshot(sync_preview), "confirm": "1"},
        follow_redirects=True,
    )
    assert "已永久删除损坏媒体" in warned.text
    assert "sync_failed" in warned.text
    assert "已经删除" in warned.text
    assert not sync_target.exists()
    assert unlink_target.exists()
    assert _database_snapshot() == before_db


@pytest.mark.parametrize("failure", ["lock", "query"])
def test_lock_and_locked_reference_query_fail_closed_before_unlink(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    content = f"{failure} failure damaged".encode()
    target = _write(media_root, f"{failure}-failure.gif", content)
    media_path = _media_path(target, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_damaged_cleanup_preview(
            db,
            media_path=media_path,
            sha256=_digest(content),
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
            original_load = media_damaged_cleanup._load_references
            calls = 0

            def fail_locked_query(session: object, path: str) -> object:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("simulated locked query failure")
                return original_load(session, path)

            monkeypatch.setattr(
                media_damaged_cleanup,
                "_load_references",
                fail_locked_query,
            )

        with pytest.raises(MediaDamagedCleanupError) as exc_info:
            execute_media_damaged_cleanup(db, **_snapshot(preview))

    assert exc_info.value.code == "reference_check_failed"
    assert target.read_bytes() == content
    assert _database_snapshot() == ((), ())
