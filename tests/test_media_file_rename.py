from __future__ import annotations

import hashlib
import html
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update

from app.database import SessionLocal, engine
from app.i18n import translate
from app.models import Creator, Item
from app.routers import pages as page_routes
from app.services import local_media, media_file_rename
from app.services.media_file_rename import (
    MediaFileRenameError,
    build_media_file_rename_preview,
    execute_media_file_rename,
)
from app.services.media_duplicate_groups import find_media_duplicate_group
from app.services.settings import save_app_settings


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(root: Path, relative_path: str, *, extra: int = 0) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def _media_path(path: Path, root: Path) -> str:
    return f"/media/{path.relative_to(root).as_posix()}"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_snapshot(path: Path) -> tuple[int, int, int, int, int, bytes]:
    file_stat = path.lstat()
    content = path.read_bytes() if stat.S_ISREG(file_stat.st_mode) else b""
    return (
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mtime_ns,
        content,
    )


def _directory_snapshot(path: Path) -> tuple[int, int, int, int, tuple[str, ...]]:
    directory_stat = path.lstat()
    return (
        directory_stat.st_mode,
        directory_stat.st_dev,
        directory_stat.st_ino,
        directory_stat.st_mtime_ns,
        tuple(sorted(child.name for child in path.iterdir())),
    )


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


def _assert_all_media_references_resolve() -> None:
    with SessionLocal() as db:
        paths = tuple(
            path
            for path in db.scalars(
                select(Item.cover_path).where(Item.cover_path.is_not(None))
            ).all()
            if path is not None
        ) + tuple(
            path
            for path in db.scalars(
                select(Creator.avatar_path).where(Creator.avatar_path.is_not(None))
            ).all()
            if path is not None
        )
    scan_entries = {
        entry.media_path: entry for entry in local_media.scan_local_media().entries
    }
    for path in paths:
        entry = scan_entries.get(path)
        assert entry is not None and entry.available and entry.sha256
        record = local_media.validate_local_media_file(
            path,
            expected_sha256=entry.sha256,
        )
        assert record.sha256


def _form(preview: media_file_rename.MediaFileRenamePreview) -> dict[str, object]:
    return {
        "media_path": preview.source.media_path,
        "target_basename": preview.target_basename,
        "next": "/media-library?media_q=Nested&media_page=2#media-files",
        "expected_sha256": preview.source.sha256,
        "expected_mode": str(preview.source.mode),
        "expected_size": str(preview.source.size),
        "expected_device": str(preview.source.device),
        "expected_inode": str(preview.source.inode),
        "expected_modified_ns": str(preview.source.modified_ns),
        "expected_changed_ns": str(preview.source.changed_ns),
        "item_reference_id": [str(value) for value in preview.item_reference_ids],
        "creator_reference_id": [
            str(value) for value in preview.creator_reference_ids
        ],
        "confirm": "1",
    }


def _preview(
    root: Path,
    source: Path,
    target_basename: str,
) -> media_file_rename.MediaFileRenamePreview:
    with SessionLocal() as db:
        return build_media_file_rename_preview(
            db,
            media_path=_media_path(source, root),
            target_basename=target_basename,
        )


def test_rename_requires_login_and_detail_exposes_only_valid_entry(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    valid = _write_gif(root, "Valid.gif")
    damaged = root / "Damaged.gif"
    damaged.write_bytes(b"not-an-image")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)

    anonymous_get = client.get(
        "/media-library/detail/rename",
        params={"media_path": "/media/Valid.gif", "target_basename": "New.gif"},
        follow_redirects=False,
    )
    anonymous_post = client.post(
        "/media-library/detail/rename",
        data={"media_path": "/media/Valid.gif"},
        follow_redirects=False,
    )
    login = client.post("/api/auth/login", json={"password": "test-password"})
    assert login.status_code == 200
    valid_detail = client.get(
        "/media-library/detail",
        params={"media_path": _media_path(valid, root)},
    )
    damaged_detail = client.get(
        "/media-library/detail",
        params={"media_path": _media_path(damaged, root)},
    )

    assert anonymous_get.status_code == 303
    assert anonymous_post.status_code == 303
    assert "data-media-rename-entry" in valid_detail.text
    assert "data-media-rename-entry" not in damaged_detail.text


