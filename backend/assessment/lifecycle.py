"""Assessment lifecycle orchestration for YOGYA."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from .adaptive_engine import (
    AssessmentState,
    Difficulty,
    Trade,
    select_stage2,
    select_stage3,
    start_assessment,
)
from .question_bank import AssessmentQuestion, QUESTION_BANK
from .repository import (
    ActiveAssessmentExistsError,
    AssessmentProgress,
    AssessmentRepository,
    AssessmentRecord,
    AssessmentResult,
    AnswerRecord,
    DuplicateAnswerError,
    QuestionAssignment,
    RepositoryError,
    RepositoryValidationError,
)
from .rubric_evaluator import EvaluationResult, evaluate_answer
from .scoring import calculate_score


AnswerLanguage = Literal["en", "te", "hi"]
AnswerSource = Literal["VOICE", "TEXT"]
Evaluator = Callable[
    [AssessmentQuestion, str, AnswerLanguage],
    EvaluationResult,
]


class LifecycleError(Exception):
    """Base exception for lifecycle orchestration failures."""


class LifecycleValidationError(LifecycleError, RepositoryValidationError):
    """Raised when lifecycle state or input is invalid."""


class LifecyclePersistenceError(LifecycleError):
    """Raised when a lifecycle database write cannot be completed."""


class LifecycleEvaluationError(LifecycleError):
    """Raised when an evaluator returns an inconsistent answer evaluation."""


@dataclass(frozen=True)
class LifecycleStartResult:
    """New assessment and its deterministic Stage 1 questions."""

    assessment: AssessmentRecord
    questions: tuple[AssessmentQuestion, AssessmentQuestion]
    state: AssessmentState


@dataclass(frozen=True)
class CurrentQuestion:
    """The next unanswered assigned question."""

    assessment: AssessmentRecord
    assignment: QuestionAssignment
    question: AssessmentQuestion


@dataclass(frozen=True)
class SubmittedAnswer:
    """Persisted answer and Gemini evaluation result."""

    answer: AnswerRecord
    evaluation: EvaluationResult


@dataclass(frozen=True)
class StageAdvanceResult:
    """Assessment state after a stage operation."""

    assessment: AssessmentRecord
    stage_number: int
    questions: tuple[AssessmentQuestion, ...]
    stage2_difficulty: Difficulty | None
    recovered_assignment: bool = False


class AssessmentLifecycle:
    """Orchestrate adaptive assessment selection and answer evaluation."""

    def __init__(
        self,
        repository: AssessmentRepository,
        *,
        bank: Mapping[
            Trade,
            Mapping[Difficulty, Sequence[AssessmentQuestion]],
        ] = QUESTION_BANK,
        evaluator: Evaluator = evaluate_answer,
    ) -> None:
        self.repository = repository
        self.bank = bank
        self.evaluator = evaluator

    def start_assessment(
        self,
        worker_id: int,
        language: AnswerLanguage,
    ) -> LifecycleStartResult:
        """Create an active assessment and assign its two Stage 1 questions."""
        if type(worker_id) is not int or worker_id <= 0:
            raise LifecycleValidationError(
                "worker_id must be a positive integer."
            )
        if language not in ("en", "te", "hi"):
            raise LifecycleValidationError(
                "language must be 'en', 'te', or 'hi'."
            )

        assessment = self.repository.create_assessment(worker_id, language)
        state, selected = start_assessment(assessment.trade, self.bank)
        if len(selected) != 2:
            raise LifecycleValidationError(
                "Stage 1 must select exactly two questions."
            )
        assignments = (
            (
                selected[0].question_id,
                1,
                1,
                "Stage 1 FOUNDATIONAL selection",
            ),
            (
                selected[1].question_id,
                1,
                2,
                "Stage 1 FOUNDATIONAL selection",
            ),
        )
        try:
            self.repository.add_question_assignments(
                assessment.id,
                assignments,
            )
        except RepositoryError as exc:
            raise LifecyclePersistenceError(
                "Could not persist Stage 1 question assignments."
            ) from exc

        return LifecycleStartResult(
            assessment=self.repository.get_assessment(assessment.id),
            questions=(selected[0], selected[1]),
            state=state,
        )

    def get_progress(self, assessment_id: int) -> AssessmentProgress:
        """Return persisted assessment progress."""
        return self.repository.get_assessment_progress(assessment_id)

    def get_current_question(
        self,
        assessment_id: int,
    ) -> CurrentQuestion | None:
        """Return the first unanswered assigned question in the current stage."""
        progress = self.repository.get_assessment_progress(assessment_id)
        assessment = progress.assessment
        if assessment.status == "COMPLETED":
            return None
        if assessment.status != "IN_PROGRESS":
            raise LifecycleValidationError(
                "Only IN_PROGRESS assessments have a current question."
            )

        answered_ids = {answer.question_id for answer in progress.answers}
        for assignment in progress.assignments:
            if (
                assignment.stage_number == assessment.current_stage
                and assignment.question_id not in answered_ids
            ):
                question = self.repository.get_assigned_assessment_question(
                    assessment_id,
                    assignment.question_id,
                )
                return CurrentQuestion(
                    assessment=assessment,
                    assignment=assignment,
                    question=question,
                )
        return None

    def submit_answer(
        self,
        assessment_id: int,
        question_id: str,
        answer_text: str,
        answer_source: AnswerSource,
    ) -> SubmittedAnswer:
        """Evaluate one answer and persist the complete validated result."""
        if type(assessment_id) is not int or assessment_id <= 0:
            raise LifecycleValidationError(
                "assessment_id must be a positive integer."
            )
        if not isinstance(answer_text, str) or not answer_text.strip():
            raise LifecycleValidationError(
                "answer_text must be a non-empty string."
            )
        if answer_source not in ("VOICE", "TEXT"):
            raise LifecycleValidationError(
                "answer_source must be 'VOICE' or 'TEXT'."
            )
        if not isinstance(question_id, str) or not question_id.strip():
            raise LifecycleValidationError(
                "question_id must be a non-empty string."
            )

        assessment = self.repository.get_assessment(assessment_id)
        if assessment.status != "IN_PROGRESS":
            raise LifecycleValidationError(
                "Answers can only be submitted for IN_PROGRESS assessments."
            )
        if assessment.language not in ("en", "te", "hi"):
            raise LifecycleValidationError(
                "Assessment has an unsupported answer language."
            )

        progress = self.repository.get_assessment_progress(assessment_id)
        if any(answer.question_id == question_id for answer in progress.answers):
            raise DuplicateAnswerError(
                "An answer already exists for this assessment and question."
            )

        try:
            assignment = self.repository.get_question_assignment(
                assessment_id,
                question_id,
            )
        except RepositoryValidationError:
            raise LifecycleValidationError(
                f"Question {question_id!r} is not assigned to this assessment."
            ) from None
        if assignment.stage_number != assessment.current_stage:
            if assignment.stage_number < assessment.current_stage:
                raise LifecycleValidationError(
                    "Answers cannot be submitted for a previous stage."
                )
            raise LifecycleValidationError(
                "Answers cannot be submitted for a future stage."
            )

        question = self.repository.get_assigned_assessment_question(
            assessment_id,
            question_id,
        )
        evaluation = self.evaluator(
            question,
            answer_text,
            assessment.language,
        )
        if evaluation.question_id != question_id:
            raise LifecycleEvaluationError(
                "Evaluation question_id does not match the requested question_id."
            )

        concept_evaluations = [
            {
                "concept": concept.concept,
                "demonstrated": concept.demonstrated,
                "evidence": concept.evidence,
                "rationale": concept.rationale,
            }
            for concept in evaluation.concept_evaluations
        ]
        feedback_json = {
            "feedback": evaluation.feedback,
            "concept_evaluations": concept_evaluations,
        }
        concerns_json = [
            {
                "concern": concern.concern,
                "evidence": concern.evidence,
            }
            for concern in evaluation.safety_concerns
        ]
        safety_reason = None
        if evaluation.safety_critical_misconception and concerns_json:
            safety_reason = concerns_json[0]["concern"]

        try:
            answer = self.repository.insert_answer(
                assessment_id,
                question_id,
                assignment.stage_number,
                answer_text,
                answer_source,
                evaluation.score,
                feedback_json,
                evaluation.safety_critical_misconception,
                safety_reason,
                concerns_json,
            )
        except DuplicateAnswerError:
            raise
        except RepositoryError as exc:
            raise LifecyclePersistenceError(
                "Evaluation succeeded, but the answer could not be persisted."
            ) from exc

        return SubmittedAnswer(answer=answer, evaluation=evaluation)

    def reconstruct_adaptive_state(
        self,
        assessment_id: int,
    ) -> AssessmentState:
        """Reconstruct and validate the adaptive state from persisted data."""
        progress = self.repository.get_assessment_progress(assessment_id)
        return self._reconstruct_adaptive_state(progress)

    def _reconstruct_adaptive_state(
        self,
        progress: AssessmentProgress,
        *,
        required_answer_stages: set[int] | None = None,
    ) -> AssessmentState:
        assessment = progress.assessment
        assignments = progress.assignments
        answers = progress.answers

        if not isinstance(assessment.current_stage, int):
            raise LifecycleValidationError(
                "Assessment current_stage is invalid."
            )
        if len(assignments) != len({item.question_id for item in assignments}):
            raise LifecycleValidationError(
                "Persisted assessment contains duplicate question assignments."
            )
        orders = [item.question_order for item in assignments]
        if len(set(orders)) != len(orders):
            raise LifecycleValidationError(
                "Persisted assessment contains duplicate question orders."
            )
        if orders != sorted(orders):
            raise LifecycleValidationError(
                "Persisted question orders are not in assessment order."
            )

        assignments_by_stage: dict[int, list[QuestionAssignment]] = {
            1: [],
            2: [],
            3: [],
        }
        for assignment in assignments:
            if assignment.stage_number not in assignments_by_stage:
                raise LifecycleValidationError(
                    "Persisted assessment has an invalid stage number."
                )
            assignments_by_stage[assignment.stage_number].append(assignment)

        stage1 = assignments_by_stage[1]
        stage2 = assignments_by_stage[2]
        stage3 = assignments_by_stage[3]
        if len(stage1) != 2:
            raise LifecycleValidationError(
                "Assessment state must contain exactly two Stage 1 assignments."
            )
        if len(stage2) not in (0, 2):
            raise LifecycleValidationError(
                "Assessment Stage 2 must contain either zero or two assignments."
            )
        if len(stage3) not in (0, 2):
            raise LifecycleValidationError(
                "Assessment Stage 3 must contain either zero or two assignments."
            )

        if [item.question_order for item in stage1] != [1, 2]:
            raise LifecycleValidationError(
                "Stage 1 question orders must be 1 and 2."
            )
        if stage2 and [item.question_order for item in stage2] != [3, 4]:
            raise LifecycleValidationError(
                "Stage 2 question orders must be 3 and 4."
            )
        if stage3 and [item.question_order for item in stage3] != [5, 6]:
            raise LifecycleValidationError(
                "Stage 3 question orders must be 5 and 6."
            )

        if assessment.current_stage == 1 and (stage2 or stage3):
            raise LifecycleValidationError(
                "Stage 2 or Stage 3 questions cannot exist before advancement."
            )
        if assessment.current_stage == 2 and stage3:
            raise LifecycleValidationError(
                "Stage 3 questions cannot exist while the assessment is at Stage 2."
            )
        if assessment.current_stage == 3 and not stage2:
            raise LifecycleValidationError(
                "Stage 3 requires persisted Stage 2 assignments."
            )

        stage1_questions = [
            self.repository.get_question(item.question_id)
            for item in stage1
        ]
        for assignment, question in zip(stage1, stage1_questions):
            if question.trade != assessment.trade:
                raise LifecycleValidationError(
                    "Persisted Stage 1 assignment does not belong to the assessment trade."
                )
        if any(question.difficulty != Difficulty.FOUNDATIONAL for question in stage1_questions):
            raise LifecycleValidationError(
                "Stage 1 assignments must use FOUNDATIONAL questions."
            )
        _, expected_stage1 = start_assessment(assessment.trade, self.bank)
        expected_stage1_ids = tuple(
            question.question_id
            for question in expected_stage1
        )
        actual_stage1_ids = tuple(
            item.question_id
            for item in sorted(stage1, key=lambda value: value.question_order)
        )
        if actual_stage1_ids != expected_stage1_ids:
            raise LifecycleValidationError(
                "Persisted Stage 1 assignments do not match deterministic selection."
            )

        stage2_difficulty: Difficulty | None = None
        stage2_questions: list[AssessmentQuestion] = []
        if stage2:
            stage2_questions = [
                self.repository.get_question(item.question_id)
                for item in stage2
            ]
            for assignment, question in zip(stage2, stage2_questions):
                if question.trade != assessment.trade:
                    raise LifecycleValidationError(
                        "Persisted Stage 2 assignment does not belong to the assessment trade."
                    )
            difficulties = {question.difficulty for question in stage2_questions}
            if len(difficulties) != 1:
                raise LifecycleValidationError(
                    "Stage 2 assignments must use exactly one difficulty."
                )
            stage2_difficulty = next(iter(difficulties))
            if stage2_difficulty not in (
                Difficulty.FOUNDATIONAL,
                Difficulty.INTERMEDIATE,
            ):
                raise LifecycleValidationError(
                    "Stage 2 difficulty must be FOUNDATIONAL or INTERMEDIATE."
                )

        stage3_questions: list[AssessmentQuestion] = []
        if stage3:
            stage3_questions = [
                self.repository.get_question(item.question_id)
                for item in stage3
            ]
            for assignment, question in zip(stage3, stage3_questions):
                if question.trade != assessment.trade:
                    raise LifecycleValidationError(
                        "Persisted Stage 3 assignment does not belong to the assessment trade."
                    )
            difficulties = {question.difficulty for question in stage3_questions}
            if len(difficulties) != 1:
                raise LifecycleValidationError(
                    "Stage 3 assignments must use exactly one difficulty."
                )
            stage3_difficulty = next(iter(difficulties))
            if stage3_difficulty not in (
                Difficulty.INTERMEDIATE,
                Difficulty.ADVANCED,
            ):
                raise LifecycleValidationError(
                    "Stage 3 difficulty must be INTERMEDIATE or ADVANCED."
                )

        answers_by_question = {answer.question_id: answer for answer in answers}
        if len(answers_by_question) != len(answers):
            raise LifecycleValidationError(
                "Persisted assessment contains duplicate answers."
            )
        if required_answer_stages is None:
            required_answer_stages = {1}
        for stage in required_answer_stages:
            items = assignments_by_stage[stage]
            if len(items) != 2:
                raise LifecycleValidationError(
                    f"Stage {stage} must have exactly two assignments."
                )
            for item in items:
                answer = answers_by_question.get(item.question_id)
                if answer is None:
                    raise LifecycleValidationError(
                        f"Stage {stage} is missing an answer."
                    )
                if answer.stage_number != stage:
                    raise LifecycleValidationError(
                        "Persisted answer stage does not match its assignment."
                )

        used_ids = tuple(
            item.question_id
            for item in sorted(assignments, key=lambda value: value.question_order)
        )
        if len(set(used_ids)) != len(used_ids):
            raise LifecycleValidationError(
                "Persisted assessment contains duplicate question IDs."
            )

        return AssessmentState(
            trade=assessment.trade,
            used_question_ids=used_ids,
            stage2_difficulty=stage2_difficulty,
            stage1_question_ids=tuple(item.question_id for item in stage1),
            stage2_question_ids=tuple(item.question_id for item in stage2),
            stage3_question_ids=tuple(item.question_id for item in stage3),
        )

    def advance_stage(
        self,
        assessment_id: int,
    ) -> StageAdvanceResult:
        """Advance one stage or recover missing assignments after an interrupted write."""
        progress = self.repository.get_assessment_progress(assessment_id)
        assessment = progress.assessment
        if assessment.status != "IN_PROGRESS":
            raise LifecycleValidationError(
                "Only IN_PROGRESS assessments can advance."
            )

        if assessment.current_stage == 1:
            stage1 = [
                item
                for item in progress.assignments
                if item.stage_number == 1
            ]
            stage2 = [
                item
                for item in progress.assignments
                if item.stage_number == 2
            ]
            stage3 = [
                item
                for item in progress.assignments
                if item.stage_number == 3
            ]
            if stage2 or stage3:
                raise LifecycleValidationError(
                    "Stage 1 recovery cannot have Stage 2 or Stage 3 assignments."
                )
            if len(stage1) == 0:
                state, selected = start_assessment(
                    assessment.trade,
                    self.bank,
                )
                del state
                assignments = tuple(
                    (
                        question.question_id,
                        1,
                        index,
                        "Recovered Stage 1 FOUNDATIONAL selection",
                    )
                    for index, question in enumerate(selected, start=1)
                )
                try:
                    persisted = self.repository.add_question_assignments(
                        assessment_id,
                        assignments,
                    )
                except RepositoryError as exc:
                    raise LifecyclePersistenceError(
                        "Could not recover Stage 1 question assignments."
                    ) from exc
                return StageAdvanceResult(
                    assessment=assessment,
                    stage_number=1,
                    questions=tuple(
                        self.repository.get_question(item.question_id)
                        for item in persisted
                    ),
                    stage2_difficulty=None,
                    recovered_assignment=True,
                )
            if len(stage1) == 1:
                raise LifecycleValidationError(
                    "Stage 1 has an invalid partial assignment state."
                )
            if len(stage1) > 2:
                raise LifecycleValidationError(
                    "Stage 1 has too many assignments."
                )
            if len(stage1) != 2:
                raise LifecycleValidationError(
                    "Stage 1 must have exactly two assigned questions."
                )
            stage1_answer_count = sum(
                answer.stage_number == 1
                for answer in progress.answers
            )
            if stage1_answer_count != 2:
                return StageAdvanceResult(
                    assessment=assessment,
                    stage_number=1,
                    questions=tuple(
                        self.repository.get_question(item.question_id)
                        for item in sorted(
                            stage1,
                            key=lambda value: value.question_order,
                        )
                    ),
                    stage2_difficulty=None,
                )
            state = self._reconstruct_adaptive_state(
                progress,
                required_answer_stages={1},
            )
            scores = self._stage_scores(progress, 1)
            updated_state, selected = select_stage2(
                state,
                self.bank,
                scores,
            )
            del updated_state
            assignments = tuple(
                (
                    question.question_id,
                    2,
                    index,
                    "Adaptive Stage 2 selection",
                )
                for index, question in enumerate(selected, start=3)
            )
            try:
                advanced = self.repository.advance_assessment_stage(
                    assessment_id,
                    2,
                )
                self.repository.add_question_assignments(
                    assessment_id,
                    assignments,
                )
            except RepositoryError as exc:
                raise LifecyclePersistenceError(
                    "Stage 2 advancement or assignment failed."
                ) from exc
            return StageAdvanceResult(
                assessment=advanced,
                stage_number=2,
                questions=tuple(selected),
                stage2_difficulty=advanced_state_difficulty(selected),
            )

        if assessment.current_stage == 2:
            stage2 = [
                item
                for item in progress.assignments
                if item.stage_number == 2
            ]
            if len(stage2) == 1:
                raise LifecycleValidationError(
                    "Stage 2 has an invalid partial assignment state."
                )
            if len(stage2) > 2:
                raise LifecycleValidationError(
                    "Stage 2 has too many assignments."
                )

            state = self._reconstruct_adaptive_state(
                progress,
                required_answer_stages={1},
            )
            stage1_scores = self._stage_scores(progress, 1)

            if len(stage2) == 2:
                stage1_only = AssessmentState(
                    trade=state.trade,
                    used_question_ids=state.stage1_question_ids,
                    stage1_question_ids=state.stage1_question_ids,
                )
                _, expected = select_stage2(
                    stage1_only,
                    self.bank,
                    stage1_scores,
                )
                expected_ids = tuple(question.question_id for question in expected)
                actual_ids = tuple(item.question_id for item in stage2)
                if actual_ids != expected_ids:
                    raise LifecycleValidationError(
                        "Existing Stage 2 assignments do not match adaptive selection."
                    )
                stage2_answer_count = sum(
                    answer.stage_number == 2
                    for answer in progress.answers
                )
                if stage2_answer_count != 2:
                    return StageAdvanceResult(
                        assessment=assessment,
                        stage_number=2,
                        questions=tuple(
                            self.repository.get_question(question_id)
                            for question_id in actual_ids
                        ),
                        stage2_difficulty=state.stage2_difficulty,
                    )
                stage2_scores = self._stage_scores(progress, 2)
                _, selected_stage3 = select_stage3(
                    state,
                    self.bank,
                    stage2_scores,
                )
                try:
                    advanced = self.repository.advance_assessment_stage(
                        assessment_id,
                        3,
                    )
                    stage3_assignments = tuple(
                        (
                            question.question_id,
                            3,
                            index,
                            "Adaptive Stage 3 selection",
                        )
                        for index, question in enumerate(
                            selected_stage3,
                            start=5,
                        )
                    )
                    self.repository.add_question_assignments(
                        assessment_id,
                        stage3_assignments,
                    )
                except RepositoryError as exc:
                    raise LifecyclePersistenceError(
                        "Stage 3 advancement or assignment failed."
                    ) from exc
                return StageAdvanceResult(
                    assessment=advanced,
                    stage_number=3,
                    questions=tuple(
                        selected_stage3
                    ),
                    stage2_difficulty=state.stage2_difficulty,
                )

            _, selected = select_stage2(
                state,
                self.bank,
                stage1_scores,
            )
            assignments = tuple(
                (
                    question.question_id,
                    2,
                    index,
                    "Adaptive Stage 2 recovery selection",
                )
                for index, question in enumerate(selected, start=3)
            )
            try:
                self.repository.add_question_assignments(
                    assessment_id,
                    assignments,
                )
            except RepositoryError as exc:
                raise LifecyclePersistenceError(
                    "Could not recover Stage 2 question assignments."
                ) from exc
            return StageAdvanceResult(
                assessment=assessment,
                stage_number=2,
                questions=tuple(selected),
                stage2_difficulty=advanced_state_difficulty(selected),
                recovered_assignment=True,
            )

        if assessment.current_stage == 3:
            stage3 = [
                item
                for item in progress.assignments
                if item.stage_number == 3
            ]
            if len(stage3) == 1:
                raise LifecycleValidationError(
                    "Stage 3 has an invalid partial assignment state."
                )
            if len(stage3) > 2:
                raise LifecycleValidationError(
                    "Stage 3 has too many assignments."
                )

            state = self._reconstruct_adaptive_state(
                progress,
                required_answer_stages={1, 2},
            )
            stage2_scores = self._stage_scores(progress, 2)

            if len(stage3) == 2:
                stage2_only = AssessmentState(
                    trade=state.trade,
                    used_question_ids=(
                        state.stage1_question_ids + state.stage2_question_ids
                    ),
                    stage2_difficulty=state.stage2_difficulty,
                    stage1_question_ids=state.stage1_question_ids,
                    stage2_question_ids=state.stage2_question_ids,
                )
                _, expected = select_stage3(
                    stage2_only,
                    self.bank,
                    stage2_scores,
                )
                expected_ids = tuple(question.question_id for question in expected)
                actual_ids = tuple(item.question_id for item in stage3)
                if actual_ids != expected_ids:
                    raise LifecycleValidationError(
                        "Existing Stage 3 assignments do not match adaptive selection."
                    )
                return StageAdvanceResult(
                    assessment=assessment,
                    stage_number=3,
                    questions=tuple(
                        self.repository.get_question(question_id)
                        for question_id in actual_ids
                    ),
                    stage2_difficulty=state.stage2_difficulty,
                )

            _, selected = select_stage3(
                state,
                self.bank,
                stage2_scores,
            )
            assignments = tuple(
                (
                    question.question_id,
                    3,
                    index,
                    "Adaptive Stage 3 recovery selection",
                )
                for index, question in enumerate(selected, start=5)
            )
            try:
                self.repository.add_question_assignments(
                    assessment_id,
                    assignments,
                )
            except RepositoryError as exc:
                raise LifecyclePersistenceError(
                    "Could not recover Stage 3 question assignments."
                ) from exc
            return StageAdvanceResult(
                assessment=assessment,
                stage_number=3,
                questions=tuple(selected),
                stage2_difficulty=state.stage2_difficulty,
                recovered_assignment=True,
            )

        raise LifecycleValidationError(
            "Assessment cannot be advanced from this stage."
        )

    def complete_assessment(
        self,
        assessment_id: int,
    ) -> AssessmentResult:
        """Validate and persist the final score for a complete assessment."""
        progress = self.repository.get_assessment_progress(assessment_id)
        assessment = progress.assessment
        if assessment.status != "IN_PROGRESS":
            raise LifecycleValidationError(
                "Only IN_PROGRESS assessments can be completed."
            )
        if assessment.current_stage != 3:
            raise LifecycleValidationError(
                "Assessment completion requires Stage 3."
            )
        state = self._reconstruct_adaptive_state(
            progress,
            required_answer_stages={1, 2, 3},
        )
        self._verify_persisted_adaptive_assignments(progress, state)
        if len(progress.assignments) != 6 or len(progress.answers) != 6:
            raise LifecycleValidationError(
                "Assessment completion requires exactly six assignments and answers."
            )

        ordered_assignments = sorted(
            progress.assignments,
            key=lambda item: item.question_order,
        )
        if [item.question_order for item in ordered_assignments] != [1, 2, 3, 4, 5, 6]:
            raise LifecycleValidationError(
                "Assessment question orders must be exactly 1 through 6."
            )
        answers_by_question = {
            answer.question_id: answer
            for answer in progress.answers
        }
        scores: list[int] = []
        for assignment in ordered_assignments:
            answer = answers_by_question.get(assignment.question_id)
            if answer is None:
                raise LifecycleValidationError(
                    "Assessment completion is missing a persisted answer."
                )
            if answer.stage_number != assignment.stage_number:
                raise LifecycleValidationError(
                    "Persisted answer stage does not match its assignment."
                )
            scores.append(answer.score)

        final_score = calculate_score(scores)
        safety_summary = self._build_safety_summary(progress.answers)
        try:
            return self.repository.persist_final_result(
                assessment_id,
                final_score.total_score,
                final_score.maximum_score,
                final_score.percentage,
                safety_summary,
            )
        except RepositoryError as exc:
            raise LifecyclePersistenceError(
                "The assessment could not be completed."
            ) from exc

    def get_result(self, assessment_id: int) -> AssessmentResult:
        """Return an existing completed assessment result."""
        return self.repository.get_assessment_result(assessment_id)

    def _verify_persisted_adaptive_assignments(
        self,
        progress: AssessmentProgress,
        state: AssessmentState,
    ) -> None:
        """Verify Stage 2 and Stage 3 IDs against deterministic engine output."""
        stage1_scores = self._stage_scores(progress, 1)
        state_before_stage2 = AssessmentState(
            trade=state.trade,
            used_question_ids=state.stage1_question_ids,
            stage1_question_ids=state.stage1_question_ids,
        )
        _, expected_stage2 = select_stage2(
            state_before_stage2,
            self.bank,
            stage1_scores,
        )
        expected_stage2_ids = tuple(
            question.question_id
            for question in expected_stage2
        )
        actual_stage2_ids = state.stage2_question_ids
        if actual_stage2_ids != expected_stage2_ids:
            raise LifecycleValidationError(
                "Persisted Stage 2 assignments do not match deterministic selection."
            )

        stage2_scores = self._stage_scores(progress, 2)
        state_for_stage3 = AssessmentState(
            trade=state.trade,
            used_question_ids=(
                state.stage1_question_ids + state.stage2_question_ids
            ),
            stage2_difficulty=state.stage2_difficulty,
            stage1_question_ids=state.stage1_question_ids,
            stage2_question_ids=state.stage2_question_ids,
        )
        _, expected_stage3 = select_stage3(
            state_for_stage3,
            self.bank,
            stage2_scores,
        )
        expected_stage3_ids = tuple(
            question.question_id
            for question in expected_stage3
        )
        actual_stage3_ids = state.stage3_question_ids
        if actual_stage3_ids != expected_stage3_ids:
            raise LifecycleValidationError(
                "Persisted Stage 3 assignments do not match deterministic selection."
            )

    def _stage_scores(
        self,
        progress: AssessmentProgress,
        stage_number: int,
    ) -> tuple[int, int]:
        answers_by_question = {
            answer.question_id: answer
            for answer in progress.answers
        }
        assignments = [
            item
            for item in progress.assignments
            if item.stage_number == stage_number
        ]
        if len(assignments) != 2:
            raise LifecycleValidationError(
                f"Stage {stage_number} must have exactly two assignments."
            )
        scores: list[int] = []
        for assignment in sorted(
            assignments,
            key=lambda item: item.question_order,
        ):
            answer = answers_by_question.get(assignment.question_id)
            if answer is None:
                raise LifecycleValidationError(
                    f"Stage {stage_number} is missing a persisted answer."
                )
            if type(answer.score) is not int:
                raise LifecycleValidationError(
                    "Persisted answer scores must be integers."
                )
            scores.append(answer.score)
        return scores[0], scores[1]

    @staticmethod
    def _build_safety_summary(
        answers: Sequence[AnswerRecord],
    ) -> dict[str, object]:
        concerns: list[dict[str, object]] = []
        flagged_question_ids: list[str] = []
        critical = False
        for answer in answers:
            if answer.safety_flag:
                critical = True
                flagged_question_ids.append(answer.question_id)
            for concern in answer.safety_concerns:
                if isinstance(concern, dict):
                    concerns.append(
                        {
                            "question_id": answer.question_id,
                            "concern": concern.get("concern"),
                            "evidence": concern.get("evidence"),
                        }
                    )
        return {
            "safety_critical_misconception": critical,
            "flagged_question_ids": flagged_question_ids,
            "concerns": concerns,
        }


def advanced_state_difficulty(
    questions: Sequence[AssessmentQuestion],
) -> Difficulty | None:
    """Return the selected difficulty for an adaptive stage result."""
    if not questions:
        return None
    difficulties = {question.difficulty for question in questions}
    if len(difficulties) != 1:
        return None
    return next(iter(difficulties))
