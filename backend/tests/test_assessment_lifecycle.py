"""Focused tests for the YOGYA assessment lifecycle."""

from dataclasses import replace
from decimal import Decimal

import pytest

import main
from assessment.adaptive_engine import Difficulty
from assessment.lifecycle import (
    AssessmentLifecycle,
    LifecycleEvaluationError,
    LifecyclePersistenceError,
    LifecycleValidationError,
)
from assessment.repository import (
    ActiveAssessmentExistsError,
    AssessmentRepository,
    DuplicateAnswerError,
)
from assessment.rubric_evaluator import (
    ConceptEvaluation,
    EvaluationResult,
    SafetyConcern,
)


def valid_evaluation(question, score=3, safety=False):
    concept_evaluations = tuple(
        ConceptEvaluation(
            concept=concept,
            demonstrated=True,
            evidence=(
                "I would isolate the supply"
                if "isolate" in concept
                else "I would use a suitable tester"
            ),
            rationale=f"The answer supports {concept}.",
        )
        for concept in question.expected_concepts
    )
    safety_concerns = (
        (
            SafetyConcern(
                concern="The answer says to work with power on.",
                evidence="I would replace the wire while power is on",
            ),
        )
        if safety
        else ()
    )
    return EvaluationResult(
        question_id=question.question_id,
        score=score,
        concept_evaluations=concept_evaluations,
        feedback="Answer-specific feedback.",
        safety_concerns=safety_concerns,
        safety_critical_misconception=safety,
    )


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "lifecycle.db")
    main.init_db()
    repository = AssessmentRepository(main.db)

    def evaluator(question, answer, language):
        del answer, language
        return valid_evaluation(question)

    return AssessmentLifecycle(repository, evaluator=evaluator)


def insert_worker(connection, trade="Electrician", name="Lifecycle Worker"):
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
            "I have relevant trade experience.",
            trade,
            4,
            "SELF_REPORTED",
        ),
    )
    return cursor.lastrowid


def create_started_lifecycle(lifecycle):
    repository = lifecycle.repository
    with main.db() as connection:
        worker_id = insert_worker(connection)
    started = lifecycle.start_assessment(worker_id, "en")
    return started, repository


def answer_stage(lifecycle, assessment_id, stage, scores):
    progress = lifecycle.repository.get_assessment_progress(assessment_id)
    assignments = [
        item
        for item in progress.assignments
        if item.stage_number == stage
    ]
    for assignment, score in zip(assignments, scores):
        lifecycle.evaluator = lambda question, answer, language, score=score: valid_evaluation(
            question,
            score=score,
        )
        lifecycle.submit_answer(
            assessment_id,
            assignment.question_id,
            "I would isolate the supply and use a suitable tester.",
            "TEXT",
        )


def test_successful_assessment_creation_assigns_two_stage1_questions(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)

    assert started.questions[0].question_id == "E01"
    assert started.questions[1].question_id == "E02"
    assert len(started.questions) == 2
    assert all(question.difficulty == Difficulty.FOUNDATIONAL for question in started.questions)
    progress = lifecycle.get_progress(started.assessment.id)
    assert len(progress.assignments) == 2
    assert [item.question_order for item in progress.assignments] == [1, 2]


@pytest.mark.parametrize("language", ["fr", "", "EN", None])
def test_start_assessment_rejects_invalid_language(lifecycle, language):
    with main.db() as connection:
        worker_id = insert_worker(connection)

    with pytest.raises(LifecycleValidationError, match="language"):
        lifecycle.start_assessment(worker_id, language)


def test_start_assessment_rejects_invalid_or_unknown_worker(lifecycle):
    with pytest.raises(LifecycleValidationError, match="positive integer"):
        lifecycle.start_assessment(True, "en")
    with pytest.raises(Exception):
        lifecycle.start_assessment(9999, "en")


