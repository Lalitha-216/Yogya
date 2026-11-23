"""Tests for deterministic adaptive assessment routing."""

from dataclasses import replace
import math

import pytest

from assessment.adaptive_engine import (
    AssessmentState,
    Difficulty,
    Question,
    Trade,
    select_stage2,
    select_stage3,
    start_assessment,
)


TRADES = (Trade.ELECTRICIAN, Trade.PLUMBER)
DIFFICULTIES = (
    Difficulty.FOUNDATIONAL,
    Difficulty.INTERMEDIATE,
    Difficulty.ADVANCED,
)


def make_trade_bank(trade: Trade) -> dict[Difficulty, list[Question]]:
    """Build an ordered four-question group for each difficulty."""
    prefix = "E" if trade == Trade.ELECTRICIAN else "P"
    return {
        difficulty: [
            Question(
                question_id=f"{prefix}-{difficulty.value[0]}{index:02d}",
                difficulty=difficulty,
            )
            for index in range(1, 5)
        ]
        for difficulty in DIFFICULTIES
    }


@pytest.fixture
def question_bank():
    """Provide complete, independent question banks for both supported trades."""
    return {trade: make_trade_bank(trade) for trade in TRADES}


def question_ids(questions):
    return tuple(question.question_id for question in questions)


def complete_assessment(bank, trade, stage1_scores, stage2_scores):
    """Run all three stages and return each stage's selected IDs and final state."""
    state, stage1_questions = start_assessment(trade, bank)
    state, stage2_questions = select_stage2(state, bank, stage1_scores)
    stage2_difficulty = state.stage2_difficulty
    state, stage3_questions = select_stage3(state, bank, stage2_scores)
    selected_by_stage = (
        question_ids(stage1_questions),
        question_ids(stage2_questions),
        question_ids(stage3_questions),
    )
    return state, stage2_difficulty, selected_by_stage


@pytest.mark.parametrize(
    ("scenario", "stage1_scores", "stage2_scores", "expected_stage2", "expected_ids"),
    [
        pytest.param(
            "stage1_at_or_above_threshold",
            [2, 4],
            [4, 4],
            Difficulty.INTERMEDIATE,
            (("E-F01", "E-F02"), ("E-I01", "E-I02"), ("E-A01", "E-A02")),
            id="stage1-average-exactly-3-selects-intermediate",
        ),
        pytest.param(
            "stage1_below_threshold",
            [2, 2],
            [0, 0],
            Difficulty.FOUNDATIONAL,
            (("E-F01", "E-F02"), ("E-F03", "E-F04"), ("E-I01", "E-I02")),
            id="stage1-below-3-reinforces-foundational",
        ),
        pytest.param(
            "stage2_intermediate_at_or_above_threshold",
            [4, 4],
            [2, 4],
            Difficulty.INTERMEDIATE,
            (("E-F01", "E-F02"), ("E-I01", "E-I02"), ("E-A01", "E-A02")),
            id="stage2-intermediate-average-exactly-3-selects-advanced",
        ),
        pytest.param(
            "stage2_intermediate_below_threshold",
            [4, 4],
            [2, 2],
            Difficulty.INTERMEDIATE,
            (("E-F01", "E-F02"), ("E-I01", "E-I02"), ("E-I03", "E-I04")),
            id="stage2-intermediate-below-3-reinforces-intermediate",
        ),
        pytest.param(
            "stage2_foundational_score_does_not_change_route",
            [0, 0],
            [0, 0],
            Difficulty.FOUNDATIONAL,
            (("E-F01", "E-F02"), ("E-F03", "E-F04"), ("E-I01", "E-I02")),
            id="stage2-foundational-low-score-still-selects-intermediate",
        ),
        pytest.param(
            "stage2_foundational_high_score_does_not_change_route",
            [0, 0],
            [4, 4],
            Difficulty.FOUNDATIONAL,
            (("E-F01", "E-F02"), ("E-F03", "E-F04"), ("E-I01", "E-I02")),
            id="stage2-foundational-high-score-still-selects-intermediate",
        ),
    ],
)
@pytest.mark.parametrize("trade", TRADES)
def test_adaptive_scenarios_select_exactly_two_unique_questions_per_stage(
    question_bank,
    trade,
    scenario,
    stage1_scores,
    stage2_scores,
    expected_stage2,
    expected_ids,
):
    """Exercise all routing rules for both trades, including exact threshold averages."""
    del scenario  # The parameter ID gives each route case a readable pytest name.
    prefix = "E" if trade == Trade.ELECTRICIAN else "P"
    trade_expected_ids = tuple(
        tuple(question_id.replace("E-", f"{prefix}-") for question_id in stage_ids)
        for stage_ids in expected_ids
    )

    state, stage2_difficulty, actual_ids = complete_assessment(
        question_bank, trade, stage1_scores, stage2_scores
    )

    assert stage2_difficulty == expected_stage2
    assert actual_ids == trade_expected_ids
    assert all(len(stage_ids) == 2 for stage_ids in actual_ids)
    all_ids = tuple(question_id for stage_ids in actual_ids for question_id in stage_ids)
    assert len(all_ids) == 6
    assert len(set(all_ids)) == 6
    assert state.used_question_ids == all_ids
    assert state.stage3_question_ids == actual_ids[2]


