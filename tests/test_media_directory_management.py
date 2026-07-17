from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media
from app.services import media_operation_lock
from app.services.media_index import get_media_index_status
from app.services.media_directory_management import (
    MediaDirectoryError,
    build_directory_snapshot,
    execute_directory_mutation,
)


def _gif(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"GIF89a\x01\x00\x01\x00" + b"x" + b";")


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
