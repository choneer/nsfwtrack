from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.services import data_health_fixes
from app.services.data_health_fixes import (
    DataHealthFixError,
    apply_data_health_fix,
)
from app.services.settings import save_app_settings


def _execute(sql: str, params: dict[str, Any] | None = None) -> None:
    with engine.connect() as conn:
        conn.execute(text(sql), params or {})
        conn.commit()


def _execute_with_pragmas(
    statements: Iterable[str],
    *,
    foreign_keys: bool = True,
    checks: bool = True,
) -> None:
    with engine.connect() as conn:
        conn.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if foreign_keys else 'OFF'}")
        conn.exec_driver_sql(
            f"PRAGMA ignore_check_constraints={'OFF' if checks else 'ON'}"
        )
        for statement in statements:
            conn.exec_driver_sql(statement)
        conn.commit()
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.exec_driver_sql("PRAGMA ignore_check_constraints=OFF")
        conn.commit()


def _scalar(sql: str) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar_one()


def _core_counts() -> dict[str, int]:
    return {
        table: int(_scalar(f"SELECT COUNT(*) FROM {table}"))
        for table in ("items", "tags", "creators", "collections")
    }


def _create_core_entities() -> None:
    _execute(
        """
        INSERT INTO items (id, title, created_at, updated_at)
        VALUES (1, 'Core Item', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )
    _execute("INSERT INTO tags (id, name, created_at) VALUES (1, 'Tag', CURRENT_TIMESTAMP)")
    _execute(
        """
        INSERT INTO creators (id, name, type, created_at)
        VALUES (1, 'Creator', 'artist', CURRENT_TIMESTAMP)
        """
    )
    _execute(
        """
        INSERT INTO collections (id, name, description, created_at, updated_at)
        VALUES (1, 'Collection', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )


def _save_policy(**values: str) -> None:
    with SessionLocal() as db:
        save_app_settings(db, values)


def test_data_health_fix_requires_login(client: TestClient) -> None:
    post_response = client.post(
        "/data-health/fix",
        data={"fix_type": "orphan_item_tags", "confirm": "1"},
        follow_redirects=False,
    )

    assert post_response.status_code == 303
    assert post_response.headers["location"] == "/login"


def test_data_health_fix_get_does_not_fix(auth_client: TestClient) -> None:
    get_response = auth_client.get("/data-health/fix", follow_redirects=False)

    assert get_response.status_code == 405


def test_data_health_fix_rejects_invalid_fix_type_and_fix_all(
    auth_client: TestClient,
) -> None:
    for fix_type in ("not_allowed", "fix_all"):
        response = auth_client.post(
            "/data-health/fix",
            data={"fix_type": fix_type, "confirm": "1"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert "修复类型无效" in response.text


def test_data_health_fix_requires_confirm(auth_client: TestClient) -> None:
    _execute("INSERT INTO tags (id, name, created_at) VALUES (1, 'Tag', CURRENT_TIMESTAMP)")
    _execute_with_pragmas(
        ("INSERT INTO item_tags (item_id, tag_id) VALUES (999, 1)",),
        foreign_keys=False,
    )

    response = auth_client.post(
        "/data-health/fix",
        data={"fix_type": "orphan_item_tags"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "缺少手动确认" in response.text
    assert _scalar("SELECT COUNT(*) FROM item_tags") == 1


def test_data_health_fix_route_cleans_orphan_item_tags_and_shows_summary(
    auth_client: TestClient,
) -> None:
    _create_core_entities()
    before_core_counts = _core_counts()
    _execute_with_pragmas(
        (
            "INSERT INTO item_tags (item_id, tag_id) VALUES (999, 1)",
            "INSERT INTO item_tags (item_id, tag_id) VALUES (1, 999)",
        ),
        foreign_keys=False,
    )

    page_response = auth_client.get("/data-health")
    fix_response = auth_client.post(
        "/data-health/fix",
        data={"fix_type": "orphan_item_tags", "confirm": "1"},
        follow_redirects=True,
    )

    assert page_response.status_code == 200
    assert "清理孤立 item_tags" in page_response.text
    assert "data-confirm-message" in page_response.text
    assert fix_response.status_code == 200
    assert "数据健康修复完成" in fix_response.text
    assert "删除 2 条" in fix_response.text
    assert _scalar("SELECT COUNT(*) FROM item_tags") == 0
    assert _core_counts() == before_core_counts


def test_data_health_fix_warning_and_backup_link_are_complete_in_both_languages(
    auth_client: TestClient,
) -> None:
    _execute("INSERT INTO tags (id, name, created_at) VALUES (1, 'Tag', CURRENT_TIMESTAMP)")
    _execute_with_pragmas(
        ("INSERT INTO item_tags (item_id, tag_id) VALUES (999, 1)",),
        foreign_keys=False,
    )
    _save_policy(backup_reminder_mode="dangerous_only")

    zh_response = auth_client.get("/data-health")
    assert "低风险手动修复" in zh_response.text
    assert "危险操作确认" in zh_response.text
    assert "所选数据健康问题记录" in zh_response.text
    assert "仅执行所选低风险修复，不删除条目、标签、创作者或合集" in zh_response.text
    assert "可能删除无效关系或辅助记录，不删除核心对象" in zh_response.text
    assert "不能自动撤销；可使用执行前 JSON 备份恢复" in zh_response.text
    assert "JSON 备份建议" in zh_response.text
    assert "执行前先导出本地 JSON 备份，并确认备份文件可用" in zh_response.text
    assert "这些操作不会删除条目 / 标签 / 创作者 / 合集" in zh_response.text
    assert "每次只允许手动修复一种问题" in zh_response.text
    assert 'href="/backup"' in zh_response.text

    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/data-health"},
    )
    assert "Low-Risk Manual Fixes" in en_response.text
    assert "Dangerous Operation Confirmation" in en_response.text
    assert "Selected data health issue records" in en_response.text
    assert "Runs only the selected low-risk fix" in en_response.text
    assert "May delete invalid relations or helper records, not core objects" in en_response.text
    assert "No automatic undo; restore from the pre-operation JSON backup" in en_response.text
    assert "JSON backup recommendation" in en_response.text
    assert "Export a local JSON backup first" in en_response.text
    assert (
        "These operations do not delete items, tags, creators, or collections"
        in en_response.text
    )
    assert "Only one issue type can be fixed manually at a time" in en_response.text
    assert 'href="/backup"' in en_response.text


def test_always_backup_reminder_does_not_weaken_strict_health_fix_confirmation(
    auth_client: TestClient,
) -> None:
    _execute("INSERT INTO tags (id, name, created_at) VALUES (1, 'Tag', CURRENT_TIMESTAMP)")
    _execute_with_pragmas(
        ("INSERT INTO item_tags (item_id, tag_id) VALUES (999, 1)",),
        foreign_keys=False,
    )
    _save_policy(
        backup_reminder_mode="always",
        danger_confirmation_mode="strict",
    )

    page = auth_client.get("/data-health")
    missing = auth_client.post(
        "/data-health/fix",
        data={"fix_type": "orphan_item_tags", "confirm": "1"},
        follow_redirects=False,
    )
    wrong = auth_client.post(
        "/data-health/fix",
        data={
            "fix_type": "orphan_item_tags",
            "confirm": "1",
            "confirmation_text": "confirm",
        },
        follow_redirects=False,
    )

    assert "JSON 备份建议" in page.text
    assert "data-strict-confirm-message" in page.text
    assert missing.status_code == 303
    assert wrong.status_code == 303
    assert _scalar("SELECT COUNT(*) FROM item_tags") == 1

    accepted = auth_client.post(
        "/data-health/fix",
        data={
            "fix_type": "orphan_item_tags",
            "confirm": "1",
            "confirmation_text": "CONFIRM",
        },
        follow_redirects=False,
    )
    assert accepted.status_code == 303
    assert _scalar("SELECT COUNT(*) FROM item_tags") == 0


def test_data_health_fixes_clean_orphan_relations_without_deleting_core_entities() -> None:
    _create_core_entities()
    before_core_counts = _core_counts()
    _execute_with_pragmas(
        (
            "INSERT INTO item_tags (item_id, tag_id) VALUES (999, 1)",
            "INSERT INTO item_tags (item_id, tag_id) VALUES (1, 999)",
            "INSERT INTO item_creators (item_id, creator_id) VALUES (999, 1)",
            "INSERT INTO item_creators (item_id, creator_id) VALUES (1, 999)",
            "INSERT INTO item_collections (item_id, collection_id) VALUES (999, 1)",
            "INSERT INTO item_collections (item_id, collection_id) VALUES (1, 999)",
        ),
        foreign_keys=False,
    )

    with SessionLocal() as db:
        tag_result = apply_data_health_fix(
            db,
            fix_type="orphan_item_tags",
            confirm=True,
        )
        creator_result = apply_data_health_fix(
            db,
            fix_type="orphan_item_creators",
            confirm=True,
        )
        collection_result = apply_data_health_fix(
            db,
            fix_type="orphan_item_collections",
            confirm=True,
        )

    assert tag_result.deleted_count == 2
    assert creator_result.deleted_count == 2
    assert collection_result.deleted_count == 2
    assert _scalar("SELECT COUNT(*) FROM item_tags") == 0
    assert _scalar("SELECT COUNT(*) FROM item_creators") == 0
    assert _scalar("SELECT COUNT(*) FROM item_collections") == 0
    assert _core_counts() == before_core_counts


def test_data_health_fixes_clean_duplicate_relations_from_old_schema() -> None:
    legacy_engine = create_engine("sqlite:///:memory:", future=True)
    with legacy_engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE tags (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE creators (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE collections (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE item_tags (item_id INTEGER, tag_id INTEGER)")
        conn.exec_driver_sql(
            "CREATE TABLE item_creators (item_id INTEGER, creator_id INTEGER)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE item_collections (item_id INTEGER, collection_id INTEGER)"
        )
        conn.exec_driver_sql("INSERT INTO items (id) VALUES (1)")
        conn.exec_driver_sql("INSERT INTO tags (id) VALUES (1)")
        conn.exec_driver_sql("INSERT INTO creators (id) VALUES (1)")
        conn.exec_driver_sql("INSERT INTO collections (id) VALUES (1)")
        conn.exec_driver_sql(
            "INSERT INTO item_tags (item_id, tag_id) VALUES (1, 1), (1, 1), (1, 1)"
        )
        conn.exec_driver_sql(
            """
            INSERT INTO item_creators (item_id, creator_id)
            VALUES (1, 1), (1, 1)
            """
        )
        conn.exec_driver_sql(
            """
            INSERT INTO item_collections (item_id, collection_id)
            VALUES (1, 1), (1, 1)
            """
        )

    with Session(legacy_engine) as db:
        tag_result = apply_data_health_fix(
            db,
            fix_type="duplicate_item_tags",
            confirm=True,
        )
        creator_result = apply_data_health_fix(
            db,
            fix_type="duplicate_item_creators",
            confirm=True,
        )
        collection_result = apply_data_health_fix(
            db,
            fix_type="duplicate_item_collections",
            confirm=True,
        )

    with legacy_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM item_tags")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM item_creators")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM item_collections")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM items")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM tags")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM creators")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM collections")).scalar_one() == 1
    assert tag_result.deleted_count == 2
    assert creator_result.deleted_count == 1
    assert collection_result.deleted_count == 1


def test_data_health_fixes_clean_orphan_activity_and_negative_counts() -> None:
    _create_core_entities()
    _execute_with_pragmas(
        (
            """
            INSERT INTO item_activity
                (
                    id,
                    item_id,
                    view_count,
                    edit_count,
                    created_at,
                    updated_at
                )
            VALUES
                (1, 999, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (2, 1, -3, -4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
        ),
        foreign_keys=False,
        checks=False,
    )

    with SessionLocal() as db:
        orphan_result = apply_data_health_fix(
            db,
            fix_type="orphan_item_activity",
            confirm=True,
        )
        negative_result = apply_data_health_fix(
            db,
            fix_type="negative_activity_counts",
            confirm=True,
        )

    assert orphan_result.deleted_count == 1
    assert negative_result.updated_count == 1
    assert _scalar("SELECT COUNT(*) FROM item_activity WHERE id = 1") == 0
    assert _scalar("SELECT view_count FROM item_activity WHERE id = 2") == 0
    assert _scalar("SELECT edit_count FROM item_activity WHERE id = 2") == 0
    assert _scalar("SELECT COUNT(*) FROM items") == 1


def test_data_health_fix_cleans_saved_view_blocked_unknown_and_external_params() -> None:
    _execute(
        """
        INSERT INTO saved_views (id, name, query_string, created_at, updated_at)
        VALUES (
            1,
            'Risky View',
            'https://example.invalid/items?state=wish&page=2&unknown=1&next=//evil.example&q=https://evil.example&sort=title_desc',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """
    )

    with SessionLocal() as db:
        result = apply_data_health_fix(
            db,
            fix_type="saved_view_blocked_params",
            confirm=True,
        )

    assert result.updated_count == 1
    assert _scalar("SELECT COUNT(*) FROM saved_views") == 1
    assert (
        _scalar("SELECT query_string FROM saved_views WHERE id = 1")
        == "state=wish&sort=title_desc"
    )


def test_data_health_fix_failure_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _create_core_entities()
    _execute("INSERT INTO item_tags (item_id, tag_id) VALUES (1, 1)")

    def _broken_handler(db: Session) -> data_health_fixes.DataHealthFixResult:
        db.execute(text("DELETE FROM item_tags"))
        raise RuntimeError("boom")

    monkeypatch.setitem(
        data_health_fixes._FIX_HANDLERS,
        "orphan_item_tags",
        _broken_handler,
    )

    with SessionLocal() as db:
        with pytest.raises(DataHealthFixError) as exc:
            apply_data_health_fix(
                db,
                fix_type="orphan_item_tags",
                confirm=True,
            )

    assert exc.value.code == "fix_failed"
    assert _scalar("SELECT COUNT(*) FROM item_tags") == 1
