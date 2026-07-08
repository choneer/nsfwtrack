from __future__ import annotations

from fastapi.testclient import TestClient


def test_search_by_title_tag_and_status(auth_client: TestClient) -> None:
    first = auth_client.post(
        "/api/items",
        json={"title": "Blue Archive", "tags": ["game"], "creators": ["Alice"]},
    ).json()
    second = auth_client.post(
        "/api/items",
        json={"title": "Quiet Sketch", "tags": ["art"], "creators": ["Bob"]},
    ).json()
    auth_client.post(
        f"/api/items/{first['id']}/state",
        json={"status": "wish"},
    )
    auth_client.post(
        f"/api/items/{second['id']}/state",
        json={"status": "watched"},
    )

    title_response = auth_client.get("/api/search", params={"q": "Blue"})
    assert title_response.status_code == 200
    assert title_response.json()["total"] == 1
    assert title_response.json()["items"][0]["title"] == "Blue Archive"

    tag_response = auth_client.get("/api/search", params={"tag": "art"})
    assert tag_response.json()["total"] == 1
    assert tag_response.json()["items"][0]["title"] == "Quiet Sketch"

    status_response = auth_client.get("/api/search", params={"status": "wish"})
    assert status_response.json()["total"] == 1
    assert status_response.json()["items"][0]["title"] == "Blue Archive"
