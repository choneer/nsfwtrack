from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Creator, Item
from app.services import (
    local_media,
    media_batch_management,
    media_file_rename,
    media_operation_token,
)
from app.services.media_batch_management import (
    MAX_MEDIA_BATCH_SIZE,
    MediaBatchError,
    build_media_batch_preview,
    execute_media_batch,
)


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(root: Path, relative_path: str, *, extra: int = 0) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def _preview(
    *,
    operation: str,
    paths: list[str],
    target_directory: str | None,
    names: list[str] | None,
):
    with SessionLocal() as db:
        return build_media_batch_preview(
            db,
            operation=operation,
            media_paths=paths,
            target_directory=target_directory,
            target_basenames=names,
            allowed_paths=set(paths),
            secret_key=get_settings().secret_key,
        )


def _tokens(preview: object) -> list[str]:
    return [item.snapshot_token for item in preview.items]


def _references() -> tuple[tuple[str | None, ...], tuple[str | None, ...]]:
    with SessionLocal() as db:
        return (
            tuple(db.scalars(select(Item.cover_path).order_by(Item.id)).all()),
            tuple(db.scalars(select(Creator.avatar_path).order_by(Creator.id)).all()),
        )


def test_batch_preview_validates_selection_targets_and_signed_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    first = _write_gif(root, "source/First.gif", extra=1)
    second = _write_gif(root, "source/Second.gif", extra=2)
    (root / "target").mkdir()
    paths = ["/media/source/First.gif", "/media/source/Second.gif"]
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    before = {path: path.read_bytes() for path in (first, second)}

    draft = _preview(
        operation="move",
        paths=paths,
        target_directory=None,
        names=None,
    )
    prepared = _preview(
        operation="move",
        paths=paths,
        target_directory="/media/target",
        names=["Moved-1.gif", "Moved-2.gif"],
    )

    assert draft.prepared is False
    assert [item.target_basename for item in draft.items] == ["First.gif", "Second.gif"]
    assert prepared.prepared is True
    assert all(item.snapshot_token for item in prepared.items)
    assert before == {path: path.read_bytes() for path in (first, second)}
    assert not list((root / "target").iterdir())

    forged = _tokens(prepared)
    forged[0] = forged[0][:-1] + ("0" if forged[0][-1] != "0" else "1")
    with SessionLocal() as db, pytest.raises(MediaBatchError) as exc_info:
        execute_media_batch(
            db,
            operation="move",
            snapshot_tokens=forged,
            secret_key=get_settings().secret_key,
        )
    assert exc_info.value.code == "invalid_snapshot"
    assert before == {path: path.read_bytes() for path in (first, second)}

    with SessionLocal() as db, pytest.raises(MediaBatchError) as duplicate:
        build_media_batch_preview(
            db,
            operation="move",
            media_paths=[paths[0], paths[0]],
            target_directory=None,
            target_basenames=None,
            allowed_paths=set(paths),
            secret_key=get_settings().secret_key,
        )
    assert duplicate.value.code == "duplicate_source"
    with SessionLocal() as db, pytest.raises(MediaBatchError) as outside:
        build_media_batch_preview(
            db,
            operation="move",
            media_paths=paths,
            target_directory=None,
            target_basenames=None,
            allowed_paths={paths[0]},
            secret_key=get_settings().secret_key,
        )
    assert outside.value.code == "selection_outside_page"
    with SessionLocal() as db, pytest.raises(MediaBatchError) as too_many:
        build_media_batch_preview(
            db,
            operation="move",
            media_paths=[f"/media/Fake-{index}.gif" for index in range(MAX_MEDIA_BATCH_SIZE + 1)],
            target_directory=None,
            target_basenames=None,
            allowed_paths=None,
            secret_key=get_settings().secret_key,
        )
    assert too_many.value.code == "batch_too_large"


