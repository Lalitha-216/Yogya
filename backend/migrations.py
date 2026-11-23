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


def _supports_json_valid(connection: sqlite3.Connection) -> bool:
    """Return whether this SQLite build provides the JSON validation function."""
    try:
        return (
            connection.execute(
                "SELECT json_valid(?), json_valid(?)",
                ("{}", "{invalid"),
            ).fetchone()
            == (1, 0)
        )
    except sqlite3.Error:
        return False


def _create_assessment_schema(connection: sqlite3.Connection) -> None:
    """Create the assessment tables without changing legacy worker tables."""
    json_checks = _supports_json_valid(connection)

    def json_check(column: str) -> str:
        return f"CHECK (json_valid({column}))" if json_checks else ""

    connection.execute(
        f"""
        CREATE TABLE questions (
            question_id TEXT NOT NULL PRIMARY KEY,
            trade TEXT NOT NULL
                CHECK (trade IN ('Electrician', 'Plumber')),
            difficulty TEXT NOT NULL
                CHECK (difficulty IN ('FOUNDATIONAL', 'INTERMEDIATE', 'ADVANCED')),
            skill_tag TEXT NOT NULL CHECK (length(trim(skill_tag)) > 0),
            question_text_en TEXT NOT NULL CHECK (length(trim(question_text_en)) > 0),
            question_text_te TEXT NOT NULL CHECK (length(trim(question_text_te)) > 0),
            question_text_hi TEXT NOT NULL CHECK (length(trim(question_text_hi)) > 0),
            expected_concepts_json TEXT NOT NULL
                {json_check("expected_concepts_json")},
            rubric_json TEXT NOT NULL
                {json_check("rubric_json")},
            safety_critical INTEGER NOT NULL
                CHECK (typeof(safety_critical) = 'integer' AND safety_critical IN (0, 1)),
            active INTEGER NOT NULL
                CHECK (typeof(active) = 'integer' AND active IN (0, 1)),
            telugu_review_required INTEGER NOT NULL
                CHECK (
                    typeof(telugu_review_required) = 'integer'
                    AND telugu_review_required IN (0, 1)
                ),
            hindi_review_required INTEGER NOT NULL
                CHECK (
                    typeof(hindi_review_required) = 'integer'
                    AND hindi_review_required IN (0, 1)
                )
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            trade TEXT NOT NULL CHECK (trade IN ('Electrician', 'Plumber')),
            language TEXT NOT NULL CHECK (language IN ('en', 'te', 'hi')),
            status TEXT NOT NULL
                CHECK (status IN ('IN_PROGRESS', 'COMPLETED', 'ABANDONED')),
            current_stage INTEGER NOT NULL
                CHECK (typeof(current_stage) = 'integer' AND current_stage BETWEEN 1 AND 3),
            total_score INTEGER
                CHECK (
                    total_score IS NULL
                    OR (typeof(total_score) = 'integer' AND total_score BETWEEN 0 AND 24)
                ),
            max_score INTEGER NOT NULL DEFAULT 24
                CHECK (typeof(max_score) = 'integer' AND max_score = 24),
            score_percentage REAL
                CHECK (
                    score_percentage IS NULL
                    OR (
                        typeof(score_percentage) IN ('integer', 'real')
                        AND score_percentage BETWEEN 0 AND 100
                    )
                ),
            safety_flags_json TEXT NOT NULL
                {json_check("safety_flags_json")},
            started_at TEXT NOT NULL,
            completed_at TEXT,
            CHECK (
                (
                    status = 'COMPLETED'
                    AND total_score IS NOT NULL
                    AND score_percentage IS NOT NULL
                    AND completed_at IS NOT NULL
                )
                OR
                (
                    status IN ('IN_PROGRESS', 'ABANDONED')
                    AND total_score IS NULL
                    AND score_percentage IS NULL
                    AND completed_at IS NULL
                )
            ),
            FOREIGN KEY (worker_id) REFERENCES workers (id) ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE assessment_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id INTEGER NOT NULL,
            question_id TEXT NOT NULL,
            stage_number INTEGER NOT NULL
                CHECK (typeof(stage_number) = 'integer' AND stage_number BETWEEN 1 AND 3),
            question_order INTEGER NOT NULL
                CHECK (typeof(question_order) = 'integer' AND question_order BETWEEN 1 AND 6),
            selection_reason TEXT NOT NULL CHECK (length(trim(selection_reason)) > 0),
            selected_at TEXT NOT NULL,
            UNIQUE (assessment_id, question_id),
            UNIQUE (assessment_id, question_order),
            FOREIGN KEY (assessment_id)
                REFERENCES assessments (id) ON DELETE RESTRICT,
            FOREIGN KEY (question_id)
                REFERENCES questions (question_id) ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE assessment_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id INTEGER NOT NULL,
            question_id TEXT NOT NULL,
            stage_number INTEGER NOT NULL
                CHECK (typeof(stage_number) = 'integer' AND stage_number BETWEEN 1 AND 3),
            answer_text TEXT NOT NULL CHECK (length(trim(answer_text)) > 0),
            answer_source TEXT NOT NULL CHECK (answer_source IN ('VOICE', 'TEXT')),
            score INTEGER NOT NULL
                CHECK (typeof(score) = 'integer' AND score BETWEEN 0 AND 4),
            rubric_feedback_json TEXT NOT NULL
                {json_check("rubric_feedback_json")},
            safety_flag INTEGER NOT NULL
                CHECK (typeof(safety_flag) = 'integer' AND safety_flag IN (0, 1)),
            safety_reason TEXT,
            safety_concerns_json TEXT NOT NULL
                {json_check("safety_concerns_json")},
            answered_at TEXT NOT NULL,
            UNIQUE (assessment_id, question_id),
            FOREIGN KEY (assessment_id)
                REFERENCES assessments (id) ON DELETE RESTRICT,
            FOREIGN KEY (question_id)
                REFERENCES questions (question_id) ON DELETE RESTRICT,
            FOREIGN KEY (assessment_id, question_id)
                REFERENCES assessment_questions (assessment_id, question_id)
                ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_assessments_worker_history
        ON assessments (worker_id, started_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_assessment_questions_ordered
        ON assessment_questions (assessment_id, stage_number, question_order)
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_assessment_answers_stage
        ON assessment_answers (assessment_id, stage_number)
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_questions_selection
        ON questions (trade, difficulty, active)
        """
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "create_assessment_schema", _create_assessment_schema),
)


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
