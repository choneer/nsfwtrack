from __future__ import annotations

from sqlalchemy import inspect, select

from app.database import SessionLocal, engine
from app.models import SchemaMigration
from app.services.schema_version import CURRENT_SCHEMA_VERSION


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
        "item_activity",
        "app_settings",
        "schema_migrations",
    }.issubset(tables)


def test_current_schema_version_is_registered() -> None:
    with SessionLocal() as db:
        migrations = db.scalars(select(SchemaMigration)).all()

    assert len(migrations) == 1
    assert migrations[0].version == CURRENT_SCHEMA_VERSION
    assert migrations[0].name == "baseline"
    assert migrations[0].applied_at is not None