def test_preview_shows_complete_identity_references_and_is_write_free(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Nested/Source.gif", extra=11)
    source_path = _media_path(source, root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="First", cover_path=source_path),
                Item(title="Second", cover_path=source_path),
                Creator(name="Creator A", type="person", avatar_path=source_path),
                Creator(name="Creator B", type="studio", avatar_path=source_path),
            ]
        )
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    before_db = _database_snapshot()
    before_file = _file_snapshot(source)
    before_root = _directory_snapshot(root)
    before_parent = _directory_snapshot(source.parent)
    writes: list[str] = []

    def capture_write(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().partition(" ")[0].upper() in {
            "INSERT",
            "UPDATE",
            "DELETE",
            "REPLACE",
            "CREATE",
            "DROP",
            "ALTER",
        }:
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", capture_write)
    try:
        response = auth_client.get(
            "/media-library/detail/rename",
            params={
                "media_path": source_path,
                "target_basename": "Renamed.gif",
                "next": "/media-library?media_q=Nested&media_page=2#media-files",
            },
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_write)

    page = html.unescape(response.text)
    source_stat = source.stat()
    assert response.status_code == 200
    assert f'data-rename-source-path>{source_path}<' in page
    assert "data-rename-target-path>/media/Nested/Renamed.gif<" in page
    assert _digest(source) in page
    assert str(source_stat.st_dev) in page
    assert str(source_stat.st_ino) in page
    assert "First" in page and "Second" in page
    assert "Creator A" in page and "Creator B" in page
    assert "BEGIN IMMEDIATE" in page
    assert 'name="item_reference_id"' in page
    assert 'name="creator_reference_id"' in page
    assert writes == []
    assert _database_snapshot() == before_db
    assert _file_snapshot(source) == before_file
    assert _directory_snapshot(root) == before_root
    assert _directory_snapshot(source.parent) == before_parent
    assert not (source.parent / "Renamed.gif").exists()


def test_confirmed_rename_migrates_all_references_and_returns_new_detail(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Nested/Source.gif", extra=17)
    duplicate = _write_gif(root, "Nested/Duplicate.gif", extra=17)
    source_path = _media_path(source, root)
    original = _file_snapshot(source)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="First", cover_path=source_path),
                Item(title="Second", cover_path=source_path),
                Creator(name="Creator A", type="person", avatar_path=source_path),
                Creator(name="Creator B", type="studio", avatar_path=source_path),
            ]
        )
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, "Renamed.gif")
    digest = preview.source.sha256
    before_group = find_media_duplicate_group(local_media.scan_local_media(), digest)
    assert before_group is not None
    assert {entry.media_path for entry in before_group.entries} == {
        source_path,
        _media_path(duplicate, root),
    }
    begin_statements: list[str] = []

    def capture_begin(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            begin_statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture_begin)
    try:
        response = auth_client.post(
            "/media-library/detail/rename",
            data=_form(preview),
            follow_redirects=False,
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_begin)

    target = source.parent / "Renamed.gif"
    assert response.status_code == 303
    location = html.unescape(response.headers["location"])
    parsed = urlsplit(location)
    query = parse_qs(parsed.query)
    assert parsed.path == "/media-library/detail"
    assert query["media_path"] == ["/media/Nested/Renamed.gif"]
    assert urlsplit(query["next"][0]).fragment == "media-files"
    assert len(begin_statements) == 2
    assert not source.exists()
    assert target.exists()
    assert target.read_bytes() == original[-1]
    assert _digest(target) == digest
    assert target.stat().st_ino == original[3]
    after_group = find_media_duplicate_group(local_media.scan_local_media(), digest)
    assert after_group is not None
    assert {entry.media_path for entry in after_group.entries} == {
        "/media/Nested/Renamed.gif",
        _media_path(duplicate, root),
    }
    with SessionLocal() as db:
        assert {row.cover_path for row in db.query(Item)} == {
            "/media/Nested/Renamed.gif"
        }
        assert {row.avatar_path for row in db.query(Creator)} == {
            "/media/Nested/Renamed.gif"
        }
    detail = auth_client.get(location)
    assert detail.status_code == 200
    assert "/media/Nested/Renamed.gif" in html.unescape(detail.text)
    assert "First" in detail.text and "Creator A" in detail.text


