from __future__ import annotations

from fastapi.testclient import TestClient


def test_import_page_previews_before_confirming(auth_client: TestClient) -> None:
    csv_content = b"title,tags,creators,status\nPreview Item,tag-x,creator-x,watched\n"

    preview_response = auth_client.post(
        "/import/csv",
        files={"file": ("items.csv", csv_content, "text/csv")},
    )

    assert preview_response.status_code == 200
    assert "确认导入" in preview_response.text
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
    assert "已导入 1 条" in confirm_response.text
    assert auth_client.get("/api/items").json()["total"] == 1


def test_language_switch_renders_chinese_and_english(client: TestClient) -> None:
    zh_response = client.get("/login")
    assert zh_response.status_code == 200
    assert '<html lang="zh">' in zh_response.text
    assert "登录" in zh_response.text
    assert "本地单用户媒体记录管理" in zh_response.text

    en_response = client.get("/set-language", params={"lang": "en", "next": "/login"})
    assert en_response.status_code == 200
    assert '<html lang="en">' in en_response.text
    assert "Login" in en_response.text
    assert "Local media records for one signed-in user." in en_response.text

    refresh_response = client.get("/login")
    assert refresh_response.status_code == 200
    assert '<html lang="en">' in refresh_response.text
