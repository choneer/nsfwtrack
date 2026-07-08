from __future__ import annotations

from fastapi.testclient import TestClient


def _create_responsive_item(client: TestClient) -> int:
    response = client.post(
        "/api/items",
        json={
            "title": "Responsive Layout Item With A Very Long Local Title",
            "summary": "Local summary for responsive layout checks.",
            "tags": ["long-responsive-tag-name"],
            "creators": ["Long Responsive Creator Name"],
            "extra": {"layout": "mobile"},
        },
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def test_base_navigation_and_dashboard_use_responsive_containers(
    auth_client: TestClient,
) -> None:
    response = auth_client.get("/")

    assert response.status_code == 200
    assert 'class="nav"' in response.text
    assert 'class="language-switch"' in response.text
    assert 'class="nav-links"' in response.text
    assert 'class="toolbar"' in response.text
    assert 'class="item-grid"' in response.text


def test_item_list_uses_mobile_friendly_filter_bulk_and_card_regions(
    auth_client: TestClient,
) -> None:
    _create_responsive_item(auth_client)

    response = auth_client.get("/items")

    assert response.status_code == 200
    assert 'class="card form-grid filter-panel"' in response.text
    assert 'class="filter-actions"' in response.text
    assert 'class="card bulk-panel"' in response.text
    assert 'class="bulk-card-select"' in response.text
    assert 'class="item-grid"' in response.text
    assert 'class="pagination"' in response.text


def test_detail_page_uses_responsive_detail_and_relation_regions(
    auth_client: TestClient,
) -> None:
    item_id = _create_responsive_item(auth_client)

    response = auth_client.get(f"/items/{item_id}")

    assert response.status_code == 200
    assert 'class="detail-layout"' in response.text
    assert 'class="detail-overview"' in response.text
    assert 'class="json-block"' in response.text
    assert 'class="relation-list"' in response.text
    assert 'class="relation-form"' in response.text
    assert 'class="card detail-section detail-actions-panel"' in response.text


def test_import_preview_keeps_tables_and_metrics_inside_responsive_regions(
    auth_client: TestClient,
) -> None:
    csv_content = (
        b"custom_title,custom_tags\n"
        b"Responsive Import Item,responsive-import-tag\n"
    )

    response = auth_client.post(
        "/import/csv",
        files={"file": ("items.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    assert 'class="metric-grid"' in response.text
    assert 'class="table-scroll"' in response.text
    assert 'name="target_field"' in response.text
    assert "Responsive Import Item" in response.text


def test_backup_stats_tags_and_creators_pages_use_responsive_tables(
    auth_client: TestClient,
) -> None:
    backup_response = auth_client.get("/backup")
    assert backup_response.status_code == 200
    assert 'class="grid"' in backup_response.text
    assert 'enctype="multipart/form-data"' in backup_response.text

    stats_response = auth_client.get("/stats")
    assert stats_response.status_code == 200
    assert 'class="stats-section"' in stats_response.text
    assert 'class="metric-grid"' in stats_response.text
    assert "统计总览" in stats_response.text
    assert "没有状态数据。" in stats_response.text

    tags_response = auth_client.get("/tags")
    assert tags_response.status_code == 200
    assert 'class="card form-grid"' in tags_response.text
    assert 'class="table-scroll"' in tags_response.text

    creators_response = auth_client.get("/creators")
    assert creators_response.status_code == 200
    assert 'class="card form-grid"' in creators_response.text
    assert 'class="table-scroll"' in creators_response.text
