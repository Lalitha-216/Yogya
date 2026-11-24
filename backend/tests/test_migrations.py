"""Tests for versioned SQLite migration infrastructure."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
import sqlite3
from threading import Barrier, Lock

import pytest

import migrations as migration_module
import main
from assessment.adaptive_engine import Difficulty, Trade
from assessment.question_bank import QUESTION_BANK
from migrations import MIGRATIONS, Migration, apply_migrations


def open_database(path):
    """Open a test database connection with application-equivalent pragmas."""
    connection = sqlite3.connect(path, timeout=5.0)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_assessment_database(tmp_path, monkeypatch):
    """Initialize an isolated database with the existing application schema."""
    database_path = tmp_path / "assessment-schema.db"
    monkeypatch.setattr(main, "DB_PATH", database_path)
    main.init_db()
    return database_path


def insert_worker(connection):
    cursor = connection.execute(
        """
        INSERT INTO workers (
            name, language, location, raw_transcript, trade,
            experience_years, evidence_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("Schema Test Worker", "en", "", "sample", "Electrician", 2, "SELF_REPORTED"),
    )
    return cursor.lastrowid


def insert_question(connection, question_id="E01"):
    if connection.execute(
        "SELECT 1 FROM questions WHERE question_id = ?",
        (question_id,),
    ).fetchone():
        return
    connection.execute(
        """
        INSERT INTO questions (
            question_id, trade, difficulty, skill_tag, question_text_en,
            question_text_te, question_text_hi, expected_concepts_json,
            rubric_json, safety_critical, active, telugu_review_required,
            hindi_review_required
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question_id,
            "Electrician",
            "FOUNDATIONAL",
            "Electrical safety",
            "Question in English",
            "ప్రశ్న",
            "प्रश्न",
            json.dumps(["concept"]),
            json.dumps({str(level): f"level {level}" for level in range(5)}),
            1,
            1,
            1,
            1,
        ),
    )


def insert_assessment(connection, worker_id, *, assessment_id=None, status="IN_PROGRESS"):
    fields = """
        worker_id, trade, language, status, current_stage, total_score,
        max_score, score_percentage, safety_flags_json, started_at, completed_at
    """
    values = (
        worker_id,
        "Electrician",
        "en",
        status,
        1,
        None,
        24,
        None,
        "[]",
        "2026-01-01T00:00:00+00:00",
        None,
    )
    if assessment_id is None:
        cursor = connection.execute(
            f"INSERT INTO assessments ({fields}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
    else:
        cursor = connection.execute(
            f"INSERT INTO assessments (id, {fields}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (assessment_id, *values),
        )
    return cursor.lastrowid


def insert_selection(
    connection,
    assessment_id,
    question_id="E01",
    *,
    stage_number=1,
    question_order=1,
):
    return connection.execute(
        """
        INSERT INTO assessment_questions (
            assessment_id, question_id, stage_number, question_order,
            selection_reason, selected_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            assessment_id,
            question_id,
            stage_number,
            question_order,
            "Initial stage selection",
            "2026-01-01T00:00:00+00:00",
        ),
    ).lastrowid


