from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.database import SessionLocal, engine
from app.models import Creator, Item
from app.services import local_media
from app.services.settings import save_app_settings


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def _write_gif(root: Path, relative_path: str, extra: int = 0) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_gif_bytes(extra))
    return path


def _snapshot_tokens(page: str) -> list[str]:
    return re.findall(r'name="snapshot_token" value="([^"]+)"', page)


def _database_paths() -> tuple[tuple[str | None, ...], tuple[str | None, ...]]:
    with SessionLocal() as db:
        return (
            tuple(db.scalars(select(Item.cover_path).order_by(Item.id)).all()),
            tuple(db.scalars(select(Creator.avatar_path).order_by(Creator.id)).all()),
        )


def test_batch_routes_preview_without_writes_and_report_each_result(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    first = _write_gif(root, "source/First.gif", 1)
    second = _write_gif(root, "source/Second.gif", 2)
    (root / "target").mkdir()
    paths = ["/media/source/First.gif", "/media/source/Second.gif"]
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="First", cover_path=paths[0]),
                Creator(name="Second", type="person", avatar_path=paths[1]),
            ]
        )
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)

    library = auth_client.get("/media-library")
    assert library.status_code == 200
    assert library.text.count('class="media-batch-checkbox"') == 2

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

    before = {first: first.read_bytes(), second: second.read_bytes()}
    event.listen(engine, "before_cursor_execute", capture_write)
    try:
        draft = auth_client.get(
            "/media-library/batch/move",
            params=[
                ("media_path", paths[0]),
                ("media_path", paths[1]),
                ("next", "/media-library?media_page=1#media-files"),
            ],
        )
        prepared = auth_client.get(
            "/media-library/batch/move",
            params=[
                ("media_path", paths[0]),
                ("media_path", paths[1]),
                ("target_directory", "/media/target"),
                ("target_basename", "Moved-First.gif"),
                ("target_basename", "Moved-Second.gif"),
                ("prepared", "1"),
                ("next", "/media-library?media_page=1#media-files"),
            ],
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_write)

    assert draft.status_code == prepared.status_code == 200
    assert "data-media-batch-editor" in draft.text
    assert "data-media-batch-preview" not in draft.text
    assert "data-media-batch-preview" in prepared.text
    assert "First" in prepared.text and "Second" in prepared.text
    tokens = _snapshot_tokens(prepared.text)
    assert len(tokens) == 2
    assert writes == []
    assert before == {first: first.read_bytes(), second: second.read_bytes()}
    assert not list((root / "target").iterdir())

    result = auth_client.post(
        "/media-library/batch/move",
        data={
            "snapshot_token": tokens,
            "next": "/media-library?media_page=1#media-files",
            "confirm": "1",
        },
    )

    assert result.status_code == 200
    assert result.text.count('data-batch-result-status="success"') == 2
    assert not first.exists() and not second.exists()
    assert (root / "target" / "Moved-First.gif").read_bytes() == _gif_bytes(1)
    assert (root / "target" / "Moved-Second.gif").read_bytes() == _gif_bytes(2)
    assert _database_paths() == (
        ("/media/target/Moved-First.gif",),
        ("/media/target/Moved-Second.gif",),
    )


def test_batch_route_rejects_anonymous_outside_page_and_forged_snapshot(
    client: TestClient,
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    for index in range(21):
        _write_gif(root, f"File-{index:02d}.gif", index + 1)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)

    with TestClient(client.app) as anonymous:
        denied = anonymous.get(
            "/media-library/batch/rename",
            params={"media_path": "/media/File-00.gif"},
            follow_redirects=False,
        )
    outside = auth_client.get(
        "/media-library/batch/rename",
        params={
            "media_path": "/media/File-20.gif",
            "next": "/media-library?media_page=1",
        },
        follow_redirects=False,
    )
    prepared = auth_client.get(
        "/media-library/batch/rename",
        params=[
            ("media_path", "/media/File-00.gif"),
            ("target_basename", "Renamed.gif"),
            ("prepared", "1"),
            ("next", "/media-library?media_page=1"),
        ],
    )
    token = _snapshot_tokens(prepared.text)[0]
    forged = token[:-1] + ("0" if token[-1] != "0" else "1")
    rejected = auth_client.post(
        "/media-library/batch/rename",
        data={"snapshot_token": forged, "confirm": "1"},
        follow_redirects=False,
    )

    assert denied.status_code == 303
    assert outside.status_code == 303
    assert rejected.status_code == 303
    assert (root / "File-00.gif").exists()
    assert not (root / "Renamed.gif").exists()


def test_batch_route_strict_confirmation_requires_exact_confirm(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = _write_gif(root, "Strict.gif", 4)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})
    prepared = auth_client.get(
        "/media-library/batch/rename",
        params={
            "media_path": "/media/Strict.gif",
            "target_basename": "Renamed.gif",
            "prepared": "1",
            "next": "/media-library",
        },
    )
    token = _snapshot_tokens(prepared.text)[0]

    rejected = auth_client.post(
        "/media-library/batch/rename",
        data={
            "snapshot_token": token,
            "confirm": "1",
            "confirmation_text": "confirm",
        },
        follow_redirects=False,
    )
    rejected_kept_source = source.exists()
    accepted = auth_client.post(
        "/media-library/batch/rename",
        data={
            "snapshot_token": token,
            "confirm": "1",
            "confirmation_text": "CONFIRM",
        },
    )

    assert "data-strict-confirm-message" in prepared.text
    assert rejected.status_code == 303 and rejected_kept_source is True
    assert accepted.status_code == 200
    assert (root / "Renamed.gif").exists()
