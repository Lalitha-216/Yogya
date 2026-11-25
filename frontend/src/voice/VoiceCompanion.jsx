import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import "./voice.css";

const VoiceCompanionContext = createContext(null);
const VOICE_LOCALES = {
  te: { locale: "te-IN", language: "te" },
  en: { locale: "en-IN", language: "en" },
  hi: { locale: "hi-IN", language: "hi" },
};

const COPY = {
  en: {
    controls: "Voice playback controls",
    repeat: "Repeat",
    stop: "Stop speaking",
    mute: "Mute voice",
    unmute: "Unmute voice",
    unsupported: "Speech playback is not supported in this browser.",
    languageUnavailable: "Voice playback is available only in Telugu, English, and Hindi.",
    voiceUnavailable: "No voice is available for this language on this device.",
    emptyText: "There is no text to speak.",
    muted: "Voice playback is muted.",
    speechError: "Speech playback could not be completed.",
    voiceLoading: "Waiting for a matching voice…",
  },
  te: {
    controls: "వాయిస్ ప్లేబ్యాక్ నియంత్రణలు",
    repeat: "మళ్లీ వినండి",
    stop: "మాట్లాడటం ఆపండి",
    mute: "వాయిస్ మ్యూట్ చేయండి",
    unmute: "వాయిస్ అన్‌మ్యూట్ చేయండి",
    unsupported: "ఈ బ్రౌజర్‌లో మాటల ప్లేబ్యాక్‌కు మద్దతు లేదు.",
    languageUnavailable: "వాయిస్ ప్లేబ్యాక్ తెలుగు, ఇంగ్లీష్, హిందీ భాషల్లో మాత్రమే అందుబాటులో ఉంది.",
    voiceUnavailable: "ఈ పరికరంలో ఎంచుకున్న భాషకు వాయిస్ అందుబాటులో లేదు.",
    emptyText: "మాట్లాడటానికి వచనం లేదు.",
    muted: "వాయిస్ ప్లేబ్యాక్ మ్యూట్‌లో ఉంది.",
    speechError: "వాయిస్ ప్లేబ్యాక్ పూర్తి కాలేదు.",
    voiceLoading: "సరిపోయే వాయిస్ కోసం వేచి ఉంది…",
    ttsLoading: "తెలుగు వాయిస్ సందేశాన్ని సిద్ధం చేస్తోంది…",
    ttsUnavailable: "తెలుగు వాయిస్ సేవ ప్రస్తుతం అందుబాటులో లేదు. తర్వాత మళ్లీ ప్రయత్నించండి.",
    ttsError: "తెలుగు వాయిస్ సందేశాన్ని ప్లే చేయలేకపోయాం. మళ్లీ ప్రయత్నించండి.",
    ttsRateLimited: "తెలుగు వాయిస్ సేవ బిజీగా ఉంది. కొద్దిసేపటి తర్వాత మళ్లీ ప్రయత్నించండి.",
    ttsTimeout: "తెలుగు వాయిస్ సందేశం సిద్ధం కావడానికి ఎక్కువ సమయం పట్టింది. మళ్లీ ప్రయత్నించండి.",
  },
  hi: {
    controls: "आवाज़ चलाने के नियंत्रण",
    repeat: "फिर सुनें",
    stop: "आवाज़ रोकें",
    mute: "आवाज़ म्यूट करें",
    unmute: "आवाज़ अनम्यूट करें",
    unsupported: "इस ब्राउज़र में आवाज़ चलाने की सुविधा उपलब्ध नहीं है।",
    languageUnavailable: "आवाज़ चलाने की सुविधा केवल तेलुगु, अंग्रेज़ी और हिन्दी में उपलब्ध है।",
    voiceUnavailable: "इस डिवाइस पर चुनी गई भाषा की आवाज़ उपलब्ध नहीं है।",
    emptyText: "बोलने के लिए कोई पाठ नहीं है।",
    muted: "आवाज़ म्यूट है।",
    speechError: "आवाज़ पूरी तरह नहीं चल सकी।",
    voiceLoading: "मेल खाती आवाज़ का इंतज़ार है…",
  },
};

