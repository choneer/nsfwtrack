from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import select, update

from app.config import get_settings
from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media, media_alias_normalization, media_operation_token
from app.services.media_alias_normalization import (
    MediaAliasNormalizationError,
    build_media_alias_normalization_preview,
    execute_media_alias_normalization,
)


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _alias_group(root: Path) -> tuple[Path, Path, Path, Path]:
    keeper = root / "one" / "Keeper.gif"
    alias_a = root / "two" / "Alias-A.gif"
    alias_b = root / "three" / "Alias-B.gif"
    independent = root / "four" / "Independent.gif"
    for path in (keeper, alias_a, alias_b, independent):
        path.parent.mkdir(parents=True, exist_ok=True)
    keeper.write_bytes(_gif_bytes(30))
    os.link(keeper, alias_a)
    os.link(keeper, alias_b)
    independent.write_bytes(keeper.read_bytes())
    return keeper, alias_a, alias_b, independent


def _paths() -> list[str]:
    return [
        "/media/one/Keeper.gif",
        "/media/two/Alias-A.gif",
        "/media/three/Alias-B.gif",
    ]


def _preview():
    with SessionLocal() as db:
        return build_media_alias_normalization_preview(
            db,
            alias_paths=_paths(),
            keeper_path=_paths()[0],
            secret_key=get_settings().secret_key,
        )


def _references() -> tuple[tuple[str | None, ...], tuple[str | None, ...]]:
    with SessionLocal() as db:
        return (
            tuple(db.scalars(select(Item.cover_path).order_by(Item.id)).all()),
            tuple(db.scalars(select(Creator.avatar_path).order_by(Creator.id)).all()),
        )


def test_alias_preview_requires_exact_inode_group_and_excludes_independent_sha(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    keeper, alias_a, alias_b, independent = _alias_group(root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    before = {path: path.read_bytes() for path in (keeper, alias_a, alias_b, independent)}

    preview = _preview()

    assert preview.keeper_path == _paths()[0]
    assert {path.record.media_path for path in preview.paths} == set(_paths())
    assert preview.independent_paths == ("/media/four/Independent.gif",)
    assert before == {path: path.read_bytes() for path in before}

    with SessionLocal() as db, pytest.raises(MediaAliasNormalizationError) as exc_info:
        build_media_alias_normalization_preview(
            db,
            alias_paths=[_paths()[0], "/media/four/Independent.gif"],
            keeper_path=_paths()[0],
            secret_key=get_settings().secret_key,
        )
    assert exc_info.value.code == "stale_group"


def test_alias_preview_rejects_oversized_signed_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    _alias_group(root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    monkeypatch.setattr(media_operation_token, "MAX_MEDIA_OPERATION_TOKEN_LENGTH", 1)

    with SessionLocal() as db, pytest.raises(MediaAliasNormalizationError) as exc_info:
        build_media_alias_normalization_preview(
            db,
            alias_paths=_paths(),
            keeper_path=_paths()[0],
            secret_key=get_settings().secret_key,
        )

    assert exc_info.value.code == "snapshot_too_large"


def test_alias_normalization_migrates_all_references_then_deletes_only_aliases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    keeper, alias_a, alias_b, independent = _alias_group(root)
    paths = _paths()
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Keeper", cover_path=paths[0]),
                Item(title="Alias A", cover_path=paths[1]),
                Item(title="Alias B", cover_path=paths[2]),
                Creator(name="Alias", type="person", avatar_path=paths[2]),
            ]
        )
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview()

    with SessionLocal() as db:
        result = execute_media_alias_normalization(
            db,
            snapshot_token=preview.snapshot_token,
            secret_key=get_settings().secret_key,
        )

    assert result.database_outcome == "committed"
    assert result.migrated_items == 2 and result.migrated_creators == 1
    assert [path.status for path in result.paths].count("deleted") == 2
    assert keeper.exists() and not alias_a.exists() and not alias_b.exists()
    assert independent.read_bytes() == _gif_bytes(30)
    assert _references() == ((paths[0],) * 3, (paths[0],))


def test_alias_normalization_rejects_forgery_and_stale_references_without_deletion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    keeper, alias_a, alias_b, independent = _alias_group(root)
    paths = _paths()
    with SessionLocal() as db:
        db.add(Item(title="Initial", cover_path=paths[1]))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview()
    forged = preview.snapshot_token[:-1] + (
        "0" if preview.snapshot_token[-1] != "0" else "1"
    )
    with SessionLocal() as db, pytest.raises(MediaAliasNormalizationError) as forged_error:
        execute_media_alias_normalization(
            db,
            snapshot_token=forged,
            secret_key=get_settings().secret_key,
        )
    assert forged_error.value.code == "invalid_snapshot"

    with SessionLocal() as db:
        db.add(Creator(name="Late", type="person", avatar_path=paths[2]))
        db.commit()
    with SessionLocal() as db, pytest.raises(MediaAliasNormalizationError) as stale:
        execute_media_alias_normalization(
            db,
            snapshot_token=preview.snapshot_token,
            secret_key=get_settings().secret_key,
        )
    assert stale.value.code == "stale_preview"
    assert all(path.exists() for path in (keeper, alias_a, alias_b, independent))
    assert _references() == ((paths[1],), (paths[2],))


def test_alias_unknown_and_mixed_commit_outcomes_retain_every_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    keeper, alias_a, alias_b, _ = _alias_group(root)
    paths = _paths()
    with SessionLocal() as setup_db:
        setup_db.add_all(
            [
                Item(title="Alias", cover_path=paths[1]),
                Creator(name="Alias", type="person", avatar_path=paths[2]),
            ]
        )
        setup_db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview()

    with SessionLocal() as db:
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError()))
        monkeypatch.setattr(
            media_alias_normalization,
            "_inspect_commit_outcome",
            lambda _snapshot: "unknown",
        )
        unknown = execute_media_alias_normalization(
            db,
            snapshot_token=preview.snapshot_token,
            secret_key=get_settings().secret_key,
        )
    assert unknown.database_outcome == "unknown"
    assert all(path.exists() for path in (keeper, alias_a, alias_b))
    assert _references() == ((paths[1],), (paths[2],))

    monkeypatch.undo()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview()
    with SessionLocal() as db:
        real_commit = db.commit

        def mixed_commit_then_raise() -> None:
            db.execute(
                update(Creator)
                .where(Creator.name == "Alias")
                .values(avatar_path=paths[2])
            )
            real_commit()
            raise RuntimeError("mixed commit")

        monkeypatch.setattr(db, "commit", mixed_commit_then_raise)
        mixed = execute_media_alias_normalization(
            db,
            snapshot_token=preview.snapshot_token,
            secret_key=get_settings().secret_key,
        )
    assert mixed.database_outcome == "unknown"
    assert all(path.exists() for path in (keeper, alias_a, alias_b))
    assert _references() == ((paths[0],), (paths[2],))