def test_start_assessment_preserves_active_assessment_conflict(lifecycle):
    with main.db() as connection:
        worker_id = insert_worker(connection)

    lifecycle.start_assessment(worker_id, "en")

    with pytest.raises(ActiveAssessmentExistsError):
        lifecycle.start_assessment(worker_id, "te")


def test_progress_and_current_question_return_assigned_data_only(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)

    progress = lifecycle.get_progress(started.assessment.id)
    current = lifecycle.get_current_question(started.assessment.id)

    assert len(progress.assignments) == 2
    assert current is not None
    assert current.assignment.question_id == "E01"
    assert current.question.question_id == "E01"


@pytest.mark.parametrize("answer_source", ["TEXT", "VOICE"])
def test_valid_text_and_voice_answer_submissions(lifecycle, answer_source):
    started, _ = create_started_lifecycle(lifecycle)

    submitted = lifecycle.submit_answer(
        started.assessment.id,
        "E01",
        "I would isolate the supply and use a suitable tester.",
        answer_source,
    )

    assert submitted.answer.question_id == "E01"
    assert submitted.answer.answer_source == answer_source
    assert submitted.answer.score == 3


def test_blank_answer_rejected_before_evaluator(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)
    calls = []
    lifecycle.evaluator = lambda *args: calls.append(args)

    with pytest.raises(LifecycleValidationError, match="non-empty"):
        lifecycle.submit_answer(
            started.assessment.id,
            "E01",
            "   ",
            "TEXT",
        )
    assert calls == []


def test_wrong_unassigned_question_rejected_before_evaluator(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)
    calls = []
    lifecycle.evaluator = lambda *args: calls.append(args)

    with pytest.raises(LifecycleValidationError, match="not assigned"):
        lifecycle.submit_answer(
            started.assessment.id,
            "E05",
            "Worker answer",
            "TEXT",
        )
    assert calls == []


def test_previous_and_future_stage_answers_are_rejected(lifecycle):
    started, repository = create_started_lifecycle(lifecycle)
    repository.add_question_assignment(
        started.assessment.id,
        "E05",
        2,
        3,
        "Future Stage 2",
    )

    with pytest.raises(LifecycleValidationError, match="future stage"):
        lifecycle.submit_answer(
            started.assessment.id,
            "E05",
            "Worker answer",
            "TEXT",
        )

def test_previous_stage_answer_is_rejected_by_current_stage(lifecycle):
    started, repository = create_started_lifecycle(lifecycle)
    with main.db() as connection:
        connection.execute(
            "UPDATE assessments SET current_stage = 2 WHERE id = ?",
            (started.assessment.id,),
        )
        connection.execute(
            "DELETE FROM assessment_answers "
            "WHERE assessment_id = ? AND question_id = 'E02'",
            (started.assessment.id,),
        )

    with pytest.raises(
        LifecycleValidationError,
        match="previous stage",
    ):
        lifecycle.submit_answer(
            started.assessment.id,
            "E02",
            "Worker answer",
            "TEXT",
        )


def test_duplicate_answer_rejected_before_evaluator(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)
    lifecycle.submit_answer(
        started.assessment.id,
        "E01",
        "Worker answer",
        "TEXT",
    )
    calls = []
    lifecycle.evaluator = lambda *args: calls.append(args)

    with pytest.raises(DuplicateAnswerError):
        lifecycle.submit_answer(
            started.assessment.id,
            "E01",
            "Second worker answer",
            "TEXT",
        )
    assert calls == []


def test_evaluator_error_leaves_no_answer_persisted(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)

    def fail_evaluator(question, answer, language):
        del question, answer, language
        raise RuntimeError("Gemini failure")

    lifecycle.evaluator = fail_evaluator
    with pytest.raises(RuntimeError, match="Gemini failure"):
        lifecycle.submit_answer(
            started.assessment.id,
            "E01",
            "Worker answer",
            "TEXT",
        )
    progress = lifecycle.get_progress(started.assessment.id)
    assert progress.answers == ()


