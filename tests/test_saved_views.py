from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import SavedView


def _saved_views() -> list[SavedView]:
    with SessionLocal() as db:
        return list(db.query(SavedView).order_by(SavedView.id.asc()).all())


def _saved_view_count() -> int:
    with SessionLocal() as db:
        return db.query(SavedView).count()


def _create_saved_view(
    client: TestClient,
    *,
    name: str = "High Rating",
    query_string: str = "q=Blue&min_rating=4&sort=rating_desc&page=3&unknown=1",
) -> SavedView:
    response = client.post(
        "/saved-views",
        data={"name": name, "query_string": query_string},
        follow_redirects=False,
    )
    assert response.status_code == 303
    views = _saved_views()
    assert len(views) == 1
    return views[0]


def test_saved_view_create_requires_login(client: TestClient) -> None:
    response = client.post(
        "/saved-views",
        data={"name": "Needs Login", "query_string": "state=wish"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_saved_view_create_saves_allowed_filters(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/saved-views",
        data={
            "name": "High Rating",
            "query_string": (
                "q=Blue&tag=game&creator=Alice&collection=3&state=wish"
                "&min_rating=4&time_range=30d&date_field=created"
                "&sort=rating_desc&page_size=50&page=9&unknown=1"
            ),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/items?q=Blue&tag=game&creator=Alice&collection=3&state=wish"
        "&min_rating=4&time_range=30d&date_field=created"
        "&sort=rating_desc&page_size=50"
    )
    [view] = _saved_views()
    assert view.name == "High Rating"
    assert view.query_string == (
        "q=Blue&tag=game&creator=Alice&collection=3&state=wish"
        "&min_rating=4&time_range=30d&date_field=created"
        "&sort=rating_desc&page_size=50"
    )
    assert "page=" not in view.query_string
    assert "unknown" not in view.query_string


def test_saved_view_create_rejects_empty_duplicate_and_long_names(
    auth_client: TestClient,
) -> None:
    empty_response = auth_client.post(
        "/saved-views",
        data={"name": "   ", "query_string": "q=Blue"},
        follow_redirects=True,
    )
    assert empty_response.status_code == 200
    assert "视图名称不能为空" in empty_response.text
    assert _saved_view_count() == 0

    _create_saved_view(auth_client, name="High Rating", query_string="min_rating=4")
    duplicate_response = auth_client.post(
        "/saved-views",
        data={"name": " high rating ", "query_string": "state=wish"},
        follow_redirects=True,
    )
    assert duplicate_response.status_code == 200
    assert "视图名称已存在" in duplicate_response.text
    assert _saved_view_count() == 1

    long_response = auth_client.post(
        "/saved-views",
        data={"name": "x" * 81, "query_string": "state=wish"},
        follow_redirects=True,
    )
    assert long_response.status_code == 200
    assert "视图名称过长" in long_response.text
    assert _saved_view_count() == 1


def test_saved_view_ignores_external_url_and_dangerous_params(
    auth_client: TestClient,
) -> None:
    _create_saved_view(
        auth_client,
        name="Safe Local View",
        query_string=(
            "https://example.invalid/items?page=9&state=wish"
            "&redirect=https://evil.example&next=//evil.example"
        ),
    )

    [view] = _saved_views()
    assert view.query_string == "state=wish"
    apply_response = auth_client.get(
        f"/saved-views/{view.id}/apply",
        follow_redirects=False,
    )
    assert apply_response.headers["location"] == "/items?state=wish"


def test_saved_view_apply_redirects_to_items_without_modifying_database(
    auth_client: TestClient,
) -> None:
    view = _create_saved_view(
        auth_client,
        name="Wish List",
        query_string="state=wish&page=4&sort=title_asc",
    )
    before = [(row.id, row.name, row.query_string, row.updated_at) for row in _saved_views()]

    response = auth_client.get(
        f"/saved-views/{view.id}/apply",
        follow_redirects=False,
    )
    after = [(row.id, row.name, row.query_string, row.updated_at) for row in _saved_views()]

    assert response.status_code == 303
    assert response.headers["location"] == "/items?state=wish&sort=title_asc"
    assert after == before


def test_saved_view_invalid_id_does_not_500(auth_client: TestClient) -> None:
    response = auth_client.get("/saved-views/999/apply", follow_redirects=True)

    assert response.status_code == 200
    assert "视图不存在" in response.text


def test_saved_view_update_changes_current_query(auth_client: TestClient) -> None:
    view = _create_saved_view(auth_client, name="Daily", query_string="state=wish")

    response = auth_client.post(
        f"/saved-views/{view.id}/update",
        data={"query_string": "q=Blue&page=2&sort=title_desc&bad=1"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/items?q=Blue&sort=title_desc"
    [updated] = _saved_views()
    assert updated.query_string == "q=Blue&sort=title_desc"


def test_saved_view_delete_requires_post_and_removes_view(
    auth_client: TestClient,
) -> None:
    view = _create_saved_view(auth_client, name="Delete Me", query_string="state=wish")

    get_response = auth_client.get(
        f"/saved-views/{view.id}/delete",
        follow_redirects=False,
    )
    assert get_response.status_code == 405
    assert _saved_view_count() == 1

    delete_response = auth_client.post(
        f"/saved-views/{view.id}/delete",
        data={"query_string": "state=wish", "confirm": "1"},
        follow_redirects=False,
    )

    assert delete_response.status_code == 303
    assert delete_response.headers["location"] == "/items?state=wish"
    assert _saved_view_count() == 0
    missing_response = auth_client.get(
        f"/saved-views/{view.id}/apply",
        follow_redirects=True,
    )
    assert missing_response.status_code == 200
    assert "视图不存在" in missing_response.text


def test_items_page_displays_saved_views(auth_client: TestClient) -> None:
    _create_saved_view(auth_client, name="High Rating", query_string="min_rating=4")

    response = auth_client.get("/items", params={"state": "wish"})

    assert response.status_code == 200
    assert "常用视图" in response.text
    assert "保存当前视图" in response.text
    assert "已保存视图" in response.text
    assert "High Rating" in response.text
    assert "min_rating=4" in response.text
    assert "应用视图" in response.text
    assert "更新视图" in response.text
    assert "删除视图" in response.text
    assert "当前筛选条件" in response.text
    assert 'name="query_string" value="state=wish"' in response.text


def test_items_page_displays_saved_views_in_english(auth_client: TestClient) -> None:
    _create_saved_view(auth_client, name="High Rating", query_string="min_rating=4")

    response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/items"},
    )

    assert response.status_code == 200
    assert "Saved Views" in response.text
    assert "Save Current View" in response.text
    assert "Apply View" in response.text
    assert "Update View" in response.text
    assert "Delete View" in response.text
    assert "Current filters" in response.text
