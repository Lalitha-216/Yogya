import { useEffect, useState } from "react";
import "./jobs.css";

const COPY = {
  en: {
    title: "Job recommendations",
    intro: "Opportunities matched to the skills saved in your Yogya profile.",
    back: "Back to Skill Passport",
    loading: "Loading job recommendations…",
    loadFailed: "Job recommendations could not be loaded. Please try again.",
    workerNotFound: "No saved worker profile was found for this ID.",
    invalidWorker: "A saved numeric worker ID is required to view job recommendations.",
    retry: "Try again",
    noJobs: "No matching jobs are available right now.",
    demoNotice: "These listings come from Yogya's demo job dataset, not live vacancies.",
    match: "Match",
    employer: "Employer",
    location: "Location",
    jobType: "Job type",
    salaryRange: "Salary range",
    jobId: "Job ID",
    matchedSkills: "Matched required skills",
    missingSkills: "Missing required skills",
    preferredSkills: "Preferred skills",
    noMatchedSkills: "No required skills matched.",
    noMissingSkills: "No missing required skills.",
    noPreferredSkills: "No preferred skills listed.",
    selfReported: "Self-reported",
    assessed: "Assessed",
    independentlyVerified: "Independently verified",
    unknownEvidence: "Other evidence",
    trades: { Electrician: "Electrician", Plumber: "Plumber" },
  },
  te: {
    title: "ఉద్యోగ సిఫార్సులు",
    intro: "మీ యోగ్య ప్రొఫైల్‌లో భద్రపరచిన నైపుణ్యాలకు సరిపోయే అవకాశాలు.",
    back: "నైపుణ్య పాస్‌పోర్ట్‌కు తిరిగి వెళ్లండి",
    loading: "ఉద్యోగ సిఫార్సులు లోడ్ అవుతున్నాయి…",
    loadFailed: "ఉద్యోగ సిఫార్సులను లోడ్ చేయలేకపోయాం. మళ్లీ ప్రయత్నించండి.",
    workerNotFound: "ఈ ఐడీకి భద్రపరచిన కార్మికుడి ప్రొఫైల్ కనబడలేదు.",
    invalidWorker: "ఉద్యోగ సిఫార్సుల కోసం భద్రపరచిన సంఖ్యా కార్మిక ఐడీ అవసరం.",
    retry: "మళ్లీ ప్రయత్నించండి",
    noJobs: "ప్రస్తుతం సరిపోయే ఉద్యోగాలు అందుబాటులో లేవు.",
    demoNotice: "ఈ జాబితాలు యోగ్య డెమో ఉద్యోగ డేటా నుంచి వచ్చాయి; ఇవి ప్రత్యక్ష ఖాళీలు కావు.",
    match: "సరిపోలిక",
    employer: "యజమాని",
    location: "ప్రాంతం",
    jobType: "ఉద్యోగ రకం",
    salaryRange: "జీత పరిధి",
    jobId: "ఉద్యోగ ఐడీ",
    matchedSkills: "సరిపోయిన తప్పనిసరి నైపుణ్యాలు",
    missingSkills: "లేని తప్పనిసరి నైపుణ్యాలు",
    preferredSkills: "అభిలషిత నైపుణ్యాలు",
    noMatchedSkills: "తప్పనిసరి నైపుణ్యాలు ఏవీ సరిపోలలేదు.",
    noMissingSkills: "తప్పనిసరి నైపుణ్యాల్లో లోటు లేదు.",
    noPreferredSkills: "అభిలషిత నైపుణ్యాలు పేర్కొనలేదు.",
    selfReported: "స్వయంగా తెలిపినవి",
    assessed: "అంచనా వేయబడినవి",
    independentlyVerified: "స్వతంత్రంగా ధృవీకరించినవి",
    unknownEvidence: "ఇతర ఆధారం",
    trades: { Electrician: "ఎలక్ట్రీషియన్", Plumber: "ప్లంబర్" },
  },
  hi: {
    title: "नौकरी सुझाव",
    intro: "आपकी योग्या प्रोफ़ाइल में दर्ज कौशलों से मेल खाते अवसर।",
    back: "कौशल पासपोर्ट पर वापस जाएँ",
    loading: "नौकरी सुझाव लोड हो रहे हैं…",
    loadFailed: "नौकरी सुझाव लोड नहीं हो सके। कृपया फिर कोशिश करें।",
    workerNotFound: "इस आईडी के लिए कामगार की सहेजी हुई प्रोफ़ाइल नहीं मिली।",
    invalidWorker: "नौकरी सुझाव देखने के लिए सहेजी हुई संख्यात्मक कामगार आईडी ज़रूरी है।",
    retry: "फिर कोशिश करें",
    noJobs: "अभी कोई मेल खाती नौकरी उपलब्ध नहीं है।",
    demoNotice: "ये सूचियाँ योग्या के डेमो जॉब डेटा से हैं, लाइव रिक्तियाँ नहीं।",
    match: "मेल",
    employer: "नियोक्ता",
    location: "स्थान",
    jobType: "काम का प्रकार",
    salaryRange: "वेतन सीमा",
    jobId: "जॉब आईडी",
    matchedSkills: "मेल खाते ज़रूरी कौशल",
    missingSkills: "नहीं मिले ज़रूरी कौशल",
    preferredSkills: "वांछित कौशल",
    noMatchedSkills: "कोई ज़रूरी कौशल मेल नहीं खाया।",
    noMissingSkills: "कोई ज़रूरी कौशल बाकी नहीं है।",
    noPreferredSkills: "कोई वांछित कौशल सूचीबद्ध नहीं है।",
    selfReported: "स्वयं बताए गए",
    assessed: "आकलित",
    independentlyVerified: "स्वतंत्र रूप से सत्यापित",
    unknownEvidence: "अन्य साक्ष्य",
    trades: { Electrician: "इलेक्ट्रीशियन", Plumber: "प्लंबर" },
  },
};

