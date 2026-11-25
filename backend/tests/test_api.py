"""Backend tests. Gemini is replaced by a fake client here (tests only);
the application code itself contains no fake/sample behaviour."""
import base64
import io
import json
import sqlite3
import wave
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors
from google.genai import errors as genai_errors

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


class FakeSequenceModels:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply)


class FakeInteractions:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


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


def use_gemini_sequence(monkeypatch, replies):
    fake = SimpleNamespace(models=FakeSequenceModels(replies))
    monkeypatch.setattr(main, "get_client", lambda: fake)
    return fake


def gemini_api_error(code):
    return genai_errors.APIError(code, {"error": {"message": "provider failure"}})


def use_gemini_tts(monkeypatch, reply):
    fake = SimpleNamespace(interactions=FakeInteractions(reply))
    monkeypatch.setattr(main, "get_client", lambda: fake)
    return fake


def make_test_wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\0\0" * 24)
    return output.getvalue()


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
        "extraction_source": "gemini",
        "skills": [
            {"skill_name": "Fan installation", "evidence_level": "SELF_REPORTED"},
            {"skill_name": "Wiring repair", "evidence_level": "SELF_REPORTED"},
        ],
    }


def test_gemini_503_falls_back_and_persists_profile(client, monkeypatch, tmp_path):
    transcript = "  I repair wiring and install ceiling fans. I have worked for five years.  "
    use_gemini(
        monkeypatch,
        genai_errors.APIError(503, {"error": {"message": "model experiencing high demand"}}),
    )

    response = client.post(
        "/api/profile/discover",
        json={**BODY, "language": "en", "transcript": transcript},
    )

    assert response.status_code == 200
    data = response.json()
    worker_id = data["worker_id"]
    assert type(worker_id) is int and worker_id > 0
    assert data["profile"]["skills"] == ["Fan installation", "Wiring repair"]
    assert data["profile"]["experience_years"] == 5
    assert data["profile"]["evidence_level"] == "SELF_REPORTED"
    assert data["profile"]["extraction_source"] == "rule_based_fallback"
    assert data["detected_trade"] is None
    assert data["trade_mismatch"] is None

    worker = client.get(f"/api/workers/{worker_id}")
    assert worker.status_code == 200
    assert worker.json()["raw_transcript"] == transcript
    assert worker.json()["extraction_source"] == "rule_based_fallback"
    assert all(
        skill["evidence_level"] == "SELF_REPORTED"
        for skill in worker.json()["skills"]
    )
    with sqlite3.connect(tmp_path / "test.db") as conn:
        assert conn.execute(
            "SELECT experience_years, experience_known, extraction_source FROM workers"
        ).fetchone() == (5, 1, "rule_based_fallback")


