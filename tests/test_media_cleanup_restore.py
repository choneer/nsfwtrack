from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media
from app.services.media_cleanup_restore import (
    MediaCleanupRestoreError,
    build_media_cleanup_restore_preview,
    execute_media_cleanup_restore,
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


def test_restore_preview_is_authenticated_complete_and_zero_write(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    anchor = _write_gif(
        media_root,
        "Recovery/.cleanup-anchor-preview.gif",
        extra=7,
    )
    media_path = _media_path(anchor, media_root)
    digest = _digest(anchor)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Preview Cover", cover_path=media_path),
                Creator(
                    name="Preview Avatar",
                    type="person",
                    avatar_path=media_path,
                ),
            ]
        )
        db.commit()
        before_rows = (
            tuple((row.id, row.cover_path) for row in db.query(Item).all()),
            tuple((row.id, row.avatar_path) for row in db.query(Creator).all()),
        )
    before_bytes = anchor.read_bytes()
    before_names = tuple(path.name for path in anchor.parent.iterdir())

    with TestClient(auth_client.app) as anonymous:
        denied = anonymous.get(
            "/media-library/recovery/preview",
            params={"media_path": media_path, "sha256": digest},
            follow_redirects=False,
        )
    center = auth_client.get("/media-library/recovery")
    preview = auth_client.get(
        "/media-library/recovery/preview",
        params={"media_path": media_path, "sha256": digest},
    )

    assert denied.status_code == 303
    assert center.status_code == 200
    assert "预览单项恢复" in center.text
    assert preview.status_code == 200
    assert 'data-cleanup-restore-preview' in preview.text
    assert media_path in preview.text
    assert digest in preview.text
    assert "Preview Cover" in preview.text
    assert "Preview Avatar" in preview.text
    assert "device" in preview.text
    assert "inode" in preview.text
    assert "mtime" in preview.text
    assert "ctime" in preview.text
    assert 'action="/media-library/recovery/restore"' in preview.text
    assert auth_client.get("/media-library/recovery/restore").status_code == 405

    with SessionLocal() as db:
        after_rows = (
            tuple((row.id, row.cover_path) for row in db.query(Item).all()),
            tuple((row.id, row.avatar_path) for row in db.query(Creator).all()),
        )
    assert after_rows == before_rows
    assert anchor.read_bytes() == before_bytes
    assert tuple(path.name for path in anchor.parent.iterdir()) == before_names


def test_confirmed_restore_migrates_all_references_without_overwrite(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    anchor = _write_gif(
        media_root,
        "Recovery/.cleanup-anchor-restore.gif",
        extra=9,
    )
    media_path = _media_path(anchor, media_root)
    digest = _digest(anchor)
    collision = anchor.parent / f"recovered-{digest[:12]}-collision.gif"
    collision.write_bytes(_gif_bytes(99))
    tokens = iter(("collision", "unique"))
    sync_kinds: list[str] = []
    original_fsync = local_media.os.fsync

    def track_fsync(file_descriptor: int) -> None:
        mode = os.fstat(file_descriptor).st_mode
        if stat.S_ISREG(mode):
            sync_kinds.append("file")
        elif stat.S_ISDIR(mode):
            sync_kinds.append("directory")
        original_fsync(file_descriptor)

    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    monkeypatch.setattr(local_media.secrets, "token_hex", lambda _: next(tokens))
    monkeypatch.setattr(local_media.os, "fsync", track_fsync)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Cover One", cover_path=media_path),
                Item(title="Cover Two", cover_path=media_path),
                Creator(name="Avatar One", type="person", avatar_path=media_path),
                Creator(name="Avatar Two", type="person", avatar_path=media_path),
            ]
        )
        db.commit()
        preview = build_media_cleanup_restore_preview(
            db,
            media_path=media_path,
            sha256=digest,
        )

    missing_confirm = auth_client.post(
        "/media-library/recovery/restore",
        data=_snapshot(preview),
        follow_redirects=True,
    )
    assert "危险操作已拒绝" in missing_confirm.text
    assert anchor.exists()
    assert collision.read_bytes() == _gif_bytes(99)

    restored = auth_client.post(
        "/media-library/recovery/restore",
        data={**_snapshot(preview), "confirm": "1"},
        follow_redirects=True,
    )

    recovered = anchor.parent / f"recovered-{digest[:12]}-unique.gif"
    recovered_path = _media_path(recovered, media_root)
    assert restored.status_code == 200
    assert "迁移条目封面 2 个、创作者头像 2 个" in restored.text
    assert not anchor.exists()
    assert recovered.exists()
    assert recovered.read_bytes() == _gif_bytes(9)
    assert _digest(recovered) == digest
    assert collision.read_bytes() == _gif_bytes(99)
    assert "file" in sync_kinds
    assert "directory" in sync_kinds
    with SessionLocal() as db:
        assert {row.cover_path for row in db.query(Item).all()} == {recovered_path}
        assert {row.avatar_path for row in db.query(Creator).all()} == {
            recovered_path
        }
        assert db.query(Item).filter(Item.cover_path == media_path).count() == 0
        assert db.query(Creator).filter(Creator.avatar_path == media_path).count() == 0


