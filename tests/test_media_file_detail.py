from __future__ import annotations

import hashlib
import html
import os
import re
import stat
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import SessionLocal, engine
from app.models import Creator, Item
from app.services import local_media


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


def _object_snapshot() -> tuple[
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


def _file_snapshot(path: Path) -> tuple[int, int, int, int, int, int, bytes]:
    file_stat = path.lstat()
    content = path.read_bytes() if stat.S_ISREG(file_stat.st_mode) else b""
    after = path.lstat()
    return (
        after.st_mode,
        after.st_size,
        after.st_dev,
        after.st_ino,
        after.st_mtime_ns,
        after.st_ctime_ns,
        content,
    )


def _directory_snapshot(
    path: Path,
) -> tuple[int, int, int, int, int, int, tuple[str, ...]]:
    directory_stat = path.lstat()
    return (
        directory_stat.st_mode,
        directory_stat.st_size,
        directory_stat.st_dev,
        directory_stat.st_ino,
        directory_stat.st_mtime_ns,
        directory_stat.st_ctime_ns,
        tuple(sorted(child.name for child in path.iterdir())),
    )


def _detail_links(page_text: str) -> list[tuple[str, dict[str, list[str]]]]:
    hrefs = re.findall(r'href="([^"]+)"', html.unescape(page_text))
    links: list[tuple[str, dict[str, list[str]]]] = []
    for href in hrefs:
        parsed = urlsplit(href)
        if parsed.path == "/media-library/detail":
            links.append((href, parse_qs(parsed.query)))
    return links


def _detail_link_for(page_text: str, media_path: str) -> str:
    return next(
        href
        for href, query in _detail_links(page_text)
        if query.get("media_path") == [media_path]
    )


def test_detail_page_requires_login_and_rejects_post(client: TestClient) -> None:
    get_response = client.get(
        "/media-library/detail",
        params={"media_path": "/media/example.gif"},
        follow_redirects=False,
    )
    post_response = client.post(
        "/media-library/detail",
        data={"media_path": "/media/example.gif"},
        follow_redirects=False,
    )

    assert get_response.status_code == 303
    assert post_response.status_code == 405


def test_valid_recovered_duplicate_detail_shows_complete_facts_and_is_read_only(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, "Copies/recovered-Primary.gif", extra=12)
    duplicate = _write_gif(media_root, "Copies/Secondary.gif", extra=12)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    target_path = _media_path(target, media_root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="First Item", cover_path=target_path),
                Item(title="Second Item", cover_path=target_path),
                Creator(name="First Creator", type="person", avatar_path=target_path),
                Creator(name="Second Creator", type="studio", avatar_path=target_path),
            ]
        )
        db.commit()
        item_ids = [row.id for row in db.query(Item).order_by(Item.id)]
        creator_ids = [row.id for row in db.query(Creator).order_by(Creator.id)]
    before_db = _object_snapshot()
    before_files = {
        target: _file_snapshot(target),
        duplicate: _file_snapshot(duplicate),
    }
    before_directories = {
        media_root: _directory_snapshot(media_root),
        target.parent: _directory_snapshot(target.parent),
    }
    writes: list[str] = []

    def capture_writes(
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

    event.listen(engine, "before_cursor_execute", capture_writes)
    return_url = (
        "/media-library?media_q=Copies&media_status=duplicate&"
        "media_sort=size_desc&media_page=2&match_page=1&create_page=1#media-files"
    )
    try:
        response = auth_client.get(
            "/media-library/detail",
            params={"media_path": target_path, "next": return_url},
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_writes)

    digest = _digest(target)
    page = html.unescape(response.text)
    assert response.status_code == 200
    assert f'data-media-detail-path="{target_path}"' in page
    assert 'data-media-detail-filename>recovered-Primary.gif<' in page
    assert 'data-media-detail-extension>.gif<' in page
    assert 'data-media-detail-mime>image/gif<' in page
    assert f'data-media-detail-size>{len(_gif_bytes(12))} B<' in page
    assert f'data-media-detail-sha256>{digest}<' in page
    assert 'data-media-detail-validity="valid"' in page
    assert 'data-media-detail-recovery="recovered"' in page
    assert 'data-media-detail-reference-status="referenced"' in page
    assert 'data-media-detail-duplicate-status="duplicate"' in page
    assert 'data-media-detail-duplicate-members>2<' in page
    assert f'data-media-detail-file-size>{len(_gif_bytes(12))} B<' in page
    assert f'data-media-detail-total-bytes>{len(_gif_bytes(12)) * 2} B<' in page
    assert f'data-media-detail-reclaimable-bytes>{len(_gif_bytes(12))} B<' in page
    assert f'data-media-detail-duplicate-path="{target_path}"' in page
    assert f'data-media-detail-duplicate-path="{_media_path(duplicate, media_root)}"' in page
    assert all(f'href="/items/{item_id}"' in page for item_id in item_ids)
    assert all(f'href="/creators/{creator_id}"' in page for creator_id in creator_ids)
    duplicate_link = next(
        href
        for href in re.findall(r'href="([^"]+)"', page)
        if urlsplit(href).path == "/media-library/duplicates"
    )
    parsed_duplicate_link = urlsplit(duplicate_link)
    assert parse_qs(parsed_duplicate_link.query) == {"duplicate_q": [digest]}
    assert parsed_duplicate_link.fragment == f"media-duplicate-{digest}"
    assert f'href="{return_url}"' in page
    assert str(tmp_path) not in page
    assert "Traceback" not in page
    assert writes == []
    assert _object_snapshot() == before_db
    assert {path: _file_snapshot(path) for path in before_files} == before_files
    assert {
        path: _directory_snapshot(path)
        for path in before_directories
    } == before_directories


def test_damaged_detail_reuses_c1_and_c4_without_adding_a_write_action(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = media_root / "Broken" / "Damaged.gif"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"not-an-image")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    target_path = _media_path(target, media_root)
    with SessionLocal() as db:
        item = Item(title="Broken Cover", cover_path=target_path)
        creator = Creator(
            name="Broken Avatar",
            type="person",
            avatar_path=target_path,
        )
        db.add_all([item, creator])
        db.commit()
        item_id = item.id
        creator_id = creator.id
    before_db = _object_snapshot()
    before_file = _file_snapshot(target)

    response = auth_client.get(
        "/media-library/detail",
        params={"media_path": target_path},
    )

    digest = hashlib.sha256(b"not-an-image").hexdigest()
    page = html.unescape(response.text)
    assert response.status_code == 200
    assert f'data-media-detail-sha256>{digest}<' in page
    assert 'data-media-detail-mime>无法安全确认<' in page
    assert 'data-media-detail-validity="damaged"' in page
    assert 'data-media-detail-recovery="ordinary"' in page
    assert 'data-media-detail-reference-status="referenced"' in page
    assert 'data-media-detail-duplicate-status="unique"' in page
    c4_link = next(
        href
        for href in re.findall(r'href="([^"]+)"', page)
        if urlsplit(href).path == "/data-health/damaged-media/delete-preview"
    )
    assert parse_qs(urlsplit(c4_link).query) == {
        "media_path": [target_path],
        "sha256": [digest],
    }
    c1_queries = [
        parse_qs(urlsplit(href).query)
        for href in re.findall(r'href="([^"]+)"', page)
        if urlsplit(href).path == "/data-health/media-reference/repair"
    ]
    assert {query["object_type"][0] for query in c1_queries} == {
        "item_cover",
        "creator_avatar",
    }
    assert {query["object_id"][0] for query in c1_queries} == {
        str(item_id),
        str(creator_id),
    }
    assert 'action="/media-library/detail"' not in page
    assert _object_snapshot() == before_db
    assert _file_snapshot(target) == before_file


def test_unique_unreferenced_detail_is_bilingual(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, "Unique.gif", extra=3)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    target_path = _media_path(target, media_root)

    chinese = auth_client.get(
        "/media-library/detail",
        params={"media_path": target_path},
    )
    auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/media-library"},
    )
    english = auth_client.get(
        "/media-library/detail",
        params={"media_path": target_path},
    )

    assert chinese.status_code == 200
    assert 'data-media-detail-reference-status="unreferenced"' in chinese.text
    assert 'data-media-detail-duplicate-status="unique"' in chinese.text
    assert "没有条目封面或创作者头像引用" in chinese.text
    assert english.status_code == 200
    assert "Read-only File Facts" in english.text
    assert "Complete SHA-256" in english.text
    assert "No item cover or creator avatar references" in english.text


