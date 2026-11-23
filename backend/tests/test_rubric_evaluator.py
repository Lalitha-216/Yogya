"""Unit tests for rubric-based answer evaluation without live Gemini calls."""

import json
import math
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors

import assessment.rubric_evaluator as evaluator
from assessment.adaptive_engine import Difficulty, Trade
from assessment.question_bank import QUESTION_BANK, AssessmentQuestion
from assessment.rubric_evaluator import (
    ConceptEvaluation,
    EvaluationResponseValidationError,
    EvaluatorConfigurationError,
    EvaluatorServiceError,
    EvaluationResult,
    InputValidationError,
    SafetyConcern,
    evaluate_answer,
)


ANSWER = (
    "I would isolate the supply. Then I would use a suitable tester "
    "to verify that no voltage is present."
)
UNSAFE_ANSWER = (
    "I would replace the wire while the power is still on. "
    "I would not isolate the supply. "
    "I would not use a tester to check for voltage."
)
TOOL_QUESTION = QUESTION_BANK[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL][0]
TOOL_ANSWER = (
    "I would use a screwdriver with a suitable tip because it fits the screw "
    "and helps prevent damage."
)
TOOL_UNSAFE_ANSWER = (
    f"{TOOL_ANSWER} I would replace the wire while the power is still on."
)
QUESTION = QUESTION_BANK[Trade.ELECTRICIAN][Difficulty.FOUNDATIONAL][2]
CONCEPT_EVIDENCE = {
    "supply must be isolated": "isolate the supply",
    "absence of voltage must be verified with a suitable tester":
        "use a suitable tester to verify that no voltage is present",
}
UNSAFE_CONCEPT_EVIDENCE = {
    "supply must be isolated": "not isolate the supply",
    "absence of voltage must be verified with a suitable tester":
        "not use a tester to check for voltage",
}
TOOL_CONCEPT_EVIDENCE = {
    "screwdriver with a suitable tip": "screwdriver with a suitable tip",
    "correct fit helps avoid damaging the screw": "it fits the screw and helps prevent damage",
}


class FakeModels:
    def __init__(self, response_text=None, error=None):
        self.response_text = response_text
        self.error = error
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.response_text)


class FakeClient:
    def __init__(self, response_text=None, error=None):
        self.models = FakeModels(response_text=response_text, error=error)


