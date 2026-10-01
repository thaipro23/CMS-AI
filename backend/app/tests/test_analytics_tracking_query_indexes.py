from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import SimpleNamespace


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0069_analytics_tracking_query_indexes.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_0069_analytics_tracking_query_indexes",
        MIGRATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load migration at {MIGRATION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CapturingOperations:
    def __init__(self) -> None:
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        self.autocommit_entries = 0
        self.autocommit_active = False
        self.created: list[dict[str, object]] = []
        self.dropped: list[dict[str, object]] = []

    def get_bind(self):
        return self.bind

    def get_context(self):
        operations = self

        class Context:
            @contextmanager
            def autocommit_block(self):
                operations.autocommit_entries += 1
                operations.autocommit_active = True
                try:
                    yield
                finally:
                    operations.autocommit_active = False

        return Context()

    def create_index(self, name, table_name, columns, **kwargs):
        self.created.append({
            "name": name,
            "table_name": table_name,
            "columns": tuple(columns),
            "kwargs": kwargs,
            "autocommit_active": self.autocommit_active,
        })

    def drop_index(self, name, **kwargs):
        self.dropped.append({
            "name": name,
            "kwargs": kwargs,
            "autocommit_active": self.autocommit_active,
        })


def test_postgres_upgrade_creates_both_tracking_indexes_concurrently(monkeypatch):
    migration = _load_migration()
    operations = CapturingOperations()
    monkeypatch.setattr(migration, "op", operations)
    monkeypatch.setattr(migration, "_index_names", lambda _table_name: set())

    migration.upgrade()

    assert migration.revision == "0069_analytics_tracking_query_indexes"
    assert migration.down_revision == "0068_analytics_loki_ingest"
    assert operations.autocommit_entries == 1
    assert operations.created == [
        {
            "name": "ix_analytics_events_course_user_id_time",
            "table_name": "analytics_tracking_events",
            "columns": ("course_id", "user_id", "event_time"),
            "kwargs": {"unique": False, "postgresql_concurrently": True},
            "autocommit_active": True,
        },
        {
            "name": "ix_analytics_tracking_events_created_id",
            "table_name": "analytics_tracking_events",
            "columns": ("created_at", "id"),
            "kwargs": {"unique": False, "postgresql_concurrently": True},
            "autocommit_active": True,
        },
    ]


def test_postgres_downgrade_drops_both_tracking_indexes_concurrently(monkeypatch):
    migration = _load_migration()
    operations = CapturingOperations()
    monkeypatch.setattr(migration, "op", operations)
    monkeypatch.setattr(
        migration,
        "_index_names",
        lambda _table_name: {
            "ix_analytics_events_course_user_id_time",
            "ix_analytics_tracking_events_created_id",
        },
    )

    migration.downgrade()

    assert operations.autocommit_entries == 1
    assert operations.dropped == [
        {
            "name": "ix_analytics_tracking_events_created_id",
            "kwargs": {
                "table_name": "analytics_tracking_events",
                "postgresql_concurrently": True,
            },
            "autocommit_active": True,
        },
        {
            "name": "ix_analytics_events_course_user_id_time",
            "kwargs": {
                "table_name": "analytics_tracking_events",
                "postgresql_concurrently": True,
            },
            "autocommit_active": True,
        },
    ]
