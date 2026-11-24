import { useEffect, useState } from "react";
import "./passport.css";

const COPY = {
  en: {
    title: "Skill Passport",
    intro: "Worker details, recorded skills, and available assessment evidence.",
    back: "Back to profile",
    loading: "Loading Skill Passport…",
    loadFailed: "The Skill Passport could not be loaded. Please try again.",
    notFound: "No worker profile was found for this ID.",
    invalidWorker: "This profile does not have a saved numeric worker ID. Demo profiles are not stored by the backend.",
    retry: "Try again",
    workerDetails: "Worker details",
    workerId: "Worker ID",
    name: "Name",
    location: "Location",
    trade: "Trade",
    language: "Language",
    experience: "Experience",
    experienceUnknown: "Not specified",
    ruleBasedFallback: "This profile was extracted using rules because Gemini was temporarily unavailable.",
    years: "years",
    skills: "Recognized skills",
    noSkills: "No skills are recorded for this worker yet.",
    selfReported: "Self-reported",
    assessed: "Assessed",
    independentlyVerified: "Independently verified",
    otherEvidence: "Evidence",
    otherBreakdown: "Other assessment evidence",
    assessment: "Assessment results",
    assessmentStatus: "Status",
    completed: "Completed",
    inProgress: "In progress",
    abandoned: "Abandoned",
    noAssessment: "No assessment",
    currentStage: "Current stage",
    totalScore: "Score",
    maximumScore: "Maximum score",
    percentage: "Percentage",
    completionDate: "Completion date",
    resultsUnavailable: "Assessment results are not available until an assessment is completed.",
    assessmentUnavailable: "No assessment data is available for this worker.",
    breakdown: "Skill-wise assessment evidence",
    demonstratedConcepts: "Demonstrated concepts",
    noConcepts: "No demonstrated concepts were returned for this skill.",
    evaluationUnavailable: "Assessment evidence is not available yet.",
    feedback: "Assessment feedback",
    safety: "Safety",
    safetyFlagged: "Safety-critical misconception recorded",
    noSafetyFlag: "No safety-critical misconception recorded",
    safetyConcerns: "Safety concerns",
    noSafetyConcerns: "No safety concerns were recorded in this assessment.",
    noBreakdown: "No skill-wise assessment evidence is available.",
    evidence: "Evidence",
    question: "Question",
    rationale: "Rationale",
    reason: "Reason",
    notProvided: "Not provided",
    demoWarning: "Independent verification is demo-only here. The assessor's identity has not been authenticated.",
    jobs: "Find matching jobs",
    languageNames: { en: "English", te: "Telugu", hi: "Hindi" },
    trades: { Electrician: "Electrician", Plumber: "Plumber" },
  },
  te: {
    title: "నైపుణ్య పాస్‌పోర్ట్",
    intro: "కార్మికుడి వివరాలు, నమోదు చేసిన నైపుణ్యాలు, అందుబాటులో ఉన్న అంచనా ఆధారాలు.",
    back: "ప్రొఫైల్‌కు తిరిగి వెళ్లండి",
    loading: "నైపుణ్య పాస్‌పోర్ట్ లోడ్ అవుతోంది…",
    loadFailed: "నైపుణ్య పాస్‌పోర్ట్‌ను లోడ్ చేయలేకపోయాం. మళ్లీ ప్రయత్నించండి.",
    notFound: "ఈ ఐడీకి కార్మికుడి ప్రొఫైల్ కనబడలేదు.",
    invalidWorker: "ఈ ప్రొఫైల్‌కు భద్రపరచిన సంఖ్యా కార్మిక ఐడీ లేదు. డెమో ప్రొఫైల్‌లు బ్యాకెండ్‌లో భద్రపరచబడవు.",
    retry: "మళ్లీ ప్రయత్నించండి",
    workerDetails: "కార్మికుడి వివరాలు",
    workerId: "కార్మికుడి ఐడీ",
    name: "పేరు",
    location: "ప్రాంతం",
    trade: "వృత్తి",
    language: "భాష",
    experience: "అనుభవం",
    experienceUnknown: "పేర్కొనలేదు",
    ruleBasedFallback: "Gemini తాత్కాలికంగా అందుబాటులో లేకపోవడంతో ఈ ప్రొఫైల్‌ను నియమాల ఆధారంగా రూపొందించాం.",
    years: "సంవత్సరాలు",
    evidence: "ఆధారం",
    skills: "గుర్తించిన నైపుణ్యాలు",
    noSkills: "ఈ కార్మికుడికి ఇంకా నైపుణ్యాలు నమోదు కాలేదు.",
    selfReported: "స్వయంగా తెలిపినవి",
    assessed: "అంచనా వేయబడినవి",
    independentlyVerified: "స్వతంత్రంగా ధృవీకరించినవి",
    assessment: "అంచనా ఫలితాలు",
    assessmentStatus: "స్థితి",
    completed: "పూర్తయింది",
    inProgress: "కొనసాగుతోంది",
    abandoned: "మధ్యలో ఆగిపోయింది",
    noAssessment: "అంచనా లేదు",
    currentStage: "ప్రస్తుత దశ",
    totalScore: "స్కోరు",
    maximumScore: "గరిష్ఠ స్కోరు",
    percentage: "శాతం",
    completionDate: "పూర్తి చేసిన తేదీ",
    resultsUnavailable: "అంచనా పూర్తయ్యే వరకు ఫలితాలు అందుబాటులో ఉండవు.",
    assessmentUnavailable: "ఈ కార్మికుడికి అంచనా సమాచారం అందుబాటులో లేదు.",
    breakdown: "నైపుణ్యాల వారీగా అంచనా ఆధారాలు",
    demonstratedConcepts: "ప్రదర్శించిన అంశాలు",
    noConcepts: "ఈ నైపుణ్యానికి ప్రదర్శించిన అంశాలు ఏవీ అందలేదు.",
    evaluationUnavailable: "అంచనా ఆధారాలు ఇంకా అందుబాటులో లేవు.",
    feedback: "అంచనా అభిప్రాయం",
    safety: "భద్రత",
    safetyFlagged: "భద్రతకు సంబంధించిన అపోహ నమోదు చేయబడింది",
    noSafetyFlag: "భద్రతకు సంబంధించిన అపోహ నమోదు కాలేదు",
    safetyConcerns: "భద్రతా ఆందోళనలు",
    noSafetyConcerns: "ఈ అంచనాలో భద్రతా ఆందోళనలు నమోదు కాలేదు.",
    noBreakdown: "నైపుణ్యాల వారీ అంచనా ఆధారాలు అందుబాటులో లేవు.",
    otherEvidence: "ఇతర ఆధారం",
    otherBreakdown: "ఇతర అంచనా ఆధారాలు",
    question: "ప్రశ్న",
    rationale: "కారణం",
    reason: "వివరణ",
    notProvided: "ఇవ్వలేదు",
    demoWarning: "ఇక్కడి స్వతంత్ర ధృవీకరణ డెమో మాత్రమే. ధృవీకరించిన వ్యక్తి గుర్తింపును నిర్ధారించలేదు.",
    jobs: "సరిపోయే ఉద్యోగాలను చూడండి",
    languageNames: { en: "ఇంగ్లీష్", te: "తెలుగు", hi: "హిందీ" },
    trades: { Electrician: "ఎలక్ట్రీషియన్", Plumber: "ప్లంబర్", Other: "ఇతర" },
  },
  hi: {
    title: "कौशल पासपोर्ट",
    intro: "कामगार की जानकारी, दर्ज कौशल और उपलब्ध मूल्यांकन साक्ष्य।",
    back: "प्रोफ़ाइल पर वापस जाएँ",
    loading: "कौशल पासपोर्ट लोड हो रहा है…",
    loadFailed: "कौशल पासपोर्ट लोड नहीं हो सका। कृपया फिर कोशिश करें।",
    notFound: "इस आईडी के लिए कामगार की प्रोफ़ाइल नहीं मिली।",
    invalidWorker: "इस प्रोफ़ाइल के पास सहेजी हुई संख्यात्मक कामगार आईडी नहीं है। डेमो प्रोफ़ाइल बैकएंड में सहेजी नहीं जाती।",
    retry: "फिर कोशिश करें",
    workerDetails: "कामगार की जानकारी",
    workerId: "कामगार आईडी",
    name: "नाम",
    location: "स्थान",
    trade: "काम",
    language: "भाषा",
    experience: "अनुभव",
    experienceUnknown: "नहीं बताया गया",
    ruleBasedFallback: "Gemini अस्थायी रूप से उपलब्ध न होने पर यह प्रोफ़ाइल नियम-आधारित तरीके से बनाई गई।",
    years: "वर्ष",
    evidence: "साक्ष्य",
    skills: "पहचाने गए कौशल",
    noSkills: "इस कामगार के लिए अभी कोई कौशल दर्ज नहीं है।",
    selfReported: "स्वयं बताए गए",
    assessed: "आकलित",
    independentlyVerified: "स्वतंत्र रूप से सत्यापित",
    assessment: "मूल्यांकन के नतीजे",
    assessmentStatus: "स्थिति",
    completed: "पूरा हुआ",
    inProgress: "जारी है",
    abandoned: "अधूरा छोड़ा गया",
    noAssessment: "कोई मूल्यांकन नहीं",
    currentStage: "मौजूदा चरण",
    totalScore: "अंक",
    maximumScore: "अधिकतम अंक",
    percentage: "प्रतिशत",
    completionDate: "पूरा होने की तारीख",
    resultsUnavailable: "मूल्यांकन पूरा होने तक नतीजे उपलब्ध नहीं हैं।",
    assessmentUnavailable: "इस कामगार के लिए मूल्यांकन की जानकारी उपलब्ध नहीं है।",
    breakdown: "कौशल के अनुसार मूल्यांकन साक्ष्य",
    demonstratedConcepts: "दिखाई गई समझ",
    noConcepts: "इस कौशल के लिए दिखाई गई समझ का कोई विवरण नहीं मिला।",
    evaluationUnavailable: "मूल्यांकन साक्ष्य अभी उपलब्ध नहीं हैं।",
    feedback: "मूल्यांकन प्रतिक्रिया",
    safety: "सुरक्षा",
    safetyFlagged: "सुरक्षा से जुड़ी गलत धारणा दर्ज की गई",
    noSafetyFlag: "सुरक्षा से जुड़ी कोई गलत धारणा दर्ज नहीं की गई",
    safetyConcerns: "सुरक्षा संबंधी चिंताएँ",
    noSafetyConcerns: "इस मूल्यांकन में सुरक्षा संबंधी कोई चिंता दर्ज नहीं की गई।",
    noBreakdown: "कौशल के अनुसार मूल्यांकन साक्ष्य उपलब्ध नहीं हैं।",
    otherEvidence: "अन्य साक्ष्य",
    otherBreakdown: "अन्य मूल्यांकन साक्ष्य",
    question: "प्रश्न",
    rationale: "आधार",
    reason: "कारण",
    notProvided: "नहीं दिया गया",
    demoWarning: "यहाँ स्वतंत्र सत्यापन केवल डेमो है। सत्यापनकर्ता की पहचान प्रमाणित नहीं की गई है।",
    jobs: "मिलते-जुलते काम देखें",
    languageNames: { en: "अंग्रेज़ी", te: "तेलुगु", hi: "हिन्दी" },
    trades: { Electrician: "इलेक्ट्रीशियन", Plumber: "प्लंबर", Other: "अन्य" },
  },
};

