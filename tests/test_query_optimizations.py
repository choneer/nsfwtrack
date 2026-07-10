from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.database import SessionLocal, engine
from app.models import Collection, Creator, Item, ItemCollection, SavedView, Tag
from app.services.data_health import DATA_HEALTH_DETAIL_LIMIT, build_data_health_report
from app.services.data_health_fixes import build_data_health_fix_options


def _add_metadata_rows() -> None:
    with SessionLocal() as db:
        db.add_all(Tag(name=f"Paged Tag {index:03d}") for index in range(55))
        db.add_all(
            Creator(name=f"Paged Creator {index:03d}", type="other")
            for index in range(55)
        )
        db.add_all(
            Collection(name=f"Paged Collection {index:03d}")
            for index in range(55)
        )
        db.commit()


def test_metadata_lists_paginate_without_hiding_later_rows(
    auth_client: TestClient,
) -> None:
    _add_metadata_rows()

    cases = (
        ("/tags", "Paged Tag 000", "Paged Tag 054"),
        ("/creators", "Paged Creator 000", "Paged Creator 054"),
        ("/collections", "Paged Collection 000", "Paged Collection 054"),
    )
    for path, first_name, last_name in cases:
        first_page = auth_client.get(path)
        second_page = auth_client.get(path, params={"page": "2"})
        assert first_page.status_code == 200
        assert first_name in first_page.text
        assert last_name not in first_page.text
        assert f'{path}?page=2' in first_page.text
        assert second_page.status_code == 200
        assert last_name in second_page.text
        assert first_name not in second_page.text


def test_collection_detail_paginates_members_and_searches_available_items(
    auth_client: TestClient,
) -> None:
    with SessionLocal() as db:
        collection = Collection(name="Paged Detail Collection")
        members = [Item(title=f"Member {index:03d}") for index in range(25)]
        available = [Item(title=f"Available {index:03d}") for index in range(30)]
        db.add_all([collection, *members, *available])
        db.flush()
        db.add_all(
            ItemCollection(item_id=item.id, collection_id=collection.id)
            for item in members
        )
        db.commit()
        collection_id = int(collection.id)

    first_page = auth_client.get(f"/collections/{collection_id}")
    second_page = auth_client.get(
        f"/collections/{collection_id}", params={"item_page": "2"}
    )
    searched = auth_client.get(
        f"/collections/{collection_id}", params={"available_q": "Available 024"}
    )

    assert first_page.status_code == 200
    assert "Member 000" in first_page.text
    assert "Member 024" not in first_page.text
    assert "Available 000" in first_page.text
    assert "Available 024" not in first_page.text
    assert second_page.status_code == 200
    assert "Member 024" in second_page.text
    assert searched.status_code == 200
    assert "Available 024" in searched.text
    assert "Available 000" not in searched.text
    assert "<strong>25</strong>" in first_page.text


def test_duplicate_and_cleanup_candidates_paginate_all_comparison_pairs(
    auth_client: TestClient,
) -> None:
    with SessionLocal() as db:
        for index in range(25):
            db.add(Item(title=f"Duplicate Pair {index:03d}"))
            db.add(Item(title=f"  Duplicate Pair {index:03d}  "))
            db.add(Tag(name=f"Cleanup Pair {index:03d}"))
            db.add(Tag(name=f" Cleanup Pair {index:03d} "))
        db.commit()

    duplicate_first = auth_client.get("/duplicates")
    duplicate_second = auth_client.get("/duplicates", params={"page": "2"})
    cleanup_first = auth_client.get("/cleanup")
    cleanup_second = auth_client.get("/cleanup", params={"page": "2"})

    assert "Duplicate Pair 000" in duplicate_first.text
    assert "Duplicate Pair 024" not in duplicate_first.text
    assert "Duplicate Pair 024" in duplicate_second.text
    assert "/duplicates?page=2" in duplicate_first.text
    assert "Cleanup Pair 000" in cleanup_first.text
    assert "Cleanup Pair 024" not in cleanup_first.text
    assert "Cleanup Pair 024" in cleanup_second.text
    assert "/cleanup?page=2" in cleanup_first.text


def test_data_health_keeps_total_when_details_are_truncated() -> None:
    with SessionLocal() as db:
        db.add_all(
            SavedView(name=f"Unsafe view {index}", query_string="page=1")
            for index in range(DATA_HEALTH_DETAIL_LIMIT + 5)
        )
        db.commit()
        report = build_data_health_report(db)

    assert report.total_issues == DATA_HEALTH_DETAIL_LIMIT + 5
    assert report.displayed_issue_count == DATA_HEALTH_DETAIL_LIMIT
    assert len(report.issues) == DATA_HEALTH_DETAIL_LIMIT
    assert report.details_truncated is True
    fix_options = build_data_health_fix_options(report)
    saved_view_fix = next(
        option for option in fix_options if option.fix_type == "saved_view_blocked_params"
    )
    assert saved_view_fix.issue_count == DATA_HEALTH_DETAIL_LIMIT + 5


@pytest.fixture
def settings_query_recorder() -> Generator[list[str], None, None]:
    statements: list[str] = []

    def record(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        if "FROM app_settings" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_items_request_reads_settings_once(
    auth_client: TestClient,
    settings_query_recorder: list[str],
) -> None:
    with SessionLocal() as db:
        db.add(Item(title="Settings query item"))
        db.commit()

    response = auth_client.get("/items")

    assert response.status_code == 200
    assert "Settings query item" in response.text
    assert len(settings_query_recorder) == 1


def test_collection_membership_is_unchanged_by_paginated_reads(
    auth_client: TestClient,
) -> None:
    with SessionLocal() as db:
        collection = Collection(name="Read only pagination")
        items = [Item(title=f"Read only {index:03d}") for index in range(30)]
        db.add_all([collection, *items])
        db.flush()
        db.add_all(
            ItemCollection(item_id=item.id, collection_id=collection.id)
            for item in items
        )
        db.commit()
        collection_id = int(collection.id)

    auth_client.get(f"/collections/{collection_id}", params={"item_page": "2"})

    with SessionLocal() as db:
        relation_count = len(
            db.scalars(
                select(ItemCollection).where(
                    ItemCollection.collection_id == collection_id
                )
            ).all()
        )
    assert relation_count == 30
