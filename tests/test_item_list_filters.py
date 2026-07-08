from __future__ import annotations

from fastapi.testclient import TestClient


def _create_item(
    client: TestClient,
    title: str,
    *,
    tags: list[str],
    creators: list[str],
    status: str,
    rating: int | None = None,
) -> int:
    create_response = client.post(
        "/api/items",
        json={"title": title, "tags": tags, "creators": creators},
    )
    assert create_response.status_code == 201
    item_id = int(create_response.json()["id"])
    state_payload: dict[str, object] = {"status": status}
    if rating is not None:
        state_payload["rating"] = rating
    state_response = client.post(f"/api/items/{item_id}/state", json=state_payload)
    assert state_response.status_code == 201
    return item_id


def _seed_items(client: TestClient) -> None:
    _create_item(
        client,
        "Blue Archive",
        tags=["game"],
        creators=["Alice"],
        status="wish",
        rating=5,
    )
    _create_item(
        client,
        "Quiet Sketch",
        tags=["art"],
        creators=["Bob"],
        status="watched",
        rating=2,
    )
    _create_item(
        client,
        "Silver Note",
        tags=["game"],
        creators=["Bob"],
        status="like",
        rating=4,
    )


def _title_index(html: str, title: str) -> int:
    return html.index(f"<h3>{title}</h3>")


def test_items_page_requires_login(client: TestClient) -> None:
    response = client.get("/items", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_items_page_renders_default_advanced_filters(auth_client: TestClient) -> None:
    _seed_items(auth_client)

    response = auth_client.get("/items")

    assert response.status_code == 200
    assert "高级筛选" in response.text
    assert "全部条目" in response.text
    assert "最近更新" in response.text
    assert "Blue Archive" in response.text
    assert "Quiet Sketch" in response.text
    assert "Silver Note" in response.text


def test_items_page_filters_by_keyword_state_tag_creator_rating_and_time_range(
    auth_client: TestClient,
) -> None:
    _seed_items(auth_client)

    keyword_response = auth_client.get("/items", params={"q": "Blue"})
    assert keyword_response.status_code == 200
    assert "Blue Archive" in keyword_response.text
    assert "Quiet Sketch" not in keyword_response.text

    state_response = auth_client.get("/items", params={"state": "wish"})
    assert state_response.status_code == 200
    assert "Blue Archive" in state_response.text
    assert "Silver Note" not in state_response.text

    tag_response = auth_client.get("/items", params={"tag": "art"})
    assert tag_response.status_code == 200
    assert "Quiet Sketch" in tag_response.text
    assert "Blue Archive" not in tag_response.text

    creator_response = auth_client.get("/items", params={"creator": "Bob"})
    assert creator_response.status_code == 200
    assert "Quiet Sketch" in creator_response.text
    assert "Silver Note" in creator_response.text
    assert "Blue Archive" not in creator_response.text

    rating_response = auth_client.get("/items", params={"min_rating": "4"})
    assert rating_response.status_code == 200
    assert "Blue Archive" in rating_response.text
    assert "Silver Note" in rating_response.text
    assert "Quiet Sketch" not in rating_response.text

    time_response = auth_client.get(
        "/items",
        params={"time_range": "7d", "date_field": "created"},
    )
    assert time_response.status_code == 200
    assert "最近 7 天" in time_response.text


def test_items_page_sorting_and_page_size(auth_client: TestClient) -> None:
    _seed_items(auth_client)

    title_response = auth_client.get("/items", params={"sort": "title_asc"})
    assert title_response.status_code == 200
    assert _title_index(title_response.text, "Blue Archive") < _title_index(
        title_response.text, "Quiet Sketch"
    )
    assert _title_index(title_response.text, "Quiet Sketch") < _title_index(
        title_response.text, "Silver Note"
    )

    rating_response = auth_client.get("/items", params={"sort": "rating_desc"})
    assert rating_response.status_code == 200
    assert _title_index(rating_response.text, "Blue Archive") < _title_index(
        rating_response.text, "Silver Note"
    )
    assert _title_index(rating_response.text, "Silver Note") < _title_index(
        rating_response.text, "Quiet Sketch"
    )

    for index in range(9):
        _create_item(
            auth_client,
            f"Extra Item {index + 1:02d}",
            tags=["extra"],
            creators=["Extra Creator"],
            status="watching",
        )

    page_response = auth_client.get(
        "/items",
        params={"page_size": "10", "sort": "title_asc"},
    )
    assert page_response.status_code == 200
    assert page_response.text.count("<article class=\"card\">") == 10
    assert "显示 1-10 / 12" in page_response.text

    second_page_response = auth_client.get(
        "/items",
        params={"page": "2", "page_size": "10", "sort": "title_asc"},
    )
    assert second_page_response.status_code == 200
    assert second_page_response.text.count("<article class=\"card\">") == 2
    assert "显示 11-12 / 12" in second_page_response.text


def test_items_page_invalid_page_params_fall_back_safely(
    auth_client: TestClient,
) -> None:
    _seed_items(auth_client)

    response = auth_client.get(
        "/items",
        params={
            "page": "abc",
            "page_size": "999",
            "min_rating": "nope",
            "sort": "bad",
            "time_range": "future",
            "date_field": "bad",
        },
    )

    assert response.status_code == 200
    assert "显示 1-3 / 3" in response.text
    assert "最近更新" in response.text


def test_items_page_preserves_filter_form_state(auth_client: TestClient) -> None:
    _seed_items(auth_client)

    response = auth_client.get(
        "/items",
        params={
            "q": "Blue",
            "tag": "game",
            "creator": "Alice",
            "state": "wish",
            "min_rating": "5",
            "time_range": "30d",
            "date_field": "created",
            "sort": "title_desc",
            "page_size": "50",
        },
    )

    assert response.status_code == 200
    assert 'name="q" value="Blue"' in response.text
    assert '<option value="wish" selected>' in response.text
    assert '<option value="game" selected>' in response.text
    assert '<option value="Alice" selected>' in response.text
    assert '<option value="5" selected>' in response.text
    assert '<option value="30d" selected>' in response.text
    assert '<option value="created" selected>' in response.text
    assert '<option value="title_desc" selected>' in response.text
    assert '<option value="50" selected>' in response.text


def test_items_page_empty_state_and_i18n_labels(auth_client: TestClient) -> None:
    _seed_items(auth_client)

    zh_response = auth_client.get("/items", params={"q": "No Match"})
    assert zh_response.status_code == 200
    assert "没有匹配的条目。" in zh_response.text
    assert "清空筛选" in zh_response.text
    assert "应用筛选" in zh_response.text

    en_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/items?q=No%20Match"},
    )
    assert en_response.status_code == 200
    assert "Advanced filters" in en_response.text
    assert "No matching items." in en_response.text
    assert "Clear Filters" in en_response.text
    assert "Apply Filters" in en_response.text
