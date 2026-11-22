import json
import os
import sqlite3
from typing import List, Literal
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()

DB_PATH = "yogya.db"
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

app = FastAPI(title="Yogya Day 1 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExtractedProfile(BaseModel):
    trade: Literal["Electrician", "Plumber", "Other"] = Field(
        description="Primary trade identified from the description."
    )
    experience_years: int = Field(
        ge=0, description="Years of work experience mentioned; 0 if unclear."
    )
    skills: List[str] = Field(
        description="Concise list of extracted skills in English, e.g. Fan installation, Wiring repair."
    )
    evidence_level: Literal["SELF_REPORTED"] = "SELF_REPORTED"


class DiscoverRequest(BaseModel):
    name: str = "Worker"
    language: str = "te"
    location: str = ""
    transcript: str


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            language TEXT NOT NULL,
            location TEXT DEFAULT '',
            raw_transcript TEXT NOT NULL,
            trade TEXT NOT NULL,
            experience_years INTEGER NOT NULL,
            evidence_level TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS worker_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            skill_name TEXT NOT NULL,
            evidence_level TEXT NOT NULL,
            FOREIGN KEY (worker_id) REFERENCES workers (id)
        )
        """
    )
    conn.commit()
    conn.close()


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.post("/api/voice/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)) -> dict:
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    mime_type = audio.content_type or "audio/webm"
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            "Transcribe this Telugu or English/code-mixed spoken worker experience clearly. Return only the plain transcript text.",
        ],
    )
    return {"transcript": (response.text or "").strip()}


@app.post("/api/profile/discover")
def discover_profile(payload: DiscoverRequest) -> dict:
    if not payload.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript or text input is required")

    prompt = (
        "Extract the worker's primary trade, years of experience, and practical skills "
        "from this Telugu/English/code-mixed statement. Normalize skill names cleanly in English "
        "(such as 'Fan installation', 'Wiring repair', 'Pipe fitting', 'Leak repair'). "
        "Always set evidence_level to 'SELF_REPORTED'.\n\n"
        f"Input ({payload.language}): {payload.transcript}"
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractedProfile,
        ),
    )

    data = json.loads(response.text)
    profile = ExtractedProfile(**data)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO workers (name, language, location, raw_transcript, trade, experience_years, evidence_level)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.name,
            payload.language,
            payload.location,
            payload.transcript,
            profile.trade,
            profile.experience_years,
            profile.evidence_level,
        ),
    )
    worker_id = cur.lastrowid

    for skill in profile.skills:
        cur.execute(
            "INSERT INTO worker_skills (worker_id, skill_name, evidence_level) VALUES (?, ?, ?)",
            (worker_id, skill, profile.evidence_level),
        )

    conn.commit()
    conn.close()

    return {
        "worker_id": worker_id,
        "profile": profile.model_dump(),
    }


@app.get("/api/workers/{worker_id}")
def get_worker(worker_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM workers WHERE id = ?", (worker_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Worker not found")

    cur.execute(
        "SELECT skill_name, evidence_level FROM worker_skills WHERE worker_id = ?",
        (worker_id,),
    )
    skills = [{"skill_name": r[0], "evidence_level": r[1]} for r in cur.fetchall()]
    conn.close()

    return {
        "id": row[0],
        "name": row[1],
        "language": row[2],
        "location": row[3],
        "raw_transcript": row[4],
        "trade": row[5],
        "experience_years": row[6],
        "evidence_level": row[7],
        "skills": skills,
    }