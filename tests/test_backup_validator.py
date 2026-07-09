from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Item
from app.services.backup_validator import validate_backup_payload


def _backup_payload() -> dict[str, object]:
    return {
        "schema": "nsfwtrack.backup.v1",
        "exported_at": "2026-07-09T00:00:00+08:00",
        "tables": {
            "items": [{"id": 1, "title": "Backup Item", "extra": '{"source":"local"}'}],
            "tags": [{"id": 2, "name": "tag-a"}],
            "creators": [{"id": 3, "name": "Creator A"}],
            "collections": [{"id": 4, "name": "Collection A"}],
            "item_tags": [{"item_id": 1, "tag_id": 2}],
            "item_creators": [{"item_id": 1, "creator_id": 3}],
            "item_collections": [{"item_id": 1, "collection_id": 4}],
            "user_item_states": [{"item_id": 1, "status": "watched", "rating": 5}],
            "saved_views": [
                {
                    "id": 5,
                    "name": "Good View",
                    "query_string": "state=wish&sort=title_asc",
                }
            ],
            "item_activity": [{"item_id": 1, "view_count": 1, "edit_count": 0}],
            "app_settings": [{"key": "default_language", "value": "zh"}],
        },
    }


def _issue_codes(report: dict[str, object]) -> set[str]:
    return {str(issue["code"]) for issue in report["issues"]}  # type: ignore[index]