@pytest.mark.parametrize("trade", TRADES)
def test_selection_is_deterministic_for_identical_inputs(question_bank, trade):
    """Repeated calls from the same input state choose the same ordered questions."""
    initial_state_a, stage1_a = start_assessment(trade, question_bank)
    initial_state_b, stage1_b = start_assessment(trade, question_bank)
    assert question_ids(stage1_a) == question_ids(stage1_b)
    assert initial_state_a == initial_state_b

    stage2_state_a, stage2_a = select_stage2(initial_state_a, question_bank, [3, 3])
    stage2_state_b, stage2_b = select_stage2(initial_state_b, question_bank, [3, 3])
    assert question_ids(stage2_a) == question_ids(stage2_b)
    assert stage2_state_a == stage2_state_b

    _, stage3_a = select_stage3(stage2_state_a, question_bank, [3, 3])
    _, stage3_b = select_stage3(stage2_state_b, question_bank, [3, 3])
    assert question_ids(stage3_a) == question_ids(stage3_b)


@pytest.mark.parametrize("trade", TRADES)
def test_stage2_records_its_selected_difficulty(question_bank, trade):
    """The state preserves whether Stage 2 was INTERMEDIATE or FOUNDATIONAL."""
    state, _ = start_assessment(trade, question_bank)
    intermediate_state, _ = select_stage2(state, question_bank, [3, 3])
    foundational_state, _ = select_stage2(state, question_bank, [2, 2])

    assert intermediate_state.stage2_difficulty == Difficulty.INTERMEDIATE
    assert foundational_state.stage2_difficulty == Difficulty.FOUNDATIONAL


@pytest.mark.parametrize("scores", [[-0.01, 2], [4.01, 2]])
@pytest.mark.parametrize("stage", ["stage2", "stage3"])
def test_scores_outside_zero_to_four_are_rejected(question_bank, scores, stage):
    if stage == "stage2":
        state, _ = start_assessment(Trade.ELECTRICIAN, question_bank)
        select = lambda: select_stage2(state, question_bank, scores)
    else:
        state, _ = start_assessment(Trade.ELECTRICIAN, question_bank)
        state, _ = select_stage2(state, question_bank, [3, 3])
        select = lambda: select_stage3(state, question_bank, scores)

    with pytest.raises(ValueError, match="scores must be finite numbers from 0 to 4"):
        select()


@pytest.mark.parametrize("scores", [[True, 2], [False, 2]])
@pytest.mark.parametrize("stage", ["stage2", "stage3"])
def test_boolean_scores_are_rejected(question_bank, scores, stage):
    if stage == "stage2":
        state, _ = start_assessment(Trade.PLUMBER, question_bank)
        select = lambda: select_stage2(state, question_bank, scores)
    else:
        state, _ = start_assessment(Trade.PLUMBER, question_bank)
        state, _ = select_stage2(state, question_bank, [3, 3])
        select = lambda: select_stage3(state, question_bank, scores)

    with pytest.raises(ValueError, match="scores must be finite numbers from 0 to 4"):
        select()


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("stage", ["stage2", "stage3"])
def test_non_finite_scores_are_rejected(question_bank, score, stage):
    scores = [score, 2]
    if stage == "stage2":
        state, _ = start_assessment(Trade.ELECTRICIAN, question_bank)
        select = lambda: select_stage2(state, question_bank, scores)
    else:
        state, _ = start_assessment(Trade.ELECTRICIAN, question_bank)
        state, _ = select_stage2(state, question_bank, [3, 3])
        select = lambda: select_stage3(state, question_bank, scores)

    with pytest.raises(ValueError, match="scores must be finite numbers from 0 to 4"):
        select()


@pytest.mark.parametrize("stage", ["stage2", "stage3"])
def test_string_scores_are_rejected(question_bank, stage):
    scores = ["2", 2]
    if stage == "stage2":
        state, _ = start_assessment(Trade.ELECTRICIAN, question_bank)
        select = lambda: select_stage2(state, question_bank, scores)
    else:
        state, _ = start_assessment(Trade.ELECTRICIAN, question_bank)
        state, _ = select_stage2(state, question_bank, [3, 3])
        select = lambda: select_stage3(state, question_bank, scores)

    with pytest.raises(ValueError, match="scores must be finite numbers from 0 to 4"):
        select()