def test_gemini_failure_extracts_socket_repairing_and_wiring_example(client, monkeypatch):
    use_gemini(
        monkeypatch,
        genai_errors.APIError(503, {"error": {"message": "temporarily unavailable"}}),
    )
    transcript = "I have 5 years experience in repairing sockets and wiring."

    response = client.post(
        "/api/profile/discover",
        json={**BODY, "language": "en", "transcript": transcript},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["profile"]["experience_years"] == 5
    assert set(data["profile"]["skills"]) == {"Socket repair", "Wiring repair"}
    assert data["profile"]["extraction_source"] == "rule_based_fallback"
    assert data["profile"]["evidence_level"] == "SELF_REPORTED"
    worker = client.get(f"/api/workers/{data['worker_id']}").json()
    assert {skill["skill_name"] for skill in worker["skills"]} == {
        "Socket repair",
        "Wiring repair",
    }
    assert all(skill["evidence_level"] == "SELF_REPORTED" for skill in worker["skills"])


@pytest.mark.parametrize(
    "failure",
    [
        genai_errors.APIError(429, {"error": {"message": "rate limited"}}),
        httpx.ReadTimeout("request timed out"),
        httpx.ConnectError("temporarily unavailable"),
    ],
)
def test_other_transient_gemini_failures_use_fallback(client, monkeypatch, failure):
    use_gemini(monkeypatch, failure)
    transcript = "I repair wiring."

    response = client.post(
        "/api/profile/discover",
        json={**BODY, "language": "en", "transcript": transcript},
    )

    assert response.status_code == 200
    assert response.json()["profile"]["extraction_source"] == "rule_based_fallback"
    assert response.json()["profile"]["skills"] == ["Wiring repair"]


def test_fallback_keeps_unknown_experience_unknown(client, monkeypatch, tmp_path):
    use_gemini(
        monkeypatch,
        genai_errors.APIError(503, {"error": {"message": "temporarily unavailable"}}),
    )

    response = client.post(
        "/api/profile/discover",
        json={**BODY, "transcript": "I repair wiring."},
    )

    assert response.status_code == 200
    worker_id = response.json()["worker_id"]
    assert response.json()["profile"]["experience_years"] is None
    worker = client.get(f"/api/workers/{worker_id}")
    assert worker.json()["experience_years"] is None
    passport = client.get(f"/api/workers/{worker_id}/passport").json()
    assert passport["worker_profile"]["experience"]["years"] is None
    assert passport["worker_profile"]["extraction_source"] == "rule_based_fallback"
    with sqlite3.connect(tmp_path / "test.db") as conn:
        assert conn.execute(
            "SELECT experience_years, experience_known FROM workers"
        ).fetchone() == (0, 0)


def test_fallback_without_supported_skills_still_creates_profile(client, monkeypatch):
    use_gemini(
        monkeypatch,
        genai_errors.APIError(503, {"error": {"message": "temporarily unavailable"}}),
    )

    response = client.post(
        "/api/profile/discover",
        json={**BODY, "transcript": "I am an electrician."},
    )

    assert response.status_code == 200
    assert response.json()["profile"]["skills"] == []
    assert response.json()["profile"]["experience_years"] is None
    assert response.json()["profile"]["extraction_source"] == "rule_based_fallback"
    assert client.get(f"/api/workers/{response.json()['worker_id']}").status_code == 200


def test_rule_based_extraction_supports_telugu_and_ignores_negative_claims():
    assert main.extract_rule_based_profile(
        "ఫ్యాన్ అమర్చడం, వైరింగ్ మరమ్మత్తు. ఐదు సంవత్సరాలు పని.",
        "Electrician",
    ) == (5, ["Fan installation", "Wiring repair"])
    assert main.extract_rule_based_profile(
        "I don't repair wiring.",
        "Electrician",
    ) == (None, [])


@pytest.mark.parametrize(
    ("trade", "transcript", "expected_skills"),
    [
        (
            "Electrician",
            "I fixed an electrical socket and installed two light switches.",
            {"Socket repair", "Switch installation"},
        ),
        (
            "Electrician",
            "I install lights and fans, and repair circuit breakers.",
            {"Light installation", "Fan installation", "Circuit breaker work"},
        ),
        (
            "Electrician",
            "I diagnose electrical faults and work on electrical wiring.",
            {"Electrical fault diagnosis", "Wiring repair"},
        ),
        (
            "Plumber",
            "I repaired pipes and installed taps.",
            {"Pipe repair", "Tap installation and repair"},
        ),
        (
            "Plumber",
            "I detect leaks and clean drains.",
            {"Leak detection", "Drainage work"},
        ),
        (
            "Plumber",
            "I fit bathroom fixtures and install water pumps.",
            {"Bathroom fitting", "Water pump installation"},
        ),
    ],
)
def test_rule_based_extraction_recognizes_trade_task_variations(
    trade, transcript, expected_skills
):
    experience_years, skills = main.extract_rule_based_profile(transcript, trade)
    assert experience_years is None
    assert set(skills) == expected_skills


@pytest.mark.parametrize(
    ("trade", "transcript"),
    [
        (
            "Electrician",
            "I read about sockets, wiring diagrams, switches, and circuit breakers.",
        ),
        (
            "Plumber",
            "I read about pipes, taps, leaks, drains, bathroom fixtures, and water pumps.",
        ),
    ],
)
def test_rule_based_extraction_ignores_unrelated_skill_word_mentions(trade, transcript):
    assert main.extract_rule_based_profile(transcript, trade) == (None, [])


def test_rule_based_extraction_keeps_positive_mention_after_negation():
    assert main.extract_rule_based_profile(
        "I don't repair wiring, but I install wiring.",
        "Electrician",
    ) == (None, ["Wiring repair"])


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


def use_sarvam_responses(monkeypatch, replies, api_key="sarvam-test-key"):
    monkeypatch.setenv("SARVAM_API_KEY", api_key)
    requests = []

    def handle_request(request):
        requests.append(request)
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    transport = httpx.MockTransport(handle_request)
    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        main.httpx,
        "AsyncClient",
        lambda *args, **kwargs: original_async_client(
            *args, transport=transport, **kwargs
        ),
    )
    return requests


def sarvam_response(status_code, payload):
    return httpx.Response(status_code, json=payload)


def test_transcribe_telugu_uses_sarvam_and_preserves_response_contract(
    client, monkeypatch
):
    requests = use_sarvam_responses(
        monkeypatch,
        [sarvam_response(200, {
            "transcript": "నేను ఐదు సంవత్సరాలు electrician",
            "language_code": "te-IN",
            "request_id": "request-123",
        })],
    )

    response = post_audio(client)

    assert response.status_code == 200
    assert response.json() == {"transcript": "నేను ఐదు సంవత్సరాలు electrician"}
    request = requests[0]
    assert request.url == main.SARVAM_TRANSCRIPTION_URL
    assert request.headers["api-subscription-key"] == "sarvam-test-key"
    assert b'name="file"; filename="rec.webm"' in request.content
    assert b"fake-audio-bytes" in request.content
    assert b'name="model"' in request.content and b"saaras:v4" in request.content
    assert b'name="mode"' in request.content and b"transcribe" in request.content
    assert b'name="language_code"' in request.content and b"te-IN" in request.content
    assert b"audio/webm" in request.content


def test_transcribe_english_uses_sarvam_language_code(client, monkeypatch):
    requests = use_sarvam_responses(
        monkeypatch,
        [sarvam_response(200, {"transcript": "I fix pipes", "language_code": "en-IN"})],
    )

    response = post_audio(client, language="en")

    assert response.status_code == 200
    assert response.json() == {"transcript": "I fix pipes"}
    assert b"en-IN" in requests[0].content


def test_transcribe_hindi_uses_sarvam_language_code(client, monkeypatch):
    requests = use_sarvam_responses(
        monkeypatch,
        [sarvam_response(200, {"transcript": "मैं पाइप ठीक करता हूँ", "language_code": "hi-IN"})],
    )

    response = post_audio(client, language="hi")

    assert response.status_code == 200
    assert response.json() == {"transcript": "मैं पाइप ठीक करता हूँ"}
    assert b"hi-IN" in requests[0].content


def test_transcribe_empty_file_is_rejected_before_provider_request(client, monkeypatch):
    requests = use_sarvam_responses(monkeypatch, [])

    response = post_audio(client, data=b"")

    assert response.status_code == 400
    assert requests == []


