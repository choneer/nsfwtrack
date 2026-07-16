from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import sessionmaker

from app.database import SessionLocal, engine
from app.models import MediaIndexEntry, MediaIndexState
from app.services import local_media
from app.services.exporter import export_backup_data
from app.services.media_index import (
    MediaIndexError,
    get_media_index_status,
    load_preferred_media_snapshot,
    refresh_media_index,
)
from app.services.schema_version import initialize_database


def _png_bytes(red: int = 0) -> bytes:
    def chunk(name: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + name
            + payload
            + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(bytes((0, red, 0, 0)))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", pixels)
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def media_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "media"
    root.mkdir()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    return root


def _media_rows() -> tuple[tuple[str, str, str], ...]:
    with SessionLocal() as db:
        return tuple(
            db.execute(
                select(
                    MediaIndexEntry.media_path,
                    MediaIndexEntry.sha256,
                    MediaIndexEntry.cache_signature,
                )
                .where(MediaIndexEntry.record_type == "media")
                .order_by(MediaIndexEntry.media_path)
            ).all()
        )


def test_incremental_refresh_reuses_exact_identity_without_content_read(
    monkeypatch: pytest.MonkeyPatch,
    media_root: Path,
) -> None:
    (media_root / "cover.png").write_bytes(_png_bytes(1))
    with SessionLocal() as db:
        first = refresh_media_index(db, full=True)
    assert first.status.rehashed_count == 1
    assert first.status.new_count == 1

    reads = 0
    original_read = local_media._read_observed_scan_candidate

    def count_read(
        candidate: local_media._LocalMediaScanCandidate,
    ) -> tuple[bytes, str]:
        nonlocal reads
        reads += 1
        return original_read(candidate)

    monkeypatch.setattr(local_media, "_read_observed_scan_candidate", count_read)
    with SessionLocal() as db:
        second = refresh_media_index(db, full=False)

    assert reads == 0
    assert second.status.reused_count == 1
    assert second.status.rehashed_count == 0
    assert second.status.new_count == 0
    assert second.status.changed_count == 0


def test_changed_identity_and_inode_replacement_are_rehashed(
    monkeypatch: pytest.MonkeyPatch,
    media_root: Path,
) -> None:
    path = media_root / "cover.png"
    path.write_bytes(_png_bytes(2))
    with SessionLocal() as db:
        refresh_media_index(db, full=True)

    reads = 0
    original_read = local_media._read_observed_scan_candidate

    def count_read(
        candidate: local_media._LocalMediaScanCandidate,
    ) -> tuple[bytes, str]:
        nonlocal reads
        reads += 1
        return original_read(candidate)

    monkeypatch.setattr(local_media, "_read_observed_scan_candidate", count_read)
    path.write_bytes(_png_bytes(3))
    with SessionLocal() as db:
        changed = refresh_media_index(db, full=False)
    assert reads == 1
    assert changed.status.changed_count == 1
    assert changed.status.rehashed_count == 1

    old_inode = path.stat().st_ino
    replacement = media_root / "replacement.png"
    replacement.write_bytes(_png_bytes(4))
    replacement.replace(path)
    assert path.stat().st_ino != old_inode
    with SessionLocal() as db:
        replaced = refresh_media_index(db, full=False)
    assert reads == 2
    assert replaced.status.changed_count == 1
    assert replaced.status.rehashed_count == 1


def test_parent_mapping_replacement_prevents_cache_reuse(
    monkeypatch: pytest.MonkeyPatch,
    media_root: Path,
) -> None:
    directory = media_root / "library"
    directory.mkdir()
    path = directory / "cover.png"
    path.write_bytes(_png_bytes(5))
    with SessionLocal() as db:
        refresh_media_index(db, full=True)

    old_directory = media_root / "old-library"
    directory.rename(old_directory)
    directory.mkdir()
    (directory / "cover.png").hardlink_to(old_directory / "cover.png")
    reads = 0
    original_read = local_media._read_observed_scan_candidate

    def count_read(
        candidate: local_media._LocalMediaScanCandidate,
    ) -> tuple[bytes, str]:
        nonlocal reads
        reads += 1
        return original_read(candidate)

    monkeypatch.setattr(local_media, "_read_observed_scan_candidate", count_read)
    with SessionLocal() as db:
        result = refresh_media_index(db, full=False)

    assert reads == 2
    assert result.status.reused_count == 0
    assert result.status.rehashed_count == 2
    assert result.status.new_count == 1
    assert result.status.changed_count == 1


def test_forged_cache_is_rehashed_and_repaired(
    monkeypatch: pytest.MonkeyPatch,
    media_root: Path,
) -> None:
    path = media_root / "cover.png"
    path.write_bytes(_png_bytes(6))
    with SessionLocal() as db:
        refresh_media_index(db, full=True)
        original_digest = db.scalar(
            select(MediaIndexEntry.sha256).where(
                MediaIndexEntry.record_type == "media"
            )
        )
        db.execute(
            update(MediaIndexEntry)
            .where(MediaIndexEntry.record_type == "media")
            .values(sha256="f" * 64)
        )
        db.commit()

    reads = 0
    original_read = local_media._read_observed_scan_candidate

    def count_read(
        candidate: local_media._LocalMediaScanCandidate,
    ) -> tuple[bytes, str]:
        nonlocal reads
        reads += 1
        return original_read(candidate)

    monkeypatch.setattr(local_media, "_read_observed_scan_candidate", count_read)
    with SessionLocal() as db:
        result = refresh_media_index(db, full=False)
        repaired_digest = db.scalar(
            select(MediaIndexEntry.sha256).where(
                MediaIndexEntry.record_type == "media"
            )
        )

    assert reads == 1
    assert result.status.reused_count == 0
    assert result.status.rehashed_count == 1
    assert result.status.changed_count == 1
    assert repaired_digest == original_digest


def test_add_remove_damaged_and_skipped_are_reported(media_root: Path) -> None:
    original = media_root / "original.png"
    original.write_bytes(_png_bytes(7))
    with SessionLocal() as db:
        refresh_media_index(db, full=True)

    (media_root / "new.png").write_bytes(_png_bytes(8))
    (media_root / "damaged.gif").write_bytes(b"not-a-gif")
    (media_root / "notes.txt").write_text("skip", encoding="utf-8")
    with SessionLocal() as db:
        added = refresh_media_index(db, full=False)

    assert added.status.new_count == 2
    assert added.status.rehashed_count == 2
    assert added.status.damaged_count == 1
    assert added.status.skipped_count == 1
    assert added.scan.skipped_entries[0].reason == "unsupported_extension"

    original.unlink()
    with SessionLocal() as db:
        removed = refresh_media_index(db, full=False)
    assert removed.status.removed_count == 1
    assert removed.status.reused_count == 2


def test_corrupt_index_falls_back_without_get_side_writes(
    monkeypatch: pytest.MonkeyPatch,
    media_root: Path,
) -> None:
    (media_root / "cover.png").write_bytes(_png_bytes(9))
    with SessionLocal() as db:
        refresh_media_index(db, full=True)
        db.execute(
            update(MediaIndexEntry)
            .where(MediaIndexEntry.record_type == "media")
            .values(cache_signature="0" * 64)
        )
        db.commit()
    before = _media_rows()

    reads = 0
    original_read = local_media._read_observed_scan_candidate

    def count_read(
        candidate: local_media._LocalMediaScanCandidate,
    ) -> tuple[bytes, str]:
        nonlocal reads
        reads += 1
        return original_read(candidate)

    monkeypatch.setattr(local_media, "_read_observed_scan_candidate", count_read)
    with SessionLocal() as db:
        snapshot = load_preferred_media_snapshot(db)
        status = get_media_index_status(db)

    assert snapshot.source == "filesystem"
    assert reads == 1
    assert not status.integrity_valid
    assert status.stale_reason == "index_corrupt"
    assert _media_rows() == before


@pytest.mark.parametrize("failure_point", ["scan", "directories"])
def test_scan_failure_retains_previous_complete_index(
    monkeypatch: pytest.MonkeyPatch,
    media_root: Path,
    failure_point: str,
) -> None:
    (media_root / "cover.png").write_bytes(_png_bytes(10))
    with SessionLocal() as db:
        refresh_media_index(db, full=True)
    before = _media_rows()

    def fail(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("simulated half scan failure")

    if failure_point == "scan":
        monkeypatch.setattr(local_media, "scan_local_media_incremental", fail)
    else:
        monkeypatch.setattr(local_media, "scan_local_media_directories", fail)

    with SessionLocal() as db:
        with pytest.raises(MediaIndexError) as exc_info:
            refresh_media_index(db, full=False)
        status = get_media_index_status(db)
        snapshot = load_preferred_media_snapshot(db)

    assert exc_info.value.code == "scan_failed"
    assert _media_rows() == before
    assert status.valid
    assert status.stale_reason == "scan_failed"
    assert snapshot.source == "index"
    assert len(snapshot.scan.entries) == 1


def test_transaction_failure_rolls_back_partial_table_replacement(
    media_root: Path,
) -> None:
    path = media_root / "cover.png"
    path.write_bytes(_png_bytes(16))
    with SessionLocal() as db:
        refresh_media_index(db, full=True)
    before = _media_rows()
    path.write_bytes(_png_bytes(17))

    def fail_index_insert(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        if statement.lstrip().upper().startswith("INSERT INTO MEDIA_INDEX_ENTRIES"):
            raise RuntimeError("simulated index insert failure")

    event.listen(engine, "before_cursor_execute", fail_index_insert)
    try:
        with SessionLocal() as db:
            with pytest.raises(MediaIndexError) as exc_info:
                refresh_media_index(db, full=False)
            status = get_media_index_status(db)
    finally:
        event.remove(engine, "before_cursor_execute", fail_index_insert)

    assert exc_info.value.code == "scan_failed"
    assert _media_rows() == before
    assert status.valid
    assert status.stale_reason == "scan_failed"


def test_root_replacement_mid_scan_rejects_new_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    media_root: Path,
) -> None:
    path = media_root / "cover.png"
    path.write_bytes(_png_bytes(18))
    with SessionLocal() as db:
        refresh_media_index(db, full=True)
    before = _media_rows()
    original_directory_scan = local_media.scan_local_media_directories
    old_root = media_root.with_name("old-media")

    def replace_root_then_scan() -> tuple[
        local_media.ValidatedLocalMediaDirectory, ...
    ]:
        media_root.rename(old_root)
        media_root.mkdir()
        (media_root / "cover.png").write_bytes(_png_bytes(18))
        return original_directory_scan()

    monkeypatch.setattr(
        local_media,
        "scan_local_media_directories",
        replace_root_then_scan,
    )
    with SessionLocal() as db:
        with pytest.raises(MediaIndexError) as exc_info:
            refresh_media_index(db, full=False)

    assert exc_info.value.code == "media_root_changed"
    assert _media_rows() == before


def test_full_rebuild_recovers_from_corrupt_index(media_root: Path) -> None:
    (media_root / "cover.png").write_bytes(_png_bytes(11))
    with SessionLocal() as db:
        refresh_media_index(db, full=True)
        db.execute(
            update(MediaIndexEntry)
            .where(MediaIndexEntry.record_type == "media")
            .values(sha256="0" * 64)
        )
        db.commit()
        result = refresh_media_index(db, full=True)

    assert result.status.integrity_valid
    assert result.status.rehashed_count == 1
    assert result.status.reused_count == 0
    assert result.scan.entries[0].sha256 != "0" * 64


def test_backup_excludes_index_and_restore_invalidates_it(media_root: Path) -> None:
    (media_root / "cover.png").write_bytes(_png_bytes(12))
    with SessionLocal() as db:
        refresh_media_index(db, full=True)
        payload = export_backup_data(db)
        assert "media_index_entries" not in payload["tables"]
        assert "media_index_state" not in payload["tables"]
        db.rollback()
        from app.services.backup import restore_backup_data

        restore_backup_data(db, payload)
        state = db.get(MediaIndexState, 1)
        assert state is not None
        assert not state.valid
        assert state.stale_reason == "backup_restored"
        assert db.scalar(select(func.count()).select_from(MediaIndexEntry)) == 2


def test_scan_center_routes_are_authenticated_and_gets_are_write_free(
    client: TestClient,
    auth_client: TestClient,
    media_root: Path,
) -> None:
    (media_root / "cover.png").write_bytes(_png_bytes(13))
    client.post("/logout")
    assert client.get("/media-library/index", follow_redirects=False).status_code == 303
    assert (
        client.post("/media-library/index/refresh", follow_redirects=False).status_code
        == 303
    )
    login = auth_client.post(
        "/api/auth/login",
        json={"password": "test-password"},
    )
    assert login.status_code == 200

    refreshed = auth_client.post(
        "/media-library/index/refresh",
        follow_redirects=True,
    )
    assert refreshed.status_code == 200
    assert "增量刷新完成" in refreshed.text
    with SessionLocal() as db:
        state = db.get(MediaIndexState, 1)
        assert state is not None
        before_state = (
            state.last_attempt_at,
            state.last_success_at,
            state.snapshot_signature,
        )
        before_rows = db.scalar(select(func.count()).select_from(MediaIndexEntry))

    center = auth_client.get("/media-library/index")
    library = auth_client.get("/media-library")
    preview = auth_client.get("/media-library/index/rebuild")
    assert center.status_code == 200
    assert "媒体扫描中心" in center.text
    assert library.status_code == 200
    assert 'data-media-index-source="index"' in library.text
    assert preview.status_code == 200
    assert "本预览零写入" in preview.text

    with SessionLocal() as db:
        state = db.get(MediaIndexState, 1)
        assert state is not None
        assert (
            state.last_attempt_at,
            state.last_success_at,
            state.snapshot_signature,
        ) == before_state
        assert db.scalar(select(func.count()).select_from(MediaIndexEntry)) == before_rows

    missing_confirm = auth_client.post(
        "/media-library/index/rebuild",
        follow_redirects=True,
    )
    assert "缺少手动确认" in missing_confirm.text
    rebuilt = auth_client.post(
        "/media-library/index/rebuild",
        data={"confirm": "1"},
        follow_redirects=True,
    )
    assert "完整验证完成" in rebuilt.text
    with SessionLocal() as db:
        state = db.get(MediaIndexState, 1)
        assert state is not None
        assert state.last_full_verification_at is not None


def test_all_primary_read_pages_prefer_complete_index(
    monkeypatch: pytest.MonkeyPatch,
    auth_client: TestClient,
    media_root: Path,
) -> None:
    directory = media_root / "library"
    directory.mkdir()
    (directory / "first.png").write_bytes(_png_bytes(14))
    (directory / "second.png").write_bytes(_png_bytes(14))
    with SessionLocal() as db:
        refresh_media_index(db, full=True)

    def reject_filesystem_scan(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("read page bypassed the complete index")

    monkeypatch.setattr(
        local_media,
        "scan_local_media_incremental",
        reject_filesystem_scan,
    )
    monkeypatch.setattr(
        local_media,
        "scan_local_media_directories",
        reject_filesystem_scan,
    )

    urls = (
        "/media-library",
        "/media-library/directories?directory=/media/library",
        "/media-library/duplicates",
        "/media-library/aliases",
        "/media-library/skipped",
    )
    for url in urls:
        response = auth_client.get(url)
        assert response.status_code == 200, url
        assert 'data-media-index-source="index"' in response.text, url


def test_file_database_index_persists_across_engine_restart(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "persistent-media"
    root.mkdir()
    (root / "cover.png").write_bytes(_png_bytes(15))
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    database_path = tmp_path / "persistent.db"
    database_url = f"sqlite:///{database_path}"

    first_engine = create_engine(database_url, future=True)
    initialize_database(first_engine)
    FirstSession = sessionmaker(bind=first_engine, future=True)
    with FirstSession() as db:
        result = refresh_media_index(db, full=True)
        assert result.status.entry_count == 1
    first_engine.dispose()

    second_engine = create_engine(database_url, future=True)
    SecondSession = sessionmaker(bind=second_engine, future=True)
    try:
        with SecondSession() as db:
            snapshot = load_preferred_media_snapshot(db)
            assert snapshot.source == "index"
            assert snapshot.status.entry_count == 1
            assert snapshot.scan.entries[0].media_path == "/media/cover.png"
    finally:
        second_engine.dispose()
