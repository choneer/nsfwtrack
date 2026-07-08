from __future__ import annotations

from fastapi.testclient import TestClient


def test_import_page_previews_before_confirming(auth_client: TestClient) -> None:
    csv_content = b"title,tags,creators,status\nPreview Item,tag-x,creator-x,watched\n"

    preview_response = auth_client.post(
        "/import/csv",
        files={"file": ("items.csv", csv_content, "text/csv")},
    )

    assert preview_response.status_code == 200
    assert "Preview" in preview_response.text
    assert auth_client.get("/api/items").json()["total"] == 0

    confirm_response = auth_client.post(
        "/import/confirm",
        data={
            "payload_json": (
                '[{"title":"Preview Item","tags":"tag-x",'
                '"creators":"creator-x","status":"watched"}]'
            )
        },
    )

    assert confirm_response.status_code == 200
    assert "Imported 1" in confirm_response.text
    assert auth_client.get("/api/items").json()["total"] == 1