@pytest.fixture(autouse=True)
def clear_evaluator_client(monkeypatch):
    monkeypatch.setattr(evaluator, "_client", None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def valid_response(
    question=QUESTION,
    *,
    score=3,
    answer=ANSWER,
    evidence_by_concept=None,
    **overrides,
):
    if evidence_by_concept is None:
        evidence_by_concept = CONCEPT_EVIDENCE
    for concept in question.expected_concepts:
        assert concept in evidence_by_concept
        evidence = evidence_by_concept[concept]
        assert evidence is None or evidence in answer
    response = {
        "score": score,
        "concept_evaluations": [
            {
                "concept": concept,
                "demonstrated": evidence_by_concept[concept] is not None,
                "evidence": evidence_by_concept[concept],
                "rationale": (
                    f'The answer says "{evidence_by_concept[concept]}", '
                    f"which supports this concept: {concept}."
                    if evidence_by_concept[concept] is not None
                    else f'The answer "{answer}" does not demonstrate this concept: {concept}.'
                ),
            }
            for concept in question.expected_concepts
        ],
        "feedback": "You described the isolation and testing checks.",
        "safety_concerns": [],
        "safety_critical_misconception": False,
    }
    response.update(overrides)
    return json.dumps(response, allow_nan=True)


def test_evaluate_answer_uses_the_localized_question_and_expected_inputs():
    client = FakeClient(valid_response())

    result = evaluate_answer(QUESTION, ANSWER, "en", client=client)

    assert isinstance(result, EvaluationResult)
    assert result.question_id == QUESTION.question_id
    assert result.score == 3
    assert all(isinstance(item, ConceptEvaluation) for item in result.concept_evaluations)
    assert [item.concept for item in result.concept_evaluations] == list(
        QUESTION.expected_concepts
    )
    assert result.feedback
    assert result.safety_concerns == ()
    assert result.safety_critical_misconception is False

    request = client.models.calls[0]
    assert request["model"] == "gemini-3.8-flash"
    assert QUESTION.question_text_en in request["contents"]
    assert ANSWER in request["contents"]
    for concept in QUESTION.expected_concepts:
        assert concept in request["contents"]
    for level, rubric_text in QUESTION.rubric_json.items():
        assert f'"{level}":' in request["contents"]
        assert rubric_text in request["contents"]
    assert "not keyword matching" in request["contents"]
    assert "untrusted data" in request["contents"]
    assert request["config"].response_mime_type == "application/json"


@pytest.mark.parametrize(
    ("language", "localized_field"),
    [
        ("en", "question_text_en"),
        ("te", "question_text_te"),
        ("hi", "question_text_hi"),
    ],
)
def test_evaluate_answer_uses_requested_language(language, localized_field):
    client = FakeClient(valid_response())

    evaluate_answer(QUESTION, ANSWER, language, client=client)

    prompt = client.models.calls[0]["contents"]
    assert getattr(QUESTION, localized_field) in prompt
    assert "concept field using the supplied English expected_concepts names unchanged" in prompt
    assert "write every concept rationale in English" in prompt
    assert (
        "Preserve every evidence excerpt exactly as written in the worker's original answer"
        in prompt
    )
    assert "do not translate, transliterate, normalize, correct, or alter" in prompt
    feedback_language = {
        "en": "en means English",
        "te": "te means Telugu",
        "hi": "hi means Hindi",
    }[language]
    assert "Write worker-facing feedback in the selected answer_language" in prompt
    assert feedback_language in prompt


@pytest.mark.parametrize("score", [0, 1, 2, 3, 4])
def test_accepts_each_integer_score_level(score):
    client = FakeClient(valid_response(score=score))

    result = evaluate_answer(QUESTION, ANSWER, "en", client=client)

    assert result.score == score


@pytest.mark.parametrize(
    ("answer", "language", "question", "message"),
    [
        pytest.param(" \n\t ", "en", QUESTION, "answer must be", id="blank-answer"),
        pytest.param(123, "en", QUESTION, "answer must be", id="non-string-answer"),
        pytest.param(ANSWER, "fr", QUESTION, "answer_language", id="unsupported-language"),
        pytest.param(ANSWER, [], QUESTION, "answer_language", id="unhashable-language"),
        pytest.param(ANSWER, "en", object(), "AssessmentQuestion", id="wrong-question-type"),
        pytest.param(
            ANSWER,
            "en",
            replace(QUESTION, question_text_en=" \t "),
            "no usable en question text",
            id="missing-localized-question",
        ),
        pytest.param(
            ANSWER,
            "te",
            replace(QUESTION, question_text_te=""),
            "no usable te question text",
            id="missing-telugu-question",
        ),
        pytest.param(
            ANSWER,
            "hi",
            replace(QUESTION, question_text_hi=""),
            "no usable hi question text",
            id="missing-hindi-question",
        ),
        pytest.param(
            ANSWER,
            "en",
            replace(QUESTION, expected_concepts=()),
            "expected_concepts",
            id="empty-concepts",
        ),
        pytest.param(
            ANSWER,
            "en",
            replace(
                QUESTION, expected_concepts=("concept", "concept")
            ),
            "duplicate concepts",
            id="duplicate-input-concepts",
        ),
        pytest.param(
            ANSWER,
            "en",
            replace(QUESTION, safety_critical="yes"),
            "safety_critical",
            id="invalid-safety-flag",
        ),
    ],
)
def test_invalid_inputs_are_rejected_before_gemini(answer, language, question, message):
    client = FakeClient(valid_response())

    with pytest.raises(InputValidationError, match=message):
        evaluate_answer(question, answer, language, client=client)

    assert client.models.calls == []


@pytest.mark.parametrize(
    ("rubric", "message"),
    [
        pytest.param({}, "exactly the levels", id="empty-rubric"),
        pytest.param(
            {**QUESTION.rubric_json, "5": "extra"},
            "exactly the levels",
            id="extra-rubric-level",
        ),
        pytest.param(
            {key: value for key, value in QUESTION.rubric_json.items() if key != "4"},
            "exactly the levels",
            id="missing-rubric-level",
        ),
        pytest.param(
            {**QUESTION.rubric_json, "4": "  "},
            "non-empty description",
            id="blank-rubric-description",
        ),
        pytest.param(
            {**QUESTION.rubric_json, "4": 4},
            "non-empty description",
            id="non-string-rubric-description",
        ),
    ],
)
def test_invalid_rubrics_are_rejected_before_gemini(rubric, message):
    question = replace(QUESTION, rubric_json=rubric)
    client = FakeClient(valid_response(question))

    with pytest.raises(InputValidationError, match=message):
        evaluate_answer(question, ANSWER, "en", client=client)

    assert client.models.calls == []


@pytest.mark.parametrize("raw_response", ["{", "", "not JSON", '{"score": NaN}'])
def test_rejects_malformed_or_nonstandard_json(raw_response):
    client = FakeClient(raw_response)

    with pytest.raises(EvaluationResponseValidationError, match="invalid evaluation JSON|empty"):
        evaluate_answer(QUESTION, ANSWER, "en", client=client)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        pytest.param(lambda result: result.pop("score"), "exactly the required", id="missing-field"),
        pytest.param(
            lambda result: result.update(unrequested="value"),
            "exactly the required",
            id="extra-field",
        ),
        pytest.param(
            lambda result: result.update(score=True),
            "integer from 0 through 4",
            id="boolean-score",
        ),
        pytest.param(
            lambda result: result.update(score=2.0),
            "integer from 0 through 4",
            id="float-score",
        ),
        pytest.param(
            lambda result: result.update(score="2"),
            "integer from 0 through 4",
            id="string-score",
        ),
        pytest.param(
            lambda result: result.update(score=math.inf),
            "invalid evaluation JSON",
            id="infinite-score",
        ),
        pytest.param(
            lambda result: result.update(score=math.nan),
            "invalid evaluation JSON",
            id="nan-score",
        ),
        pytest.param(
            lambda result: result.update(score=-1),
            "integer from 0 through 4",
            id="score-too-low",
        ),
        pytest.param(
            lambda result: result.update(score=5),
            "integer from 0 through 4",
            id="score-too-high",
        ),
        pytest.param(
            lambda result: result.update(feedback=" "),
            "feedback.*non-empty",
            id="empty-feedback",
        ),
        pytest.param(
            lambda result: result.update(feedback=12),
            "feedback.*non-empty",
            id="non-string-feedback",
        ),
        pytest.param(
            lambda result: result.update(concept_evaluations="not a list"),
            "concept_evaluations.*array",
            id="invalid-concept-container",
        ),
        pytest.param(
            lambda result: result["concept_evaluations"][0].update(demonstrated=1),
            "demonstrated value must be a Boolean",
            id="invalid-demonstrated-type",
        ),
        pytest.param(
            lambda result: result["concept_evaluations"][0].update(extra="field"),
            "exactly concept, demonstrated, evidence, and rationale",
            id="extra-concept-result-field",
        ),
        pytest.param(
            lambda result: result["concept_evaluations"][0].update(evidence="not quoted"),
            "quote the worker answer verbatim",
            id="ungrounded-concept-evidence",
        ),
        pytest.param(
            lambda result: result["concept_evaluations"][0].update(evidence=42),
            "concept evidence.*non-empty string",
            id="invalid-concept-evidence-type",
        ),
        pytest.param(
            lambda result: result["concept_evaluations"][0].update(rationale=" "),
            "concept rationale.*non-empty",
            id="empty-concept-rationale",
        ),
        pytest.param(
            lambda result: result["concept_evaluations"][0].update(
                rationale="This concept is demonstrated."
            ),
            "rationale must quote and explain",
            id="rationale-does-not-cite-evidence",
        ),
        pytest.param(
            lambda result: result.update(safety_concerns="unsafe"),
            "safety_concerns.*array",
            id="invalid-safety-concerns-container",
        ),
        pytest.param(
            lambda result: result.update(safety_critical_misconception="false"),
            "safety_critical_misconception must be a Boolean",
            id="string-misconception-flag",
        ),
    ],
)
def test_rejects_invalid_response_fields_and_types(mutation, message):
    response = json.loads(valid_response())
    mutation(response)
    client = FakeClient(json.dumps(response, allow_nan=True))

    with pytest.raises(EvaluationResponseValidationError, match=message):
        evaluate_answer(QUESTION, ANSWER, "en", client=client)


