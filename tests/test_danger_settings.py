from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import AppSetting, Collection, Creator, Item, Tag
from app.services.danger import DangerPolicy, get_danger_policy
from app.services.settings import AppSettingsError, get_app_settings, save_app_settings


def _save_policy(**values: str) -> None:
    with SessionLocal() as db:
        save_app_settings(db, values)


def _create_item(title: str) -> int:
    with SessionLocal() as db:
        item = Item(title=title)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item.id


def _object_exists(model: type[Item] | type[Tag] | type[Creator] | type[Collection], object_id: int) -> bool:
    with SessionLocal() as db:
        return db.get(model, object_id) is not None


def test_danger_settings_save_only_allowlisted_values(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/settings",
        data={
            "danger_confirmation_mode": "strict",
            "backup_reminder_mode": "always",
            "danger_result_detail": "summary",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        settings = get_app_settings(db)
    assert settings.danger_confirmation_mode == "strict"
    assert settings.backup_reminder_mode == "always"
    assert settings.danger_result_detail == "summary"
    assert 'value="off"' not in response.text
    assert 'value="disabled"' not in response.text
    assert 'value="never"' not in response.text


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("danger_confirmation_mode", "off"),
        ("danger_confirmation_mode", "disabled"),
        ("backup_reminder_mode", "never"),
        ("backup_reminder_mode", "off"),
        ("danger_result_detail", "full<script>"),
        ("unknown_danger_setting", "strict"),
    ],
)
def test_danger_settings_reject_unknown_or_disabling_values(
    auth_client: TestClient,
    key: str,
    value: str,
) -> None:
    response = auth_client.post(
        "/settings",
        data={key: value},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "设置" in response.text
    with SessionLocal() as db:
        assert db.query(AppSetting).count() == 0


def test_standard_mode_requires_server_confirmation(auth_client: TestClient) -> None:
    item_id = _create_item("Standard Delete")

    rejected = auth_client.post(
        f"/items/{item_id}/delete",
        follow_redirects=False,
    )
    assert rejected.status_code == 303
    assert _object_exists(Item, item_id)

    accepted = auth_client.post(
        f"/items/{item_id}/delete",
        data={"confirm": "1"},
        follow_redirects=False,
    )
    assert accepted.status_code == 303
    assert not _object_exists(Item, item_id)


def test_strict_mode_rejects_missing_and_wrong_text_then_accepts_confirm(
    auth_client: TestClient,
) -> None:
    _save_policy(danger_confirmation_mode="strict")
    item_id = _create_item("Strict Delete")

    missing = auth_client.post(
        f"/items/{item_id}/delete",
        data={"confirm": "1"},
        follow_redirects=True,
    )
    wrong = auth_client.post(
        f"/items/{item_id}/delete",
        data={"confirm": "1", "confirmation_text": "confirm"},
        follow_redirects=True,
    )
    padded = auth_client.post(
        f"/items/{item_id}/delete",
        data={"confirm": "1", "confirmation_text": " CONFIRM "},
        follow_redirects=True,
    )

    assert "CONFIRM" in missing.text
    assert "CONFIRM" in wrong.text
    assert "CONFIRM" in padded.text
    assert _object_exists(Item, item_id)

    accepted = auth_client.post(
        f"/items/{item_id}/delete",
        data={"confirm": "1", "confirmation_text": "CONFIRM"},
        follow_redirects=False,
    )

    assert accepted.status_code == 303
    assert not _object_exists(Item, item_id)


def test_strict_mode_guards_every_named_dangerous_page_flow(
    auth_client: TestClient,
) -> None:
    _save_policy(danger_confirmation_mode="strict")
    with SessionLocal() as db:
        item_delete = Item(title="Guard Item Delete")
        item_bulk = Item(title="Guard Item Bulk")
        item_primary = Item(title="Guard Merge Primary")
        item_duplicate = Item(title="Guard Merge Duplicate")
        activity_item = Item(title="Guard Activity")
        tag_delete = Tag(name="Guard Tag Delete")
        tag_primary = Tag(name="Guard Tag Primary")
        tag_duplicate = Tag(name=" guard tag primary ")
        creator_delete = Creator(name="Guard Creator", type="other")
        collection_delete = Collection(name="Guard Collection", description="")
        db.add_all(
            [
                item_delete,
                item_bulk,
                item_primary,
                item_duplicate,
                activity_item,
                tag_delete,
                tag_primary,
                tag_duplicate,
                creator_delete,
                collection_delete,
            ]
        )
        db.commit()
        ids = {
            "item_delete": item_delete.id,
            "item_bulk": item_bulk.id,
            "item_primary": item_primary.id,
            "item_duplicate": item_duplicate.id,
            "activity_item": activity_item.id,
            "tag_delete": tag_delete.id,
            "tag_primary": tag_primary.id,
            "tag_duplicate": tag_duplicate.id,
            "creator_delete": creator_delete.id,
            "collection_delete": collection_delete.id,
        }

    auth_client.get(f"/items/{ids['activity_item']}")
    backup_payload = auth_client.get("/api/backup/export/json").json()

    guarded_requests = [
        auth_client.post(
            f"/items/{ids['item_delete']}/delete",
            data={"confirm": "1"},
            follow_redirects=False,
        ),
        auth_client.post(
            "/items/bulk",
            data={
                "bulk_action": "delete",
                "item_ids": str(ids["item_bulk"]),
                "confirm": "1",
            },
            follow_redirects=False,
        ),
        auth_client.post(
            f"/tags/{ids['tag_delete']}/delete",
            data={"confirm": "1"},
            follow_redirects=False,
        ),
        auth_client.post(
            f"/creators/{ids['creator_delete']}/delete",
            data={"confirm": "1"},
            follow_redirects=False,
        ),
        auth_client.post(
            f"/collections/{ids['collection_delete']}/delete",
            data={"confirm": "1"},
            follow_redirects=False,
        ),
        auth_client.post(
            "/duplicates/merge",
            data={
                "primary_id": str(ids["item_primary"]),
                "duplicate_id": str(ids["item_duplicate"]),
                "confirm": "1",
            },
            follow_redirects=False,
        ),
        auth_client.post(
            "/cleanup/merge",
            data={
                "type": "tag",
                "primary_id": str(ids["tag_primary"]),
                "duplicate_id": str(ids["tag_duplicate"]),
                "confirm": "1",
            },
            follow_redirects=False,
        ),
        auth_client.post(
            "/activity/clear",
            data={"confirm": "1"},
            follow_redirects=False,
        ),
        auth_client.post(
            "/data-health/fix",
            data={"fix_type": "orphan_item_tags", "confirm": "1"},
            follow_redirects=False,
        ),
        auth_client.post(
            "/settings/reset",
            data={"confirm": "1"},
            follow_redirects=False,
        ),
    ]
    restore_page = auth_client.post(
        "/backup/restore",
        data={"confirm": "1"},
        files={
            "file": (
                "backup.json",
                json.dumps(backup_payload).encode("utf-8"),
                "application/json",
            )
        },
    )
    restore_api = auth_client.post(
        "/api/backup/restore/json",
        data={"confirm": "1"},
        files={
            "file": (
                "backup.json",
                json.dumps(backup_payload).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert all(response.status_code == 303 for response in guarded_requests)
    assert "CONFIRM" in restore_page.text
    assert restore_api.status_code == 400
    assert "CONFIRM" in restore_api.json()["detail"]
    assert _object_exists(Item, ids["item_delete"])
    assert _object_exists(Item, ids["item_bulk"])
    assert _object_exists(Item, ids["item_duplicate"])
    assert _object_exists(Tag, ids["tag_delete"])
    assert _object_exists(Tag, ids["tag_duplicate"])
    assert _object_exists(Creator, ids["creator_delete"])
    assert _object_exists(Collection, ids["collection_delete"])
    with SessionLocal() as db:
        assert db.query(AppSetting).count() == 1


@pytest.mark.parametrize(
    "path",
    [
        "/items/1/delete",
        "/items/bulk",
        "/tags/1/delete",
        "/creators/1/delete",
        "/collections/1/delete",
        "/duplicates/merge",
        "/cleanup/merge",
        "/activity/clear",
        "/backup/restore",
        "/data-health/fix",
        "/settings/reset",
        "/media-library/duplicates/organize/apply",
    ],
)
def test_get_cannot_execute_named_dangerous_operations(
    auth_client: TestClient,
    path: str,
) -> None:
    assert auth_client.get(path, follow_redirects=False).status_code == 405


def test_invalid_or_unreadable_confirmation_setting_falls_back_to_standard(
    auth_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SessionLocal() as db:
        db.add(AppSetting(key="danger_confirmation_mode", value="off"))
        db.commit()
        assert get_danger_policy(db).confirmation_mode == "standard"

    item_id = _create_item("Invalid Setting Fallback")
    response = auth_client.post(
        f"/items/{item_id}/delete",
        data={"confirm": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert not _object_exists(Item, item_id)

    def fail_to_read_settings(_db: object) -> object:
        raise RuntimeError("simulated settings read failure")

    monkeypatch.setattr("app.services.danger.get_app_settings", fail_to_read_settings)
    with SessionLocal() as db:
        assert get_danger_policy(db) == DangerPolicy()


def test_backup_reminder_mode_never_hides_the_safety_notice(
    auth_client: TestClient,
) -> None:
    _save_policy(backup_reminder_mode="dangerous_only")
    selective = auth_client.get("/activity")

    assert "危险操作确认" in selective.text
    assert "当前确认模式" in selective.text
    assert "JSON 备份建议" not in selective.text

    _save_policy(backup_reminder_mode="always")
    always = auth_client.get("/activity")

    assert "危险操作确认" in always.text
    assert "JSON 备份建议" in always.text
    assert DangerPolicy(backup_reminder_mode="always").show_backup_reminder(False)
    assert not DangerPolicy(
        backup_reminder_mode="dangerous_only"
    ).show_backup_reminder(False)


def test_result_detail_changes_display_without_changing_merge_behavior(
    auth_client: TestClient,
) -> None:
    with SessionLocal() as db:
        summary_primary = Tag(name="Summary Primary")
        summary_duplicate = Tag(name=" summary primary ")
        detailed_primary = Tag(name="Detailed Primary")
        detailed_duplicate = Tag(name=" detailed primary ")
        db.add_all(
            [
                summary_primary,
                summary_duplicate,
                detailed_primary,
                detailed_duplicate,
            ]
        )
        db.commit()
        ids = (
            summary_primary.id,
            summary_duplicate.id,
            detailed_primary.id,
            detailed_duplicate.id,
        )

    _save_policy(danger_result_detail="summary")
    summary_response = auth_client.post(
        "/cleanup/merge",
        data={
            "type": "tag",
            "primary_id": ids[0],
            "duplicate_id": ids[1],
            "confirm": "1",
        },
        follow_redirects=True,
    )

    _save_policy(danger_result_detail="detailed")
    detailed_response = auth_client.post(
        "/cleanup/merge",
        data={
            "type": "tag",
            "primary_id": ids[2],
            "duplicate_id": ids[3],
            "confirm": "1",
        },
        follow_redirects=True,
    )

    assert "合并摘要" not in summary_response.text
    assert "合并摘要" in detailed_response.text
    assert _object_exists(Tag, ids[0])
    assert not _object_exists(Tag, ids[1])
    assert _object_exists(Tag, ids[2])
    assert not _object_exists(Tag, ids[3])


def test_settings_service_rejects_disabling_values_without_partial_write() -> None:
    with SessionLocal() as db:
        with pytest.raises(AppSettingsError, match="invalid_value"):
            save_app_settings(
                db,
                {
                    "danger_result_detail": "summary",
                    "backup_reminder_mode": "never",
                },
            )
        assert db.query(AppSetting).count() == 0