def test_evaluator_question_id_mismatch_is_not_persisted(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)

    def mismatched_evaluator(question, answer, language):
        del answer, language
        return replace(valid_evaluation(question), question_id="E02")

    lifecycle.evaluator = mismatched_evaluator

    with pytest.raises(
        LifecycleEvaluationError,
        match="does not match the requested question_id",
    ):
        lifecycle.submit_answer(
            started.assessment.id,
            "E01",
            "Worker answer",
            "TEXT",
        )
    assert lifecycle.get_progress(started.assessment.id).answers == ()


def test_valid_evaluation_persists_feedback_safety_and_score(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)

    def unsafe_evaluator(question, answer, language):
        del answer, language
        return valid_evaluation(question, score=2, safety=True)

    lifecycle.evaluator = unsafe_evaluator
    submitted = lifecycle.submit_answer(
        started.assessment.id,
        "E01",
        "I would replace the wire while power is on.",
        "TEXT",
    )

    assert submitted.answer.score == 2
    assert submitted.answer.safety_flag is True
    assert submitted.answer.safety_reason
    assert submitted.answer.safety_concerns
    assert "concept_evaluations" in submitted.answer.rubric_feedback


@pytest.mark.parametrize(
    ("stage1_scores", "expected_difficulty"),
    [
        ([2, 4], Difficulty.INTERMEDIATE),
        ([2, 2], Difficulty.FOUNDATIONAL),
    ],
)
def test_stage2_threshold_selection(lifecycle, stage1_scores, expected_difficulty):
    started, _ = create_started_lifecycle(lifecycle)
    answer_stage(lifecycle, started.assessment.id, 1, stage1_scores)

    advanced = lifecycle.advance_stage(started.assessment.id)

    assert advanced.stage_number == 2
    assert advanced.stage2_difficulty == expected_difficulty
    assert len(advanced.questions) == 2


@pytest.mark.parametrize(
    ("stage2_difficulty", "stage2_scores", "expected_difficulty"),
    [
        (Difficulty.INTERMEDIATE, [4, 4], Difficulty.ADVANCED),
        (Difficulty.INTERMEDIATE, [2, 2], Difficulty.INTERMEDIATE),
        (Difficulty.FOUNDATIONAL, [4, 4], Difficulty.INTERMEDIATE),
    ],
)
def test_stage3_all_adaptive_routes(
    lifecycle,
    stage2_difficulty,
    stage2_scores,
    expected_difficulty,
):
    started, _ = create_started_lifecycle(lifecycle)
    stage1_scores = (
        [4, 4]
        if stage2_difficulty == Difficulty.INTERMEDIATE
        else [2, 2]
    )
    answer_stage(lifecycle, started.assessment.id, 1, stage1_scores)
    lifecycle.advance_stage(started.assessment.id)
    answer_stage(lifecycle, started.assessment.id, 2, stage2_scores)

    advanced = lifecycle.advance_stage(started.assessment.id)

    assert advanced.stage_number == 3
    assert all(question.difficulty == expected_difficulty for question in advanced.questions)


def test_reconstruct_adaptive_state(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)
    answer_stage(lifecycle, started.assessment.id, 1, [4, 4])
    lifecycle.advance_stage(started.assessment.id)

    state = lifecycle.reconstruct_adaptive_state(started.assessment.id)

    assert state.trade == started.assessment.trade
    assert state.stage1_question_ids == ("E01", "E02")
    assert len(state.used_question_ids) == 4
    assert state.stage2_difficulty == Difficulty.INTERMEDIATE


def test_invalid_incomplete_state_is_rejected(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)

    with pytest.raises(LifecycleValidationError, match="missing an answer"):
        lifecycle.reconstruct_adaptive_state(started.assessment.id)


