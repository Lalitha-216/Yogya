"""Deterministic adaptive assessment question selection."""

from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real
from typing import Mapping, Sequence


class Trade(str, Enum):
    """Trades supported by the assessment question bank."""

    ELECTRICIAN = "Electrician"
    PLUMBER = "Plumber"


class Difficulty(str, Enum):
    """Difficulty levels used to route assessment stages."""

    FOUNDATIONAL = "FOUNDATIONAL"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


@dataclass(frozen=True)
class Question:
    """A question and its stable identifier and difficulty."""

    question_id: str
    difficulty: Difficulty


QuestionBank = Mapping[
    Trade | str,
    Mapping[Difficulty | str, Sequence[Question]],
]


@dataclass(frozen=True)
class AssessmentState:
    """Assessment progress needed to continue adaptive question selection."""

    trade: Trade
    used_question_ids: tuple[str, ...]
    stage2_difficulty: Difficulty | None = None
    stage1_question_ids: tuple[str, ...] = ()
    stage2_question_ids: tuple[str, ...] = ()
    stage3_question_ids: tuple[str, ...] = ()


def _trade(value: Trade | str) -> Trade:
    try:
        return Trade(value)
    except (TypeError, ValueError):
        raise ValueError(f"Unsupported trade: {value!r}.") from None


def _difficulty(value: Difficulty | str) -> Difficulty:
    try:
        return Difficulty(value)
    except (TypeError, ValueError):
        raise ValueError(f"Unsupported question difficulty: {value!r}.") from None


def _trade_bank(bank: QuestionBank, trade: Trade) -> dict[Difficulty, tuple[Question, ...]]:
    """Validate and normalize one trade's ordered bank."""
    if not isinstance(bank, Mapping):
        raise ValueError("Question bank must be a mapping of trades to difficulty banks.")

    trade_bank = None
    for bank_trade, questions_by_difficulty in bank.items():
        normalized_trade = _trade(bank_trade)
        if normalized_trade == trade:
            if trade_bank is not None:
                raise ValueError(f"Question bank contains duplicate entries for {trade.value}.")
            trade_bank = questions_by_difficulty

    if trade_bank is None:
        raise ValueError(f"Question bank has no questions for {trade.value}.")
    if not isinstance(trade_bank, Mapping):
        raise ValueError(f"The {trade.value} question bank must be grouped by difficulty.")

    normalized_bank: dict[Difficulty, tuple[Question, ...]] = {}
    seen_question_ids: set[str] = set()
    for raw_difficulty, raw_questions in trade_bank.items():
        difficulty = _difficulty(raw_difficulty)
        if difficulty in normalized_bank:
            raise ValueError(f"Question bank contains duplicate {difficulty.value} groups.")
        if isinstance(raw_questions, (str, bytes)) or not isinstance(raw_questions, Sequence):
            raise ValueError(f"The {difficulty.value} question group must be a sequence.")

        questions = tuple(raw_questions)
        if len(questions) != 4:
            raise ValueError(
                f"The {trade.value} bank must contain exactly four "
                f"{difficulty.value} questions."
            )
        for question in questions:
            if not isinstance(question, Question):
                raise ValueError("Every bank entry must be a Question.")
            if not isinstance(question.question_id, str) or not question.question_id.strip():
                raise ValueError("Every question must have a non-empty string question_id.")
            question_difficulty = _difficulty(question.difficulty)
            if question_difficulty != difficulty:
                raise ValueError(
                    f"Question {question.question_id!r} is grouped under "
                    f"{difficulty.value} but declares {question_difficulty.value}."
                )
            if question.question_id in seen_question_ids:
                raise ValueError(
                    f"Question ID {question.question_id!r} is duplicated in the {trade.value} bank."
                )
            seen_question_ids.add(question.question_id)
        normalized_bank[difficulty] = questions

    if set(normalized_bank) != set(Difficulty):
        raise ValueError(
            f"The {trade.value} bank must contain FOUNDATIONAL, INTERMEDIATE, "
            "and ADVANCED groups."
        )
    return normalized_bank


def _scores(scores: Sequence[Real], stage_name: str) -> tuple[float, float]:
    """Validate and normalize the two scores for a completed stage."""
    if isinstance(scores, (str, bytes)) or not isinstance(scores, Sequence) or len(scores) != 2:
        raise ValueError(f"{stage_name} must contain exactly two scores.")

    normalized: list[float] = []
    for score in scores:
        if isinstance(score, bool) or not isinstance(score, Real):
            raise ValueError(f"{stage_name} scores must be finite numbers from 0 to 4.")
        try:
            numeric_score = float(score)
        except (OverflowError, TypeError, ValueError):
            raise ValueError(
                f"{stage_name} scores must be finite numbers from 0 to 4."
            ) from None
        if not math.isfinite(numeric_score) or not 0 <= numeric_score <= 4:
            raise ValueError(f"{stage_name} scores must be finite numbers from 0 to 4.")
        normalized.append(numeric_score)
    return normalized[0], normalized[1]


