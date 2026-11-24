"""Tests for deterministic, evidence-based assessment rubric evaluation."""

from dataclasses import replace

import pytest

from assessment.adaptive_engine import Difficulty, Trade
from assessment.question_bank import QUESTION_BANK
from assessment.rubric_evaluator import _CONCEPT_CUES
from assessment.rubric_evaluator import (
    EvaluationResponseValidationError,
    InputValidationError,
    evaluate_answer,
)


QUESTION = QUESTION_BANK[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL][2]
TOOL_QUESTION = QUESTION_BANK[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL][0]
COMPLETE_ANSWER = (
    "I would isolate the supply and use a suitable tester "
    "to verify that no voltage is present."
)


def test_every_question_bank_concept_has_a_deterministic_evidence_rule():
    concepts = {
        concept
        for trade_questions in QUESTION_BANK.values()
        for difficulty_questions in trade_questions.values()
        for question in difficulty_questions
        for concept in question.expected_concepts
    }

    assert concepts == set(_CONCEPT_CUES)


def test_complete_rubric_evidence_scores_three_without_reasoning():
    result = evaluate_answer(QUESTION, COMPLETE_ANSWER, "en")

    assert result.question_id == QUESTION.question_id
    assert result.score == 3
    assert [item.demonstrated for item in result.concept_evaluations] == [True, True]
    assert [item.evidence for item in result.concept_evaluations] == [
        "isolate the supply",
        "verify that no voltage is present",
    ]
    assert result.safety_concerns == ()
    assert result.safety_critical_misconception is False


def test_complete_evidence_with_rubric_reasoning_scores_four():
    answer = (
        "I would isolate the supply and use a suitable tester to verify that "
        "no voltage is present because this prevents electric shock."
    )

    result = evaluate_answer(QUESTION, answer, "en")

    assert result.score == 4
    assert all(item.demonstrated for item in result.concept_evaluations)


def test_partial_evidence_is_not_treated_as_demonstrated():
    result = evaluate_answer(QUESTION, "I checked voltage with a tester.", "en")

    assert result.score == 1
    assert [item.demonstrated for item in result.concept_evaluations] == [False, False]


@pytest.mark.parametrize(
    "answer",
    [
        "",
        "   ",
        "I like going to the market.",
        "I would check it.",
    ],
)
def test_empty_unclear_and_irrelevant_answers_score_zero(answer):
    if not answer.strip():
        with pytest.raises(InputValidationError, match="non-empty"):
            evaluate_answer(QUESTION, answer, "en")
    else:
        assert evaluate_answer(QUESTION, answer, "en").score == 0


@pytest.mark.parametrize(
    ("answer", "language"),
    [
        (
            "సరఫరాను నిలిపి టెస్టర్‌తో వోల్టేజ్ లేదని పరీక్షించాలి.",
            "te",
        ),
        (
            "बिजली बंद करके टेस्टर से जाँचें कि वोल्टेज नहीं है।",
            "hi",
        ),
    ],
)
def test_telugu_and_hindi_explicit_rubric_evidence_is_recognized(answer, language):
    result = evaluate_answer(QUESTION, answer, language)

    assert result.score == 3
    assert all(item.demonstrated for item in result.concept_evaluations)


def test_only_points_supported_by_the_question_rubric_are_counted():
    answer = (
        "I would use a screwdriver with a suitable tip because it fits the screw "
        "and helps prevent damage. I would also replace the whole circuit."
    )

    result = evaluate_answer(TOOL_QUESTION, answer, "en")

    assert result.score == 4
    assert all(item.demonstrated for item in result.concept_evaluations)
    assert all(item.evidence in answer for item in result.concept_evaluations)


def test_explicit_unsafe_statement_creates_safety_finding_without_changing_score():
    answer = (
        "I would work while the power is still on. "
        "I would isolate the supply and use a suitable tester "
        "to verify that no voltage is present."
    )

    result = evaluate_answer(QUESTION, answer, "en")

    assert result.score == 3
    assert result.safety_critical_misconception is True
    assert len(result.safety_concerns) == 1
    assert result.safety_concerns[0].evidence == "work while the power is still on"
    assert result.safety_concerns[0].evidence in answer


def test_negated_unsafe_phrase_is_not_reported_as_a_misconception():
    answer = (
        "I would not work while the power is still on. "
        "I would isolate the supply and use a suitable tester "
        "to verify that no voltage is present."
    )

    result = evaluate_answer(QUESTION, answer, "en")

    assert result.safety_critical_misconception is False
    assert result.safety_concerns == ()


def test_unsupported_safety_claim_does_not_create_safety_flag():
    question = replace(QUESTION, safety_critical=False)
    answer = "I would work while the power is still on."

    result = evaluate_answer(question, answer, "en")

    assert result.safety_critical_misconception is False
    assert result.safety_concerns == ()


def test_invalid_language_and_rubric_are_rejected():
    with pytest.raises(InputValidationError, match="answer_language"):
        evaluate_answer(QUESTION, COMPLETE_ANSWER, "fr")

    malformed = replace(QUESTION, rubric_json={"0": "not a complete rubric"})
    with pytest.raises(EvaluationResponseValidationError, match="levels"):
        evaluate_answer(malformed, COMPLETE_ANSWER, "en")


def test_evaluator_result_has_no_assessment_progression_or_verification_authority():
    result = evaluate_answer(QUESTION, COMPLETE_ANSWER, "en")

    assert not hasattr(result, "stage")
    assert not hasattr(result, "next_question")
    assert not hasattr(result, "evidence_level")
    assert not hasattr(result, "verified_competence")