def test_stage2_recovery_after_advancement_before_assignment(lifecycle):
    started, repository = create_started_lifecycle(lifecycle)
    answer_stage(lifecycle, started.assessment.id, 1, [4, 4])
    repository.advance_assessment_stage(started.assessment.id, 2)

    recovered = lifecycle.advance_stage(started.assessment.id)

    assert recovered.recovered_assignment is True
    assert recovered.stage_number == 2
    progress = lifecycle.get_progress(started.assessment.id)
    assert len([item for item in progress.assignments if item.stage_number == 2]) == 2


def test_stage2_recovery_is_idempotent(lifecycle):
    started, repository = create_started_lifecycle(lifecycle)
    answer_stage(lifecycle, started.assessment.id, 1, [4, 4])
    repository.advance_assessment_stage(started.assessment.id, 2)

    first = lifecycle.advance_stage(started.assessment.id)
    second = lifecycle.advance_stage(started.assessment.id)

    assert first.recovered_assignment is True
    assert second.recovered_assignment is False
    progress = lifecycle.get_progress(started.assessment.id)
    stage2 = [item for item in progress.assignments if item.stage_number == 2]
    assert len(stage2) == 2


def test_stage1_recovery_after_assignment_persistence_failure(lifecycle):
    started, repository = create_started_lifecycle(lifecycle)
    with main.db() as connection:
        connection.execute(
            "DELETE FROM assessment_questions WHERE assessment_id = ?",
            (started.assessment.id,),
        )

    recovered = lifecycle.advance_stage(started.assessment.id)

    assert recovered.recovered_assignment is True
    assert recovered.stage_number == 1
    progress = lifecycle.get_progress(started.assessment.id)
    stage1 = [
        item
        for item in progress.assignments
        if item.stage_number == 1
    ]
    assert len(stage1) == 2
    assert [item.question_order for item in stage1] == [1, 2]


def test_stage1_recovery_is_idempotent(lifecycle):
    started, repository = create_started_lifecycle(lifecycle)
    with main.db() as connection:
        connection.execute(
            "DELETE FROM assessment_questions WHERE assessment_id = ?",
            (started.assessment.id,),
        )

    first = lifecycle.advance_stage(started.assessment.id)
    second = lifecycle.advance_stage(started.assessment.id)

    assert first.recovered_assignment is True
    assert second.recovered_assignment is False
    progress = lifecycle.get_progress(started.assessment.id)
    assert len([
        item
        for item in progress.assignments
        if item.stage_number == 1
    ]) == 2


def test_repeated_stage1_advancement_is_safely_handled(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)
    answer_stage(lifecycle, started.assessment.id, 1, [4, 4])

    first = lifecycle.advance_stage(started.assessment.id)
    progress = lifecycle.get_progress(started.assessment.id)
    assert progress.assessment.current_stage == 2

    repeated = lifecycle.advance_stage(started.assessment.id)
    assert repeated.stage_number == 2


def test_complete_requires_exactly_six_answers(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)

    with pytest.raises(LifecycleValidationError, match="requires Stage 3"):
        lifecycle.complete_assessment(started.assessment.id)


def test_stage3_advancement_before_assignment_recovers_exactly_two_questions(lifecycle):
    started, repository = create_started_lifecycle(lifecycle)
    answer_stage(lifecycle, started.assessment.id, 1, [4, 4])
    lifecycle.advance_stage(started.assessment.id)
    answer_stage(lifecycle, started.assessment.id, 2, [4, 4])
    repository.advance_assessment_stage(started.assessment.id, 3)

    recovered = lifecycle.advance_stage(started.assessment.id)

    assert recovered.recovered_assignment is True
    assert recovered.stage_number == 3
    assert len(recovered.questions) == 2
    progress = lifecycle.get_progress(started.assessment.id)
    stage3 = [
        item
        for item in progress.assignments
        if item.stage_number == 3
    ]
    assert len(stage3) == 2
    assert [item.question_order for item in stage3] == [5, 6]