@pytest.mark.parametrize(
    ("mutate_concepts", "message"),
    [
        pytest.param(
            lambda items: items.pop(),
            "Every expected concept must be evaluated exactly once",
            id="missing-concept",
        ),
        pytest.param(
            lambda items: items.__setitem__(1, dict(items[0])),
            "exactly once",
            id="duplicate-concept",
        ),
        pytest.param(
            lambda items: items.__setitem__(0, {**items[0], "concept": "unexpected"}),
            "match expected concepts exactly",
            id="extra-concept",
        ),
    ],
)
def test_rejects_missing_duplicate_or_extra_concepts(mutate_concepts, message):
    response = json.loads(valid_response())
    mutate_concepts(response["concept_evaluations"])
    client = FakeClient(json.dumps(response))

    with pytest.raises(EvaluationResponseValidationError, match=message):
        evaluate_answer(QUESTION, ANSWER, "en", client=client)


def test_i_dont_know_can_leave_all_concepts_undemonstrated():
    answer = "I don't know."
    missing_evidence = {concept: None for concept in QUESTION.expected_concepts}
    client = FakeClient(
        valid_response(
            answer=answer,
            evidence_by_concept=missing_evidence,
            score=0,
        )
    )

    result = evaluate_answer(QUESTION, answer, "en", client=client)

    assert result.score == 0
    assert all(not item.demonstrated for item in result.concept_evaluations)
    assert all(item.evidence is None for item in result.concept_evaluations)
    assert all("does not demonstrate" in item.rationale for item in result.concept_evaluations)
    assert result.safety_concerns == ()
    assert result.safety_critical_misconception is False


