from __future__ import annotations

from fastapi.testclient import TestClient


def test_csv_import(auth_client: TestClient) -> None:
    csv_content = b"title,tags,creators,status,rating,review\nImported One,tag-a|tag-b,Alice,wish,3,Queued\n"

    response = auth_client.post(
        "/api/import/csv",
        files={"file": ("items.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 1

    items_response = auth_client.get("/api/items")
    assert items_response.json()["total"] == 1
    item = items_response.json()["items"][0]
    assert item["state"]["status"] == "wish"
    assert sorted(tag["name"] for tag in item["tags"]) == ["tag-a", "tag-b"]


def test_json_import(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/import/json",
        files={
            "file": (
                "items.json",
                b'[{"title":"Imported JSON","tags":["json"],"creators":["Casey"]}]',
                "application/json",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert auth_client.get("/api/search", params={"tag": "json"}).json()["total"] == 1