def test_stage3_recovery_is_idempotent(lifecycle):
    started, repository = create_started_lifecycle(lifecycle)
    answer_stage(lifecycle, started.assessment.id, 1, [4, 4])
    lifecycle.advance_stage(started.assessment.id)
    answer_stage(lifecycle, started.assessment.id, 2, [4, 4])
    repository.advance_assessment_stage(started.assessment.id, 3)

    first = lifecycle.advance_stage(started.assessment.id)
    second = lifecycle.advance_stage(started.assessment.id)

    assert first.recovered_assignment is True
    assert second.recovered_assignment is False
    progress = lifecycle.get_progress(started.assessment.id)
    assert len([
        item
        for item in progress.assignments
        if item.stage_number == 3
    ]) == 2


def test_invalid_partial_stage3_assignment_is_rejected(lifecycle):
    started, repository = create_started_lifecycle(lifecycle)
    answer_stage(lifecycle, started.assessment.id, 1, [4, 4])
    lifecycle.advance_stage(started.assessment.id)
    answer_stage(lifecycle, started.assessment.id, 2, [4, 4])
    repository.advance_assessment_stage(started.assessment.id, 3)
    repository.add_question_assignment(
        started.assessment.id,
        "E09",
        3,
        5,
        "Invalid partial Stage 3",
    )

    with pytest.raises(
        LifecycleValidationError,
        match="invalid partial assignment state",
    ):
        lifecycle.advance_stage(started.assessment.id)


def setup_completed_assessment(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)
    answer_stage(lifecycle, started.assessment.id, 1, [4, 4])
    lifecycle.advance_stage(started.assessment.id)
    answer_stage(lifecycle, started.assessment.id, 2, [4, 4])
    lifecycle.advance_stage(started.assessment.id)
    answer_stage(lifecycle, started.assessment.id, 3, [4, 3])
    return started


def test_correct_final_score_and_percentage_persisted(lifecycle):
    started = setup_completed_assessment(lifecycle)

    result = lifecycle.complete_assessment(started.assessment.id)

    assert result.status == "COMPLETED"
    assert result.total_score == 23
    assert result.maximum_score == 24
    assert result.score_percentage == pytest.approx(95.83)


def test_tampered_same_trade_stage1_assignment_is_rejected_before_completion(lifecycle):
    started = setup_completed_assessment(lifecycle)

    with main.db() as connection:
        connection.execute(
            "DELETE FROM assessment_answers WHERE assessment_id = ? AND question_id = 'E01'",
            (started.assessment.id,),
        )
        connection.execute(
            """
            UPDATE assessment_questions
            SET question_id = 'E03'
            WHERE assessment_id = ? AND stage_number = 1
              AND question_order = 1
            """,
            (started.assessment.id,),
        )
        connection.execute(
            """
            INSERT INTO assessment_answers (
                assessment_id, question_id, stage_number, answer_text,
                answer_source, score, rubric_feedback_json, safety_flag,
                safety_reason, safety_concerns_json, answered_at
            ) VALUES (?, 'E03', 1, 'Tampered answer', 'TEXT', 4,
                      '{"feedback":"Feedback"}', 0, NULL, '[]',
                      '2026-01-01T00:00:00+00:00')
            """,
            (started.assessment.id,),
        )

    with pytest.raises(
        LifecycleValidationError,
        match="Persisted Stage 1 assignments",
    ):
        lifecycle.complete_assessment(started.assessment.id)

    progress = lifecycle.get_progress(started.assessment.id)
    assert progress.assessment.status == "IN_PROGRESS"


