from __future__ import annotations

from fastapi.testclient import TestClient


def test_items_api_requires_login(client: TestClient) -> None:
    response = client.get("/api/items")

    assert response.status_code == 401


def test_item_crud(auth_client: TestClient) -> None:
    create_response = auth_client.post(
        "/api/items",
        json={
            "title": "First Item",
            "summary": "Local record",
            "tags": ["alpha", "beta"],
            "creators": ["creator one"],
            "extra": {"source": "manual"},
        },
    )
    assert create_response.status_code == 201
    item = create_response.json()
    assert item["title"] == "First Item"
    assert [tag["name"] for tag in item["tags"]] == ["alpha", "beta"]

    item_id = item["id"]
    list_response = auth_client.get("/api/items")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    update_response = auth_client.put(
        f"/api/items/{item_id}",
        json={"title": "Updated Item", "tags": ["beta"]},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Updated Item"
    assert [tag["name"] for tag in update_response.json()["tags"]] == ["beta"]

    delete_response = auth_client.delete(f"/api/items/{item_id}")
    assert delete_response.status_code == 200
    assert auth_client.get(f"/api/items/{item_id}").status_code == 404
