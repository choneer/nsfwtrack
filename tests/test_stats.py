from __future__ import annotations

from fastapi.testclient import TestClient


def test_stats_api(auth_client: TestClient) -> None:
    item = auth_client.post(
        "/api/items",
        json={"title": "Stats Item", "tags": ["stats"], "creators": ["Counter"]},
    ).json()
    auth_client.post(f"/api/items/{item['id']}/state", json={"status": "like"})

    summary_response = auth_client.get("/api/stats/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_items"] == 1
    assert summary["total_tags"] == 1
    assert summary["total_creators"] == 1
    assert summary["states"]["like"] == 1

    timeline_response = auth_client.get("/api/stats/timeline")
    assert timeline_response.status_code == 200
    assert timeline_response.json()[0]["count"] == 1
