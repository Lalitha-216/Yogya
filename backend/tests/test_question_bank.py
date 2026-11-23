"""Tests for the static multilingual occupational question bank."""

from copy import deepcopy
from dataclasses import replace

import pytest

from assessment.adaptive_engine import Difficulty, Question, Trade
from assessment.question_bank import (
    AssessmentQuestion,
    QUESTION_BANK,
    validate_question_bank,
)


EXPECTED_IDS = {
    Trade.ELECTRICIAN: {
        Difficulty.FOUNDATIONAL: ("E01", "E02", "E03", "E04"),
        Difficulty.INTERMEDIATE: ("E05", "E06", "E07", "E08"),
        Difficulty.ADVANCED: ("E09", "E10", "E11", "E12"),
    },
    Trade.PLUMBER: {
        Difficulty.FOUNDATIONAL: ("P01", "P02", "P03", "P04"),
        Difficulty.INTERMEDIATE: ("P05", "P06", "P07", "P08"),
        Difficulty.ADVANCED: ("P09", "P10", "P11", "P12"),
    },
}

REQUIRED_FIELDS = (
    "question_id",
    "trade",
    "difficulty",
    "skill_tag",
    "question_text_en",
    "question_text_te",
    "question_text_hi",
    "expected_concepts",
    "rubric_json",
    "safety_critical",
    "active",
    "telugu_review_required",
    "hindi_review_required",
)


def all_questions(bank=QUESTION_BANK):
    """Return all questions in trade and difficulty order."""
    return [
        question
        for trade_groups in bank.values()
        for questions in trade_groups.values()
        for question in questions
    ]


def replace_question(bank, trade_key, difficulty_group, index, **changes):
    """Replace one immutable question in a copied bank."""
    questions = list(bank[trade_key][difficulty_group])
    questions[index] = replace(questions[index], **changes)
    bank[trade_key][difficulty_group] = tuple(questions)


def test_bank_contains_exactly_electrician_and_plumber():
    assert set(QUESTION_BANK) == {Trade.ELECTRICIAN, Trade.PLUMBER}


@pytest.mark.parametrize("trade", (Trade.ELECTRICIAN, Trade.PLUMBER))
def test_each_trade_has_three_difficulty_groups_with_four_questions(trade):
    trade_bank = QUESTION_BANK[trade]

    assert set(trade_bank) == set(Difficulty)
    assert all(len(trade_bank[difficulty]) == 4 for difficulty in Difficulty)
    assert sum(len(group) for group in trade_bank.values()) == 12


def test_all_24_ids_are_unique_and_follow_the_required_order():
    ids = [
        question.question_id
        for trade in (Trade.ELECTRICIAN, Trade.PLUMBER)
        for difficulty in (
            Difficulty.FOUNDATIONAL,
            Difficulty.INTERMEDIATE,
            Difficulty.ADVANCED,
        )
        for question in QUESTION_BANK[trade][difficulty]
    ]

    assert len(ids) == 24
    assert len(set(ids)) == 24
    assert ids == [f"E{number:02d}" for number in range(1, 13)] + [
        f"P{number:02d}" for number in range(1, 13)
    ]


@pytest.mark.parametrize("trade", (Trade.ELECTRICIAN, Trade.PLUMBER))
@pytest.mark.parametrize("difficulty", tuple(Difficulty))
def test_question_ids_trade_and_difficulty_match_mapping(trade, difficulty):
    questions = QUESTION_BANK[trade][difficulty]

    assert tuple(question.question_id for question in questions) == EXPECTED_IDS[trade][difficulty]
    assert all(question.trade == trade for question in questions)
    assert all(question.difficulty == difficulty for question in questions)


def test_every_bank_question_is_compatible_with_adaptive_engine():
    assert len(all_questions()) == 24
    assert all(isinstance(question, Question) for question in all_questions())
    assert all(isinstance(question, AssessmentQuestion) for question in all_questions())


def test_every_question_has_all_required_fields_populated():
    for question in all_questions():
        for field in REQUIRED_FIELDS:
            assert hasattr(question, field), f"{question.question_id} is missing {field}"

        assert question.question_id.strip()
        assert question.skill_tag.strip()
        assert question.question_text_en.strip()
        assert question.question_text_te.strip()
        assert question.question_text_hi.strip()
        assert question.expected_concepts
        assert isinstance(question.rubric_json, dict)


