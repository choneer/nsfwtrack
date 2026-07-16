from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media, media_file_rename
from app.services.media_file_rename import (
    MediaFileRenameError,
    build_media_file_rename_preview,
    execute_media_file_rename,
)
from app.services.media_index import load_preferred_media_snapshot
from app.services.settings import save_app_settings


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(root: Path, relative_path: str, *, extra: int = 0) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def _preview(
    source_path: str,
    target_directory: str,
    target_basename: str | None = None,
) -> media_file_rename.MediaFileRenamePreview:
    with SessionLocal() as db:
        return build_media_file_rename_preview(
            db,
            media_path=source_path,
            target_directory=target_directory,
            target_basename=target_basename,
        )


def _service_args(
    preview: media_file_rename.MediaFileRenamePreview,
) -> dict[str, object]:
    return {
        "media_path": preview.source.media_path,
        "target_directory": preview.target_directory.media_path,
        "target_basename": preview.target_basename,
        "expected_sha256": preview.source.sha256,
        "expected_mode": preview.source.mode,
        "expected_size": preview.source.size,
        "expected_device": preview.source.device,
        "expected_inode": preview.source.inode,
        "expected_modified_ns": preview.source.modified_ns,
        "expected_changed_ns": preview.source.changed_ns,
        "expected_source_directory_token": local_media.local_media_directory_identity_token(
            preview.source
        ),
        "expected_target_directory_token": local_media.local_media_directory_identity_token(
            preview.target_directory
        ),
        "expected_item_reference_ids": [
            str(value) for value in preview.item_reference_ids
        ],
        "expected_creator_reference_ids": [
            str(value) for value in preview.creator_reference_ids
        ],
    }


def _form(preview: media_file_rename.MediaFileRenamePreview) -> dict[str, object]:
    args = _service_args(preview)
    return {
        "media_path": args["media_path"],
        "target_directory": args["target_directory"],
        "target_basename": args["target_basename"],
        "expected_sha256": args["expected_sha256"],
        "expected_mode": args["expected_mode"],
        "expected_size": args["expected_size"],
        "expected_device": args["expected_device"],
        "expected_inode": args["expected_inode"],
        "expected_modified_ns": args["expected_modified_ns"],
        "expected_changed_ns": args["expected_changed_ns"],
        "expected_source_directory_token": args["expected_source_directory_token"],
        "expected_target_directory_token": args["expected_target_directory_token"],
        "item_reference_id": args["expected_item_reference_ids"],
        "creator_reference_id": args["expected_creator_reference_ids"],
        "confirm": "1",
    }


def _references() -> tuple[tuple[str | None, ...], tuple[str | None, ...]]:
    with SessionLocal() as db:
        return (
            tuple(db.scalars(select(Item.cover_path).order_by(Item.id)).all()),
            tuple(db.scalars(select(Creator.avatar_path).order_by(Creator.id)).all()),
        )


def test_move_preview_and_apply_migrate_every_reference_without_overwrite(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "source/Original.gif", extra=4)
    (root / "target" / "nested").mkdir(parents=True)
    source_path = "/media/source/Original.gif"
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="First", cover_path=source_path),
                Item(title="Second", cover_path=source_path),
                Creator(name="One", type="person", avatar_path=source_path),
                Creator(name="Two", type="studio", avatar_path=source_path),
            ]
        )
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)

    preview_response = auth_client.get(
        "/media-library/detail/move",
        params={
            "media_path": source_path,
            "target_directory": "/media/target/nested",
            "target_basename": "Moved.gif",
            "next": "/media-library/directories?directory=%2Fmedia%2Fsource&dir_page=2",
        },
    )
    assert preview_response.status_code == 200
    assert "data-media-file-move-preview" in preview_response.text
    assert "/media/target/nested/Moved.gif" in preview_response.text
    assert 'name="expected_source_directory_token"' in preview_response.text
    assert 'name="expected_target_directory_token"' in preview_response.text

    preview = _preview(source_path, "/media/target/nested", "Moved.gif")
    response = auth_client.post(
        "/media-library/detail/move",
        data={
            **_form(preview),
            "next": "/media-library/directories?directory=%2Fmedia%2Fsource&dir_page=2",
        },
        follow_redirects=False,
    )

    target = root / "target" / "nested" / "Moved.gif"
    assert response.status_code == 303
    assert not source.exists()
    assert target.read_bytes() == _gif_bytes(4)
    assert _references() == (
        ("/media/target/nested/Moved.gif",) * 2,
        ("/media/target/nested/Moved.gif",) * 2,
    )
    with SessionLocal() as db:
        snapshot = load_preferred_media_snapshot(db)
        assert snapshot.source == "index"
        assert snapshot.status.last_refresh_source == "post_move"
        indexed_paths = {entry.media_path for entry in snapshot.scan.entries}
        assert source_path not in indexed_paths
        assert indexed_paths == {"/media/target/nested/Moved.gif"}
    assert "directory%3D%252Fmedia%252Fsource" in response.headers["location"]