def test_transcribe_oversized_file_is_rejected_before_provider_request(
    client, monkeypatch
):
    requests = use_sarvam_responses(monkeypatch, [])
    monkeypatch.setattr(main, "MAX_AUDIO_BYTES", 4)

    response = post_audio(client, data=b"12345")

    assert response.status_code == 413
    assert "too large" in response.json()["detail"]
    assert requests == []


def test_transcribe_missing_sarvam_key_is_clear_and_does_not_call_provider(
    client, monkeypatch
):
    requests = use_sarvam_responses(monkeypatch, [])
    monkeypatch.delenv("SARVAM_API_KEY")

    response = post_audio(client)

    assert response.status_code == 503
    assert "SARVAM_API_KEY" in response.json()["detail"]
    assert requests == []


def test_transcribe_rejects_unsupported_audio_format(client, monkeypatch):
    requests = use_sarvam_responses(monkeypatch, [])

    response = post_audio(client, ctype="text/plain")

    assert response.status_code == 415
    assert "Unsupported audio format" in response.json()["detail"]
    assert requests == []


def test_transcribe_quota_exhaustion_is_not_retried(client, monkeypatch):
    requests = use_sarvam_responses(
        monkeypatch,
        [
            sarvam_response(
                429,
                {
                    "error": {
                        "code": "insufficient_quota_error",
                        "message": "The account quota is exhausted",
                    }
                },
            )
        ],
    )

    response = post_audio(client)

    assert response.status_code == 429
    assert "credits or quota are exhausted" in response.json()["detail"]
    assert len(requests) == 1


@pytest.mark.parametrize(
    "first_response",
    [
        sarvam_response(
            429,
            {
                "error": {
                    "code": "rate_limit_exceeded_error",
                    "message": "Rate limit exceeded, retry soon",
                }
            },
        ),
        sarvam_response(503, {"error": {"message": "Temporarily unavailable"}}),
    ],
)
def test_transcribe_retries_temporary_sarvam_errors(
    client, monkeypatch, first_response
):
    requests = use_sarvam_responses(
        monkeypatch,
        [first_response, sarvam_response(200, {"transcript": "recognized words"})],
    )
    delays = []

    async def record_delay(delay):
        delays.append(delay)

    monkeypatch.setattr(main, "_wait_for_sarvam_retry", record_delay)

    response = post_audio(client)

    assert response.status_code == 200
    assert response.json() == {"transcript": "recognized words"}
    assert len(requests) == 2
    assert delays == [main.SARVAM_TRANSCRIPTION_RETRY_BASE_SECONDS]


def test_transcribe_stops_after_bounded_sarvam_503_retries(client, monkeypatch):
    requests = use_sarvam_responses(
        monkeypatch,
        [
            sarvam_response(503, {"error": {"message": "Temporarily unavailable"}})
            for _ in range(main.SARVAM_TRANSCRIPTION_MAX_ATTEMPTS)
        ],
    )
    delays = []

    async def record_delay(delay):
        delays.append(delay)

    monkeypatch.setattr(main, "_wait_for_sarvam_retry", record_delay)

    response = post_audio(client)

    assert response.status_code == 503
    assert len(requests) == main.SARVAM_TRANSCRIPTION_MAX_ATTEMPTS
    assert delays == [0.5, 1.0]


def test_transcribe_timeout_is_reported_without_retry(client, monkeypatch):
    requests = use_sarvam_responses(
        monkeypatch,
        [httpx.ReadTimeout("provider timed out")],
    )

    response = post_audio(client)

    assert response.status_code == 504
    assert "timed out" in response.json()["detail"]
    assert len(requests) == 1


def test_transcribe_empty_provider_transcript_is_422(client, monkeypatch):
    use_sarvam_responses(monkeypatch, [sarvam_response(200, {"transcript": "  "})])

    response = post_audio(client)

    assert response.status_code == 422
    assert "No speech was detected" in response.json()["detail"]


def test_transcribe_maps_sarvam_duration_limit_error(client, monkeypatch):
    use_sarvam_responses(
        monkeypatch,
        [
            sarvam_response(
                400,
                {"error": {"message": "Audio duration exceeds the 30 seconds limit"}},
            )
        ],
    )

    response = post_audio(client)

    assert response.status_code == 413
    assert "30-second REST limit" in response.json()["detail"]


def test_transcribe_maps_sarvam_422_without_exposing_provider_details(
    client, monkeypatch, caplog
):
    requests = use_sarvam_responses(
        monkeypatch,
        [
            sarvam_response(
                422,
                {
                    "error": {
                        "code": "unprocessable_entity_error",
                        "message": "provider-internal validation text",
                    }
                },
            )
        ],
    )

    response = post_audio(client)

    assert response.status_code == 422
    assert "supported recording" in response.json()["detail"]
    assert "provider-internal" not in response.json()["detail"]
    assert "code=unprocessable_entity_error" in caplog.text
    assert len(requests) == 1


def test_transcribe_invalid_sarvam_key_is_not_retried(client, monkeypatch):
    requests = use_sarvam_responses(
        monkeypatch,
        [sarvam_response(401, {"error": {"message": "invalid api key"}})],
    )

    response = post_audio(client)

    assert response.status_code == 502
    assert "Sarvam rejected the API key" in response.json()["detail"]
    assert len(requests) == 1


