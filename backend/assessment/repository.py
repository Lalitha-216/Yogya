"""SQLite repository for the YOGYA assessment lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import sqlite3
from typing import Any

from .adaptive_engine import Difficulty, Trade
from .question_bank import AssessmentQuestion


DatabaseFactory = Callable[[], AbstractContextManager[sqlite3.Connection]]


class RepositoryError(Exception):
    """Base class for assessment repository failures."""


class RepositoryValidationError(RepositoryError, ValueError):
    """Raised when repository input or persisted state is invalid."""


class WorkerNotFoundError(RepositoryError):
    """Raised when a worker ID does not exist."""


class AssessmentNotFoundError(RepositoryError):
    """Raised when an assessment ID does not exist."""


class ActiveAssessmentExistsError(RepositoryError):
    """Raised when a worker already has an active assessment."""


class DuplicateAnswerError(RepositoryError):
    """Raised when an answer is inserted more than once."""


class DuplicateAssignmentError(RepositoryError):
    """Raised when a question is assigned more than once."""


class ForeignKeyIntegrityError(RepositoryError):
    """Raised when a repository write violates a foreign-key constraint."""


@dataclass(frozen=True)
class WorkerRecord:
    id: int
    name: str
    language: str
    location: str
    raw_transcript: str
    trade: Trade
    experience_years: int
    evidence_level: str


@dataclass(frozen=True)
class AssessmentRecord:
    id: int
    worker_id: int
    trade: Trade
    language: str
    status: str
    current_stage: int
    total_score: int | None
    max_score: int
    score_percentage: float | None
    safety_flags_json: list[Any] | dict[str, Any]
    started_at: str
    completed_at: str | None


@dataclass(frozen=True)
class QuestionAssignment:
    id: int
    assessment_id: int
    question_id: str
    stage_number: int
    question_order: int
    selection_reason: str
    selected_at: str


@dataclass(frozen=True)
class AnswerRecord:
    id: int
    assessment_id: int
    question_id: str
    stage_number: int
    answer_text: str
    answer_source: str
    score: int
    rubric_feedback: dict[str, Any]
    safety_flag: bool
    safety_reason: str | None
    safety_concerns: list[Any]
    answered_at: str


@dataclass(frozen=True)
class AssessmentProgress:
    assessment: AssessmentRecord
    assignments: tuple[QuestionAssignment, ...]
    answers: tuple[AnswerRecord, ...]
    stage2_difficulty: Difficulty | None


@dataclass(frozen=True)
class AssessmentResult:
    assessment_id: int
    status: str
    total_score: int
    maximum_score: int
    score_percentage: float
    safety_flags: list[Any] | dict[str, Any]
    completed_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RepositoryValidationError(f"{field} must be a non-empty string.")
    return value


def _serialize_json(value: object, field: str) -> str:
    if isinstance(value, (str, bytes, bytearray)):
        raise RepositoryValidationError(f"{field} must contain JSON object or array data.")
    if not isinstance(value, (Mapping, list, tuple)):
        raise RepositoryValidationError(f"{field} must contain JSON object or array data.")
    if isinstance(value, tuple):
        value = list(value)
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True if isinstance(value, Mapping) else False,
            separators=(",", ":"),
        )
        json.loads(serialized)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RepositoryValidationError(f"{field} contains invalid JSON data.") from exc
    return serialized


def _parse_json_object_or_array(value: str, field: str) -> list[Any] | dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RepositoryValidationError(f"Stored {field} contains invalid JSON.") from exc
    if not isinstance(parsed, (list, dict)):
        raise RepositoryValidationError(f"Stored {field} must be a JSON object or array.")
    return parsed


class AssessmentRepository:
    """Repository for SQLite-backed assessment lifecycle records."""

    def __init__(self, database_factory: DatabaseFactory) -> None:
        if not callable(database_factory):
            raise TypeError("database_factory must be callable.")
        self._database_factory = database_factory

    def get_worker(self, worker_id: int) -> WorkerRecord:
        if type(worker_id) is not int or worker_id <= 0:
            raise RepositoryValidationError("worker_id must be a positive integer.")
        with self._database_factory() as connection:
            row = connection.execute(
                """
                SELECT id, name, language, location, raw_transcript, trade,
                       experience_years, evidence_level
                FROM workers
                WHERE id = ?
                """,
                (worker_id,),
            ).fetchone()
        if row is None:
            raise WorkerNotFoundError(f"Worker {worker_id} was not found.")
        try:
            trade = Trade(row[5])
        except (TypeError, ValueError):
            raise RepositoryValidationError(
                f"Worker {worker_id} has an unsupported trade: {row[5]!r}."
            ) from None
        return WorkerRecord(
            id=row[0],
            name=row[1],
            language=row[2],
            location=row[3],
            raw_transcript=row[4],
            trade=trade,
            experience_years=row[6],
            evidence_level=row[7],
        )

    def get_assessment(self, assessment_id: int) -> AssessmentRecord:
        if type(assessment_id) is not int or assessment_id <= 0:
            raise RepositoryValidationError("assessment_id must be a positive integer.")
        with self._database_factory() as connection:
            row = connection.execute(
                """
                SELECT id, worker_id, trade, language, status, current_stage,
                       total_score, max_score, score_percentage,
                       safety_flags_json, started_at, completed_at
                FROM assessments
                WHERE id = ?
                """,
                (assessment_id,),
            ).fetchone()
        if row is None:
            raise AssessmentNotFoundError(
                f"Assessment {assessment_id} was not found."
            )
        try:
            trade = Trade(row[2])
        except (TypeError, ValueError):
            raise RepositoryValidationError(
                f"Assessment {assessment_id} has an unsupported trade: {row[2]!r}."
            ) from None
        if row[3] not in {"en", "te", "hi"}:
            raise RepositoryValidationError(
                f"Assessment {assessment_id} has an unsupported language: {row[3]!r}."
            )
        if row[4] not in {"IN_PROGRESS", "COMPLETED", "ABANDONED"}:
            raise RepositoryValidationError(
                f"Assessment {assessment_id} has an invalid status: {row[4]!r}."
            )
        return AssessmentRecord(
            id=row[0],
            worker_id=row[1],
            trade=trade,
            language=row[3],
            status=row[4],
            current_stage=row[5],
            total_score=row[6],
            max_score=row[7],
            score_percentage=row[8],
            safety_flags_json=_parse_json_object_or_array(
                row[9], "safety_flags_json"
            ),
            started_at=row[10],
            completed_at=row[11],
        )

    def create_assessment(
        self,
        worker_id: int,
        language: str,
        trade: Trade | str | None = None,
    ) -> AssessmentRecord:
        if type(worker_id) is not int or worker_id <= 0:
            raise RepositoryValidationError("worker_id must be a positive integer.")
        if language not in {"en", "te", "hi"}:
            raise RepositoryValidationError("language must be 'en', 'te', or 'hi'.")

        with self._database_factory() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                worker = connection.execute(
                    "SELECT trade FROM workers WHERE id = ?",
                    (worker_id,),
                ).fetchone()
                if worker is None:
                    raise WorkerNotFoundError(f"Worker {worker_id} was not found.")
                try:
                    worker_trade = Trade(worker[0])
                except (TypeError, ValueError):
                    raise RepositoryValidationError(
                        f"Worker {worker_id} has an unsupported trade: {worker[0]!r}."
                    ) from None
                if trade is not None:
                    if isinstance(trade, Trade):
                        requested_trade = trade
                    else:
                        try:
                            requested_trade = Trade(trade)
                        except (TypeError, ValueError):
                            raise RepositoryValidationError(
                                f"Unsupported trade value: {trade!r}."
                            ) from None
                    if requested_trade != worker_trade:
                        raise RepositoryValidationError(
                            "Requested trade does not match the worker trade."
                        )
                active = connection.execute(
                    """
                    SELECT id
                    FROM assessments
                    WHERE worker_id = ? AND status = 'IN_PROGRESS'
                    LIMIT 1
                    """,
                    (worker_id,),
                ).fetchone()
                if active is not None:
                    raise ActiveAssessmentExistsError(
                        f"Worker {worker_id} already has an IN_PROGRESS assessment."
                    )
                cursor = connection.execute(
                    """
                    INSERT INTO assessments (
                        worker_id, trade, language, status, current_stage,
                        max_score, safety_flags_json, started_at
                    ) VALUES (?, ?, ?, 'IN_PROGRESS', 1, 24, '[]', ?)
                    """,
                    (worker_id, worker_trade.value, language, _utc_now()),
                )
                assessment_id = cursor.lastrowid
                connection.commit()
            except WorkerNotFoundError:
                connection.rollback()
                raise
            except ActiveAssessmentExistsError:
                connection.rollback()
                raise
            except (RepositoryValidationError, TypeError, ValueError):
                connection.rollback()
                raise
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ForeignKeyIntegrityError(
                    "Assessment creation violated a database constraint."
                ) from exc
        return self.get_assessment(assessment_id)

    def add_question_assignment(
        self,
        assessment_id: int,
        question_id: str,
        stage_number: int,
        question_order: int,
        selection_reason: str,
        selected_at: str | None = None,
    ) -> QuestionAssignment:
        if type(assessment_id) is not int or assessment_id <= 0:
            raise RepositoryValidationError("assessment_id must be a positive integer.")
        question_id = _require_text(question_id, "question_id")
        selection_reason = _require_text(selection_reason, "selection_reason")
        if type(stage_number) is not int or stage_number not in (1, 2, 3):
            raise RepositoryValidationError("stage_number must be 1, 2, or 3.")
        if type(question_order) is not int or question_order not in range(1, 7):
            raise RepositoryValidationError("question_order must be from 1 through 6.")
        timestamp = selected_at or _utc_now()
        timestamp = _require_text(timestamp, "selected_at")

        with self._database_factory() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                assessment = connection.execute(
                    "SELECT status, trade FROM assessments WHERE id = ?",
                    (assessment_id,),
                ).fetchone()
                if assessment is None:
                    raise AssessmentNotFoundError(
                        f"Assessment {assessment_id} was not found."
                    )
                if assessment[0] != "IN_PROGRESS":
                    raise RepositoryValidationError(
                        "Questions can only be assigned to an IN_PROGRESS assessment."
                    )
                question = connection.execute(
                    "SELECT trade, active FROM questions WHERE question_id = ?",
                    (question_id,),
                ).fetchone()
                if question is None:
                    raise RepositoryValidationError(
                        f"Question {question_id!r} was not found."
                    )
                if question[0] != assessment[1]:
                    raise RepositoryValidationError(
                        "Question trade does not match the assessment trade."
                    )
                if question[1] != 1:
                    raise RepositoryValidationError(
                        f"Question {question_id!r} is not active."
                    )
                cursor = connection.execute(
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
                        selection_reason,
                        timestamp,
                    ),
                )
                assignment_id = cursor.lastrowid
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                message = str(exc).lower()
                if "assessment_question" in message:
                    raise DuplicateAssignmentError(
                        "Question or question order is already assigned."
                    ) from exc
                raise ForeignKeyIntegrityError(
                    "Question assignment violated a database constraint."
                ) from exc
            except RepositoryError:
                connection.rollback()
                raise
            except RepositoryValidationError:
                connection.rollback()
                raise
        return self.get_question_assignment(assessment_id, question_id)

    def add_question_assignments(
        self,
        assessment_id: int,
        assignments: Sequence[tuple[str, int, int, str]],
    ) -> tuple[QuestionAssignment, ...]:
        """Atomically persist a complete set of question assignments."""
        if type(assessment_id) is not int or assessment_id <= 0:
            raise RepositoryValidationError("assessment_id must be a positive integer.")
        if isinstance(assignments, (str, bytes)):
            raise RepositoryValidationError("assignments must be a sequence.")
        if not isinstance(assignments, Sequence) or not assignments:
            raise RepositoryValidationError(
                "assignments must be a non-empty sequence."
            )

        seen_questions: set[str] = set()
        seen_orders: set[int] = set()
        normalized: list[tuple[str, int, int, str, str]] = []
        for assignment in assignments:
            if not isinstance(assignment, tuple) or len(assignment) != 4:
                raise RepositoryValidationError(
                    "Each assignment must contain question_id, stage_number, "
                    "question_order, and selection_reason."
                )
            question_id, stage_number, question_order, reason = assignment
            question_id = _require_text(question_id, "question_id")
            reason = _require_text(reason, "selection_reason")
            if type(stage_number) is not int or stage_number not in (1, 2, 3):
                raise RepositoryValidationError("stage_number must be 1, 2, or 3.")
            if type(question_order) is not int or question_order not in range(1, 7):
                raise RepositoryValidationError("question_order must be from 1 through 6.")
            if question_id in seen_questions:
                raise DuplicateAssignmentError(
                    f"Question {question_id!r} is assigned more than once."
                )
            if question_order in seen_orders:
                raise DuplicateAssignmentError(
                    f"Question order {question_order} is assigned more than once."
                )
            seen_questions.add(question_id)
            seen_orders.add(question_order)
            normalized.append(
                (question_id, stage_number, question_order, reason, _utc_now())
            )

        with self._database_factory() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                assessment = connection.execute(
                    "SELECT status, trade FROM assessments WHERE id = ?",
                    (assessment_id,),
                ).fetchone()
                if assessment is None:
                    raise AssessmentNotFoundError(
                        f"Assessment {assessment_id} was not found."
                    )
                if assessment[0] != "IN_PROGRESS":
                    raise RepositoryValidationError(
                        "Questions can only be assigned to an IN_PROGRESS assessment."
                    )
                for question_id, stage_number, question_order, reason, timestamp in normalized:
                    question = connection.execute(
                        "SELECT trade, active FROM questions WHERE question_id = ?",
                        (question_id,),
                    ).fetchone()
                    if question is None:
                        raise RepositoryValidationError(
                            f"Question {question_id!r} was not found."
                        )
                    if question[0] != assessment[1] or question[1] != 1:
                        raise RepositoryValidationError(
                            f"Question {question_id!r} is unavailable for this assessment."
                        )
                    connection.execute(
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
                            reason,
                            timestamp,
                        ),
                    )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                message = str(exc).lower()
                if "unique" in message or "assessment_question" in message:
                    raise DuplicateAssignmentError(
                        "Question or question order is already assigned."
                    ) from exc
                raise ForeignKeyIntegrityError(
                    "Question assignment violated a database constraint."
                ) from exc
            except (RepositoryError, RepositoryValidationError):
                connection.rollback()
                raise
        return tuple(
            self.get_question_assignment(assessment_id, question_id)
            for question_id, *_ in normalized
        )

    def get_question_assignment(
        self,
        assessment_id: int,
        question_id: str,
    ) -> QuestionAssignment:
        with self._database_factory() as connection:
            row = connection.execute(
                """
                SELECT id, assessment_id, question_id, stage_number,
                       question_order, selection_reason, selected_at
                FROM assessment_questions
                WHERE assessment_id = ? AND question_id = ?
                """,
                (assessment_id, question_id),
            ).fetchone()
        if row is None:
            raise RepositoryValidationError(
                f"Question {question_id!r} is not assigned to assessment "
                f"{assessment_id}."
            )
        return QuestionAssignment(*row)

    def get_assigned_questions(
        self,
        assessment_id: int,
    ) -> tuple[QuestionAssignment, ...]:
        with self._database_factory() as connection:
            rows = connection.execute(
                """
                SELECT id, assessment_id, question_id, stage_number,
                       question_order, selection_reason, selected_at
                FROM assessment_questions
                WHERE assessment_id = ?
                ORDER BY question_order
                """,
                (assessment_id,),
            ).fetchall()
        return tuple(QuestionAssignment(*row) for row in rows)

    def get_question(self, question_id: str) -> AssessmentQuestion:
        question_id = _require_text(question_id, "question_id")
        with self._database_factory() as connection:
            row = connection.execute(
                """
                SELECT question_id, trade, difficulty, skill_tag, question_text_en,
                       question_text_te, question_text_hi, expected_concepts_json,
                       rubric_json, safety_critical, active,
                       telugu_review_required, hindi_review_required
                FROM questions
                WHERE question_id = ?
                """,
                (question_id,),
            ).fetchone()
        if row is None:
            raise RepositoryValidationError(
                f"Question {question_id!r} was not found."
            )
        return self._hydrate_question(row)

    def get_assigned_assessment_question(
        self,
        assessment_id: int,
        question_id: str,
    ) -> AssessmentQuestion:
        assignment = self.get_question_assignment(assessment_id, question_id)
        question = self.get_question(question_id)
        if assignment.stage_number not in (1, 2, 3):
            raise RepositoryValidationError("Assigned question has an invalid stage.")
        return question

    @staticmethod
    def _hydrate_question(row: Sequence[Any]) -> AssessmentQuestion:
        question_id = row[0]
        try:
            trade = Trade(row[1])
            difficulty = Difficulty(row[2])
        except (TypeError, ValueError) as exc:
            raise RepositoryValidationError(
                f"Question {question_id!r} has invalid trade or difficulty."
            ) from exc
        try:
            concepts = json.loads(row[7])
            rubric = json.loads(row[8])
        except (TypeError, json.JSONDecodeError) as exc:
            raise RepositoryValidationError(
                f"Question {question_id!r} has invalid stored JSON."
            ) from exc
        if not isinstance(concepts, list) or not concepts or any(
            not isinstance(concept, str) or not concept.strip()
            for concept in concepts
        ):
            raise RepositoryValidationError(
                f"Question {question_id!r} has invalid expected concepts."
            )
        if not isinstance(rubric, dict) or set(rubric) != {"0", "1", "2", "3", "4"}:
            raise RepositoryValidationError(
                f"Question {question_id!r} has an invalid rubric."
            )
        if any(not isinstance(text, str) or not text.strip() for text in rubric.values()):
            raise RepositoryValidationError(
                f"Question {question_id!r} has an invalid rubric description."
            )
        for index in (9, 10, 11, 12):
            if row[index] not in (0, 1):
                raise RepositoryValidationError(
                    f"Question {question_id!r} has an invalid Boolean value."
                )
        for index, field in ((3, "skill_tag"), (4, "question_text_en"),
                             (5, "question_text_te"), (6, "question_text_hi")):
            if not isinstance(row[index], str) or not row[index].strip():
                raise RepositoryValidationError(
                    f"Question {question_id!r} has invalid {field}."
                )
        return AssessmentQuestion(
            question_id=question_id,
            difficulty=difficulty,
            trade=trade,
            skill_tag=row[3],
            question_text_en=row[4],
            question_text_te=row[5],
            question_text_hi=row[6],
            expected_concepts=tuple(concepts),
            rubric_json=rubric,
            safety_critical=bool(row[9]),
            active=bool(row[10]),
            telugu_review_required=bool(row[11]),
            hindi_review_required=bool(row[12]),
        )

    def insert_answer(
        self,
        assessment_id: int,
        question_id: str,
        stage_number: int,
        answer_text: str,
        answer_source: str,
        score: int,
        rubric_feedback_json: Mapping[str, Any],
        safety_flag: bool,
        safety_reason: str | None,
        safety_concerns_json: list[Any] | tuple[Any, ...],
    ) -> AnswerRecord:
        if type(assessment_id) is not int or assessment_id <= 0:
            raise RepositoryValidationError("assessment_id must be a positive integer.")
        question_id = _require_text(question_id, "question_id")
        answer_text = _require_text(answer_text, "answer_text")
        if answer_source not in {"VOICE", "TEXT"}:
            raise RepositoryValidationError("answer_source must be 'VOICE' or 'TEXT'.")
        if type(stage_number) is not int or stage_number not in (1, 2, 3):
            raise RepositoryValidationError("stage_number must be 1, 2, or 3.")
        if type(score) is not int or not 0 <= score <= 4:
            raise RepositoryValidationError("score must be an integer from 0 through 4.")
        if type(safety_flag) is not bool:
            raise RepositoryValidationError("safety_flag must be a Boolean.")
        if safety_reason is not None:
            safety_reason = _require_text(safety_reason, "safety_reason")
        feedback_json = _serialize_json(rubric_feedback_json, "rubric_feedback_json")
        concerns_json = _serialize_json(safety_concerns_json, "safety_concerns_json")

        with self._database_factory() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                assessment = connection.execute(
                    "SELECT status, current_stage FROM assessments WHERE id = ?",
                    (assessment_id,),
                ).fetchone()
                if assessment is None:
                    raise AssessmentNotFoundError(
                        f"Assessment {assessment_id} was not found."
                    )
                if assessment[0] != "IN_PROGRESS":
                    raise RepositoryValidationError(
                        "Answers can only be inserted for an IN_PROGRESS assessment."
                    )
                assignment = connection.execute(
                    """
                    SELECT stage_number
                    FROM assessment_questions
                    WHERE assessment_id = ? AND question_id = ?
                    """,
                    (assessment_id, question_id),
                ).fetchone()
                if assignment is None:
                    raise RepositoryValidationError(
                        "Question is not assigned to this assessment."
                    )
                if assignment[0] != stage_number:
                    raise RepositoryValidationError(
                        "Answer stage_number does not match the assigned stage."
                    )
                if assignment[0] != assessment[1]:
                    raise RepositoryValidationError(
                        "Answers cannot be submitted for a stage that is not current."
                    )
                duplicate = connection.execute(
                    """
                    SELECT id
                    FROM assessment_answers
                    WHERE assessment_id = ? AND question_id = ?
                    """,
                    (assessment_id, question_id),
                ).fetchone()
                if duplicate is not None:
                    raise DuplicateAnswerError(
                        "An answer already exists for this assessment and question."
                    )
                cursor = connection.execute(
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
                        answer_text,
                        answer_source,
                        score,
                        feedback_json,
                        int(safety_flag),
                        safety_reason,
                        concerns_json,
                        _utc_now(),
                    ),
                )
                answer_id = cursor.lastrowid
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                message = str(exc).lower()
                if "unique" in message or "assessment_answer" in message:
                    raise DuplicateAnswerError(
                        "An answer already exists for this assessment and question."
                    ) from exc
                raise ForeignKeyIntegrityError(
                    "Answer insertion violated a database constraint."
                ) from exc
            except (RepositoryError, RepositoryValidationError):
                connection.rollback()
                raise
        return self.get_answer(assessment_id, question_id)

    def get_answer(
        self,
        assessment_id: int,
        question_id: str,
    ) -> AnswerRecord:
        with self._database_factory() as connection:
            row = connection.execute(
                """
                SELECT id, assessment_id, question_id, stage_number, answer_text,
                       answer_source, score, rubric_feedback_json, safety_flag,
                       safety_reason, safety_concerns_json, answered_at
                FROM assessment_answers
                WHERE assessment_id = ? AND question_id = ?
                """,
                (assessment_id, question_id),
            ).fetchone()
        if row is None:
            raise RepositoryValidationError(
                f"Answer for question {question_id!r} was not found."
            )
        feedback = _parse_json_object_or_array(
            row[7], "rubric_feedback_json"
        )
        concerns = _parse_json_object_or_array(
            row[10], "safety_concerns_json"
        )
        if not isinstance(feedback, dict):
            raise RepositoryValidationError(
                "Stored rubric_feedback_json must be a JSON object."
            )
        if not isinstance(concerns, list):
            raise RepositoryValidationError(
                "Stored safety_concerns_json must be a JSON array."
            )
        return AnswerRecord(
            id=row[0],
            assessment_id=row[1],
            question_id=row[2],
            stage_number=row[3],
            answer_text=row[4],
            answer_source=row[5],
            score=row[6],
            rubric_feedback=feedback,
            safety_flag=bool(row[8]),
            safety_reason=row[9],
            safety_concerns=concerns,
            answered_at=row[11],
        )

    def get_answers(
        self,
        assessment_id: int,
    ) -> tuple[AnswerRecord, ...]:
        with self._database_factory() as connection:
            rows = connection.execute(
                """
                SELECT id, assessment_id, question_id, stage_number, answer_text,
                       answer_source, score, rubric_feedback_json, safety_flag,
                       safety_reason, safety_concerns_json, answered_at
                FROM assessment_answers
                WHERE assessment_id = ?
                ORDER BY (
                    SELECT question_order
                    FROM assessment_questions
                    WHERE assessment_questions.assessment_id = assessment_answers.assessment_id
                      AND assessment_questions.question_id = assessment_answers.question_id
                )
                """,
                (assessment_id,),
            ).fetchall()
        return tuple(
            self.get_answer(assessment_id, row[2])
            for row in rows
        )

    def get_assessment_progress(
        self,
        assessment_id: int,
    ) -> AssessmentProgress:
        assessment = self.get_assessment(assessment_id)
        assignments = self.get_assigned_questions(assessment_id)
        answers = self.get_answers(assessment_id)
        stage2_difficulty: Difficulty | None = None
        stage2_assignments = [
            assignment
            for assignment in assignments
            if assignment.stage_number == 2
        ]
        if stage2_assignments:
            difficulties: set[Difficulty] = set()
            for assignment in stage2_assignments:
                question = self.get_question(assignment.question_id)
                difficulties.add(question.difficulty)
            if len(difficulties) != 1:
                raise RepositoryValidationError(
                    "Stage 2 assignments must use exactly one difficulty."
                )
            stage2_difficulty = next(iter(difficulties))
            if stage2_difficulty == Difficulty.ADVANCED:
                raise RepositoryValidationError(
                    "Stage 2 cannot use ADVANCED questions."
                )
        return AssessmentProgress(
            assessment=assessment,
            assignments=assignments,
            answers=answers,
            stage2_difficulty=stage2_difficulty,
        )

    def advance_assessment_stage(
        self,
        assessment_id: int,
        stage_number: int,
    ) -> AssessmentRecord:
        if type(stage_number) is not int or stage_number not in (2, 3):
            raise RepositoryValidationError("stage_number must be 2 or 3.")
        with self._database_factory() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT status, current_stage FROM assessments WHERE id = ?",
                    (assessment_id,),
                ).fetchone()
                if row is None:
                    raise AssessmentNotFoundError(
                        f"Assessment {assessment_id} was not found."
                    )
                if row[0] != "IN_PROGRESS":
                    raise RepositoryValidationError(
                        "Only IN_PROGRESS assessments can advance."
                    )
                expected_stage = row[1] + 1
                if stage_number != expected_stage:
                    raise RepositoryValidationError(
                        f"Assessment must advance to stage {expected_stage}, "
                        f"not {stage_number}."
                    )
                assignment_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM assessment_questions
                    WHERE assessment_id = ? AND stage_number = ?
                    """,
                    (assessment_id, row[1]),
                ).fetchone()[0]
                if assignment_count != 2:
                    raise RepositoryValidationError(
                        f"Stage {row[1]} must have exactly two assigned questions "
                        f"before advancement."
                    )
                answer_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM assessment_answers
                    WHERE assessment_id = ? AND stage_number = ?
                    """,
                    (assessment_id, row[1]),
                ).fetchone()[0]
                if answer_count != 2:
                    raise RepositoryValidationError(
                        f"Stage {row[1]} must have exactly two persisted answers "
                        f"before advancement."
                    )
                connection.execute(
                    "UPDATE assessments SET current_stage = ? WHERE id = ?",
                    (stage_number, assessment_id),
                )
                connection.commit()
            except (RepositoryError, RepositoryValidationError):
                connection.rollback()
                raise
        return self.get_assessment(assessment_id)

    def persist_final_result(
        self,
        assessment_id: int,
        total_score: int,
        max_score: int,
        score_percentage: float | Decimal,
        safety_flags_json: Mapping[str, Any] | list[Any],
    ) -> AssessmentResult:
        if type(total_score) is not int or not 0 <= total_score <= 24:
            raise RepositoryValidationError(
                "total_score must be an integer from 0 through 24."
            )
        if type(max_score) is not int or max_score != 24:
            raise RepositoryValidationError("max_score must be 24.")
        if isinstance(score_percentage, Decimal):
            percentage = float(score_percentage)
        elif type(score_percentage) in (int, float):
            percentage = float(score_percentage)
        else:
            raise RepositoryValidationError(
                "score_percentage must be a numeric Decimal or float."
            )
        if not 0 <= percentage <= 100:
            raise RepositoryValidationError(
                "score_percentage must be from 0 through 100."
            )
        safety_json = _serialize_json(
            safety_flags_json, "safety_flags_json"
        )

        with self._database_factory() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT status, current_stage FROM assessments WHERE id = ?",
                    (assessment_id,),
                ).fetchone()
                if row is None:
                    raise AssessmentNotFoundError(
                        f"Assessment {assessment_id} was not found."
                    )
                if row[0] != "IN_PROGRESS":
                    raise RepositoryValidationError(
                        "Only IN_PROGRESS assessments can be completed."
                    )
                if row[1] != 3:
                    raise RepositoryValidationError(
                        "Assessment completion requires the assessment to be at Stage 3."
                    )

                assignment_count = connection.execute(
                    "SELECT COUNT(*) FROM assessment_questions WHERE assessment_id = ?",
                    (assessment_id,),
                ).fetchone()[0]
                answer_count = connection.execute(
                    "SELECT COUNT(*) FROM assessment_answers WHERE assessment_id = ?",
                    (assessment_id,),
                ).fetchone()[0]
                if assignment_count != 6 or answer_count != 6:
                    raise RepositoryValidationError(
                        "Assessment completion requires six assignments and six answers."
                    )
                stage_counts = connection.execute(
                    """
                    SELECT stage_number, COUNT(*)
                    FROM assessment_questions
                    WHERE assessment_id = ?
                    GROUP BY stage_number
                    """,
                    (assessment_id,),
                ).fetchall()
                if (
                    len(stage_counts) != 3
                    or any(count != 2 for _, count in stage_counts)
                    or {stage for stage, _ in stage_counts} != {1, 2, 3}
                ):
                    raise RepositoryValidationError(
                        "Assessment must contain exactly two questions in each stage."
                    )
                orders = connection.execute(
                    """
                    SELECT question_order
                    FROM assessment_questions
                    WHERE assessment_id = ?
                    """,
                    (assessment_id,),
                ).fetchall()
                if sorted(order[0] for order in orders) != list(range(1, 7)):
                    raise RepositoryValidationError(
                        "Assessment question orders must be exactly 1 through 6."
                    )
                answer_stage_counts = connection.execute(
                    """
                    SELECT stage_number, COUNT(*)
                    FROM assessment_answers
                    WHERE assessment_id = ?
                    GROUP BY stage_number
                    """,
                    (assessment_id,),
                ).fetchall()
                if (
                    len(answer_stage_counts) != 3
                    or any(count != 2 for _, count in answer_stage_counts)
                ):
                    raise RepositoryValidationError(
                        "Assessment must contain exactly two answers in each stage."
                    )
                persisted_scores = connection.execute(
                    """
                    SELECT score
                    FROM assessment_answers
                    WHERE assessment_id = ?
                    """,
                    (assessment_id,),
                ).fetchall()
                persisted_total = sum(row[0] for row in persisted_scores)
                if persisted_total != total_score:
                    raise RepositoryValidationError(
                        "total_score does not match the sum of persisted answer scores."
                    )
                calculated_percentage = (
                    Decimal(persisted_total) * Decimal(100) / Decimal(24)
                ).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)
                if isinstance(score_percentage, Decimal):
                    supplied_percentage = score_percentage
                elif type(score_percentage) is int:
                    supplied_percentage = Decimal(score_percentage)
                elif type(score_percentage) is float:
                    supplied_percentage = Decimal(str(score_percentage))
                else:
                    raise RepositoryValidationError(
                        "score_percentage must be a numeric Decimal or float."
                    )
                if supplied_percentage != calculated_percentage:
                    raise RepositoryValidationError(
                        "score_percentage does not match the calculated assessment percentage."
                    )

                completed_at = _utc_now()
                connection.execute(
                    """
                    UPDATE assessments
                    SET status = 'COMPLETED',
                        total_score = ?,
                        max_score = 24,
                        score_percentage = ?,
                        safety_flags_json = ?,
                        completed_at = ?
                    WHERE id = ?
                    """,
                    (
                        total_score,
                        percentage,
                        safety_json,
                        completed_at,
                        assessment_id,
                    ),
                )
                connection.commit()
            except (RepositoryError, RepositoryValidationError):
                connection.rollback()
                raise
        assessment = self.get_assessment(assessment_id)
        if assessment.completed_at is None:
            raise RepositoryValidationError(
                "Completed assessment is missing its completed_at timestamp."
            )
        return AssessmentResult(
            assessment_id=assessment_id,
            status="COMPLETED",
            total_score=assessment.total_score or 0,
            maximum_score=assessment.max_score,
            score_percentage=assessment.score_percentage or 0.0,
            safety_flags=assessment.safety_flags_json,
            completed_at=assessment.completed_at,
        )

    def get_assessment_result(
        self,
        assessment_id: int,
    ) -> AssessmentResult:
        assessment = self.get_assessment(assessment_id)
        if assessment.status != "COMPLETED":
            raise RepositoryValidationError(
                "Assessment result is available only after completion."
            )
        if (
            assessment.total_score is None
            or assessment.score_percentage is None
            or assessment.completed_at is None
        ):
            raise RepositoryValidationError(
                "Completed assessment is missing final result fields."
            )
        return AssessmentResult(
            assessment_id=assessment_id,
            status=assessment.status,
            total_score=assessment.total_score,
            maximum_score=assessment.max_score,
            score_percentage=assessment.score_percentage,
            safety_flags=assessment.safety_flags_json,
            completed_at=assessment.completed_at,
        )