def test_answer_may_omit_one_expected_concept():
    answer = "I would isolate the supply."
    concept_evidence = {
        "supply must be isolated": "isolate the supply",
        "absence of voltage must be verified with a suitable tester": None,
    }
    client = FakeClient(
        valid_response(
            answer=answer,
            evidence_by_concept=concept_evidence,
            score=2,
        )
    )

    result = evaluate_answer(QUESTION, answer, "en", client=client)

    assert result.score == 2
    assert result.concept_evaluations[0].demonstrated is True
    assert result.concept_evaluations[0].evidence == "isolate the supply"
    assert result.concept_evaluations[1].demonstrated is False
    assert result.concept_evaluations[1].evidence is None
    assert "does not demonstrate" in result.concept_evaluations[1].rationale


def test_non_demonstrated_concept_allows_null_evidence():
    answer = "I don't know."
    concept_evidence = {
        "supply must be isolated": None,
        "absence of voltage must be verified with a suitable tester": None,
    }
    client = FakeClient(
        valid_response(answer=answer, evidence_by_concept=concept_evidence, score=0)
    )

    result = evaluate_answer(QUESTION, answer, "en", client=client)

    assert all(item.evidence is None for item in result.concept_evaluations)
    assert all(item.demonstrated is False for item in result.concept_evaluations)


def test_non_demonstrated_concept_allows_relevant_quoted_evidence():
    answer = "I would not use a tester to check for voltage."
    concept = "absence of voltage must be verified with a suitable tester"
    response = json.loads(
        valid_response(
            answer=answer,
            evidence_by_concept={
                "supply must be isolated": None,
                concept: "not use a tester to check for voltage",
            },
            score=1,
        )
    )
    response["concept_evaluations"][1]["demonstrated"] = False
    response["concept_evaluations"][1]["rationale"] = (
        f'The answer says "not use a tester to check for voltage", so it does not '
        f"demonstrate this concept: {concept}."
    )
    client = FakeClient(json.dumps(response))

    result = evaluate_answer(QUESTION, answer, "en", client=client)

    non_demonstrated = result.concept_evaluations[1]
    assert non_demonstrated.demonstrated is False
    assert non_demonstrated.evidence == "not use a tester to check for voltage"
    assert non_demonstrated.evidence in non_demonstrated.rationale
    assert "does not demonstrate" in non_demonstrated.rationale


def test_demonstrated_concept_with_null_evidence_is_rejected():
    response = json.loads(valid_response())
    response["concept_evaluations"][0]["evidence"] = None
    client = FakeClient(json.dumps(response))

    with pytest.raises(EvaluationResponseValidationError, match="concept evidence.*non-empty string"):
        evaluate_answer(QUESTION, ANSWER, "en", client=client)


