from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Collection, ItemCollection


def _create_item(
    client: TestClient,
    title: str,
    *,
    tags: list[str] | None = None,
    creators: list[str] | None = None,
    status: str | None = None,
) -> int:
    response = client.post(
        "/api/items",
        json={"title": title, "tags": tags or [], "creators": creators or []},
    )
    assert response.status_code == 201
    item_id = int(response.json()["id"])
    if status:
        state_response = client.post(
            f"/api/items/{item_id}/state",
            json={"status": status},
        )
        assert state_response.status_code == 201
    return item_id


def _create_collection(
    client: TestClient,
    name: str,
    description: str | None = None,
) -> int:
    response = client.post(
        "/collections",
        data={"name": name, "description": description or ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with SessionLocal() as db:
        collection = db.query(Collection).filter(Collection.name == name.strip()).one()
        return int(collection.id)


def _relation_count(item_id: int, collection_id: int) -> int:
    with SessionLocal() as db:
        return (
            db.query(ItemCollection)
            .filter(
                ItemCollection.item_id == item_id,
                ItemCollection.collection_id == collection_id,
            )
            .count()
        )


def _collection_count() -> int:
    with SessionLocal() as db:
        return db.query(Collection).count()


def _bulk_data(
    action: str,
    item_ids: list[int] | None = None,
    **values: str,
) -> dict[str, object]:
    data: dict[str, object] = {"bulk_action": action, "next": "/items"}
    if action == "delete":
        data["confirm"] = "1"
    if item_ids is not None:
        data["item_ids"] = [str(item_id) for item_id in item_ids]
    data.update(values)
    return data


def test_collections_page_requires_login(client: TestClient) -> None:
    login_response = client.get("/collections", follow_redirects=False)
    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/login"


def test_collections_page_renders_empty_state(auth_client: TestClient) -> None:
    response = auth_client.get("/collections")
    assert response.status_code == 200
    assert "合集列表" in response.text
    assert "没有合集。" in response.text
    assert "新建合集" in response.text


def test_collection_create_edit_delete_and_delete_keeps_items(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(auth_client, "Kept Item")

    empty_response = auth_client.post(
        "/collections",
        data={"name": "   ", "description": ""},
        follow_redirects=True,
    )
    assert empty_response.status_code == 200
    assert "合集名称不能为空" in empty_response.text

    collection_id = _create_collection(auth_client, "Watch Later", "Manual list")
    duplicate_response = auth_client.post(
        "/collections",
        data={"name": "Watch Later", "description": ""},
        follow_redirects=True,
    )
    assert duplicate_response.status_code == 200
    assert "合集名称已存在" in duplicate_response.text

    edit_response = auth_client.post(
        f"/collections/{collection_id}/edit",
        data={"name": "Watch Later Updated", "description": "Updated note"},
        follow_redirects=True,
    )
    assert edit_response.status_code == 200
    assert "合集已更新" in edit_response.text
    assert "Watch Later Updated" in edit_response.text

    auth_client.post(
        f"/collections/{collection_id}/items",
        data={"item_id": str(item_id)},
        follow_redirects=True,
    )
    assert _relation_count(item_id, collection_id) == 1

    delete_response = auth_client.post(
        f"/collections/{collection_id}/delete",
        data={"confirm": "1"},
        follow_redirects=True,
    )
    assert delete_response.status_code == 200
    assert "合集已删除" in delete_response.text
    assert auth_client.get(f"/api/items/{item_id}").status_code == 200
    assert _collection_count() == 0


def test_collection_detail_adds_removes_items_and_handles_duplicates(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(
        auth_client,
        "Collection Detail Item",
        tags=["detail-tag"],
        creators=["Detail Creator"],
        status="like",
    )
    collection_id = _create_collection(auth_client, "Detail Collection")

    empty_response = auth_client.get(f"/collections/{collection_id}")
    assert empty_response.status_code == 200
    assert "合集为空。" in empty_response.text

    add_response = auth_client.post(
        f"/collections/{collection_id}/items",
        data={"item_id": str(item_id)},
        follow_redirects=True,
    )
    assert add_response.status_code == 200
    assert "已加入合集" in add_response.text
    assert "Collection Detail Item" in add_response.text
    assert _relation_count(item_id, collection_id) == 1

    duplicate_response = auth_client.post(
        f"/collections/{collection_id}/items",
        data={"item_id": str(item_id)},
        follow_redirects=True,
    )
    assert duplicate_response.status_code == 200
    assert "重复关联" in duplicate_response.text
    assert _relation_count(item_id, collection_id) == 1

    remove_response = auth_client.post(
        f"/collections/{collection_id}/items/{item_id}/delete",
        follow_redirects=True,
    )
    assert remove_response.status_code == 200
    assert "已移出合集" in remove_response.text
    assert _relation_count(item_id, collection_id) == 0

    repeat_remove_response = auth_client.post(
        f"/collections/{collection_id}/items/{item_id}/delete",
        follow_redirects=True,
    )
    assert repeat_remove_response.status_code == 200
    assert "已移出合集" in repeat_remove_response.text


def test_item_detail_shows_and_manages_collections(auth_client: TestClient) -> None:
    item_id = _create_item(auth_client, "Item Detail Collection")
    collection_id = _create_collection(auth_client, "Detail Owned")

    add_response = auth_client.post(
        f"/items/{item_id}/collections",
        data={"collection_id": str(collection_id), "next": "/items?collection=1"},
        follow_redirects=True,
    )
    assert add_response.status_code == 200
    assert "已加入合集" in add_response.text
    assert "Detail Owned" in add_response.text
    assert _relation_count(item_id, collection_id) == 1

    duplicate_response = auth_client.post(
        f"/items/{item_id}/collections",
        data={"collection_id": str(collection_id)},
        follow_redirects=True,
    )
    assert duplicate_response.status_code == 200
    assert "重复关联" in duplicate_response.text
    assert _relation_count(item_id, collection_id) == 1

    detail_response = auth_client.get(f"/items/{item_id}")
    assert detail_response.status_code == 200
    assert "所属合集" in detail_response.text
    assert "Detail Owned" in detail_response.text

    remove_response = auth_client.post(
        f"/items/{item_id}/collections/{collection_id}/delete",
        follow_redirects=True,
    )
    assert remove_response.status_code == 200
    assert "已移出合集" in remove_response.text
    assert _relation_count(item_id, collection_id) == 0


def test_items_page_filters_by_collection_and_preserves_query_string(
    auth_client: TestClient,
) -> None:
    first_id = _create_item(
        auth_client,
        "Collection Blue",
        tags=["collection-tag"],
        creators=["Collection Creator"],
        status="wish",
    )
    _create_item(auth_client, "Outside Blue", tags=["collection-tag"], creators=["Other"])
    collection_id = _create_collection(auth_client, "Filter Collection")
    auth_client.post(
        f"/collections/{collection_id}/items",
        data={"item_id": str(first_id)},
        follow_redirects=True,
    )

    response = auth_client.get(
        "/items",
        params={
            "collection": str(collection_id),
            "q": "Blue",
            "tag": "collection-tag",
            "creator": "Collection Creator",
            "state": "wish",
            "page_size": "10",
        },
    )
    assert response.status_code == 200
    assert "Collection Blue" in response.text
    assert "Outside Blue" not in response.text
    assert f'<option value="{collection_id}" selected>' in response.text
    assert "collection%3D" in response.text

    invalid_response = auth_client.get("/items", params={"collection": "not-an-id"})
    assert invalid_response.status_code == 200
    assert "Outside Blue" in invalid_response.text


def test_bulk_add_remove_collection_and_error_paths(auth_client: TestClient) -> None:
    first_id = _create_item(auth_client, "Bulk Collection One")
    second_id = _create_item(auth_client, "Bulk Collection Two")
    collection_id = _create_collection(auth_client, "Bulk Collection")

    missing_selection = auth_client.post(
        "/items/bulk",
        data=_bulk_data("add_collection", [first_id]),
        follow_redirects=True,
    )
    assert missing_selection.status_code == 200
    assert "请选择一个已有合集" in missing_selection.text

    missing_collection = auth_client.post(
        "/items/bulk",
        data=_bulk_data("add_collection", [first_id], add_collection_id="999999"),
        follow_redirects=True,
    )
    assert missing_collection.status_code == 200
    assert "合集不存在" in missing_collection.text

    add_response = auth_client.post(
        "/items/bulk",
        data=_bulk_data(
            "add_collection",
            [first_id, second_id],
            add_collection_id=str(collection_id),
        ),
        follow_redirects=True,
    )
    assert add_response.status_code == 200
    assert "批量操作成功" in add_response.text
    assert _relation_count(first_id, collection_id) == 1
    assert _relation_count(second_id, collection_id) == 1

    repeat_response = auth_client.post(
        "/items/bulk",
        data=_bulk_data("add_collection", [first_id], add_collection_id=str(collection_id)),
        follow_redirects=True,
    )
    assert repeat_response.status_code == 200
    assert _relation_count(first_id, collection_id) == 1

    remove_response = auth_client.post(
        "/items/bulk",
        data=_bulk_data(
            "remove_collection",
            [first_id, second_id],
            remove_collection_id=str(collection_id),
        ),
        follow_redirects=True,
    )
    assert remove_response.status_code == 200
    assert _relation_count(first_id, collection_id) == 0
    assert _relation_count(second_id, collection_id) == 0

    repeat_remove = auth_client.post(
        "/items/bulk",
        data=_bulk_data(
            "remove_collection",
            [first_id],
            remove_collection_id=str(collection_id),
        ),
        follow_redirects=True,
    )
    assert repeat_remove.status_code == 200


def test_stats_show_collection_counts_and_ranking(auth_client: TestClient) -> None:
    first_id = _create_item(auth_client, "Stats Collection One")
    second_id = _create_item(auth_client, "Stats Collection Two")
    third_id = _create_item(auth_client, "Stats Collection None")
    collection_id = _create_collection(auth_client, "Stats Collection")
    auth_client.post(
        f"/collections/{collection_id}/items",
        data={"item_id": str(first_id)},
        follow_redirects=True,
    )
    auth_client.post(
        f"/collections/{collection_id}/items",
        data={"item_id": str(second_id)},
        follow_redirects=True,
    )

    summary = auth_client.get("/api/stats/summary").json()
    assert summary["total_items"] == 3
    assert summary["total_collections"] == 1
    assert summary["items_with_collections"] == 2
    assert summary["items_without_collections"] == 1
    assert summary["collection_ranking"]["rows"][0]["name"] == "Stats Collection"
    assert summary["collection_ranking"]["rows"][0]["count"] == 2

    page_response = auth_client.get("/stats")
    assert page_response.status_code == 200
    assert "总合集数" in page_response.text
    assert "合集排行" in page_response.text
    assert "Stats Collection" in page_response.text
    assert auth_client.get(f"/api/items/{third_id}").status_code == 200


def test_collections_page_i18n_labels(auth_client: TestClient) -> None:
    _create_collection(auth_client, "Bilingual Collection")

    zh_response = auth_client.get("/collections")
    assert zh_response.status_code == 200
    assert "合集列表" in zh_response.text
    assert "新建合集" in zh_response.text
    assert "删除合集不会删除条目" in zh_response.text

    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/collections"},
    )
    assert en_response.status_code == 200
    assert "Collection List" in en_response.text
    assert "New Collection" in en_response.text
    assert "Deleting a collection removes only the collection links" in en_response.text
