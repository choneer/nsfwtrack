from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.models import Collection, ItemCollection, SavedView


def _create_backup_item(client: TestClient) -> int:
    response = client.post(
        "/api/items",
        json={
            "title": "Backup Item",
            "summary": "Local only",
            "tags": ["backup-tag"],
            "creators": ["Backup Creator"],
        },
    )
    assert response.status_code == 201
    item_id = int(response.json()["id"])
    state_response = client.post(
        f"/api/items/{item_id}/state",
        json={"status": "watched", "rating": 5, "review": "Restorable"},
    )
    assert state_response.status_code == 201
    return item_id


def _create_backup_collection(
    client: TestClient,
    item_id: int,
    name: str = "Backup Collection",
) -> int:
    response = client.post(
        "/collections",
        data={"name": name, "description": "Local collection"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    collection_id = int(response.headers["location"].rstrip("/").split("/")[-1])
    add_response = client.post(
        f"/collections/{collection_id}/items",
        data={"item_id": str(item_id)},
        follow_redirects=True,
    )
    assert add_response.status_code == 200
    return collection_id


def _collection_count() -> int:
    with SessionLocal() as db:
        return db.query(Collection).count()


def _item_collection_count() -> int:
    with SessionLocal() as db:
        return db.query(ItemCollection).count()


def _saved_view_count() -> int:
    with SessionLocal() as db:
        return db.query(SavedView).count()


def _saved_view_query(name: str) -> str | None:
    with SessionLocal() as db:
        saved_view = db.query(SavedView).filter(SavedView.name == name).one_or_none()
        return saved_view.query_string if saved_view is not None else None


def test_backup_exports_require_login(client: TestClient) -> None:
    assert client.get("/api/backup/export/json").status_code == 401
    assert client.get("/api/backup/export/csv").status_code == 401


def test_backup_preview_requires_login(client: TestClient) -> None:
    response = client.post(
        "/api/backup/preview/json",
        files={"file": ("backup.json", b"{}", "application/json")},
    )

    assert response.status_code == 401


def test_json_export_contains_core_tables(auth_client: TestClient) -> None:
    _create_backup_item(auth_client)

    response = auth_client.get("/api/backup/export/json")

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="nsfwtrack-backup-'
    )
    payload = response.json()
    assert payload["schema"] == "nsfwtrack.backup.v1"
    assert set(payload["tables"]) == {
        "items",
        "tags",
        "creators",
        "collections",
        "item_tags",
        "item_creators",
        "item_collections",
        "user_item_states",
        "saved_views",
    }
    assert payload["tables"]["items"][0]["title"] == "Backup Item"
    assert payload["tables"]["user_item_states"][0]["status"] == "watched"
    assert payload["tables"]["saved_views"] == []


def test_json_backup_exports_and_previews_collection_tables(
    auth_client: TestClient,
) -> None:
    item_id = _create_backup_item(auth_client)
    collection_id = _create_backup_collection(auth_client, item_id)

    payload = auth_client.get("/api/backup/export/json").json()

    assert payload["tables"]["collections"][0]["name"] == "Backup Collection"
    assert payload["tables"]["collections"][0]["description"] == "Local collection"
    assert payload["tables"]["item_collections"] == [
        {"item_id": item_id, "collection_id": collection_id}
    ]

    preview_response = auth_client.post(
        "/api/backup/preview/json",
        files={
            "file": (
                "backup.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert preview_response.status_code == 200
    preview = preview_response.json()["preview"]
    assert preview["collections"] == 1
    assert preview["item_collections"] == 1
    assert preview["collections_to_create"] == 0
    assert preview["collections_to_merge"] == 1
    assert preview["item_collections_restorable"] == 1
    assert preview["item_collections_unrestorable"] == 0


def test_csv_export_contains_readable_item_data(auth_client: TestClient) -> None:
    _create_backup_item(auth_client)

    response = auth_client.get("/api/backup/export/csv")

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="nsfwtrack-items-'
    )
    assert "Backup Item" in response.text
    assert "backup-tag" in response.text
    assert "Backup Creator" in response.text
    assert "collections" in response.text.splitlines()[0]
    assert "watched" in response.text


def test_csv_export_contains_semicolon_separated_collections(
    auth_client: TestClient,
) -> None:
    item_id = _create_backup_item(auth_client)
    _create_backup_collection(auth_client, item_id, "Watch Later")
    _create_backup_collection(auth_client, item_id, "Favorites")

    response = auth_client.get("/api/backup/export/csv")

    assert response.status_code == 200
    assert "collections" in response.text.splitlines()[0]
    assert "Favorites;Watch Later" in response.text


def test_json_backup_preview_succeeds_without_modifying_database(
    auth_client: TestClient,
) -> None:
    _create_backup_item(auth_client)
    backup_payload = auth_client.get("/api/backup/export/json").json()
    assert auth_client.delete(
        f"/api/items/{backup_payload['tables']['items'][0]['id']}"
    ).status_code == 200
    assert auth_client.get("/api/items").json()["total"] == 0

    response = auth_client.post(
        "/api/backup/preview/json",
        files={
            "file": (
                "backup.json",
                json.dumps(backup_payload).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert preview["schema"] == "nsfwtrack.backup.v1"
    assert preview["items"] == 1
    assert preview["tags"] == 1
    assert preview["creators"] == 1
    assert preview["item_tags"] == 1
    assert preview["item_creators"] == 1
    assert preview["user_item_states"] == 1
    assert preview["collections"] == 0
    assert preview["item_collections"] == 0
    assert preview["saved_views"] == 0
    assert auth_client.get("/api/items").json()["total"] == 0


def test_old_json_backup_without_optional_tables_still_previews_and_restores(
    auth_client: TestClient,
) -> None:
    _create_backup_item(auth_client)
    backup_payload = auth_client.get("/api/backup/export/json").json()
    backup_payload["tables"].pop("collections")
    backup_payload["tables"].pop("item_collections")
    backup_payload["tables"].pop("saved_views")
    item_id = backup_payload["tables"]["items"][0]["id"]
    assert auth_client.delete(f"/api/items/{item_id}").status_code == 200

    preview_response = auth_client.post(
        "/api/backup/preview/json",
        files={
            "file": (
                "backup.json",
                json.dumps(backup_payload).encode("utf-8"),
                "application/json",
            )
        },
    )
    restore_response = auth_client.post(
        "/api/backup/restore/json",
        files={
            "file": (
                "backup.json",
                json.dumps(backup_payload).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert preview_response.status_code == 200
    assert preview_response.json()["preview"]["collections"] == 0
    assert preview_response.json()["preview"]["saved_views"] == 0
    assert restore_response.status_code == 200
    assert auth_client.get("/api/items").json()["total"] == 1


def test_json_backup_exports_previews_and_restores_saved_views(
    auth_client: TestClient,
) -> None:
    create_response = auth_client.post(
        "/saved-views",
        data={
            "name": "Backup View",
            "query_string": "state=wish&page=9&sort=title_asc&unknown=1",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 303

    payload = auth_client.get("/api/backup/export/json").json()

    assert payload["tables"]["saved_views"][0]["name"] == "Backup View"
    assert payload["tables"]["saved_views"][0]["query_string"] == (
        "state=wish&sort=title_asc"
    )

    preview_response = auth_client.post(
        "/api/backup/preview/json",
        files={
            "file": (
                "backup.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["preview"]
    assert preview["saved_views"] == 1
    assert preview["saved_views_to_create"] == 0
    assert preview["saved_views_to_update"] == 1
    assert preview["saved_view_errors"] == 0

    saved_view_id = payload["tables"]["saved_views"][0]["id"]
    delete_response = auth_client.post(
        f"/saved-views/{saved_view_id}/delete",
        follow_redirects=False,
    )
    assert delete_response.status_code == 303
    assert _saved_view_count() == 0

    restore_response = auth_client.post(
        "/api/backup/restore/json",
        files={
            "file": (
                "backup.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert restore_response.status_code == 200
    result = restore_response.json()["result"]
    assert result["saved_views_created"] == 1
    assert result["saved_views_updated"] == 0
    assert _saved_view_query("Backup View") == "state=wish&sort=title_asc"


def test_backup_preview_rejects_missing_invalid_and_wrong_schema_files(
    auth_client: TestClient,
) -> None:
    missing_response = auth_client.post("/api/backup/preview/json")
    assert missing_response.status_code == 400
    assert "JSON" in missing_response.json()["detail"]

    txt_response = auth_client.post(
        "/api/backup/preview/json",
        files={"file": ("backup.txt", b"{}", "text/plain")},
    )
    assert txt_response.status_code == 400
    assert "JSON" in txt_response.json()["detail"]

    invalid_response = auth_client.post(
        "/api/backup/preview/json",
        files={"file": ("backup.json", b"{", "application/json")},
    )
    assert invalid_response.status_code == 400
    assert "JSON" in invalid_response.json()["detail"]

    schema_response = auth_client.post(
        "/api/backup/preview/json",
        files={
            "file": (
                "backup.json",
                b'{"schema":"wrong","tables":{}}',
                "application/json",
            )
        },
    )
    assert schema_response.status_code == 400
    assert "schema" in schema_response.json()["detail"]

    missing_field_response = auth_client.post(
        "/api/backup/preview/json",
        files={
            "file": (
                "backup.json",
                json.dumps(
                    {
                        "schema": "nsfwtrack.backup.v1",
                        "tables": {
                            "items": [{"id": 1}],
                            "tags": [],
                            "creators": [],
                            "item_tags": [],
                            "item_creators": [],
                            "user_item_states": [],
                        },
                    }
                ).encode("utf-8"),
                "application/json",
            )
        },
    )
    assert missing_field_response.status_code == 400
    assert "字段" in missing_field_response.json()["detail"]


def test_backup_preview_rejects_oversized_file(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_BACKUP_UPLOAD_MB", "1")
    get_settings.cache_clear()
    try:
        response = auth_client.post(
            "/api/backup/preview/json",
            files={
                "file": (
                    "backup.json",
                    b"{" + (b" " * (1024 * 1024 + 1)) + b"}",
                    "application/json",
                )
            },
        )
    finally:
        monkeypatch.delenv("MAX_BACKUP_UPLOAD_MB", raising=False)
        get_settings.cache_clear()

    assert response.status_code == 413
    assert "大小限制" in response.json()["detail"]


def test_backup_restore_rejects_oversized_file_before_modifying_database(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_backup_item(auth_client)
    monkeypatch.setenv("MAX_BACKUP_UPLOAD_MB", "1")
    get_settings.cache_clear()
    try:
        response = auth_client.post(
            "/api/backup/restore/json",
            files={
                "file": (
                    "backup.json",
                    b"{" + (b" " * (1024 * 1024 + 1)) + b"}",
                    "application/json",
                )
            },
        )
    finally:
        monkeypatch.delenv("MAX_BACKUP_UPLOAD_MB", raising=False)
        get_settings.cache_clear()

    assert response.status_code == 413
    assert auth_client.get("/api/items").json()["total"] == 1


def test_json_backup_restore_merges_data(auth_client: TestClient) -> None:
    _create_backup_item(auth_client)
    backup_payload = auth_client.get("/api/backup/export/json").json()
    item_id = backup_payload["tables"]["items"][0]["id"]
    assert auth_client.delete(f"/api/items/{item_id}").status_code == 200
    assert auth_client.get("/api/items").json()["total"] == 0

    restore_response = auth_client.post(
        "/api/backup/restore/json",
        files={
            "file": (
                "backup.json",
                json.dumps(backup_payload).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert restore_response.status_code == 200
    assert restore_response.json()["ok"] is True
    items_response = auth_client.get("/api/items")
    assert items_response.json()["total"] == 1
    restored_item = items_response.json()["items"][0]
    assert restored_item["title"] == "Backup Item"
    assert restored_item["state"]["status"] == "watched"


def test_json_backup_restore_collections_deduplicates_and_skips_bad_links(
    auth_client: TestClient,
) -> None:
    existing_id = _create_backup_item(auth_client)
    payload = {
        "schema": "nsfwtrack.backup.v1",
        "exported_at": "2026-07-09T00:00:00+00:00",
        "tables": {
            "items": [{"id": 99, "title": "Restored Collection Item"}],
            "tags": [],
            "creators": [],
            "collections": [
                {"id": 1, "name": "Restored Collection", "description": "One"},
                {"id": 2, "name": "Restored Collection", "description": "Duplicate"},
                {"id": 3, "name": "   ", "description": "Bad"},
            ],
            "item_tags": [],
            "item_creators": [],
            "item_collections": [
                {"item_id": 99, "collection_id": 1},
                {"item_id": 99, "collection_id": 1},
                {"item_id": 404, "collection_id": 1},
                {"item_id": 99, "collection_id": 404},
                {"item_id": "bad", "collection_id": 1},
            ],
            "user_item_states": [],
        },
    }

    response = auth_client.post(
        "/api/backup/restore/json",
        files={
            "file": (
                "backup.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["collections_created"] == 1
    assert result["collections_skipped"] == 2
    assert result["item_collections_created"] == 1
    assert result["item_collections_skipped"] == 4
    assert result["collection_errors"] == 4
    assert _collection_count() == 1
    assert _item_collection_count() == 1
    item_titles = [item["title"] for item in auth_client.get("/api/items").json()["items"]]
    assert "Restored Collection Item" in item_titles
    assert auth_client.get(f"/api/items/{existing_id}").status_code == 200

    repeat_response = auth_client.post(
        "/api/backup/restore/json",
        files={
            "file": (
                "backup.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        },
    )
    assert repeat_response.status_code == 200
    assert _collection_count() == 1
    assert _item_collection_count() == 1


def test_invalid_json_backup_does_not_modify_database(auth_client: TestClient) -> None:
    _create_backup_item(auth_client)

    response = auth_client.post(
        "/api/backup/restore/json",
        files={"file": ("backup.json", b'{"schema":"wrong"}', "application/json")},
    )

    assert response.status_code == 400
    items_response = auth_client.get("/api/items")
    assert items_response.json()["total"] == 1
    assert items_response.json()["items"][0]["title"] == "Backup Item"


def test_restore_failure_rolls_back_partial_changes(auth_client: TestClient) -> None:
    _create_backup_item(auth_client)
    broken_payload = {
        "schema": "nsfwtrack.backup.v1",
        "exported_at": "2026-07-08T00:00:00+00:00",
        "tables": {
            "items": [
                {
                    "id": 99,
                    "title": "Broken Item",
                    "created_at": "not-a-date",
                }
            ],
            "tags": [{"id": 88, "name": "partial-tag"}],
            "creators": [],
            "item_tags": [],
            "item_creators": [],
            "user_item_states": [],
        },
    }

    response = auth_client.post(
        "/api/backup/restore/json",
        files={
            "file": (
                "backup.json",
                json.dumps(broken_payload).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert response.status_code == 400
    tag_names = [tag["name"] for tag in auth_client.get("/api/tags").json()]
    assert "backup-tag" in tag_names
    assert "partial-tag" not in tag_names


def test_backup_page_renders_chinese_and_english(auth_client: TestClient) -> None:
    zh_response = auth_client.get("/backup")
    assert zh_response.status_code == 200
    assert "备份与恢复" in zh_response.text
    assert "导出 JSON 备份" in zh_response.text
    assert "合并恢复" in zh_response.text
    assert "合集" in zh_response.text
    assert "collections 字段" in zh_response.text
    assert "不支持 URL 导入" in zh_response.text
    assert "预览备份" in zh_response.text

    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/backup"},
    )
    assert en_response.status_code == 200
    assert "Backup and Restore" in en_response.text
    assert "Export JSON Backup" in en_response.text
    assert "merge strategy" in en_response.text
    assert "collections field" in en_response.text
    assert "URL import" in en_response.text
    assert "Preview Backup" in en_response.text


def test_backup_page_preview_failure_shows_clear_error(
    auth_client: TestClient,
) -> None:
    response = auth_client.post(
        "/backup/preview",
        files={"file": ("backup.json", b"{", "application/json")},
    )

    assert response.status_code == 200
    assert "预览失败" in response.text
    assert "JSON 格式错误" in response.text
