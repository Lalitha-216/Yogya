"""Tests for six-answer numerical assessment scoring."""

from dataclasses import FrozenInstanceError, fields
from decimal import Decimal

import pytest

from assessment.scoring import AssessmentScore, calculate_score


@pytest.mark.parametrize(
    "answer_scores",
    [
        [0, 1, 2, 3, 4, 1],
        (0, 1, 2, 3, 4, 1),
    ],
    ids=("list", "tuple"),
)
def test_calculate_score_accepts_list_and_tuple(answer_scores):
    result = calculate_score(answer_scores)

    assert result == AssessmentScore(
        total_score=11,
        maximum_score=24,
        percentage=Decimal("45.83"),
    )


def test_calculate_score_uses_two_decimal_places_for_percentage():
    result = calculate_score([0, 1, 2, 3, 4, 1])

    assert isinstance(result.percentage, Decimal)
    assert result.percentage.as_tuple().exponent == -2
    assert result.percentage == Decimal("45.83")


@pytest.mark.parametrize(
    ("answer_scores", "expected_total", "expected_percentage"),
    [
        ([0, 0, 0, 0, 0, 0], 0, Decimal("0.00")),
        ([4, 4, 4, 4, 4, 4], 24, Decimal("100.00")),
        ([0, 4, 0, 4, 0, 4], 12, Decimal("50.00")),
    ],
    ids=("all-zero", "all-four", "boundary-scores"),
)
def test_calculate_score_handles_boundaries(
    answer_scores,
    expected_total,
    expected_percentage,
):
    result = calculate_score(answer_scores)

    assert result.total_score == expected_total
    assert result.maximum_score == 24
    assert result.percentage == expected_percentage


@pytest.mark.parametrize(
    "invalid_score",
    [
        pytest.param(True, id="boolean"),
        pytest.param(False, id="false-boolean"),
        pytest.param(1.0, id="float"),
        pytest.param("1", id="string"),
        pytest.param(None, id="none"),
        pytest.param(-1, id="negative-integer"),
        pytest.param(5, id="integer-above-four"),
    ],
)
def test_calculate_score_rejects_invalid_values(invalid_score):
    answer_scores = [0, 1, 2, 3, 4, 1]
    answer_scores[0] = invalid_score

    with pytest.raises(ValueError, match=r"answer_scores\[0\]"):
        calculate_score(answer_scores)


@pytest.mark.parametrize(
    "answer_scores",
    [
        pytest.param([], id="empty"),
        pytest.param([1, 2, 3, 4, 0], id="fewer-than-six"),
        pytest.param([1, 2, 3, 4, 0, 1, 2], id="more-than-six"),
    ],
)
def test_calculate_score_requires_exactly_six_scores(answer_scores):
    with pytest.raises(ValueError, match="exactly six"):
        calculate_score(answer_scores)


@pytest.mark.parametrize(
    "answer_scores",
    [
        pytest.param("123456", id="string"),
        pytest.param(b"123456", id="bytes"),
        pytest.param(bytearray(b"123456"), id="bytearray"),
    ],
)
def test_calculate_score_rejects_string_like_inputs(answer_scores):
    with pytest.raises(ValueError, match="not a string or bytes"):
        calculate_score(answer_scores)


def test_calculate_score_rejects_non_sequence_input():
    with pytest.raises(ValueError, match="must be a sequence"):
        calculate_score(iter([0, 1, 2, 3, 4, 1]))


def test_assessment_score_has_only_numerical_fields():
    result = calculate_score([0, 1, 2, 3, 4, 1])

    assert tuple(field.name for field in fields(AssessmentScore)) == (
        "total_score",
        "maximum_score",
        "percentage",
    )
    assert not hasattr(result, "safety_critical")
    assert not hasattr(result, "safety_concerns")


def test_assessment_score_is_frozen():
    result = calculate_score([0, 1, 2, 3, 4, 1])

    with pytest.raises(FrozenInstanceError):
        result.total_score = 12
