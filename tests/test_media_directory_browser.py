from __future__ import annotations

import html
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import SessionLocal, engine
from app.models import Creator, Item
from app.services import local_media


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(root: Path, relative_path: str, *, extra: int = 0) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def test_directory_browser_is_authenticated_read_only_and_preserves_state(
    client: TestClient,
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    first = _write_gif(root, "library/First.gif", extra=1)
    _write_gif(root, "library/Duplicate.gif", extra=1)
    damaged = root / "library" / "Damaged.gif"
    damaged.write_bytes(b"damaged")
    _write_gif(root, "library/nested/Child.gif", extra=2)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Used Item", cover_path="/media/library/First.gif"),
                Creator(
                    name="Used Creator",
                    type="person",
                    avatar_path="/media/library/Duplicate.gif",
                ),
            ]
        )
        db.commit()
    before_files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
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

    with TestClient(client.app) as anonymous:
        denied = anonymous.get(
            "/media-library/directories",
            follow_redirects=False,
        )
    event.listen(engine, "before_cursor_execute", capture_write)
    try:
        response = auth_client.get(
            "/media-library/directories",
            params={
                "directory": "/media/library",
                "dir_q": "First",
                "dir_status": "used",
                "dir_sort": "size_desc",
                "dir_page": "1",
            },
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_write)

    page = html.unescape(response.text)
    assert denied.status_code == 303
    assert response.status_code == 200
    assert "data-media-directory-breadcrumbs" in page
    assert "/media/library" in page
    assert "nested/" in page
    assert "First.gif" in page
    assert "Duplicate.gif" not in page
    assert "Damaged.gif" not in page
    assert 'name="dir_q" value="First"' in page
    assert 'value="used" selected' in page
    assert 'value="size_desc" selected' in page
    assert "directory=%2Fmedia%2Flibrary" in page
    assert "dir_status=used" in page
    assert writes == []
    assert first.exists()
    assert before_files == {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_directory_stats_pagination_and_invalid_directories(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    for index in range(22):
        _write_gif(root, f"page/File-{index:02d}.gif", extra=index + 1)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)

    first = auth_client.get(
        "/media-library/directories",
        params={"directory": "/media/page"},
    )
    second = auth_client.get(
        "/media-library/directories",
        params={"directory": "/media/page", "dir_page": 2},
    )

    assert first.status_code == second.status_code == 200
    assert "File-00.gif" in first.text and "File-19.gif" in first.text
    assert "File-20.gif" not in first.text
    assert "File-20.gif" in second.text and "File-21.gif" in second.text
    assert "22" in first.text
    for invalid in (
        "/media/missing",
        "/media/linked",
        "/media/../outside",
        "https://example.invalid/media",
    ):
        response = auth_client.get(
            "/media-library/directories",
            params={"directory": invalid},
        )
        assert response.status_code == 404
