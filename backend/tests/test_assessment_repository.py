"""Focused tests for the SQLite assessment repository."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import sqlite3

import pytest

import main
from assessment.adaptive_engine import Difficulty, Trade
from assessment.question_bank import AssessmentQuestion
from assessment.repository import (
    ActiveAssessmentExistsError,
    AssessmentNotFoundError,
    AssessmentRepository,
    DuplicateAnswerError,
    DuplicateAssignmentError,
    ForeignKeyIntegrityError,
    RepositoryValidationError,
    WorkerNotFoundError,
)


@pytest.fixture
def repository(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "repository.db")
    main.init_db()
    return AssessmentRepository(main.db)


def insert_worker(connection, name="Repository Worker"):
    cursor = connection.execute(
        """
        INSERT INTO workers (
            name, language, location, raw_transcript, trade,
            experience_years, evidence_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            "en",
            "Hyderabad",
            "I have electrical experience.",
            "Electrician",
            4,
            "SELF_REPORTED",
        ),
    )
    return cursor.lastrowid


def setup_six_answer_assessment(repository, worker_id, scores=None):
    assessment = repository.create_assessment(worker_id, "en")
    assignments = [
        ("E01", 1, 1, "Stage 1"),
        ("E02", 1, 2, "Stage 1"),
        ("E05", 2, 3, "Stage 2"),
        ("E06", 2, 4, "Stage 2"),
        ("E09", 3, 5, "Stage 3"),
        ("E10", 3, 6, "Stage 3"),
    ]
    repository.add_question_assignments(assessment.id, assignments)
    answer_scores = scores or [3, 3, 3, 3, 3, 3]
    for (question_id, stage_number, _, _), score in zip(assignments[:2], answer_scores[:2]):
        repository.insert_answer(
            assessment.id,
            question_id,
            stage_number,
            "Worker answer",
            "TEXT",
            score,
            {"feedback": "Feedback"},
            False,
            None,
            [],
        )
    repository.advance_assessment_stage(assessment.id, 2)
    for (question_id, stage_number, _, _), score in zip(assignments[2:4], answer_scores[2:4]):
        repository.insert_answer(
            assessment.id,
            question_id,
            stage_number,
            "Worker answer",
            "TEXT",
            score,
            {"feedback": "Feedback"},
            False,
            None,
            [],
        )
    repository.advance_assessment_stage(assessment.id, 3)
    for (question_id, stage_number, _, _), score in zip(assignments[4:], answer_scores[4:]):
        repository.insert_answer(
            assessment.id,
            question_id,
            stage_number,
            "Worker answer",
            "TEXT",
            score,
            {"feedback": "Feedback"},
            False,
            None,
            [],
        )
    return assessment