# --- Telugu speech generation -----------------------------------------------
def test_speak_telugu_returns_wav_from_gemini(client, monkeypatch):
    audio = make_test_wav()
    interaction = SimpleNamespace(
        output_audio=SimpleNamespace(data=base64.b64encode(audio).decode("ascii"))
    )
    fake = use_gemini_tts(monkeypatch, interaction)

    response = client.post(
        "/api/voice/speak",
        json={"text": "యోగ్యకు స్వాగతం", "language": "te-IN"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == audio
    call = fake.interactions.calls[0]
    assert call["model"] == main.TTS_MODEL_NAME
    assert call["api_version"] == "v1beta"
    assert call["response_format"] == {"type": "audio", "mime_type": "audio/wav"}
    assert call["input"][0]["content"][0]["text"] == "యోగ్యకు స్వాగతం"


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "", "language": "te-IN"},
        {"text": " \n ", "language": "te-IN"},
        {"text": "x" * (main.MAX_TTS_TEXT_CHARS + 1), "language": "te-IN"},
        {"text": "తెలుగు", "language": "te"},
    ],
)
def test_speak_telugu_validates_request(client, monkeypatch, payload):
    fake = use_gemini_tts(monkeypatch, None)

    response = client.post("/api/voice/speak", json=payload)

    assert response.status_code == 422
    assert fake.interactions.calls == []


def test_speak_telugu_requires_server_api_key(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    response = client.post(
        "/api/voice/speak",
        json={"text": "తెలుగు మాటలు", "language": "te-IN"},
    )

    assert response.status_code == 503


@pytest.mark.parametrize(
    ("reply", "expected_status"),
    [
        (genai_errors.APIError(429, {"error": {"message": "limited"}}), 429),
        (TimeoutError("request timed out"), 504),
        (RuntimeError("provider error"), 502),
    ],
)
def test_speak_telugu_maps_provider_failures(
    client, monkeypatch, reply, expected_status
):
    use_gemini_tts(monkeypatch, reply)

    response = client.post(
        "/api/voice/speak",
        json={"text": "తెలుగు మాటలు", "language": "te-IN"},
    )

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "output_audio",
    [None, SimpleNamespace(data=""), SimpleNamespace(data="not-base64")],
)
def test_speak_telugu_rejects_empty_or_invalid_audio(
    client, monkeypatch, output_audio
):
    fake = use_gemini_tts(
        monkeypatch, SimpleNamespace(output_audio=output_audio)
    )

    response = client.post(
        "/api/voice/speak",
        json={"text": "తెలుగు మాటలు", "language": "te-IN"},
    )

    assert response.status_code == 502
    assert fake.interactions.calls


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


def test_submit_answer_succeeds_when_gemini_is_unavailable(
    client,
    tmp_path,
    monkeypatch,
):
    class UnavailableGemini:
        def __init__(self):
            self.calls = 0

        def generate_content(self, **kwargs):
            self.calls += 1
            raise genai_errors.APIError(
                503,
                {"error": {"message": "model experiencing high demand"}},
            )

    unavailable_gemini = UnavailableGemini()
    monkeypatch.setattr(main, "_client", SimpleNamespace(models=unavailable_gemini))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()

    response = client.post(
        f"/api/assessments/{assessment['assessment_id']}/answers",
        json={
            "question_id": "E01",
            "answer_text": (
                "I would use a screwdriver with a suitable tip because it fits "
                "the screw and helps prevent damage."
            ),
            "answer_source": "TEXT",
        },
    )

    assert response.status_code == 200
    assert response.json()["score"] == 4
    assert all(
        item["demonstrated"]
        for item in response.json()["concept_evaluations"]
    )
    assert unavailable_gemini.calls == 0
    progress = client.get(
        f"/api/assessments/{assessment['assessment_id']}"
    ).json()
    assert progress["answered_question_count"] == 1
    assert progress["current_stage"] == 1


def test_answer_retry_persists_once_and_advances_only_after_both_answers(
    client,
    tmp_path,
):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()
    assessment_id = assessment["assessment_id"]
    first_answer = {
        "question_id": "E01",
        "answer_text": (
            "I would use a screwdriver with a suitable tip because it fits the "
            "screw and helps prevent damage."
        ),
        "answer_source": "TEXT",
    }

    first = client.post(
        f"/api/assessments/{assessment_id}/answers",
        json=first_answer,
    )
    retry = client.post(
        f"/api/assessments/{assessment_id}/answers",
        json=first_answer,
    )
    assert first.status_code == 200
    assert first.json()["score"] == 4
    assert retry.status_code == 409
    progress_after_retry = client.get(
        f"/api/assessments/{assessment_id}"
    ).json()
    assert progress_after_retry["answered_question_count"] == 1
    assert progress_after_retry["current_stage"] == 1

    second = client.post(
        f"/api/assessments/{assessment_id}/answers",
        json={
            "question_id": "E02",
            "answer_text": (
                "A switch controls the electrical supply to a load, and a socket "
                "provides a connection for an appliance because it lets the "
                "appliance receive power."
            ),
            "answer_source": "TEXT",
        },
    )
    assert second.status_code == 200
    assert second.json()["score"] == 4
    advanced = client.post(
        f"/api/assessments/{assessment_id}/stages/next"
    )
    assert advanced.status_code == 200
    assert advanced.json()["stage_number"] == 2
    assert advanced.json()["stage2_difficulty"] == "INTERMEDIATE"
    assert client.get(
        f"/api/assessments/{assessment_id}"
    ).json()["answered_question_count"] == 2


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


def test_passport_unknown_worker_returns_404(client):
    response = client.get("/api/workers/9999/passport")
    assert response.status_code == 404


