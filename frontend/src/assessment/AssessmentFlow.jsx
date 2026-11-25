import { useEffect, useRef, useState } from "react";
import "./assessment.css";
import { ASSESSMENT_COPY, LANGUAGES } from "./copy";
import { useVoiceCompanion } from "../voice/VoiceCompanion";

const fill = (template, values) =>
  Object.entries(values).reduce(
    (message, [key, value]) => message.replace(`{${key}}`, value),
    template
  );

const pickLanguage = (code) => (ASSESSMENT_COPY[code] ? code : "en");

const MAX_TEXT = 500; // characters per typed answer
const TOTAL_QUESTIONS = 6;
const AUDIO_FILE_EXTENSIONS = {
  "audio/webm": "webm",
  "audio/ogg": "ogg",
  "audio/mp4": "m4a",
  "audio/mpeg": "mp3",
  "audio/aac": "aac",
  "audio/aiff": "aiff",
  "audio/flac": "flac",
  "audio/opus": "opus",
  "audio/wav": "wav",
};

function mergeQuestions(existing, incoming) {
  const byId = new Map(existing.map((question) => [question.question_id, question]));
  incoming.forEach((question) => {
    if (question && typeof question.question_id === "string") {
      byId.set(question.question_id, question);
    }
  });
  return [...byId.values()].sort(
    (left, right) => left.question_order - right.question_order
  );
}

function validateQuestion(question, t) {
  if (
    !question ||
    typeof question.question_id !== "string" ||
    typeof question.question_text !== "string" ||
    !Number.isInteger(question.question_order) ||
    !Number.isInteger(question.stage_number)
  ) {
    throw new Error(t.invalidQuestion);
  }
  return question;
}

async function requestJson(url, options, t) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (error instanceof TypeError) throw new Error(t.backendUnavailable);
    throw error;
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail = typeof payload?.detail === "string"
      ? payload.detail
      : Array.isArray(payload?.detail)
        ? JSON.stringify(payload.detail)
        : "";
    const error = new Error(
      `${detail || t.requestFailed} (HTTP ${response.status})`
    );
    error.status = response.status;
    throw error;
  }
  if (!payload || typeof payload !== "object") {
    throw new Error(t.invalidResponse);
  }
  return payload;
}

function transcriptionFailureMessage(error, t) {
  const detail = typeof error?.message === "string" ? error.message : "";
  const status = error?.status;
  if (detail.includes("SARVAM_API_KEY") || detail.includes("Sarvam rejected the API key")) {
    return t.transcriptionNotConfigured;
  }
  if (detail.includes("30-second REST limit")) return t.transcriptionTooLong;
  if (detail.includes("credits or quota are exhausted")) return t.transcriptionQuotaExceeded;
  if (detail.includes("rate limited") || status === 429) return t.transcriptionRateLimited;
  if (detail.includes("No speech was detected")) return t.transcriptionNoSpeech;
  if (detail.includes("Empty audio file")) return t.voiceEmpty;
  if (detail.includes("Audio file is too large")) return t.transcriptionFileTooLarge;
  if (detail.includes("Unsupported audio format") || status === 415) {
    return t.transcriptionUnsupported;
  }
  if (detail.includes("Sarvam could not process") || status === 422) {
    return t.transcriptionInvalidAudio;
  }
  if (status === 413) return t.transcriptionTooLong;
  if ([502, 503, 504].includes(status)) return t.transcriptionUnavailable;
  return t.transcriptionFailed;
}

/**
 * Assessment questions, evaluation, and results come from the backend.
 * The browser keeps only current-session answer text and recordings for review.
 */