def insert_answer(
    connection,
    assessment_id,
    question_id="E01",
    *,
    stage_number=1,
    answer_source="TEXT",
    score=3,
):
    return connection.execute(
        """
        INSERT INTO assessment_answers (
            assessment_id, question_id, stage_number, answer_text,
            answer_source, score, rubric_feedback_json, safety_flag,
            safety_reason, safety_concerns_json, answered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assessment_id,
            question_id,
            stage_number,
            "Worker answer",
            answer_source,
            score,
            json.dumps({"feedback": "Valid feedback"}),
            0,
            None,
            "[]",
            "2026-01-01T00:00:00+00:00",
        ),
    ).lastrowid


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


@pytest.mark.parametrize("invalid_worker_id", [0, -1])
def test_verification_records_reject_non_positive_worker_ids(
    tmp_path,
    monkeypatch,
    invalid_worker_id,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO verification_records (
                    worker_id, skill_name, assessor_identifier, outcome,
                    evidence, notes, verified_at
                ) VALUES (?, 'Electrical safety', 'DEMO-ASSESSOR-001',
                          'VERIFIED', 'Observed task', NULL,
                          '2026-01-01T00:00:00+00:00')
                """,
                (invalid_worker_id,),
            )
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
        ).fetchall() == [(migration.version,) for migration in MIGRATIONS]
        assert connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall() == [
            ("assessment_answers",),
            ("assessment_questions",),
            ("assessments",),
            ("questions",),
            ("schema_migrations",),
            ("verification_records",),
            ("worker_skills",),
            ("workers",),
        ]


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
        workers_before = connection.execute(
            """
            SELECT id, name, language, location, raw_transcript, trade,
                   experience_years, evidence_level
            FROM workers
            """
        ).fetchall()
        skills_before = connection.execute("SELECT * FROM worker_skills").fetchall()
        skills_schema_before = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'worker_skills'"
        ).fetchone()
    finally:
        connection.close()

    main.init_db()

    with main.db() as connection:
        assert connection.execute(
            """
            SELECT id, name, language, location, raw_transcript, trade,
                   experience_years, evidence_level
            FROM workers
            """
        ).fetchall() == workers_before
        assert connection.execute("SELECT * FROM worker_skills").fetchall() == skills_before
        assert connection.execute(
            "SELECT experience_known, extraction_source FROM workers WHERE id = 17"
        ).fetchone() == (1, "gemini")
        assert connection.execute(
            "SELECT name FROM pragma_table_info('workers')"
        ).fetchall()[-2:] == [("experience_known",), ("extraction_source",)]
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


EXPECTED_ASSESSMENT_COLUMNS = {
    "questions": {
        "question_id", "trade", "difficulty", "skill_tag", "question_text_en",
        "question_text_te", "question_text_hi", "expected_concepts_json",
        "rubric_json", "safety_critical", "active", "telugu_review_required",
        "hindi_review_required",
    },
    "assessments": {
        "id", "worker_id", "trade", "language", "status", "current_stage",
        "total_score", "max_score", "score_percentage", "safety_flags_json",
        "started_at", "completed_at",
    },
    "assessment_questions": {
        "id", "assessment_id", "question_id", "stage_number", "question_order",
        "selection_reason", "selected_at",
    },
    "assessment_answers": {
        "id", "assessment_id", "question_id", "stage_number", "answer_text",
        "answer_source", "score", "rubric_feedback_json", "safety_flag",
        "safety_reason", "safety_concerns_json", "answered_at",
    },
}


def test_assessment_schema_migration_creates_four_tables_and_expected_columns(
    tmp_path,
    monkeypatch,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "questions",
            "assessments",
            "assessment_questions",
            "assessment_answers",
        } <= table_names

        for table_name, expected_columns in EXPECTED_ASSESSMENT_COLUMNS.items():
            columns = {
                row[1]: (row[2], row[3], row[4], row[5])
                for row in connection.execute(f'PRAGMA table_info("{table_name}")')
            }
            assert set(columns) == expected_columns

        assert columns["score"][0:2] == ("INTEGER", 1)
        assessment_columns = {
            row[1]: (row[2], row[3], row[4], row[5])
            for row in connection.execute("PRAGMA table_info(assessments)")
        }
        assert assessment_columns["max_score"] == ("INTEGER", 1, "24", 0)
        assert assessment_columns["score_percentage"][0] == "REAL"
    finally:
        connection.close()


def test_assessment_schema_declares_restrictive_foreign_keys_and_indexes(
    tmp_path,
    monkeypatch,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        question_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(assessment_questions)"
        ).fetchall()
        assert {(row[2], row[3], row[4], row[6]) for row in question_foreign_keys} == {
            ("assessments", "assessment_id", "id", "RESTRICT"),
            ("questions", "question_id", "question_id", "RESTRICT"),
        }

        answer_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(assessment_answers)"
        ).fetchall()
        assert len(answer_foreign_keys) == 4
        assert all(row[6] == "RESTRICT" for row in answer_foreign_keys)
        assert {
            (row[2], row[3], row[4])
            for row in answer_foreign_keys
        } >= {
            ("assessments", "assessment_id", "id"),
            ("questions", "question_id", "question_id"),
            ("assessment_questions", "assessment_id", "assessment_id"),
            ("assessment_questions", "question_id", "question_id"),
        }
        assert connection.execute(
            "PRAGMA foreign_key_list(assessments)"
        ).fetchone()[6] == "RESTRICT"

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert {
            "idx_assessments_worker_history",
            "idx_assessment_questions_ordered",
            "idx_assessment_answers_stage",
            "idx_questions_selection",
        } <= indexes
    finally:
        connection.close()


