from __future__ import annotations

from fastapi.testclient import TestClient


def _create_item(
    client: TestClient,
    title: str,
    *,
    summary: str | None = None,
    tags: list[str] | None = None,
    creators: list[str] | None = None,
    extra: dict[str, object] | None = None,
    status: str | None = None,
    rating: int | None = None,
    review: str | None = None,
) -> int:
    payload: dict[str, object] = {
        "title": title,
        "tags": tags or [],
        "creators": creators or [],
    }
    if summary is not None:
        payload["summary"] = summary
    if extra is not None:
        payload["extra"] = extra
    create_response = client.post("/api/items", json=payload)
    assert create_response.status_code == 201
    item_id = int(create_response.json()["id"])
    if status:
        state_payload: dict[str, object] = {"status": status}
        if rating is not None:
            state_payload["rating"] = rating
        if review is not None:
            state_payload["review"] = review
        state_response = client.post(f"/api/items/{item_id}/state", json=state_payload)
        assert state_response.status_code == 201
    return item_id


def _create_tag(client: TestClient, name: str) -> int:
    response = client.post("/api/tags", json={"name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def _create_creator(client: TestClient, name: str) -> int:
    response = client.post("/api/creators", json={"name": name, "type": "artist"})
    assert response.status_code == 201
    return int(response.json()["id"])


def _item(client: TestClient, item_id: int) -> dict[str, object]:
    response = client.get(f"/api/items/{item_id}")
    assert response.status_code == 200
    return response.json()


def _tag_names(client: TestClient, item_id: int) -> list[str]:
    return [tag["name"] for tag in _item(client, item_id)["tags"]]


def _creator_names(client: TestClient, item_id: int) -> list[str]:
    return [creator["name"] for creator in _item(client, item_id)["creators"]]


def test_item_detail_requires_login(client: TestClient) -> None:
    response = client.get("/items/1", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_item_detail_renders_sections_relations_state_and_extra(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(
        auth_client,
        "Detail Item",
        summary="Local detail summary",
        tags=["detail-tag"],
        creators=["Detail Creator"],
        extra={"source": "manual"},
        status="like",
        rating=5,
        review="Tiny note",
    )

    response = auth_client.get(f"/items/{item_id}")

    assert response.status_code == 200
    assert "条目详情" in response.text
    assert "基本信息" in response.text
    assert "状态信息" in response.text
    assert "标签信息" in response.text
    assert "创作者信息" in response.text
    assert "Detail Item" in response.text
    assert "Local detail summary" in response.text
    assert "detail-tag" in response.text
    assert "Detail Creator" in response.text
    assert "喜欢" in response.text
    assert "评分 5" in response.text
    assert "Tiny note" in response.text
    assert "extra JSON" in response.text
    assert "manual" in response.text


def test_item_detail_updates_state_rating_review_and_creates_missing_state(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(auth_client, "State Create")
    assert _item(auth_client, item_id)["state"] is None

    response = auth_client.post(
        f"/items/{item_id}/state",
        data={"status_value": "watching", "rating": "4", "review": "  first note  "},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "状态已更新" in response.text
    state = _item(auth_client, item_id)["state"]
    assert state["status"] == "watching"
    assert state["rating"] == 4
    assert state["review"] == "first note"

    clear_response = auth_client.post(
        f"/items/{item_id}/state",
        data={"status_value": "watched", "rating": "", "review": ""},
        follow_redirects=True,
    )

    assert clear_response.status_code == 200
    state = _item(auth_client, item_id)["state"]
    assert state["status"] == "watched"
    assert state["rating"] is None
    assert state["review"] is None


def test_item_detail_rejects_invalid_status_and_rating(auth_client: TestClient) -> None:
    item_id = _create_item(
        auth_client,
        "Invalid State",
        status="wish",
        rating=2,
        review="keep",
    )

    invalid_status_response = auth_client.post(
        f"/items/{item_id}/state",
        data={"status_value": "bad", "rating": "3", "review": "changed"},
        follow_redirects=True,
    )

    assert invalid_status_response.status_code == 200
    assert "状态值无效" in invalid_status_response.text
    state = _item(auth_client, item_id)["state"]
    assert state["status"] == "wish"
    assert state["rating"] == 2
    assert state["review"] == "keep"

    invalid_rating_response = auth_client.post(
        f"/items/{item_id}/state",
        data={"status_value": "like", "rating": "9", "review": "changed"},
        follow_redirects=True,
    )

    assert invalid_rating_response.status_code == 200
    assert "评分值无效" in invalid_rating_response.text
    state = _item(auth_client, item_id)["state"]
    assert state["status"] == "wish"
    assert state["rating"] == 2
    assert state["review"] == "keep"


def test_item_detail_adds_and_removes_existing_tag(auth_client: TestClient) -> None:
    item_id = _create_item(auth_client, "Tag Detail", tags=["keep-tag"])
    tag_id = _create_tag(auth_client, "detail-add-tag")

    add_response = auth_client.post(
        f"/items/{item_id}/tags",
        data={"tag_id": str(tag_id)},
        follow_redirects=True,
    )

    assert add_response.status_code == 200
    assert "标签已添加" in add_response.text
    assert "detail-add-tag" in _tag_names(auth_client, item_id)

    duplicate_response = auth_client.post(
        f"/items/{item_id}/tags",
        data={"tag_id": str(tag_id)},
        follow_redirects=True,
    )
    assert duplicate_response.status_code == 200
    assert "重复关联" in duplicate_response.text
    assert _tag_names(auth_client, item_id).count("detail-add-tag") == 1

    missing_response = auth_client.post(
        f"/items/{item_id}/tags",
        data={"tag_id": "999999"},
        follow_redirects=True,
    )
    assert missing_response.status_code == 200
    assert "标签不存在" in missing_response.text

    remove_response = auth_client.post(
        f"/items/{item_id}/tags/{tag_id}/delete",
        follow_redirects=True,
    )

    assert remove_response.status_code == 200
    assert "标签已移除" in remove_response.text
    assert "detail-add-tag" not in _tag_names(auth_client, item_id)
    assert "keep-tag" in _tag_names(auth_client, item_id)


def test_item_detail_adds_and_removes_existing_creator(auth_client: TestClient) -> None:
    item_id = _create_item(auth_client, "Creator Detail", creators=["Keep Creator"])
    creator_id = _create_creator(auth_client, "Detail Add Creator")

    add_response = auth_client.post(
        f"/items/{item_id}/creators",
        data={"creator_id": str(creator_id)},
        follow_redirects=True,
    )

    assert add_response.status_code == 200
    assert "创作者已添加" in add_response.text
    assert "Detail Add Creator" in _creator_names(auth_client, item_id)

    duplicate_response = auth_client.post(
        f"/items/{item_id}/creators",
        data={"creator_id": str(creator_id)},
        follow_redirects=True,
    )
    assert duplicate_response.status_code == 200
    assert "重复关联" in duplicate_response.text
    assert _creator_names(auth_client, item_id).count("Detail Add Creator") == 1

    missing_response = auth_client.post(
        f"/items/{item_id}/creators",
        data={"creator_id": "999999"},
        follow_redirects=True,
    )
    assert missing_response.status_code == 200
    assert "创作者不存在" in missing_response.text

    remove_response = auth_client.post(
        f"/items/{item_id}/creators/{creator_id}/delete",
        follow_redirects=True,
    )

    assert remove_response.status_code == 200
    assert "创作者已解除" in remove_response.text
    assert "Detail Add Creator" not in _creator_names(auth_client, item_id)
    assert "Keep Creator" in _creator_names(auth_client, item_id)


def test_item_detail_preserves_safe_next_and_rejects_open_redirect(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(auth_client, "Context Item", status="wish")
    list_url = "/items?q=Context&state=wish&sort=title_desc&page=1&page_size=50"

    list_response = auth_client.get(list_url)
    assert list_response.status_code == 200
    assert f"/items/{item_id}?next=/items%3Fq%3DContext" in list_response.text
    assert "sort%3Dtitle_desc" in list_response.text
    assert "page%3D1" in list_response.text
    assert "page_size%3D50" in list_response.text

    detail_next = "/items?q=Context&state=wish&sort=title_desc&page=2&page_size=50"
    detail_response = auth_client.get(f"/items/{item_id}", params={"next": detail_next})
    assert detail_response.status_code == 200
    assert 'href="/items?q=Context&amp;state=wish&amp;sort=title_desc&amp;page=2&amp;page_size=50"' in detail_response.text
    assert 'name="next" value="/items?q=Context&amp;state=wish&amp;sort=title_desc&amp;page=2&amp;page_size=50"' in detail_response.text

    unsafe_response = auth_client.post(
        f"/items/{item_id}/state",
        data={"status_value": "like", "next": "//evil.example/items"},
        follow_redirects=False,
    )

    assert unsafe_response.status_code == 303
    assert unsafe_response.headers["location"] == f"/items/{item_id}"


def test_item_detail_i18n_labels(auth_client: TestClient) -> None:
    item_id = _create_item(auth_client, "Bilingual Detail")

    zh_response = auth_client.get(f"/items/{item_id}")
    assert zh_response.status_code == 200
    assert "条目详情" in zh_response.text
    assert "返回列表" in zh_response.text
    assert "保存评分" in zh_response.text
    assert "没有关联标签。" in zh_response.text
    assert "没有关联创作者。" in zh_response.text

    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": f"/items/{item_id}"},
    )
    assert en_response.status_code == 200
    assert "Item Detail" in en_response.text
    assert "Back to List" in en_response.text
    assert "Save Rating" in en_response.text
    assert "No linked tags." in en_response.text
    assert "No linked creators." in en_response.text