@pytest.mark.parametrize(
    "media_path",
    [
        None,
        "https://example.com/image.gif",
        "/etc/passwd",
        "/media/../secret.gif",
        "/media/%2e%2e/secret.gif",
        "/media//double.gif",
        "/media/residue.tmp",
        "/media/Missing.gif",
    ],
)
def test_detail_rejects_invalid_external_and_missing_paths(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    media_path: str | None,
) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    params = {} if media_path is None else {"media_path": media_path}

    response = auth_client.get("/media-library/detail", params=params)

    assert response.status_code == 404
    assert str(tmp_path) not in response.text
    assert "Traceback" not in response.text
    assert "OSError" not in response.text


def test_detail_rejects_anchor_symlink_directory_and_special_file_without_external_read(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    anchor = _write_gif(media_root, ".cleanup-anchor-private.gif", extra=2)
    external = tmp_path / "external.gif"
    external.write_bytes(_gif_bytes(20))
    symlink = media_root / "linked.gif"
    symlink.symlink_to(external)
    directory = media_root / "folder.gif"
    directory.mkdir()
    fifo = media_root / "pipe.gif"
    os.mkfifo(fifo)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    before_external = _file_snapshot(external)

    for target in (anchor, symlink, directory, fifo):
        response = auth_client.get(
            "/media-library/detail",
            params={"media_path": _media_path(target, media_root)},
        )
        assert response.status_code == 404
        assert str(tmp_path) not in response.text

    assert _file_snapshot(external) == before_external
    assert symlink.is_symlink()
    assert directory.is_dir()
    assert stat.S_ISFIFO(fifo.lstat().st_mode)


def test_detail_does_not_reopen_target_with_path_stat_or_read_bytes(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, "Nested/Target.gif", extra=4)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    original_stat = Path.stat
    original_read_bytes = Path.read_bytes

    def guarded_stat(path: Path, *args: object, **kwargs: object) -> os.stat_result:
        if path == target:
            raise AssertionError("detail target reopened with Path.stat")
        return original_stat(path, *args, **kwargs)

    def guarded_read_bytes(path: Path) -> bytes:
        if path == target:
            raise AssertionError("detail target reopened with Path.read_bytes")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "stat", guarded_stat)
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)

    response = auth_client.get(
        "/media-library/detail",
        params={"media_path": _media_path(target, media_root)},
    )

    assert response.status_code == 200
    assert 'data-media-detail-validity="valid"' in response.text


