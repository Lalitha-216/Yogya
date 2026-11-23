import { useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const EXT_BY_MIME = {
  "audio/webm": "webm",
  "audio/ogg": "ogg",
  "audio/mp4": "m4a",
  "audio/mpeg": "mp3",
  "audio/wav": "wav",
};

// FastAPI returns `detail` as a string (our own errors) or a list (validation errors).
async function readError(res, fallback) {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // response was not JSON
  }
  return `${fallback} (HTTP ${res.status})`;
}

export default function App() {
  const [step, setStep] = useState("landing"); // landing | onboard | result
  const [language, setLanguage] = useState("te");
  const [name, setName] = useState("Ramesh Kumar");
  const [location, setLocation] = useState("Kakinada");
  const [selectedTrade, setSelectedTrade] = useState("Electrician");

  const [transcript, setTranscript] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [savedResult, setSavedResult] = useState(null);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  const startRecording = async () => {
    setStatusMsg("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const mime = (recorder.mimeType || "audio/webm").split(";")[0];
        const blob = new Blob(chunksRef.current, { type: mime });
        await sendAudioToBackend(blob, `recording.${EXT_BY_MIME[mime] || "webm"}`);
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    } catch {
      setStatusMsg(
        "Microphone unavailable. Allow microphone access, upload an audio file, or type your experience below."
      );
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const sendAudioToBackend = async (fileOrBlob, filename = "audio.webm") => {
    setLoading(true);
    setStatusMsg("Transcribing audio...");
    try {
      const formData = new FormData();
      formData.append("audio", fileOrBlob, filename);
      formData.append("language", language);

      const res = await fetch(`${API_BASE}/api/voice/transcribe`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(await readError(res, "Transcription failed"));
      const data = await res.json();
      setTranscript(data.transcript);
      setStatusMsg("Transcript ready—review or edit before generating profile.");
    } catch (err) {
      // Keep whatever the user already typed; never substitute sample text.
      setStatusMsg(
        `Transcription failed: ${err.message}. You can type your experience below instead.`
      );
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (file) {
      await sendAudioToBackend(file, file.name);
    }
    e.target.value = ""; // allow re-selecting the same file
  };

  const handleGenerateProfile = async (e) => {
    e.preventDefault();
    const finalText = transcript.trim();
    if (!finalText) {
      setStatusMsg("Please record your voice, upload audio, or type your work experience first.");
      return;
    }
    setLoading(true);
    setStatusMsg("Extracting structured skill profile...");
    try {
      const res = await fetch(`${API_BASE}/api/profile/discover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          language,
          location,
          selected_trade: selectedTrade,
          transcript: finalText,
        }),
      });
      if (!res.ok) throw new Error(await readError(res, "Profile extraction failed"));
      const data = await res.json();
      setSavedResult(data);
      setStep("result");
      setStatusMsg("");
    } catch (err) {
      const offline = err instanceof TypeError; // fetch itself failed
      setStatusMsg(
        offline
          ? `Cannot reach the backend at ${API_BASE}. Check that FastAPI is running on port 8000.`
          : `Error: ${err.message}`
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 680, margin: "2rem auto", fontFamily: "system-ui, sans-serif", padding: "0 1rem" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <div>
          <h1 style={{ margin: 0 }}>YOGYA</h1>
          <small>Skills Deserve Recognition</small>
        </div>
        <div>
          <button onClick={() => setLanguage("te")} style={{ fontWeight: language === "te" ? "700" : "400", marginRight: 8 }}>
            తెలుగు (TE)
          </button>
          <button onClick={() => setLanguage("en")} style={{ fontWeight: language === "en" ? "700" : "400" }}>
            English (EN)
          </button>
        </div>
      </header>

      {step === "landing" && (
        <section>
          <h2>No formal certificate or English resume? Your skills still count.</h2>
          <p>Speak or type about your work in Telugu or English to create a structured skill profile.</p>
          <button onClick={() => setStep("onboard")} style={{ padding: "0.75rem 1.25rem", fontSize: "1rem" }}>
            Start Worker Onboarding
          </button>
        </section>
      )}

      {step === "onboard" && (
        <form onSubmit={handleGenerateProfile} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div>
            <label>Name: </label>
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </div>

          <div>
            <label>Location: </label>
            <input value={location} onChange={(e) => setLocation(e.target.value)} />
          </div>

          <div>
            <span>Trade: </span>
            {["Electrician", "Plumber"].map((t) => (
              <button
                type="button"
                key={t}
                onClick={() => setSelectedTrade(t)}
                style={{
                  marginRight: 8,
                  fontWeight: selectedTrade === t ? "700" : "400",
                }}
              >
                {t}
              </button>
            ))}
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {!isRecording ? (
              <button type="button" onClick={startRecording}>
                Record Voice
              </button>
            ) : (
              <button type="button" onClick={stopRecording}>
                Stop Recording
              </button>
            )}
            <label>
              Upload Audio: <input type="file" accept="audio/*" onChange={handleFileUpload} />
            </label>
          </div>

          <div>
            <label>Transcript / Experience Text (editable):</label>
            <textarea
              rows={4}
              required
              style={{ width: "100%", marginTop: 6 }}
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              placeholder="Speak above or type your work experience here..."
            />
          </div>

          {statusMsg && <p style={{ color: "#b45309" }}>{statusMsg}</p>}

          <button type="submit" disabled={loading || isRecording} style={{ padding: "0.75rem 1.25rem" }}>
            {loading ? "Processing..." : "Generate Structured Profile"}
          </button>
        </form>
      )}

      {step === "result" && savedResult && (
        <section style={{ border: "1px solid #d1d5db", borderRadius: 8, padding: "1.25rem" }}>
          <h2>Structured Worker Profile (Saved #{savedResult.worker_id})</h2>
          <p><strong>Trade:</strong> {savedResult.profile.trade}</p>
          {savedResult.trade_mismatch && (
            <p style={{ color: "#b45309" }}>
              Note: your description sounds more like "{savedResult.detected_trade}" work. Your
              selected trade was saved.
            </p>
          )}
          <p><strong>Experience:</strong> {savedResult.profile.experience_years} years</p>
          <p><strong>Evidence Level:</strong> {savedResult.profile.evidence_level}</p>
          <p><strong>Skills:</strong></p>
          <ul>
            {savedResult.profile.skills.map((s) => (
              <li key={s}>
                {s} — <em>{savedResult.profile.evidence_level}</em>
              </li>
            ))}
          </ul>
          <button
            onClick={() => {
              setTranscript("");
              setStatusMsg("");
              setSavedResult(null);
              setStep("onboard");
            }}
          >
            Create Another Profile
          </button>
        </section>
      )}
    </div>
  );
}