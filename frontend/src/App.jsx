import { useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const SAMPLE_TELUGU_TEXT =
  "Nenu five years nunchi electrician ga work chestunnanu. Fan installation, wiring repair chestanu.";

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
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        await sendAudioToBackend(blob, "recording.webm");
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    } catch {
      setStatusMsg(
        "Microphone unavailable—use sample text below or type your experience directly."
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

      const res = await fetch(`${API_BASE}/api/voice/transcribe`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("Transcription failed");
      const data = await res.json();
      setTranscript(data.transcript || "");
      setStatusMsg("Transcript ready—review or edit before generating profile.");
    } catch {
      setStatusMsg(
        "Voice transcription fallback: edit or paste your experience text below and continue."
      );
      if (!transcript) setTranscript(SAMPLE_TELUGU_TEXT);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (file) {
      await sendAudioToBackend(file, file.name);
    }
  };

  const handleGenerateProfile = async (e) => {
    e.preventDefault();
    const finalText = transcript.trim() || SAMPLE_TELUGU_TEXT;
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
          transcript: finalText,
        }),
      });
      if (!res.ok) throw new Error("Profile extraction failed");
      const data = await res.json();
      setSavedResult(data);
      setStep("result");
      setStatusMsg("");
    } catch (err) {
      setStatusMsg(`Error: ${err.message}. Check that FastAPI is running on port 8000.`);
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
            <button
              type="button"
              onClick={() => {
                setTranscript(SAMPLE_TELUGU_TEXT);
                setStatusMsg("Loaded sample Telugu statement.");
              }}
            >
              Load Sample Telugu Text
            </button>
          </div>

          <div>
            <label>Transcript / Experience Text (Editable fallback):</label>
            <textarea
              rows={4}
              style={{ width: "100%", marginTop: 6 }}
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              placeholder="Speak above or type your work experience here..."
            />
          </div>

          {statusMsg && <p style={{ color: "#b45309" }}>{statusMsg}</p>}

          <button type="submit" disabled={loading} style={{ padding: "0.75rem 1.25rem" }}>
            {loading ? "Processing..." : "Generate Structured Profile"}
          </button>
        </form>
      )}

      {step === "result" && savedResult && (
        <section style={{ border: "1px solid #d1d5db", borderRadius: 8, padding: "1.25rem" }}>
          <h2>Structured Worker Profile (Saved #{savedResult.worker_id})</h2>
          <p><strong>Trade:</strong> {savedResult.profile.trade}</p>
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
          <button onClick={() => setStep("onboard")}>Create Another Profile</button>
        </section>
      )}
    </div>
  );
}