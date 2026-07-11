from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Collection, Creator, Item, ItemCollection, Tag


def _create_item(
    client: TestClient,
    title: str,
    *,
    summary: str | None = None,
    tags: list[str] | None = None,
    creators: list[str] | None = None,
    extra: dict[str, Any] | None = None,
    status: str | None = None,
    rating: int | None = None,
    review: str | None = None,
) -> int:
    payload: dict[str, Any] = {
        "title": title,
        "tags": tags or [],
        "creators": creators or [],
    }
    if summary is not None:
        payload["summary"] = summary
    if extra is not None:
        payload["extra"] = extra
    response = client.post("/api/items", json=payload)
    assert response.status_code == 201
    item_id = int(response.json()["id"])
    if status:
        state_payload: dict[str, Any] = {"status": status}
        if rating is not None:
            state_payload["rating"] = rating
        if review is not None:
            state_payload["review"] = review
        state_response = client.post(f"/api/items/{item_id}/state", json=state_payload)
        assert state_response.status_code == 201
    return item_id


def _direct_item(title: str, *, extra: str | None = None) -> int:
    with SessionLocal() as db:
        item = Item(title=title, extra=extra)
        db.add(item)
        db.commit()
        db.refresh(item)
        return int(item.id)


def _item(client: TestClient, item_id: int) -> dict[str, Any]:
    response = client.get(f"/api/items/{item_id}")
    assert response.status_code == 200
    return response.json()