def test_tampered_other_trade_stage1_assignment_is_rejected_before_completion(lifecycle):
    started = setup_completed_assessment(lifecycle)

    with main.db() as connection:
        connection.execute(
            "DELETE FROM assessment_answers WHERE assessment_id = ? AND question_id = 'E01'",
            (started.assessment.id,),
        )
        connection.execute(
            """
            UPDATE assessment_questions
            SET question_id = 'P01'
            WHERE assessment_id = ? AND stage_number = 1
              AND question_order = 1
            """,
            (started.assessment.id,),
        )
        connection.execute(
            """
            INSERT INTO assessment_answers (
                assessment_id, question_id, stage_number, answer_text,
                answer_source, score, rubric_feedback_json, safety_flag,
                safety_reason, safety_concerns_json, answered_at
            ) VALUES (?, 'P01', 1, 'Tampered answer', 'TEXT', 4,
                      '{"feedback":"Feedback"}', 0, NULL, '[]',
                      '2026-01-01T00:00:00+00:00')
            """,
            (started.assessment.id,),
        )

    with pytest.raises(
        LifecycleValidationError,
        match="assessment trade",
    ):
        lifecycle.complete_assessment(started.assessment.id)

    progress = lifecycle.get_progress(started.assessment.id)
    assert progress.assessment.status == "IN_PROGRESS"


def test_tampered_other_trade_stage2_assignment_is_rejected_before_completion(lifecycle):
    started = setup_completed_assessment(lifecycle)

    with main.db() as connection:
        connection.execute(
            "DELETE FROM assessment_answers WHERE assessment_id = ? AND question_id = 'E05'",
            (started.assessment.id,),
        )
        connection.execute(
            """
            UPDATE assessment_questions
            SET question_id = 'P05'
            WHERE assessment_id = ? AND stage_number = 2
              AND question_order = 3
            """,
            (started.assessment.id,),
        )
        connection.execute(
            """
            INSERT INTO assessment_answers (
                assessment_id, question_id, stage_number, answer_text,
                answer_source, score, rubric_feedback_json, safety_flag,
                safety_reason, safety_concerns_json, answered_at
            ) VALUES (?, 'P05', 2, 'Tampered answer', 'TEXT', 4,
                      '{"feedback":"Feedback"}', 0, NULL, '[]',
                      '2026-01-01T00:00:00+00:00')
            """,
            (started.assessment.id,),
        )

    with pytest.raises(
        LifecycleValidationError,
        match="assessment trade",
    ):
        lifecycle.complete_assessment(started.assessment.id)

    progress = lifecycle.get_progress(started.assessment.id)
    assert progress.assessment.status == "IN_PROGRESS"


def test_tampered_stage2_assignment_is_rejected_before_completion(lifecycle):
    started = setup_completed_assessment(lifecycle)

    with main.db() as connection:
        connection.execute(
            """
            DELETE FROM assessment_answers
            WHERE assessment_id = ? AND question_id = 'E05'
            """,
            (started.assessment.id,),
        )
        connection.execute(
            """
            DELETE FROM assessment_questions
            WHERE assessment_id = ? AND stage_number = 2
              AND question_order = 3
            """,
            (started.assessment.id,),
        )
        connection.execute(
            """
            INSERT INTO assessment_questions (
                assessment_id, question_id, stage_number, question_order,
                selection_reason, selected_at
            ) VALUES (?, 'E07', 2, 3, 'Tampered assignment',
                      '2026-01-01T00:00:00+00:00')
            """,
            (started.assessment.id,),
        )
        connection.execute(
            """
            INSERT INTO assessment_answers (
                assessment_id, question_id, stage_number, answer_text,
                answer_source, score, rubric_feedback_json, safety_flag,
                safety_reason, safety_concerns_json, answered_at
            ) VALUES (?, 'E07', 2, 'Tampered answer', 'TEXT', 4,
                      '{"feedback":"Feedback"}', 0, NULL, '[]',
                      '2026-01-01T00:00:00+00:00')
            """,
            (started.assessment.id,),
        )

    with pytest.raises(
        LifecycleValidationError,
        match="Stage 2 assignments",
    ):
        lifecycle.complete_assessment(started.assessment.id)

    progress = lifecycle.get_progress(started.assessment.id)
    assert progress.assessment.status == "IN_PROGRESS"


