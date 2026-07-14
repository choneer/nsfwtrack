from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Creator, Item
from app.services import local_media
from app.services.data_health import build_data_health_report
from app.services.media_scan_skips import query_media_scan_skips


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _database_snapshot() -> tuple[
    tuple[tuple[int, str, str | None], ...],
    tuple[tuple[int, str, str | None], ...],
]:
    with SessionLocal() as db:
        return (
            tuple(
                (row.id, row.title, row.cover_path)
                for row in db.query(Item).order_by(Item.id)
            ),
            tuple(
                (row.id, row.name, row.avatar_path)
                for row in db.query(Creator).order_by(Creator.id)
            ),
        )


def _skip_identity(scan: local_media.LocalMediaScan) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            entry.path,
            entry.reason,
            entry.extension,
            entry.size,
            entry.device,
            entry.inode,
            entry.modified_ns,
            entry.changed_ns,
        )
        for entry in scan.skipped_entries
    )


def test_scan_records_all_skip_types_deterministically_without_content_reads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    unsupported = _write(media_root / "docs/Notes.TXT", b"do not read notes")
    escaped_name = _write(media_root / "docs/odd\nname.log", b"do not read odd")
    entry_error = _write(media_root / "broken-entry.dat", b"do not read error")
    blocked = media_root / "blocked"
    _write(blocked / "hidden.txt", b"do not enumerate")
    fifo = media_root / "events.pipe"
    os.mkfifo(fifo)
    outside = _write(tmp_path / "outside/target.png", b"outside target")
    link = media_root / "linked.png"
    link.symlink_to(outside)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    blocked_inode = blocked.stat(follow_symlinks=False).st_ino
    original_entries = local_media._sorted_scan_entries
    original_lstat = local_media._entry_lstat

    def fail_one_directory(directory_fd: int) -> list[os.DirEntry[str]]:
        if os.fstat(directory_fd).st_ino == blocked_inode:
            raise PermissionError(f"private absolute path: {blocked}")
        return original_entries(directory_fd)

    def fail_one_entry(entry: os.DirEntry[str]) -> os.stat_result:
        if entry.name == entry_error.name:
            raise OSError(f"private absolute path: {entry_error}")
        return original_lstat(entry)

    monkeypatch.setattr(local_media, "_sorted_scan_entries", fail_one_directory)
    monkeypatch.setattr(local_media, "_entry_lstat", fail_one_entry)
    before = {
        path: path.read_bytes()
        for path in (unsupported, escaped_name, entry_error, outside)
    }

    with monkeypatch.context() as no_content_read:
        original_read_bytes = Path.read_bytes

        def reject_skipped_read(path: Path) -> bytes:
            if path in before:
                raise AssertionError(f"skipped content read: {path}")
            return original_read_bytes(path)

        def reject_hash(content: bytes = b"") -> object:
            del content
            raise AssertionError("skipped content hashed")

        no_content_read.setattr(Path, "read_bytes", reject_skipped_read)
        no_content_read.setattr(local_media.hashlib, "sha256", reject_hash)
        first = local_media.scan_local_media()
        second = local_media.scan_local_media()

    by_path = {entry.path: entry for entry in first.skipped_entries}
    assert _skip_identity(first) == _skip_identity(second)
    assert tuple(by_path) == tuple(
        sorted(by_path, key=lambda path: (path.casefold(), path))
    )
    assert by_path["linked.png"].reason == "symlink"
    assert by_path["docs/Notes.TXT"].reason == "unsupported_extension"
    assert by_path["docs/Notes.TXT"].extension == ".TXT"
    assert by_path["docs/odd\\u000aname.log"].reason == "unsupported_extension"
    assert by_path["events.pipe"].reason == "special_file"
    assert by_path["blocked"].reason == "directory_unreadable"
    assert by_path["broken-entry.dat"].reason == "entry_error"
    assert by_path["broken-entry.dat"].size is None
    assert all(entry.path != str(media_root) for entry in first.skipped_entries)
    assert all("\n" not in entry.path for entry in first.skipped_entries)
    assert all(str(tmp_path) not in entry.path for entry in first.skipped_entries)
    assert first.skipped_symlinks == 1
    assert first.skipped_unsupported == 5
    assert len(first.skipped_entries) == 6
    assert first.skipped_symlinks + first.skipped_unsupported == len(
        first.skipped_entries
    )
    assert {
        entry.reason for entry in first.skipped_entries
    } == {
        "symlink",
        "unsupported_extension",
        "special_file",
        "directory_unreadable",
        "entry_error",
    }
    assert {path: path.read_bytes() for path in before} == before
    assert link.is_symlink()


