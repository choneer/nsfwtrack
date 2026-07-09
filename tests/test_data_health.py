from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.database import engine
from app.services.data_health import build_data_health_report


def _execute(sql: str, params: dict[str, Any] | None = None) -> None:
    with engine.connect() as conn:
        conn.execute(text(sql), params or {})
        conn.commit()


def _execute_many(statements: Iterable[str]) -> None:
    with engine.connect() as conn:
        for statement in statements:
            conn.exec_driver_sql(statement)
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


def _table_snapshot() -> dict[str, list[tuple[Any, ...]]]:
    tables = (
        "items",
        "tags",
        "creators",
        "collections",
        "item_tags",
        "item_creators",
        "item_collections",
        "saved_views",
        "item_activity",
        "user_item_states",
    )
    with engine.connect() as conn:
        return {
            table: [tuple(row) for row in conn.execute(text(f"SELECT * FROM {table}"))]
            for table in tables
        }


def _create_valid_item(item_id: int = 1, title: str = "Healthy Item") -> None:
    _execute(
        """
        INSERT INTO items (id, title, created_at, updated_at)
        VALUES (:id, :title, '2026-07-09 00:00:00', '2026-07-09 00:00:00')
        """,
        {"id": item_id, "title": title},
    )


def test_data_health_page_requires_login(client: TestClient) -> None:
    response = client.get("/data-health", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_data_health_page_renders_healthy_state_and_navigation(
    auth_client: TestClient,
) -> None:
    response = auth_client.get("/data-health")
    dashboard_response = auth_client.get("/")

    assert response.status_code == 200
    assert "数据健康检查" in response.text
    assert "本页只读" in response.text
    assert "暂无数据问题" in response.text
    assert "问题总数" in response.text
    assert 'href="/data-health"' in response.text
    assert dashboard_response.status_code == 200
    assert 'href="/data-health"' in dashboard_response.text
    assert "数据健康检查" in dashboard_response.text


def test_data_health_page_renders_in_english(auth_client: TestClient) -> None:
    response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/data-health"},
    )

    assert response.status_code == 200
    assert "Data Health Check" in response.text
    assert "This page is read-only" in response.text
    assert "No Data Issues" in response.text
    assert "Total Issues" in response.text


def test_data_health_reports_item_basic_issues(auth_client: TestClient) -> None:
    _execute(
        """
        INSERT INTO items (id, title, created_at, updated_at, extra)
        VALUES (
            1,
            '',
            '2026-07-09 10:00:00',
            '2026-07-09 09:00:00',
            '{bad-json'
        )
        """
    )
    _execute_with_pragmas(
        (
            """
            INSERT INTO user_item_states
                (id, item_id, status, rating, created_at, updated_at)
            VALUES
                (1, 1, 'bad-status', 9, '2026-07-09 10:00:00', '2026-07-09 10:00:00')
            """,
        ),
        checks=False,
    )

    response = auth_client.get("/data-health")

    assert response.status_code == 200
    assert "空标题" in response.text
    assert "无效评分" in response.text
    assert "无效状态" in response.text
    assert "extra JSON 无效" in response.text
    assert "更新时间早于创建时间" in response.text


def test_data_health_reports_orphan_relations(auth_client: TestClient) -> None:
    _execute_with_pragmas(
        (
            """
            INSERT INTO item_tags (item_id, tag_id)
            VALUES (999, 1), (1, 999)
            """,
            """
            INSERT INTO item_creators (item_id, creator_id)
            VALUES (999, 1), (1, 999)
            """,
            """
            INSERT INTO item_collections (item_id, collection_id)
            VALUES (999, 1), (1, 999)
            """,
        ),
        foreign_keys=False,
    )

    response = auth_client.get("/data-health")

    assert response.status_code == 200
    assert "item_tags 指向不存在条目" in response.text
    assert "item_tags 指向不存在标签" in response.text
    assert "item_creators 指向不存在条目" in response.text
    assert "item_creators 指向不存在创作者" in response.text
    assert "item_collections 指向不存在条目" in response.text
    assert "item_collections 指向不存在合集" in response.text


