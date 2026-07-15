from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.database import SessionLocal, engine
from app.models import Creator, Item
from app.services import local_media
from app.services.settings import save_app_settings


def _gif_bytes() -> bytes:
    return b"GIF89a\x01\x00\x01\x00alias;"


def _setup_aliases(root: Path) -> tuple[list[str], list[Path], Path]:
    files = [root / "one/Keep.gif", root / "two/A.gif", root / "three/B.gif"]
    independent = root / "four/Independent.gif"
    for path in [*files, independent]:
        path.parent.mkdir(parents=True, exist_ok=True)
    files[0].write_bytes(_gif_bytes())
    os.link(files[0], files[1])
    os.link(files[0], files[2])
    independent.write_bytes(_gif_bytes())
    return (
        ["/media/one/Keep.gif", "/media/two/A.gif", "/media/three/B.gif"],
        files,
        independent,
    )


def _snapshot_token(page: str) -> str:
    match = re.search(r'name="snapshot_token" value="([^"]+)"', page)
    assert match is not None
    return match.group(1)


def test_alias_normalization_route_preview_is_write_free_and_applies_exact_group(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    paths, files, independent = _setup_aliases(root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Alias A", cover_path=paths[1]),
                Creator(name="Alias B", type="person", avatar_path=paths[2]),
            ]
        )
        db.commit()
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    audit = auth_client.get("/media-library/aliases")
    assert audit.status_code == 200
    assert "data-alias-normalization-form" in audit.text

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

    before = {path: path.read_bytes() for path in [*files, independent]}
    event.listen(engine, "before_cursor_execute", capture_write)
    try:
        preview = auth_client.get(
            "/media-library/aliases/normalize",
            params=[
                *(('alias_path', path) for path in paths),
                ("keeper_path", paths[0]),
                ("next", "/media-library/aliases"),
            ],
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_write)

    assert preview.status_code == 200
    assert "data-alias-normalization-preview" in preview.text
    assert "data-alias-independent-paths" in preview.text
    assert "Alias A" in preview.text and "Alias B" in preview.text
    assert writes == []
    assert before == {path: path.read_bytes() for path in before}

    result = auth_client.post(
        "/media-library/aliases/normalize",
        data={
            "snapshot_token": _snapshot_token(preview.text),
            "next": "/media-library/aliases",
            "confirm": "1",
        },
    )

    assert result.status_code == 200
    assert 'data-alias-normalization-result="committed"' in result.text
    assert result.text.count('data-alias-result-status="deleted"') == 2
    assert files[0].exists() and not files[1].exists() and not files[2].exists()
    assert independent.read_bytes() == _gif_bytes()
    with SessionLocal() as db:
        assert tuple(db.scalars(select(Item.cover_path)).all()) == (paths[0],)
        assert tuple(db.scalars(select(Creator.avatar_path)).all()) == (paths[0],)


def test_alias_normalization_requires_login_exact_confirm_and_valid_token(
    client: TestClient,
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    paths, files, _ = _setup_aliases(root)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})
    with TestClient(client.app) as anonymous:
        denied = anonymous.get(
            "/media-library/aliases/normalize",
            params={"alias_path": paths},
            follow_redirects=False,
        )
    preview = auth_client.get(
        "/media-library/aliases/normalize",
        params=[
            *(('alias_path', path) for path in paths),
            ("keeper_path", paths[0]),
        ],
    )
    token = _snapshot_token(preview.text)
    rejected = auth_client.post(
        "/media-library/aliases/normalize",
        data={
            "snapshot_token": token,
            "confirm": "1",
            "confirmation_text": "confirm",
        },
        follow_redirects=False,
    )
    forged = token[:-1] + ("0" if token[-1] != "0" else "1")
    forged_result = auth_client.post(
        "/media-library/aliases/normalize",
        data={
            "snapshot_token": forged,
            "confirm": "1",
            "confirmation_text": "CONFIRM",
        },
        follow_redirects=False,
    )

    assert denied.status_code == 303
    assert "data-strict-confirm-message" in preview.text
    assert rejected.status_code == 303
    assert forged_result.status_code == 303
    assert all(path.exists() for path in files)
