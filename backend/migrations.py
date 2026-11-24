"""Versioned SQLite schema migration infrastructure."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3

from assessment.adaptive_engine import Difficulty, Trade
from assessment.question_bank import QUESTION_BANK, AssessmentQuestion, validate_question_bank


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


_QUESTION_COLUMNS = (
    "question_id",
    "trade",
    "difficulty",
    "skill_tag",
    "question_text_en",
    "question_text_te",
    "question_text_hi",
    "expected_concepts_json",
    "rubric_json",
    "safety_critical",
    "active",
    "telugu_review_required",
    "hindi_review_required",
)


def _serialize_question_json(
    question: AssessmentQuestion,
) -> tuple[str, str]:
    """Validate and deterministically serialize structured question fields."""
    concepts = question.expected_concepts
    rubric = question.rubric_json
    if not isinstance(concepts, tuple) or not concepts or any(
        not isinstance(concept, str) or not concept.strip()
        for concept in concepts
    ):
        raise ValueError(
            f"Question {question.question_id!r} has invalid expected concepts."
        )
    if not isinstance(rubric, dict) or set(rubric) != {"0", "1", "2", "3", "4"}:
        raise ValueError(
            f"Question {question.question_id!r} rubric must contain scores 0 through 4."
        )
    if any(not isinstance(text, str) or not text.strip() for text in rubric.values()):
        raise ValueError(
            f"Question {question.question_id!r} has an invalid rubric description."
        )
    try:
        concepts_json = json.dumps(
            concepts,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        rubric_json = json.dumps(
            rubric,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        parsed_concepts = json.loads(concepts_json)
        parsed_rubric = json.loads(rubric_json)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Question {question.question_id!r} contains invalid JSON data."
        ) from exc

    if parsed_concepts != list(concepts) or parsed_rubric != rubric:
        raise ValueError(
            f"Question {question.question_id!r} JSON data failed round-trip validation."
        )
    return concepts_json, rubric_json


def _question_row(question: AssessmentQuestion) -> tuple[object, ...]:
    """Validate a bank question and map it to its database row values."""
    question_id = question.question_id
    if not isinstance(question_id, str) or not question_id.strip():
        raise ValueError("Every question must have a non-empty question ID.")
    if not isinstance(question.trade, Trade) or not isinstance(question.difficulty, Difficulty):
        raise ValueError(f"Question {question_id!r} has invalid trade or difficulty.")
    for field in (
        "skill_tag",
        "question_text_en",
        "question_text_te",
        "question_text_hi",
    ):
        value = getattr(question, field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Question {question_id!r} has invalid {field}.")
    for field in (
        "safety_critical",
        "active",
        "telugu_review_required",
        "hindi_review_required",
    ):
        if type(getattr(question, field)) is not bool:
            raise ValueError(f"Question {question_id!r} has invalid Boolean field {field}.")

    expected_concepts_json, rubric_json = _serialize_question_json(question)
    return (
        question_id,
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


def _seed_question_bank(connection: sqlite3.Connection) -> None:
    """Seed missing question IDs, rejecting any existing content conflict."""
    try:
        validate_question_bank(QUESTION_BANK)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid assessment question bank: {exc}") from exc

    rows = [
        _question_row(question)
        for trade in (Trade.ELECTRICIAN, Trade.PLUMBER)
        for difficulty in (
            Difficulty.FOUNDATIONAL,
            Difficulty.INTERMEDIATE,
            Difficulty.ADVANCED,
        )
        for question in QUESTION_BANK[trade][difficulty]
    ]

    select_sql = (
        "SELECT "
        + ", ".join(_QUESTION_COLUMNS[1:])
        + " FROM questions WHERE question_id = ?"
    )
    insert_sql = (
        "INSERT INTO questions ("
        + ", ".join(_QUESTION_COLUMNS)
        + ") VALUES ("
        + ", ".join("?" for _ in _QUESTION_COLUMNS)
        + ")"
    )
    for row in rows:
        existing = connection.execute(select_sql, (row[0],)).fetchone()
        if existing is not None:
            if tuple(existing) != row[1:]:
                raise ValueError(
                    f"Question ID {row[0]!r} already exists with different content."
                )
            continue
        connection.execute(insert_sql, row)


def _create_verification_records_schema(connection: sqlite3.Connection) -> None:
    """Create the independent human verification audit table."""
    connection.execute(
        """
        CREATE TABLE verification_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL
                CHECK (typeof(worker_id) = 'integer' AND worker_id > 0),
            skill_name TEXT NOT NULL
                CHECK (length(trim(skill_name)) > 0),
            assessor_identifier TEXT NOT NULL
                CHECK (length(trim(assessor_identifier)) > 0),
            outcome TEXT NOT NULL
                CHECK (outcome IN ('VERIFIED', 'NOT_VERIFIED')),
            evidence TEXT NOT NULL
                CHECK (length(trim(evidence)) > 0),
            notes TEXT,
            verified_at TEXT NOT NULL,
            FOREIGN KEY (worker_id) REFERENCES workers (id) ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_verification_records_worker_time
        ON verification_records (worker_id, verified_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX idx_verification_records_worker_skill
        ON verification_records (worker_id, skill_name)
        """
    )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "create_assessment_schema", _create_assessment_schema),
    Migration(2, "seed_assessment_question_bank", _seed_question_bank),
    Migration(3, "create_verification_records", _create_verification_records_schema),
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
