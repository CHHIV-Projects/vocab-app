"""Ordered additive PostgreSQL migrations for the Vocab application."""

from __future__ import annotations

from pathlib import Path
from typing import Any


MIGRATION_DIR = Path(__file__).with_name("db") / "migrations"


def apply_migrations(connection: Any) -> list[str]:
    """Apply committed migrations atomically under a PostgreSQL advisory lock."""
    applied: list[str] = []
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(4976045)")
        cursor.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        cursor.execute("SELECT version FROM schema_migrations")
        rows = cursor.fetchall() or []
        known = {row[0] if not isinstance(row, dict) else row["version"] for row in rows}
        for path in sorted(MIGRATION_DIR.glob("*.sql")):
            version = path.stem
            if version in known:
                continue
            cursor.execute(path.read_text(encoding="utf-8"))
            applied.append(version)
    connection.commit()
    return applied