def test_unreferenced_recovered_media_can_be_renamed(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "recovered-old.gif", extra=3)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, "ordinary.gif")

    assert preview.is_recovered is True
    assert preview.reference_count == 0
    response = auth_client.post(
        "/media-library/detail/rename",
        data=_form(preview),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert not source.exists()
    assert (root / "ordinary.gif").read_bytes() == _gif_bytes(3)


def test_strict_mode_requires_exact_confirm(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Strict.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})
    preview = _preview(root, source, "Renamed.gif")
    preview_page = auth_client.get(
        "/media-library/detail/rename",
        params={
            "media_path": preview.source.media_path,
            "target_basename": preview.target_basename,
        },
    )
    form = _form(preview)

    rejected = auth_client.post(
        "/media-library/detail/rename",
        data={**form, "confirmation_text": "confirm"},
        follow_redirects=False,
    )
    assert rejected.status_code == 303
    assert source.exists()
    accepted = auth_client.post(
        "/media-library/detail/rename",
        data={**form, "confirmation_text": "CONFIRM"},
        follow_redirects=False,
    )

    assert "data-strict-confirm-message" in preview_page.text
    assert accepted.status_code == 303
    assert not source.exists()
    assert (root / "Renamed.gif").exists()


@pytest.mark.parametrize(
    ("target_basename", "error_code"),
    [
        ("", "basename_required"),
        ("../Escape.gif", "invalid_basename"),
        ("Nested/Escape.gif", "invalid_basename"),
        ("Back\\slash.gif", "invalid_basename"),
        ("Percent%20.gif", "invalid_basename"),
        ("Control\x01.gif", "invalid_basename"),
        (" Space.gif ", "invalid_basename"),
        ("Renamed.png", "extension_changed"),
        ("Renamed.GIF", "extension_changed"),
        ("Source.gif", "basename_unchanged"),
        (".cleanup-anchor-name.gif", "reserved_basename"),
        (".UPLOAD-name.gif", "reserved_basename"),
        ("Recovered-name.gif", "reserved_basename"),
        (("x" * 252) + ".gif", "basename_too_long"),
    ],
)
def test_invalid_basename_is_rejected_without_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target_basename: str,
    error_code: str,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    before = _directory_snapshot(root)

    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as exc_info:
        build_media_file_rename_preview(
            db,
            media_path="/media/Source.gif",
            target_basename=target_basename,
        )

    assert exc_info.value.code == error_code
    assert _directory_snapshot(root) == before
    assert source.read_bytes() == _gif_bytes()


@pytest.mark.parametrize("target_type", ["file", "symlink", "directory", "fifo", "hardlink"])
def test_existing_target_object_is_never_overwritten(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target_type: str,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=2)
    target = root / "Target.gif"
    outside = _write_gif(tmp_path, "outside.gif", extra=40)
    if target_type == "file":
        target.write_bytes(b"existing")
    elif target_type == "symlink":
        target.symlink_to(outside)
    elif target_type == "directory":
        target.mkdir()
    elif target_type == "fifo":
        os.mkfifo(target)
    else:
        os.link(source, target)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    before_target = target.lstat()
    before_outside = outside.read_bytes()

    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as exc_info:
        build_media_file_rename_preview(
            db,
            media_path="/media/Source.gif",
            target_basename="Target.gif",
        )

    assert exc_info.value.code == "target_exists"
    assert target.lstat().st_dev == before_target.st_dev
    assert target.lstat().st_ino == before_target.st_ino
    assert outside.read_bytes() == before_outside


