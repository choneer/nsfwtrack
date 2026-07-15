from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import SessionLocal, engine
from app.models import Creator, Item
from app.services import local_media
from app.services.media_hardlink_aliases import query_media_hardlink_aliases


def _gif_bytes(extra: int = 0) -> bytes:
    return b"GIF89a\x01\x00\x01\x00" + (b"x" * extra) + b";"


def test_alias_audit_groups_dev_inode_and_separates_same_sha_files(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    source = root / "one" / "Source.gif"
    alias = root / "two" / "Alias.gif"
    independent = root / "three" / "Independent.gif"
    source.parent.mkdir(parents=True)
    alias.parent.mkdir(parents=True)
    independent.parent.mkdir(parents=True)
    source.write_bytes(_gif_bytes(7))
    os.link(source, alias)
    independent.write_bytes(source.read_bytes())
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)
    with SessionLocal() as db:
        db.add_all(
            [
                Item(title="Alias Cover", cover_path="/media/one/Source.gif"),
                Creator(
                    name="Alias Avatar",
                    type="person",
                    avatar_path="/media/two/Alias.gif",
                ),
            ]
        )
        db.commit()
        result = query_media_hardlink_aliases(
            db,
            local_media.scan_local_media(),
            q=None,
            sort=None,
            page=None,
        )

    assert result.total_groups == 1
    group = result.groups[0]
    assert group.path_count == 2
    assert group.reference_count == 2
    assert {row.entry.media_path for row in group.paths} == {
        "/media/one/Source.gif",
        "/media/two/Alias.gif",
    }
    assert tuple(row.media_path for row in group.same_sha_independent_paths) == (
        "/media/three/Independent.gif",
    )

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
            "/media-library/aliases",
            params={"alias_q": "Alias", "alias_sort": "references_desc"},
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_write)

    assert response.status_code == 200
    assert "data-hardlink-alias-group" in response.text
    assert "/media/one/Source.gif" in response.text
    assert "/media/two/Alias.gif" in response.text
    assert "/media/three/Independent.gif" in response.text
    assert "Alias Cover" in response.text and "Alias Avatar" in response.text
    assert "data-same-sha-independent" in response.text
    assert writes == []


def test_alias_audit_requires_login_and_paginates(
    client: TestClient,
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "media"
    root.mkdir()
    for index in range(21):
        source = root / f"Source-{index:02d}.gif"
        alias = root / f"Alias-{index:02d}.gif"
        source.write_bytes(_gif_bytes(index + 1))
        os.link(source, alias)
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", root)

    with TestClient(client.app) as anonymous:
        denied = anonymous.get("/media-library/aliases", follow_redirects=False)
    first = auth_client.get("/media-library/aliases")
    second = auth_client.get("/media-library/aliases", params={"alias_page": 2})

    assert denied.status_code == 303
    assert first.status_code == second.status_code == 200
    assert first.text.count("data-hardlink-alias-group") == 20
    assert second.text.count("data-hardlink-alias-group") == 1