def test_directory_replaced_by_symlink_is_not_followed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    racing = media_root / "racing-dir"
    _write(racing / "original.txt", b"original")
    outside = tmp_path / "outside"
    secret = _write(outside / "secret.txt", b"external secret")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    original_lstat = local_media._entry_lstat
    replaced = False

    def replace_after_lstat(entry: os.DirEntry[str]) -> os.stat_result:
        nonlocal replaced
        file_stat = original_lstat(entry)
        if entry.name == "racing-dir" and not replaced:
            racing.rename(media_root / "original-dir")
            racing.symlink_to(outside, target_is_directory=True)
            replaced = True
        return file_stat

    monkeypatch.setattr(local_media, "_entry_lstat", replace_after_lstat)
    before_secret = secret.read_bytes()
    with monkeypatch.context() as no_read:
        original_read_bytes = Path.read_bytes

        def reject_secret_read(path: Path) -> bytes:
            if path == secret:
                raise AssertionError("symlink target content read")
            return original_read_bytes(path)

        no_read.setattr(Path, "read_bytes", reject_secret_read)
        scan = local_media.scan_local_media()

    assert replaced is True
    assert any(
        entry.path == "racing-dir" and entry.reason == "symlink"
        for entry in scan.skipped_entries
    )
    assert all("secret.txt" not in entry.path for entry in scan.skipped_entries)
    assert secret.read_bytes() == before_secret


def test_legacy_counts_and_media_boundaries_remain_compatible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    ordinary = _write(media_root / "ordinary.gif", _gif_bytes(1))
    recovered = _write(media_root / "recovered-copy.gif", _gif_bytes(2))
    anchor = _write(media_root / ".cleanup-anchor-hidden.gif", _gif_bytes(3))
    residue = _write(media_root / ".upload-stale.tmp", b"partial")
    note = _write(media_root / "note.txt", b"note")
    outside = _write(tmp_path / "outside.gif", _gif_bytes(4))
    symlink = media_root / "linked.gif"
    symlink.symlink_to(outside)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    ordinary_scan = local_media.scan_local_media()
    recovery_scan = local_media.scan_local_media(include_cleanup_anchors=True)

    assert {entry.media_path for entry in ordinary_scan.entries} == {
        "/media/ordinary.gif",
        "/media/recovered-copy.gif",
    }
    assert {entry.media_path for entry in recovery_scan.entries} == {
        "/media/.cleanup-anchor-hidden.gif",
        "/media/ordinary.gif",
        "/media/recovered-copy.gif",
    }
    assert ordinary_scan.skipped_symlinks == 1
    assert ordinary_scan.skipped_unsupported == 2
    assert {
        (entry.path, entry.reason)
        for entry in ordinary_scan.skipped_entries
    } == {
        (".upload-stale.tmp", "unsupported_extension"),
        ("linked.gif", "symlink"),
        ("note.txt", "unsupported_extension"),
    }
    assert ordinary.read_bytes() == _gif_bytes(1)
    assert recovered.read_bytes() == _gif_bytes(2)
    assert anchor.read_bytes() == _gif_bytes(3)
    assert residue.read_bytes() == b"partial"
    assert note.read_bytes() == b"note"
    assert symlink.is_symlink()


def test_query_search_type_sort_and_pagination_are_stable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    for index in range(25):
        _write(media_root / f"docs/file-{index:02d}.txt", f"{index}".encode())
    outside = _write(tmp_path / "outside.png", b"outside")
    (media_root / "docs-link.png").symlink_to(outside)
    fifo = media_root / "special.pipe"
    os.mkfifo(fifo)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    scan = local_media.scan_local_media()

    result = query_media_scan_skips(
        scan,
        q="docs/file-",
        skip_type="unsupported_extension",
        sort="path_desc",
        page=2,
    )
    invalid = query_media_scan_skips(
        scan,
        q="x" * 201,
        skip_type="invalid",
        sort="invalid",
        page="invalid",
    )
    legacy = query_media_scan_skips(
        scan,
        q=None,
        skip_type="unsupported",
        sort="type_asc",
        page=1,
    )

    assert result.page_info.page_size == 20
    assert result.page_info.total == 25
    assert result.page_info.total_pages == 2
    assert len(result.rows) == 5
    assert [entry.path for entry in result.rows] == [
        "docs/file-04.txt",
        "docs/file-03.txt",
        "docs/file-02.txt",
        "docs/file-01.txt",
        "docs/file-00.txt",
    ]
    assert invalid.filters.q == ""
    assert invalid.filters.skip_type == "all"
    assert invalid.filters.sort == "path_asc"
    assert invalid.page_info.page == 1
    assert legacy.page_info.total == scan.skipped_unsupported == 26
    assert legacy.legacy_unsupported_count == scan.skipped_unsupported
    assert legacy.symlink_count == scan.skipped_symlinks == 1


