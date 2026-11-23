"""Aggregate the six numerical scores in an assessment."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


_QUESTION_COUNT = 6
_MAXIMUM_QUESTION_SCORE = 4
_MAXIMUM_SCORE = _QUESTION_COUNT * _MAXIMUM_QUESTION_SCORE
_PERCENTAGE_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class AssessmentScore:
    """Numerical total and percentage for one completed assessment."""

    total_score: int
    maximum_score: int
    percentage: Decimal


def calculate_score(answer_scores: Sequence[int]) -> AssessmentScore:
    """Validate six integer answer scores and calculate their aggregate."""
    if isinstance(answer_scores, (str, bytes, bytearray)):
        raise ValueError("answer_scores must be a sequence, not a string or bytes.")
    if not isinstance(answer_scores, Sequence):
        raise ValueError("answer_scores must be a sequence containing exactly six scores.")
    if len(answer_scores) != _QUESTION_COUNT:
        raise ValueError("answer_scores must contain exactly six scores.")

    for index, score in enumerate(answer_scores):
        if type(score) is not int:
            raise ValueError(
                f"answer_scores[{index}] must be an integer from 0 through 4; "
                "booleans are not accepted."
            )
        if not 0 <= score <= _MAXIMUM_QUESTION_SCORE:
            raise ValueError(f"answer_scores[{index}] must be between 0 and 4.")

    total_score = sum(answer_scores)
    percentage = (
        Decimal(total_score) * Decimal(100) / Decimal(_MAXIMUM_SCORE)
    ).quantize(_PERCENTAGE_QUANTUM, rounding=ROUND_HALF_UP)

    return AssessmentScore(
        total_score=total_score,
        maximum_score=_MAXIMUM_SCORE,
        percentage=percentage,
    )
