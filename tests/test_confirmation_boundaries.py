from __future__ import annotations

from html import unescape

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Collection, Creator, Item, Tag, UserItemState
from app.services.settings import save_app_settings


def _create_item_with_relations(
    client: TestClient,
) -> tuple[int, int, int, int, int, int]:
    item_response = client.post(
        "/api/items",
        json={
            "title": "Confirmation Item",
            "tags": ["Existing Tag"],
            "creators": ["Existing Creator"],
        },
    )
    item_id = int(item_response.json()["id"])
    client.post(
        f"/api/items/{item_id}/state",
        json={"status": "wish", "rating": 2, "review": "keep"},
    )
    with SessionLocal() as db:
        tag_id = db.query(Tag.id).filter(Tag.name == "Existing Tag").scalar()
        creator_id = db.query(Creator.id).filter(Creator.name == "Existing Creator").scalar()
        new_tag = Tag(name="New Tag")
        collection = Collection(name="Existing Collection")
        new_collection = Collection(name="New Collection")
        db.add_all([new_tag, collection, new_collection])
        db.commit()
        db.refresh(new_tag)
        db.refresh(collection)
        db.refresh(new_collection)
        item = db.get(Item, item_id)
        assert item is not None
        item.collections.append(collection)
        db.commit()
        return (
            item_id,
            int(tag_id),
            int(creator_id),
            collection.id,
            new_tag.id,
            new_collection.id,
        )


def _item_snapshot(client: TestClient, item_id: int) -> dict[str, object]:
    response = client.get(f"/api/items/{item_id}")
    assert response.status_code == 200
    return response.json()


def _bulk_requests(
    item_id: int,
    tag_id: int,
    collection_id: int,
    new_tag_id: int,
    new_collection_id: int,
) -> list[dict[str, object]]:
    return [
        {"bulk_action": "status", "status_value": "like", "item_ids": str(item_id)},
        {"bulk_action": "rating", "rating": "5", "item_ids": str(item_id)},
        {"bulk_action": "add_tag", "add_tag_id": str(new_tag_id), "item_ids": str(item_id)},
        {"bulk_action": "remove_tag", "remove_tag_id": str(tag_id), "item_ids": str(item_id)},
        {
            "bulk_action": "add_collection",
            "add_collection_id": str(new_collection_id),
            "item_ids": str(item_id),
        },
        {
            "bulk_action": "remove_collection",
            "remove_collection_id": str(collection_id),
            "item_ids": str(item_id),
        },
        {"bulk_action": "delete", "item_ids": str(item_id)},
    ]


def test_every_bulk_write_rejects_missing_confirmation_without_partial_write(
    auth_client: TestClient,
) -> None:
    item_id, tag_id, _, collection_id, new_tag_id, new_collection_id = (
        _create_item_with_relations(auth_client)
    )
    before = _item_snapshot(auth_client, item_id)

    for data in _bulk_requests(
        item_id,
        tag_id,
        collection_id,
        new_tag_id,
        new_collection_id,
    ):
        response = auth_client.post("/items/bulk", data=data, follow_redirects=True)
        assert response.status_code == 200
        assert "缺少手动确认" in response.text
        assert _item_snapshot(auth_client, item_id) == before


def test_strict_bulk_confirmation_rejects_wrong_text_and_accepts_exact_text(
    auth_client: TestClient,
) -> None:
    item_id, tag_id, _, collection_id, new_tag_id, new_collection_id = (
        _create_item_with_relations(auth_client)
    )
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})
    before = _item_snapshot(auth_client, item_id)

    for data in _bulk_requests(
        item_id,
        tag_id,
        collection_id,
        new_tag_id,
        new_collection_id,
    ):
        rejected = auth_client.post(
            "/items/bulk",
            data={**data, "confirm": "1", "confirmation_text": "confirm"},
            follow_redirects=True,
        )
        assert rejected.status_code == 200
        assert "CONFIRM" in rejected.text
        assert _item_snapshot(auth_client, item_id) == before

    accepted = auth_client.post(
        "/items/bulk",
        data={
            "bulk_action": "status",
            "status_value": "like",
            "item_ids": str(item_id),
            "confirm": "1",
            "confirmation_text": "CONFIRM",
        },
        follow_redirects=False,
    )
    assert accepted.status_code == 303
    assert _item_snapshot(auth_client, item_id)["state"]["status"] == "like"


