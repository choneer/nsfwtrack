from __future__ import annotations

from fastapi.testclient import TestClient


def _create_item(
    client: TestClient,
    title: str,
    *,
    tags: list[str] | None = None,
    creators: list[str] | None = None,
    status: str | None = None,
    rating: int | None = None,
) -> int:
    response = client.post(
        "/api/items",
        json={"title": title, "tags": tags or [], "creators": creators or []},
    )
    assert response.status_code == 201
    item_id = int(response.json()["id"])
    if status:
        payload: dict[str, object] = {"status": status}
        if rating is not None:
            payload["rating"] = rating
        state_response = client.post(f"/api/items/{item_id}/state", json=payload)
        assert state_response.status_code == 201
    return item_id


def _create_tag(client: TestClient, name: str) -> int:
    response = client.post("/api/tags", json={"name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def _bulk_data(
    action: str,
    item_ids: list[int] | None = None,
    **values: str,
) -> dict[str, object]:
    data: dict[str, object] = {
        "bulk_action": action,
        "next": "/items",
        "confirm": "1",
    }
    if item_ids is not None:
        data["item_ids"] = [str(item_id) for item_id in item_ids]
    data.update(values)
    return data


def _item(client: TestClient, item_id: int) -> dict[str, object]:
    response = client.get(f"/api/items/{item_id}")
    assert response.status_code == 200
    return response.json()


def _tag_names(client: TestClient, item_id: int) -> list[str]:
    item = _item(client, item_id)
    return [tag["name"] for tag in item["tags"]]


def test_bulk_action_requires_login(client: TestClient) -> None:
    response = client.post(
        "/items/bulk",
        data=_bulk_data("delete", [1]),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_bulk_action_without_selection_shows_error(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/items/bulk",
        data=_bulk_data("status", None, status_value="like"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "未选择任何条目" in response.text


def test_bulk_status_success_invalid_status_and_preserved_next(
    auth_client: TestClient,
) -> None:
    first_id = _create_item(auth_client, "Blue One", status="wish")
    second_id = _create_item(auth_client, "Blue Two", status="watched")
    next_url = "/items?q=Blue&sort=title_desc&page_size=50"

    response = auth_client.post(
        "/items/bulk",
        data={
            "bulk_action": "status",
            "item_ids": [str(first_id), str(second_id), "999999"],
            "status_value": "like",
            "next": next_url,
            "confirm": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert str(response.url).endswith(next_url)
    assert "批量操作成功：已处理 2 条，已跳过 1 条。" in response.text
    assert _item(auth_client, first_id)["state"]["status"] == "like"
    assert _item(auth_client, second_id)["state"]["status"] == "like"
    assert 'name="q" value="Blue"' in response.text
    assert '<option value="title_desc" selected>' in response.text

    invalid_response = auth_client.post(
        "/items/bulk",
        data=_bulk_data("status", [first_id], status_value="bad"),
        follow_redirects=True,
    )

    assert invalid_response.status_code == 200
    assert "状态值无效" in invalid_response.text
    assert _item(auth_client, first_id)["state"]["status"] == "like"


def test_bulk_add_tag_success_and_missing_tag_failure(auth_client: TestClient) -> None:
    first_id = _create_item(auth_client, "Tag One", tags=["existing"])
    second_id = _create_item(auth_client, "Tag Two")
    tag_id = _create_tag(auth_client, "bulk-tag")

    response = auth_client.post(
        "/items/bulk",
        data=_bulk_data("add_tag", [first_id, second_id], add_tag_id=str(tag_id)),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "批量操作成功" in response.text
    assert "bulk-tag" in _tag_names(auth_client, first_id)
    assert "bulk-tag" in _tag_names(auth_client, second_id)

    repeat_response = auth_client.post(
        "/items/bulk",
        data=_bulk_data("add_tag", [first_id], add_tag_id=str(tag_id)),
        follow_redirects=True,
    )
    assert repeat_response.status_code == 200
    assert _tag_names(auth_client, first_id).count("bulk-tag") == 1

    required_response = auth_client.post(
        "/items/bulk",
        data=_bulk_data("add_tag", [first_id]),
        follow_redirects=True,
    )
    assert required_response.status_code == 200
    assert "请选择一个已有标签" in required_response.text

    missing_response = auth_client.post(
        "/items/bulk",
        data=_bulk_data("add_tag", [first_id], add_tag_id="999999"),
        follow_redirects=True,
    )

    assert missing_response.status_code == 200
    assert "标签不存在" in missing_response.text


def test_bulk_remove_tag_success(auth_client: TestClient) -> None:
    first_id = _create_item(auth_client, "Remove One", tags=["drop-me", "keep-me"])
    second_id = _create_item(auth_client, "Remove Two")
    drop_tag_id = next(
        tag["id"] for tag in _item(auth_client, first_id)["tags"] if tag["name"] == "drop-me"
    )

    response = auth_client.post(
        "/items/bulk",
        data=_bulk_data("remove_tag", [first_id, second_id], remove_tag_id=str(drop_tag_id)),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "批量操作成功" in response.text
    assert "drop-me" not in _tag_names(auth_client, first_id)
    assert "keep-me" in _tag_names(auth_client, first_id)
    assert _tag_names(auth_client, second_id) == []


def test_bulk_rating_success_and_invalid_rating(auth_client: TestClient) -> None:
    first_id = _create_item(auth_client, "Rate One", status="wish", rating=1)
    second_id = _create_item(auth_client, "Rate Two", status="watched", rating=2)

    response = auth_client.post(
        "/items/bulk",
        data=_bulk_data("rating", [first_id, second_id], rating="5"),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert _item(auth_client, first_id)["state"]["rating"] == 5
    assert _item(auth_client, second_id)["state"]["rating"] == 5

    invalid_response = auth_client.post(
        "/items/bulk",
        data=_bulk_data("rating", [first_id], rating="9"),
        follow_redirects=True,
    )

    assert invalid_response.status_code == 200
    assert "评分值无效" in invalid_response.text
    assert _item(auth_client, first_id)["state"]["rating"] == 5


def test_bulk_delete_removes_only_selected_items_and_related_rows(
    auth_client: TestClient,
) -> None:
    first_id = _create_item(
        auth_client,
        "Delete One",
        tags=["delete-tag"],
        creators=["Delete Creator"],
        status="wish",
        rating=4,
    )
    second_id = _create_item(
        auth_client,
        "Delete Two",
        tags=["delete-tag"],
        creators=["Delete Creator"],
        status="watched",
        rating=5,
    )
    keep_id = _create_item(
        auth_client,
        "Keep Me",
        tags=["delete-tag"],
        creators=["Delete Creator"],
        status="like",
        rating=3,
    )

    response = auth_client.post(
        "/items/bulk",
        data=_bulk_data("delete", [first_id, second_id]),
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "批量操作成功：已处理 2 条，已跳过 0 条。" in response.text
    assert auth_client.get(f"/api/items/{first_id}").status_code == 404
    assert auth_client.get(f"/api/items/{second_id}").status_code == 404
    assert auth_client.get(f"/api/items/{keep_id}").status_code == 200

    backup_payload = auth_client.get("/api/backup/export/json").json()
    deleted_ids = {first_id, second_id}
    for table_name in ("item_tags", "item_creators", "user_item_states"):
        assert all(
            row["item_id"] not in deleted_ids
            for row in backup_payload["tables"][table_name]
        )


def test_bulk_action_i18n_labels(auth_client: TestClient) -> None:
    _create_item(auth_client, "Bulk UI", tags=["ui-tag"])

    zh_response = auth_client.get("/items")
    assert zh_response.status_code == 200
    assert "批量操作" in zh_response.text
    assert "全选当前页" in zh_response.text
    assert "确认批量删除选中的条目？删除后无法撤销。" in zh_response.text

    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/items"},
    )
    assert en_response.status_code == 200
    assert "Bulk actions" in en_response.text
    assert "Select current page" in en_response.text
    assert "Delete the selected items? This cannot be undone." in en_response.text