def test_move_blank_basename_keeps_name_and_unreferenced_file_is_supported(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "source/Keep.gif", extra=3)
    (root / "target").mkdir()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview("/media/source/Keep.gif", "/media/target", None)

    with SessionLocal() as db:
        result = execute_media_file_rename(db, **_service_args(preview))

    assert result.target_path == "/media/target/Keep.gif"
    assert result.migrated_items == result.migrated_creators == 0
    assert not source.exists()
    assert (root / "target" / "Keep.gif").exists()


@pytest.mark.parametrize(
    ("target_directory", "expected_code"),
    [
        ("/media/missing", "target_directory_unavailable"),
        ("/media/file.gif", "target_directory_unavailable"),
        ("/media/linked", "target_directory_unavailable"),
        ("/media/.cleanup-anchor-hidden", "invalid_target_directory"),
        ("/media/.upload-hidden", "invalid_target_directory"),
        ("/media/../outside", "invalid_target_directory"),
        ("https://example.invalid/target", "invalid_target_directory"),
    ],
)
def test_move_rejects_nonordinary_or_out_of_root_target_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target_directory: str,
    expected_code: str,
) -> None:
    root = tmp_path / "media"
    _write_gif(root, "source/Source.gif")
    _write_gif(root, "file.gif", extra=2)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".cleanup-anchor-hidden").mkdir()
    (root / ".upload-hidden").mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)

    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as exc_info:
        build_media_file_rename_preview(
            db,
            media_path="/media/source/Source.gif",
            target_directory=target_directory,
            target_basename="Target.gif",
        )

    assert exc_info.value.code == expected_code
    assert (root / "source" / "Source.gif").exists()
    assert not (outside / "Target.gif").exists()


