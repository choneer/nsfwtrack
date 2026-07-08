from __future__ import annotations

from fastapi.testclient import TestClient


def _create_item(client: TestClient) -> int:
    response = client.post("/api/items", json={"title": "State Item"})
    assert response.status_code == 201
    return int(response.json()["id"])


def test_state_lifecycle(auth_client: TestClient) -> None:
    item_id = _create_item(auth_client)

    create_response = auth_client.post(
        f"/api/items/{item_id}/state",
        json={"status": "watched", "rating": 4, "review": "Solid."},
    )
    assert create_response.status_code == 201
    assert create_response.json()["status"] == "watched"

    get_response = auth_client.get(f"/api/items/{item_id}/state")
    assert get_response.status_code == 200
    assert get_response.json()["rating"] == 4

    update_response = auth_client.post(
        f"/api/items/{item_id}/state",
        json={"status": "like", "rating": 5},
    )
    assert update_response.status_code == 201
    assert update_response.json()["status"] == "like"

    delete_response = auth_client.delete(f"/api/items/{item_id}/state")
    assert delete_response.status_code == 200
    assert auth_client.get(f"/api/items/{item_id}/state").status_code == 404