def test_batch_preview_rejects_oversized_signed_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    _write_gif(root, "Source.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    monkeypatch.setattr(media_operation_token, "MAX_MEDIA_OPERATION_TOKEN_LENGTH", 1)

    with SessionLocal() as db, pytest.raises(MediaBatchError) as exc_info:
        build_media_batch_preview(
            db,
            operation="rename",
            media_paths=["/media/Source.gif"],
            target_directory=None,
            target_basenames=["Target.gif"],
            allowed_paths={"/media/Source.gif"},
            secret_key=get_settings().secret_key,
        )

    assert exc_info.value.code == "snapshot_too_large"


def test_batch_move_same_directory_sources_complete_independently(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    first = _write_gif(root, "source/First.gif", extra=3)
    second = _write_gif(root, "source/Second.gif", extra=4)
    (root / "target").mkdir()
    paths = ["/media/source/First.gif", "/media/source/Second.gif"]
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="First", cover_path=paths[0]),
                Item(title="Second", cover_path=paths[1]),
                Creator(name="Second", type="person", avatar_path=paths[1]),
            ]
        )
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(
        operation="move",
        paths=paths,
        target_directory="/media/target",
        names=["Moved-First.gif", "Moved-Second.gif"],
    )

    with SessionLocal() as db:
        result = execute_media_batch(
            db,
            operation="move",
            snapshot_tokens=_tokens(preview),
            secret_key=get_settings().secret_key,
        )

    assert [item.status for item in result.items] == ["success", "success"]
    assert not first.exists() and not second.exists()
    assert (root / "target" / "Moved-First.gif").read_bytes() == _gif_bytes(3)
    assert (root / "target" / "Moved-Second.gif").read_bytes() == _gif_bytes(4)
    assert _references() == (
        ("/media/target/Moved-First.gif", "/media/target/Moved-Second.gif"),
        ("/media/target/Moved-Second.gif",),
    )


def test_batch_rename_rejects_duplicate_targets_and_name_exchange(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    _write_gif(root, "source/First.gif", extra=5)
    _write_gif(root, "source/Second.gif", extra=6)
    paths = ["/media/source/First.gif", "/media/source/Second.gif"]
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)

    with SessionLocal() as db, pytest.raises(MediaBatchError) as duplicate:
        build_media_batch_preview(
            db,
            operation="rename",
            media_paths=paths,
            target_directory=None,
            target_basenames=["Same.gif", "Same.gif"],
            allowed_paths=set(paths),
            secret_key=get_settings().secret_key,
        )
    assert duplicate.value.code == "duplicate_target"
    with SessionLocal() as db, pytest.raises(MediaBatchError) as exchange:
        build_media_batch_preview(
            db,
            operation="rename",
            media_paths=paths,
            target_directory=None,
            target_basenames=["Second.gif", "First.gif"],
            allowed_paths=set(paths),
            secret_key=get_settings().secret_key,
        )
    assert exchange.value.code == "selected_target_conflict"

    preview = _preview(
        operation="rename",
        paths=paths,
        target_directory=None,
        names=["Renamed-1.gif", "Renamed-2.gif"],
    )
    with SessionLocal() as db:
        result = execute_media_batch(
            db,
            operation="rename",
            snapshot_tokens=_tokens(preview),
            secret_key=get_settings().secret_key,
        )
    assert [item.status for item in result.items] == ["success", "success"]
    assert (root / "source" / "Renamed-1.gif").exists()
    assert (root / "source" / "Renamed-2.gif").exists()