function getSpeechSynthesis() {
  if (typeof window === "undefined") return null;
  const synthesis = window.speechSynthesis;
  return synthesis && typeof synthesis.speak === "function" ? synthesis : null;
}

function getUtteranceConstructor() {
  if (typeof window === "undefined") return null;
  return typeof window.SpeechSynthesisUtterance === "function"
    ? window.SpeechSynthesisUtterance
    : null;
}

function findMatchingVoice(voices, language) {
  const requested = VOICE_LOCALES[language];
  if (!requested) return null;
  const normalized = (voice) => String(voice.lang || "").replace("_", "-").toLowerCase();
  return (
    voices.find((voice) => normalized(voice) === requested.locale.toLowerCase()) ||
    voices.find((voice) => normalized(voice) === requested.language) ||
    voices.find((voice) => normalized(voice).startsWith(`${requested.language}-`)) ||
    null
  );
}

export function VoiceCompanionProvider({ apiBase, language, screenKey, children }) {
  const [speaking, setSpeaking] = useState(false);
  const [loading, setLoading] = useState(false);
  const [muted, setMuted] = useState(false);
  const [feedback, setFeedback] = useState("");
  const available = language === "te"
    ? Boolean(apiBase)
    : Boolean(getSpeechSynthesis() && getUtteranceConstructor());
  const [canRepeat, setCanRepeat] = useState(false);
  const synthesisRef = useRef(null);
  const utteranceConstructorRef = useRef(null);
  const utteranceRef = useRef(null);
  const audioRef = useRef(null);
  const audioUrlRef = useRef(null);
  const requestControllerRef = useRef(null);
  const voicesRef = useRef([]);
  const voiceWaitersRef = useRef(new Set());
  const requestIdRef = useRef(0);
  const lastTextRef = useRef("");
  const lastAudioRef = useRef(null);

  const refreshVoices = useCallback((fromEvent = false) => {
    const synthesis = synthesisRef.current;
    if (!synthesis) return [];
    let loadedVoices = [];
    try {
      loadedVoices = synthesis.getVoices();
    } catch {
      loadedVoices = [];
    }
    voicesRef.current = loadedVoices;
    if (loadedVoices.length || fromEvent) {
      voiceWaitersRef.current.forEach((resolve) => resolve(loadedVoices));
      voiceWaitersRef.current.clear();
    }
    return loadedVoices;
  }, []);

  const disposeAudio = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      audioRef.current = null;
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
  }, []);

  const cancelCurrent = useCallback(() => {
    const requestController = requestControllerRef.current;
    requestControllerRef.current = null;
    requestController?.abort();
    disposeAudio();
    try {
      synthesisRef.current?.cancel();
    } catch {
      setFeedback((COPY[language] || COPY.en).speechError);
    }
    utteranceRef.current = null;
    setSpeaking(false);
    setLoading(false);
  }, [disposeAudio, language]);

  const stop = useCallback(() => {
    requestIdRef.current += 1;
    cancelCurrent();
    setFeedback("");
  }, [cancelCurrent]);

  const waitForVoices = useCallback(() => {
    const currentVoices = refreshVoices();
    if (currentVoices.length) return Promise.resolve(currentVoices);
    return new Promise((resolve) => {
      let settled = false;
      const finish = (loadedVoices) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeout);
        voiceWaitersRef.current.delete(finish);
        resolve(loadedVoices);
      };
      const timeout = window.setTimeout(
        () => finish(voicesRef.current),
        2500
      );
      voiceWaitersRef.current.add(finish);
    });
  }, [refreshVoices]);

  const playAudioBlob = useCallback(async (blob, requestId) => {
    try {
      const audioUrl = URL.createObjectURL(blob);
      audioUrlRef.current = audioUrl;
      const audio = new Audio(audioUrl);
      audioRef.current = audio;
      audio.onended = () => {
        if (requestId !== requestIdRef.current) return;
        disposeAudio();
        setSpeaking(false);
        setFeedback("");
      };
      audio.onerror = () => {
        if (requestId !== requestIdRef.current) return;
        disposeAudio();
        setSpeaking(false);
        setFeedback(COPY.te.ttsError);
      };
      setLoading(false);
      setSpeaking(true);
      setFeedback("");
      await audio.play();
      return requestId === requestIdRef.current;
    } catch {
      if (requestId === requestIdRef.current) {
        disposeAudio();
        setLoading(false);
        setSpeaking(false);
        setFeedback(COPY.te.ttsError);
      }
      return false;
    }
  }, [disposeAudio]);

  const speak = useCallback(async (text) => {
    const localized = COPY[language] || COPY.en;
    const normalizedText = typeof text === "string" ? text.trim() : "";
    if (!normalizedText) {
      setFeedback(localized.emptyText);
      return false;
    }
    if (!VOICE_LOCALES[language]) {
      setFeedback(localized.languageUnavailable);
      return false;
    }
    if (muted) {
      setFeedback(localized.muted);
      return false;
    }

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    cancelCurrent();

    if (language === "te") {
      const cachedAudio = lastAudioRef.current;
      if (cachedAudio?.text === normalizedText) {
        lastTextRef.current = normalizedText;
        return playAudioBlob(cachedAudio.blob, requestId);
      }

      const localizedTelugu = COPY.te;
      const controller = new AbortController();
      requestControllerRef.current = controller;
      setLoading(true);
      setFeedback(localizedTelugu.ttsLoading);
      try {
        const endpoint = `${apiBase.replace(/\/+$/, "")}/api/voice/speak`;
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: normalizedText, language: "te-IN" }),
          signal: controller.signal,
        });
        if (requestId !== requestIdRef.current) return false;
        if (!response.ok) {
          setLoading(false);
          setFeedback(
            response.status === 503
              ? localizedTelugu.ttsUnavailable
              : response.status === 429
                ? localizedTelugu.ttsRateLimited
                : response.status === 504
                  ? localizedTelugu.ttsTimeout
                  : localizedTelugu.ttsError
          );
          return false;
        }

        const contentType = response.headers
          .get("content-type")
          ?.split(";")[0]
          .trim()
          .toLowerCase();
        const audioBlob = await response.blob();
        if (
          requestId !== requestIdRef.current ||
          contentType !== "audio/wav" ||
          audioBlob.size === 0
        ) {
          if (requestId === requestIdRef.current) {
            setLoading(false);
            setFeedback(localizedTelugu.ttsError);
          }
          return false;
        }

        lastAudioRef.current = { text: normalizedText, blob: audioBlob };
        lastTextRef.current = normalizedText;
        setCanRepeat(true);
        return await playAudioBlob(audioBlob, requestId);
      } catch (error) {
        if (
          requestId === requestIdRef.current &&
          error?.name !== "AbortError"
        ) {
          setLoading(false);
          setFeedback(localizedTelugu.ttsUnavailable);
        }
        return false;
      } finally {
        if (requestControllerRef.current === controller) {
          requestControllerRef.current = null;
        }
      }
    }

    if (!synthesisRef.current || !utteranceConstructorRef.current) {
      setFeedback(localized.unsupported);
      return false;
    }

    setFeedback(localized.voiceLoading);

    const loadedVoices = await waitForVoices();
    if (requestId !== requestIdRef.current) return false;
    const voice = findMatchingVoice(loadedVoices, language);
    if (!voice) {
      setFeedback(localized.voiceUnavailable);
      return false;
    }

    const Utterance = utteranceConstructorRef.current;
    const utterance = new Utterance(normalizedText);
    utterance.lang = VOICE_LOCALES[language].locale;
    utterance.voice = voice;
    utteranceRef.current = utterance;
    lastTextRef.current = normalizedText;
    setCanRepeat(true);
    utterance.onstart = () => {
      if (requestId === requestIdRef.current) {
        setSpeaking(true);
        setFeedback("");
      }
    };
    utterance.onend = () => {
      if (requestId === requestIdRef.current) {
        utteranceRef.current = null;
        setSpeaking(false);
      }
    };
    utterance.onerror = (event) => {
      if (requestId !== requestIdRef.current) return;
      utteranceRef.current = null;
      setSpeaking(false);
      if (event.error !== "canceled" && event.error !== "interrupted") {
        setFeedback(localized.speechError);
      }
    };

    try {
      synthesisRef.current.speak(utterance);
      return true;
    } catch {
      utteranceRef.current = null;
      setSpeaking(false);
      setFeedback(localized.speechError);
      return false;
    }
  }, [apiBase, cancelCurrent, language, muted, playAudioBlob, waitForVoices]);

  const repeat = useCallback(() => {
    if (!lastTextRef.current) {
      setFeedback((COPY[language] || COPY.en).emptyText);
      return false;
    }
    return speak(lastTextRef.current);
  }, [language, speak]);

  const mute = useCallback(() => {
    setMuted(true);
    requestIdRef.current += 1;
    cancelCurrent();
    setFeedback((COPY[language] || COPY.en).muted);
  }, [cancelCurrent, language]);

  const unmute = useCallback(() => {
    setMuted(false);
    setFeedback("");
  }, []);

  useEffect(() => {
    const synthesis = getSpeechSynthesis();
    const Utterance = getUtteranceConstructor();
    if (!synthesis || !Utterance) return undefined;
    synthesisRef.current = synthesis;
    utteranceConstructorRef.current = Utterance;
    refreshVoices();

    const handleVoicesChanged = () => refreshVoices(true);
    if (typeof synthesis.addEventListener === "function") {
      synthesis.addEventListener("voiceschanged", handleVoicesChanged);
      return () => synthesis.removeEventListener("voiceschanged", handleVoicesChanged);
    }

    const previousHandler = synthesis.onvoiceschanged;
    synthesis.onvoiceschanged = handleVoicesChanged;
    return () => {
      if (synthesis.onvoiceschanged === handleVoicesChanged) {
        synthesis.onvoiceschanged = previousHandler || null;
      }
    };
  }, [refreshVoices]);

  useEffect(() => {
    requestIdRef.current += 1;
    // Cancel browser speech and reset its shared controls when the route changes.
    // eslint-disable-next-line react/set-state-in-effect
    cancelCurrent();
    lastTextRef.current = "";
    setCanRepeat(false);
    setFeedback("");
  }, [cancelCurrent, language, screenKey]);

  useEffect(() => () => {
    requestIdRef.current += 1;
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
    disposeAudio();
    try {
      synthesisRef.current?.cancel();
    } catch {
      // The browser may already have torn down its speech service.
    }
    utteranceRef.current = null;
    voiceWaitersRef.current.forEach((resolve) => resolve([]));
    voiceWaitersRef.current.clear();
  }, [disposeAudio]);

  const clearFeedback = useCallback(() => setFeedback(""), []);
  const value = useMemo(() => ({
    speak,
    repeat,
    stop,
    mute,
    unmute,
    speaking,
    loading,
    muted,
    available,
    feedback,
    canRepeat,
    clearFeedback,
  }), [
    available,
    canRepeat,
    clearFeedback,
    feedback,
    loading,
    mute,
    muted,
    repeat,
    speaking,
    speak,
    stop,
    unmute,
  ]);

  return (
    <VoiceCompanionContext.Provider value={value}>
      {children}
    </VoiceCompanionContext.Provider>
  );
}

// eslint-disable-next-line react/only-export-components
export function useVoiceCompanion() {
  const context = useContext(VoiceCompanionContext);
  if (!context) {
    throw new Error("useVoiceCompanion must be used within VoiceCompanionProvider.");
  }
  return context;
}

export function VoiceCompanionControls({ language }) {
  const voice = useVoiceCompanion();
  const text = COPY[language] || COPY.en;

  return (
    <section className="voice-companion-controls" aria-label={text.controls}>
      <button
        type="button"
        className="voice-companion-button"
        onClick={voice.repeat}
        disabled={!voice.canRepeat || voice.muted || !voice.available || voice.loading}
      >
        {text.repeat}
      </button>
      <button
        type="button"
        className="voice-companion-button"
        onClick={voice.stop}
        disabled={!voice.speaking && !voice.loading}
      >
        {text.stop}
      </button>
      <button
        type="button"
        className="voice-companion-button"
        onClick={voice.muted ? voice.unmute : voice.mute}
        aria-pressed={voice.muted}
      >
        {voice.muted ? text.unmute : text.mute}
      </button>
      <span className="voice-companion-feedback" role="status" aria-live="polite">
        {voice.feedback || (!voice.available ? text.unsupported : "")}
      </span>
    </section>
  );
}
