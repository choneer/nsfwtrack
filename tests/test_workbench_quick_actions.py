from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import ItemActivity, SavedView


def _create_item(client: TestClient, title: str) -> int:
    response = client.post(
        "/api/items",
        json={"title": title, "tags": [], "creators": []},
    )
    assert response.status_code == 201
    return int(response.json()["id"])


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


def _create_saved_view(
    client: TestClient,
    *,
    name: str = "High Rating",
    query_string: str = "min_rating=4",
) -> int:
    response = client.post(
        "/saved-views",
        data={"name": name, "query_string": query_string},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with SessionLocal() as db:
        saved_view = db.query(SavedView).filter(SavedView.name == name).one()
        return int(saved_view.id)


def _activity_count() -> int:
    with SessionLocal() as db:
        return db.query(ItemActivity).count()


def _section(html: str, element_id: str) -> str:
    start = html.index(f'id="{element_id}"')
    end = html.index("</section>", start)
    return html[start:end]


def _assert_navigation_only(section: str) -> None:
    assert "<form" not in section
    assert 'method="post"' not in section
    assert "data-confirm-message" not in section
    assert "/duplicates/merge" not in section
    assert "/cleanup/merge" not in section
    assert "/activity/clear" not in section


def test_dashboard_requires_login_for_workbench(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_dashboard_renders_workbench_quick_actions_without_writes(
    auth_client: TestClient,
) -> None:
    response = auth_client.get("/")

    assert response.status_code == 200
    assert "工作台" in response.text
    assert "常用入口" in response.text
    for href in (
        "/items/new",
        "/items",
        "/items#saved-views",
        "/activity",
        "/stats",
        "/collections",
        "/duplicates",
        "/cleanup",
        "/import",
        "/backup",
    ):
        assert f'href="{href}"' in response.text
    assert "暂无已保存视图" in response.text
    assert "没有最近访问记录" in response.text
    assert "没有最近编辑记录" in response.text
    _assert_navigation_only(_section(response.text, "workbench"))
    assert _activity_count() == 0


def test_dashboard_shows_recent_activity_and_saved_view_entries(
    auth_client: TestClient,
) -> None:
    item_id = _create_item(auth_client, "Workbench Item")
    saved_view_id = _create_saved_view(auth_client, name="Workbench View")

    view_response = auth_client.get(f"/items/{item_id}")
    edit_response = auth_client.post(
        f"/items/{item_id}/edit",
        data=_base_edit_data("Workbench Item Updated"),
        follow_redirects=False,
    )
    dashboard_response = auth_client.get("/")

    assert view_response.status_code == 200
    assert edit_response.status_code == 303
    assert dashboard_response.status_code == 200
    assert "Workbench Item Updated" in dashboard_response.text
    assert "Workbench View" in dashboard_response.text
    assert f'href="/saved-views/{saved_view_id}/apply"' in dashboard_response.text
    assert 'href="/activity#recent-views"' in dashboard_response.text
    assert 'href="/activity#recent-edits"' in dashboard_response.text


def test_items_page_quick_actions_preserve_filters_and_saved_views(
    auth_client: TestClient,
) -> None:
    _create_item(auth_client, "Blue Workbench")
    _create_item(auth_client, "Red Workbench")
    _create_saved_view(auth_client, name="Blue View", query_string="q=Blue")

    response = auth_client.get("/items", params={"q": "Blue"})

    assert response.status_code == 200
    assert "Blue Workbench" in response.text
    assert "Red Workbench" not in response.text
    assert "快捷操作" in response.text
    for href in (
        "/items/new",
        "#saved-views",
        "/activity",
        "/duplicates",
        "/cleanup",
        "/import",
        "/backup",
    ):
        assert f'href="{href}"' in response.text
    assert "保存当前视图" in response.text
    assert "常用视图" in response.text
    assert "Blue View" in response.text
    assert 'name="query_string" value="q=Blue"' in response.text
    _assert_navigation_only(_section(response.text, "item-list-quick-actions"))


def test_workbench_quick_actions_render_in_english(
    auth_client: TestClient,
) -> None:
    dashboard_response = auth_client.get(
        "/set-language",
        params={"lang": "en", "next": "/"},
    )
    items_response = auth_client.get("/items")

    assert dashboard_response.status_code == 200
    assert "Workbench" in dashboard_response.text
    assert "Common Entries" in dashboard_response.text
    assert "Import Data" in dashboard_response.text
    assert "Backup Data" in dashboard_response.text
    assert items_response.status_code == 200
    assert "Quick Actions" in items_response.text
    assert "Save Current View" in items_response.text