def test_non_demonstrated_concept_requires_absence_rationale():
    answer = "I don't know."
    response = json.loads(
        valid_response(
            answer=answer,
            evidence_by_concept={concept: None for concept in QUESTION.expected_concepts},
            score=0,
        )
    )
    response["concept_evaluations"][0]["rationale"] = "No supporting details."
    client = FakeClient(json.dumps(response))

    with pytest.raises(EvaluationResponseValidationError, match="does not demonstrate that concept"):
        evaluate_answer(QUESTION, answer, "en", client=client)


@pytest.mark.parametrize("invalid_evidence", [42, True, [], {}])
def test_non_demonstrated_concept_rejects_invalid_evidence_types(invalid_evidence):
    answer = "I don't know."
    response = json.loads(
        valid_response(
            answer=answer,
            evidence_by_concept={concept: None for concept in QUESTION.expected_concepts},
            score=0,
        )
    )
    response["concept_evaluations"][0]["evidence"] = invalid_evidence
    client = FakeClient(json.dumps(response))

    with pytest.raises(EvaluationResponseValidationError, match="concept evidence.*non-empty string"):
        evaluate_answer(QUESTION, answer, "en", client=client)


def test_rejects_duplicate_json_object_keys():
    response = valid_response()
    response = response.replace('"score": 3', '"score": 3, "score": 2')
    client = FakeClient(response)

    with pytest.raises(EvaluationResponseValidationError, match="invalid evaluation JSON"):
        evaluate_answer(QUESTION, ANSWER, "en", client=client)


def test_rejects_invalid_safety_concern_structure():
    response = json.loads(valid_response())
    response["safety_concerns"] = [{"concern": "missing evidence"}]
    client = FakeClient(json.dumps(response))

    with pytest.raises(EvaluationResponseValidationError, match="concern and evidence"):
        evaluate_answer(QUESTION, ANSWER, "en", client=client)


def test_rejects_ungrounded_safety_concern():
    response = json.loads(valid_response())
    response["safety_concerns"] = [
        {"concern": "Dangerous claim", "evidence": "not in the answer"}
    ]
    client = FakeClient(json.dumps(response))

    with pytest.raises(EvaluationResponseValidationError, match="quote the worker answer verbatim"):
        evaluate_answer(QUESTION, ANSWER, "en", client=client)


def test_safety_concern_must_quote_its_evidence():
    response = json.loads(valid_response(answer=UNSAFE_ANSWER, evidence_by_concept=UNSAFE_CONCEPT_EVIDENCE))
    response["safety_critical_misconception"] = True
    response["safety_concerns"] = [
        {
            "concern": "The answer indicates an electric-shock risk.",
            "evidence": "while the power is still on",
        }
    ]
    client = FakeClient(json.dumps(response))

    with pytest.raises(EvaluationResponseValidationError, match="safety concern must quote"):
        evaluate_answer(QUESTION, UNSAFE_ANSWER, "en", client=client)


def test_safety_critical_misconception_requires_a_specific_grounded_concern():
    response = json.loads(
        valid_response(
            score=1,
            answer=UNSAFE_ANSWER,
            evidence_by_concept=UNSAFE_CONCEPT_EVIDENCE,
        )
    )
    response["safety_critical_misconception"] = True
    response["safety_concerns"] = [
        {
            "concern": (
                'The statement "while the power is still on" describes working '
                "on an energized wire, creating an electric-shock risk."
            ),
            "evidence": "while the power is still on",
        }
    ]
    client = FakeClient(json.dumps(response))

    result = evaluate_answer(QUESTION, UNSAFE_ANSWER, "en", client=client)

    assert result.score == 1
    assert result.safety_critical_misconception is True
    assert result.safety_concerns == (
        SafetyConcern(
            concern=(
                'The statement "while the power is still on" describes working '
                "on an energized wire, creating an electric-shock risk."
            ),
            evidence="while the power is still on",
        ),
    )