export default function AssessmentFlow({
  apiBase,
  workerId,
  workerName,
  workerLocation,
  trade,
  initialLanguage,
  onLanguageChange,
  onExit,
  onOpenPassport,
}) {
  const [lang, setLang] = useState(pickLanguage(initialLanguage));
  const [phase, setPhase] = useState("intro");
  const [index, setIndex] = useState(0);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [preferredMode, setPreferredMode] = useState("text");
  const [assessmentId, setAssessmentId] = useState(null);
  const [assessmentResult, setAssessmentResult] = useState(null);
  const [lastAnswerFeedback, setLastAnswerFeedback] = useState(null);
  const [completionSaved, setCompletionSaved] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("");
  const [apiError, setApiError] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [voiceError, setVoiceError] = useState("");
  const [transcriptionError, setTranscriptionError] = useState("");
  const [transcriptionReady, setTranscriptionReady] = useState(false);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const objectUrlsRef = useRef(new Set());
  const answerSubmissionInProgressRef = useRef(false);
  const transcriptionRetryInProgressRef = useRef(false);
  const voice = useVoiceCompanion();
  const voiceSpeakRef = useRef(voice.speak);
  const voiceStopRef = useRef(voice.stop);
  const lastSpeechKeyRef = useRef("");
  const speechGenerationRef = useRef(0);
  const spokenFeedbackIdsRef = useRef(new Set());

  const t = ASSESSMENT_COPY[lang];
  const total = TOTAL_QUESTIONS;
  const hasValidWorkerId = Number.isInteger(workerId) && workerId > 0;
  const question = questions[index];
  const currentQuestionAnswer = question ? answers[question.question_id] || {} : {};
  const currentAnswerMode = currentQuestionAnswer.mode || preferredMode;
  const currentQuestionInstructions = lang === "hi"
    ? t.questionHindiInstruction
    : currentAnswerMode === "voice"
      ? t.questionVoiceInstruction
      : t.questionTextInstruction;
  const currentQuestionSpeech = question
    ? `${fill(t.questionOf, { n: question.question_order, total })}. ${question.question_text}. ${currentQuestionInstructions}`
    : "";
  const currentAnswerFeedback = phase === "questions" &&
    lastAnswerFeedback?.questionId === question?.question_id
    ? lastAnswerFeedback
    : null;
  const previousAnswerFeedback = phase === "questions" &&
    lastAnswerFeedback?.questionOrder === question?.question_order - 1
    ? lastAnswerFeedback
    : null;
  const visibleAnswerFeedback = currentAnswerFeedback || previousAnswerFeedback;
  const reviewAnswerFeedback = phase === "review" &&
    lastAnswerFeedback?.questionOrder === total
    ? lastAnswerFeedback
    : null;
  const feedbackForAnnouncement =
    currentAnswerFeedback || previousAnswerFeedback || reviewAnswerFeedback;
  const feedbackMessage = feedbackForAnnouncement
    ? feedbackForAnnouncement.feedbackReturned
      ? `${t.answerFeedbackLabel}. ${feedbackForAnnouncement.text}`
      : feedbackForAnnouncement.text
    : "";
  const speechBaseText = phase === "intro"
    ? t.introVoiceInstructions
    : phase === "questions" && question
      ? currentQuestionSpeech
      : phase === "review"
        ? t.reviewVoiceInstructions
        : phase === "done"
          ? t.completionVoiceInstructions
          : "";
  const speechKey = [
    lang,
    phase,
    question?.question_id || "",
    phase === "questions" ? currentAnswerMode : "",
    feedbackForAnnouncement?.questionId || "",
  ].join(":");
  const isAnswered = (q) => {
    if (!q) return false;
    const a = answers[q.question_id];
    if (!a) return false;
    if (a.mode === "text") return Boolean(a.text && a.text.trim());
    if (a.mode === "voice") return Boolean(a.voiceBlob || a.voiceUrl || a.transcript);
    return false;
  };

  useEffect(() => {
    voiceSpeakRef.current = voice.speak;
  }, [voice.speak]);

  useEffect(() => {
    voiceStopRef.current = voice.stop;
  }, [voice.stop]);

  useEffect(() => {
    if (speechKey === lastSpeechKeyRef.current || !speechBaseText) return;

    const shouldSpeakFeedback = feedbackForAnnouncement &&
      !spokenFeedbackIdsRef.current.has(feedbackForAnnouncement.questionId);
    const speechText = [
      shouldSpeakFeedback ? feedbackMessage : "",
      speechBaseText,
    ].filter(Boolean).join(". ");

    const generation = ++speechGenerationRef.current;
    voiceStopRef.current();
    if (isLoading || isRecording) return;

    lastSpeechKeyRef.current = speechKey;
    if (shouldSpeakFeedback) {
      spokenFeedbackIdsRef.current.add(feedbackForAnnouncement.questionId);
    }

    Promise.resolve().then(() => {
      if (generation === speechGenerationRef.current && !isLoading && !isRecording) {
        voiceSpeakRef.current(speechText);
      }
    });
  }, [
    feedbackMessage,
    feedbackForAnnouncement,
    isLoading,
    isRecording,
    speechKey,
    speechBaseText,
  ]);

  useEffect(() => {
    if (isLoading || isRecording) voiceStopRef.current();
  }, [isLoading, isRecording]);

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
    setTranscriptionError("");
    setTranscriptionReady(false);
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
  const answeredCount = Object.values(answers).filter((answer) => answer.submitted).length;
  const answerModeCounts = Object.values(answers).reduce((counts, answer) => {
    if (answer.submitted && (answer.mode === "text" || answer.mode === "voice")) {
      counts[answer.mode] += 1;
    }
    return counts;
  }, { text: 0, voice: 0 });
  const updateAnswer = (questionId, patch) => {
    setAnswers((previous) => ({
      ...previous,
      [questionId]: { ...previous[questionId], ...patch },
    }));
  };
  const tradeLabel = t.trades[trade] || trade;
  const changeLanguage = (code) => {
    setLang(code);
    onLanguageChange?.(code);
  };

  const apiRequest = (path, options = {}) =>
    requestJson(`${apiBase.replace(/\/$/, "")}${path}`, options, t);

  const fetchCurrentQuestion = async (id) => {
    const data = await apiRequest(
      `/api/assessments/${id}/questions/current`
    );
    return data.question ? validateQuestion(data.question, t) : null;
  };

  const showQuestion = (currentQuestion, loadedQuestions) => {
    const updatedQuestions = mergeQuestions(loadedQuestions, [currentQuestion]);
    setQuestions(updatedQuestions);
    setIndex(updatedQuestions.findIndex(
      (item) => item.question_id === currentQuestion.question_id
    ));
    setPhase("questions");
  };

  const continueFromBackend = async (id, loadedQuestions) => {
    const currentQuestion = await fetchCurrentQuestion(id);
    if (currentQuestion) {
      showQuestion(currentQuestion, loadedQuestions);
      return;
    }

    const progress = await apiRequest(`/api/assessments/${id}`);
    if (!Number.isInteger(progress.current_stage)) {
      throw new Error(t.invalidResponse);
    }

    if (progress.current_stage < 3) {
      const advanced = await apiRequest(
        `/api/assessments/${id}/stages/next`,
        { method: "POST" }
      );
      const stageQuestions = Array.isArray(advanced.questions)
        ? advanced.questions.map((item) => validateQuestion(item, t))
        : [];
      const questionsWithStage = mergeQuestions(loadedQuestions, stageQuestions);
      setQuestions(questionsWithStage);
      const nextQuestion = await fetchCurrentQuestion(id);
      if (!nextQuestion) throw new Error(t.noCurrentQuestion);
      showQuestion(nextQuestion, questionsWithStage);
      return;
    }

    if (
      progress.current_stage === 3 &&
      progress.answered_question_count === TOTAL_QUESTIONS
    ) {
      setQuestions(loadedQuestions);
      setPhase("review");
      return;
    }

    throw new Error(t.incompleteAssessment);
  };

  const start = async () => {
    if (!hasValidWorkerId) {
      setApiError(t.invalidWorkerId);
      return;
    }
    setIsLoading(true);
    setLoadingLabel(t.starting);
    setApiError("");
    try {
      let id = assessmentId;
      let loadedQuestions = questions;
      if (id == null) {
        const created = await apiRequest("/api/assessments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ worker_id: workerId, language: lang }),
        });
        if (
          !Number.isInteger(created.assessment_id) ||
          created.worker_id !== workerId ||
          created.status !== "IN_PROGRESS"
        ) {
          throw new Error(t.invalidResponse);
        }
        id = created.assessment_id;
        setAssessmentId(id);
        loadedQuestions = Array.isArray(created.questions)
          ? created.questions.map((item) => validateQuestion(item, t))
          : [];
        setQuestions(loadedQuestions);
        setAnswers({});
        setLastAnswerFeedback(null);
      }
      await continueFromBackend(id, loadedQuestions);
    } catch (error) {
      setApiError(error.message || t.requestFailed);
    } finally {
      setIsLoading(false);
      setLoadingLabel("");
    }
  };

  const transcribeVoiceAnswer = async (blob) => {
    const formData = new FormData();
    const mimeType = blob.type.split(";")[0].trim().toLowerCase();
    const extension = AUDIO_FILE_EXTENSIONS[mimeType];
    const filename = extension ? `assessment-answer.${extension}` : "assessment-answer";
    formData.append("audio", blob, filename);
    formData.append("language", lang);
    const data = await apiRequest("/api/voice/transcribe", {
      method: "POST",
      body: formData,
    });
    if (typeof data.transcript !== "string" || !data.transcript.trim()) {
      throw new Error(t.invalidTranscript);
    }
    return data.transcript.trim();
  };

  const retryTranscription = async (currentQuestion, answer) => {
    if (
      !answer.voiceBlob ||
      isLoading ||
      transcriptionRetryInProgressRef.current
    ) {
      return;
    }

    transcriptionRetryInProgressRef.current = true;
    setIsLoading(true);
    setLoadingLabel(t.transcriptionRetrying);
    setApiError("");
    setTranscriptionError("");
    setTranscriptionReady(false);

    let speechMessage = "";
    try {
      const transcript = await transcribeVoiceAnswer(answer.voiceBlob);
      updateAnswer(currentQuestion.question_id, {
        transcript,
        text: transcript,
      });
      setTranscriptionReady(true);
      speechMessage = t.transcriptionReady;
    } catch (error) {
      speechMessage = transcriptionFailureMessage(error, t);
      setTranscriptionError(speechMessage);
    } finally {
      setIsLoading(false);
      setLoadingLabel("");
      transcriptionRetryInProgressRef.current = false;
    }

    if (speechMessage) voice.speak(speechMessage);
  };

  const submitAndContinue = async (currentQuestion, answer) => {
    const questionId = currentQuestion.question_id;
    if (answer.submitted) {
      if (index < questions.length - 1) {
        setIndex(index + 1);
      } else if (currentQuestion.question_order === TOTAL_QUESTIONS) {
        setPhase("review");
      } else {
        setIsLoading(true);
        setLoadingLabel(t.submitting);
        setApiError("");
        try {
          await continueFromBackend(assessmentId, questions);
        } catch (error) {
          setApiError(error.message || t.requestFailed);
        } finally {
          setIsLoading(false);
          setLoadingLabel("");
        }
      }
      return;
    }
    if (isLoading || answerSubmissionInProgressRef.current) return;

    answerSubmissionInProgressRef.current = true;
    setIsLoading(true);
    setLoadingLabel(t.submitting);
    setApiError("");
    setTranscriptionError("");
    setTranscriptionReady(false);
    try {
      let answerText;
      let answerSource;
      let feedbackText = "";
      let feedbackReturned = false;
      if (answer.mode === "text") {
        answerText = answer.text?.trim();
        answerSource = "TEXT";
      } else if (answer.mode === "voice") {
        answerSource = "VOICE";
        try {
          answerText = answer.transcript || await transcribeVoiceAnswer(answer.voiceBlob);
        } catch (error) {
          const message = transcriptionFailureMessage(error, t);
          setTranscriptionError(message);
          voice.speak(message);
          return;
        }
        updateAnswer(questionId, { transcript: answerText, text: answerText });
      } else {
        throw new Error(t.answerRequired);
      }

      if (!answerText) throw new Error(t.answerRequired);
      try {
        const submission = await apiRequest(`/api/assessments/${assessmentId}/answers`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question_id: questionId,
            answer_text: answerText,
            answer_source: answerSource,
          }),
        });
        if (typeof submission.feedback === "string" && submission.feedback.trim()) {
          feedbackText = submission.feedback.trim();
          feedbackReturned = true;
        }
      } catch (submissionError) {
        const progress = await apiRequest(`/api/assessments/${assessmentId}`);
        if (
          !Number.isInteger(progress.answered_question_count) ||
          progress.answered_question_count < currentQuestion.question_order
        ) {
          throw submissionError;
        }
      }
      if (!feedbackText) feedbackText = t.answerReceived;
      const feedback = {
        questionId,
        questionOrder: currentQuestion.question_order,
        text: feedbackText,
        feedbackReturned,
      };
      setLastAnswerFeedback(feedback);
      updateAnswer(questionId, {
        text: answerText,
        transcript: answer.mode === "voice" ? answerText : undefined,
        submitted: true,
        feedback: feedbackText,
        feedbackReturned,
      });
      await continueFromBackend(assessmentId, questions);
    } catch (error) {
      setApiError(error.message || t.requestFailed);
    } finally {
      setIsLoading(false);
      setLoadingLabel("");
      answerSubmissionInProgressRef.current = false;
    }
  };

  const finishAssessment = async () => {
    if (assessmentId == null) {
      setApiError(t.invalidResponse);
      return;
    }
    setIsLoading(true);
    setLoadingLabel(t.finishing);
    setApiError("");
    try {
      if (!completionSaved) {
        try {
          await apiRequest(`/api/assessments/${assessmentId}/complete`, {
            method: "POST",
          });
          setCompletionSaved(true);
        } catch (completionError) {
          try {
            const recoveredResult = await apiRequest(
              `/api/assessments/${assessmentId}/results`
            );
            if (recoveredResult.status === "COMPLETED") {
              setAssessmentResult(recoveredResult);
              setPhase("done");
              return;
            }
          } catch (resultError) {
            if (resultError.status !== 409) throw resultError;
          }
          throw completionError;
        }
      }

      const result = await apiRequest(
        `/api/assessments/${assessmentId}/results`
      );
      if (result.status !== "COMPLETED") throw new Error(t.invalidResponse);
      setAssessmentResult(result);
      setPhase("done");
    } catch (error) {
      setApiError(error.message || t.requestFailed);
    } finally {
      setIsLoading(false);
      setLoadingLabel("");
    }
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
            disabled={isLoading || phase !== "intro"}
            onClick={() => changeLanguage(code)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );

  let body;

  if (phase === "intro") {
    body = (
      <section className="result-section">
        <span className="section-kicker">{t.kicker}</span>
        <h1>{t.introTitle}</h1>
        <p className="result-intro">{t.introText}</p>

        <div className="result-card">
          <div className="result-details" style={{ margin: 0, border: 0, padding: 0 }}>
            <div>
              <small>{t.tradeLabel}</small>
              <strong>{tradeLabel}</strong>
            </div>
            <div>
              <small>{t.questionsLabel}</small>
              <strong>{t.adaptiveQuestions}</strong>
            </div>
            <div>
              <small>{t.workerId}</small>
              <strong>#{workerId}</strong>
            </div>
          </div>
        </div>

        {!hasValidWorkerId && (
          <div className="status-message warning-message" role="alert">
            {t.invalidWorkerId}
          </div>
        )}
        <div className="as-actions">
          <button type="button" className="as-button-secondary" onClick={onExit}>
            {t.backToProfile}
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={isLoading || !hasValidWorkerId}
            onClick={start}
          >
            {t.start} <span>→</span>
          </button>
        </div>
      </section>
    );
  } else if (phase === "questions") {
    const currentQuestion = question;
    const entry = answers[currentQuestion.question_id] || {};
    const mode = entry.mode || preferredMode;
    const text = entry.text || "";
    const answered = isAnswered(currentQuestion);
    const isLast = currentQuestion.question_order === total;

    body = (
      <section className="onboarding-section">
        <div className="as-progress">
          <div className="as-progress-meta">
            <span>{fill(t.questionOf, { n: currentQuestion.question_order, total })}</span>
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
            {currentQuestion.question_text}
          </h2>
          <button
            type="button"
            className="voice-companion-button"
            disabled={isLoading || isRecording}
            onClick={() => voice.speak(currentQuestionSpeech)}
          >
            {t.listenQuestion}
          </button>
          {visibleAnswerFeedback && (
            <div className="status-message" role="status" aria-live="polite">
              <strong>
                {visibleAnswerFeedback.feedbackReturned
                  ? t.answerFeedbackLabel
                  : t.answerReceivedLabel}
                :
              </strong>{" "}
              {visibleAnswerFeedback.text}
            </div>
          )}

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
                  disabled={
                    isRecording ||
                    isLoading ||
                    entry.submitted ||
                    value === "choice"
                  }
                  onClick={() => {
                    setPreferredMode(value);
                    setTranscriptionError("");
                    setTranscriptionReady(false);
                    updateAnswer(currentQuestion.question_id, { mode: value });
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <p className="privacy-note">{t.choiceUnavailable}</p>

          {mode === "choice" ? (
            <p className="privacy-note">{t.choiceUnavailable}</p>
          ) : mode === "text" ? (
            <div className="as-text">
              <label className="field">
                <span>{t.textLabel}</span>
                <textarea
                  rows={6}
                  maxLength={MAX_TEXT}
                  value={text}
                  placeholder={t.textPlaceholder}
                  disabled={isLoading || entry.submitted}
                  onChange={(event) =>
                    updateAnswer(currentQuestion.question_id, { mode: "text", text: event.target.value })
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
                    disabled={isLoading || entry.submitted}
                    onClick={() => startVoiceRecording(currentQuestion.question_id)}
                  >
                    {entry.voiceUrl ? t.voiceRerecord : t.voiceStart}
                  </button>
                )}
              </div>
              {voiceError && <p className="as-voice-error" role="alert">{voiceError}</p>}
              {transcriptionError && (
                <div className="status-message warning-message" role="alert">
                  <p>{transcriptionError}</p>
                  <button
                    type="button"
                    className="as-button-secondary"
                    disabled={isLoading || !entry.voiceBlob}
                    onClick={() => retryTranscription(currentQuestion, entry)}
                  >
                    {t.transcriptionRetry}
                  </button>
                </div>
              )}
              {transcriptionReady && (
                <p className="status-message" role="status">
                  {t.transcriptionReady}
                </p>
              )}
              <p className="privacy-note">{t.voicePrivacy}</p>
            </div>
          )}

          {!answered && !isRecording && (
            <p className="privacy-note">
              {mode === "text" ? t.textHint : t.voiceHint}
            </p>
          )}

          <div className="as-actions as-nav">
            <button
              type="button"
              className="as-button-secondary"
              disabled={index === 0 || isRecording || isLoading}
              onClick={() => {
                setTranscriptionError("");
                setTranscriptionReady(false);
                setIndex(index - 1);
              }}
            >
              ← {t.previous}
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={
                !answered ||
                isRecording ||
                isLoading ||
                Boolean(transcriptionError && mode === "voice" && !entry.transcript)
              }
              onClick={() => submitAndContinue(currentQuestion, entry)}
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
          {questions.map((reviewQuestion, questionIndex) => {
            const answer = answers[reviewQuestion.question_id] || {};
            const answerSummary = answer.text?.trim() || (
              answer.mode === "voice" ? t.voiceAnswerSaved : t.notAnswered
            );
            return (
              <article className="as-review-item" key={reviewQuestion.question_id}>
                <div className="as-review-heading">
                  <span className="as-review-number">{reviewQuestion.question_order}</span>
                  <span className="as-review-mode">
                    {answer.mode === "voice" ? t.modeVoice : t.modeType}
                  </span>
                </div>
                <h3>{reviewQuestion.question_text}</h3>
                <p className="as-review-answer">{answerSummary}</p>
                {answer.feedback && (
                  <p className="privacy-note">
                    <strong>
                      {answer.feedbackReturned
                        ? t.answerFeedbackLabel
                        : t.answerReceivedLabel}
                      :
                    </strong>{" "}
                    {answer.feedback}
                  </p>
                )}
                <button
                  type="button"
                  className="as-review-edit"
                  onClick={() => { setIndex(questionIndex); setPhase("questions"); }}
                >
                  {t.viewAnswer}
                </button>
              </article>
            );
          })}
        </div>
        <p className="privacy-note as-review-privacy">{t.reviewPrivacy}</p>
        <div className="as-actions as-review-actions">
          <button type="button" className="as-button-secondary" onClick={() => { setIndex(questions.length - 1); setPhase("questions"); }}>
            {t.backToQuestions}
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={isLoading}
            onClick={finishAssessment}
          >
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
            <h2>{t.assessmentResults}</h2>
            <div className="as-passport-mode-grid">
              <div className="as-passport-mode">
                <span>{t.totalScore}</span>
                <strong>
                  {assessmentResult?.total_score ?? t.notProvided}
                  {" / "}
                  {assessmentResult?.maximum_score ?? t.notProvided}
                </strong>
              </div>
              <div className="as-passport-mode">
                <span>{t.percentage}</span>
                <strong>
                  {typeof assessmentResult?.score_percentage === "number"
                    ? `${assessmentResult.score_percentage}%`
                    : t.notProvided}
                </strong>
              </div>
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
                <strong className="as-passport-evidence-status">{t.evaluationComplete}</strong>
                <p>{t.assessedEvidenceText}</p>
              </article>
              <article className="as-passport-evidence">
                <h3>{t.verifiedEvidence}</h3>
                <strong className="as-passport-evidence-status">{t.viewPassportPrompt}</strong>
                <p>{t.verifiedEvidenceText}</p>
              </article>
            </div>
          </section>

          <p className="as-passport-disclaimer">{t.passportDisclaimer}</p>
          {assessmentResult?.safety_flags?.safety_critical_misconception && (
            <div className="status-message warning-message" role="status">
              {t.safetyConcern}
            </div>
          )}
        </div>

        <div className="as-actions">
          <button type="button" className="primary-button" onClick={onExit}>
            {t.backToProfile}
          </button>
          <button type="button" className="primary-button" onClick={onOpenPassport}>
            {t.openPassport} <span>→</span>
          </button>
        </div>
      </section>
    );
  }

  return (
    <div className="as-root" lang={lang}>
      {languageSwitch}
      {isLoading && (
        <div className="status-message as-request-status" role="status" aria-live="polite">
          <span className="loading-spinner" />
          {loadingLabel}
        </div>
      )}
      {apiError && (
        <div className="status-message warning-message as-request-status" role="alert">
          {apiError}
        </div>
      )}
      {body}
    </div>
  );
}