const isRecord = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);

function evidenceLabel(level, t) {
  if (level === "SELF_REPORTED") return t.selfReported;
  if (level === "ASSESSED") return t.assessed;
  if (level === "INDEPENDENTLY_VERIFIED") return t.independentlyVerified;
  return level || t.unknownEvidence;
}

function JobSkills({ title, skills, emptyText, t, showEvidence = false }) {
  return (
    <section className="job-skill-section">
      <h3>{title}</h3>
      {skills.length ? (
        <ul className="job-skill-list">
          {skills.map((skill, index) => {
            const name = typeof skill === "string" ? skill : skill?.skill_name;
            if (!name) return null;
            return (
              <li key={`${name}-${index}`}>
                <span>{name}</span>
                {showEvidence && skill.evidence_level && (
                  <small>{evidenceLabel(skill.evidence_level, t)}</small>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="job-muted">{emptyText}</p>
      )}
    </section>
  );
}

export default function JobRecommendationsPage({
  apiBase,
  language,
  workerId,
  onBack,
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
  const jobs = Array.isArray(data?.jobs) ? data.jobs.filter(isRecord) : [];
  const trade = t.trades[data?.trade] || data?.trade;

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
    async function loadRecommendations() {
      try {
        const response = await fetch(
          `${base}/api/workers/${workerId}/jobs`,
          { signal: controller.signal }
        );
        if (!response.ok) {
          const error = new Error("Job recommendations request failed");
          error.status = response.status;
          throw error;
        }

        const payload = await response.json();
        if (
          !isRecord(payload) ||
          payload.worker_id !== workerId ||
          typeof payload.trade !== "string" ||
          !Array.isArray(payload.jobs)
        ) {
          throw new Error("Job recommendations response has an invalid shape");
        }
        if (active) {
          setRequest({ key: requestKey, status: "success", data: payload });
        }
      } catch (error) {
        if (!active || error.name === "AbortError") return;
        setRequest({
          key: requestKey,
          status: "error",
          error: error.status === 404 ? "workerNotFound" : "loadFailed",
        });
      }
    }

    loadRecommendations();
    return () => {
      active = false;
      controller.abort();
    };
  }, [apiBase, invalidWorker, requestKey, workerId]);

  return (
    <section className="jobs-page" aria-labelledby="jobs-title" lang={language}>
      <button type="button" className="back-link jobs-back" onClick={onBack}>
        ← {t.back}
      </button>

      <header className="jobs-heading">
        <span className="section-kicker">YOGYA · {t.title}</span>
        <h1 id="jobs-title">{t.title}</h1>
        <p>{t.intro}</p>
        {trade && <span className="jobs-trade">{trade}</span>}
      </header>

      {requestStatus === "loading" && (
        <div className="status-message jobs-status" role="status" aria-live="polite">
          <span className="loading-spinner" />
          {t.loading}
        </div>
      )}

      {requestStatus === "error" && (
        <div className="status-message warning-message jobs-status" role="alert">
          <p>{t[requestError] || t.loadFailed}</p>
          {requestError !== "invalidWorker" && (
            <button
              type="button"
              className="jobs-retry"
              onClick={() => setAttempt((value) => value + 1)}
            >
              {t.retry}
            </button>
          )}
        </div>
      )}

      {requestStatus === "success" && (
        <>
          {data.demo === true && (
            <div className="jobs-demo-notice" role="note">{t.demoNotice}</div>
          )}
          {jobs.length ? (
            <div className="jobs-list">
              {jobs.map((job) => (
                <article className="job-card" key={job.job_id}>
                  <header className="job-card-header">
                    <div>
                      <span className="job-id">{t.jobId}: {job.job_id}</span>
                      <h2>{job.job_title}</h2>
                      <p>{job.employer_name}</p>
                    </div>
                    <div className="job-match">
                      <strong>
                        {typeof job.match_percentage === "number"
                          ? `${job.match_percentage}%`
                          : "—"}
                      </strong>
                      <span>{t.match}</span>
                    </div>
                  </header>

                  {job.description && (
                    <p className="job-description">{job.description}</p>
                  )}

                  <div className="job-details">
                    <div><span>{t.location}</span><strong>{job.location || "—"}</strong></div>
                    <div><span>{t.jobType}</span><strong>{job.job_type || "—"}</strong></div>
                    <div>
                      <span>{t.salaryRange}</span>
                      <strong>
                        {job.salary_min ?? "—"} – {job.salary_max ?? "—"}
                      </strong>
                    </div>
                  </div>

                  <div className="job-skills-grid">
                    <JobSkills
                      title={t.matchedSkills}
                      skills={Array.isArray(job.matched_skills) ? job.matched_skills : []}
                      emptyText={t.noMatchedSkills}
                      t={t}
                      showEvidence
                    />
                    <JobSkills
                      title={t.missingSkills}
                      skills={Array.isArray(job.missing_skills) ? job.missing_skills : []}
                      emptyText={t.noMissingSkills}
                      t={t}
                    />
                    <JobSkills
                      title={t.preferredSkills}
                      skills={Array.isArray(job.preferred_skills) ? job.preferred_skills : []}
                      emptyText={t.noPreferredSkills}
                      t={t}
                    />
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="jobs-empty">
              <h2>{t.noJobs}</h2>
            </div>
          )}
        </>
      )}

      <div className="jobs-page-actions">
        <button type="button" className="as-button-secondary" onClick={onBack}>
          ← {t.back}
        </button>
      </div>
    </section>
  );
}
