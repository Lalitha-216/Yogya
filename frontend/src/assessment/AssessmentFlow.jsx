import { useEffect, useRef, useState } from "react";
import "./assessment.css";
import { ASSESSMENT_COPY, LANGUAGES } from "./copy";
import { QUESTIONS } from "./questions";

const fill = (template, values) =>
  Object.entries(values).reduce(
    (message, [key, value]) => message.replace(`{${key}}`, value),
    template
  );

const pickLanguage = (code) => (ASSESSMENT_COPY[code] ? code : "en");

const MAX_TEXT = 500; // characters per typed answer

/**
 * Assessment: intro -> questions -> final review -> local Skill Passport preview.
 * Answers live in local state only; nothing is sent to the backend and no score
 * is computed. `workerId` and `trade` come from the saved profile result.
 */
export default function AssessmentFlow({
  workerId,
  workerName,
  workerLocation,
  trade,
  initialLanguage,
  onExit,
}) {
  const [lang, setLang] = useState(pickLanguage(initialLanguage));
  const [phase, setPhase] = useState("intro"); // "intro" | "questions" | "review" | "done"
  const [index, setIndex] = useState(0);
  // { [questionId]: { mode: "choice" | "text", optionId?: string, text?: string } }
  // Both values are kept when the worker switches mode, so switching back restores
  // them; the entry's active `mode` decides which one counts as the answer.
  const [answers, setAnswers] = useState({});
  // Mode a not-yet-answered question opens in: follows the worker's last choice.
  const [preferredMode, setPreferredMode] = useState("choice");
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [voiceError, setVoiceError] = useState("");
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const objectUrlsRef = useRef(new Set());

  // Follow the app's te/en switch; the assessment's own switch also offers Hindi.
  useEffect(() => {
    setLang(pickLanguage(initialLanguage));
  }, [initialLanguage]);

  const t = ASSESSMENT_COPY[lang];
  const questions = QUESTIONS[trade] || [];
  const total = questions.length;
  const isAnswered = (q) => {
    const a = answers[q.id];
    if (!a) return false;
    if (a.mode === "text") return Boolean(a.text && a.text.trim());
    if (a.mode === "voice") return Boolean(a.voiceUrl);
    return Boolean(a.optionId);
  };

  useEffect(() => {
    if (!isRecording) return undefined;
    const timer = window.setInterval(() => {
      setRecordingSeconds((seconds) => seconds + 1);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isRecording]);

  useEffect(() => () => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  const startVoiceRecording = async (questionId) => {
    setVoiceError("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setVoiceError(t.voiceUnsupported);
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      const chunks = [];
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) chunks.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        if (blob.size > 0) {
          const url = URL.createObjectURL(blob);
          objectUrlsRef.current.add(url);
          updateAnswer(questionId, { mode: "voice", voiceBlob: blob, voiceUrl: url });
        } else {
          setVoiceError(t.voiceEmpty);
        }
        stream.getTracks().forEach((track) => track.stop());
        if (streamRef.current === stream) streamRef.current = null;
        setIsRecording(false);
        setRecordingSeconds(0);
      };

      recorder.start();
      setRecordingSeconds(0);
      setIsRecording(true);
    } catch (error) {
      setVoiceError(
        error?.name === "NotAllowedError" || error?.name === "PermissionDeniedError"
          ? t.voicePermission
          : t.voiceFailed
      );
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  };

  const stopVoiceRecording = () => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  };
  const answeredCount = questions.filter(isAnswered).length;
  const answerModeCounts = questions.reduce((counts, question) => {
    if (!isAnswered(question)) return counts;
    const mode = answers[question.id]?.mode;
    const key = mode === "voice" ? "voice" : mode === "text" ? "text" : "mcq";
    counts[key] += 1;
    return counts;
  }, { mcq: 0, text: 0, voice: 0 });
  const updateAnswer = (questionId, patch) =>
    setAnswers((prev) => ({ ...prev, [questionId]: { ...prev[questionId], ...patch } }));
  const tradeLabel = t.trades[trade] || trade;

  const start = () => {
    setAnswers({});
    setIndex(0);
    setPhase("questions");
  };

  const languageSwitch = (
    <div className="as-lang-row">
      <div className="language-switch" role="group" aria-label={t.chooseLanguage}>
        {LANGUAGES.map(({ code, label }) => (
          <button
            key={code}
            type="button"
            className={lang === code ? "active" : ""}
            aria-pressed={lang === code}
            onClick={() => setLang(code)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );

  let body;

  if (total === 0) {
    body = (
      <section className="result-section">
        <p className="result-intro">{t.unavailable}</p>
        <div className="as-actions">
          <button type="button" className="primary-button" onClick={onExit}>
            {t.backToProfile}
          </button>
        </div>
      </section>
    );
  } else if (phase === "intro") {
    body = (
      <section className="result-section">
        <span className="section-kicker">{t.kicker}</span>
        <h1>{t.introTitle}</h1>
        <p className="result-intro">{fill(t.introText, { total })}</p>

        <div className="result-card">
          <div className="result-details" style={{ margin: 0, border: 0, padding: 0 }}>
            <div>
              <small>{t.tradeLabel}</small>
              <strong>{tradeLabel}</strong>
            </div>
            <div>
              <small>{t.questionsLabel}</small>
              <strong>{total}</strong>
            </div>
            <div>
              <small>{t.workerId}</small>
              <strong>#{workerId}</strong>
            </div>
          </div>
        </div>

        <div className="as-actions">
          <button type="button" className="as-button-secondary" onClick={onExit}>
            {t.backToProfile}
          </button>
          <button type="button" className="primary-button" onClick={start}>
            {t.start} <span>→</span>
          </button>
        </div>
      </section>
    );
  } else if (phase === "questions") {
    const question = questions[index];
    const entry = answers[question.id] || {};
    const mode = entry.mode || preferredMode;
    const selected = entry.optionId;
    const text = entry.text || "";
    const answered = isAnswered(question);
    const isLast = index === total - 1;

    body = (
      <section className="onboarding-section">
        <div className="as-progress">
          <div className="as-progress-meta">
            <span>{fill(t.questionOf, { n: index + 1, total })}</span>
            <span>{fill(t.answeredCount, { n: answeredCount, total })}</span>
          </div>
          <div
            className="as-progress-track"
            role="progressbar"
            aria-label={t.progressLabel}
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={answeredCount}
          >
            <div
              className="as-progress-fill"
              style={{ width: `${(answeredCount / total) * 100}%` }}
            />
          </div>
        </div>

        <div className="onboarding-card">
          <span className="section-kicker">{tradeLabel.toUpperCase()}</span>
          <h2 id="as-question-text" className="as-question">
            {question.text[lang]}
          </h2>

          <div className="as-mode">
            <span id="as-mode-label" className="as-mode-label">
              {t.answerMode}
            </span>
            <div className="language-switch" role="group" aria-labelledby="as-mode-label">
              {[
                ["choice", t.modeChoose],
                ["text", t.modeType],
                ["voice", t.modeVoice],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={mode === value ? "active" : ""}
                  aria-pressed={mode === value}
                  disabled={isRecording}
                  onClick={() => {
                    setPreferredMode(value);
                    updateAnswer(question.id, { mode: value });
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {mode === "choice" ? (
            <div className="as-options" role="radiogroup" aria-labelledby="as-question-text">
              {question.options.map((option, i) => {
                const isSelected = selected === option.id;
                return (
                  <button
                    key={option.id}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    className={`trade-option as-option ${isSelected ? "selected" : ""}`}
                    onClick={() =>
                      updateAnswer(question.id, { mode: "choice", optionId: option.id })
                    }
                  >
                    <span className="trade-symbol">{String.fromCharCode(65 + i)}</span>
                    <span className="trade-info">
                      <strong>{option.text[lang]}</strong>
                    </span>
                    <span className="trade-radio">{isSelected ? "✓" : ""}</span>
                  </button>
                );
              })}
            </div>
          ) : mode === "text" ? (
            <div className="as-text">
              <label className="field">
                <span>{t.textLabel}</span>
                <textarea
                  rows={6}
                  maxLength={MAX_TEXT}
                  value={text}
                  placeholder={t.textPlaceholder}
                  onChange={(event) =>
                    updateAnswer(question.id, { mode: "text", text: event.target.value })
                  }
                />
              </label>
              <p className="privacy-note as-count">
                {text.length} / {MAX_TEXT}
              </p>
            </div>
          ) : (
            <div className="as-voice">
              {entry.voiceUrl && (
                <div className="as-audio-preview">
                  <p>{t.voiceRecorded}</p>
                  <audio controls src={entry.voiceUrl}>{t.audioUnsupported}</audio>
                </div>
              )}
              {isRecording ? (
                <div className="as-recording-status" role="status">
                  <span className="as-recording-dot" />
                  {t.voiceRecording} · {Math.floor(recordingSeconds / 60)}:
                  {String(recordingSeconds % 60).padStart(2, "0")}
                </div>
              ) : null}
              {!isRecording && entry.voiceUrl && <p className="privacy-note">{t.voiceReady}</p>}
              <div className="as-voice-actions">
                {isRecording ? (
                  <button type="button" className="primary-button" onClick={stopVoiceRecording}>
                    {t.voiceStop}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => startVoiceRecording(question.id)}
                  >
                    {entry.voiceUrl ? t.voiceRerecord : t.voiceStart}
                  </button>
                )}
              </div>
              {voiceError && <p className="as-voice-error" role="alert">{voiceError}</p>}
              <p className="privacy-note">{t.voicePrivacy}</p>
            </div>
          )}

          {!answered && !isRecording && (
            <p className="privacy-note">
              {mode === "text" ? t.textHint : mode === "voice" ? t.voiceHint : t.selectHint}
            </p>
          )}

          <div className="as-actions as-nav">
            <button
              type="button"
              className="as-button-secondary"
              disabled={index === 0 || isRecording}
              onClick={() => setIndex(index - 1)}
            >
              ← {t.previous}
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={!answered || isRecording}
              onClick={() => (isLast ? setPhase("review") : setIndex(index + 1))}
            >
              {isLast ? t.reviewAnswers : t.next} <span>→</span>
            </button>
          </div>
        </div>
      </section>
    );
  } else if (phase === "review") {
    body = (
      <section className="result-section as-review-section">
        <span className="section-kicker">{t.reviewKicker}</span>
        <h1>{t.reviewTitle}</h1>
        <p className="result-intro">{t.reviewText}</p>
        <div className="as-review-list">
          {questions.map((q, questionIndex) => {
            const answer = answers[q.id] || {};
            const selectedOption = q.options.find((option) => option.id === answer.optionId);
            let answerSummary = t.notAnswered;
            if (answer.mode === "choice" && selectedOption) answerSummary = selectedOption.text[lang];
            else if (answer.mode === "text" && answer.text?.trim()) answerSummary = answer.text;
            else if (answer.mode === "voice" && answer.voiceUrl) answerSummary = t.voiceAnswerSaved;
            return (
              <article className="as-review-item" key={q.id}>
                <div className="as-review-heading">
                  <span className="as-review-number">{questionIndex + 1}</span>
                  <span className="as-review-mode">
                    {answer.mode === "voice" ? t.modeVoice : answer.mode === "text" ? t.modeType : t.modeChoose}
                  </span>
                </div>
                <h3>{q.text[lang]}</h3>
                <p className="as-review-answer">{answerSummary}</p>
                <button
                  type="button"
                  className="as-review-edit"
                  onClick={() => { setIndex(questionIndex); setPhase("questions"); }}
                >
                  {t.editAnswer}
                </button>
              </article>
            );
          })}
        </div>
        <p className="privacy-note as-review-privacy">{t.reviewPrivacy}</p>
        <div className="as-actions as-review-actions">
          <button type="button" className="as-button-secondary" onClick={() => { setIndex(total - 1); setPhase("questions"); }}>
            {t.backToQuestions}
          </button>
          <button type="button" className="primary-button" onClick={() => setPhase("done")}>
            {t.confirmFinish} <span>→</span>
          </button>
        </div>
      </section>
    );
  } else {
    body = (
      <section className="result-section as-passport-section">
        <div className="result-success-icon">✓</div>
        <span className="section-kicker">{t.passportKicker}</span>
        <h1>{t.passportTitle}</h1>
        <p className="result-intro">{t.passportIntro}</p>

        <div className="as-passport">
          <div className="as-passport-header">
            <div>
              <span className="as-passport-label">{t.completionStatus}</span>
              <strong className="as-passport-complete" role="status">{t.completed}</strong>
            </div>
            <div>
              <span className="as-passport-label">{t.questionsCompleted}</span>
              <strong>{fill(t.questionsCompletedCount, { completed: answeredCount, total })}</strong>
            </div>
          </div>

          <div className="as-passport-meta">
            <div>
              <span>{t.workerName}</span>
              <strong>{workerName?.trim() || t.notProvided}</strong>
            </div>
            <div>
              <span>{t.workerLocation}</span>
              <strong>{workerLocation?.trim() || t.notProvided}</strong>
            </div>
            <div>
              <span>{t.tradeLabel}</span>
              <strong>{tradeLabel || t.notProvided}</strong>
            </div>
            {workerId != null && (
              <div>
                <span>{t.workerId}</span>
                <strong>#{workerId}</strong>
              </div>
            )}
          </div>

          <section className="as-passport-section-block">
            <h2>{t.answerModeBreakdown}</h2>
            <div className="as-passport-mode-grid">
              {[
                [t.mcqModeLabel, answerModeCounts.mcq],
                [t.textModeLabel, answerModeCounts.text],
                [t.voiceModeLabel, answerModeCounts.voice],
              ].map(([label, count]) => (
                <div className="as-passport-mode" key={label}>
                  <span>{label}</span>
                  <strong>{count}</strong>
                </div>
              ))}
            </div>
          </section>

          <section className="as-passport-section-block">
            <h2>{t.evidenceTitle}</h2>
            <div className="as-passport-evidence-grid">
              <article className="as-passport-evidence">
                <h3>{t.selfReportedEvidence}</h3>
                <p>{t.selfReportedEvidenceText}</p>
              </article>
              <article className="as-passport-evidence">
                <h3>{t.assessedEvidence}</h3>
                <strong className="as-passport-evidence-status">{t.awaitingEvaluation}</strong>
                <p>{t.assessedEvidenceText}</p>
              </article>
              <article className="as-passport-evidence">
                <h3>{t.verifiedEvidence}</h3>
                <strong className="as-passport-evidence-status">{t.notYetVerified}</strong>
                <p>{t.verifiedEvidenceText}</p>
              </article>
            </div>
          </section>

          <p className="as-passport-disclaimer">{t.passportDisclaimer}</p>
          <div className="status-message as-note" role="status">
            {t.completeNote}
          </div>
        </div>

        <div className="as-actions">
          <button type="button" className="primary-button" onClick={onExit}>
            {t.backToProfile}
          </button>
        </div>
      </section>
    );
  }

  return (
    <div className="as-root" lang={lang}>
      {languageSwitch}
      {body}
    </div>
  );
}
