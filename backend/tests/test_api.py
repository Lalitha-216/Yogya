"""Backend tests. Gemini is replaced by a fake client here (tests only);
the application code itself contains no fake/sample behaviour."""
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from assessment.rubric_evaluator import (
    ConceptEvaluation,
    EvaluationResult,
)


class FakeModels:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(text=self.reply)


class FakeClient:
    def __init__(self, reply):
        self.models = FakeModels(reply)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(main, "_client", None)
    with TestClient(main.app) as c:
        yield c


def use_gemini(monkeypatch, reply):
    fake = FakeClient(reply)
    monkeypatch.setattr(main, "get_client", lambda: fake)
    return fake


GOOD = json.dumps(
    {"trade": "Electrician", "experience_years": 5, "skills": ["Fan installation", "Wiring repair"]}
)
BODY = {
    "name": "Ramesh",
    "language": "te",
    "location": "Kakinada",
    "selected_trade": "Electrician",
    "transcript": "Nenu five years nunchi electrician ga work chestunnanu.",
}


# --- DB path ---------------------------------------------------------------
def test_db_path_is_relative_to_backend_file():
    assert main.DB_PATH.parent == main.BASE_DIR
    assert main.DB_PATH.is_absolute()


# --- Transcript validation (no sample fallback) -----------------------------
@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_blank_transcript_rejected_and_nothing_saved(client, monkeypatch, text):
    fake = use_gemini(monkeypatch, GOOD)
    r = client.post("/api/profile/discover", json={**BODY, "transcript": text})
    assert r.status_code == 400
    assert "Transcript is required" in r.json()["detail"]
    assert fake.models.calls == []  # Gemini never called
    assert client.get("/api/workers/1").status_code == 404


def test_missing_transcript_rejected(client, monkeypatch):
    use_gemini(monkeypatch, GOOD)
    body = {k: v for k, v in BODY.items() if k != "transcript"}
    assert client.post("/api/profile/discover", json=body).status_code == 422


# --- Selected trade ---------------------------------------------------------
def test_selected_trade_required(client, monkeypatch):
    use_gemini(monkeypatch, GOOD)
    body = {k: v for k, v in BODY.items() if k != "selected_trade"}
    assert client.post("/api/profile/discover", json=body).status_code == 422


def test_invalid_trade_rejected(client, monkeypatch):
    use_gemini(monkeypatch, GOOD)
    r = client.post("/api/profile/discover", json={**BODY, "selected_trade": "Carpenter"})
    assert r.status_code == 422


def test_selected_trade_sent_to_gemini_and_saved(client, monkeypatch):
    fake = use_gemini(monkeypatch, json.dumps(
        {"trade": "Plumber", "experience_years": 3, "skills": ["Pipe fitting"]}))
    r = client.post("/api/profile/discover", json={**BODY, "selected_trade": "Plumber"})
    assert r.status_code == 200
    assert "declared their trade as: Plumber" in fake.models.calls[0]["contents"]
    assert client.get(f"/api/workers/{r.json()['worker_id']}").json()["trade"] == "Plumber"


def test_trade_mismatch_is_reported_not_hidden(client, monkeypatch):
    use_gemini(monkeypatch, json.dumps(
        {"trade": "Plumber", "experience_years": 2, "skills": ["Leak repair"]}))
    data = client.post("/api/profile/discover", json=BODY).json()  # selected Electrician
    assert data["profile"]["trade"] == "Electrician"
    assert data["detected_trade"] == "Plumber"
    assert data["trade_mismatch"] is True


# --- Extraction + persistence + GET ----------------------------------------
def test_discover_saves_profile_and_self_reported_skills(client, monkeypatch, tmp_path):
    use_gemini(monkeypatch, GOOD)
    r = client.post("/api/profile/discover", json=BODY)
    assert r.status_code == 200
    data = r.json()
    assert data["profile"]["evidence_level"] == "SELF_REPORTED"
    assert data["profile"]["skills"] == ["Fan installation", "Wiring repair"]
    assert data["trade_mismatch"] is False

    conn = sqlite3.connect(tmp_path / "test.db")
    assert conn.execute("select trade, experience_years, evidence_level, raw_transcript from workers").fetchall() == [
        ("Electrician", 5, "SELF_REPORTED", BODY["transcript"])]
    assert conn.execute("select skill_name, evidence_level from worker_skills order by id").fetchall() == [
        ("Fan installation", "SELF_REPORTED"), ("Wiring repair", "SELF_REPORTED")]