@pytest.mark.parametrize("scores", [[], [2], [1, 2, 3], "22"])
@pytest.mark.parametrize("stage", ["stage2", "stage3"])
def test_incorrect_score_counts_are_rejected(question_bank, scores, stage):
    if stage == "stage2":
        state, _ = start_assessment(Trade.PLUMBER, question_bank)
        select = lambda: select_stage2(state, question_bank, scores)
    else:
        state, _ = start_assessment(Trade.PLUMBER, question_bank)
        state, _ = select_stage2(state, question_bank, [3, 3])
        select = lambda: select_stage3(state, question_bank, scores)

    with pytest.raises(ValueError, match="exactly two scores"):
        select()


@pytest.mark.parametrize("trade", ["Carpenter", "", None, 42])
def test_unsupported_trade_is_rejected(question_bank, trade):
    with pytest.raises(ValueError, match="Unsupported trade"):
        start_assessment(trade, question_bank)


@pytest.mark.parametrize(
    "bad_bank",
    [
        pytest.param(
            {"Carpenter": make_trade_bank(Trade.ELECTRICIAN)},
            id="unsupported-trade-key",
        ),
        pytest.param(
            {
                Trade.ELECTRICIAN: {
                    "EXPERT": [Question(f"E-X{i}", Difficulty.ADVANCED) for i in range(4)]
                }
            },
            id="invalid-difficulty-key",
        ),
        pytest.param(
            {
                Trade.ELECTRICIAN: {
                    **make_trade_bank(Trade.ELECTRICIAN),
                    Difficulty.FOUNDATIONAL: [
                        Question(f"E-F{i}", "EXPERT") for i in range(1, 5)
                    ],
                }
            },
            id="invalid-question-difficulty",
        ),
    ],
)
def test_invalid_trade_or_difficulty_in_bank_is_rejected(bad_bank):
    with pytest.raises(ValueError):
        start_assessment(Trade.ELECTRICIAN, bad_bank)


def test_invalid_stage2_difficulty_value_is_rejected(question_bank):
    state, _ = start_assessment(Trade.ELECTRICIAN, question_bank)
    invalid_state = replace(state, stage2_difficulty="EXPERT")

    with pytest.raises(ValueError, match="Unsupported question difficulty"):
        select_stage3(invalid_state, question_bank, [2, 2])


def test_advanced_is_rejected_as_stage2_difficulty(question_bank):
    state, _ = start_assessment(Trade.ELECTRICIAN, question_bank)
    state, _ = select_stage2(state, question_bank, [3, 3])
    invalid_state = replace(state, stage2_difficulty=Difficulty.ADVANCED)

    with pytest.raises(
        ValueError,
        match="Stage 2 difficulty must be FOUNDATIONAL or INTERMEDIATE",
    ):
        select_stage3(invalid_state, question_bank, [3, 3])


@pytest.mark.parametrize(
    ("invalid_state", "message"),
    [
        pytest.param(object(), "Assessment state must be an AssessmentState", id="wrong-type"),
        pytest.param(
            AssessmentState(
                trade="Carpenter",
                used_question_ids=("E-F01", "E-F02"),
                stage1_question_ids=("E-F01", "E-F02"),
            ),
            "Unsupported trade",
            id="unsupported-state-trade",
        ),
        pytest.param(
            AssessmentState(
                trade=Trade.ELECTRICIAN,
                used_question_ids=("E-F01", "E-F02", "E-I01"),
                stage1_question_ids=("E-F01", "E-F02"),
            ),
            "used_question_ids do not match",
            id="inconsistent-used-ids",
        ),
        pytest.param(
            AssessmentState(
                trade=Trade.ELECTRICIAN,
                used_question_ids=("E-F01", "E-F02"),
                stage1_question_ids=("E-F01",),
            ),
            "exactly two distinct Stage 1",
            id="incomplete-stage1",
        ),
    ],
)
def test_invalid_assessment_states_are_rejected(
    question_bank, invalid_state, message
):
    with pytest.raises(ValueError, match=message):
        select_stage2(invalid_state, question_bank, [2, 2])


def test_stage2_with_incomplete_state_is_rejected(question_bank):
    state, _ = start_assessment(Trade.ELECTRICIAN, question_bank)
    incomplete_state = replace(
        state,
        stage2_difficulty=Difficulty.INTERMEDIATE,
    )

    with pytest.raises(ValueError, match="incomplete Stage 2 information"):
        select_stage3(incomplete_state, question_bank, [2, 2])