def test_existing_worker_lookup(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
        connection.execute(
            """
            INSERT INTO worker_skills (worker_id, skill_name, evidence_level)
            VALUES (?, ?, ?)
            """,
            (worker_id, "Wiring repair", "SELF_REPORTED"),
        )

    worker = repository.get_worker(worker_id)

    assert worker.id == worker_id
    assert worker.trade == Trade.ELECTRICIAN
    assert worker.evidence_level == "SELF_REPORTED"


def test_unknown_worker_lookup_raises_clear_error(repository):
    with pytest.raises(WorkerNotFoundError, match="Worker 9999"):
        repository.get_worker(9999)


def test_assessment_creation_persists_expected_state(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)

    assessment = repository.create_assessment(
        worker_id,
        "en",
        Trade.ELECTRICIAN,
    )

    assert assessment.worker_id == worker_id
    assert assessment.trade == Trade.ELECTRICIAN
    assert assessment.status == "IN_PROGRESS"
    assert assessment.current_stage == 1
    assert assessment.max_score == 24
    assert assessment.total_score is None
    assert assessment.score_percentage is None
    assert assessment.completed_at is None


def test_duplicate_active_assessment_is_prevented(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)

    repository.create_assessment(worker_id, "te")

    with pytest.raises(ActiveAssessmentExistsError, match="IN_PROGRESS"):
        repository.create_assessment(worker_id, "hi")


def test_new_assessment_can_start_after_completion(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)

    first = repository.create_assessment(worker_id, "en")
    assignments = [
        ("E01", 1, 1, "Stage 1 foundational"),
        ("E02", 1, 2, "Stage 1 foundational"),
        ("E03", 2, 3, "Stage 2 selection"),
        ("E04", 2, 4, "Stage 2 selection"),
        ("E05", 3, 5, "Stage 3 selection"),
        ("E06", 3, 6, "Stage 3 selection"),
    ]
    repository.add_question_assignments(first.id, assignments)
    for question_id, stage_number, _, _ in assignments[:2]:
        repository.insert_answer(
            first.id,
            question_id,
            stage_number,
            "A complete worker answer.",
            "TEXT",
            3,
            {"feedback": "Meaningful feedback"},
            False,
            None,
            [],
        )
    repository.advance_assessment_stage(first.id, 2)
    for question_id, stage_number, _, _ in assignments[2:4]:
        repository.insert_answer(
            first.id,
            question_id,
            stage_number,
            "A complete worker answer.",
            "TEXT",
            3,
            {"feedback": "Meaningful feedback"},
            False,
            None,
            [],
        )
    repository.advance_assessment_stage(first.id, 3)
    for question_id, stage_number, _, _ in assignments[4:]:
        repository.insert_answer(
            first.id,
            question_id,
            stage_number,
            "A complete worker answer.",
            "TEXT",
            3,
            {"feedback": "Meaningful feedback"},
            False,
            None,
            [],
        )

    repository.persist_final_result(
        first.id,
        total_score=18,
        max_score=24,
        score_percentage=Decimal("75.00"),
        safety_flags_json={"safety_critical": False, "concerns": []},
    )
    second = repository.create_assessment(worker_id, "hi")

    assert second.id != first.id
    assert second.status == "IN_PROGRESS"


def test_question_assignment_persistence_and_hydration(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "hi")

    assignment = repository.add_question_assignment(
        assessment.id,
        "E01",
        1,
        1,
        "Initial foundational selection",
    )
    hydrated = repository.get_assigned_assessment_question(
        assessment.id,
        "E01",
    )

    assert assignment.question_id == "E01"
    assert assignment.stage_number == 1
    assert assignment.question_order == 1
    assert isinstance(hydrated, AssessmentQuestion)
    assert hydrated.question_id == "E01"
    assert hydrated.trade == Trade.ELECTRICIAN
    assert hydrated.difficulty == Difficulty.FOUNDATIONAL
    assert hydrated.question_text_hi
    assert hydrated.expected_concepts
    assert set(hydrated.rubric_json) == {"0", "1", "2", "3", "4"}


def test_assignment_bulk_insert_rolls_back_on_second_invalid_question(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")

    with pytest.raises(RepositoryValidationError, match="not found"):
        repository.add_question_assignments(
            assessment.id,
            [
                ("E01", 1, 1, "Valid first selection"),
                ("X99", 1, 2, "Invalid second selection"),
            ],
        )

    assert repository.get_assigned_questions(assessment.id) == ()


def test_duplicate_question_assignment_is_rejected(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    repository.add_question_assignment(
        assessment.id, "E01", 1, 1, "First assignment"
    )

    with pytest.raises(DuplicateAssignmentError):
        repository.add_question_assignment(
            assessment.id, "E01", 1, 2, "Duplicate assignment"
        )


def test_duplicate_question_order_is_rejected(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    repository.add_question_assignment(
        assessment.id, "E01", 1, 1, "First assignment"
    )

    with pytest.raises(DuplicateAssignmentError):
        repository.add_question_assignment(
            assessment.id, "E02", 1, 1, "Duplicate order"
        )


def test_answer_insertion_retrieval_and_duplicate_rejection(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    repository.add_question_assignment(
        assessment.id, "E01", 1, 1, "Foundational selection"
    )

    answer = repository.insert_answer(
        assessment.id,
        "E01",
        1,
        "I would isolate the supply and verify no voltage.",
        "VOICE",
        4,
        {"feedback": "Accurate isolation procedure"},
        False,
        None,
        [{"concern": "No concern", "evidence": "isolated"}],
    )

    assert answer.score == 4
    assert answer.answer_source == "VOICE"
    assert answer.safety_flag is False
    assert repository.get_answer(assessment.id, "E01") == answer

    with pytest.raises(DuplicateAnswerError):
        repository.insert_answer(
            assessment.id,
            "E01",
            1,
            "A second answer.",
            "TEXT",
            2,
            {"feedback": "Duplicate"},
            False,
            None,
            [],
        )


def test_answer_stage_must_match_assignment(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    repository.add_question_assignment(
        assessment.id, "E01", 1, 1, "Foundational selection"
    )

    with pytest.raises(RepositoryValidationError, match="does not match"):
        repository.insert_answer(
            assessment.id,
            "E01",
            2,
            "Worker answer",
            "TEXT",
            2,
            {"feedback": "Valid shape"},
            False,
            None,
            [],
        )


def test_answer_for_future_stage_is_rejected_before_advancement(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    repository.add_question_assignment(
        assessment.id, "E05", 2, 3, "Future stage selection"
    )

    with pytest.raises(
        RepositoryValidationError,
        match="stage that is not current",
    ):
        repository.insert_answer(
            assessment.id,
            "E05",
            2,
            "Worker answer",
            "TEXT",
            2,
            {"feedback": "Valid shape"},
            False,
            None,
            [],
        )


@pytest.mark.parametrize("answer_count", [0, 1], ids=["zero-answers", "one-answer"])
def test_stage_advancement_requires_two_answers(repository, answer_count):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    repository.add_question_assignment(
        assessment.id, "E01", 1, 1, "First Stage 1 question"
    )
    repository.add_question_assignment(
        assessment.id, "E02", 1, 2, "Second Stage 1 question"
    )

    for question_id in ("E01",)[:answer_count]:
        repository.insert_answer(
            assessment.id,
            question_id,
            1,
            "Worker answer",
            "TEXT",
            3,
            {"feedback": "Feedback"},
            False,
            None,
            [],
        )

    with pytest.raises(
        RepositoryValidationError,
        match=r"Stage 1 must have exactly two persisted answers",
    ):
        repository.advance_assessment_stage(assessment.id, 2)

    progress = repository.get_assessment_progress(assessment.id)
    assert progress.assessment.current_stage == 1
    assert len(progress.assignments) == 2
    assert len(progress.answers) == answer_count


def test_stage_advancement_requires_two_assigned_questions(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    repository.add_question_assignment(
        assessment.id, "E01", 1, 1, "Only Stage 1 question"
    )

    with pytest.raises(
        RepositoryValidationError,
        match=r"Stage 1 must have exactly two assigned questions",
    ):
        repository.advance_assessment_stage(assessment.id, 2)


def test_stage_advancement_succeeds_after_two_assignments_and_answers(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    repository.add_question_assignment(
        assessment.id, "E01", 1, 1, "First Stage 1 question"
    )
    repository.add_question_assignment(
        assessment.id, "E02", 1, 2, "Second Stage 1 question"
    )
    for question_id in ("E01", "E02"):
        repository.insert_answer(
            assessment.id,
            question_id,
            1,
            "Worker answer",
            "TEXT",
            3,
            {"feedback": "Feedback"},
            False,
            None,
            [],
        )

    advanced = repository.advance_assessment_stage(assessment.id, 2)

    assert advanced.status == "IN_PROGRESS"
    assert advanced.current_stage == 2


def test_assessment_progress_retrieval(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    repository.add_question_assignments(
        assessment.id,
        [
            ("E01", 1, 1, "Stage 1"),
            ("E02", 1, 2, "Stage 1"),
            ("E05", 2, 3, "Stage 2"),
            ("E06", 2, 4, "Stage 2"),
        ],
    )
    repository.insert_answer(
        assessment.id,
        "E01",
        1,
        "Worker answer",
        "TEXT",
        3,
        {"feedback": "Feedback"},
        False,
        None,
        [],
    )

    progress = repository.get_assessment_progress(assessment.id)

    assert progress.assessment.id == assessment.id
    assert len(progress.assignments) == 4
    assert len(progress.answers) == 1
    assert progress.stage2_difficulty == Difficulty.INTERMEDIATE


def test_final_result_persistence_and_retrieval(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    assignments = [
        ("E01", 1, 1, "Stage 1"),
        ("E02", 1, 2, "Stage 1"),
        ("E05", 2, 3, "Stage 2"),
        ("E06", 2, 4, "Stage 2"),
        ("E09", 3, 5, "Stage 3"),
        ("E10", 3, 6, "Stage 3"),
    ]
    repository.add_question_assignments(assessment.id, assignments)
    for question_id, stage_number, _, _ in assignments[:2]:
        repository.insert_answer(
            assessment.id,
            question_id,
            stage_number,
            "A complete worker answer.",
            "TEXT",
            3,
            {"feedback": "Meaningful feedback"},
            False,
            None,
            [],
        )
    repository.advance_assessment_stage(assessment.id, 2)
    for question_id, stage_number, _, _ in assignments[2:4]:
        repository.insert_answer(
            assessment.id,
            question_id,
            stage_number,
            "A complete worker answer.",
            "TEXT",
            3,
            {"feedback": "Meaningful feedback"},
            False,
            None,
            [],
        )
    repository.advance_assessment_stage(assessment.id, 3)
    for question_id, stage_number, _, _ in assignments[4:]:
        repository.insert_answer(
            assessment.id,
            question_id,
            stage_number,
            "A complete worker answer.",
            "TEXT",
            3,
            {"feedback": "Meaningful feedback"},
            False,
            None,
            [],
        )

    result = repository.persist_final_result(
        assessment.id,
        total_score=18,
        max_score=24,
        score_percentage=Decimal("75.00"),
        safety_flags_json={
            "safety_critical_misconception": False,
            "concerns": [],
        },
    )
    retrieved = repository.get_assessment_result(assessment.id)

    assert result.status == "COMPLETED"
    assert result.total_score == 18
    assert result.maximum_score == 24
    assert result.score_percentage == 75.0
    assert retrieved == result


def test_incorrect_persisted_total_score_is_rejected(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = setup_six_answer_assessment(
        repository,
        worker_id,
        scores=[3, 3, 3, 3, 3, 3],
    )

    with pytest.raises(
        RepositoryValidationError,
        match="does not match the sum of persisted answer scores",
    ):
        repository.persist_final_result(
            assessment.id,
            total_score=17,
            max_score=24,
            score_percentage=Decimal("75.00"),
            safety_flags_json={"concerns": []},
        )


def test_incorrect_persisted_percentage_is_rejected(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = setup_six_answer_assessment(
        repository,
        worker_id,
        scores=[3, 3, 3, 3, 3, 3],
    )

    with pytest.raises(
        RepositoryValidationError,
        match="does not match the calculated assessment percentage",
    ):
        repository.persist_final_result(
            assessment.id,
            total_score=18,
            max_score=24,
            score_percentage=Decimal("74.99"),
            safety_flags_json={"concerns": []},
        )


def test_correct_persisted_total_and_percentage_are_accepted(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = setup_six_answer_assessment(
        repository,
        worker_id,
        scores=[4, 4, 4, 4, 3, 3],
    )

    result = repository.persist_final_result(
        assessment.id,
        total_score=22,
        max_score=24,
        score_percentage=Decimal("91.67"),
        safety_flags_json={"concerns": []},
    )

    assert result.total_score == 22
    assert result.score_percentage == 91.67


def test_completion_is_rejected_before_stage_three(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    assignments = [
        ("E01", 1, 1, "Stage 1"),
        ("E02", 1, 2, "Stage 1"),
        ("E05", 2, 3, "Stage 2"),
        ("E06", 2, 4, "Stage 2"),
    ]
    repository.add_question_assignments(assessment.id, assignments)
    for question_id, stage_number, _, _ in assignments:
        if stage_number == 1:
            repository.insert_answer(
                assessment.id,
                question_id,
                stage_number,
                "Worker answer",
                "TEXT",
                3,
                {"feedback": "Feedback"},
                False,
                None,
                [],
            )
    repository.advance_assessment_stage(assessment.id, 2)
    for question_id, stage_number, _, _ in assignments:
        if stage_number == 2:
            repository.insert_answer(
                assessment.id,
                question_id,
                stage_number,
                "Worker answer",
                "TEXT",
                3,
                {"feedback": "Feedback"},
                False,
                None,
                [],
            )

    with pytest.raises(
        RepositoryValidationError,
        match="requires the assessment to be at Stage 3",
    ):
        repository.persist_final_result(
            assessment.id,
            total_score=12,
            max_score=24,
            score_percentage=Decimal("50.00"),
            safety_flags_json={"concerns": []},
        )


@pytest.mark.parametrize("invalid_assessment_id", [True, False, 0, -1, "1", None])
def test_bulk_assignment_rejects_invalid_assessment_ids(
    repository,
    invalid_assessment_id,
):
    with pytest.raises(
        RepositoryValidationError,
        match="assessment_id must be a positive integer",
    ):
        repository.add_question_assignments(
            invalid_assessment_id,
            [("E01", 1, 1, "Stage 1")],
        )


@pytest.mark.parametrize("unsupported_trade", ["Carpenter", True, 123, None])
def test_create_assessment_normalizes_unsupported_trade(
    repository,
    unsupported_trade,
):
    with main.db() as connection:
        worker_id = insert_worker(connection)

    if unsupported_trade is None:
        unsupported_trade = object()

    with pytest.raises(RepositoryValidationError, match="Unsupported trade"):
        repository.create_assessment(
            worker_id,
            "en",
            unsupported_trade,
        )


def test_transaction_rolls_back_failed_bulk_assignment(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")

    with pytest.raises(RepositoryValidationError):
        repository.add_question_assignments(
            assessment.id,
            [
                ("E01", 1, 1, "Valid"),
                ("P01", 1, 2, "Wrong trade"),
            ],
        )

    assert repository.get_assigned_questions(assessment.id) == ()


def test_foreign_key_integrity_is_preserved(repository):
    with pytest.raises(WorkerNotFoundError):
        repository.create_assessment(9999, "en")

    with pytest.raises(AssessmentNotFoundError):
        repository.add_question_assignment(
            9999,
            "E01",
            1,
            1,
            "Missing assessment",
        )


def test_answer_duplicate_is_atomic_under_concurrent_requests(repository):
    with main.db() as connection:
        worker_id = insert_worker(connection)
    assessment = repository.create_assessment(worker_id, "en")
    repository.add_question_assignment(
        assessment.id, "E01", 1, 1, "Foundational selection"
    )

    def submit_answer(value):
        return repository.insert_answer(
            assessment.id,
            "E01",
            1,
            f"Worker answer {value}",
            "TEXT",
            3,
            {"feedback": "Feedback"},
            False,
            None,
            [],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit_answer, value) for value in ("A", "B")]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except DuplicateAnswerError as exc:
                outcomes.append(exc)

    assert sum(isinstance(outcome, DuplicateAnswerError) for outcome in outcomes) == 1
    assert sum(hasattr(outcome, "id") for outcome in outcomes) == 1