def test_alias_unlink_failure_retains_alias_with_keeper_references_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    keeper, alias_a, alias_b, _ = _alias_group(root)
    paths = _paths()
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Alias A", cover_path=paths[1]),
                Creator(name="Alias B", type="person", avatar_path=paths[2]),
            ]
        )
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview()
    original_delete = local_media.delete_validated_local_media_file

    def fail_one(record: local_media.ValidatedLocalMediaFile) -> None:
        if record.media_path == paths[1]:
            raise local_media.LocalMediaDeleteError("delete_failed")
        original_delete(record)

    monkeypatch.setattr(local_media, "delete_validated_local_media_file", fail_one)
    with SessionLocal() as db:
        result = execute_media_alias_normalization(
            db,
            snapshot_token=preview.snapshot_token,
            secret_key=get_settings().secret_key,
        )

    statuses = {path.media_path: path.status for path in result.paths}
    assert statuses == {paths[0]: "keeper", paths[1]: "retained", paths[2]: "deleted"}
    assert keeper.exists() and alias_a.exists() and not alias_b.exists()
    assert _references() == ((paths[0],), (paths[0],))


def test_alias_parent_replacement_after_preview_rejects_without_deletion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    keeper, alias_a, alias_b, independent = _alias_group(root)
    paths = _paths()
    with SessionLocal() as db:
        db.add(Item(title="Alias", cover_path=paths[1]))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview()
    moved_parent = tmp_path / "moved-two"
    alias_a.parent.rename(moved_parent)
    alias_a.parent.mkdir()
    alias_a.hardlink_to(keeper)

    with SessionLocal() as db, pytest.raises(MediaAliasNormalizationError) as exc_info:
        execute_media_alias_normalization(
            db,
            snapshot_token=preview.snapshot_token,
            secret_key=get_settings().secret_key,
        )

    assert exc_info.value.code in {"stale_group", "stale_preview"}
    assert all(path.exists() for path in (keeper, alias_a, alias_b, independent))
    assert (moved_parent / "Alias-A.gif").exists()
    assert _references() == ((paths[1],), ())