const normalize = (value) =>
  typeof value === "string" ? value.trim().toLocaleLowerCase() : "";

const isRecord = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);

function evidenceLabel(level, t) {
  if (level === "SELF_REPORTED") return t.selfReported;
  if (level === "ASSESSED") return t.assessed;
  if (level === "INDEPENDENTLY_VERIFIED") return t.independentlyVerified;
  return level ? `${t.otherEvidence}: ${level}` : t.notProvided;
}

function statusLabel(status, t) {
  const labels = {
    COMPLETED: t.completed,
    IN_PROGRESS: t.inProgress,
    ABANDONED: t.abandoned,
    NO_ASSESSMENT: t.noAssessment,
  };
  return labels[status] || status || t.notProvided;
}

function DisplayField({ label, children }) {
  return (
    <div className="passport-field">
      <span>{label}</span>
      <strong>{children ?? "—"}</strong>
    </div>
  );
}

function EvidenceItem({ item, t }) {
  if (typeof item === "string" || typeof item === "number") {
    return <li className="passport-evidence-item">{item}</li>;
  }
  if (!isRecord(item)) return null;
  return (
    <li className="passport-evidence-item">
      {item.question_id && (
        <p><span>{t.question}:</span> {item.question_id}</p>
      )}
      {item.concept && <h4>{item.concept}</h4>}
      {item.feedback && <p>{item.feedback}</p>}
      {item.concern && <p><span>{t.safetyConcerns}:</span> {item.concern}</p>}
      {item.evidence && <p><span>{t.evidence}:</span> {item.evidence}</p>}
      {item.rationale && <p><span>{t.rationale}:</span> {item.rationale}</p>}
      {item.reason && <p><span>{t.reason}:</span> {item.reason}</p>}
    </li>
  );
}