def test_assessment_schema_migration_is_registered_once_on_repeated_init(
    tmp_path,
    monkeypatch,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    with main.db() as connection:
        first_record = connection.execute(
            "SELECT version, name, applied_at FROM schema_migrations"
        ).fetchall()

    main.init_db()

    with main.db() as connection:
        assert connection.execute(
            "SELECT version, name, applied_at FROM schema_migrations"
        ).fetchall() == first_record
        assert first_record == [
            (migration.version, migration.name, applied_at)
            for (migration, (_, _, applied_at)) in zip(MIGRATIONS, first_record)
        ]
        assert len(first_record) == len(MIGRATIONS)
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name IN "
            "('questions', 'assessments', 'assessment_questions', 'assessment_answers')"
        ).fetchone() == (4,)


def test_verification_records_migration_creates_table_constraints_and_indexes(
    tmp_path,
    monkeypatch,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        table = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'verification_records'"
        ).fetchone()
        assert table == ("verification_records",)

        columns = {
            row[1]: (row[2], row[3], row[4], row[5])
            for row in connection.execute(
                "PRAGMA table_info(verification_records)"
            )
        }
        assert set(columns) == {
            "id",
            "worker_id",
            "skill_name",
            "assessor_identifier",
            "outcome",
            "evidence",
            "notes",
            "verified_at",
        }

        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(verification_records)"
        ).fetchall()
        assert len(foreign_keys) == 1
        assert foreign_keys[0][2] == "workers"
        assert foreign_keys[0][6] == "RESTRICT"

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert {
            "idx_verification_records_worker_time",
            "idx_verification_records_worker_skill",
        } <= indexes
        assert connection.execute(
            "SELECT version, name FROM schema_migrations "
            "WHERE version = 3"
        ).fetchone() == (
            3,
            "create_verification_records",
        )
        assert connection.execute(
            "SELECT version, name FROM schema_migrations WHERE version = 4"
        ).fetchone() == (4, "add_profile_discovery_metadata")
    finally:
        connection.close()