def test_move_rejects_target_claim_and_previewed_directory_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "source/Source.gif", extra=5)
    target_directory = root / "target"
    target_directory.mkdir()
    source_path = "/media/source/Source.gif"
    with SessionLocal() as db:
        db.add(Item(title="Protected", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    claimed_preview = _preview(source_path, "/media/target", "Claimed.gif")
    (target_directory / "Claimed.gif").write_bytes(b"external claimant")

    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as claimed:
        execute_media_file_rename(db, **_service_args(claimed_preview))
    assert claimed.value.code == "target_exists"
    assert (target_directory / "Claimed.gif").read_bytes() == b"external claimant"
    (target_directory / "Claimed.gif").unlink()

    replaced_preview = _preview(source_path, "/media/target", "Moved.gif")
    target_directory.rename(root / "old-target")
    target_directory.mkdir()
    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as replaced:
        execute_media_file_rename(db, **_service_args(replaced_preview))
    assert replaced.value.code == "stale_preview"
    assert source.exists()
    assert not (target_directory / "Moved.gif").exists()
    assert _references()[0] == (source_path,)


def test_move_does_not_delete_target_claimed_after_link(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "source/Source.gif", extra=8)
    target_directory = root / "target"
    target_directory.mkdir()
    source_path = "/media/source/Source.gif"
    target = target_directory / "Moved.gif"
    with SessionLocal() as db:
        db.add(Item(title="Protected", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(source_path, "/media/target", "Moved.gif")
    original_create = local_media.create_validated_local_media_hardlink

    @contextmanager
    def claim_target(
        record: local_media.ValidatedLocalMediaFile,
        target_media_path: str,
        *,
        target_directory: local_media.ValidatedLocalMediaDirectory | None = None,
    ):
        with original_create(
            record,
            target_media_path,
            target_directory=target_directory,
        ) as link:
            target.unlink()
            target.write_bytes(b"external-after-link")
            yield link

    monkeypatch.setattr(
        local_media,
        "create_validated_local_media_hardlink",
        claim_target,
    )
    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as exc_info:
        execute_media_file_rename(db, **_service_args(preview))

    assert exc_info.value.code == "stale_source"
    assert source.exists()
    assert target.read_bytes() == b"external-after-link"
    assert _references()[0] == (source_path,)


@pytest.mark.parametrize("replacement", ["directory", "symlink"])
def test_move_target_parent_replacement_during_publish_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    replacement: str,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "source/Source.gif", extra=81)
    target_directory = root / "target"
    target_directory.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    external = _write_gif(outside, "External.gif", extra=82)
    source_path = "/media/source/Source.gif"
    with SessionLocal() as db:
        db.add(Item(title="Parent Race", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(source_path, "/media/target", "Moved.gif")
    original_create = local_media.create_validated_local_media_hardlink

    @contextmanager
    def replace_parent(
        record: local_media.ValidatedLocalMediaFile,
        target_media_path: str,
        *,
        target_directory: local_media.ValidatedLocalMediaDirectory | None = None,
    ):
        (root / "target").rename(root / "old-target")
        if replacement == "directory":
            (root / "target").mkdir()
        else:
            (root / "target").symlink_to(outside, target_is_directory=True)
        with original_create(
            record,
            target_media_path,
            target_directory=target_directory,
        ) as link:
            yield link

    monkeypatch.setattr(
        local_media,
        "create_validated_local_media_hardlink",
        replace_parent,
    )
    with SessionLocal() as db, pytest.raises(MediaFileRenameError):
        execute_media_file_rename(db, **_service_args(preview))

    assert source.exists()
    assert not (root / "old-target" / "Moved.gif").exists()
    assert not (outside / "Moved.gif").exists()
    assert external.read_bytes() == _gif_bytes(82)
    assert _references()[0] == (source_path,)


@pytest.mark.parametrize("replacement", ["directory", "symlink"])
def test_move_source_parent_replacement_during_publish_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    replacement: str,
) -> None:
    root = tmp_path / "media"
    source_directory = root / "source"
    source = _write_gif(root, "source/Source.gif", extra=83)
    (root / "target").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    external = _write_gif(outside, "External.gif", extra=84)
    source_path = "/media/source/Source.gif"
    with SessionLocal() as db:
        db.add(Item(title="Source Parent Race", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(source_path, "/media/target", "Moved.gif")
    original_create = local_media.create_validated_local_media_hardlink

    @contextmanager
    def replace_parent(
        record: local_media.ValidatedLocalMediaFile,
        target_media_path: str,
        *,
        target_directory: local_media.ValidatedLocalMediaDirectory | None = None,
    ):
        source_directory.rename(root / "old-source")
        if replacement == "directory":
            source_directory.mkdir()
        else:
            source_directory.symlink_to(outside, target_is_directory=True)
        with original_create(
            record,
            target_media_path,
            target_directory=target_directory,
        ) as link:
            yield link

    monkeypatch.setattr(
        local_media,
        "create_validated_local_media_hardlink",
        replace_parent,
    )
    with SessionLocal() as db, pytest.raises(MediaFileRenameError):
        execute_media_file_rename(db, **_service_args(preview))

    assert (root / "old-source" / "Source.gif").read_bytes() == _gif_bytes(83)
    assert not (root / "target" / "Moved.gif").exists()
    assert not (outside / "Moved.gif").exists()
    assert external.read_bytes() == _gif_bytes(84)
    assert _references()[0] == (source_path,)


def test_move_rejects_reference_changes_after_preview(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "source/Source.gif", extra=85)
    (root / "target").mkdir()
    source_path = "/media/source/Source.gif"
    with SessionLocal() as db:
        db.add(Item(title="Initial", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(source_path, "/media/target", "Moved.gif")
    with SessionLocal() as db:
        db.add(Creator(name="Late", type="person", avatar_path=source_path))
        db.commit()

    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as exc_info:
        execute_media_file_rename(db, **_service_args(preview))

    assert exc_info.value.code == "stale_preview"
    assert source.exists()
    assert not (root / "target" / "Moved.gif").exists()
    assert _references() == ((source_path,), (source_path,))


def test_move_commit_ambiguity_retains_safe_paths_and_references(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "source/Source.gif", extra=9)
    (root / "target").mkdir()
    source_path = "/media/source/Source.gif"
    with SessionLocal() as setup_db:
        setup_db.add(Item(title="Commit", cover_path=source_path))
        setup_db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(source_path, "/media/target", "Moved.gif")

    with SessionLocal() as db:
        real_commit = db.commit

        def commit_then_raise() -> None:
            real_commit()
            raise RuntimeError("injected after commit")

        monkeypatch.setattr(db, "commit", commit_then_raise)
        result = execute_media_file_rename(db, **_service_args(preview))

    target = root / "target" / "Moved.gif"
    assert result.warning_code == "committed_source_retained"
    assert source.exists() and target.exists()
    assert _references()[0] == ("/media/target/Moved.gif",)

    target.unlink()
    with SessionLocal() as db:
        db.execute(
            media_file_rename.update(Item)
            .where(Item.id == 1)
            .values(cover_path=source_path)
        )
        db.commit()
    preview = _preview(source_path, "/media/target", "Unknown.gif")
    with SessionLocal() as db:
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError()))
        monkeypatch.setattr(media_file_rename, "_inspect_commit_outcome", lambda **_: "unknown")
        result = execute_media_file_rename(db, **_service_args(preview))
    assert result.warning_code == "commit_outcome_unknown"
    assert source.exists() and (root / "target" / "Unknown.gif").exists()
    assert _references()[0] == (source_path,)


def test_move_fsync_and_unlink_failures_never_break_references(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "source/Source.gif", extra=10)
    (root / "target").mkdir()
    source_path = "/media/source/Source.gif"
    with SessionLocal() as db:
        db.add(Item(title="Durability", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(source_path, "/media/target", "Fsync.gif")
    real_fsync = os.fsync
    calls = 0

    def fail_first_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(local_media.os, "fsync", fail_first_fsync)
    with SessionLocal() as db, pytest.raises(MediaFileRenameError):
        execute_media_file_rename(db, **_service_args(preview))
    assert source.exists()
    assert not (root / "target" / "Fsync.gif").exists()
    assert _references()[0] == (source_path,)

    monkeypatch.setattr(local_media.os, "fsync", real_fsync)
    preview = _preview(source_path, "/media/target", "Retained.gif")
    real_unlink = os.unlink

    def fail_source_unlink(path: str, *args: object, **kwargs: object) -> None:
        if path == "Source.gif":
            raise OSError("injected unlink failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(local_media.os, "unlink", fail_source_unlink)
    with SessionLocal() as db:
        result = execute_media_file_rename(db, **_service_args(preview))
    assert result.warning_code == "delete_failed"
    assert source.exists() and (root / "target" / "Retained.gif").exists()
    assert _references()[0] == ("/media/target/Retained.gif",)


def test_move_route_requires_exact_strict_confirmation(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "source/Strict.gif", extra=12)
    (root / "target").mkdir()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview("/media/source/Strict.gif", "/media/target", "Moved.gif")
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})

    missing = auth_client.post(
        "/media-library/detail/move",
        data=_form(preview),
        follow_redirects=False,
    )
    assert missing.status_code == 303
    assert source.exists()
    wrong = auth_client.post(
        "/media-library/detail/move",
        data={**_form(preview), "confirmation_text": "confirm"},
        follow_redirects=False,
    )
    assert wrong.status_code == 303
    assert source.exists()
    success = auth_client.post(
        "/media-library/detail/move",
        data={**_form(preview), "confirmation_text": "CONFIRM"},
        follow_redirects=False,
    )

    assert success.status_code == 303
    assert not source.exists()
    assert (root / "target" / "Moved.gif").exists()
