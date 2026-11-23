"""Tests for versioned SQLite migration infrastructure."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Barrier, Lock

import pytest

import main
from migrations import Migration, apply_migrations


def open_database(path):
    """Open a test database connection with application-equivalent pragmas."""
    connection = sqlite3.connect(path, timeout=5.0)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def test_apply_migrations_creates_tracking_table_and_records_version(tmp_path):
    connection = open_database(tmp_path / "migrations.db")
    try:
        apply_migrations(
            connection,
            [Migration(1, "create_example", lambda conn: conn.execute(
                "CREATE TABLE example (id INTEGER PRIMARY KEY)"
            ))],
        )

        assert connection.execute(
            "SELECT version, name FROM schema_migrations"
        ).fetchall() == [(1, "create_example")]
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'example'"
        ).fetchone() == ("example",)
        applied_at = connection.execute(
            "SELECT applied_at FROM schema_migrations WHERE version = 1"
        ).fetchone()[0]
        assert applied_at.endswith("+00:00")
    finally:
        connection.close()


def test_migrations_run_in_version_order(tmp_path):
    connection = open_database(tmp_path / "ordered.db")
    execution_order = []
    try:
        apply_migrations(
            connection,
            [
                Migration(2, "second", lambda conn: execution_order.append(2)),
                Migration(1, "first", lambda conn: execution_order.append(1)),
            ],
        )

        assert execution_order == [1, 2]
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,)]
    finally:
        connection.close()


def test_already_applied_migration_is_skipped(tmp_path):
    connection = open_database(tmp_path / "skip.db")
    call_count = 0

    def migration(conn):
        nonlocal call_count
        call_count += 1
        conn.execute("CREATE TABLE example (id INTEGER PRIMARY KEY)")

    try:
        definition = [Migration(1, "create_example", migration)]
        apply_migrations(connection, definition)
        apply_migrations(connection, definition)

        assert call_count == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 1"
        ).fetchone() == (1,)
    finally:
        connection.close()


def test_failed_migration_rolls_back_all_changes_and_version_rows(tmp_path):
    connection = open_database(tmp_path / "rollback.db")

    def create_first_table(conn):
        conn.execute("CREATE TABLE first_migration (id INTEGER PRIMARY KEY)")

    def fail_second_migration(conn):
        conn.execute("CREATE TABLE second_migration (id INTEGER PRIMARY KEY)")
        raise RuntimeError("migration failure")

    try:
        with pytest.raises(RuntimeError, match="migration failure"):
            apply_migrations(
                connection,
                [
                    Migration(1, "create_first_table", create_first_table),
                    Migration(2, "create_then_fail", fail_second_migration),
                ],
            )

        assert connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name IN ('first_migration', 'second_migration')"
        ).fetchone() is None
        assert connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone() is None
        assert not connection.in_transaction
    finally:
        connection.close()


def test_application_connections_enable_foreign_keys_and_busy_timeout(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "application.db")

    with main.db() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("PRAGMA busy_timeout").fetchone() == (5000,)


def test_init_db_preserves_existing_worker_tables_and_records(tmp_path, monkeypatch):
    database_path = tmp_path / "existing.db"
    monkeypatch.setattr(main, "DB_PATH", database_path)

    main.init_db()
    with main.db() as connection:
        connection.execute(
            """
            INSERT INTO workers (
                name, language, location, raw_transcript, trade,
                experience_years, evidence_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("Test Worker", "en", "Test Location", "Transcript", "Electrician", 5, "SELF_REPORTED"),
        )
        worker_id = connection.execute("SELECT id FROM workers").fetchone()[0]
        connection.execute(
            """
            INSERT INTO worker_skills (worker_id, skill_name, evidence_level)
            VALUES (?, ?, ?)
            """,
            (worker_id, "Wiring repair", "SELF_REPORTED"),
        )

    with main.db() as connection:
        before_workers = connection.execute(
            "SELECT * FROM workers ORDER BY id"
        ).fetchall()
        before_skills = connection.execute(
            "SELECT * FROM worker_skills ORDER BY id"
        ).fetchall()

    main.init_db()

    with main.db() as connection:
        assert connection.execute("SELECT * FROM workers ORDER BY id").fetchall() == before_workers
        assert connection.execute(
            "SELECT * FROM worker_skills ORDER BY id"
        ).fetchall() == before_skills
        assert connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall() == []
        assert connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall() == [("schema_migrations",), ("worker_skills",), ("workers",)]


def test_init_db_preserves_legacy_tables_and_records_created_before_initialization(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "preexisting-legacy.db"
    monkeypatch.setattr(main, "DB_PATH", database_path)

    connection = open_database(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                language TEXT NOT NULL,
                location TEXT DEFAULT '',
                raw_transcript TEXT NOT NULL,
                trade TEXT NOT NULL,
                experience_years INTEGER NOT NULL,
                evidence_level TEXT NOT NULL
            );
            CREATE TABLE worker_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                skill_name TEXT NOT NULL,
                evidence_level TEXT NOT NULL,
                FOREIGN KEY (worker_id) REFERENCES workers (id)
            );
            INSERT INTO workers (
                id, name, language, location, raw_transcript, trade,
                experience_years, evidence_level
            ) VALUES (
                17, 'Existing Worker', 'te', 'Existing Location',
                'Existing transcript', 'Plumber', 8, 'SELF_REPORTED'
            );
            INSERT INTO worker_skills (id, worker_id, skill_name, evidence_level)
            VALUES (23, 17, 'Pipe joint repair', 'SELF_REPORTED');
            """
        )
        connection.commit()
        workers_before = connection.execute("SELECT * FROM workers").fetchall()
        skills_before = connection.execute("SELECT * FROM worker_skills").fetchall()
        workers_schema_before = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'workers'"
        ).fetchone()
        skills_schema_before = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'worker_skills'"
        ).fetchone()
    finally:
        connection.close()

    main.init_db()

    with main.db() as connection:
        assert connection.execute("SELECT * FROM workers").fetchall() == workers_before
        assert connection.execute("SELECT * FROM worker_skills").fetchall() == skills_before
        assert connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'workers'"
        ).fetchone() == workers_schema_before
        assert connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'worker_skills'"
        ).fetchone() == skills_schema_before


def test_concurrent_migration_execution_uses_independent_connections(tmp_path):
    database_path = tmp_path / "concurrent.db"
    start_together = Barrier(2)
    calls_lock = Lock()
    migration_calls = 0

    def create_marker_table(connection):
        nonlocal migration_calls
        with calls_lock:
            migration_calls += 1
        connection.execute("CREATE TABLE migration_marker (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO migration_marker (id) VALUES (1)")

    migrations = [Migration(1, "create_marker", create_marker_table)]

    def run_migration():
        connection = open_database(database_path)
        try:
            start_together.wait(timeout=5)
            apply_migrations(connection, migrations)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_migration) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)

    verification_connection = open_database(database_path)
    try:
        assert migration_calls == 1
        assert verification_connection.execute(
            "SELECT COUNT(*) FROM migration_marker"
        ).fetchone() == (1,)
        assert verification_connection.execute(
            "SELECT version, name FROM schema_migrations"
        ).fetchall() == [(1, "create_marker")]
    finally:
        verification_connection.close()