def _validate_state(
    state: AssessmentState,
    bank: QuestionBank,
    *,
    require_stage2: bool,
) -> tuple[dict[Difficulty, tuple[Question, ...]], Difficulty | None]:
    if not isinstance(state, AssessmentState):
        raise ValueError("Assessment state must be an AssessmentState.")

    trade = _trade(state.trade)
    normalized_bank = _trade_bank(bank, trade)
    for name, question_ids in (
        ("used_question_ids", state.used_question_ids),
        ("stage1_question_ids", state.stage1_question_ids),
        ("stage2_question_ids", state.stage2_question_ids),
        ("stage3_question_ids", state.stage3_question_ids),
    ):
        if not isinstance(question_ids, tuple) or any(
            not isinstance(question_id, str) or not question_id.strip()
            for question_id in question_ids
        ):
            raise ValueError(f"Assessment state {name} must be a tuple of non-empty IDs.")

    if len(state.stage1_question_ids) != 2 or len(set(state.stage1_question_ids)) != 2:
        raise ValueError("Assessment state must contain exactly two distinct Stage 1 question IDs.")

    stage2_difficulty = (
        None if state.stage2_difficulty is None else _difficulty(state.stage2_difficulty)
    )
    if stage2_difficulty == Difficulty.ADVANCED:
        raise ValueError("Stage 2 difficulty must be FOUNDATIONAL or INTERMEDIATE.")
    stage2_started = stage2_difficulty is not None or bool(state.stage2_question_ids)
    if stage2_started:
        if stage2_difficulty is None or len(state.stage2_question_ids) != 2:
            raise ValueError("Assessment state has incomplete Stage 2 information.")
        if len(set(state.stage2_question_ids)) != 2:
            raise ValueError("Stage 2 question IDs must be distinct.")
    elif require_stage2:
        raise ValueError("Stage 3 cannot be selected before Stage 2 is complete.")
    elif state.stage3_question_ids:
        raise ValueError("Stage 3 cannot be recorded before Stage 2 is complete.")

    if state.stage3_question_ids and len(state.stage3_question_ids) != 2:
        raise ValueError("Stage 3 question IDs must contain exactly two questions.")
    if len(set(state.stage3_question_ids)) != len(state.stage3_question_ids):
        raise ValueError("Stage 3 question IDs must be distinct.")

    expected_used_ids = (
        state.stage1_question_ids
        + state.stage2_question_ids
        + state.stage3_question_ids
    )
    if (
        len(set(expected_used_ids)) != len(expected_used_ids)
        or state.used_question_ids != expected_used_ids
    ):
        raise ValueError("Assessment state used_question_ids do not match its completed stages.")

    questions_by_id = {
        question.question_id: question
        for questions in normalized_bank.values()
        for question in questions
    }
    for question_id in state.stage1_question_ids:
        question = questions_by_id.get(question_id)
        if question is None or _difficulty(question.difficulty) != Difficulty.FOUNDATIONAL:
            raise ValueError("Assessment state contains an invalid Stage 1 question ID.")
    if state.stage1_question_ids != tuple(
        question.question_id for question in normalized_bank[Difficulty.FOUNDATIONAL][:2]
    ):
        raise ValueError("Stage 1 question IDs do not match the deterministic bank selection.")

    if stage2_difficulty is not None:
        for question_id in state.stage2_question_ids:
            question = questions_by_id.get(question_id)
            if question is None or _difficulty(question.difficulty) != stage2_difficulty:
                raise ValueError("Assessment state contains an invalid Stage 2 question ID.")
        expected_stage2_ids = tuple(
            question.question_id
            for question in normalized_bank[stage2_difficulty]
            if question.question_id not in state.stage1_question_ids
        )[:2]
        if state.stage2_question_ids != expected_stage2_ids:
            raise ValueError("Stage 2 question IDs do not match the deterministic bank selection.")

    stage3_difficulty = None
    for question_id in state.stage3_question_ids:
        question = questions_by_id.get(question_id)
        if question is None or _difficulty(question.difficulty) not in (
            Difficulty.INTERMEDIATE,
            Difficulty.ADVANCED,
        ):
            raise ValueError("Assessment state contains an invalid Stage 3 question ID.")
        question_difficulty = _difficulty(question.difficulty)
        if stage3_difficulty is None:
            stage3_difficulty = question_difficulty
        elif question_difficulty != stage3_difficulty:
            raise ValueError("Stage 3 question IDs must have the same difficulty.")

    if stage3_difficulty is not None:
        if (
            stage2_difficulty == Difficulty.FOUNDATIONAL
            and stage3_difficulty != Difficulty.INTERMEDIATE
        ):
            raise ValueError("A foundational Stage 2 must route to INTERMEDIATE in Stage 3.")
        expected_stage3_ids = tuple(
            question.question_id
            for question in normalized_bank[stage3_difficulty]
            if question.question_id not in state.used_question_ids[
                : len(state.stage1_question_ids) + len(state.stage2_question_ids)
            ]
        )[:2]
        if state.stage3_question_ids != expected_stage3_ids:
            raise ValueError("Stage 3 question IDs do not match the deterministic bank selection.")

    return normalized_bank, stage2_difficulty