def test_get_worker_returns_saved_profile(client, monkeypatch):
    use_gemini(monkeypatch, GOOD)
    wid = client.post("/api/profile/discover", json=BODY).json()["worker_id"]
    r = client.get(f"/api/workers/{wid}")
    assert r.status_code == 200
    assert r.json() == {
        "id": wid, "name": "Ramesh", "language": "te", "location": "Kakinada",
        "raw_transcript": BODY["transcript"], "trade": "Electrician",
        "experience_years": 5, "evidence_level": "SELF_REPORTED",
        "skills": [
            {"skill_name": "Fan installation", "evidence_level": "SELF_REPORTED"},
            {"skill_name": "Wiring repair", "evidence_level": "SELF_REPORTED"},
        ],
    }


def test_get_unknown_worker_404(client):
    assert client.get("/api/workers/9999").status_code == 404


def test_model_cannot_set_evidence_level(client, monkeypatch):
    use_gemini(monkeypatch, json.dumps({
        "trade": "Electrician", "experience_years": 1, "skills": ["Wiring repair"],
        "evidence_level": "VERIFIED"}))
    data = client.post("/api/profile/discover", json=BODY).json()
    assert data["profile"]["evidence_level"] == "SELF_REPORTED"


def test_skills_cleaned_and_deduped(client, monkeypatch):
    use_gemini(monkeypatch, json.dumps({
        "trade": "Electrician", "experience_years": 1,
        "skills": ["  Fan   installation ", "fan installation", "", "Wiring repair"]}))
    skills = client.post("/api/profile/discover", json=BODY).json()["profile"]["skills"]
    assert skills == ["Fan installation", "Wiring repair"]


def test_no_skills_is_an_error_and_nothing_saved(client, monkeypatch):
    use_gemini(monkeypatch, json.dumps({"trade": "Other", "experience_years": 0, "skills": []}))
    assert client.post("/api/profile/discover", json=BODY).status_code == 422
    assert client.get("/api/workers/1").status_code == 404


def test_garbage_gemini_output_is_502(client, monkeypatch):
    use_gemini(monkeypatch, "not json at all")
    assert client.post("/api/profile/discover", json=BODY).status_code == 502