def test_detail_parent_replacement_race_never_reads_external_target(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    parent = media_root / "Nested"
    target = _write_gif(media_root, "Nested/Target.gif", extra=5)
    original_content = target.read_bytes()
    external = tmp_path / "external"
    external_target = _write_gif(external, "Target.gif", extra=30)
    moved = media_root / "Moved"
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    original_read = local_media._read_scan_file_descriptor
    observed: list[bytes] = []

    def replace_parent_after_fd_read(file_descriptor: int) -> bytes:
        content = original_read(file_descriptor)
        observed.append(content)
        parent.rename(moved)
        parent.symlink_to(external, target_is_directory=True)
        return content

    monkeypatch.setattr(
        local_media,
        "_read_scan_file_descriptor",
        replace_parent_after_fd_read,
    )

    response = auth_client.get(
        "/media-library/detail",
        params={"media_path": "/media/Nested/Target.gif"},
    )

    assert response.status_code == 404
    assert observed == [original_content]
    assert parent.is_symlink()
    assert (moved / "Target.gif").read_bytes() == original_content
    assert external_target.read_bytes() == _gif_bytes(30)
    assert str(tmp_path) not in response.text


def test_library_duplicate_and_recovery_detail_links_preserve_source_state(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    for index in range(21):
        _write_gif(media_root, f"Nav/Z{index:02d}.gif", extra=index)
    target = _write_gif(media_root, "Nav/recovered-A.gif", extra=40)
    duplicate = _write_gif(media_root, "Nav/B-copy.gif", extra=40)
    anchor = _write_gif(media_root, "Nav/.cleanup-anchor-private.gif", extra=7)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)
    target_path = _media_path(target, media_root)
    digest = _digest(target)

    library = auth_client.get(
        "/media-library",
        params={
            "media_q": "Nav",
            "media_status": "unused",
            "media_sort": "filename_desc",
            "media_page": "2",
            "match_page": "1",
            "create_page": "1",
        },
    )
    library_detail = _detail_link_for(library.text, target_path)
    library_next = parse_qs(urlsplit(library_detail).query)["next"][0]
    parsed_library_next = urlsplit(library_next)
    assert parsed_library_next.path == "/media-library"
    assert parsed_library_next.fragment == "media-files"
    assert parse_qs(parsed_library_next.query) == {
        "media_q": ["Nav"],
        "media_status": ["unused"],
        "media_sort": ["filename_desc"],
        "media_page": ["2"],
        "match_page": ["1"],
        "create_page": ["1"],
    }

    duplicates = auth_client.get(
        "/media-library/duplicates",
        params={
            "duplicate_q": digest,
            "duplicate_sort": "reclaimable_desc",
            "duplicate_page": "1",
        },
    )
    duplicate_detail = _detail_link_for(duplicates.text, target_path)
    duplicate_next = parse_qs(urlsplit(duplicate_detail).query)["next"][0]
    parsed_duplicate_next = urlsplit(duplicate_next)
    assert parsed_duplicate_next.path == "/media-library/duplicates"
    assert parsed_duplicate_next.fragment == f"media-duplicate-{digest}"
    assert parse_qs(parsed_duplicate_next.query) == {
        "duplicate_q": [digest],
        "duplicate_sort": ["reclaimable_desc"],
        "duplicate_page": ["1"],
    }

    recovery = auth_client.get(
        "/media-library/recovery",
        params={
            "recovery_q": "recovered-A",
            "recovery_status": "recovered",
            "recovery_sort": "size_desc",
            "recovery_page": "1",
        },
    )
    recovery_detail = _detail_link_for(recovery.text, target_path)
    recovery_next = parse_qs(urlsplit(recovery_detail).query)["next"][0]
    parsed_recovery_next = urlsplit(recovery_next)
    assert parsed_recovery_next.path == "/media-library/recovery"
    assert parse_qs(parsed_recovery_next.query) == {
        "recovery_q": ["recovered-A"],
        "recovery_status": ["recovered"],
        "recovery_sort": ["size_desc"],
        "recovery_page": ["1"],
    }

    recovery_all = auth_client.get("/media-library/recovery")
    assert all(
        query.get("media_path") != [_media_path(anchor, media_root)]
        for _, query in _detail_links(recovery_all.text)
    )
    assert _media_path(duplicate, media_root) in duplicates.text


def test_detail_rejects_external_return_url(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    target = _write_gif(media_root, "Target.gif")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    response = auth_client.get(
        "/media-library/detail",
        params={
            "media_path": _media_path(target, media_root),
            "next": "https://example.com/escape",
        },
    )

    assert response.status_code == 200
    assert 'href="/media-library"' in response.text
    assert "example.com/escape" not in response.text
