from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Item


def _create_stats_item(
    client: TestClient,
    title: str,
    *,
    summary: str | None = None,
    tags: list[str] | None = None,
    creators: list[str] | None = None,
    status: str | None = None,
    rating: int | None = None,
    created_days_ago: int = 0,
    updated_days_ago: int = 0,
) -> int:
    payload: dict[str, Any] = {
        "title": title,
        "tags": tags or [],
        "creators": creators or [],
    }
    if summary is not None:
        payload["summary"] = summary
    response = client.post("/api/items", json=payload)
    assert response.status_code == 201
    item_id = int(response.json()["id"])
    if status:
        state_payload: dict[str, Any] = {"status": status}
        if rating is not None:
            state_payload["rating"] = rating
        state_response = client.post(f"/api/items/{item_id}/state", json=state_payload)
        assert state_response.status_code == 201
    _set_item_times(
        item_id,
        created_days_ago=created_days_ago,
        updated_days_ago=updated_days_ago,
    )
    return item_id


def _set_item_times(
    item_id: int,
    *,
    created_days_ago: int,
    updated_days_ago: int,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        item = db.get(Item, item_id)
        assert item is not None
        item.created_at = now - timedelta(days=created_days_ago)
        item.updated_at = now - timedelta(days=updated_days_ago)
        db.commit()


def _seed_stats_dataset(client: TestClient) -> None:
    _create_stats_item(
        client,
        "Recent Rated Item",
        summary="Local stats summary",
        tags=["rank-top", "shared"],
        creators=["Creator Top", "Shared Creator"],
        status="like",
        rating=5,
        created_days_ago=1,
        updated_days_ago=1,
    )
    _create_stats_item(
        client,
        "Older Rated Item",
        tags=["rank-top"],
        creators=["Creator Top"],
        status="watched",
        rating=3,
        created_days_ago=10,
        updated_days_ago=3,
    )
    _create_stats_item(
        client,
        "Sparse Item",
        created_days_ago=40,
        updated_days_ago=40,
    )


def _row_by_key(rows: list[dict[str, Any]], key: str, value: object) -> dict[str, Any]:
    for row in rows:
        if row[key] == value:
            return row
    raise AssertionError(f"missing row where {key}={value!r}")


def test_stats_page_requires_login(client: TestClient) -> None:
    response = client.get("/stats", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_stats_page_renders_empty_database_without_division_by_zero(
    auth_client: TestClient,
) -> None:
    response = auth_client.get("/stats")

    assert response.status_code == 200
    assert "统计总览" in response.text
    assert "没有状态数据。" in response.text
    assert "没有评分数据。" in response.text
    assert "没有标签数据。" in response.text
    assert "没有创作者数据。" in response.text
    assert "没有近期活动。" in response.text
    assert "暂无" in response.text

    summary = auth_client.get("/api/stats/summary").json()
    assert summary["total_items"] == 0
    assert summary["rated_items"] == 0
    assert summary["average_rating"] is None
    assert all(row["percent"] == 0 for row in summary["status_distribution"]["rows"])
    assert all(row["percent"] == 0 for row in summary["rating_distribution"]["rows"])


def test_stats_summary_counts_distributions_rankings_activity_and_integrity(
    auth_client: TestClient,
) -> None:
    _seed_stats_dataset(auth_client)

    response = auth_client.get("/api/stats/summary")

    assert response.status_code == 200
    summary = response.json()
    assert summary["total_items"] == 3
    assert summary["total_tags"] == 2
    assert summary["total_creators"] == 2
    assert summary["state_items"] == 2
    assert summary["rated_items"] == 2
    assert summary["average_rating"] == 4.0
    assert summary["created_7d"] == 1
    assert summary["created_30d"] == 2

    assert summary["states"]["like"] == 1
    assert summary["states"]["watched"] == 1
    assert summary["states"]["wish"] == 0
    like_row = _row_by_key(summary["status_distribution"]["rows"], "status", "like")
    assert like_row["count"] == 1
    assert like_row["percent"] == 50.0

    rating_distribution = summary["rating_distribution"]
    assert rating_distribution["average_rating"] == 4.0
    assert rating_distribution["highest_rating"] == 5
    assert rating_distribution["lowest_rating"] == 3
    assert _row_by_key(rating_distribution["rows"], "rating", 3)["count"] == 1
    assert _row_by_key(rating_distribution["rows"], "rating", 5)["count"] == 1

    tag_rows = summary["tag_ranking"]["rows"]
    assert tag_rows[0]["name"] == "rank-top"
    assert tag_rows[0]["count"] == 2
    assert tag_rows[1]["name"] == "shared"
    assert tag_rows[1]["count"] == 1

    creator_rows = summary["creator_ranking"]["rows"]
    assert creator_rows[0]["name"] == "Creator Top"
    assert creator_rows[0]["count"] == 2
    assert creator_rows[1]["name"] == "Shared Creator"
    assert creator_rows[1]["count"] == 1

    activity = summary["activity"]
    assert activity["created_7d"] == 1
    assert activity["created_30d"] == 2
    assert activity["updated_7d"] == 2
    assert activity["updated_30d"] == 2
    assert activity["has_recent"] is True

    integrity = {row["key"]: row["count"] for row in summary["integrity"]}
    assert integrity == {
        "missing_tags": 1,
        "missing_creators": 1,
        "missing_state": 1,
        "missing_rating": 1,
        "missing_summary": 2,
    }


def test_stats_timeline_keeps_created_date_count_api(auth_client: TestClient) -> None:
    _seed_stats_dataset(auth_client)

    response = auth_client.get("/api/stats/timeline")

    assert response.status_code == 200
    timeline = response.json()
    assert len(timeline) == 3
    assert all(row["count"] == 1 for row in timeline)
    assert all("date" in row for row in timeline)


def test_stats_page_renders_chinese_and_english_panels(
    auth_client: TestClient,
) -> None:
    _seed_stats_dataset(auth_client)

    zh_response = auth_client.get("/stats")
    assert zh_response.status_code == 200
    assert "统计总览" in zh_response.text
    assert "状态分布" in zh_response.text
    assert "评分分布" in zh_response.text
    assert "标签使用排行" in zh_response.text
    assert "创作者关联排行" in zh_response.text
    assert "最近活动" in zh_response.text
    assert "数据完整性" in zh_response.text
    assert "rank-top" in zh_response.text
    assert "Creator Top" in zh_response.text

    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/stats"},
    )
    assert en_response.status_code == 200
    assert "Stats Overview" in en_response.text
    assert "Status Distribution" in en_response.text
    assert "Rating Distribution" in en_response.text
    assert "Tag Usage Ranking" in en_response.text
    assert "Creator Link Ranking" in en_response.text
    assert "Recent Activity" in en_response.text
    assert "Data Completeness" in en_response.text