def test_tampered_stage3_assignment_is_rejected_before_completion(lifecycle):
    started = setup_completed_assessment(lifecycle)

    with main.db() as connection:
        connection.execute(
            """
            DELETE FROM assessment_answers
            WHERE assessment_id = ? AND question_id = 'E09'
            """,
            (started.assessment.id,),
        )
        connection.execute(
            """
            DELETE FROM assessment_questions
            WHERE assessment_id = ? AND stage_number = 3
              AND question_order = 5
            """,
            (started.assessment.id,),
        )
        connection.execute(
            """
            INSERT INTO assessment_questions (
                assessment_id, question_id, stage_number, question_order,
                selection_reason, selected_at
            ) VALUES (?, 'E11', 3, 5, 'Tampered assignment',
                      '2026-01-01T00:00:00+00:00')
            """,
            (started.assessment.id,),
        )
        connection.execute(
            """
            INSERT INTO assessment_answers (
                assessment_id, question_id, stage_number, answer_text,
                answer_source, score, rubric_feedback_json, safety_flag,
                safety_reason, safety_concerns_json, answered_at
            ) VALUES (?, 'E11', 3, 'Tampered answer', 'TEXT', 4,
                      '{"feedback":"Feedback"}', 0, NULL, '[]',
                      '2026-01-01T00:00:00+00:00')
            """,
            (started.assessment.id,),
        )

    with pytest.raises(
        LifecycleValidationError,
        match="Stage 3 assignments",
    ):
        lifecycle.complete_assessment(started.assessment.id)

    progress = lifecycle.get_progress(started.assessment.id)
    assert progress.assessment.status == "IN_PROGRESS"


def test_safety_summary_does_not_affect_numeric_score(lifecycle):
    started, _ = create_started_lifecycle(lifecycle)
    answer_stage(lifecycle, started.assessment.id, 1, [4, 4])
    lifecycle.advance_stage(started.assessment.id)
    answer_stage(lifecycle, started.assessment.id, 2, [4, 4])
    lifecycle.advance_stage(started.assessment.id)

    progress = lifecycle.get_progress(started.assessment.id)
    stage3 = [item for item in progress.assignments if item.stage_number == 3]
    lifecycle.evaluator = lambda question, answer, language: valid_evaluation(
        question,
        score=4,
        safety=True,
    )
    for assignment in stage3:
        lifecycle.submit_answer(
            started.assessment.id,
            assignment.question_id,
            "I would replace the wire while power is on.",
            "TEXT",
        )

    result = lifecycle.complete_assessment(started.assessment.id)

    assert result.total_score == 24
    assert result.score_percentage == 100.0
    assert result.safety_flags["safety_critical_misconception"] is True


def test_completed_result_retrieval(lifecycle):
    started = setup_completed_assessment(lifecycle)
    lifecycle.complete_assessment(started.assessment.id)

    result = lifecycle.get_result(started.assessment.id)

    assert result.status == "COMPLETED"
    assert result.total_score == 23


def test_persistence_failure_does_not_complete_assessment(lifecycle):
    started = setup_completed_assessment(lifecycle)

    def fail_persist(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("database failure")

    lifecycle.repository.persist_final_result = fail_persist

    with pytest.raises(RuntimeError, match="database failure"):
        lifecycle.complete_assessment(started.assessment.id)
    progress = lifecycle.get_progress(started.assessment.id)
    assert progress.assessment.status == "IN_PROGRESS"


def test_lifecycle_never_assigns_independent_verification(lifecycle):
    started = setup_completed_assessment(lifecycle)

    result = lifecycle.complete_assessment(started.assessment.id)
    result_json = str(result.safety_flags)

    assert "INDEPENDENTLY_VERIFIED" not in result_json