def test_target_path_with_existing_database_reference_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add(Item(title="Stale Target", cover_path="/media/Target.gif"))
        db.commit()

    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as exc_info:
        build_media_file_rename_preview(
            db,
            media_path=_media_path(source, root),
            target_basename="Target.gif",
        )

    assert exc_info.value.code == "target_referenced"
    assert source.exists()
    assert not (root / "Target.gif").exists()


@pytest.mark.parametrize(
    "source_kind",
    ["missing", "damaged", "anchor", "symlink", "directory", "fifo", "residue"],
)
def test_ineligible_source_is_rejected_without_touching_external_objects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    source_kind: str,
) -> None:
    root = tmp_path / "media"
    root.mkdir()
    outside = _write_gif(tmp_path, "outside.gif", extra=50)
    source = root / "Source.gif"
    media_path = "/media/Source.gif"
    if source_kind == "damaged":
        source.write_bytes(b"damaged")
    elif source_kind == "anchor":
        source = _write_gif(root, ".cleanup-anchor-test.gif")
        media_path = "/media/.cleanup-anchor-test.gif"
    elif source_kind == "symlink":
        source.symlink_to(outside)
    elif source_kind == "directory":
        source.mkdir()
    elif source_kind == "fifo":
        os.mkfifo(source)
    elif source_kind == "residue":
        source = root / ".upload-test.tmp"
        source.write_bytes(b"residue")
        media_path = "/media/.upload-test.tmp"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    outside_before = outside.read_bytes()

    with SessionLocal() as db, pytest.raises(MediaFileRenameError):
        build_media_file_rename_preview(
            db,
            media_path=media_path,
            target_basename="Target.gif",
        )

    assert outside.read_bytes() == outside_before
    assert not (root / "Target.gif").exists()


