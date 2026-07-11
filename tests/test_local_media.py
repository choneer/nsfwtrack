from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Collection, Creator, Item, Tag
from app.services import local_media
from app.services.backup_validator import validate_backup_payload


INVALID_MEDIA_PATHS = [
    "https://example.invalid/cover.jpg",
    "//example.invalid/cover.jpg",
    "data:image/png;base64,AAAA",
    "/covers/cover.jpg",
    "/media/../cover.jpg",
    "/media/covers\\cover.jpg",
    "/media/covers%2Fcover.jpg",
    "/media/cover.svg",
    "/media/cover.jpg?source=remote",
]


@pytest.mark.parametrize("path", INVALID_MEDIA_PATHS)
def test_item_api_rejects_non_local_cover_paths_without_writing(
    auth_client: TestClient,
    path: str,
) -> None:
    response = auth_client.post(
        "/api/items",
        json={"title": "Rejected Cover", "cover_path": path},
    )

    assert response.status_code == 422
    assert auth_client.get("/api/items").json()["total"] == 0


@pytest.mark.parametrize("path", INVALID_MEDIA_PATHS)
def test_creator_api_rejects_non_local_avatar_paths_without_writing(
    auth_client: TestClient,
    path: str,
) -> None:
    response = auth_client.post(
        "/api/creators",
        json={"name": "Rejected Avatar", "avatar_path": path},
    )

    assert response.status_code == 422
    assert auth_client.get("/api/creators").json() == []


def test_page_forms_reject_external_media_paths(auth_client: TestClient) -> None:
    item_response = auth_client.post(
        "/items",
        data={"title": "Page Cover", "cover_path": "https://example.invalid/a.jpg"},
        follow_redirects=True,
    )
    creator_response = auth_client.post(
        "/creators",
        data={
            "name": "Page Avatar",
            "type_value": "other",
            "avatar_path": "//example.invalid/a.jpg",
        },
        follow_redirects=True,
    )

    assert item_response.status_code == 200
    assert creator_response.status_code == 200
    with SessionLocal() as db:
        assert db.query(Item).count() == 0
        assert db.query(Creator).count() == 0


def test_valid_local_cover_renders_and_is_served_only_after_login(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    media_root = tmp_path / "media"
    cover = media_root / "covers" / "sample.png"
    cover.parent.mkdir(parents=True)
    cover.write_bytes(b"local-image")
    monkeypatch.setattr(local_media, "LOCAL_MEDIA_ROOT", media_root)

    created = auth_client.post(
        "/api/items",
        json={"title": "Local Cover", "cover_path": "/media/covers/sample.png"},
    )
    item_id = created.json()["id"]
    with SessionLocal() as db:
        item = db.get(Item, item_id)
        assert item is not None
        collection = Collection(name="Local Media Collection")
        collection.items.append(item)
        db.add(collection)
        db.commit()
        collection_id = collection.id
    list_response = auth_client.get("/items")
    detail_response = auth_client.get(f"/items/{item_id}")
    collection_response = auth_client.get(f"/collections/{collection_id}")
    file_response = auth_client.get("/media/covers/sample.png")

    assert created.status_code == 201
    assert 'src="/media/covers/sample.png"' in list_response.text
    assert 'src="/media/covers/sample.png"' in detail_response.text
    assert 'src="/media/covers/sample.png"' in collection_response.text
    assert file_response.status_code == 200
    assert file_response.content == b"local-image"
    auth_client.cookies.clear()
    unauthenticated = auth_client.get(
        "/media/covers/sample.png",
        follow_redirects=False,
    )
    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"] == "/login"


def test_legacy_external_cover_is_not_rendered(auth_client: TestClient) -> None:
    external_url = "https://example.invalid/legacy.png"
    with SessionLocal() as db:
        item = Item(title="Legacy Cover", cover_path=external_url)
        collection = Collection(name="Legacy Cover Collection")
        collection.items.append(item)
        db.add_all([item, collection])
        db.commit()
        item_id = item.id
        collection_id = collection.id

    list_response = auth_client.get("/items")
    detail_response = auth_client.get(f"/items/{item_id}")
    collection_response = auth_client.get(f"/collections/{collection_id}")

    assert external_url not in list_response.text
    assert external_url not in detail_response.text
    assert external_url not in collection_response.text


@pytest.mark.parametrize(
    ("table_name", "field_name", "row"),
    [
        (
            "items",
            "cover_path",
            {"id": 101, "title": "Backup Item", "cover_path": "https://example.invalid/a.jpg"},
        ),
        (
            "creators",
            "avatar_path",
            {"id": 102, "name": "Backup Creator", "avatar_path": "//example.invalid/a.jpg"},
        ),
    ],
)
def test_backup_preview_and_restore_reject_invalid_media_without_partial_write(
    auth_client: TestClient,
    table_name: str,
    field_name: str,
    row: dict[str, object],
) -> None:
    payload = auth_client.get("/api/backup/export/json").json()
    payload["tables"][table_name].append(row)
    payload["tables"]["tags"].append({"id": 103, "name": "Must Not Restore"})
    report = validate_backup_payload(payload).to_dict()
    upload = {
        "file": (
            "backup.json",
            json.dumps(payload).encode("utf-8"),
            "application/json",
        )
    }

    preview_response = auth_client.post("/api/backup/preview/json", files=upload)
    restore_response = auth_client.post(
        "/api/backup/restore/json",
        data={"confirm": "1"},
        files=upload,
    )

    assert report["status"] == "blocked"
    assert any(
        issue["code"] == "invalid_local_media_path"
        and issue["detail"] == field_name
        for issue in report["issues"]
    )
    assert preview_response.status_code == 400
    assert restore_response.status_code == 400
    with SessionLocal() as db:
        assert db.query(Item).count() == 0
        assert db.query(Creator).count() == 0
        assert db.query(Tag).filter(Tag.name == "Must Not Restore").count() == 0
