from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Collection, Creator, Item, ItemActivity, SavedView, Tag


def _create_item(client: TestClient, title: str) -> int:
    response = client.post(
        "/api/items",
        json={"title": title, "tags": [], "creators": []},
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def _create_item_in_db(title: str) -> int:
    with SessionLocal() as db:
        item = Item(title=title)
        db.add(item)
        db.commit()
        db.refresh(item)
        return int(item.id)


def _create_tag(client: TestClient, name: str) -> int:
    response = client.post("/api/tags", json={"name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def _create_creator(client: TestClient, name: str) -> int:
    response = client.post("/api/creators", json={"name": name, "type": "artist"})
    assert response.status_code == 201
    return int(response.json()["id"])


def _create_collection(client: TestClient, name: str) -> int:
    response = client.post(
        "/collections",
        data={"name": name, "description": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with SessionLocal() as db:
        collection = db.query(Collection).filter(Collection.name == name).one()
        return int(collection.id)


def _activity(item_id: int) -> ItemActivity | None:
    with SessionLocal() as db:
        activity = (
            db.query(ItemActivity).filter(ItemActivity.item_id == item_id).one_or_none()
        )
        if activity is not None:
            db.expunge(activity)
        return activity


def _activity_count() -> int:
    with SessionLocal() as db:
        return db.query(ItemActivity).count()


def _counts() -> dict[str, int]:
    with SessionLocal() as db:
        return {
            "items": db.query(Item).count(),
            "tags": db.query(Tag).count(),
            "creators": db.query(Creator).count(),
            "collections": db.query(Collection).count(),
            "saved_views": db.query(SavedView).count(),
            "activity": db.query(ItemActivity).count(),
        }


def _base_edit_data(title: str) -> dict[str, str]:
    return {
        "title": title,
        "cover_path": "",
        "summary": "",
        "release_date": "",
        "tags": "",
        "creators": "",
        "extra_json": "",
    }


def test_activity_page_requires_login(client: TestClient) -> None:
    response = client.get("/activity", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_activity_page_renders_empty_state(auth_client: TestClient) -> None:
    response = auth_client.get("/activity")

    assert response.status_code == 200
    assert "最近活动" in response.text
    assert "没有最近访问记录" in response.text
    assert "没有最近编辑记录" in response.text


def test_item_detail_get_is_read_only_and_post_records_repeated_views(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(auth_client, "Viewed Item")

    detail_response = auth_client.get(f"/items/{item_id}")
    assert detail_response.status_code == 200
    assert _activity(item_id) is None
    assert f'fetch("/items/{item_id}/view"' in detail_response.text

    first_response = auth_client.post(f"/items/{item_id}/view")
    second_response = auth_client.post(f"/items/{item_id}/view")

    assert first_response.status_code == 204
    assert second_response.status_code == 204
    activity = _activity(item_id)
    assert activity is not None
    assert activity.last_viewed_at is not None
    assert activity.view_count == 2
    assert activity.edit_count == 0


def test_missing_detail_does_not_create_activity(auth_client: TestClient) -> None:
    auth_client.get("/items/999999", follow_redirects=False)

    assert _activity_count() == 0


def test_unauthenticated_detail_does_not_create_activity(client: TestClient) -> None:
    item_id = _create_item_in_db("Private View")

    response = client.get(f"/items/{item_id}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert _activity_count() == 0


def test_item_base_edit_records_recent_edit_and_repeated_edits(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(auth_client, "Editable Item")

    first_response = auth_client.post(
        f"/items/{item_id}/edit",
        data=_base_edit_data("Editable Item Updated"),
        follow_redirects=False,
    )
    second_response = auth_client.post(
        f"/items/{item_id}/edit",
        data=_base_edit_data("Editable Item Updated Again"),
        follow_redirects=False,
    )

    assert first_response.status_code == 303
    assert second_response.status_code == 303
    activity = _activity(item_id)
    assert activity is not None
    assert activity.last_edited_at is not None
    assert activity.edit_count == 2


def test_state_rating_review_update_records_recent_edit(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(auth_client, "State Activity")

    status_response = auth_client.post(
        f"/items/{item_id}/state",
        data={"status_value": "watching", "rating": "", "review": ""},
        follow_redirects=False,
    )
    rating_response = auth_client.post(
        f"/items/{item_id}/state",
        data={"status_value": "watching", "rating": "5", "review": ""},
        follow_redirects=False,
    )
    review_response = auth_client.post(
        f"/items/{item_id}/state",
        data={"status_value": "watching", "rating": "5", "review": "note"},
        follow_redirects=False,
    )

    assert status_response.status_code == 303
    assert rating_response.status_code == 303
    assert review_response.status_code == 303
    activity = _activity(item_id)
    assert activity is not None
    assert activity.edit_count == 3
    assert activity.last_edited_at is not None


def test_tag_creator_and_collection_changes_record_recent_edit(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(auth_client, "Relation Activity")
    tag_id = _create_tag(auth_client, "activity-tag")
    creator_id = _create_creator(auth_client, "Activity Creator")
    collection_id = _create_collection(auth_client, "Activity Collection")

    responses = [
        auth_client.post(
            f"/items/{item_id}/tags",
            data={"tag_id": str(tag_id)},
            follow_redirects=False,
        ),
        auth_client.post(
            f"/items/{item_id}/creators",
            data={"creator_id": str(creator_id)},
            follow_redirects=False,
        ),
        auth_client.post(
            f"/items/{item_id}/collections",
            data={"collection_id": str(collection_id)},
            follow_redirects=False,
        ),
        auth_client.post(
            f"/items/{item_id}/collections/{collection_id}/delete",
            data={"confirm": "1"},
            follow_redirects=False,
        ),
        auth_client.post(
            f"/items/{item_id}/creators/{creator_id}/delete",
            data={"confirm": "1"},
            follow_redirects=False,
        ),
        auth_client.post(
            f"/items/{item_id}/tags/{tag_id}/delete",
            data={"confirm": "1"},
            follow_redirects=False,
        ),
    ]

    assert all(response.status_code == 303 for response in responses)
    activity = _activity(item_id)
    assert activity is not None
    assert activity.edit_count == 6


def test_collection_detail_item_changes_record_recent_edit(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(auth_client, "Collection Side Activity")
    collection_id = _create_collection(auth_client, "Collection Side")

    add_response = auth_client.post(
        f"/collections/{collection_id}/items",
        data={"item_id": str(item_id)},
        follow_redirects=False,
    )
    remove_response = auth_client.post(
        f"/collections/{collection_id}/items/{item_id}/delete",
        data={"confirm": "1"},
        follow_redirects=False,
    )

    assert add_response.status_code == 303
    assert remove_response.status_code == 303
    activity = _activity(item_id)
    assert activity is not None
    assert activity.edit_count == 2


def test_bulk_edit_records_activity_for_affected_items(
    auth_client: TestClient,
) -> None:
    first_id = _create_item(auth_client, "Bulk Activity One")
    second_id = _create_item(auth_client, "Bulk Activity Two")

    response = auth_client.post(
        "/items/bulk",
        data={
            "bulk_action": "status",
            "item_ids": [str(first_id), str(second_id), "999999"],
            "status_value": "like",
            "next": "/items",
            "confirm": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert _activity(first_id).edit_count == 1
    assert _activity(second_id).edit_count == 1
    assert _activity_count() == 2


def test_activity_page_orders_recent_views_and_edits_desc(
    auth_client: TestClient,
) -> None:
    older_id = _create_item(auth_client, "Older Activity")
    newer_id = _create_item(auth_client, "Newer Activity")
    auth_client.get(f"/items/{older_id}")
    auth_client.get(f"/items/{newer_id}")
    auth_client.post(
        f"/items/{older_id}/state",
        data={"status_value": "wish", "rating": "", "review": ""},
        follow_redirects=False,
    )
    auth_client.post(
        f"/items/{newer_id}/state",
        data={"status_value": "like", "rating": "", "review": ""},
        follow_redirects=False,
    )

    response = auth_client.get("/activity")

    assert response.status_code == 200
    view_section = response.text.split('id="recent-views"', maxsplit=1)[1]
    edit_section = response.text.split('id="recent-edits"', maxsplit=1)[1]
    assert view_section.index("Newer Activity") < view_section.index("Older Activity")
    assert edit_section.index("Newer Activity") < edit_section.index("Older Activity")


def test_clear_activity_requires_login(client: TestClient) -> None:
    response = client.post("/activity/clear", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_clear_activity_requires_post_and_keeps_business_data(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(auth_client, "Clear Activity")
    tag_id = _create_tag(auth_client, "clear-tag")
    creator_id = _create_creator(auth_client, "Clear Creator")
    collection_id = _create_collection(auth_client, "Clear Collection")
    auth_client.post(
        f"/items/{item_id}/tags",
        data={"tag_id": str(tag_id)},
        follow_redirects=False,
    )
    auth_client.post(
        f"/items/{item_id}/creators",
        data={"creator_id": str(creator_id)},
        follow_redirects=False,
    )
    auth_client.post(
        f"/items/{item_id}/collections",
        data={"collection_id": str(collection_id)},
        follow_redirects=False,
    )
    auth_client.post(
        "/saved-views",
        data={"name": "Clear View", "query_string": "state=like"},
        follow_redirects=False,
    )
    before = _counts()
    before_activity = _activity(item_id)
    assert before["activity"] == 1
    assert before_activity is not None
    assert before_activity.edit_count == 3

    get_response = auth_client.get("/activity/clear", follow_redirects=False)
    clear_response = auth_client.post(
        "/activity/clear",
        data={"confirm": "1"},
        follow_redirects=True,
    )

    assert get_response.status_code == 405
    assert clear_response.status_code == 200
    assert "最近活动记录已清空" in clear_response.text
    after = _counts()
    assert after["activity"] == 0
    assert after["items"] == before["items"]
    assert after["tags"] == before["tags"]
    assert after["creators"] == before["creators"]
    assert after["collections"] == before["collections"]
    assert after["saved_views"] == before["saved_views"]


def test_activity_page_i18n_labels(auth_client: TestClient) -> None:
    _create_item(auth_client, "Activity I18n")

    zh_response = auth_client.get("/activity")
    assert zh_response.status_code == 200
    assert "最近活动" in zh_response.text
    assert "最近访问" in zh_response.text
    assert "清空最近活动" in zh_response.text

    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/activity"},
    )
    assert en_response.status_code == 200
    assert "Recent Activity" in en_response.text
    assert "Recent Views" in en_response.text
    assert "Clear Recent Activity" in en_response.text