export default function SkillPassportPage({
  apiBase,
  language,
  workerId,
  onBack,
  onOpenJobs,
}) {
  const t = COPY[language] || COPY.en;
  const [attempt, setAttempt] = useState(0);
  const [request, setRequest] = useState(null);
  const requestKey = `${apiBase}:${workerId}:${attempt}`;
  const invalidWorker = !Number.isInteger(workerId) || workerId <= 0;
  const requestIsCurrent = request?.key === requestKey;
  const requestStatus = invalidWorker
    ? "error"
    : requestIsCurrent
      ? request.status
      : "loading";
  const requestError = invalidWorker
    ? "invalidWorker"
    : requestIsCurrent
      ? request.error
      : null;
  const data = requestStatus === "success" ? request.data : null;

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    if (invalidWorker) {
      return () => {
        active = false;
        controller.abort();
      };
    }

    const base = apiBase.replace(/\/$/, "");

    async function loadPassport() {
      try {
        const response = await fetch(
          `${base}/api/workers/${workerId}/passport`,
          { signal: controller.signal }
        );
        if (!response.ok) {
          const error = new Error("Passport request failed");
          error.status = response.status;
          throw error;
        }

        const data = await response.json();
        if (!isRecord(data) || !isRecord(data.worker_profile)) {
          throw new Error("Passport response has an invalid shape");
        }
        if (active) {
          setRequest({ key: requestKey, status: "success", data });
        }
      } catch (error) {
        if (!active || error.name === "AbortError") return;
        setRequest({
          key: requestKey,
          status: "error",
          error: error.status === 404 ? "notFound" : "loadFailed",
        });
      }
    }

    loadPassport();
    return () => {
      active = false;
      controller.abort();
    };
  }, [apiBase, attempt, invalidWorker, requestKey, workerId]);

  const profile = data?.worker_profile || {};
  const skills = Array.isArray(data?.recognized_skills) ? data.recognized_skills : [];
  const summary = isRecord(data?.assessment_summary) ? data.assessment_summary : null;
  const assessmentEvidence = isRecord(data?.assessment_evidence)
    ? data.assessment_evidence
    : {};
  const concepts = Array.isArray(assessmentEvidence.demonstrated_concepts)
    ? assessmentEvidence.demonstrated_concepts
    : [];
  const feedback = Array.isArray(assessmentEvidence.relevant_feedback)
    ? assessmentEvidence.relevant_feedback
    : [];
  const safety = isRecord(assessmentEvidence.safety) ? assessmentEvidence.safety : {};
  const concerns = Array.isArray(safety.concerns) ? safety.concerns : [];
  const completed = summary?.status === "COMPLETED";
  const languageName = t.languageNames[profile.language] || profile.language;
  const tradeName = t.trades[profile.trade] || profile.trade;
  const verifiedDemo = skills.some(
    (skill) =>
      isRecord(skill) &&
      skill.evidence_level === "INDEPENDENTLY_VERIFIED" &&
      skill.assessor_identity_authenticated === false
  );

  const questionSkills = new Map();
  [...concepts, ...feedback].forEach((item) => {
    if (item?.question_id && item?.skill_tag) {
      questionSkills.set(item.question_id, item.skill_tag);
    }
  });

  const concernSkill = (concern) =>
    concern?.skill_tag || questionSkills.get(concern?.question_id) || "";

  const unmatchedConcepts = concepts.filter(
    (concept) =>
      isRecord(concept) &&
      !skills.some((skill) =>
        normalize(skill?.skill_name) &&
        normalize(skill?.skill_name) === normalize(concept.skill_tag)
      )
  );
  const unmatchedConcerns = concerns.filter(
    (concern) =>
      !skills.some((skill) =>
        normalize(skill?.skill_name) &&
        normalize(skill?.skill_name) === normalize(concernSkill(concern))
      )
  );
  const unmatchedFeedback = feedback.filter(
    (item) =>
      isRecord(item) &&
      !skills.some((skill) =>
        normalize(skill?.skill_name) &&
        normalize(skill?.skill_name) === normalize(item.skill_tag)
      )
  );

  return (
    <section className="passport-page" aria-labelledby="passport-title" lang={language}>
      <button type="button" className="back-link passport-back" onClick={onBack}>
        ← {t.back}
      </button>

      <header className="passport-heading">
        <span className="section-kicker">YOGYA · {t.title}</span>
        <h1 id="passport-title">{t.title}</h1>
        <p>{t.intro}</p>
      </header>

      {requestStatus === "loading" && (
        <div className="status-message passport-status" role="status" aria-live="polite">
          <span className="loading-spinner" />
          {t.loading}
        </div>
      )}

      {requestStatus === "error" && (
        <div className="status-message warning-message passport-status" role="alert">
          <p>{t[requestError] || t.loadFailed}</p>
          {requestError !== "invalidWorker" && (
            <button type="button" className="passport-retry" onClick={() => setAttempt((value) => value + 1)}>
              {t.retry}
            </button>
          )}
        </div>
      )}

      {requestStatus === "success" && (
        <>
          {verifiedDemo && (
            <div className="status-message warning-message passport-demo-warning" role="note">
              {t.demoWarning}
            </div>
          )}

          <section className="passport-card">
            <h2>{t.workerDetails}</h2>
            <div className="passport-fields">
              <DisplayField label={t.workerId}>{profile.worker_id}</DisplayField>
              <DisplayField label={t.name}>{profile.name || t.notProvided}</DisplayField>
              <DisplayField label={t.location}>{profile.location || t.notProvided}</DisplayField>
              <DisplayField label={t.trade}>{tradeName || t.notProvided}</DisplayField>
              <DisplayField label={t.language}>{languageName || t.notProvided}</DisplayField>
              <DisplayField label={t.experience}>
                {typeof profile.experience?.years === "number"
                  ? `${profile.experience.years} ${t.years}`
                  : t.experienceUnknown}
              </DisplayField>
              {profile.experience?.evidence_level && (
                <DisplayField label={t.evidence}>
                  {evidenceLabel(profile.experience.evidence_level, t)}
                </DisplayField>
              )}
            </div>
            {profile.extraction_source === "rule_based_fallback" && (
              <div className="status-message warning-message passport-demo-warning" role="note">
                {t.ruleBasedFallback}
              </div>
            )}
          </section>

          <section className="passport-card">
            <h2>{t.skills}</h2>
            {skills.length ? (
              <ul className="passport-skills">
                {skills.map((skill, index) => (
                  isRecord(skill) && (
                    <li className="passport-skill" key={`${skill.skill_name || "skill"}-${index}`}>
                      <strong>{skill.skill_name || t.notProvided}</strong>
                      <span className={`passport-evidence passport-evidence-${String(skill.evidence_level || "other").toLowerCase()}`}>
                        {evidenceLabel(skill.evidence_level, t)}
                      </span>
                    </li>
                  )
                ))}
              </ul>
            ) : (
              <p className="passport-muted">{t.noSkills}</p>
            )}
          </section>

          <section className="passport-card">
            <h2>{t.assessment}</h2>
            {summary ? (
              <>
                <div className="passport-fields">
                  <DisplayField label={t.assessmentStatus}>
                    {statusLabel(summary.status, t)}
                  </DisplayField>
                  {summary.assessment_id != null && (
                    <DisplayField label={t.assessment}>#{summary.assessment_id}</DisplayField>
                  )}
                  {summary.current_stage != null && (
                    <DisplayField label={t.currentStage}>{summary.current_stage}</DisplayField>
                  )}
                  {completed && (
                    <>
                      <DisplayField label={t.totalScore}>
                        {summary.total_score ?? t.notProvided}
                      </DisplayField>
                      <DisplayField label={t.maximumScore}>
                        {summary.maximum_score ?? t.notProvided}
                      </DisplayField>
                      <DisplayField label={t.percentage}>
                        {typeof summary.percentage === "number"
                          ? `${summary.percentage}%`
                          : t.notProvided}
                      </DisplayField>
                      <DisplayField label={t.completionDate}>
                        {summary.completion_date || t.notProvided}
                      </DisplayField>
                    </>
                  )}
                </div>
                {!completed && (
                  <p className="passport-muted">
                    {summary.status === "NO_ASSESSMENT"
                      ? t.assessmentUnavailable
                      : t.resultsUnavailable}
                  </p>
                )}
              </>
            ) : (
              <p className="passport-muted">{t.assessmentUnavailable}</p>
            )}
          </section>

          <section className="passport-card">
            <h2>{t.breakdown}</h2>
            {!completed ? (
              <p className="passport-muted">{t.evaluationUnavailable}</p>
            ) : skills.length || concepts.length || feedback.length || concerns.length ? (
              <div className="passport-breakdown">
                {skills.map((skill, index) => {
                  if (!isRecord(skill)) return null;
                  const skillName = skill.skill_name;
                  const key = normalize(skillName);
                  const skillConcepts = concepts.filter(
                    (item) => normalize(item?.skill_tag) === key
                  );
                  const skillFeedback = feedback.filter(
                    (item) => normalize(item?.skill_tag) === key
                  );
                  const skillConcerns = concerns.filter(
                    (item) => normalize(concernSkill(item)) === key
                  );

                  return (
                    <article className="passport-breakdown-skill" key={`${skillName || "skill"}-${index}`}>
                      <h3>{skillName || t.notProvided}</h3>
                      {skillConcepts.length ? (
                        <div>
                          <h4>{t.demonstratedConcepts}</h4>
                          <ul>{skillConcepts.map((item, itemIndex) => (
                            <EvidenceItem item={item} t={t} key={`${item.question_id || "concept"}-${itemIndex}`} />
                          ))}</ul>
                        </div>
                      ) : (
                        <p className="passport-muted">{t.noConcepts}</p>
                      )}
                      {skillFeedback.length > 0 && (
                        <div>
                          <h4>{t.feedback}</h4>
                          <ul>{skillFeedback.map((item, itemIndex) => (
                            <EvidenceItem item={item} t={t} key={`${item.question_id || "feedback"}-${itemIndex}`} />
                          ))}</ul>
                        </div>
                      )}
                      {skillConcerns.length > 0 && (
                        <div>
                          <h4>{t.safetyConcerns}</h4>
                          <ul>{skillConcerns.map((item, itemIndex) => (
                            <EvidenceItem item={item} t={t} key={`${item.question_id || "concern"}-${itemIndex}`} />
                          ))}</ul>
                        </div>
                      )}
                    </article>
                  );
                })}

                {unmatchedConcepts.length > 0 && (
                  <article className="passport-breakdown-skill">
                    <h3>{t.otherBreakdown}</h3>
                    <ul>{unmatchedConcepts.map((item, index) => (
                      <EvidenceItem item={item} t={t} key={`${item.question_id || "concept"}-${index}`} />
                    ))}</ul>
                    {unmatchedFeedback.length > 0 && (
                      <ul>{unmatchedFeedback.map((item, index) => (
                        <EvidenceItem item={item} t={t} key={`${item.question_id || "feedback"}-${index}`} />
                      ))}</ul>
                    )}
                  </article>
                )}

                {unmatchedFeedback.length > 0 && unmatchedConcepts.length === 0 && (
                  <article className="passport-breakdown-skill">
                    <h3>{t.otherBreakdown}</h3>
                    <ul>{unmatchedFeedback.map((item, index) => (
                      <EvidenceItem item={item} t={t} key={`${item.question_id || "feedback"}-${index}`} />
                    ))}</ul>
                  </article>
                )}

                <article className="passport-safety-summary">
                  <h3>{t.safety}</h3>
                  <p className={safety.safety_critical_misconception ? "passport-safety-flagged" : ""}>
                    {safety.safety_critical_misconception ? t.safetyFlagged : t.noSafetyFlag}
                  </p>
                  {unmatchedConcerns.length ? (
                    <>
                      <h4>{t.safetyConcerns}</h4>
                      <ul>{unmatchedConcerns.map((item, index) => (
                        <EvidenceItem item={item} t={t} key={`${item?.question_id || "concern"}-${index}`} />
                      ))}</ul>
                    </>
                  ) : concerns.length === 0 ? (
                    <p className="passport-muted">{t.noSafetyConcerns}</p>
                  ) : null}
                </article>
              </div>
            ) : (
              <p className="passport-muted">{t.noBreakdown}</p>
            )}
          </section>
        </>
      )}

      <div className="passport-page-actions">
        <button type="button" className="as-button-secondary" onClick={onBack}>
          ← {t.back}
        </button>
        {Number.isInteger(workerId) && workerId > 0 && (
          <button type="button" className="primary-button" onClick={onOpenJobs}>
            {t.jobs} <span>→</span>
          </button>
        )}
      </div>
    </section>
  );
}