def test_backup_validate_page_requires_login(client: TestClient) -> None:
    response = client.post(
        "/backup/preview",
        files={
            "file": (
                "backup.json",
                json.dumps(_backup_payload()).encode("utf-8"),
                "application/json",
            )
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_backup_validate_page_shows_report_and_does_not_write(
    auth_client: TestClient,
) -> None:
    response = auth_client.post(
        "/backup/preview",
        files={
            "file": (
                "backup.json",
                json.dumps(_backup_payload()).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert response.status_code == 200
    assert "备份校验 / 恢复 dry-run 报告" in response.text
    assert "dry-run 不会写入数据库" in response.text
    assert "可继续" in response.text
    assert auth_client.get("/api/items").json()["total"] == 0


def test_backup_validate_page_handles_invalid_and_empty_json_without_500(
    auth_client: TestClient,
) -> None:
    invalid_response = auth_client.post(
        "/backup/preview",
        files={"file": ("backup.json", b"{", "application/json")},
    )
    empty_response = auth_client.post(
        "/backup/preview",
        files={"file": ("backup.json", b"{}", "application/json")},
    )

    assert invalid_response.status_code == 200
    assert "JSON 格式错误" in invalid_response.text
    assert empty_response.status_code == 200
    assert "不建议继续" in empty_response.text
    assert "backup schema 不匹配" in empty_response.text
    assert "备份缺少 tables 字段" in empty_response.text


def test_backup_validator_accepts_old_backups_without_new_optional_tables() -> None:
    payload = _backup_payload()
    tables = payload["tables"]  # type: ignore[index]
    assert isinstance(tables, dict)
    tables.pop("saved_views")
    tables.pop("item_activity")
    tables.pop("app_settings")

    report = validate_backup_payload(payload).to_dict()

    assert report["error_count"] == 0
    assert "optional_table_missing" in _issue_codes(report)


def test_backup_validator_reports_unknown_fields_required_fields_and_values() -> None:
    payload = _backup_payload()
    payload["unexpected"] = True
    tables = payload["tables"]  # type: ignore[index]
    assert isinstance(tables, dict)
    tables["items"] = [
        {"id": 1, "title": "", "extra": "{bad", "mystery": "value"},
        {"id": 1, "title": "Duplicate ID"},
    ]
    tables["user_item_states"] = [
        {"item_id": 1, "status": "planned", "rating": 9},
    ]
    tables["app_settings"] = [
        {"key": "default_home", "value": "https://example.test"},
    ]

    report = validate_backup_payload(payload).to_dict()
    codes = _issue_codes(report)

    assert report["status"] == "blocked"
    assert "unknown_top_level_field" in codes
    assert "unknown_field" in codes
    assert "empty_title" in codes
    assert "invalid_extra_json" in codes
    assert "duplicate_id" in codes
    assert "invalid_status" in codes
    assert "invalid_rating" in codes
    assert "invalid_setting" in codes


def test_backup_validator_reports_orphans_duplicates_and_saved_view_activity() -> None:
    payload = _backup_payload()
    tables = payload["tables"]  # type: ignore[index]
    assert isinstance(tables, dict)
    tables["item_tags"] = [
        {"item_id": 1, "tag_id": 2},
        {"item_id": 1, "tag_id": 2},
        {"item_id": 404, "tag_id": 2},
        {"item_id": 1, "tag_id": 404},
    ]
    tables["saved_views"] = [
        {
            "id": 9,
            "name": "Bad View",
            "query_string": "https://example.test/?next=https://bad.test&unknown=1&bad=%ZZ",
        }
    ]
    tables["item_activity"] = [
        {"item_id": 404, "view_count": -1, "edit_count": "bad"},
        {"item_id": 1, "view_count": 1},
        {"item_id": 1, "view_count": 2},
    ]

    report = validate_backup_payload(payload).to_dict()
    codes = _issue_codes(report)

    assert report["status"] == "blocked"
    assert "duplicate_relation" in codes
    assert "orphan_item_tag_item" in codes
    assert "orphan_item_tag_target" in codes
    assert "saved_view_invalid_query" in codes
    assert "saved_view_external_url" in codes
    assert "saved_view_blocked_param" in codes
    assert "saved_view_unknown_param" in codes
    assert "item_activity_missing_item" in codes
    assert "duplicate_item_activity" in codes
    assert "negative_view_count" in codes
    assert "negative_edit_count" in codes


def test_backup_validator_is_read_only_and_does_not_delete_business_data(
    auth_client: TestClient,
) -> None:
    create_response = auth_client.post(
        "/api/items",
        json={"title": "Existing Item", "tags": ["keep"], "creators": []},
    )
    assert create_response.status_code == 201

    before_total = auth_client.get("/api/items").json()["total"]
    with SessionLocal() as db:
        report = validate_backup_payload(_backup_payload(), db).to_dict()
        db.rollback()

    after_total = auth_client.get("/api/items").json()["total"]
    with SessionLocal() as db:
        titles = [item.title for item in db.query(Item).all()]

    assert report["error_count"] == 0
    assert before_total == 1
    assert after_total == 1
    assert titles == ["Existing Item"]


def test_backup_preview_api_returns_validation_report(auth_client: TestClient) -> None:
    payload = _backup_payload()
    payload["extra_top_level"] = "warning"

    response = auth_client.post(
        "/api/backup/preview/json",
        files={
            "file": (
                "backup.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["preview"]["items"] == 1
    assert body["report"]["warning_count"] >= 1
    assert "unknown_top_level_field" in _issue_codes(body["report"])


def test_backup_validation_copy_has_chinese_and_english(
    auth_client: TestClient,
) -> None:
    zh_response = auth_client.post(
        "/backup/preview",
        files={
            "file": (
                "backup.json",
                json.dumps(_backup_payload()).encode("utf-8"),
                "application/json",
            )
        },
    )
    assert "备份校验" in zh_response.text
    assert "错误" in zh_response.text
    assert "警告" in zh_response.text
    assert "信息" in zh_response.text

    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/backup"},
    )
    assert en_response.status_code == 200
    preview_response = auth_client.post(
        "/backup/preview",
        files={
            "file": (
                "backup.json",
                json.dumps(_backup_payload()).encode("utf-8"),
                "application/json",
            )
        },
    )
    assert "Backup Validation" in preview_response.text
    assert "Errors" in preview_response.text
    assert "Warnings" in preview_response.text
    assert "Info" in preview_response.text