def test_strict_state_clear_and_relationship_detach_require_exact_confirmation(
    auth_client: TestClient,
) -> None:
    item_id, tag_id, creator_id, collection_id, _, _ = _create_item_with_relations(
        auth_client
    )
    with SessionLocal() as db:
        save_app_settings(db, {"danger_confirmation_mode": "strict"})

    guarded_paths = [
        f"/items/{item_id}/state/delete",
        f"/items/{item_id}/tags/{tag_id}/delete",
        f"/items/{item_id}/creators/{creator_id}/delete",
        f"/items/{item_id}/collections/{collection_id}/delete",
        f"/collections/{collection_id}/items/{item_id}/delete",
    ]
    for path in guarded_paths:
        missing = auth_client.post(path, follow_redirects=False)
        wrong = auth_client.post(
            path,
            data={"confirm": "1", "confirmation_text": "confirm"},
            follow_redirects=False,
        )
        assert missing.status_code == 303
        assert wrong.status_code == 303

    before = _item_snapshot(auth_client, item_id)
    assert before["state"] is not None
    assert len(before["tags"]) == 1
    assert len(before["creators"]) == 1
    assert len(before["collections"]) == 1

    for path in guarded_paths[:4]:
        accepted = auth_client.post(
            path,
            data={"confirm": "1", "confirmation_text": "CONFIRM"},
            follow_redirects=False,
        )
        assert accepted.status_code == 303

    auth_client.post(
        f"/collections/{collection_id}/items",
        data={"item_id": str(item_id)},
    )
    collection_side_accepted = auth_client.post(
        guarded_paths[4],
        data={"confirm": "1", "confirmation_text": "CONFIRM"},
        follow_redirects=False,
    )
    assert collection_side_accepted.status_code == 303

    after = _item_snapshot(auth_client, item_id)
    assert after["state"] is None
    assert after["tags"] == []
    assert after["creators"] == []
    assert after["collections"] == []
    with SessionLocal() as db:
        assert db.get(Tag, tag_id) is not None
        assert db.get(Creator, creator_id) is not None
        assert db.get(Collection, collection_id) is not None
        assert db.query(UserItemState).filter(UserItemState.item_id == item_id).count() == 0


def test_confirmation_prompts_are_complete_in_both_languages(
    auth_client: TestClient,
) -> None:
    item_id, _, _, collection_id, _, _ = _create_item_with_relations(auth_client)

    zh_items = auth_client.get("/items")
    zh_detail = auth_client.get(f"/items/{item_id}")
    zh_collection = auth_client.get(f"/collections/{collection_id}")
    assert "确认批量修改所选条目的状态？" in zh_items.text
    assert "确认批量解除所选条目与这个标签的关系" in zh_items.text
    assert "确认清除当前条目的状态、评分和短评？" in zh_detail.text
    assert "确认解除当前条目与这个创作者的关系" in zh_detail.text
    assert "确认将这个条目移出合集？" in zh_collection.text

    auth_client.get("/set-language", params={"lang": "en", "next": "/items"})
    en_items = auth_client.get("/items")
    en_detail = auth_client.get(f"/items/{item_id}")
    en_collection = auth_client.get(f"/collections/{collection_id}")
    assert "Update the status of every selected item?" in en_items.text
    assert "Detach this tag from every selected item?" in en_items.text
    assert "Clear this item's status, rating, and short review?" in unescape(
        en_detail.text
    )
    assert "Detach this creator from the item?" in en_detail.text
    assert "Remove this item from the collection?" in en_collection.text
