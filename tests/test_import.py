from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _csv_confirm_data(
    rows: list[dict[str, str]],
    source_headers: list[str],
    target_fields: list[str],
) -> dict[str, object]:
    return {
        "source_type": "csv",
        "payload_json": json.dumps(rows),
        "source_header": source_headers,
        "target_field": target_fields,
    }


def test_import_templates_require_login(client: TestClient) -> None:
    assert client.get("/api/import/template/csv").status_code == 401
    assert client.get("/api/import/template/json").status_code == 401


def test_csv_template_download_contains_required_headers(auth_client: TestClient) -> None:
    response = auth_client.get("/api/import/template/csv")

    assert response.status_code == 200
    assert 'filename="nsfwtrack-import-template.csv"' in response.headers[
        "content-disposition"
    ]
    assert "title,summary,status,rating,note,tags,creators,extra" in response.text
    assert "Example item" in response.text


def test_json_template_download_contains_items_example(auth_client: TestClient) -> None:
    response = auth_client.get("/api/import/template/json")

    assert response.status_code == 200
    assert 'filename="nsfwtrack-import-template.json"' in response.headers[
        "content-disposition"
    ]
    payload = response.json()
    assert isinstance(payload["items"], list)
    assert payload["items"][0]["title"] == "Example item"
    assert payload["items"][0]["extra"] == {"source": "manual"}