def test_passport_without_assessment_is_valid_and_has_empty_evidence(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")

    response = client.get(f"/api/workers/{worker_id}/passport")

    assert response.status_code == 200
    data = response.json()
    assert data["worker_profile"]["worker_id"] == worker_id
    assert data["assessment_summary"]["status"] == "NO_ASSESSMENT"
    assert data["assessment_summary"]["total_score"] is None
    assert data["assessment_evidence"]["demonstrated_concepts"] == []
    assert data["assessment_evidence"]["relevant_feedback"] == []
    assert data["assessment_evidence"]["safety"]["concerns"] == []
    assert "raw_transcript" not in str(data)


def test_passport_with_in_progress_assessment_uses_empty_assessment_evidence(
    client,
    tmp_path,
):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    assessment = client.post(
        "/api/assessments",
        json={"worker_id": worker_id, "language": "en"},
    ).json()

    response = client.get(f"/api/workers/{worker_id}/passport")

    assert response.status_code == 200
    data = response.json()
    assert data["assessment_summary"]["assessment_id"] == assessment["assessment_id"]
    assert data["assessment_summary"]["status"] == "IN_PROGRESS"
    assert data["assessment_summary"]["total_score"] is None
    assert data["assessment_evidence"]["demonstrated_concepts"] == []


def test_passport_completed_assessment_includes_persisted_evidence(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            """
            UPDATE worker_skills
            SET evidence_level = 'SELF_REPORTED'
            WHERE worker_id = ?
            """,
            (worker_id,),
        )
        cursor = conn.execute(
            """
            INSERT INTO assessments (
                worker_id, trade, language, status, current_stage,
                total_score, max_score, score_percentage, safety_flags_json,
                started_at, completed_at
            ) VALUES (?, 'Electrician', 'en', 'COMPLETED', 3,
                      18, 24, 75.0, ?, ?, ?)
            """,
            (
                worker_id,
                '{"safety_critical_misconception":true,"concerns":[]}',
                "2026-01-01T00:00:00+00:00",
                "2026-01-02T00:00:00+00:00",
            ),
        )
        assessment_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO assessment_questions (
                assessment_id, question_id, stage_number, question_order,
                selection_reason, selected_at
            ) VALUES (?, 'E03', 1, 1, 'Test selection',
                      '2026-01-01T00:00:00+00:00')
            """,
            (assessment_id,),
        )
        conn.execute(
            """
            INSERT INTO assessment_answers (
                assessment_id, question_id, stage_number, answer_text,
                answer_source, score, rubric_feedback_json, safety_flag,
                safety_reason, safety_concerns_json, answered_at
            ) VALUES (?, 'E03', 1, 'Test answer', 'TEXT', 4, ?, 1,
                      'Unsafe working practice',
                      '[{"concern":"Working while live","evidence":"power is on"}]',
                      '2026-01-02T00:00:00+00:00')
            """,
            (
                assessment_id,
                '{"feedback":"Accurate isolation explanation","concept_evaluations":[{"concept":"supply must be isolated","demonstrated":true,"evidence":"isolate the supply","rationale":"The answer demonstrates isolation"}]}',
            ),
        )
        conn.commit()

    response = client.get(f"/api/workers/{worker_id}/passport")

    assert response.status_code == 200
    data = response.json()
    assert data["assessment_summary"]["assessment_id"] == assessment_id
    assert data["assessment_summary"]["status"] == "COMPLETED"
    assert data["assessment_summary"]["total_score"] == 18
    assert data["assessment_summary"]["maximum_score"] == 24
    assert data["assessment_summary"]["percentage"] == 75.0
    assert data["assessment_summary"]["completion_date"] == "2026-01-02T00:00:00+00:00"
    assert len(data["assessment_evidence"]["demonstrated_concepts"]) == 1
    assert len(data["assessment_evidence"]["relevant_feedback"]) == 1
    assert data["assessment_evidence"]["safety"]["safety_critical_misconception"] is True
    assert len(data["assessment_evidence"]["safety"]["concerns"]) == 1
    assessed_skills = [
        skill
        for skill in data["recognized_skills"]
        if skill["evidence_level"] == "ASSESSED"
    ]
    assert assessed_skills
    assert any(
        skill["skill_name"] == "Electrical safety"
        for skill in assessed_skills
    )


def test_passport_multiple_assessments_selects_latest_completed(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            """
            INSERT INTO assessments (
                worker_id, trade, language, status, current_stage,
                total_score, max_score, score_percentage, safety_flags_json,
                started_at, completed_at
            ) VALUES (?, 'Electrician', 'en', 'COMPLETED', 3,
                      12, 24, 50.0, '[]',
                      '2026-01-01T00:00:00+00:00',
                      '2026-01-02T00:00:00+00:00')
            """,
            (worker_id,),
        )
        conn.execute(
            """
            INSERT INTO assessments (
                worker_id, trade, language, status, current_stage,
                max_score, safety_flags_json, started_at
            ) VALUES (?, 'Electrician', 'en', 'IN_PROGRESS', 1,
                      24, '[]', '2026-02-01T00:00:00+00:00')
            """,
            (worker_id,),
        )
        conn.execute(
            """
            INSERT INTO assessments (
                worker_id, trade, language, status, current_stage,
                total_score, max_score, score_percentage, safety_flags_json,
                started_at, completed_at
            ) VALUES (?, 'Electrician', 'en', 'COMPLETED', 3,
                      21, 24, 87.5, '[]',
                      '2026-01-03T00:00:00+00:00',
                      '2026-01-04T00:00:00+00:00')
            """,
            (worker_id,),
        )
        conn.commit()

    response = client.get(f"/api/workers/{worker_id}/passport")

    assert response.status_code == 200
    data = response.json()
    assert data["assessment_summary"]["total_score"] == 21
    assert data["assessment_summary"]["percentage"] == 87.5
    assert data["assessment_summary"]["completion_date"] == "2026-01-04T00:00:00+00:00"


def test_passport_preserves_evidence_levels_and_never_invented_verification(
    client,
    tmp_path,
):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    with sqlite3.connect(tmp_path / "test.db") as conn:
        cursor = conn.execute(
            """
            INSERT INTO assessments (
                worker_id, trade, language, status, current_stage,
                total_score, max_score, score_percentage, safety_flags_json,
                started_at, completed_at
            ) VALUES (?, 'Electrician', 'en', 'COMPLETED', 3,
                      24, 24, 100.0, '[]',
                      '2026-01-01T00:00:00+00:00',
                      '2026-01-02T00:00:00+00:00')
            """,
            (worker_id,),
        )
        assessment_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO assessment_questions (
                assessment_id, question_id, stage_number, question_order,
                selection_reason, selected_at
            ) VALUES (?, 'E03', 1, 1, 'High-score assessment',
                      '2026-01-01T00:00:00+00:00')
            """,
            (assessment_id,),
        )
        conn.execute(
            """
            INSERT INTO assessment_answers (
                assessment_id, question_id, stage_number, answer_text,
                answer_source, score, rubric_feedback_json, safety_flag,
                safety_reason, safety_concerns_json, answered_at
            ) VALUES (?, 'E03', 1, 'I isolate supply and verify no voltage',
                      'TEXT', 4,
                      '{"feedback":"Accurate safety procedure","concept_evaluations":[{"concept":"supply must be isolated","demonstrated":true,"evidence":"isolate supply","rationale":"The answer demonstrates isolation"}]}',
                      0, NULL, '[]',
                      '2026-01-02T00:00:00+00:00')
            """,
            (assessment_id,),
        )
        conn.commit()

    response = client.get(f"/api/workers/{worker_id}/passport")

    assert response.status_code == 200
    data = response.json()
    assert all(
        skill["evidence_level"] != "INDEPENDENTLY_VERIFIED"
        for skill in data["recognized_skills"]
    )
    assessed = [
        skill
        for skill in data["recognized_skills"]
        if skill["evidence_level"] == "ASSESSED"
    ]
    assert assessed
    assert any(
        skill["skill_name"] == "Electrical safety"
        for skill in assessed
    )
    assert any(
        skill["evidence_level"] == "SELF_REPORTED"
        for skill in data["recognized_skills"]
    )
    classifications = data["evidence_classification"]
    assert "SELF_REPORTED" in classifications
    assert "ASSESSED" in classifications
    assert "INDEPENDENTLY_VERIFIED" in classifications