# --- Config / secrets -------------------------------------------------------
def test_missing_api_key_gives_clear_503(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = client.post("/api/profile/discover", json=BODY)
    assert r.status_code == 503
    assert "backend/.env" in r.json()["detail"]


def test_health_never_leaks_key(client):
    r = client.get("/api/health")
    assert r.json() == {"status": "ok", "gemini_configured": True}
    assert "test-key-not-real" not in r.text


# --- Transcription ----------------------------------------------------------
def post_audio(client, data=b"fake-audio-bytes", ctype="audio/webm;codecs=opus", language="te"):
    return client.post("/api/voice/transcribe",
                       files={"audio": ("rec.webm", data, ctype)}, data={"language": language})


def test_transcribe_returns_gemini_text_and_normalises_mime(client, monkeypatch):
    fake = use_gemini(monkeypatch, "  నేను ఐదు సంవత్సరాలు electrician  ")
    r = post_audio(client)
    assert r.status_code == 200
    assert r.json() == {"transcript": "నేను ఐదు సంవత్సరాలు electrician"}
    part = fake.models.calls[0]["contents"][0]
    assert part.inline_data.mime_type == "audio/webm"  # codecs suffix stripped
    assert "Telugu" in fake.models.calls[0]["contents"][1]


def test_transcribe_english_hint(client, monkeypatch):
    fake = use_gemini(monkeypatch, "I fix pipes")
    post_audio(client, language="en")
    assert "English" in fake.models.calls[0]["contents"][1]


@pytest.mark.parametrize("reply", ["", "   ", main.NO_SPEECH_SENTINEL])
def test_transcribe_no_speech_is_422_not_empty_success(client, monkeypatch, reply):
    use_gemini(monkeypatch, reply)
    assert post_audio(client).status_code == 422


def test_transcribe_empty_file_400(client, monkeypatch):
    use_gemini(monkeypatch, "x")
    assert post_audio(client, data=b"").status_code == 400


def test_transcribe_rejects_non_audio(client, monkeypatch):
    use_gemini(monkeypatch, "x")
    assert post_audio(client, ctype="text/plain").status_code == 415


def test_transcribe_gemini_failure_is_502(client, monkeypatch):
    use_gemini(monkeypatch, RuntimeError("boom"))
    assert post_audio(client).status_code == 502


# --- CORS -------------------------------------------------------------------
def test_cors_allows_vite_origin_only(client):
    ok = client.options("/api/profile/discover", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/api/profile/discover", headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def insert_assessment_test_worker(db_path, trade="Electrician"):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.execute(
        """
        INSERT INTO workers (
            name, language, location, raw_transcript, trade,
            experience_years, evidence_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "API Worker",
            "en",
            "Hyderabad",
            "I have practical trade experience.",
            trade,
            5,
            "SELF_REPORTED",
        ),
    )
    worker_id = cursor.lastrowid
    conn.execute(
        """
        INSERT INTO worker_skills (worker_id, skill_name, evidence_level)
        VALUES (?, ?, ?)
        """,
        (worker_id, "Wiring repair", "SELF_REPORTED"),
    )
    conn.commit()
    conn.close()
    return worker_id


def mock_answer_evaluator(monkeypatch, score=3, safety=False):
    def evaluator(question, answer, language):
        del answer, language
        concept_evaluations = tuple(
            ConceptEvaluation(
                concept=concept,
                demonstrated=True,
                evidence="I would isolate the supply",
                rationale=f"The answer supports {concept}.",
            )
            for concept in question.expected_concepts
        )
        return EvaluationResult(
            question_id=question.question_id,
            score=score,
            concept_evaluations=concept_evaluations,
            feedback="Answer-specific feedback.",
            safety_concerns=(),
            safety_critical_misconception=safety,
        )

    monkeypatch.setattr(main, "evaluate_answer", evaluator)


def test_start_assessment_api_returns_two_stage1_questions(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")

    response = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["trade"] == "Electrician"
    assert data["status"] == "IN_PROGRESS"
    assert data["current_stage"] == 1
    assert [question["question_id"] for question in data["questions"]] == ["E01", "E02"]
    assert all(question["question_order"] in (1, 2) for question in data["questions"])


def test_start_assessment_rejects_unknown_worker(client):
    response = client.post(
        "/api/assessments",
        json={"worker_id": 9999, "language": "en"},
    )
    assert response.status_code == 404


def test_start_assessment_rejects_invalid_language(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    response = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "fr"},
    )
    assert response.status_code == 422


def test_start_assessment_rejects_active_duplicate(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assert client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).status_code == 200

    response = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "te"},
    )
    assert response.status_code == 409


def test_assessment_progress_and_current_question(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "hi"},
    ).json()

    progress = client.get(f"/api/assessments/{assessment['assessment_id']}").json()
    current = client.get(
        f"/api/assessments/{assessment['assessment_id']}/questions/current"
    ).json()

    assert progress["assigned_question_count"] == 2
    assert progress["answered_question_count"] == 0
    assert progress["current_stage"] == 1
    assert current["question"]["question_id"] == "E01"


@pytest.mark.parametrize("answer_source", ["TEXT", "VOICE"])
def test_submit_answer_returns_score_feedback_and_safety(
    client,
    tmp_path,
    monkeypatch,
    answer_source,
):
    mock_answer_evaluator(monkeypatch)
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()

    response = client.post(
        f"/api/assessments/{assessment['assessment_id']}/answers",
        json={
            "question_id": "E01",
            "answer_text": "I would isolate the supply and use a tester.",
            "answer_source": answer_source,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["question_id"] == "E01"
    assert data["score"] == 3
    assert data["feedback"] == "Answer-specific feedback."
    assert data["safety_critical_misconception"] is False
    assert data["safety_concerns"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"question_id": "E01", "answer_text": "   ", "answer_source": "TEXT"},
        {"question_id": "E01", "answer_text": "Answer", "answer_source": "AUDIO"},
    ],
)
def test_submit_answer_rejects_invalid_input(client, tmp_path, payload):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()
    response = client.post(
        f"/api/assessments/{assessment['assessment_id']}/answers",
        json=payload,
    )
    assert response.status_code in (422, 400)


def test_duplicate_answer_returns_conflict(client, tmp_path, monkeypatch):
    mock_answer_evaluator(monkeypatch)
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()
    body = {
        "question_id": "E01",
        "answer_text": "I would isolate the supply.",
        "answer_source": "TEXT",
    }
    assert client.post(
        f"/api/assessments/{assessment['assessment_id']}/answers",
        json=body,
    ).status_code == 200
    response = client.post(
        f"/api/assessments/{assessment['assessment_id']}/answers",
        json=body,
    )
    assert response.status_code == 409


def test_unassigned_question_returns_validation_error(client, tmp_path, monkeypatch):
    mock_answer_evaluator(monkeypatch)
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()
    response = client.post(
        f"/api/assessments/{assessment['assessment_id']}/answers",
        json={
            "question_id": "E05",
            "answer_text": "Worker answer",
            "answer_source": "TEXT",
        },
    )
    assert response.status_code == 400


def test_stage_next_selects_stage2_and_stage3(client, tmp_path, monkeypatch):
    mock_answer_evaluator(monkeypatch, score=4)
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()
    assessment_id = assessment["assessment_id"]

    for question_id in ("E01", "E02"):
        assert client.post(
            f"/api/assessments/{assessment_id}/answers",
            json={
                "question_id": question_id,
                "answer_text": "I would isolate the supply.",
                "answer_source": "TEXT",
            },
        ).status_code == 200
    stage2 = client.post(
        f"/api/assessments/{assessment_id}/stages/next"
    )
    assert stage2.status_code == 200
    stage2_data = stage2.json()
    assert stage2_data["stage_number"] == 2
    assert len(stage2_data["questions"]) == 2

    for question in stage2_data["questions"]:
        assert client.post(
            f"/api/assessments/{assessment_id}/answers",
            json={
                "question_id": question["question_id"],
                "answer_text": "I would isolate the supply.",
                "answer_source": "TEXT",
            },
        ).status_code == 200
    stage3 = client.post(
        f"/api/assessments/{assessment_id}/stages/next"
    )
    assert stage3.status_code == 200
    stage3_data = stage3.json()
    assert stage3_data["stage_number"] == 3
    assert len(stage3_data["questions"]) == 2


def test_stage_advancement_rejected_after_only_one_answer(client, tmp_path, monkeypatch):
    mock_answer_evaluator(monkeypatch, score=4)
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()
    assessment_id = assessment["assessment_id"]

    submitted = client.post(
        f"/api/assessments/{assessment_id}/answers",
        json={
            "question_id": "E01",
            "answer_text": "I would isolate the supply.",
            "answer_source": "TEXT",
        },
    )
    assert submitted.status_code == 200

    advancement = client.post(
        f"/api/assessments/{assessment_id}/stages/next"
    )
    assert advancement.status_code == 400

    progress = client.get(
        f"/api/assessments/{assessment_id}"
    )
    assert progress.status_code == 200
    assert progress.json()["current_stage"] == 1
    assert progress.json()["answered_question_count"] == 1


def test_excessively_long_answer_is_rejected_by_validation(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()

    response = client.post(
        f"/api/assessments/{assessment['assessment_id']}/answers",
        json={
            "question_id": "E01",
            "answer_text": "A" * 5001,
            "answer_source": "TEXT",
        },
    )
    assert response.status_code == 422


def test_complete_and_results_endpoint(client, tmp_path, monkeypatch):
    mock_answer_evaluator(monkeypatch, score=4)
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()
    assessment_id = assessment["assessment_id"]

    for question_id in ("E01", "E02"):
        response = client.post(
            f"/api/assessments/{assessment_id}/answers",
            json={
                "question_id": question_id,
                "answer_text": "I would isolate the supply.",
                "answer_source": "TEXT",
            },
        )
        assert response.status_code == 200
    stage2_response = client.post(
        f"/api/assessments/{assessment_id}/stages/next"
    )
    assert stage2_response.status_code == 200
    with sqlite3.connect(tmp_path / "test.db") as conn:
        stage2_ids = [
            row[0]
            for row in conn.execute(
                "SELECT question_id FROM assessment_questions "
                "WHERE assessment_id = ? AND stage_number = 2 "
                "ORDER BY question_order",
                (assessment_id,),
            )
        ]
    for question_id in stage2_ids:
        response = client.post(
            f"/api/assessments/{assessment_id}/answers",
            json={
                "question_id": question_id,
                "answer_text": "I would isolate the supply.",
                "answer_source": "TEXT",
            },
        )
        assert response.status_code == 200
    stage3_response = client.post(
        f"/api/assessments/{assessment_id}/stages/next"
    )
    assert stage3_response.status_code == 200
    with sqlite3.connect(tmp_path / "test.db") as conn:
        stage3_ids = [
            row[0]
            for row in conn.execute(
                "SELECT question_id FROM assessment_questions "
                "WHERE assessment_id = ? AND stage_number = 3 "
                "ORDER BY question_order",
                (assessment_id,),
            )
        ]
    for question_id in stage3_ids:
        response = client.post(
            f"/api/assessments/{assessment_id}/answers",
            json={
                "question_id": question_id,
                "answer_text": "I would isolate the supply.",
                "answer_source": "TEXT",
            },
        )
        assert response.status_code == 200

    complete = client.post(
        f"/api/assessments/{assessment_id}/complete"
    )
    assert complete.status_code == 200
    assert complete.json()["total_score"] == 24
    assert complete.json()["maximum_score"] == 24
    assert complete.json()["score_percentage"] == 100.0

    results = client.get(
        f"/api/assessments/{assessment_id}/results"
    )
    assert results.status_code == 200
    assert results.json()["status"] == "COMPLETED"


def test_results_before_completion_returns_conflict(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()

    response = client.get(
        f"/api/assessments/{assessment['assessment_id']}/results"
    )
    assert response.status_code == 409