def test_strict_restore_requires_exact_confirm_and_unreferenced_anchor_succeeds(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    anchor = _write_gif(media_root, ".cleanup-anchor-strict.gif", extra=10)
    media_path = _media_path(anchor, media_root)
    digest = _digest(anchor)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})
        preview = build_media_cleanup_restore_preview(
            db,
            media_path=media_path,
            sha256=digest,
        )
    preview_page = auth_client.get(
        "/media-library/recovery/preview",
        params={"media_path": media_path, "sha256": digest},
    )
    assert "data-strict-confirm-message" in preview_page.text

    rejected = auth_client.post(
        "/media-library/recovery/restore",
        data={
            **_snapshot(preview),
            "confirm": "1",
            "confirmation_text": "confirm",
        },
        follow_redirects=True,
    )
    assert "CONFIRM" in rejected.text
    assert anchor.exists()

    accepted = auth_client.post(
        "/media-library/recovery/restore",
        data={
            **_snapshot(preview),
            "confirm": "1",
            "confirmation_text": "CONFIRM",
        },
        follow_redirects=True,
    )
    assert accepted.status_code == 200
    assert "迁移条目封面 0 个、创作者头像 0 个" in accepted.text
    assert not anchor.exists()
    recovered = list(media_root.glob("recovered-*.gif"))
    assert len(recovered) == 1
    assert _digest(recovered[0]) == digest


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    [
        ("damaged", "anchor_damaged"),
        ("symlink", "anchor_damaged"),
        ("wrong_extension", "invalid_request"),
        ("recovered", "not_anchor"),
        ("ordinary", "not_anchor"),
    ],
)
def test_preview_rejects_nonrestorable_targets(
    kind: str,
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    ordinary = _write_gif(media_root, "ordinary.gif", extra=1)
    if kind == "damaged":
        target = media_root / ".cleanup-anchor-damaged.gif"
        target.write_bytes(b"damaged")
    elif kind == "symlink":
        target = media_root / ".cleanup-anchor-symlink.gif"
        target.symlink_to(ordinary)
    elif kind == "wrong_extension":
        target = media_root / ".cleanup-anchor-wrong.tmp"
        target.write_bytes(_gif_bytes(2))
    elif kind == "recovered":
        target = _write_gif(media_root, "recovered-normal.gif", extra=3)
    else:
        target = ordinary
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    before_paths = set(media_root.rglob("*"))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    with SessionLocal() as db, pytest.raises(MediaCleanupRestoreError) as exc_info:
        build_media_cleanup_restore_preview(
            db,
            media_path=_media_path(target, media_root),
            sha256=digest,
        )
    assert exc_info.value.code == expected_code
    assert set(media_root.rglob("*")) == before_paths


def test_stale_or_forged_identity_is_rejected_before_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    anchor = _write_gif(media_root, ".cleanup-anchor-stale.gif", extra=11)
    media_path = _media_path(anchor, media_root)
    digest = _digest(anchor)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        preview = build_media_cleanup_restore_preview(
            db,
            media_path=media_path,
            sha256=digest,
        )
        forged = _snapshot(preview)
        forged["expected_inode"] = str(preview.anchor.inode + 1)
        with pytest.raises(MediaCleanupRestoreError) as forged_error:
            execute_media_cleanup_restore(db, **forged)
        assert forged_error.value.code == "stale_anchor"

        os.utime(anchor, ns=(preview.anchor.modified_ns, preview.anchor.modified_ns + 1))
        with pytest.raises(MediaCleanupRestoreError) as stale_error:
            execute_media_cleanup_restore(db, **_snapshot(preview))
        assert stale_error.value.code == "stale_anchor"

    assert anchor.exists()
    assert not list(media_root.rglob("recovered-*"))


def test_database_failure_rolls_back_references_and_removes_recovery_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    anchor = _write_gif(media_root, ".cleanup-anchor-db-failure.gif", extra=12)
    media_path = _media_path(anchor, media_root)
    digest = _digest(anchor)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        item = Item(title="DB Failure", cover_path=media_path)
        creator = Creator(name="DB Failure", type="person", avatar_path=media_path)
        db.add_all([item, creator])
        db.commit()
        item_id = item.id
        creator_id = creator.id
        preview = build_media_cleanup_restore_preview(
            db,
            media_path=media_path,
            sha256=digest,
        )

        def fail_commit() -> None:
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(MediaCleanupRestoreError) as exc_info:
            execute_media_cleanup_restore(db, **_snapshot(preview))
        assert exc_info.value.code == "database_failed"
        assert db.get(Item, item_id).cover_path == media_path
        assert db.get(Creator, creator_id).avatar_path == media_path

    assert anchor.exists()
    assert _digest(anchor) == digest
    assert not list(media_root.rglob("recovered-*"))


def test_anchor_delete_failure_retains_anchor_but_references_stay_recovered(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    anchor = _write_gif(media_root, ".cleanup-anchor-delete-failure.gif", extra=13)
    media_path = _media_path(anchor, media_root)
    digest = _digest(anchor)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    original_delete = local_media.delete_validated_local_media_file

    def fail_anchor_delete(record: local_media.ValidatedLocalMediaFile) -> None:
        if record.media_path == media_path:
            raise local_media.LocalMediaDeleteError("delete_failed")
        original_delete(record)

    monkeypatch.setattr(
        local_media,
        "delete_validated_local_media_file",
        fail_anchor_delete,
    )
    with SessionLocal() as db:
        item = Item(title="Retained Anchor", cover_path=media_path)
        creator = Creator(
            name="Retained Anchor",
            type="person",
            avatar_path=media_path,
        )
        db.add_all([item, creator])
        db.commit()
        item_id = item.id
        creator_id = creator.id
        preview = build_media_cleanup_restore_preview(
            db,
            media_path=media_path,
            sha256=digest,
        )
        result = execute_media_cleanup_restore(db, **_snapshot(preview))

        assert result.anchor_removed is False
        assert result.anchor_retained_path == media_path
        assert result.anchor_removal_code == "delete_failed"
        assert db.get(Item, item_id).cover_path == result.recovered_path
        assert db.get(Creator, creator_id).avatar_path == result.recovered_path
        assert db.query(Item).filter(Item.cover_path == media_path).count() == 0
        assert db.query(Creator).filter(Creator.avatar_path == media_path).count() == 0

    recovered = media_root / result.recovered_path.removeprefix("/media/")
    assert anchor.exists()
    assert recovered.exists()
    assert _digest(anchor) == _digest(recovered) == digest


def test_ordinary_interactive_writes_cannot_create_anchor_references(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    anchor = _write_gif(media_root, ".cleanup-anchor-internal.gif", extra=14)
    media_path = _media_path(anchor, media_root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        item = Item(title="Ordinary Item")
        existing_anchor_item = Item(title="Existing Anchor", cover_path=media_path)
        creator = Creator(name="Ordinary Creator", type="person")
        db.add_all([item, existing_anchor_item, creator])
        db.commit()
        item_id = item.id
        existing_id = existing_anchor_item.id
        creator_id = creator.id

    set_cover = auth_client.post(
        "/media-library/set-item-cover",
        data={"item_id": item_id, "media_path": media_path},
        follow_redirects=True,
    )
    set_avatar = auth_client.post(
        "/media-library/set-creator-avatar",
        data={"creator_id": creator_id, "media_path": media_path},
        follow_redirects=True,
    )
    create_item = auth_client.post(
        "/api/items",
        json={"title": "Rejected Anchor", "cover_path": media_path},
    )
    create_creator = auth_client.post(
        "/api/creators",
        json={"name": "Rejected Anchor", "avatar_path": media_path},
    )
    update_to_anchor = auth_client.put(
        f"/api/items/{item_id}",
        json={"cover_path": media_path},
    )
    preserve_existing = auth_client.put(
        f"/api/items/{existing_id}",
        json={"title": "Existing Anchor Renamed", "cover_path": media_path},
    )

    assert "无法关联媒体" in set_cover.text
    assert "无法关联媒体" in set_avatar.text
    assert create_item.status_code == 422
    assert create_creator.status_code == 422
    assert update_to_anchor.status_code == 422
    assert preserve_existing.status_code == 200
    with SessionLocal() as db:
        assert db.get(Item, item_id).cover_path is None
        assert db.get(Creator, creator_id).avatar_path is None
        assert db.get(Item, existing_id).cover_path == media_path