def test_forged_identity_and_reference_snapshots_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif")
    source_path = _media_path(source, root)
    with SessionLocal() as db:
        db.add(Item(title="Referenced", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, "Target.gif")
    forged_identity = _form(preview)
    forged_identity["expected_inode"] = str(preview.source.inode + 1)
    forged_references = _form(preview)
    forged_references["item_reference_id"] = []

    for form in (forged_identity, forged_references):
        with SessionLocal() as db, pytest.raises(MediaFileRenameError) as exc_info:
            execute_media_file_rename(
                db,
                media_path=str(form["media_path"]),
                target_basename=str(form["target_basename"]),
                expected_sha256=str(form["expected_sha256"]),
                expected_mode=str(form["expected_mode"]),
                expected_size=str(form["expected_size"]),
                expected_device=str(form["expected_device"]),
                expected_inode=str(form["expected_inode"]),
                expected_modified_ns=str(form["expected_modified_ns"]),
                expected_changed_ns=str(form["expected_changed_ns"]),
                expected_item_reference_ids=form["item_reference_id"],
                expected_creator_reference_ids=form["creator_reference_id"],
            )
        assert exc_info.value.code == "stale_preview"
        assert source.exists()
        assert not (root / "Target.gif").exists()
        assert _database_snapshot()[0][0][1] == source_path


def test_reference_added_after_preview_is_rejected_under_write_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif")
    source_path = _media_path(source, root)
    with SessionLocal() as db:
        db.add(Item(title="Initial", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, "Target.gif")
    with SessionLocal() as db:
        db.add(Creator(name="Late", type="person", avatar_path=source_path))
        db.commit()

    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as exc_info:
        execute_media_file_rename(db, **_service_args(preview))

    assert exc_info.value.code == "stale_preview"
    assert source.exists()
    assert not (root / "Target.gif").exists()
    assert _database_snapshot() == (
        ((1, source_path),),
        ((1, source_path),),
    )


def test_preview_and_apply_do_not_use_target_path_stat_or_read_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Nested/Source.gif", extra=8)
    target = source.parent / "Target.gif"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    original_stat = Path.stat
    original_read_bytes = Path.read_bytes

    def guarded_stat(path: Path, *args: object, **kwargs: object) -> os.stat_result:
        if path in {source, target}:
            raise AssertionError("target Path.stat must not be used")
        return original_stat(path, *args, **kwargs)

    def guarded_read_bytes(path: Path) -> bytes:
        if path in {source, target}:
            raise AssertionError("target Path.read_bytes must not be used")
        return original_read_bytes(path)

    with monkeypatch.context() as guarded:
        guarded.setattr(Path, "stat", guarded_stat)
        guarded.setattr(Path, "read_bytes", guarded_read_bytes)
        preview = _preview(root, source, target.name)
        with SessionLocal() as db:
            result = execute_media_file_rename(db, **_service_args(preview))

    assert result.source_removed is True
    assert not source.exists()
    assert target.read_bytes() == _gif_bytes(8)


def test_target_race_before_hardlink_does_not_overwrite_claimant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif")
    target = root / "Target.gif"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, target.name)
    original_create = local_media.create_validated_local_media_hardlink

    @contextmanager
    def claim_target(
        record: local_media.ValidatedLocalMediaFile,
        target_media_path: str,
    ):
        target.write_bytes(b"claimant")
        with original_create(record, target_media_path) as handle:
            yield handle

    monkeypatch.setattr(
        local_media,
        "create_validated_local_media_hardlink",
        claim_target,
    )

    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as exc_info:
        execute_media_file_rename(db, **_service_args(preview))

    assert exc_info.value.code == "target_exists"
    assert source.exists()
    assert target.read_bytes() == b"claimant"


def _service_args(
    preview: media_file_rename.MediaFileRenamePreview,
) -> dict[str, object]:
    form = _form(preview)
    return {
        "media_path": form["media_path"],
        "target_basename": form["target_basename"],
        "expected_sha256": form["expected_sha256"],
        "expected_mode": form["expected_mode"],
        "expected_size": form["expected_size"],
        "expected_device": form["expected_device"],
        "expected_inode": form["expected_inode"],
        "expected_modified_ns": form["expected_modified_ns"],
        "expected_changed_ns": form["expected_changed_ns"],
        "expected_item_reference_ids": form["item_reference_id"],
        "expected_creator_reference_ids": form["creator_reference_id"],
    }


def test_source_identity_race_before_hardlink_rolls_back_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=4)
    source_path = _media_path(source, root)
    with SessionLocal() as db:
        db.add(Item(title="Referenced", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, "Target.gif")
    original_create = local_media.create_validated_local_media_hardlink

    @contextmanager
    def change_source(
        record: local_media.ValidatedLocalMediaFile,
        target_media_path: str,
    ):
        source.write_bytes(_gif_bytes(20))
        with original_create(record, target_media_path) as handle:
            yield handle

    monkeypatch.setattr(
        local_media,
        "create_validated_local_media_hardlink",
        change_source,
    )

    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as exc_info:
        execute_media_file_rename(db, **_service_args(preview))

    assert exc_info.value.code == "publish_failed"
    assert source.read_bytes() == _gif_bytes(20)
    assert not (root / "Target.gif").exists()
    assert _database_snapshot()[0][0][1] == source_path


def test_target_replacement_after_link_is_not_deleted_or_committed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=3)
    source_path = _media_path(source, root)
    target = root / "Target.gif"
    with SessionLocal() as db:
        db.add(Item(title="Referenced", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, target.name)
    original_create = local_media.create_validated_local_media_hardlink

    @contextmanager
    def replace_target(
        record: local_media.ValidatedLocalMediaFile,
        target_media_path: str,
    ):
        with original_create(record, target_media_path) as handle:
            target.unlink()
            target.write_bytes(b"claimant-after-link")
            yield handle

    monkeypatch.setattr(
        local_media,
        "create_validated_local_media_hardlink",
        replace_target,
    )

    with SessionLocal() as db, pytest.raises(MediaFileRenameError) as exc_info:
        execute_media_file_rename(db, **_service_args(preview))

    assert exc_info.value.code == "stale_source"
    assert source.exists()
    assert target.read_bytes() == b"claimant-after-link"
    assert _database_snapshot()[0][0][1] == source_path


@pytest.mark.parametrize("replacement", ["directory", "symlink"])
def test_parent_replacement_before_link_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    replacement: str,
) -> None:
    root = tmp_path / "media"
    parent = root / "Nested"
    source = _write_gif(root, "Nested/Source.gif", extra=3)
    source_path = _media_path(source, root)
    outside = tmp_path / "outside"
    outside.mkdir()
    external = _write_gif(outside, "External.gif", extra=60)
    moved = root / "Moved"
    with SessionLocal() as db:
        db.add(Item(title="Referenced", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, "Target.gif")
    original_create = local_media.create_validated_local_media_hardlink

    @contextmanager
    def replace_parent(
        record: local_media.ValidatedLocalMediaFile,
        target_media_path: str,
    ):
        parent.rename(moved)
        if replacement == "directory":
            parent.mkdir()
        else:
            parent.symlink_to(outside, target_is_directory=True)
        with original_create(record, target_media_path) as handle:
            yield handle

    monkeypatch.setattr(
        local_media,
        "create_validated_local_media_hardlink",
        replace_parent,
    )

    with SessionLocal() as db, pytest.raises(MediaFileRenameError):
        execute_media_file_rename(db, **_service_args(preview))

    assert (moved / "Source.gif").read_bytes() == _gif_bytes(3)
    assert not (moved / "Target.gif").exists()
    assert not (outside / "Target.gif").exists()
    assert external.read_bytes() == _gif_bytes(60)
    assert _database_snapshot()[0][0][1] == source_path


def test_database_commit_failure_removes_created_target_and_preserves_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=9)
    source_path = _media_path(source, root)
    with SessionLocal() as setup_db:
        setup_db.add(Item(title="Referenced", cover_path=source_path))
        setup_db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, "Target.gif")

    with SessionLocal() as db:
        def fail_commit() -> None:
            os.link(source, root / "Concurrent-link.gif")
            raise RuntimeError("injected commit failure")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(MediaFileRenameError) as exc_info:
            execute_media_file_rename(db, **_service_args(preview))

    assert exc_info.value.code == "database_failed"
    assert source.read_bytes() == _gif_bytes(9)
    assert not (root / "Target.gif").exists()
    assert (root / "Concurrent-link.gif").stat().st_ino == source.stat().st_ino
    assert _database_snapshot()[0][0][1] == source_path


