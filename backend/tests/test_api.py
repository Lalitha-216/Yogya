"""Backend tests. Gemini is replaced by a fake client here (tests only);
the application code itself contains no fake/sample behaviour."""
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main


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
