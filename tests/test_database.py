from __future__ import annotations

from sqlalchemy import inspect

from app.database import engine


def test_expected_tables_exist() -> None:
    tables = set(inspect(engine).get_table_names())

    assert {
        "items",
        "creators",
        "tags",
        "item_tags",
        "item_creators",
        "user_item_states",
        "collections",
        "item_collections",
        "saved_views",
    }.issubset(tables)