def test_true_misconception_without_concern_is_rejected():
    response = json.loads(
        valid_response(
            answer=UNSAFE_ANSWER,
            evidence_by_concept=UNSAFE_CONCEPT_EVIDENCE,
        )
    )
    response["safety_critical_misconception"] = True
    client = FakeClient(json.dumps(response))

    with pytest.raises(EvaluationResponseValidationError, match="requires at least one"):
        evaluate_answer(QUESTION, UNSAFE_ANSWER, "en", client=client)


def test_non_safety_critical_question_cannot_have_misconception_flag():
    answer = TOOL_UNSAFE_ANSWER
    response = json.loads(
        valid_response(
            TOOL_QUESTION,
            answer=answer,
            evidence_by_concept=TOOL_CONCEPT_EVIDENCE,
        )
    )
    response["safety_critical_misconception"] = True
    response["safety_concerns"] = [
        {
            "concern": (
                'The statement "while the power is still on" describes working '
                "on an energized wire, creating an electric-shock risk."
            ),
            "evidence": "while the power is still on",
        }
    ]
    client = FakeClient(json.dumps(response))

    with pytest.raises(EvaluationResponseValidationError, match="non-safety-critical"):
        evaluate_answer(TOOL_QUESTION, answer, "en", client=client)


@pytest.mark.parametrize("score", [0, 1, 2, 3, 4])
def test_safety_concerns_do_not_change_numeric_score(score):
    response = json.loads(
        valid_response(
            score=score,
            answer=UNSAFE_ANSWER,
            evidence_by_concept=UNSAFE_CONCEPT_EVIDENCE,
        )
    )
    response["safety_critical_misconception"] = True
    response["safety_concerns"] = [
        {
            "concern": (
                'The statement "while the power is still on" describes working '
                "on an energized wire, creating an electric-shock risk."
            ),
            "evidence": "while the power is still on",
        }
    ]
    client = FakeClient(json.dumps(response))

    result = evaluate_answer(QUESTION, UNSAFE_ANSWER, "en", client=client)

    assert result.score == score
    assert result.safety_critical_misconception is True


def test_missing_api_key_raises_configuration_error(monkeypatch):
    client = FakeClient(valid_response())
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(evaluator, "_client", None)

    with pytest.raises(EvaluatorConfigurationError, match="GEMINI_API_KEY"):
        evaluate_answer(QUESTION, ANSWER, "en")

    assert client.models.calls == []


def test_client_initialization_error_logs_only_safe_context(monkeypatch, caplog):
    secret = "do-not-log-this-key"
    monkeypatch.setenv("GEMINI_API_KEY", secret)

    def fail_client_initialization(**kwargs):
        assert kwargs["api_key"] == secret
        raise RuntimeError(f"initialization failed for {secret}")

    monkeypatch.setattr(evaluator.genai, "Client", fail_client_initialization)

    with pytest.raises(EvaluatorConfigurationError):
        evaluator._get_client()

    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("timeout"),
        TimeoutError("timeout"),
    ],
)
def test_timeout_raises_service_error_without_leaking_details(error):
    client = FakeClient(error=error)

    with pytest.raises(EvaluatorServiceError, match="timed out") as caught:
        evaluate_answer(QUESTION, ANSWER, "en", client=client)

    assert "timeout" not in str(caught.value).lower()
    assert len(client.models.calls) == 1


def test_gemini_api_error_raises_safe_service_error():
    client = FakeClient(error=genai_errors.APIError(503, {}))

    with pytest.raises(EvaluatorServiceError, match="could not complete"):
        evaluate_answer(QUESTION, ANSWER, "en", client=client)

    assert len(client.models.calls) == 1


def test_other_provider_failure_raises_service_error():
    client = FakeClient(error=RuntimeError("secret-bearing provider details"))

    with pytest.raises(EvaluatorServiceError, match="could not complete") as caught:
        evaluate_answer(QUESTION, ANSWER, "en", client=client)

    assert "secret-bearing" not in str(caught.value)
    assert len(client.models.calls) == 1


def test_result_has_no_assessment_progression_or_evidence_authority():
    assert isinstance(QUESTION, AssessmentQuestion)
    client = FakeClient(valid_response())

    result = evaluate_answer(QUESTION, ANSWER, "en", client=client)

    assert not hasattr(result, "stage")
    assert not hasattr(result, "next_question")
    assert not hasattr(result, "evidence_level")
    assert not hasattr(result, "verified_competence")