def test_passport_does_not_expose_raw_worker_transcript(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")

    response = client.get(f"/api/workers/{worker_id}/passport")

    assert response.status_code == 200
    payload = response.json()
    assert "raw_transcript" not in str(payload)


def test_worker_jobs_electrician_success(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            """
            UPDATE worker_skills
            SET skill_name = 'Electrical safety'
            WHERE worker_id = ?
            """,
            (worker_id,),
        )

    response = client.get(f"/api/workers/{worker_id}/jobs")

    assert response.status_code == 200
    data = response.json()
    assert data["worker_id"] == worker_id
    assert data["trade"] == "Electrician"
    assert data["demo"] is True
    assert data["jobs"]
    assert all(job["job_id"].startswith("DEMO-E-") for job in data["jobs"])


def test_worker_jobs_plumber_success(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db", trade="Plumber")
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            """
            UPDATE worker_skills
            SET skill_name = 'Pipe joint repair'
            WHERE worker_id = ?
            """,
            (worker_id,),
        )

    response = client.get(f"/api/workers/{worker_id}/jobs")

    assert response.status_code == 200
    data = response.json()
    assert data["trade"] == "Plumber"
    assert data["jobs"]
    assert all(job["job_id"].startswith("DEMO-P-") for job in data["jobs"])


def test_worker_jobs_location_filter(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")

    response = client.get(
        f"/api/workers/{worker_id}/jobs",
        params={"location": "Hyderabad"},
    )

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert jobs
    assert all("hyderabad" in job["location"].lower() for job in jobs)


def test_worker_jobs_unknown_worker(client):
    response = client.get("/api/workers/9999/jobs")
    assert response.status_code == 404
    assert response.json()["detail"] == "Worker not found"


def test_worker_jobs_trade_with_no_matching_listings_is_empty(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")

    response = client.get(
        f"/api/workers/{worker_id}/jobs",
        params={"location": "No Such Demo Location"},
    )

    assert response.status_code == 200
    assert response.json()["jobs"] == []


def test_worker_jobs_preserve_evidence_and_preferred_skills(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            """
            UPDATE worker_skills
            SET skill_name = 'Electrical safety',
                evidence_level = 'ASSESSED'
            WHERE worker_id = ?
            """,
            (worker_id,),
        )

    response = client.get(f"/api/workers/{worker_id}/jobs")

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert jobs
    matched = [
        skill
        for job in jobs
        for skill in job["matched_skills"]
    ]
    assert matched
    assert all(
        skill["evidence_level"] in (
            "SELF_REPORTED",
            "ASSESSED",
            "INDEPENDENTLY_VERIFIED",
        )
        for skill in matched
    )
    assert all(
        skill["evidence_level"] != "INDEPENDENTLY_VERIFIED"
        for skill in matched
    )


def insert_completed_assessment_for_job_evidence(
    tmp_path,
    worker_id,
    *,
    total_score,
    demonstrated,
):
    with sqlite3.connect(tmp_path / "test.db") as conn:
        cursor = conn.execute(
            """
            INSERT INTO assessments (
                worker_id, trade, language, status, current_stage,
                total_score, max_score, score_percentage, safety_flags_json,
                started_at, completed_at
            ) VALUES (?, 'Electrician', 'en', 'COMPLETED', 3,
                      ?, 24, ?, '[]',
                      '2026-01-01T00:00:00+00:00',
                      '2026-01-02T00:00:00+00:00')
            """,
            (
                worker_id,
                total_score,
                round(total_score * 100 / 24, 2),
            ),
        )
        assessment_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO assessment_questions (
                assessment_id, question_id, stage_number, question_order,
                selection_reason, selected_at
            ) VALUES (?, 'E03', 1, 1, 'Evidence test',
                      '2026-01-01T00:00:00+00:00')
            """,
            (assessment_id,),
        )
        feedback = (
            '{"feedback":"Test feedback","concept_evaluations":'
            '[{"concept":"supply must be isolated","demonstrated":'
            + ("true" if demonstrated else "false")
            + ',"evidence":null,"rationale":"The answer does not demonstrate isolation"}]}'
        )
        conn.execute(
            """
            INSERT INTO assessment_answers (
                assessment_id, question_id, stage_number, answer_text,
                answer_source, score, rubric_feedback_json, safety_flag,
                safety_reason, safety_concerns_json, answered_at
            ) VALUES (?, 'E03', 1, 'Test answer', 'TEXT', ?, ?, 0,
                      NULL, '[]', '2026-01-02T00:00:00+00:00')
            """,
            (assessment_id, 4 if demonstrated else 1, feedback),
        )
        conn.commit()
    return assessment_id


def test_job_matching_non_demonstrated_concept_not_assessed(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    insert_completed_assessment_for_job_evidence(
        tmp_path,
        worker_id,
        total_score=6,
        demonstrated=False,
    )
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            """
            UPDATE worker_skills
            SET skill_name = 'Electrical safety',
                evidence_level = 'SELF_REPORTED'
            WHERE worker_id = ?
            """,
            (worker_id,),
        )
        conn.commit()

    response = client.get(
        f"/api/workers/{worker_id}/jobs",
        params={"location": "Hyderabad"},
    )

    assert response.status_code == 200
    electrical_safety_matches = [
        skill
        for job in response.json()["jobs"]
        for skill in job["matched_skills"]
        if skill["skill_name"].lower() == "electrical safety"
    ]
    assert electrical_safety_matches
    assert all(
        skill["evidence_level"] == "SELF_REPORTED"
        for skill in electrical_safety_matches
    )
    assert all(
        skill["evidence_level"] != "INDEPENDENTLY_VERIFIED"
        for skill in electrical_safety_matches
    )


def test_demo_verification_success_is_persisted_and_passport_shows_independent(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            "UPDATE worker_skills SET skill_name = 'Electrical safety', "
            "evidence_level = 'ASSESSED' WHERE worker_id = ?",
            (worker_id,),
        )
        conn.commit()

    response = client.post(
        "/api/verifications",
        json={
            "worker_id": worker_id,
            "skill_name": "  electrical   safety ",
            "assessor_identifier": "DEMO-ASSESSOR-001",
            "outcome": "VERIFIED",
            "evidence": "Observed isolation and voltage testing.",
            "notes": "Demo assessor record",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["outcome"] == "VERIFIED"
    assert data["demo_assessor_access"] is True
    assert data["assessor_identity_authenticated"] is False

    passport = client.get(f"/api/workers/{worker_id}/passport").json()
    electrical = [
        skill
        for skill in passport["recognized_skills"]
        if skill["skill_name"].lower() == "electrical safety"
    ]
    assert electrical
    assert electrical[0]["evidence_level"] == "INDEPENDENTLY_VERIFIED"
    assert electrical[0]["source"] == "demo_human_verification"


def test_verification_rejects_unknown_worker(client):
    response = client.post(
        "/api/verifications",
        json={
            "worker_id": 9999,
            "skill_name": "Electrical safety",
            "assessor_identifier": "DEMO-ASSESSOR-001",
            "outcome": "VERIFIED",
            "evidence": "Observed the task.",
        },
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {
            "worker_id": 1,
            "skill_name": "Electrical safety",
            "assessor_identifier": "",
            "outcome": "VERIFIED",
            "evidence": "Observed the task.",
        },
        {
            "worker_id": 1,
            "skill_name": "Electrical safety",
            "assessor_identifier": "DEMO-ASSESSOR-001",
            "outcome": "VERIFIED",
            "evidence": "   ",
        },
        {
            "worker_id": 1,
            "skill_name": "Electrical safety",
            "assessor_identifier": "DEMO-ASSESSOR-001",
            "outcome": "UNKNOWN",
            "evidence": "Observed the task.",
        },
    ],
)
def test_verification_invalid_input_returns_422(client, payload):
    response = client.post("/api/verifications", json=payload)
    assert response.status_code == 422


def test_verification_rejects_unrelated_skill(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")

    response = client.post(
        "/api/verifications",
        json={
            "worker_id": worker_id,
            "skill_name": "Spacecraft repair",
            "assessor_identifier": "DEMO-ASSESSOR-001",
            "outcome": "VERIFIED",
            "evidence": "Observed a spacecraft task.",
        },
    )
    assert response.status_code == 422


def test_latest_not_verified_removes_older_independent_status(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            "UPDATE worker_skills SET skill_name = 'Electrical safety', "
            "evidence_level = 'ASSESSED' WHERE worker_id = ?",
            (worker_id,),
        )
        conn.execute(
            """
            INSERT INTO verification_records (
                worker_id, skill_name, assessor_identifier, outcome,
                evidence, notes, verified_at
            ) VALUES (?, 'Electrical safety', 'DEMO-ASSESSOR-001',
                      'VERIFIED', 'Earlier evidence', NULL,
                      '2026-01-01T00:00:00+00:00')
            """,
            (worker_id,),
        )
        conn.execute(
            """
            INSERT INTO verification_records (
                worker_id, skill_name, assessor_identifier, outcome,
                evidence, notes, verified_at
            ) VALUES (?, '  electrical   safety ', 'DEMO-ASSESSOR-002',
                      'NOT_VERIFIED', 'Latest observation', 'No practical pass',
                      '2026-01-02T00:00:00+00:00')
            """,
            (worker_id,),
        )
        conn.commit()

    passport = client.get(f"/api/workers/{worker_id}/passport")
    assert passport.status_code == 200
    electrical = [
        skill
        for skill in passport.json()["recognized_skills"]
        if skill["skill_name"].lower() == "electrical safety"
    ]
    assert electrical
    assert electrical[0]["evidence_level"] == "ASSESSED"

    jobs = client.get(f"/api/workers/{worker_id}/jobs").json()["jobs"]
    electrical_jobs = [
        skill
        for job in jobs
        for skill in job["matched_skills"]
        if skill["skill_name"].lower() == "electrical safety"
    ]
    assert electrical_jobs
    assert all(
        skill["evidence_level"] != "INDEPENDENTLY_VERIFIED"
        for skill in electrical_jobs
    )

    with sqlite3.connect(tmp_path / "test.db") as conn:
        historical_outcomes = conn.execute(
            """
            SELECT outcome
            FROM verification_records
            WHERE worker_id = ?
            ORDER BY id
            """,
            (worker_id,),
        ).fetchall()
    assert historical_outcomes == [
        ("VERIFIED",),
        ("NOT_VERIFIED",),
    ]


def test_verification_skill_normalization_for_case_and_repeated_whitespace(
    client,
    tmp_path,
):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            "UPDATE worker_skills SET skill_name = 'Electrical   safety', "
            "evidence_level = 'ASSESSED' WHERE worker_id = ?",
            (worker_id,),
        )
        conn.commit()

    verified = client.post(
        "/api/verifications",
        json={
            "worker_id": worker_id,
            "skill_name": "  ELECTRICAL safety ",
            "assessor_identifier": "DEMO-NORMALIZATION",
            "outcome": "VERIFIED",
            "evidence": "Observed normalized skill evidence.",
        },
    )

    assert verified.status_code == 200
    passport = client.get(f"/api/workers/{worker_id}/passport")
    assert passport.status_code == 200
    electrical = [
        skill
        for skill in passport.json()["recognized_skills"]
        if " ".join(skill["skill_name"].lower().split()) == "electrical safety"
    ]
    assert electrical
    assert electrical[0]["evidence_level"] == "INDEPENDENTLY_VERIFIED"


def test_verification_audit_history_preserves_records(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            "UPDATE worker_skills SET skill_name = 'Electrical safety', "
            "evidence_level = 'SELF_REPORTED' WHERE worker_id = ?",
            (worker_id,),
        )
        conn.commit()

    first = client.post(
        "/api/verifications",
        json={
            "worker_id": worker_id,
            "skill_name": "Electrical safety",
            "assessor_identifier": "DEMO-ASSESSOR-001",
            "outcome": "VERIFIED",
            "evidence": "Observed the task.",
        },
    )
    second = client.post(
        "/api/verifications",
        json={
            "worker_id": worker_id,
            "skill_name": "Electrical safety",
            "assessor_identifier": "DEMO-ASSESSOR-002",
            "outcome": "NOT_VERIFIED",
            "evidence": "Observed an incomplete task.",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    with sqlite3.connect(tmp_path / "test.db") as conn:
        records = conn.execute(
            "SELECT outcome FROM verification_records "
            "WHERE worker_id = ? ORDER BY id",
            (worker_id,),
        ).fetchall()
    assert records == [("VERIFIED",), ("NOT_VERIFIED",)]


def test_job_matching_demonstrated_concept_is_assessed(client, tmp_path):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    insert_completed_assessment_for_job_evidence(
        tmp_path,
        worker_id,
        total_score=18,
        demonstrated=True,
    )
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            "UPDATE worker_skills SET evidence_level = 'SELF_REPORTED' "
            "WHERE worker_id = ?",
            (worker_id,),
        )
        conn.commit()

    response = client.get(
        f"/api/workers/{worker_id}/jobs",
        params={"location": "Hyderabad"},
    )

    assert response.status_code == 200
    electrical_safety_matches = [
        skill
        for job in response.json()["jobs"]
        for skill in job["matched_skills"]
        if skill["skill_name"].lower() == "electrical safety"
    ]
    assert electrical_safety_matches
    assert all(
        skill["evidence_level"] == "ASSESSED"
        for skill in electrical_safety_matches
    )


def test_high_assessment_score_does_not_assume_all_skills_demonstrated(
    client,
    tmp_path,
):
    worker_id = insert_assessment_test_worker(tmp_path / "test.db")
    insert_completed_assessment_for_job_evidence(
        tmp_path,
        worker_id,
        total_score=24,
        demonstrated=False,
    )
    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.execute(
            """
            UPDATE worker_skills
            SET skill_name = 'Electrical safety',
                evidence_level = 'SELF_REPORTED'
            WHERE worker_id = ?
            """,
            (worker_id,),
        )
        conn.commit()

    response = client.get(f"/api/workers/{worker_id}/jobs")

    assert response.status_code == 200
    electrical_safety_matches = [
        skill
        for job in response.json()["jobs"]
        for skill in job["matched_skills"]
        if skill["skill_name"].lower() == "electrical safety"
    ]
    assert electrical_safety_matches
    assert all(
        skill["evidence_level"] == "SELF_REPORTED"
        for skill in electrical_safety_matches
    )
    assert all(
        skill["evidence_level"] != "INDEPENDENTLY_VERIFIED"
        for skill in electrical_safety_matches
    )