def _select(
    questions: Sequence[Question],
    used_question_ids: tuple[str, ...],
    difficulty: Difficulty,
) -> tuple[Question, Question]:
    eligible = [
        question
        for question in questions
        if question.question_id not in used_question_ids
    ]
    if len(eligible) < 2:
        raise ValueError(
            f"Fewer than two unused {difficulty.value} questions remain."
        )
    return eligible[0], eligible[1]


def start_assessment(
    trade: Trade | str,
    bank: QuestionBank,
) -> tuple[AssessmentState, tuple[Question, Question]]:
    """Start an assessment with its first two FOUNDATIONAL questions."""
    normalized_trade = _trade(trade)
    normalized_bank = _trade_bank(bank, normalized_trade)
    selected = _select(
        normalized_bank[Difficulty.FOUNDATIONAL],
        (),
        Difficulty.FOUNDATIONAL,
    )
    question_ids = tuple(question.question_id for question in selected)
    state = AssessmentState(
        trade=normalized_trade,
        used_question_ids=question_ids,
        stage1_question_ids=question_ids,
    )
    return state, selected


def select_stage2(
    state: AssessmentState,
    bank: QuestionBank,
    stage1_scores: Sequence[Real],
) -> tuple[AssessmentState, tuple[Question, Question]]:
    """Choose Stage 2 from the Stage 1 average and remember its difficulty."""
    normalized_bank, stage2_difficulty = _validate_state(
        state, bank, require_stage2=False
    )
    if stage2_difficulty is not None:
        raise ValueError("Stage 2 has already been selected for this assessment.")

    scores = _scores(stage1_scores, "Stage 1")
    difficulty = (
        Difficulty.INTERMEDIATE
        if sum(scores) / 2 >= 3
        else Difficulty.FOUNDATIONAL
    )
    selected = _select(
        normalized_bank[difficulty],
        state.used_question_ids,
        difficulty,
    )
    selected_ids = tuple(question.question_id for question in selected)
    updated_state = AssessmentState(
        trade=_trade(state.trade),
        used_question_ids=state.used_question_ids + selected_ids,
        stage2_difficulty=difficulty,
        stage1_question_ids=state.stage1_question_ids,
        stage2_question_ids=selected_ids,
    )
    return updated_state, selected


def select_stage3(
    state: AssessmentState,
    bank: QuestionBank,
    stage2_scores: Sequence[Real],
) -> tuple[AssessmentState, tuple[Question, Question]]:
    """Choose Stage 3 using the recorded Stage 2 difficulty and score average."""
    normalized_bank, stage2_difficulty = _validate_state(
        state, bank, require_stage2=True
    )
    if state.stage3_question_ids:
        raise ValueError("Stage 3 has already been selected for this assessment.")
    scores = _scores(stage2_scores, "Stage 2")
    if stage2_difficulty == Difficulty.FOUNDATIONAL:
        difficulty = Difficulty.INTERMEDIATE
    elif sum(scores) / 2 >= 3:
        difficulty = Difficulty.ADVANCED
    else:
        difficulty = Difficulty.INTERMEDIATE

    selected = _select(
        normalized_bank[difficulty],
        state.used_question_ids,
        difficulty,
    )
    selected_ids = tuple(question.question_id for question in selected)
    updated_state = AssessmentState(
        trade=_trade(state.trade),
        used_question_ids=state.used_question_ids + selected_ids,
        stage2_difficulty=stage2_difficulty,
        stage1_question_ids=state.stage1_question_ids,
        stage2_question_ids=state.stage2_question_ids,
        stage3_question_ids=selected_ids,
    )
    return updated_state, selected