def test_data_health_reports_duplicate_relations_from_old_schema() -> None:
    legacy_engine = create_engine("sqlite:///:memory:", future=True)
    with legacy_engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                updated_at TEXT,
                extra TEXT
            )
            """
        )
        conn.exec_driver_sql("CREATE TABLE tags (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE creators (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE collections (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql(
            "CREATE TABLE item_tags (item_id INTEGER, tag_id INTEGER)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE item_creators (item_id INTEGER, creator_id INTEGER)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE item_collections (item_id INTEGER, collection_id INTEGER)"
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE saved_views (
                id INTEGER PRIMARY KEY,
                name TEXT,
                query_string TEXT
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE item_activity (
                id INTEGER PRIMARY KEY,
                item_id INTEGER,
                last_viewed_at TEXT,
                view_count INTEGER,
                last_edited_at TEXT,
                edit_count INTEGER
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE user_item_states (
                id INTEGER PRIMARY KEY,
                item_id INTEGER,
                status TEXT,
                rating INTEGER
            )
            """
        )
        conn.exec_driver_sql(
            """
            INSERT INTO items (id, title, created_at, updated_at, extra)
            VALUES (1, 'Legacy Item', '2026-07-09 00:00:00', '2026-07-09 00:00:00', NULL)
            """
        )
        conn.exec_driver_sql("INSERT INTO tags (id) VALUES (1)")
        conn.exec_driver_sql("INSERT INTO creators (id) VALUES (1)")
        conn.exec_driver_sql("INSERT INTO collections (id) VALUES (1)")
        conn.exec_driver_sql(
            "INSERT INTO item_tags (item_id, tag_id) VALUES (1, 1), (1, 1)"
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
        report = build_data_health_report(db)

    issue_codes = {issue.code for issue in report.issues}
    assert "duplicate_item_tag" in issue_codes
    assert "duplicate_item_creator" in issue_codes
    assert "duplicate_item_collection" in issue_codes


def test_data_health_reports_saved_view_parameter_issues(
    auth_client: TestClient,
) -> None:
    _execute_with_pragmas(
        (
            """
            INSERT INTO saved_views (id, name, query_string)
            VALUES (1, '', '')
            """,
            """
            INSERT INTO saved_views (id, name, query_string)
            VALUES (
                2,
                'Unsafe Params',
                'state=wish&page=2&next=//example.invalid&redirect=https://example.invalid&unknown=1'
            )
            """,
            """
            INSERT INTO saved_views (id, name, query_string)
            VALUES (3, 'External URL', 'https://example.invalid/items?state=wish')
            """,
            """
            INSERT INTO saved_views (id, name, query_string)
            VALUES (4, 'Bad Percent', 'q=bad%ZZ')
            """,
        ),
        checks=False,
    )

    response = auth_client.get("/data-health")

    assert response.status_code == 200
    assert "saved view 名称为空" in response.text
    assert "saved view query_string 为空" in response.text
    assert "query_string 包含未知参数" in response.text
    assert "query_string 包含不应保存的参数" in response.text
    assert "query_string 包含外部 URL" in response.text
    assert "saved view query_string 异常" in response.text
    assert "page" in response.text
    assert "next" in response.text
    assert "redirect" in response.text


def test_data_health_reports_item_activity_issues(auth_client: TestClient) -> None:
    _execute_with_pragmas(
        (
            """
            INSERT INTO item_activity
                (
                    id,
                    item_id,
                    last_viewed_at,
                    view_count,
                    last_edited_at,
                    edit_count,
                    created_at,
                    updated_at
                )
            VALUES
                (
                    1,
                    999,
                    'not-a-date',
                    -1,
                    'also-not-a-date',
                    -2,
                    '2026-07-09 10:00:00',
                    '2026-07-09 10:00:00'
                )
            """,
        ),
        foreign_keys=False,
        checks=False,
    )

    response = auth_client.get("/data-health")

    assert response.status_code == 200
    assert "item_activity 指向不存在条目" in response.text
    assert "view_count 为负数" in response.text
    assert "edit_count 为负数" in response.text
    assert "last_viewed_at 异常" in response.text
    assert "last_edited_at 异常" in response.text


def test_data_health_get_does_not_modify_or_delete_business_data(
    auth_client: TestClient,
) -> None:
    _create_valid_item(1, "Read Only Item")
    _execute("INSERT INTO tags (id, name, created_at) VALUES (1, 'tag', CURRENT_TIMESTAMP)")
    _execute(
        """
        INSERT INTO creators (id, name, type, created_at)
        VALUES (1, 'creator', 'artist', CURRENT_TIMESTAMP)
        """
    )
    _execute(
        """
        INSERT INTO collections (id, name, description, created_at, updated_at)
        VALUES (1, 'collection', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )
    _execute("INSERT INTO item_tags (item_id, tag_id) VALUES (1, 1)")
    _execute("INSERT INTO item_creators (item_id, creator_id) VALUES (1, 1)")
    _execute(
        """
        INSERT INTO item_collections (item_id, collection_id, created_at)
        VALUES (1, 1, CURRENT_TIMESTAMP)
        """
    )
    _execute(
        """
        INSERT INTO saved_views (id, name, query_string, created_at, updated_at)
        VALUES (1, 'Readonly', 'state=wish', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )
    _execute(
        """
        INSERT INTO user_item_states
            (id, item_id, status, rating, created_at, updated_at)
        VALUES
            (1, 1, 'wish', 5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )
    _execute(
        """
        INSERT INTO item_activity
            (
                id,
                item_id,
                last_viewed_at,
                view_count,
                last_edited_at,
                edit_count,
                created_at,
                updated_at
            )
        VALUES
            (
                1,
                1,
                CURRENT_TIMESTAMP,
                1,
                CURRENT_TIMESTAMP,
                1,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
        """
    )
    before = _table_snapshot()

    response = auth_client.get("/data-health")
    after = _table_snapshot()

    assert response.status_code == 200
    assert after == before