def test_batch_item_failures_do_not_block_later_items(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    sources = [
        _write_gif(root, f"source/{name}.gif", extra=index + 10)
        for index, name in enumerate(("Claimed", "Reference", "Success"))
    ]
    (root / "target").mkdir()
    paths = [f"/media/source/{name}.gif" for name in ("Claimed", "Reference", "Success")]
    with SessionLocal() as db:
        db.add(Item(title="Original", cover_path=paths[1]))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(
        operation="move",
        paths=paths,
        target_directory="/media/target",
        names=["Claimed-Out.gif", "Reference-Out.gif", "Success-Out.gif"],
    )
    (root / "target" / "Claimed-Out.gif").write_bytes(b"external claimant")
    with SessionLocal() as db:
        db.add(Creator(name="Late", type="person", avatar_path=paths[1]))
        db.commit()

    with SessionLocal() as db:
        result = execute_media_batch(
            db,
            operation="move",
            snapshot_tokens=_tokens(preview),
            secret_key=get_settings().secret_key,
        )

    assert [item.status for item in result.items] == ["failed", "failed", "success"]
    assert result.items[0].code == "target_exists"
    assert result.items[1].code == "stale_preview"
    assert (root / "target" / "Claimed-Out.gif").read_bytes() == b"external claimant"
    assert sources[0].exists() and sources[1].exists() and not sources[2].exists()
    assert (root / "target" / "Success-Out.gif").exists()
    assert _references() == ((paths[1],), (paths[1],))


def test_batch_unknown_commit_retains_both_paths_and_continues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    first = _write_gif(root, "source/First.gif", extra=20)
    second = _write_gif(root, "source/Second.gif", extra=21)
    (root / "target").mkdir()
    paths = ["/media/source/First.gif", "/media/source/Second.gif"]
    with SessionLocal() as setup_db:
        setup_db.add_all(
            [
                Item(title="First", cover_path=paths[0]),
                Item(title="Second", cover_path=paths[1]),
            ]
        )
        setup_db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(
        operation="move",
        paths=paths,
        target_directory="/media/target",
        names=["Unknown.gif", "Completed.gif"],
    )
    monkeypatch.setattr(media_file_rename, "_inspect_commit_outcome", lambda **_: "unknown")

    with SessionLocal() as db:
        real_commit = db.commit
        calls = 0

        def fail_first_commit() -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected unknown commit")
            real_commit()

        monkeypatch.setattr(db, "commit", fail_first_commit)
        result = execute_media_batch(
            db,
            operation="move",
            snapshot_tokens=_tokens(preview),
            secret_key=get_settings().secret_key,
        )

    assert [item.status for item in result.items] == ["unknown", "success"]
    assert first.exists() and (root / "target" / "Unknown.gif").exists()
    assert not second.exists() and (root / "target" / "Completed.gif").exists()
    assert _references() == ((paths[0], "/media/target/Completed.gif"), ())


def test_batch_parent_mapping_replacement_fails_only_later_item(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    _write_gif(root, "source/First.gif", extra=30)
    second = _write_gif(root, "source/Second.gif", extra=31)
    (root / "target").mkdir()
    paths = ["/media/source/First.gif", "/media/source/Second.gif"]
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(
        operation="move",
        paths=paths,
        target_directory="/media/target",
        names=["First-Out.gif", "Second-Out.gif"],
    )
    real_execute = media_batch_management.execute_media_file_rename
    calls = 0

    def replace_source_parent_after_first(*args: object, **kwargs: object):
        nonlocal calls
        result = real_execute(*args, **kwargs)
        calls += 1
        if calls == 1:
            moved = tmp_path / "moved-source"
            (root / "source").rename(moved)
            (root / "source").mkdir()
            (root / "source" / "Second.gif").hardlink_to(moved / "Second.gif")
        return result

    monkeypatch.setattr(
        media_batch_management,
        "execute_media_file_rename",
        replace_source_parent_after_first,
    )
    with SessionLocal() as db:
        result = execute_media_batch(
            db,
            operation="move",
            snapshot_tokens=_tokens(preview),
            secret_key=get_settings().secret_key,
        )

    assert [item.status for item in result.items] == ["success", "failed"]
    assert result.items[1].code == "stale_preview"
    assert (root / "target" / "First-Out.gif").exists()
    assert not (root / "target" / "Second-Out.gif").exists()
    assert second.parent.parent == root
    assert (tmp_path / "moved-source" / "Second.gif").exists()
    assert (root / "source" / "Second.gif").exists()


def test_batch_fsync_failure_isolated_from_later_item(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    first = _write_gif(root, "source/First.gif", extra=40)
    second = _write_gif(root, "source/Second.gif", extra=41)
    (root / "target").mkdir()
    paths = ["/media/source/First.gif", "/media/source/Second.gif"]
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(
        operation="move",
        paths=paths,
        target_directory="/media/target",
        names=["First-Out.gif", "Second-Out.gif"],
    )
    real_fsync = local_media.os.fsync
    calls = 0

    def fail_first_sync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(local_media.os, "fsync", fail_first_sync)
    with SessionLocal() as db:
        result = execute_media_batch(
            db,
            operation="move",
            snapshot_tokens=_tokens(preview),
            secret_key=get_settings().secret_key,
        )

    assert [item.status for item in result.items] == ["failed", "success"]
    assert result.items[0].code == "publish_failed"
    assert first.exists() and not second.exists()
    assert not (root / "target" / "First-Out.gif").exists()
    assert (root / "target" / "Second-Out.gif").exists()


def test_batch_unlink_failure_retains_source_and_continues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    first = _write_gif(root, "source/First.gif", extra=50)
    second = _write_gif(root, "source/Second.gif", extra=51)
    (root / "target").mkdir()
    paths = ["/media/source/First.gif", "/media/source/Second.gif"]
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(
        operation="move",
        paths=paths,
        target_directory="/media/target",
        names=["First-Out.gif", "Second-Out.gif"],
    )
    real_unlink = local_media.os.unlink

    def fail_first_source(path: str, *args: object, **kwargs: object) -> None:
        if path == "First.gif":
            raise OSError("injected unlink failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(local_media.os, "unlink", fail_first_source)
    with SessionLocal() as db:
        result = execute_media_batch(
            db,
            operation="move",
            snapshot_tokens=_tokens(preview),
            secret_key=get_settings().secret_key,
        )

    assert [item.status for item in result.items] == ["source_retained", "success"]
    assert result.items[0].code == "delete_failed"
    assert first.exists() and not second.exists()
    assert (root / "target" / "First-Out.gif").exists()
    assert (root / "target" / "Second-Out.gif").exists()
