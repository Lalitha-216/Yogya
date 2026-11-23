"""Versioned SQLite schema migration infrastructure."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3


MigrationOperation = Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class Migration:
    """One ordered database migration."""

    version: int
    name: str
    apply: MigrationOperation


# Assessment schema migrations will be added in later implementation phases.
MIGRATIONS: tuple[Migration, ...] = ()


def _ordered_migrations(migrations: Sequence[Migration]) -> tuple[Migration, ...]:
    """Validate and order migration definitions by their version."""
    definitions = tuple(migrations)
    if any(not isinstance(migration, Migration) for migration in definitions):
        raise ValueError("Every migration must be a Migration.")
    if any(
        type(migration.version) is not int
        or migration.version < 1
        or not isinstance(migration.name, str)
        or not migration.name.strip()
        or not callable(migration.apply)
        for migration in definitions
    ):
        raise ValueError("Migrations require a positive version, name, and callable operation.")
    versions = [migration.version for migration in definitions]
    if len(versions) != len(set(versions)):
        raise ValueError("Migration versions must be unique.")
    return tuple(sorted(definitions, key=lambda migration: migration.version))


def apply_migrations(
    connection: sqlite3.Connection,
    migrations: Sequence[Migration] = MIGRATIONS,
) -> None:
    """Apply pending migrations atomically while holding SQLite's write lock."""
    if not isinstance(connection, sqlite3.Connection):
        raise ValueError("connection must be a sqlite3.Connection.")
    if connection.in_transaction:
        raise ValueError("Migrations cannot run inside an existing transaction.")

    ordered = _ordered_migrations(migrations)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied_versions = {
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }

        for migration in ordered:
            if migration.version in applied_versions:
                continue
            migration.apply(connection)
            connection.execute(
                """
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
