from __future__ import annotations

import json

from fastapi.testclient import TestClient


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


def test_backup_exports_require_login(client: TestClient) -> None:
    assert client.get("/api/backup/export/json").status_code == 401
    assert client.get("/api/backup/export/csv").status_code == 401


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
        "item_tags",
        "item_creators",
        "user_item_states",
    }
    assert payload["tables"]["items"][0]["title"] == "Backup Item"
    assert payload["tables"]["user_item_states"][0]["status"] == "watched"


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
    assert "watched" in response.text


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

    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/backup"},
    )
    assert en_response.status_code == 200
    assert "Backup and Restore" in en_response.text
    assert "Export JSON Backup" in en_response.text