def test_readonly_page_is_authenticated_paginated_and_zero_write(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    paths = [
        _write(media_root / f"docs/file-{index:02d}.txt", f"body-{index}".encode())
        for index in range(25)
    ]
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    with SessionLocal() as db:
        db.add(Item(title="Unchanged", cover_path=None))
        db.commit()
    before_db = _database_snapshot()
    before_files = {path: path.read_bytes() for path in paths}

    with TestClient(auth_client.app) as anonymous:
        denied = anonymous.get("/media-library/skipped", follow_redirects=False)
    with monkeypatch.context() as no_read:
        original_read_bytes = Path.read_bytes

        def reject_read(path: Path) -> bytes:
            if path in before_files:
                raise AssertionError(f"skipped content read: {path}")
            return original_read_bytes(path)

        no_read.setattr(Path, "read_bytes", reject_read)
        first = auth_client.get("/media-library/skipped")
        second = auth_client.get(
            "/media-library/skipped",
            params={
                "skip_q": "docs/file-",
                "skip_type": "unsupported_extension",
                "skip_sort": "path_desc",
                "skip_page": "2",
            },
        )
    post = auth_client.post("/media-library/skipped", follow_redirects=False)

    assert denied.status_code == 303
    assert first.status_code == 200
    assert "data-media-scan-skips" in first.text
    assert first.text.count("data-skip-path=") == 20
    assert "安全相对路径" in first.text
    assert "扩展名不支持" in first.text
    assert "设备号 (device)" in first.text
    assert "mtime（纳秒）" in first.text
    assert "不会被读取、解析或哈希" in first.text
    assert str(media_root) not in first.text
    assert second.status_code == 200
    assert second.text.count("data-skip-path=") == 5
    assert 'value="docs/file-"' in second.text
    assert '<option value="unsupported_extension" selected>' in second.text
    assert '<option value="path_desc" selected>' in second.text
    assert "skip_type=unsupported_extension" in second.text
    assert "skip_sort=path_desc" in second.text
    assert "skip_q=docs%2Ffile-" in second.text
    assert "skip_page=1" in second.text
    assert post.status_code == 405
    assert _database_snapshot() == before_db
    assert {path: path.read_bytes() for path in before_files} == before_files


def test_data_health_links_both_legacy_summaries_to_consistent_filters(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    note = _write(media_root / "note.txt", b"note")
    fifo = media_root / "events.pipe"
    os.mkfifo(fifo)
    outside = _write(tmp_path / "outside.gif", _gif_bytes())
    link = media_root / "linked.gif"
    link.symlink_to(outside)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    before_db = _database_snapshot()

    with SessionLocal() as db:
        report = build_data_health_report(db)
    response = auth_client.get("/data-health")
    scan = local_media.scan_local_media()
    by_code = {issue.code: issue for issue in report.issues}

    assert response.status_code == 200
    assert 'href="/media-library/skipped?skip_type=symlink"' in response.text
    assert 'href="/media-library/skipped?skip_type=unsupported"' in response.text
    assert response.text.count("查看跳过项") == 2
    assert by_code["media_scan_skipped_symlinks"].detail == (
        f"count={scan.skipped_symlinks}"
    )
    assert by_code["media_scan_skipped_unsupported"].detail == (
        f"count={scan.skipped_unsupported}"
    )
    assert scan.skipped_symlinks == sum(
        entry.reason == "symlink" for entry in scan.skipped_entries
    )
    assert scan.skipped_unsupported == sum(
        entry.reason != "symlink" for entry in scan.skipped_entries
    )
    assert _database_snapshot() == before_db
    assert note.read_bytes() == b"note"
    assert link.is_symlink()


def test_english_page_has_readonly_boundary_and_no_raw_error(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    broken = _write(media_root / "private.dat", b"private")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    original_lstat = local_media._entry_lstat

    def fail_entry(entry: os.DirEntry[str]) -> os.stat_result:
        if entry.name == broken.name:
            raise OSError(f"raw private error at {broken}")
        return original_lstat(entry)

    monkeypatch.setattr(local_media, "_entry_lstat", fail_entry)
    response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/media-library/skipped"},
    )

    assert response.status_code == 200
    assert "Media Scan Skipped Items" in response.text
    assert "Entry Check Error" in response.text
    assert "never reads, parses, or hashes skipped-file content" in response.text
    assert "absolute paths and raw system errors are never shown" in response.text
    assert str(tmp_path) not in response.text
    assert "raw private error" not in response.text


def test_empty_scan_page_and_old_four_argument_scan_constructor_remain_valid(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    legacy = local_media.LocalMediaScan((), 0, 0, 0)

    response = auth_client.get("/media-library/skipped")

    assert legacy.skipped_entries == ()
    assert response.status_code == 200
    assert "没有匹配的跳过项" in response.text
    assert "data-media-scan-skips" not in response.text