def test_commit_applied_before_exception_preserves_both_paths_and_references(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=10)
    source_path = _media_path(source, root)
    target = root / "Target.gif"
    with SessionLocal() as setup_db:
        setup_db.add_all(
            [
                Item(title="Referenced item", cover_path=source_path),
                Creator(
                    name="Referenced creator",
                    type="person",
                    avatar_path=source_path,
                ),
            ]
        )
        setup_db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, target.name)

    with SessionLocal() as db:
        original_commit = db.commit

        def commit_then_raise() -> None:
            original_commit()
            raise RuntimeError("injected error after real commit")

        monkeypatch.setattr(db, "commit", commit_then_raise)
        result = execute_media_file_rename(db, **_service_args(preview))

    assert result.source_removed is False
    assert result.warning_code == "committed_source_retained"
    assert source.exists() and target.exists()
    assert source.stat().st_ino == target.stat().st_ino
    item_rows, creator_rows = _database_snapshot()
    assert item_rows[0][1] == "/media/Target.gif"
    assert creator_rows[0][1] == "/media/Target.gif"
    _assert_all_media_references_resolve()


def test_mixed_commit_outcome_preserves_both_paths_and_valid_references(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=12)
    source_path = _media_path(source, root)
    target = root / "Target.gif"
    with SessionLocal() as setup_db:
        item = Item(title="Referenced item", cover_path=source_path)
        creator = Creator(
            name="Referenced creator",
            type="person",
            avatar_path=source_path,
        )
        setup_db.add_all([item, creator])
        setup_db.commit()
        creator_id = creator.id
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, target.name)

    with SessionLocal() as db:
        original_commit = db.commit

        def commit_mixed_then_raise() -> None:
            db.execute(
                update(Creator)
                .where(Creator.id == creator_id)
                .values(avatar_path=source_path)
            )
            original_commit()
            raise RuntimeError("injected mixed commit outcome")

        monkeypatch.setattr(db, "commit", commit_mixed_then_raise)
        result = execute_media_file_rename(db, **_service_args(preview))

    assert result.source_removed is False
    assert result.warning_code == "commit_outcome_unknown"
    assert source.exists() and target.exists()
    assert source.stat().st_ino == target.stat().st_ino
    item_rows, creator_rows = _database_snapshot()
    assert item_rows[0][1] == "/media/Target.gif"
    assert creator_rows[0][1] == source_path
    _assert_all_media_references_resolve()