def test_question_seed_migration_inserts_24_questions_with_expected_trade_counts(
    tmp_path,
    monkeypatch,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        rows = connection.execute(
            "SELECT question_id, trade FROM questions ORDER BY question_id"
        ).fetchall()
        assert len(rows) == 24
        assert sum(trade == Trade.ELECTRICIAN.value for _, trade in rows) == 12
        assert sum(trade == Trade.PLUMBER.value for _, trade in rows) == 12
        assert {version for version, in connection.execute(
            "SELECT version FROM schema_migrations"
        )} == {1, 2, 3, 4}
    finally:
        connection.close()


def test_question_seed_migration_maps_fields_and_round_trips_json(
    tmp_path,
    monkeypatch,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        actual_questions = {
            row[0]: row[1:]
            for row in connection.execute(
                """
                SELECT question_id, trade, difficulty, skill_tag, question_text_en,
                       question_text_te, question_text_hi, expected_concepts_json,
                       rubric_json, safety_critical, active, telugu_review_required,
                       hindi_review_required
                FROM questions
                """
            )
        }
        expected_count = 0
        for trade in (Trade.ELECTRICIAN, Trade.PLUMBER):
            for difficulty in (
                Difficulty.FOUNDATIONAL,
                Difficulty.INTERMEDIATE,
                Difficulty.ADVANCED,
            ):
                for question in QUESTION_BANK[trade][difficulty]:
                    expected_count += 1
                    expected_concepts_json = json.dumps(
                        question.expected_concepts,
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    )
                    rubric_json = json.dumps(
                        question.rubric_json,
                        ensure_ascii=False,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    assert actual_questions[question.question_id] == (
                        question.trade.value,
                        question.difficulty.value,
                        question.skill_tag,
                        question.question_text_en,
                        question.question_text_te,
                        question.question_text_hi,
                        expected_concepts_json,
                        rubric_json,
                        int(question.safety_critical),
                        int(question.active),
                        int(question.telugu_review_required),
                        int(question.hindi_review_required),
                    )
                    assert json.loads(expected_concepts_json) == list(question.expected_concepts)
                    assert json.loads(rubric_json) == question.rubric_json
        assert expected_count == 24
        assert len(actual_questions) == expected_count
    finally:
        connection.close()


def test_question_seed_migration_is_idempotent_on_repeated_initialization(
    tmp_path,
    monkeypatch,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        original_questions = connection.execute(
            "SELECT * FROM questions ORDER BY question_id"
        ).fetchall()
        original_migrations = connection.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
    finally:
        connection.close()

    main.init_db()

    connection = open_database(database_path)
    try:
        assert connection.execute(
            "SELECT * FROM questions ORDER BY question_id"
        ).fetchall() == original_questions
        assert connection.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall() == original_migrations
    finally:
        connection.close()


def test_matching_existing_question_content_is_skipped(tmp_path, monkeypatch):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    question = QUESTION_BANK[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL][0]
    connection = open_database(database_path)
    try:
        row = connection.execute(
            "SELECT * FROM questions WHERE question_id = ?",
            (question.question_id,),
        ).fetchone()
        connection.execute("DELETE FROM questions")
        connection.execute("DELETE FROM schema_migrations WHERE version = 2")
        connection.execute(
            """
            INSERT INTO questions (
                question_id, trade, difficulty, skill_tag, question_text_en,
                question_text_te, question_text_hi, expected_concepts_json,
                rubric_json, safety_critical, active, telugu_review_required,
                hindi_review_required
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        connection.commit()

        apply_migrations(connection, MIGRATIONS[1:])

        assert connection.execute("SELECT COUNT(*) FROM questions").fetchone() == (24,)
        assert connection.execute(
            "SELECT * FROM questions WHERE question_id = ?",
            (question.question_id,),
        ).fetchone() == row
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,)]
    finally:
        connection.close()


def test_conflicting_question_content_raises_and_rolls_back_seed_transaction(
    tmp_path,
    monkeypatch,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    question = QUESTION_BANK[Trade.PLUMBER][Difficulty.ADVANCED][-1]
    connection = open_database(database_path)
    try:
        question_row = connection.execute(
            "SELECT * FROM questions WHERE question_id = ?",
            (question.question_id,),
        ).fetchone()
        conflicting_row = (*question_row[:4], "Conflicting question text", *question_row[5:])
        connection.execute("DELETE FROM questions")
        connection.execute("DELETE FROM schema_migrations WHERE version = 2")
        connection.execute(
            """
            INSERT INTO questions (
                question_id, trade, difficulty, skill_tag, question_text_en,
                question_text_te, question_text_hi, expected_concepts_json,
                rubric_json, safety_critical, active, telugu_review_required,
                hindi_review_required
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            conflicting_row,
        )
        connection.commit()

        with pytest.raises(ValueError, match=r"Question ID 'P12'.*different content"):
            apply_migrations(connection, MIGRATIONS[1:])

        assert connection.execute("SELECT * FROM questions").fetchall() == [
            conflicting_row
        ]
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (3,), (4,)]
    finally:
        connection.close()


def test_invalid_question_data_is_rejected_without_partial_seed(
    tmp_path,
    monkeypatch,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    invalid_bank = deepcopy(QUESTION_BANK)
    question = invalid_bank[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL][0]
    invalid_questions = list(invalid_bank[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL])
    invalid_questions[0] = replace(question, expected_concepts=())
    invalid_bank[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL] = tuple(invalid_questions)
    monkeypatch.setattr(migration_module, "QUESTION_BANK", invalid_bank)

    connection = open_database(database_path)
    try:
        connection.execute("DELETE FROM questions")
        connection.execute("DELETE FROM schema_migrations WHERE version = 2")
        connection.commit()

        with pytest.raises(ValueError, match="has no expected concepts"):
            apply_migrations(connection, MIGRATIONS[1:])

        assert connection.execute("SELECT COUNT(*) FROM questions").fetchone() == (0,)
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (3,), (4,)]
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("column", "invalid_value"),
    [
        ("trade", "Carpenter"),
        ("difficulty", "EXPERT"),
        ("safety_critical", 2),
        ("active", 1.5),
        ("active", -1),
        ("telugu_review_required", 2),
        ("hindi_review_required", -1),
    ],
)
def test_questions_check_constraints_reject_invalid_values(
    tmp_path,
    monkeypatch,
    column,
    invalid_value,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        values = {
            "question_id": "E-invalid",
            "trade": "Electrician",
            "difficulty": "FOUNDATIONAL",
            "skill_tag": "Tag",
            "question_text_en": "English",
            "question_text_te": "Telugu",
            "question_text_hi": "Hindi",
            "expected_concepts_json": "[]",
            "rubric_json": "{}",
            "safety_critical": 0,
            "active": 1,
            "telugu_review_required": 1,
            "hindi_review_required": 1,
        }
        values[column] = invalid_value
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                f"INSERT INTO questions ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("column", "invalid_value"),
    [
        ("trade", "Carpenter"),
        ("language", "fr"),
        ("status", "PENDING"),
        ("current_stage", 0),
        ("current_stage", 1.5),
        ("total_score", 25),
        ("max_score", 23),
        ("score_percentage", 100.1),
        ("score_percentage", "not-a-number"),
        ("safety_flags_json", "{invalid"),
    ],
)
def test_assessments_check_constraints_reject_invalid_values(
    tmp_path,
    monkeypatch,
    column,
    invalid_value,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        worker_id = insert_worker(connection)
        values = {
            "worker_id": worker_id,
            "trade": "Electrician",
            "language": "en",
            "status": "IN_PROGRESS",
            "current_stage": 1,
            "max_score": 24,
            "safety_flags_json": "[]",
            "started_at": "2026-01-01T00:00:00+00:00",
        }
        values[column] = invalid_value
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                f"INSERT INTO assessments ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("status", "total_score", "score_percentage", "completed_at"),
    [
        ("COMPLETED", None, 50.0, "2026-01-02T00:00:00+00:00"),
        ("COMPLETED", 12, None, "2026-01-02T00:00:00+00:00"),
        ("COMPLETED", 12, 50.0, None),
        ("IN_PROGRESS", 12, 50.0, "2026-01-02T00:00:00+00:00"),
        ("ABANDONED", 12, None, None),
    ],
)
def test_assessments_enforce_final_score_status_consistency(
    tmp_path,
    monkeypatch,
    status,
    total_score,
    score_percentage,
    completed_at,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        worker_id = insert_worker(connection)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO assessments (
                    worker_id, trade, language, status, current_stage, total_score,
                    max_score, score_percentage, safety_flags_json, started_at,
                    completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, 24, ?, '[]', ?, ?)
                """,
                (
                    worker_id,
                    "Electrician",
                    "en",
                    status,
                    3,
                    total_score,
                    score_percentage,
                    "2026-01-01T00:00:00+00:00",
                    completed_at,
                ),
            )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("column", "invalid_value"),
    [
        ("stage_number", 4),
        ("stage_number", 1.5),
        ("question_order", 7),
        ("question_order", 1.5),
    ],
)
def test_assessment_question_check_constraints_reject_invalid_values(
    tmp_path,
    monkeypatch,
    column,
    invalid_value,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        worker_id = insert_worker(connection)
        insert_question(connection)
        assessment_id = insert_assessment(connection, worker_id)
        values = {
            "assessment_id": assessment_id,
            "question_id": "E01",
            "stage_number": 1,
            "question_order": 1,
            "selection_reason": "Initial selection",
            "selected_at": "2026-01-01T00:00:00+00:00",
        }
        values[column] = invalid_value
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                f"INSERT INTO assessment_questions ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("column", "invalid_value"),
    [
        ("stage_number", 0),
        ("stage_number", 1.5),
        ("answer_source", "AUDIO"),
        ("score", 5),
        ("score", 3.5),
        ("safety_flag", 2),
    ],
)
def test_assessment_answer_check_constraints_reject_invalid_values(
    tmp_path,
    monkeypatch,
    column,
    invalid_value,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        worker_id = insert_worker(connection)
        insert_question(connection)
        assessment_id = insert_assessment(connection, worker_id)
        insert_selection(connection, assessment_id)
        values = {
            "assessment_id": assessment_id,
            "question_id": "E01",
            "stage_number": 1,
            "answer_text": "Answer",
            "answer_source": "TEXT",
            "score": 3,
            "rubric_feedback_json": '{"feedback": "ok"}',
            "safety_flag": 0,
            "safety_reason": None,
            "safety_concerns_json": "[]",
            "answered_at": "2026-01-01T00:00:00+00:00",
        }
        values[column] = invalid_value
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                f"INSERT INTO assessment_answers ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
    finally:
        connection.close()


def test_foreign_keys_reject_missing_worker_and_question(tmp_path, monkeypatch):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            insert_assessment(connection, worker_id=999)

        worker_id = insert_worker(connection)
        assessment_id = insert_assessment(connection, worker_id)
        with pytest.raises(sqlite3.IntegrityError):
            insert_selection(connection, assessment_id, "missing-question")
    finally:
        connection.close()


def test_composite_foreign_key_rejects_answer_for_unselected_question(
    tmp_path,
    monkeypatch,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        worker_id = insert_worker(connection)
        insert_question(connection)
        assessment_id = insert_assessment(connection, worker_id)

        with pytest.raises(sqlite3.IntegrityError):
            insert_answer(connection, assessment_id)
    finally:
        connection.close()


def test_duplicate_question_assignment_and_answer_are_rejected(tmp_path, monkeypatch):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        worker_id = insert_worker(connection)
        insert_question(connection)
        assessment_id = insert_assessment(connection, worker_id)
        insert_selection(connection, assessment_id, "E01", question_order=1)
        with pytest.raises(sqlite3.IntegrityError):
            insert_selection(connection, assessment_id, "E01", question_order=2)
        with pytest.raises(sqlite3.IntegrityError):
            insert_selection(connection, assessment_id, "E02", question_order=1)

        insert_answer(connection, assessment_id, "E01")
        with pytest.raises(sqlite3.IntegrityError):
            insert_answer(connection, assessment_id, "E01")
    finally:
        connection.close()


def test_foreign_key_deletions_are_restricted(tmp_path, monkeypatch):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        worker_id = insert_worker(connection)
        insert_question(connection)
        assessment_id = insert_assessment(connection, worker_id)
        insert_selection(connection, assessment_id)
        insert_answer(connection, assessment_id)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM assessments WHERE id = ?", (assessment_id,))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM questions WHERE question_id = 'E01'")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM assessment_questions "
                "WHERE assessment_id = ? AND question_id = 'E01'",
                (assessment_id,),
            )
    finally:
        connection.close()


def test_json_checks_are_added_only_when_sqlite_json_valid_is_supported(
    tmp_path,
    monkeypatch,
):
    database_path = initialize_assessment_database(tmp_path, monkeypatch)
    connection = open_database(database_path)
    try:
        json_supported = connection.execute(
            "SELECT json_valid(?), json_valid(?)",
            ("{}", "{invalid"),
        ).fetchone() == (1, 0)
        if json_supported:
            worker_id = insert_worker(connection)
            values = (
                "E-invalid-json", "Electrician", "FOUNDATIONAL", "Tag",
                "English", "Telugu", "Hindi", "{invalid", "{}", 0, 1, 1, 1,
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO questions (
                        question_id, trade, difficulty, skill_tag, question_text_en,
                        question_text_te, question_text_hi, expected_concepts_json,
                        rubric_json, safety_critical, active, telugu_review_required,
                        hindi_review_required
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
            assert worker_id > 0
        else:
            schema_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='questions'"
            ).fetchone()[0]
            assert "json_valid" not in schema_sql
    finally:
        connection.close()


def test_failed_followup_migration_rolls_back_assessment_schema(tmp_path):
    connection = open_database(tmp_path / "schema-rollback.db")

    def fail_after_schema_creation(conn):
        raise RuntimeError("forced migration failure")

    try:
        with pytest.raises(RuntimeError, match="forced migration failure"):
            apply_migrations(
                connection,
                [MIGRATIONS[0], Migration(2, "forced_failure", fail_after_schema_creation)],
            )

        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('schema_migrations', 'questions', 'assessments', "
            "'assessment_questions', 'assessment_answers')"
        ).fetchall() == []
        assert not connection.in_transaction
    finally:
        connection.close()