def test_stage3_cannot_be_selected_before_stage2(question_bank):
    state, _ = start_assessment(Trade.ELECTRICIAN, question_bank)

    with pytest.raises(ValueError, match="before Stage 2 is complete"):
        select_stage3(state, question_bank, [2, 2])


def test_stage2_cannot_be_selected_twice(question_bank):
    state, _ = start_assessment(Trade.PLUMBER, question_bank)
    state, _ = select_stage2(state, question_bank, [3, 3])

    with pytest.raises(ValueError, match="Stage 2 has already been selected"):
        select_stage2(state, question_bank, [3, 3])


def test_stage3_cannot_be_selected_twice(question_bank):
    state, _ = start_assessment(Trade.PLUMBER, question_bank)
    state, _ = select_stage2(state, question_bank, [3, 3])
    state, _ = select_stage3(state, question_bank, [3, 3])

    with pytest.raises(ValueError, match="Stage 3 has already been selected"):
        select_stage3(state, question_bank, [3, 3])


@pytest.mark.parametrize(
    ("mutate_bank", "message"),
    [
        pytest.param(
            lambda bank: bank[Trade.ELECTRICIAN].pop(Difficulty.ADVANCED),
            "must contain FOUNDATIONAL, INTERMEDIATE, and ADVANCED",
            id="missing-difficulty-group",
        ),
        pytest.param(
            lambda bank: bank[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL].pop(),
            "exactly four FOUNDATIONAL questions",
            id="insufficient-foundational-pool",
        ),
        pytest.param(
            lambda bank: bank[Trade.ELECTRICIAN][Difficulty.INTERMEDIATE].pop(),
            "exactly four INTERMEDIATE questions",
            id="insufficient-intermediate-pool",
        ),
        pytest.param(
            lambda bank: bank[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL].__setitem__(
                1,
                bank[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL][0],
            ),
            "duplicated in the Electrician bank",
            id="duplicate-question-id",
        ),
        pytest.param(
            lambda bank: bank[Trade.ELECTRICIAN][Difficulty.INTERMEDIATE].__setitem__(
                0,
                Question("E-I01", Difficulty.ADVANCED),
            ),
            "grouped under INTERMEDIATE",
            id="question-difficulty-mismatches-group",
        ),
        pytest.param(
            lambda bank: bank[Trade.ELECTRICIAN][Difficulty.ADVANCED].__setitem__(
                0,
                "not a Question",
            ),
            "Every bank entry must be a Question",
            id="non-question-entry",
        ),
        pytest.param(
            lambda bank: bank[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL].__setitem__(
                0,
                Question("   ", Difficulty.FOUNDATIONAL),
            ),
            "non-empty string question_id",
            id="empty-question-id",
        ),
        pytest.param(
            lambda bank: bank[Trade.ELECTRICIAN].__setitem__(
                Difficulty.ADVANCED,
                "not a question sequence",
            ),
            "must be a sequence",
            id="malformed-question-group",
        ),
    ],
)
def test_malformed_or_insufficient_question_banks_are_rejected(
    question_bank, mutate_bank, message
):
    mutate_bank(question_bank)

    with pytest.raises(ValueError, match=message):
        start_assessment(Trade.ELECTRICIAN, question_bank)


def test_stage2_rejects_insufficient_unused_question_pool(question_bank):
    """A malformed short pool must not silently produce fewer than two questions."""
    state, _ = start_assessment(Trade.ELECTRICIAN, question_bank)
    question_bank[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL].pop()

    with pytest.raises(ValueError, match="exactly four FOUNDATIONAL questions"):
        select_stage2(state, question_bank, [0, 0])


def test_question_bank_must_be_a_mapping():
    with pytest.raises(ValueError, match="must be a mapping"):
        start_assessment(Trade.ELECTRICIAN, [])


@pytest.mark.parametrize("trade", TRADES)
def test_returned_questions_have_declared_difficulty(question_bank, trade):
    """Every stage's selected questions agree with the route recorded in state."""
    state, stage1_questions = start_assessment(trade, question_bank)
    assert len(stage1_questions) == 2
    assert {question.difficulty for question in stage1_questions} == {
        Difficulty.FOUNDATIONAL
    }

    state, stage2_questions = select_stage2(state, question_bank, [1, 4])
    assert len(stage2_questions) == 2
    assert {question.difficulty for question in stage2_questions} == {
        state.stage2_difficulty
    }

    _, stage3_questions = select_stage3(state, question_bank, [0, 4])
    assert len(stage3_questions) == 2
    assert len({question.difficulty for question in stage3_questions}) == 1