def test_unreferenced_commit_exception_is_unknown_and_preserves_both_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=13)
    target = root / "Target.gif"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, target.name)

    with SessionLocal() as db:
        original_commit = db.commit

        def commit_then_raise() -> None:
            original_commit()
            raise RuntimeError("injected unreferenced commit ambiguity")

        monkeypatch.setattr(db, "commit", commit_then_raise)
        result = execute_media_file_rename(db, **_service_args(preview))

    assert result.source_removed is False
    assert result.warning_code == "commit_outcome_unknown"
    assert source.exists() and target.exists()
    assert source.stat().st_ino == target.stat().st_ino
    assert _database_snapshot() == ((), ())


def test_commit_outcome_query_failure_preserves_all_files_and_references(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=14)
    source_path = _media_path(source, root)
    target = root / "Target.gif"
    concurrent_link = root / "Concurrent-link.gif"
    outside = _write_gif(tmp_path / "outside", "External.gif", extra=40)
    outside_before = _file_snapshot(outside)
    with SessionLocal() as setup_db:
        setup_db.add_all(
            [
                Item(title="Referenced item", cover_path=source_path),
                Creator(
                    name="Referenced creator",
                    type="person",
                    avatar_path=source_path,
                ),
            ]
        )
        setup_db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, target.name)

    with SessionLocal() as db:
        def fail_commit_before_apply() -> None:
            os.link(source, concurrent_link)
            raise RuntimeError("injected pre-commit failure")

        def fail_verification_session() -> None:
            raise RuntimeError("injected independent query failure")

        monkeypatch.setattr(db, "commit", fail_commit_before_apply)
        monkeypatch.setattr(
            media_file_rename,
            "SessionLocal",
            fail_verification_session,
        )
        result = execute_media_file_rename(db, **_service_args(preview))

    assert result.source_removed is False
    assert result.warning_code == "commit_outcome_unknown"
    assert source.exists() and target.exists() and concurrent_link.exists()
    assert source.stat().st_ino == target.stat().st_ino
    assert source.stat().st_ino == concurrent_link.stat().st_ino
    assert _file_snapshot(outside) == outside_before
    item_rows, creator_rows = _database_snapshot()
    assert item_rows[0][1] == source_path
    assert creator_rows[0][1] == source_path
    _assert_all_media_references_resolve()


