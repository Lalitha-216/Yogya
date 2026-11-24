// DEVELOPMENT ONLY. Everything that uses this module in App.jsx is gated by
// `import.meta.env.DEV`, so Vite removes it from production builds.
//
// Produces a sample profile in the SAME shape the real /api/profile/discover
// response has, so the result screen and the assessment run unchanged. It is not
// a real worker: the id is the fixed string "DEMO", nothing is saved to SQLite,
// nothing is sent to Gemini or the backend, and there is no assessment data.

export const DEMO_WORKER_ID = "DEMO";

// Skill names are English on purpose: the real backend normalises skills to English.
const PROFILES = {
  Electrician: {
    experience_years: 6,
    skills: [
      "Fan installation",
      "Wiring repair",
      "Switchboard and socket fitting",
      "MCB and fuse replacement",
      "Earthing check",
    ],
  },
  Plumber: {
    experience_years: 5,
    skills: [
      "Pipe fitting",
      "Leak repair",
      "Tap and mixer installation",
      "Drain unblocking",
      "Water tank connection",
    ],
  },
};

// Used only when the form fields are still empty.
const IDENTITY = {
  en: { name: "Demo Worker", location: "Hyderabad" },
  te: { name: "డెమో కార్మికుడు", location: "హైదరాబాద్" },
  hi: { name: "डेमो कामगार", location: "हैदराबाद" },
};

export function buildDemoProfile(trade, language) {
  const base = PROFILES[trade] || PROFILES.Electrician;
  const identity = IDENTITY[language] || IDENTITY.en;
  return {
    name: identity.name,
    location: identity.location,
    result: {
      worker_id: DEMO_WORKER_ID,
      profile: {
        trade,
        experience_years: base.experience_years,
        skills: [...base.skills],
        evidence_level: "SELF_REPORTED",
      },
      detected_trade: trade,
      trade_mismatch: false,
      demo: true, // additive flag so the result screen can label it
    },
  };
}

export const DEMO_COPY = {
  en: {
    tag: "DEV ONLY",
    useDemo: "Use Demo Profile",
    hint: "Skips voice and Gemini. Creates a sample {trade} profile on this device only, so you can test the result screen and the skill assessment.",
    banner:
      "DEMO PROFILE: sample data for development. This is not a real worker, and nothing was saved or sent to the server.",
  },
  te: {
    tag: "డెవలప్‌మెంట్ మాత్రమే",
    useDemo: "డెమో ప్రొఫైల్ ఉపయోగించండి",
    hint: "వాయిస్, Gemini లేకుండా ఈ పరికరంలో మాత్రమే నమూనా {trade} ప్రొఫైల్‌ను సృష్టిస్తుంది. ఫలితం స్క్రీన్, నైపుణ్య అంచనాను పరీక్షించడానికి ఉపయోగించండి.",
    banner:
      "డెమో ప్రొఫైల్: డెవలప్‌మెంట్ కోసం నమూనా వివరాలు. ఇది నిజమైన కార్మికుడు కాదు; ఏదీ సర్వర్‌లో భద్రపరచబడలేదు లేదా పంపబడలేదు.",
  },
  hi: {
    tag: "केवल डेवलपमेंट",
    useDemo: "डेमो प्रोफ़ाइल इस्तेमाल करें",
    hint: "आवाज़ और Gemini के बिना, सिर्फ़ इसी डिवाइस पर एक नमूना {trade} प्रोफ़ाइल बनाता है, ताकि आप परिणाम स्क्रीन और कौशल मूल्यांकन जाँच सकें।",
    banner:
      "डेमो प्रोफ़ाइल: विकास के लिए नमूना जानकारी। यह कोई वास्तविक कामगार नहीं है और कुछ भी सर्वर पर सहेजा या भेजा नहीं गया है।",
  },
};