def test_csv_import_auto_mapping_and_summary(auth_client: TestClient) -> None:
    csv_content = (
        b"title,tags,creators,status,rating,note,extra\n"
        b'Imported One,tag-a|tag-b,Alice,wish,3,Queued,"{""source"":""manual""}"\n'
    )

    response = auth_client.post(
        "/api/import/csv",
        files={"file": ("items.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["imported"] == 1
    assert payload["skipped"] == 0
    assert payload["created_tags"] == 2
    assert payload["created_creators"] == 1
    assert payload["linked_tags"] == 2
    assert payload["linked_creators"] == 1
    assert payload["state_records"] == 1

    item = auth_client.get("/api/items").json()["items"][0]
    assert item["state"]["status"] == "wish"
    assert item["state"]["rating"] == 3
    assert item["state"]["review"] == "Queued"
    assert sorted(tag["name"] for tag in item["tags"]) == ["tag-a", "tag-b"]


def test_json_import_uses_items_structure(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/import/json",
        files={
            "file": (
                "items.json",
                json.dumps(
                    {
                        "items": [
                            {
                                "title": "Imported JSON",
                                "tags": ["json"],
                                "creators": ["Casey"],
                            }
                        ]
                    }
                ).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert auth_client.get("/api/search", params={"tag": "json"}).json()["total"] == 1


def test_csv_preview_does_not_write_database(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/import/csv",
        files={
            "file": (
                "items.csv",
                b"title,tags,creators,status\nPreview Item,tag-x,creator-x,watched\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert "可导入数量" in response.text
    assert "Preview Item" in response.text
    assert auth_client.get("/api/items").json()["total"] == 0


def test_csv_manual_field_mapping_imports_data(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/import/confirm",
        data=_csv_confirm_data(
            [{"Name": "Mapped Item", "Labels": "tag-a;tag-b", "People": "Alice"}],
            ["Name", "Labels", "People"],
            ["title", "tags", "creators"],
        ),
    )

    assert response.status_code == 200
    assert "已导入 1 条，跳过 0 条。" in response.text
    item = auth_client.get("/api/items").json()["items"][0]
    assert item["title"] == "Mapped Item"
    assert sorted(tag["name"] for tag in item["tags"]) == ["tag-a", "tag-b"]


def test_csv_missing_title_mapping_fails(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/import/confirm",
        data=_csv_confirm_data(
            [{"Name": "No Mapping"}],
            ["Name"],
            ["summary"],
        ),
    )

    assert response.status_code == 200
    assert "CSV 缺少 title 映射" in response.text
    assert auth_client.get("/api/items").json()["total"] == 0


def test_csv_duplicate_mapping_fails(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/import/confirm",
        data=_csv_confirm_data(
            [{"Name": "Duplicate", "Title": "Also Duplicate"}],
            ["Name", "Title"],
            ["title", "title"],
        ),
    )

    assert response.status_code == 200
    assert "CSV 字段重复映射" in response.text
    assert auth_client.get("/api/items").json()["total"] == 0


def test_csv_empty_and_missing_header_fail(auth_client: TestClient) -> None:
    empty_response = auth_client.post(
        "/import/csv",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    header_response = auth_client.post(
        "/import/csv",
        files={"file": ("header.csv", b",,\nvalue\n", "text/csv")},
    )

    assert "CSV 为空" in empty_response.text
    assert "CSV 缺少表头" in header_response.text


def test_csv_row_errors_are_shown_for_missing_title_status_rating_and_extra(
    auth_client: TestClient,
) -> None:
    csv_content = (
        "title,status,rating,extra\n"
        ",wish,3,{}\n"
        "Bad Status,planned,3,{}\n"
        "Bad Rating,wish,6,{}\n"
        'Bad Extra,wish,4,"{bad"\n'
    ).encode("utf-8")

    response = auth_client.post(
        "/import/csv",
        files={"file": ("bad.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    assert "该行缺少标题" in response.text
    assert "status 值无效" in response.text
    assert "rating 值无效" in response.text
    assert "extra JSON 无效" in response.text
    assert "disabled" in response.text
    assert auth_client.get("/api/items").json()["total"] == 0


def test_partial_error_rows_import_only_valid_rows_and_show_summary(
    auth_client: TestClient,
) -> None:
    response = auth_client.post(
        "/import/confirm",
        data=_csv_confirm_data(
            [
                {
                    "title": "Valid Item",
                    "status": "watched",
                    "rating": "5",
                    "tags": "tag-a;tag-b",
                    "creators": "Alice",
                },
                {"title": "", "status": "watched", "rating": "4"},
            ],
            ["title", "status", "rating", "tags", "creators"],
            ["title", "status", "rating", "tags", "creators"],
        ),
    )

    assert response.status_code == 200
    assert "已导入 1 条，跳过 1 条。" in response.text
    assert "创建标签" in response.text
    assert "创建创作者" in response.text
    assert "标签关联" in response.text
    assert "状态记录" in response.text
    assert "该行缺少标题" in response.text
    assert auth_client.get("/api/items").json()["total"] == 1


def test_json_format_and_shape_errors_fail(auth_client: TestClient) -> None:
    invalid_json = auth_client.post(
        "/import/json",
        files={"file": ("items.json", b"{", "application/json")},
    )
    missing_items = auth_client.post(
        "/import/json",
        files={"file": ("items.json", b"{}", "application/json")},
    )
    items_not_array = auth_client.post(
        "/import/json",
        files={"file": ("items.json", b'{"items": {}}', "application/json")},
    )

    assert "JSON 格式错误" in invalid_json.text
    assert "JSON 缺少 items" in missing_items.text
    assert "JSON items 不是数组" in items_not_array.text


def test_json_item_missing_title_enters_error_rows(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/import/json",
        files={
            "file": (
                "items.json",
                json.dumps({"items": [{"summary": "Missing title"}]}).encode("utf-8"),
                "application/json",
            )
        },
    )

    assert response.status_code == 200
    assert "JSON item 缺少 title" in response.text
    assert "错误行" in response.text
    assert auth_client.get("/api/items").json()["total"] == 0


def test_missing_and_unsupported_uploads_show_readable_errors(
    auth_client: TestClient,
) -> None:
    missing = auth_client.post("/import/csv")
    unsupported = auth_client.post(
        "/import/csv",
        files={"file": ("items.txt", b"title\nNope\n", "text/plain")},
    )

    assert "请先选择要导入的本地文件" in missing.text
    assert "文件类型不支持" in unsupported.text


def test_import_page_chinese_and_english_copy(auth_client: TestClient) -> None:
    zh_response = auth_client.get("/import")
    assert zh_response.status_code == 200
    assert "下载 CSV 模板" in zh_response.text
    assert "不支持 URL 导入" in zh_response.text
    zh_preview = auth_client.post(
        "/import/csv",
        files={"file": ("items.csv", b"title\nCopy Item\n", "text/csv")},
    )
    assert "CSV 字段映射" in zh_preview.text

    en_response = auth_client.get("/set-language", params={"lang": "en", "next": "/import"})
    assert en_response.status_code == 200
    assert "Download CSV Template" in en_response.text
    assert "URL import is not supported" in en_response.text
    en_preview = auth_client.post(
        "/import/csv",
        files={"file": ("items.csv", b"title\nCopy Item\n", "text/csv")},
    )
    assert "CSV Field Mapping" in en_preview.text