def test_commit_outcome_warnings_are_explicit_and_unknown_is_not_success(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=16)
    target = root / "Target.gif"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, target.name)
    os.link(source, target)
    unknown_result = media_file_rename.MediaFileRenameResult(
        source_path=preview.source.media_path,
        target_path=preview.target_media_path,
        sha256=preview.source.sha256,
        migrated_items=0,
        migrated_creators=0,
        source_removed=False,
        warning_code="commit_outcome_unknown",
    )
    monkeypatch.setattr(
        page_routes,
        "execute_media_file_rename",
        lambda *_args, **_kwargs: unknown_result,
    )

    zh_response = auth_client.post(
        "/media-library/detail/rename",
        data=_form(preview),
        follow_redirects=True,
    )
    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/media-library"},
    )
    en_response = auth_client.post(
        "/media-library/detail/rename",
        data=_form(preview),
        follow_redirects=True,
    )

    assert zh_response.status_code == 200
    assert "数据库提交结果无法安全判断" in zh_response.text
    assert "媒体路径已迁移" not in zh_response.text
    assert en_response.status_code == 200
    assert "database commit outcome cannot be determined safely" in en_response.text
    assert "Media path migrated" not in en_response.text
    for language in ("zh", "en"):
        committed_message = translate(
            language,
            "flash.media_file_rename_warning_committed_source_retained",
            source="/media/Source.gif",
            target="/media/Target.gif",
        )
        assert "/media/Source.gif" in committed_message
        assert "/media/Target.gif" in committed_message


def test_source_delete_failure_commits_target_and_reports_both_paths(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=7)
    source_path = _media_path(source, root)
    with SessionLocal() as db:
        db.add(Item(title="Referenced", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, "Target.gif")
    monkeypatch.setattr(
        local_media.ValidatedLocalMediaHardlink,
        "remove_source",
        lambda _self: local_media.LocalMediaLinkRemoval(False, "delete_failed"),
    )

    response = auth_client.post(
        "/media-library/detail/rename",
        data=_form(preview),
        follow_redirects=True,
    )

    target = root / "Target.gif"
    page = html.unescape(response.text)
    assert response.status_code == 200
    assert source.exists() and target.exists()
    assert source.stat().st_ino == target.stat().st_ino
    assert "/media/Source.gif" in page and "/media/Target.gif" in page
    assert "两个路径均保留" in page
    assert _database_snapshot()[0][0][1] == "/media/Target.gif"


def test_source_directory_fsync_failure_keeps_target_and_valid_references(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=18)
    source_path = _media_path(source, root)
    target = root / "Target.gif"
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Referenced item", cover_path=source_path),
                Creator(
                    name="Referenced creator",
                    type="person",
                    avatar_path=source_path,
                ),
            ]
        )
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, target.name)
    original_fsync = local_media.os.fsync
    fsync_calls = 0

    def fail_source_directory_sync(descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 3:
            raise OSError("injected source directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(local_media.os, "fsync", fail_source_directory_sync)
    with SessionLocal() as db:
        result = execute_media_file_rename(db, **_service_args(preview))

    assert fsync_calls == 3
    assert result.source_removed is True
    assert result.warning_code == "sync_failed"
    assert not source.exists()
    assert target.exists()
    item_rows, creator_rows = _database_snapshot()
    assert item_rows[0][1] == "/media/Target.gif"
    assert creator_rows[0][1] == "/media/Target.gif"
    _assert_all_media_references_resolve()


def test_source_path_replacement_after_commit_is_not_deleted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Source.gif", extra=6)
    source_path = _media_path(source, root)
    replacement_content = b"external-claimant"
    with SessionLocal() as db:
        db.add(Item(title="Referenced", cover_path=source_path))
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    preview = _preview(root, source, "Target.gif")
    original_remove = local_media.ValidatedLocalMediaHardlink.remove_source

    def replace_source_then_remove(
        handle: local_media.ValidatedLocalMediaHardlink,
    ) -> local_media.LocalMediaLinkRemoval:
        source.unlink()
        source.write_bytes(replacement_content)
        return original_remove(handle)

    monkeypatch.setattr(
        local_media.ValidatedLocalMediaHardlink,
        "remove_source",
        replace_source_then_remove,
    )

    with SessionLocal() as db:
        result = execute_media_file_rename(db, **_service_args(preview))

    assert result.source_removed is False
    assert result.warning_code == "link_changed"
    assert source.read_bytes() == replacement_content
    assert (root / "Target.gif").read_bytes() == _gif_bytes(6)
    assert _database_snapshot()[0][0][1] == "/media/Target.gif"