def test_all_translations_are_present_and_marked_for_review():
    for question in all_questions():
        assert question.question_text_en.strip()
        assert question.question_text_te.strip()
        assert question.question_text_hi.strip()
        assert question.telugu_review_required is True
        assert question.hindi_review_required is True


def test_every_rubric_has_exactly_five_nonempty_score_descriptions():
    expected_levels = {"0", "1", "2", "3", "4"}
    for question in all_questions():
        assert set(question.rubric_json) == expected_levels
        assert all(
            isinstance(description, str) and description.strip()
            for description in question.rubric_json.values()
        )


def test_safety_and_active_flags_are_booleans():
    for question in all_questions():
        assert type(question.safety_critical) is bool
        assert type(question.active) is bool


def test_validate_question_bank_accepts_the_question_bank():
    assert validate_question_bank() is None


def test_validation_rejects_missing_difficulty_group():
    bank = deepcopy(QUESTION_BANK)
    del bank[Trade.ELECTRICIAN][Difficulty.ADVANCED]

    with pytest.raises(ValueError, match="all three difficulty groups"):
        validate_question_bank(bank)


def test_validation_rejects_missing_question():
    bank = deepcopy(QUESTION_BANK)
    bank[Trade.PLUMBER][Difficulty.INTERMEDIATE] = bank[Trade.PLUMBER][
        Difficulty.INTERMEDIATE
    ][:3]

    with pytest.raises(ValueError, match="exactly four INTERMEDIATE questions"):
        validate_question_bank(bank)


def test_validation_rejects_duplicate_question_id():
    bank = deepcopy(QUESTION_BANK)
    duplicate_id = bank[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL][0].question_id
    replace_question(
        bank,
        Trade.ELECTRICIAN,
        Difficulty.FOUNDATIONAL,
        1,
        question_id=duplicate_id,
    )

    with pytest.raises(ValueError, match="Duplicate question ID"):
        validate_question_bank(bank)


def test_validation_rejects_incorrect_trade_assignment():
    bank = deepcopy(QUESTION_BANK)
    replace_question(
        bank,
        Trade.ELECTRICIAN,
        Difficulty.FOUNDATIONAL,
        0,
        trade=Trade.PLUMBER,
    )

    with pytest.raises(ValueError, match="incorrect trade assignment"):
        validate_question_bank(bank)


def test_validation_rejects_incorrect_difficulty_assignment():
    bank = deepcopy(QUESTION_BANK)
    replace_question(
        bank,
        Trade.ELECTRICIAN,
        Difficulty.FOUNDATIONAL,
        0,
        difficulty=Difficulty.ADVANCED,
    )

    with pytest.raises(ValueError, match="incorrect difficulty assignment"):
        validate_question_bank(bank)


def test_validation_rejects_missing_hindi_text():
    bank = deepcopy(QUESTION_BANK)
    replace_question(
        bank,
        Trade.PLUMBER,
        Difficulty.FOUNDATIONAL,
        0,
        question_text_hi="",
    )

    with pytest.raises(ValueError, match="missing Hindi question text"):
        validate_question_bank(bank)


def test_validation_rejects_missing_telugu_text():
    bank = deepcopy(QUESTION_BANK)
    replace_question(
        bank,
        Trade.PLUMBER,
        Difficulty.FOUNDATIONAL,
        0,
        question_text_te="",
    )

    with pytest.raises(ValueError, match="Telugu wording must be marked for review"):
        validate_question_bank(bank)


def test_validation_rejects_missing_rubric_score_level():
    bank = deepcopy(QUESTION_BANK)
    question = bank[Trade.PLUMBER][Difficulty.ADVANCED][0]
    incomplete_rubric = dict(question.rubric_json)
    del incomplete_rubric["4"]
    replace_question(
        bank,
        Trade.PLUMBER,
        Difficulty.ADVANCED,
        0,
        rubric_json=incomplete_rubric,
    )

    with pytest.raises(ValueError, match="rubric must cover scores 0 through 4"):
        validate_question_bank(bank)