def _create_collection(client: TestClient, name: str) -> int:
    response = client.post(
        "/collections",
        data={"name": name, "description": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with SessionLocal() as db:
        collection_id = db.scalar(select(Collection.id).where(Collection.name == name))
        assert collection_id is not None
        return int(collection_id)


def _add_collection(client: TestClient, item_id: int, collection_id: int) -> None:
    response = client.post(
        f"/items/{item_id}/collections",
        data={"collection_id": str(collection_id), "next": "/items"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _table_counts() -> dict[str, int]:
    with SessionLocal() as db:
        return {
            "items": db.scalar(select(func.count(Item.id))) or 0,
            "tags": db.scalar(select(func.count(Tag.id))) or 0,
            "creators": db.scalar(select(func.count(Creator.id))) or 0,
            "collections": db.scalar(select(func.count(Collection.id))) or 0,
            "item_collections": db.scalar(select(func.count(ItemCollection.item_id))) or 0,
        }


def _set_extra_raw(item_id: int, extra: str) -> None:
    with SessionLocal() as db:
        item = db.get(Item, item_id)
        assert item is not None
        item.extra = extra
        db.commit()


def test_duplicates_page_requires_login(client: TestClient) -> None:
    response = client.get("/duplicates", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_duplicates_page_renders_empty_state(auth_client: TestClient) -> None:
    response = auth_client.get("/duplicates")

    assert response.status_code == 200
    assert "暂无重复候选" in response.text
    assert "候选列表只读" in response.text


def test_duplicates_page_detects_exact_and_normalized_candidates(
    auth_client: TestClient,
) -> None:
    first_id = _direct_item("Exact Local Title")
    second_id = _direct_item("  Exact Local Title  ")
    _direct_item("Ａ  MIX")
    _direct_item("a mix")
    _create_item(auth_client, "Unique Local Title")

    response = auth_client.get("/duplicates")

    assert response.status_code == 200
    assert "标题完全匹配" in response.text
    assert "标题归一化匹配" in response.text
    assert "Exact Local Title" in response.text
    assert "Ａ  MIX" in response.text
    assert "a mix" in response.text
    assert "Unique Local Title" not in response.text
    assert f"/duplicates/compare?primary_id={first_id}&duplicate_id={second_id}" in response.text
    with SessionLocal() as db:
        preserved_title = db.get(Item, second_id).title  # type: ignore[union-attr]
    assert preserved_title == "  Exact Local Title  "


def test_duplicate_compare_page_validation_and_content(
    auth_client: TestClient,
) -> None:
    primary_id = _create_item(
        auth_client,
        "Compare Primary",
        summary="Keep this",
        tags=["compare-tag"],
        creators=["Compare Creator"],
        extra={"origin": "primary"},
        status="like",
        rating=4,
        review="primary note",
    )
    duplicate_id = _create_item(
        auth_client,
        "Compare Duplicate",
        summary="Take this",
        tags=["duplicate-tag"],
        creators=["Duplicate Creator"],
        extra={"origin": "duplicate", "new": "value"},
        status="watched",
        rating=2,
        review="duplicate note",
    )
    collection_id = _create_collection(auth_client, "Compare Collection")
    _add_collection(auth_client, duplicate_id, collection_id)

    response = auth_client.get(
        "/duplicates/compare",
        params={"primary_id": str(primary_id), "duplicate_id": str(duplicate_id)},
    )

    assert response.status_code == 200
    assert "保留条目" in response.text
    assert "重复条目" in response.text
    assert "危险操作" in response.text
    assert "Compare Primary" in response.text
    assert "Compare Duplicate" in response.text
    assert "compare-tag" in response.text
    assert "Duplicate Creator" in response.text
    assert "Compare Collection" in response.text
    assert "使用重复条目的简介覆盖保留条目" in response.text
    assert "extra 冲突默认保留 primary" in response.text

    invalid_response = auth_client.get(
        "/duplicates/compare",
        params={"primary_id": "not-an-id", "duplicate_id": str(duplicate_id)},
        follow_redirects=True,
    )
    assert "条目 ID 无效" in invalid_response.text

    same_response = auth_client.get(
        "/duplicates/compare",
        params={"primary_id": str(primary_id), "duplicate_id": str(primary_id)},
        follow_redirects=True,
    )
    assert "不能合并同一个条目" in same_response.text

    missing_response = auth_client.get(
        "/duplicates/compare",
        params={"primary_id": str(primary_id), "duplicate_id": "9999"},
        follow_redirects=True,
    )
    assert "条目不存在" in missing_response.text


def test_duplicate_merge_requires_login_and_post(client: TestClient) -> None:
    primary_id = _direct_item("Unauth Primary")
    duplicate_id = _direct_item("Unauth Duplicate")

    post_response = client.post(
        "/duplicates/merge",
        data={
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
            "confirm": "1",
        },
        follow_redirects=False,
    )
    get_response = client.get(
        "/duplicates/merge",
        params={"primary_id": str(primary_id), "duplicate_id": str(duplicate_id)},
    )

    assert post_response.status_code == 303
    assert post_response.headers["location"] == "/login"
    assert get_response.status_code == 405
    with SessionLocal() as db:
        assert db.get(Item, primary_id) is not None
        assert db.get(Item, duplicate_id) is not None


def test_duplicate_merge_transfers_relations_and_deletes_duplicate(
    auth_client: TestClient,
) -> None:
    primary_id = _create_item(
        auth_client,
        "Merge Primary",
        tags=["shared-tag", "primary-tag"],
        creators=["Primary Creator"],
    )
    duplicate_id = _create_item(
        auth_client,
        "Merge Duplicate",
        summary="Copied summary",
        tags=["shared-tag", "duplicate-tag"],
        creators=["Duplicate Creator"],
    )
    shared_collection_id = _create_collection(auth_client, "Shared Merge Collection")
    duplicate_collection_id = _create_collection(auth_client, "Duplicate Merge Collection")
    _add_collection(auth_client, primary_id, shared_collection_id)
    _add_collection(auth_client, duplicate_id, shared_collection_id)
    _add_collection(auth_client, duplicate_id, duplicate_collection_id)
    before_counts = _table_counts()

    response = auth_client.post(
        "/duplicates/merge",
        data={
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
            "confirm": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "合并摘要" in response.text
    assert "已将" in response.text
    primary = _item(auth_client, primary_id)
    assert auth_client.get(f"/api/items/{duplicate_id}").status_code == 404
    assert primary["summary"] == "Copied summary"
    assert {tag["name"] for tag in primary["tags"]} == {
        "shared-tag",
        "primary-tag",
        "duplicate-tag",
    }
    assert {creator["name"] for creator in primary["creators"]} == {
        "Primary Creator",
        "Duplicate Creator",
    }
    assert {collection["name"] for collection in primary["collections"]} == {
        "Shared Merge Collection",
        "Duplicate Merge Collection",
    }
    after_counts = _table_counts()
    assert after_counts["items"] == before_counts["items"] - 1
    assert after_counts["tags"] == before_counts["tags"]
    assert after_counts["creators"] == before_counts["creators"]
    assert after_counts["collections"] == before_counts["collections"]
    assert after_counts["item_collections"] == 2


def test_duplicate_merge_defaults_keep_primary_conflicts_and_merges_extra(
    auth_client: TestClient,
) -> None:
    primary_id = _create_item(
        auth_client,
        "Conflict Primary",
        summary="primary summary",
        extra={"same": "primary", "keep": 1},
        status="like",
        rating=5,
        review="primary review",
    )
    duplicate_id = _create_item(
        auth_client,
        "Conflict Duplicate",
        summary="duplicate summary",
        extra={"same": "duplicate", "new": 2},
        status="watched",
        rating=2,
        review="duplicate review",
    )

    response = auth_client.post(
        "/duplicates/merge",
        data={
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
            "confirm": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "保留 primary" in response.text
    primary = _item(auth_client, primary_id)
    assert primary["summary"] == "primary summary"
    assert primary["state"]["status"] == "like"
    assert primary["state"]["rating"] == 5
    assert primary["state"]["review"] == "primary review"
    assert primary["extra"] == {"keep": 1, "new": 2, "same": "primary"}
    assert auth_client.get(f"/api/items/{duplicate_id}").status_code == 404


def test_duplicate_merge_can_overwrite_selected_text_and_state_fields(
    auth_client: TestClient,
) -> None:
    primary_id = _create_item(
        auth_client,
        "Overwrite Primary",
        summary="primary summary",
        extra={"same": "primary"},
        status="wish",
        rating=1,
        review="primary review",
    )
    duplicate_id = _create_item(
        auth_client,
        "Overwrite Duplicate",
        summary="duplicate summary",
        extra={"same": "duplicate"},
        status="watched",
        rating=4,
        review="duplicate review",
    )

    response = auth_client.post(
        "/duplicates/merge",
        data={
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
            "use_duplicate_summary": "1",
            "use_duplicate_status": "1",
            "use_duplicate_rating": "1",
            "use_duplicate_review": "1",
            "confirm": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "已覆盖" in response.text
    primary = _item(auth_client, primary_id)
    assert primary["summary"] == "duplicate summary"
    assert primary["state"]["status"] == "watched"
    assert primary["state"]["rating"] == 4
    assert primary["state"]["review"] == "duplicate review"
    assert primary["extra"] == {"same": "primary"}


def test_duplicate_merge_copies_state_when_primary_missing_and_repairs_bad_extra(
    auth_client: TestClient,
) -> None:
    primary_id = _create_item(auth_client, "Copy Missing Primary")
    duplicate_id = _create_item(
        auth_client,
        "Copy Missing Duplicate",
        extra={"source": "duplicate"},
        status="watching",
        rating=3,
        review="copied review",
    )
    _set_extra_raw(primary_id, "{bad-json")

    response = auth_client.post(
        "/duplicates/merge",
        data={
            "primary_id": str(primary_id),
            "duplicate_id": str(duplicate_id),
            "confirm": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    primary = _item(auth_client, primary_id)
    assert primary["state"]["status"] == "watching"
    assert primary["state"]["rating"] == 3
    assert primary["state"]["review"] == "copied review"
    assert primary["extra"] == {"raw": "{bad-json", "source": "duplicate"}


def test_duplicates_i18n_labels(auth_client: TestClient) -> None:
    zh_response = auth_client.get("/duplicates")
    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/duplicates"},
        follow_redirects=True,
    )

    assert "重复条目检测" in zh_response.text
    assert "候选列表只读" in zh_response.text
    assert "Duplicate Items" in en_response.text
    assert "read-only" in en_response.text
