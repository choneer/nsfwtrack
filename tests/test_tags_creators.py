from __future__ import annotations

from fastapi.testclient import TestClient


def test_tags_api(auth_client: TestClient) -> None:
    create_response = auth_client.post(
        "/api/tags",
        json={"name": "tag-one", "category": "genre"},
    )
    assert create_response.status_code == 201
    tag_id = create_response.json()["id"]

    list_response = auth_client.get("/api/tags")
    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "tag-one"

    update_response = auth_client.put(
        f"/api/tags/{tag_id}",
        json={"name": "tag-two", "category": "tone"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "tag-two"

    delete_response = auth_client.delete(f"/api/tags/{tag_id}")
    assert delete_response.status_code == 200
    assert auth_client.get("/api/tags").json() == []


def test_creators_api(auth_client: TestClient) -> None:
    create_response = auth_client.post(
        "/api/creators",
        json={"name": "Creator One", "type": "author"},
    )
    assert create_response.status_code == 201
    creator_id = create_response.json()["id"]

    list_response = auth_client.get("/api/creators")
    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "Creator One"

    detail_response = auth_client.get(f"/api/creators/{creator_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["items"] == []

    delete_response = auth_client.delete(f"/api/creators/{creator_id}")
    assert delete_response.status_code == 200
    assert auth_client.get(f"/api/creators/{creator_id}").status_code == 404
