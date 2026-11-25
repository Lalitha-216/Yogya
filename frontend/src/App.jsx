
import { useEffect, useRef, useState } from "react";
import "./App.css";
import AssessmentFlow from "./assessment/AssessmentFlow";
import { ASSESSMENT_COPY } from "./assessment/copy";
import DemoProfilePanel from "./dev/DemoProfilePanel";
import { buildDemoProfile, DEMO_COPY } from "./dev/demoProfile";
import SkillPassportPage from "./passport/SkillPassportPage";
import JobRecommendationsPage from "./jobs/JobRecommendationsPage";
import {
  VoiceCompanionControls,
  VoiceCompanionProvider,
  useVoiceCompanion,
} from "./voice/VoiceCompanion";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const EXT_BY_MIME = {
  "audio/webm": "webm",
  "audio/ogg": "ogg",
  "audio/mp4": "m4a",
  "audio/m4a": "m4a",
  "audio/mpeg": "mp3",
  "audio/mp3": "mp3",
  "audio/aiff": "aiff",
  "audio/aac": "aac",
  "audio/flac": "flac",
  "audio/opus": "opus",
  "audio/wav": "wav",
  "audio/l16": "pcm",
  "audio/alaw": "alaw",
  "audio/mulaw": "mulaw",
};

const MIME_ALIASES = {
  "audio/x-wav": "audio/wav",
  "audio/wave": "audio/wav",
  "audio/x-m4a": "audio/m4a",
  "audio/x-aac": "audio/aac",
};

const COPY = {
  en: {
    chooseLanguage: "Choose language",
    howItWorks: "How it works",
    whyYogya: "Why Yogya",
    getStarted: "Get started",
    listenInstructions: "Listen to instructions",
    landingIntroduction: "Welcome to Yogya. Tell us what work you know. Yogya will help identify and assess your skills. Press Start to begin.",
    onboardingVoiceGuide: "Welcome to your Yogya profile setup. Enter your name and, if you want, your location. Choose Electrician for wiring, repairs, or installations, or Plumber for pipes, fittings, or maintenance. Then tell us about your work, tasks, tools, and experience. To record, press Start recording, speak, then press Stop recording. You can also type or upload audio.",
    resultVoiceGuide: "Yogya has identified the skills you described. Review them here. They are self-reported and have not yet been assessed. Next, you can take the assessment or open your Skill Passport.",
    resultVoiceGuideNoSkills: "Yogya has prepared your profile, but could not identify specific skills from your description yet. Review the guidance here. You can add more detail by creating another profile or continue to the assessment.",
    eyebrow: "SKILLS DESERVE RECOGNITION",
    heroLine1: "Your skills matter.",
    heroLine2: "Your story deserves",
    heroLine3: "to be heard.",
    heroDescription: "No certificates? No formal resume? No problem. Tell us about the work you do. Yogya helps turn your experience into a skill profile employers can understand.",
    startJourney: "Start your journey",
    seeHow: "See how it works",
    trustLanguages: "Telugu & English",
    voiceFirst: "Voice-first",
    noResume: "No resume needed",
    yourSkillsStory: "YOUR SKILLS, YOUR STORY",
    experienceSkill: "Experience is a skill.",
    makeVisible: "Let's make it visible.",
    speakLanguage: "Speak in your language",
    skillPassport: "Skill Passport",
    workRecognised: "Your work, recognised",
    simpleDesign: "SIMPLE BY DESIGN",
    howHeading: "Three steps to make your skills visible.",
    howDescription: "No complicated forms. No lengthy resumes. Just your experience.",
    tellStory: "Tell your story",
    tellStoryDescription: "Speak or type about your work in Telugu or English.",
    showKnowledge: "Show what you know",
    showKnowledgeDescription: "Complete a simple trade-based knowledge assessment.",
    exploreJobs: "Explore opportunities",
    exploreJobsDescription: "Build your Skill Passport and discover relevant jobs.",
    fairerWay: "A FAIRER WAY TO BE SEEN",
    fairerHeading: "Because ability isn't measured by paperwork.",
    fairerDescription: "Yogya helps workers communicate their experience and gives employers clearer evidence to evaluate. A skill claim, an assessment and an independent verification are kept distinct — because trust matters.",
    nextStep: "YOUR NEXT STEP STARTS HERE",
    nextStepHeading: "Your experience has value. Let's show it.",
    createProfile: "Create your skill profile",
    backHome: "Back to home",
    getToKnowYou: "LET'S GET TO KNOW YOU",
    startStory: "Start with your story.",
    aboutYourself: "Tell us a little about yourself and the work you do. You can speak or type. It's your choice.",
    stepProgress: "STEP 1 OF 3 · WORKER PROFILE",
    aboutYou: "01 — ABOUT YOU",
    yourDetails: "Your details",
    requiredFields: "* Required fields",
    yourName: "Your name *",
    enterName: "Enter your name",
    yourLocation: "Your location",
    cityTown: "City or town",
    yourWork: "02 — YOUR WORK",
    workType: "What kind of work do you do?",
    chooseTrade: "Choose the trade that best describes your experience.",
    electrician: "Electrician",
    electricianDetails: "Wiring, repairs, installations",
    plumber: "Plumber",
    plumberDetails: "Pipes, fittings, maintenance",
    yourExperience: "03 — YOUR EXPERIENCE",
    workExperiencePrompt: "Tell us about your work.",
    experienceGuidance: "Mention the tasks you do, tools you use and years of experience. Speak naturally.",
    shareExperience: "Share your experience",
    voiceOrType: "Choose voice recording or type your answer.",
    english: "English",
    startRecording: "Start recording",
    stopRecording: "Stop recording",
    or: "OR",
    uploadAudio: "Upload audio",
    recordingInProgress: "Recording in progress. Select stop when you're finished.",
    transcriptLabel: "Transcript / Work experience *",
    teluguPlaceholder: "మీరు చేసే పనులు, మీ అనుభవం గురించి చెప్పండి...",
    englishPlaceholder: "Describe your work, the tasks you do and how long you have done them...",
    transcriptPrivacy: "Your transcript can be reviewed and edited before your profile is generated.",
    requiredFooter: "Fields marked * are required.",
    creatingProfile: "Creating profile...",
    generateProfile: "Generate my skill profile",
    profileCreated: "PROFILE CREATED",
    experienceTakingShape: "Your experience is taking shape.",
    profileSaved: "Your profile has been saved. Review the extracted information below.",
    ruleBasedFallback: "Rule-based fallback used because Gemini was temporarily unavailable.",
    fallbackNoSkills: "Your profile was saved, but no specific skills could be identified from this transcript. Add more detail to your work description to help identify skills.",
    yogyaProfile: "YOGYA SKILL PROFILE",
    locationNotProvided: "Location not provided",
    selfReported: "SELF-REPORTED",
    trade: "Trade",
    experience: "Experience",
    years: "years",
    experienceUnknown: "Not specified",
    workerId: "Worker ID",
    tradeMismatch: "Your description sounds more like {trade} work. Your selected trade was saved.",
    skillsIdentified: "Skills identified",
    noSkills: "No skills were identified. You can update your description and try again.",
    selfReportedSkills: "Self-reported",
    openPassport: "View Skill Passport",
    evidenceDisclaimer: "These skills are currently self-reported. They have not yet been assessed or independently verified.",
    createAnother: "Create another profile",
    footerTagline: "Skills deserve recognition.",
    madeForWorkers: "Made for every worker.",
    transcribing: "Transcribing your voice...",
    transcriptReady: "Transcript ready. Review or edit it before continuing.",
    transcriptionFailed: "Transcription failed",
    typeInstead: "You can type your experience instead.",
    profileRequired: "Please record, upload or type your work experience first.",
    profileCreating: "Creating your skill profile...",
    microphoneUnsupported: "Microphone recording is not supported in this browser. You can upload audio or type your experience.",
    microphoneDenied: "Microphone access was denied. Allow microphone access or type your experience.",
    microphoneMissing: "No microphone was found. Connect a microphone, upload audio or type your experience.",
    microphoneBusy: "The microphone is unavailable or already in use. Try again or type your experience.",
    unsupportedRecording: "This audio format is not supported. Record again or upload WAV, MP3, M4A, OGG, AAC, AIFF, FLAC or WebM audio.",
    emptyRecording: "No audio was captured. Please record again.",
    microphoneError: "Microphone unavailable. Allow microphone access or type your experience.",
    missingApiKey: "Voice transcription is unavailable because the server is missing its Gemini API key.",
    missingSarvamApiKey: "Voice transcription is unavailable because the server is missing its Sarvam API key.",
    noSpeech: "No speech was detected. Please record again.",
    audioTooLarge: "The audio file is too large (maximum 15 MB). Record a shorter clip or upload a smaller file.",
    audioDurationTooLong: "This recording is longer than Sarvam's 30-second limit. Record or upload audio that is 30 seconds or shorter.",
    providerRateLimit: "The transcription service is busy. Please wait a moment and try again.",
    providerQuotaExceeded: "Sarvam transcription credits or quota are exhausted. Please contact the app administrator.",
    providerRejected: "The transcription service rejected this audio or its model configuration. Try a supported audio format or contact the app administrator.",
    modelUnavailable: "The configured Gemini model is unavailable. Check GEMINI_MODEL and model access.",
    providerUnavailable: "The transcription service is temporarily unavailable. Please try again later.",
    cannotReachBackend: "Cannot reach the backend at {url}. Check that FastAPI is running.",
    profileFailed: "Profile extraction failed",
    noSkillsFound: "No skills could be identified. Please describe your work in a bit more detail.",
    genericRequestFailed: "The request could not be completed. Please try again.",
  },
  te: {
    chooseLanguage: "భాషను ఎంచుకోండి",
    howItWorks: "ఇది ఎలా పనిచేస్తుంది",
    whyYogya: "యోగ్యత ఎందుకు",
    getStarted: "ప్రారంభించండి",
    listenInstructions: "సూచనలు వినండి",
    landingIntroduction: "యోగ్యకు స్వాగతం. మీకు తెలిసిన పనిని యోగ్యకు చెప్పండి. మీ నైపుణ్యాలను గుర్తించి, అంచనా వేయడానికి యోగ్య సహాయపడుతుంది. ప్రారంభించడానికి ప్రారంభించండి నొక్కండి.",
    onboardingVoiceGuide: "యోగ్యలో మీ ప్రొఫైల్ ప్రారంభిద్దాం. మీ పేరు నమోదు చేయండి. ప్రాంతం ఇవ్వడం ఐచ్ఛికం. వైరింగ్, మరమ్మతులు లేదా అమరికల పనికి ఎలక్ట్రీషియన్‌ను ఎంచుకోండి. పైపులు, ఫిట్టింగ్‌లు లేదా నిర్వహణ పనికి ప్లంబర్‌ను ఎంచుకోండి. మీ పని, చేసే పనులు, పనిముట్లు, అనుభవం గురించి చెప్పండి. రికార్డ్ చేయడానికి 'రికార్డింగ్ ప్రారంభించండి' నొక్కి మాట్లాడండి. పూర్తయ్యాక 'రికార్డింగ్ ఆపండి' నొక్కండి. టైప్ చేయవచ్చు లేదా ఆడియో అప్‌లోడ్ చేయవచ్చు.",
    resultVoiceGuide: "మీరు తెలిపిన నైపుణ్యాలను యోగ్య గుర్తించింది. వాటిని ఇక్కడ పరిశీలించండి. ఇవి మీరు తెలిపిన వివరాలు; ఇంకా అంచనా వేయలేదు. తర్వాత నైపుణ్య అంచనా వేయించుకోవచ్చు లేదా మీ నైపుణ్య పాస్‌పోర్ట్‌ను తెరవవచ్చు.",
    resultVoiceGuideNoSkills: "యోగ్య మీ ప్రొఫైల్‌ను సిద్ధం చేసింది, కానీ మీ వివరణలో నిర్దిష్ట నైపుణ్యాలను గుర్తించలేకపోయింది. ఇక్కడి సూచనలను పరిశీలించండి. మరిన్ని వివరాలతో మరో ప్రొఫైల్ రూపొందించవచ్చు లేదా అంచనాకు వెళ్లవచ్చు.",
    eyebrow: "నైపుణ్యాలకు గుర్తింపు అవసరం",
    heroLine1: "మీ నైపుణ్యాలు ముఖ్యం.",
    heroLine2: "మీ కథ వినిపించాలి.",
    heroLine3: "",
    heroDescription: "సర్టిఫికెట్లు లేవా? అధికారిక రెజ్యూమ్ లేదా? పరవాలేదు. మీరు చేసే పని గురించి మాకు చెప్పండి. యోగ్య మీ అనుభవాన్ని యజమానులు అర్థం చేసుకునే నైపుణ్య ప్రొఫైల్‌గా రూపొందిస్తుంది.",
    startJourney: "మీ ప్రయాణాన్ని ప్రారంభించండి",
    seeHow: "ఇది ఎలా పనిచేస్తుందో చూడండి",
    trustLanguages: "తెలుగు & ఇంగ్లీష్",
    voiceFirst: "వాయిస్ ద్వారా",
    noResume: "రెజ్యూమ్ అవసరం లేదు",
    yourSkillsStory: "మీ నైపుణ్యాలు, మీ కథ",
    experienceSkill: "అనుభవం కూడా ఒక నైపుణ్యమే.",
    makeVisible: "దాన్ని అందరికీ తెలియజేద్దాం.",
    speakLanguage: "మీ భాషలో మాట్లాడండి",
    skillPassport: "నైపుణ్య పాస్‌పోర్ట్",
    workRecognised: "మీ పనికి గుర్తింపు",
    simpleDesign: "సులభంగా రూపొందించబడింది",
    howHeading: "మీ నైపుణ్యాలను తెలియజేయడానికి మూడు దశలు.",
    howDescription: "క్లిష్టమైన ఫారమ్‌లు లేవు. పెద్ద రెజ్యూమ్‌లు లేవు. మీ అనుభవం చాలు.",
    tellStory: "మీ కథ చెప్పండి",
    tellStoryDescription: "మీ పని గురించి తెలుగులో లేదా ఇంగ్లీష్‌లో మాట్లాడండి లేదా టైప్ చేయండి.",
    showKnowledge: "మీకు తెలిసిన పనిని చూపండి",
    showKnowledgeDescription: "మీ వృత్తికి సంబంధించిన సులభమైన నైపుణ్య అంచనాను పూర్తి చేయండి.",
    exploreJobs: "ఉద్యోగ అవకాశాలను చూడండి",
    exploreJobsDescription: "మీ నైపుణ్య పాస్‌పోర్ట్‌ను రూపొందించి తగిన ఉద్యోగాలను కనుగొనండి.",
    fairerWay: "మీ ప్రతిభకు న్యాయమైన గుర్తింపు",
    fairerHeading: "సామర్థ్యాన్ని పత్రాలతో మాత్రమే కొలవలేం.",
    fairerDescription: "కార్మికులు తమ అనుభవాన్ని తెలియజేయడానికి యోగ్య సహాయపడుతుంది. యజమానులు స్పష్టమైన వివరాలతో అంచనా వేయగలరు. నైపుణ్య వివరాలు, అంచనా, స్వతంత్ర ధృవీకరణ వేర్వేరుగా ఉంటాయి — నమ్మకం ముఖ్యం కాబట్టి.",
    nextStep: "మీ తదుపరి అడుగు ఇక్కడే",
    nextStepHeading: "మీ అనుభవానికి విలువ ఉంది. దాన్ని తెలియజేద్దాం.",
    createProfile: "నైపుణ్య ప్రొఫైల్ రూపొందించండి",
    backHome: "ప్రధాన పేజీకి తిరిగి వెళ్లండి",
    getToKnowYou: "మీ గురించి తెలుసుకుందాం",
    startStory: "మీ కథతో ప్రారంభించండి.",
    aboutYourself: "మీ గురించి, మీరు చేసే పని గురించి కొంచెం చెప్పండి. మాట్లాడవచ్చు లేదా టైప్ చేయవచ్చు. మీ ఇష్టం.",
    stepProgress: "దశ 1 / 3 · కార్మికుడి ప్రొఫైల్",
    aboutYou: "01 — మీ గురించి",
    yourDetails: "మీ వివరాలు",
    requiredFields: "* తప్పనిసరి వివరాలు",
    yourName: "మీ పేరు *",
    enterName: "మీ పేరు నమోదు చేయండి",
    yourLocation: "మీ ప్రాంతం",
    cityTown: "నగరం లేదా పట్టణం",
    yourWork: "02 — మీ పని",
    workType: "మీరు ఏ పని చేస్తారు?",
    chooseTrade: "మీ అనుభవానికి సరిపోయే వృత్తిని ఎంచుకోండి.",
    electrician: "ఎలక్ట్రీషియన్",
    electricianDetails: "వైరింగ్, మరమ్మతులు, అమరికలు",
    plumber: "ప్లంబర్",
    plumberDetails: "పైపులు, ఫిట్టింగ్‌లు, నిర్వహణ",
    yourExperience: "03 — మీ అనుభవం",
    workExperiencePrompt: "మీ పని గురించి చెప్పండి.",
    experienceGuidance: "మీరు చేసే పనులు, ఉపయోగించే పనిముట్లు, అనుభవ సంవత్సరాల గురించి చెప్పండి. సహజంగా మాట్లాడండి.",
    shareExperience: "మీ అనుభవాన్ని పంచుకోండి",
    voiceOrType: "మాట్లాడి రికార్డ్ చేయండి లేదా టైప్ చేయండి.",
    english: "ఇంగ్లీష్",
    startRecording: "రికార్డింగ్ ప్రారంభించండి",
    stopRecording: "రికార్డింగ్ ఆపండి",
    or: "లేదా",
    uploadAudio: "ఆడియో అప్‌లోడ్ చేయండి",
    recordingInProgress: "రికార్డింగ్ జరుగుతోంది. పూర్తయ్యాక ఆపు ఎంచుకోండి.",
    transcriptLabel: "ట్రాన్స్‌క్రిప్ట్ / పని అనుభవం *",
    teluguPlaceholder: "మీరు చేసే పనులు, మీ అనుభవం గురించి చెప్పండి...",
    englishPlaceholder: "మీ పని, మీరు చేసే పనులు, ఎంతకాలంగా చేస్తున్నారో వివరించండి...",
    transcriptPrivacy: "ప్రొఫైల్ రూపొందించే ముందు మీ ట్రాన్స్‌క్రిప్ట్‌ను పరిశీలించి సవరించవచ్చు.",
    requiredFooter: "* గుర్తు ఉన్న వివరాలు తప్పనిసరి.",
    creatingProfile: "ప్రొఫైల్ రూపొందిస్తోంది...",
    generateProfile: "నా నైపుణ్య ప్రొఫైల్ రూపొందించండి",
    profileCreated: "ప్రొఫైల్ రూపొందించబడింది",
    experienceTakingShape: "మీ అనుభవంతో ప్రొఫైల్ సిద్ధమవుతోంది.",
    profileSaved: "మీ ప్రొఫైల్ భద్రపరచబడింది. దిగువ వివరాలను పరిశీలించండి.",
    ruleBasedFallback: "Gemini తాత్కాలికంగా అందుబాటులో లేకపోవడంతో నియమాల ఆధారిత పద్ధతిని ఉపయోగించాం.",
    fallbackNoSkills: "మీ ప్రొఫైల్ భద్రపరచబడింది. ఈ వివరణలోంచి నిర్దిష్ట నైపుణ్యాలను గుర్తించలేకపోయాం. నైపుణ్యాలను గుర్తించేందుకు మీ పని గురించి మరింత వివరించండి.",
    yogyaProfile: "యోగ్య నైపుణ్య ప్రొఫైల్",
    locationNotProvided: "ప్రాంతం ఇవ్వలేదు",
    selfReported: "స్వయంగా తెలిపినవి",
    trade: "వృత్తి",
    experience: "అనుభవం",
    years: "సంవత్సరాలు",
    experienceUnknown: "పేర్కొనలేదు",
    workerId: "కార్మికుడి ఐడీ",
    tradeMismatch: "మీ వివరణ {trade} పనికి దగ్గరగా ఉంది. మీరు ఎంచుకున్న వృత్తినే భద్రపరిచాం.",
    skillsIdentified: "గుర్తించిన నైపుణ్యాలు",
    noSkills: "నైపుణ్యాలు గుర్తించబడలేదు. మీ వివరణను మార్చి మళ్లీ ప్రయత్నించండి.",
    selfReportedSkills: "స్వయంగా తెలిపినవి",
    openPassport: "నైపుణ్య పాస్‌పోర్ట్ చూడండి",
    evidenceDisclaimer: "ఈ నైపుణ్యాలను మీరు స్వయంగా తెలిపారు. వీటిని ఇంకా అంచనా వేయలేదు లేదా స్వతంత్రంగా ధృవీకరించలేదు.",
    createAnother: "మరో ప్రొఫైల్ రూపొందించండి",
    footerTagline: "నైపుణ్యాలకు గుర్తింపు అవసరం.",
    madeForWorkers: "ప్రతి కార్మికుడి కోసం.",
    transcribing: "మీ మాటలను టెక్స్ట్‌గా మారుస్తోంది...",
    transcriptReady: "ట్రాన్స్‌క్రిప్ట్ సిద్ధంగా ఉంది. కొనసాగించే ముందు పరిశీలించండి లేదా సవరించండి.",
    transcriptionFailed: "ట్రాన్స్‌క్రిప్షన్ విఫలమైంది",
    typeInstead: "బదులుగా మీ పని అనుభవాన్ని టైప్ చేయవచ్చు.",
    profileRequired: "ముందుగా మీ పని అనుభవాన్ని రికార్డ్ చేయండి, అప్‌లోడ్ చేయండి లేదా టైప్ చేయండి.",
    profileCreating: "మీ నైపుణ్య ప్రొఫైల్ రూపొందిస్తోంది...",
    microphoneUnsupported: "ఈ బ్రౌజర్‌లో మైక్రోఫోన్ రికార్డింగ్‌కు మద్దతు లేదు. ఆడియో అప్‌లోడ్ చేయండి లేదా మీ అనుభవాన్ని టైప్ చేయండి.",
    microphoneDenied: "మైక్రోఫోన్ అనుమతి నిరాకరించబడింది. అనుమతి ఇవ్వండి లేదా మీ అనుభవాన్ని టైప్ చేయండి.",
    microphoneMissing: "మైక్రోఫోన్ కనబడలేదు. మైక్రోఫోన్‌ను కనెక్ట్ చేయండి, ఆడియో అప్‌లోడ్ చేయండి లేదా అనుభవాన్ని టైప్ చేయండి.",
    microphoneBusy: "మైక్రోఫోన్ అందుబాటులో లేదు లేదా ఇప్పటికే ఉపయోగంలో ఉంది. మళ్లీ ప్రయత్నించండి లేదా అనుభవాన్ని టైప్ చేయండి.",
    unsupportedRecording: "ఈ ఆడియో ఫార్మాట్‌కు మద్దతు లేదు. మళ్లీ రికార్డ్ చేయండి లేదా WAV, MP3, M4A, OGG, AAC, AIFF, FLAC లేదా WebM ఆడియో అప్‌లోడ్ చేయండి.",
    emptyRecording: "ఆడియో రికార్డ్ కాలేదు. దయచేసి మళ్లీ రికార్డ్ చేయండి.",
    microphoneError: "మైక్రోఫోన్ అందుబాటులో లేదు. అనుమతి ఇవ్వండి లేదా మీ అనుభవాన్ని టైప్ చేయండి.",
    missingApiKey: "సర్వర్‌లో Gemini API కీ లేకపోవడంతో వాయిస్ ట్రాన్స్‌క్రిప్షన్ అందుబాటులో లేదు.",
    missingSarvamApiKey: "సర్వర్‌లో Sarvam API కీ లేకపోవడంతో వాయిస్ ట్రాన్స్‌క్రిప్షన్ అందుబాటులో లేదు.",
    noSpeech: "మాటలు గుర్తించబడలేదు. మళ్లీ రికార్డ్ చేయండి.",
    audioTooLarge: "ఆడియో ఫైల్ చాలా పెద్దది (గరిష్ఠం 15 MB). చిన్న రికార్డింగ్ చేయండి లేదా చిన్న ఫైల్ అప్‌లోడ్ చేయండి.",
    audioDurationTooLong: "ఈ రికార్డింగ్ Sarvam 30 సెకన్ల పరిమితిని మించింది. 30 సెకన్లు లేదా అంతకంటే తక్కువ ఆడియోను రికార్డ్ చేయండి లేదా అప్‌లోడ్ చేయండి.",
    providerRateLimit: "ట్రాన్స్‌క్రిప్షన్ సేవ ప్రస్తుతం బిజీగా ఉంది. కొద్దిసేపటి తర్వాత మళ్లీ ప్రయత్నించండి.",
    providerQuotaExceeded: "Sarvam ట్రాన్స్‌క్రిప్షన్ క్రెడిట్‌లు లేదా కోటా అయిపోయాయి. యాప్ నిర్వాహకుడిని సంప్రదించండి.",
    providerRejected: "ఈ ఆడియో లేదా మోడల్ సెట్టింగ్‌ను ట్రాన్స్‌క్రిప్షన్ సేవ అంగీకరించలేదు. మద్దతున్న ఆడియో ఫార్మాట్ ప్రయత్నించండి లేదా నిర్వాహకుడిని సంప్రదించండి.",
    modelUnavailable: "సర్వర్‌లో సెటప్ చేసిన Gemini మోడల్ అందుబాటులో లేదు. GEMINI_MODEL మరియు మోడల్ యాక్సెస్‌ను తనిఖీ చేయండి.",
    providerUnavailable: "ట్రాన్స్‌క్రిప్షన్ సేవ తాత్కాలికంగా అందుబాటులో లేదు. తర్వాత మళ్లీ ప్రయత్నించండి.",
    cannotReachBackend: "బ్యాకెండ్‌ను {url} వద్ద సంప్రదించలేకపోయాం. FastAPI నడుస్తోందో చూడండి.",
    profileFailed: "ప్రొఫైల్ వివరాలను వెలికితీయడం విఫలమైంది",
    noSkillsFound: "నైపుణ్యాలు గుర్తించబడలేదు. మీ పని గురించి మరికొంత వివరంగా చెప్పండి.",
    genericRequestFailed: "అభ్యర్థన పూర్తి కాలేదు. దయచేసి మళ్లీ ప్రయత్నించండి.",
  },
  hi: {
    chooseLanguage: "भाषा चुनें",
    howItWorks: "यह कैसे काम करता है",
    whyYogya: "योग्या क्यों",
    getStarted: "शुरू करें",
    listenInstructions: "निर्देश सुनें",
    landingIntroduction: "योग्या में आपका स्वागत है। आप जो काम जानते हैं, उसके बारे में योग्या को बताएँ। योग्या आपके कौशल पहचानने और उनका आकलन करने में मदद करेगा। शुरू करने के लिए शुरू करें दबाएँ।",
    onboardingVoiceGuide: "योग्या में आपकी प्रोफ़ाइल शुरू करते हैं। अपना नाम लिखें; स्थान देना वैकल्पिक है। वायरिंग, मरम्मत या इंस्टॉलेशन के काम के लिए इलेक्ट्रीशियन चुनें। पाइप, फिटिंग या रखरखाव के काम के लिए प्लंबर चुनें। अपने काम, किए जाने वाले कामों, औज़ारों और अनुभव के बारे में बताएँ। रिकॉर्ड करने के लिए 'रिकॉर्डिंग शुरू करें' दबाएँ, बोलें, फिर 'रिकॉर्डिंग रोकें' दबाएँ। आप टाइप भी कर सकते हैं या ऑडियो अपलोड कर सकते हैं।",
    resultVoiceGuide: "योग्या ने आपके बताए कौशल पहचान लिए हैं। उन्हें यहाँ देखें। ये आपके बताए हुए कौशल हैं; इनका अभी आकलन नहीं हुआ है। आगे आप आकलन करवा सकते हैं या अपना कौशल पासपोर्ट खोल सकते हैं।",
    resultVoiceGuideNoSkills: "योग्या ने आपकी प्रोफ़ाइल तैयार की है, लेकिन अभी आपके विवरण से कोई विशेष कौशल नहीं पहचान पाया। यहाँ दी गई जानकारी देखें। आप अधिक विवरण के साथ दूसरी प्रोफ़ाइल बना सकते हैं या आकलन जारी रख सकते हैं।",
    eyebrow: "कौशल को पहचान मिलनी चाहिए",
    heroLine1: "आपके कौशल मायने रखते हैं।",
    heroLine2: "आपकी कहानी सुनी",
    heroLine3: "जानी चाहिए।",
    heroDescription: "प्रमाणपत्र नहीं हैं? औपचारिक रिज़्यूमे नहीं है? कोई बात नहीं। आप जो काम करते हैं, उसके बारे में बताइए। योग्या आपके अनुभव को ऐसी कौशल प्रोफ़ाइल में बदलने में मदद करता है जिसे नियोक्ता समझ सकें।",
    startJourney: "अपनी यात्रा शुरू करें",
    seeHow: "जानें यह कैसे काम करता है",
    trustLanguages: "तेलुगु, अंग्रेज़ी और हिन्दी",
    voiceFirst: "आवाज़ से आसान",
    noResume: "रिज़्यूमे की ज़रूरत नहीं",
    yourSkillsStory: "आपके कौशल, आपकी कहानी",
    experienceSkill: "अनुभव भी एक कौशल है।",
    makeVisible: "आइए, इसे सबके सामने लाएँ।",
    speakLanguage: "अपनी भाषा में बताइए",
    skillPassport: "कौशल पासपोर्ट",
    workRecognised: "आपके काम को पहचान",
    simpleDesign: "सादगी के लिए बनाया गया",
    howHeading: "अपने कौशल सामने लाने के तीन आसान चरण।",
    howDescription: "न मुश्किल फ़ॉर्म, न लंबे रिज़्यूमे। बस आपका अनुभव।",
    tellStory: "अपनी कहानी बताइए",
    tellStoryDescription: "तेलुगु या अंग्रेज़ी में बोलें, या हिन्दी में अपना अनुभव लिखें।",
    showKnowledge: "अपना हुनर दिखाइए",
    showKnowledgeDescription: "अपने काम से जुड़ी एक सरल कौशल जाँच पूरी करें।",
    exploreJobs: "काम के अवसर खोजें",
    exploreJobsDescription: "अपना कौशल पासपोर्ट बनाएँ और अपने लिए उपयुक्त काम खोजें।",
    fairerWay: "पहचान पाने का अधिक निष्पक्ष तरीका",
    fairerHeading: "काबिलियत का पैमाना सिर्फ़ कागज़ात नहीं हैं।",
    fairerDescription: "योग्या कामगारों को अपना अनुभव बताने में मदद करता है और नियोक्ताओं को उसका बेहतर आकलन करने के लिए स्पष्ट जानकारी देता है। बताए गए कौशल, कौशल जाँच और स्वतंत्र सत्यापन को अलग-अलग रखा जाता है — क्योंकि भरोसा मायने रखता है।",
    nextStep: "आपका अगला कदम यहाँ से शुरू होता है",
    nextStepHeading: "आपके अनुभव की अहमियत है। आइए, इसे सामने लाएँ।",
    createProfile: "अपनी कौशल प्रोफ़ाइल बनाएँ",
    backHome: "मुख्य पृष्ठ पर लौटें",
    getToKnowYou: "आइए, आपके बारे में जानें",
    startStory: "अपनी कहानी से शुरुआत करें।",
    aboutYourself: "अपने और अपने काम के बारे में थोड़ा बताइए। आप बोल सकते हैं या लिख सकते हैं—जैसा आपको ठीक लगे।",
    stepProgress: "चरण 1 / 3 · कामगार प्रोफ़ाइल",
    aboutYou: "01 — आपके बारे में",
    yourDetails: "आपकी जानकारी",
    requiredFields: "* ज़रूरी जानकारी",
    yourName: "आपका नाम *",
    enterName: "अपना नाम लिखें",
    yourLocation: "आपका स्थान",
    cityTown: "शहर या कस्बा",
    yourWork: "02 — आपका काम",
    workType: "आप किस तरह का काम करते हैं?",
    chooseTrade: "वह काम चुनें जो आपके अनुभव से सबसे अधिक मेल खाता हो।",
    electrician: "इलेक्ट्रीशियन",
    electricianDetails: "वायरिंग, मरम्मत और फिटिंग",
    plumber: "प्लंबर",
    plumberDetails: "पाइप, फिटिंग और रखरखाव",
    yourExperience: "03 — आपका अनुभव",
    workExperiencePrompt: "अपने काम के बारे में बताइए।",
    experienceGuidance: "आप कौन-से काम करते हैं, कौन-से औज़ार इस्तेमाल करते हैं और आपको कितने साल का अनुभव है—यह बताइए। तेलुगु या अंग्रेज़ी में बोलें, या लिखें।",
    shareExperience: "अपना अनुभव साझा करें",
    voiceOrType: "तेलुगु या अंग्रेज़ी में बोलकर रिकॉर्ड करें, या हिन्दी में अपना जवाब लिखें।",
    english: "अंग्रेज़ी",
    hindi: "हिन्दी",
    hindiPlaceholder: "अपने काम, किए जाने वाले कार्यों और अनुभव की अवधि के बारे में बताएँ...",
    startRecording: "रिकॉर्डिंग शुरू करें",
    stopRecording: "रिकॉर्डिंग रोकें",
    or: "या",
    uploadAudio: "ऑडियो अपलोड करें",
    recordingInProgress: "रिकॉर्डिंग जारी है। पूरा होने पर रोकें चुनें।",
    transcriptLabel: "लिखा हुआ विवरण / काम का अनुभव *",
    teluguPlaceholder: "अपने काम और अनुभव के बारे में बताएँ...",
    englishPlaceholder: "अपने काम, किए जाने वाले कार्यों और अनुभव की अवधि के बारे में बताएँ...",
    transcriptPrivacy: "प्रोफ़ाइल बनाने से पहले आप अपने लिखे हुए विवरण को देख और बदल सकते हैं।",
    requiredFooter: "* निशान वाले फ़ील्ड भरना ज़रूरी है।",
    creatingProfile: "प्रोफ़ाइल बनाई जा रही है...",
    generateProfile: "मेरी कौशल प्रोफ़ाइल बनाएँ",
    profileCreated: "प्रोफ़ाइल बन गई",
    experienceTakingShape: "आपके अनुभव की प्रोफ़ाइल तैयार है।",
    profileSaved: "आपकी प्रोफ़ाइल सहेज ली गई है। नीचे निकाली गई जानकारी देखें।",
    ruleBasedFallback: "Gemini के अस्थायी रूप से उपलब्ध न होने पर नियम-आधारित तरीका इस्तेमाल किया गया।",
    fallbackNoSkills: "आपकी प्रोफ़ाइल सहेज ली गई है, लेकिन इस विवरण से कोई खास कौशल नहीं पहचाना जा सका। कौशल पहचानने में मदद के लिए अपने काम के बारे में कुछ और बताएँ।",
    yogyaProfile: "योग्या कौशल प्रोफ़ाइल",
    locationNotProvided: "स्थान नहीं दिया गया",
    selfReported: "स्वयं बताई गई जानकारी",
    trade: "काम",
    experience: "अनुभव",
    years: "वर्ष",
    experienceUnknown: "नहीं बताया गया",
    workerId: "कामगार आईडी",
    tradeMismatch: "आपका विवरण {trade} के काम से ज़्यादा मेल खाता है। आपके चुने हुए काम को ही सहेजा गया है।",
    skillsIdentified: "पहचाने गए कौशल",
    noSkills: "कोई कौशल नहीं पहचाना गया। अपना विवरण बदलकर फिर कोशिश करें।",
    selfReportedSkills: "स्वयं बताए गए",
    openPassport: "कौशल पासपोर्ट देखें",
    evidenceDisclaimer: "ये कौशल अभी स्वयं बताए गए हैं। इनका अभी कौशल आकलन या स्वतंत्र सत्यापन नहीं हुआ है।",
    createAnother: "एक और प्रोफ़ाइल बनाएँ",
    footerTagline: "कौशल को पहचान मिलनी चाहिए।",
    madeForWorkers: "हर कामगार के लिए।",
    transcribing: "आपकी आवाज़ को लिखावट में बदला जा रहा है...",
    transcriptReady: "लिखा हुआ विवरण तैयार है। आगे बढ़ने से पहले इसे देखें या बदलें।",
    transcriptionFailed: "आवाज़ का ट्रांसक्रिप्शन नहीं हो पाया",
    typeInstead: "इसके बजाय अपना अनुभव लिख सकते हैं।",
    profileRequired: "पहले अपने काम का अनुभव रिकॉर्ड करें, ऑडियो अपलोड करें या लिखें।",
    profileCreating: "आपकी कौशल प्रोफ़ाइल बनाई जा रही है...",
    microphoneUnsupported: "इस ब्राउज़र में माइक्रोफ़ोन रिकॉर्डिंग उपलब्ध नहीं है। ऑडियो अपलोड करें या अपना अनुभव लिखें।",
    microphoneDenied: "माइक्रोफ़ोन की अनुमति नहीं मिली। अनुमति दें या अपना अनुभव लिखें।",
    microphoneMissing: "माइक्रोफ़ोन नहीं मिला। माइक्रोफ़ोन जोड़ें, ऑडियो अपलोड करें या अपना अनुभव लिखें।",
    microphoneBusy: "माइक्रोफ़ोन उपलब्ध नहीं है या पहले से इस्तेमाल हो रहा है। फिर कोशिश करें या अपना अनुभव लिखें।",
    unsupportedRecording: "यह ऑडियो फ़ॉर्मैट उपलब्ध नहीं है। फिर रिकॉर्ड करें या WAV, MP3, M4A, OGG, AAC, AIFF, FLAC या WebM ऑडियो अपलोड करें।",
    emptyRecording: "कोई ऑडियो रिकॉर्ड नहीं हुआ। कृपया फिर से रिकॉर्ड करें।",
    microphoneError: "माइक्रोफ़ोन उपलब्ध नहीं है। अनुमति दें या अपना अनुभव लिखें।",
    missingApiKey: "सर्वर पर Gemini API कुंजी नहीं है, इसलिए आवाज़ का ट्रांसक्रिप्शन उपलब्ध नहीं है।",
    missingSarvamApiKey: "सर्वर पर Sarvam API कुंजी नहीं है, इसलिए आवाज़ का ट्रांसक्रिप्शन उपलब्ध नहीं है।",
    noSpeech: "कोई बोली हुई आवाज़ नहीं मिली। कृपया फिर से रिकॉर्ड करें।",
    audioTooLarge: "ऑडियो फ़ाइल बहुत बड़ी है (अधिकतम 15 MB)। छोटी रिकॉर्डिंग करें या छोटी फ़ाइल अपलोड करें।",
    audioDurationTooLong: "यह रिकॉर्डिंग Sarvam की 30 सेकंड की सीमा से लंबी है। 30 सेकंड या उससे कम का ऑडियो रिकॉर्ड करें या अपलोड करें।",
    providerRateLimit: "ट्रांसक्रिप्शन सेवा अभी व्यस्त है। थोड़ी देर बाद फिर कोशिश करें।",
    providerQuotaExceeded: "Sarvam ट्रांसक्रिप्शन के क्रेडिट या कोटा समाप्त हो गए हैं। कृपया ऐप व्यवस्थापक से संपर्क करें।",
    providerRejected: "ट्रांसक्रिप्शन सेवा ने इस ऑडियो या मॉडल सेटिंग को स्वीकार नहीं किया। उपलब्ध ऑडियो फ़ॉर्मैट आज़माएँ या ऐप व्यवस्थापक से संपर्क करें।",
    modelUnavailable: "सेट किया गया Gemini मॉडल उपलब्ध नहीं है। GEMINI_MODEL और मॉडल की पहुँच जाँचें।",
    providerUnavailable: "ट्रांसक्रिप्शन सेवा कुछ समय के लिए उपलब्ध नहीं है। कृपया बाद में फिर कोशिश करें।",
    cannotReachBackend: "{url} पर बैकएंड से संपर्क नहीं हो पा रहा है। जाँचें कि FastAPI चल रहा है।",
    profileFailed: "प्रोफ़ाइल की जानकारी निकालना असफल रहा",
    noSkillsFound: "कोई कौशल नहीं पहचाना जा सका। कृपया अपने काम के बारे में थोड़ा और विस्तार से बताएँ।",
    genericRequestFailed: "अनुरोध पूरा नहीं हो पाया। कृपया फिर कोशिश करें।",
  },
};

function microphoneErrorMessage(error, text) {
  if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
    return text.microphoneDenied;
  }
  if (error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError") {
    return text.microphoneMissing;
  }
  if (error?.name === "NotReadableError" || error?.name === "TrackStartError") {
    return text.microphoneBusy;
  }
  return text.microphoneError;
}

function getRecordingMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  if (typeof MediaRecorder.isTypeSupported !== "function") return "";
  return [
    "audio/webm;codecs=opus",
    "audio/ogg;codecs=opus",
    "audio/mp4",
    "audio/webm",
    "audio/ogg",
  ].find((mime) => MediaRecorder.isTypeSupported(mime)) || "";
}

async function readError(res) {
  try {
    const body = await res.json();
    return { status: res.status, body };
  } catch {
    return { status: res.status, body: null };
  }
}

function translatedApiError(result, fallback, language, kind) {
  const text = COPY[language];
  const detail = typeof result.body?.detail === "string" ? result.body.detail : "";
  if (detail.includes("GEMINI_API_KEY")) return text.missingApiKey;
  if (detail.includes("SARVAM_API_KEY")) return text.missingSarvamApiKey;
  if (detail.includes("30-second REST limit")) return text.audioDurationTooLong;
  if (detail.includes("credits or quota are exhausted")) return text.providerQuotaExceeded;
  if (detail.includes("No speech was detected")) return text.noSpeech;
  if (detail.includes("Empty audio file")) return text.emptyRecording;
  if (detail.includes("Audio file is too large")) return text.audioTooLarge;
  if (detail.includes("Unsupported audio format")) return text.unsupportedRecording;
  if (detail.includes("Gemini model")) return text.modelUnavailable;
  if (detail.includes("No skills could be identified")) return text.noSkillsFound;
  if (detail.includes("Gemini rejected") || detail.includes("Sarvam rejected")) {
    return text.providerRejected;
  }
  if (detail.includes("Sarvam could not process")) return text.providerRejected;
  if (result.status === 413) return text.audioTooLarge;
  if (result.status === 415) return text.unsupportedRecording;
  if (result.status === 400 && kind === "transcription") return text.emptyRecording;
  if (result.status === 429) return text.providerRateLimit;
  if (result.status === 422 && kind === "transcription") return text.noSpeech;
  if ([502, 503, 504].includes(result.status)) return text.providerUnavailable;
  return `${fallback || text.genericRequestFailed} (HTTP ${result.status})`;
}

function formatMessage(template, values) {
  return Object.entries(values).reduce(
    (message, [key, value]) => message.replace(`{${key}}`, value),
    template
  );
}

function apiLanguage(language) {
  return language === "hi" ? "en" : language;
}

function localizedTrade(trade, text) {
  if (trade === "Electrician") return text.electrician;
  if (trade === "Plumber") return text.plumber;
  return trade;
}

function mimeFromFile(file) {
  const contentType = MIME_ALIASES[file.type?.toLowerCase()] || file.type?.toLowerCase();
  if (EXT_BY_MIME[contentType]) return contentType;
  const extension = file.name.split(".").pop()?.toLowerCase();
  return Object.entries(EXT_BY_MIME).find(([, ext]) => ext === extension)?.[0] || "";
}

function LandingIntroductionButton({ language }) {
  const voice = useVoiceCompanion();
  const text = COPY[language];
  const voiceSpeakRef = useRef(voice.speak);
  const spokenRef = useRef(false);
  const previousLanguageRef = useRef(language);

  useEffect(() => {
    voiceSpeakRef.current = voice.speak;
  }, [voice.speak]);

  useEffect(() => {
    const shouldSpeak =
      !spokenRef.current || previousLanguageRef.current !== language;
    spokenRef.current = true;
    previousLanguageRef.current = language;

    if (shouldSpeak) {
      Promise.resolve().then(() => {
        voiceSpeakRef.current(text.landingIntroduction);
      });
    }
  }, [language, text.landingIntroduction]);

  return (
    <button
      className="primary-button"
      onClick={() => voice.speak(text.landingIntroduction)}
    >
      {text.listenInstructions}
    </button>
  );
}

function OnboardingVoiceGuide({ language, instructions }) {
  const voice = useVoiceCompanion();
  const voiceSpeakRef = useRef(voice.speak);
  const previousLanguageRef = useRef(language);
  const previousInstructionsRef = useRef(null);

  useEffect(() => {
    voiceSpeakRef.current = voice.speak;
  }, [voice.speak]);

  useEffect(() => {
    const shouldSpeak =
      previousLanguageRef.current !== language ||
      previousInstructionsRef.current !== instructions;
    previousLanguageRef.current = language;
    previousInstructionsRef.current = instructions;

    if (shouldSpeak) {
      Promise.resolve().then(() => {
        voiceSpeakRef.current(instructions);
      });
    }
  }, [instructions, language]);

  return (
    <button
      type="button"
      className="voice-companion-button"
      onClick={() => voice.speak(instructions)}
    >
      {COPY[language].listenInstructions}
    </button>
  );
}

export default function App() {
  const [step, setStep] = useState("landing");
  const [language, setLanguage] = useState("te");
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [selectedTrade, setSelectedTrade] = useState("Electrician");
  const [transcript, setTranscript] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [savedResult, setSavedResult] = useState(null);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const text = COPY[language];

  const startRecording = async () => {
    setStatusMsg("");

    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
        setStatusMsg(text.microphoneUnsupported);
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredMime = getRecordingMimeType();
      if (typeof MediaRecorder.isTypeSupported === "function" && !preferredMime) {
        stream.getTracks().forEach((track) => track.stop());
        setStatusMsg(text.unsupportedRecording);
        return;
      }

      const recorder = new MediaRecorder(
        stream,
        preferredMime ? { mimeType: preferredMime } : undefined
      );
      const recordingLanguage = language;
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const mime = (recorder.mimeType || chunksRef.current[0]?.type || "")
          .split(";")[0]
          .toLowerCase();
        const normalizedMime = MIME_ALIASES[mime] || mime;
        const extension = EXT_BY_MIME[normalizedMime];
        if (!extension) {
          setStatusMsg(text.unsupportedRecording);
          return;
        }
        const blob = new Blob(chunksRef.current, { type: normalizedMime });
        if (!blob.size) {
          setStatusMsg(text.emptyRecording);
          return;
        }
        await sendAudioToBackend(blob, `recording.${extension}`, recordingLanguage);
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    } catch (error) {
      setStatusMsg(microphoneErrorMessage(error, text));
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const sendAudioToBackend = async (fileOrBlob, filename = "audio.webm", requestLanguage = language) => {
    setLoading(true);
    setStatusMsg(text.transcribing);

    try {
      const formData = new FormData();
      formData.append("audio", fileOrBlob, filename);
      formData.append("language", requestLanguage);

      const response = await fetch(`${API_BASE}/api/voice/transcribe`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const result = await readError(response);
        throw new Error(translatedApiError(result, text.transcriptionFailed, language, "transcription"));
      }

      const data = await response.json();
      setTranscript(data.transcript || "");
      setStatusMsg(text.transcriptReady);
    } catch (error) {
      const reason = error instanceof TypeError
        ? formatMessage(text.cannotReachBackend, { url: API_BASE })
        : error.message;
      setStatusMsg(`${text.transcriptionFailed}: ${reason} ${text.typeInstead}`);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files?.[0];
    if (file) {
      const mime = mimeFromFile(file);
      if (!mime) {
        setStatusMsg(text.unsupportedRecording);
      } else {
        await sendAudioToBackend(new Blob([file], { type: mime }), file.name, language);
      }
    }
    event.target.value = "";
  };

  const handleGenerateProfile = async (event) => {
    event.preventDefault();

    if (!transcript.trim()) {
      setStatusMsg(text.profileRequired);
      return;
    }

    setLoading(true);
    setStatusMsg(text.profileCreating);

    try {
      const response = await fetch(`${API_BASE}/api/profile/discover`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          language: apiLanguage(language),
          location,
          selected_trade: selectedTrade,
          transcript,
        }),
      });

      if (!response.ok) {
        const result = await readError(response);
        throw new Error(translatedApiError(result, text.profileFailed, language, "profile"));
      }

      const data = await response.json();
      setSavedResult(data);
      setStep("result");
      setStatusMsg("");
    } catch (error) {
      const offline = error instanceof TypeError;
      setStatusMsg(
        offline
          ? formatMessage(text.cannotReachBackend, { url: API_BASE })
          : error.message
      );
    } finally {
      setLoading(false);
    }
  };

  // DEVELOPMENT ONLY: fills the same state the real /api/profile/discover response
  // would, without calling the backend or Gemini. `null` in production builds.
  const handleUseDemoProfile = import.meta.env.DEV
    ? () => {
        const demo = buildDemoProfile(selectedTrade, language);
        if (!name.trim()) setName(demo.name);
        if (!location.trim()) setLocation(demo.location);
        setSavedResult(demo.result);
        setStatusMsg("");
        setStep("result");
      }
    : null;

  const resetOnboarding = () => {
    setTranscript("");
    setStatusMsg("");
    setSavedResult(null);
    setStep("onboard");
  };

  return (
    <VoiceCompanionProvider
      apiBase={API_BASE}
      language={language}
      screenKey={step}
    >
      <div className="app-shell" lang={language}>
        <header className="navbar">
        <button
          className="brand"
          disabled={step === "assessment"}
          onClick={() => setStep("landing")}
        >
          <span className="brand-mark">Y</span>
          <span>yogya<span className="brand-dot">.</span></span>
        </button>

        <nav className="nav-links">
          <a href="#how-it-works">{text.howItWorks}</a>
          <a href="#why-yogya">{text.whyYogya}</a>
        </nav>

        <div className="nav-actions">
          <div className="language-switch" aria-label={text.chooseLanguage}>
            <button
              className={language === "en" ? "active" : ""}
              onClick={() => setLanguage("en")}
              aria-pressed={language === "en"}
              disabled={loading || isRecording || step === "assessment"}
            >
              English
            </button>
            <button
              className={language === "te" ? "active" : ""}
              onClick={() => setLanguage("te")}
              aria-pressed={language === "te"}
              disabled={loading || isRecording || step === "assessment"}
            >
              తెలుగు
            </button>
            <button
              className={language === "hi" ? "active" : ""}
              onClick={() => setLanguage("hi")}
              aria-pressed={language === "hi"}
              disabled={loading || isRecording || step === "assessment"}
            >
              हिन्दी
            </button>
          </div>
          <button
            className="nav-cta"
            disabled={step === "assessment"}
            onClick={() => setStep("onboard")}
          >
            {text.getStarted} <span>→</span>
          </button>
        </div>
        </header>

        <main>
        {step === "landing" && (
          <>
            <section className="hero-section">
              <div className="hero-copy">
                <div className="eyebrow">
                  <span className="eyebrow-dot" />
                  {text.eyebrow}
                </div>

                <h1>
                  {text.heroLine1}
                  <br />
                  <span>{text.heroLine2}</span>
                  {text.heroLine3 && <><br />{text.heroLine3}</>}
                </h1>

                <p className="hero-description">{text.heroDescription}</p>

                <div className="hero-actions">
                  <button
                    className="primary-button"
                    onClick={() => setStep("onboard")}
                  >
                    {text.startJourney} <span>→</span>
                  </button>
                  <LandingIntroductionButton language={language} />
                  <a href="#how-it-works" className="text-link">
                    {text.seeHow} ↓
                  </a>
                </div>

                <div className="trust-row">
                  <span>✓ {text.trustLanguages}</span>
                  <span>✓ {text.voiceFirst}</span>
                  <span>✓ {text.noResume}</span>
                </div>
              </div>

              <div className="hero-visual">
                <div className="visual-orbit orbit-one" />
                <div className="visual-orbit orbit-two" />

                <div className="visual-card main-visual-card">
                  <div className="visual-card-top">
                    <span className="mini-brand">yogya.</span>
                    <span className="live-label">
                      <span /> {text.yourSkillsStory}
                    </span>
                  </div>

                  <div className="worker-illustration">
                    <div className="worker-head">
                      <div className="worker-hair" />
                      <div className="worker-face">
                        <span className="eye eye-left" />
                        <span className="eye eye-right" />
                        <span className="smile" />
                      </div>
                    </div>
                    <div className="worker-body">
                      <div className="worker-shirt">
                        <span className="shirt-line" />
                      </div>
                      <div className="worker-arm arm-left" />
                      <div className="worker-arm arm-right" />
                    </div>
                    <div className="worker-tool">✦</div>
                  </div>

                  <div className="visual-caption">
                    <strong>{text.experienceSkill}</strong>
                    <span>{text.makeVisible}</span>
                  </div>
                </div>

                <div className="floating-card floating-top">
                  <span className="floating-icon">✦</span>
                  <div>
                    <strong>{text.voiceFirst}</strong>
                    <small>{text.speakLanguage}</small>
                  </div>
                </div>

                <div className="floating-card floating-bottom">
                  <span className="floating-check">✓</span>
                  <div>
                    <strong>{text.skillPassport}</strong>
                    <small>{text.workRecognised}</small>
                  </div>
                </div>
              </div>
            </section>

            <section className="how-section" id="how-it-works">
              <div className="section-heading">
                <span className="section-kicker">{text.simpleDesign}</span>
                <h2>{text.howHeading}</h2>
                <p>{text.howDescription}</p>
              </div>

              <div className="steps-grid">
                <article className="step-card">
                  <span className="step-number">01</span>
                  <div className="step-icon">◉</div>
                  <h3>{text.tellStory}</h3>
                  <p>{text.tellStoryDescription}</p>
                </article>
                <article className="step-card">
                  <span className="step-number">02</span>
                  <div className="step-icon">✳</div>
                  <h3>{text.showKnowledge}</h3>
                  <p>{text.showKnowledgeDescription}</p>
                </article>
                <article className="step-card">
                  <span className="step-number">03</span>
                  <div className="step-icon">↗</div>
                  <h3>{text.exploreJobs}</h3>
                  <p>{text.exploreJobsDescription}</p>
                </article>
              </div>
            </section>

            <section className="why-section" id="why-yogya">
              <div>
                <span className="section-kicker">{text.fairerWay}</span>
                <h2>{text.fairerHeading}</h2>
              </div>
              <p>{text.fairerDescription}</p>
            </section>

            <section className="bottom-cta">
              <div>
                <span className="section-kicker">{text.nextStep}</span>
                <h2>{text.nextStepHeading}</h2>
              </div>
              <button
                className="primary-button"
                onClick={() => setStep("onboard")}
              >
                {text.createProfile} <span>→</span>
              </button>
            </section>
          </>
        )}

        {step === "onboard" && (
          <section className="onboarding-section">
            <button className="back-link" onClick={() => setStep("landing")}>
              ← {text.backHome}
            </button>

            <div className="onboarding-heading">
              <span className="section-kicker">{text.getToKnowYou}</span>
              <h1>{text.startStory}</h1>
              <p>{text.aboutYourself}</p>
              <div className="form-progress">
                <span />
                <small>{text.stepProgress}</small>
              </div>
              <OnboardingVoiceGuide
                language={language}
                instructions={text.onboardingVoiceGuide}
              />
            </div>

            <form className="onboarding-card" onSubmit={handleGenerateProfile}>
              <div className="form-section-title">
                <div>
                  <span className="section-kicker">{text.aboutYou}</span>
                  <h2>{text.yourDetails}</h2>
                </div>
                <span className="required-note">{text.requiredFields}</span>
              </div>

              <div className="form-grid">
                <label className="field">
                  <span>{text.yourName}</span>
                  <input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder={text.enterName}
                    required
                  />
                </label>

                <label className="field">
                  <span>{text.yourLocation}</span>
                  <input
                    value={location}
                    onChange={(event) => setLocation(event.target.value)}
                    placeholder={text.cityTown}
                  />
                </label>
              </div>

              <div className="form-divider" />

              <div className="form-section-title">
                <div>
                  <span className="section-kicker">{text.yourWork}</span>
                  <h2>{text.workType}</h2>
                  <p>{text.chooseTrade}</p>
                </div>
              </div>

              <div className="trade-grid">
                {[
                  { name: "Electrician", label: text.electrician, symbol: "ϟ", detail: text.electricianDetails },
                  { name: "Plumber", label: text.plumber, symbol: "⌁", detail: text.plumberDetails },
                ].map((trade) => (
                  <button
                    type="button"
                    key={trade.name}
                    className={`trade-option ${selectedTrade === trade.name ? "selected" : ""}`}
                    onClick={() => setSelectedTrade(trade.name)}
                    aria-pressed={selectedTrade === trade.name}
                  >
                    <span className="trade-symbol">{trade.symbol}</span>
                    <span className="trade-info">
                      <strong>{trade.label}</strong>
                      <small>{trade.detail}</small>
                    </span>
                    <span className="trade-radio">
                      {selectedTrade === trade.name ? "✓" : ""}
                    </span>
                  </button>
                ))}
              </div>

              <div className="form-divider" />

              <div className="form-section-title">
                <div>
                  <span className="section-kicker">{text.yourExperience}</span>
                  <h2>{text.workExperiencePrompt}</h2>
                  <p>{text.experienceGuidance}</p>
                </div>
              </div>

              <div className="voice-panel">
                <div className="voice-panel-heading">
                  <div>
                    <strong>{text.shareExperience}</strong>
                    <small>{text.voiceOrType}</small>
                  </div>
                  <span className="language-tag">
                    {language === "te" ? "తెలుగు" : language === "hi" ? text.hindi : text.english}
                  </span>
                </div>

                <div className="voice-controls">
                  <button
                    type="button"
                    className={`record-button ${isRecording ? "recording" : ""}`}
                    onClick={isRecording ? stopRecording : startRecording}
                    disabled={loading}
                  >
                    <span className="record-symbol">
                      {isRecording ? "■" : "●"}
                    </span>
                    {isRecording ? text.stopRecording : text.startRecording}
                  </button>

                  <span className="or-divider">{text.or}</span>

                  <label className="upload-button">
                    <span>↑</span> {text.uploadAudio}
                    <input
                      type="file"
                      accept="audio/*"
                      onChange={handleFileUpload}
                      disabled={loading}
                    />
                  </label>
                </div>

                {isRecording && (
                  <div className="recording-indicator">
                    <span className="recording-pulse" />
                    {text.recordingInProgress}
                  </div>
                )}

                <label className="field transcript-field">
                  <span>{text.transcriptLabel}</span>
                  <textarea
                    rows={5}
                    value={transcript}
                    onChange={(event) => setTranscript(event.target.value)}
                    placeholder={
                      language === "te"
                        ? text.teluguPlaceholder
                        : language === "hi"
                          ? text.hindiPlaceholder
                          : text.englishPlaceholder
                    }
                    required
                  />
                </label>

                <p className="privacy-note">{text.transcriptPrivacy}</p>
              </div>

              {statusMsg && (
                <div className="status-message" role="status" aria-live="polite">
                  {loading && <span className="loading-spinner" />}
                  {statusMsg}
                </div>
              )}

              <div className="form-footer">
                <span>{text.requiredFooter}</span>
                <button
                  type="submit"
                  className="primary-button"
                  disabled={loading || isRecording}
                >
                  {loading ? text.creatingProfile : text.generateProfile}
                  <span>→</span>
                </button>
              </div>
            </form>

            {import.meta.env.DEV && (
              <DemoProfilePanel
                language={language}
                tradeLabel={localizedTrade(selectedTrade, text)}
                disabled={loading || isRecording}
                onUse={handleUseDemoProfile}
              />
            )}
          </section>
        )}

        {step === "result" && savedResult && (
          <section className="result-section">
            <div className="result-success-icon">✓</div>
            <span className="section-kicker">{text.profileCreated}</span>
            <h1>{text.experienceTakingShape}</h1>
            <p className="result-intro">
              {savedResult.profile.extraction_source === "rule_based_fallback" &&
              !savedResult.profile.skills?.length
                ? text.fallbackNoSkills
                : text.profileSaved}
            </p>
            <OnboardingVoiceGuide
              language={language}
              instructions={
                savedResult.profile.skills?.length
                  ? text.resultVoiceGuide
                  : text.resultVoiceGuideNoSkills
              }
            />

            {savedResult.profile.extraction_source === "rule_based_fallback" && (
              <div className="status-message warning-message" role="note">
                {text.ruleBasedFallback}
              </div>
            )}

            {import.meta.env.DEV && savedResult.demo && (
              <div className="status-message warning-message dev-demo-banner" role="note">
                {(DEMO_COPY[language] || DEMO_COPY.en).banner}
              </div>
            )}

            <div className="result-card">
              <div className="result-card-header">
                <div>
                  <span className="section-kicker">{text.yogyaProfile}</span>
                  <h2>{name}</h2>
                  <p>{location || text.locationNotProvided}</p>
                </div>
                <span className="evidence-pill">{text.selfReported}</span>
              </div>

              <div className="result-details">
                <div>
                  <small>{text.trade}</small>
                  <strong>{localizedTrade(savedResult.profile.trade, text)}</strong>
                </div>
                <div>
                  <small>{text.experience}</small>
                  <strong>
                    {typeof savedResult.profile.experience_years === "number"
                      ? `${savedResult.profile.experience_years} ${text.years}`
                      : text.experienceUnknown}
                  </strong>
                </div>
                <div>
                  <small>{text.workerId}</small>
                  <strong>#{savedResult.worker_id}</strong>
                </div>
              </div>

              {savedResult.trade_mismatch && (
                <div className="status-message warning-message">
                  {formatMessage(text.tradeMismatch, { trade: localizedTrade(savedResult.detected_trade, text) })}
                </div>
              )}

              <div className="result-skills">
                <h3>{text.skillsIdentified}</h3>
                {savedResult.profile.skills?.length ? (
                  <div className="skill-list">
                    {savedResult.profile.skills.map((skill) => (
                      <div className="skill-row" key={skill}>
                        <span className="skill-check">✓</span>
                        <strong>{skill}</strong>
                        <span className="evidence-pill">{text.selfReportedSkills}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p>{text.noSkills}</p>
                )}
              </div>

              <p className="evidence-disclaimer">{text.evidenceDisclaimer}</p>
            </div>

            <div className="as-actions">
              <button className="primary-button" onClick={() => setStep("assessment")}>
                {ASSESSMENT_COPY[language].openCta} <span>→</span>
              </button>
              <button className="primary-button" onClick={() => setStep("passport")}>
                {text.openPassport} <span>→</span>
              </button>
              <button className="primary-button" onClick={resetOnboarding}>
                {text.createAnother} <span>→</span>
              </button>
            </div>
          </section>
        )}

        {step === "assessment" && savedResult && (
          <AssessmentFlow
            apiBase={API_BASE}
            workerId={savedResult.worker_id}
            workerName={name}
            workerLocation={location}
            trade={savedResult.profile.trade}
            initialLanguage={language}
            onLanguageChange={setLanguage}
            onExit={() => setStep("result")}
            onOpenPassport={() => setStep("passport")}
          />
        )}

        {step === "passport" && savedResult && (
          <SkillPassportPage
            apiBase={API_BASE}
            language={language}
            workerId={savedResult.worker_id}
            onBack={() => setStep("result")}
            onOpenJobs={() => setStep("jobs")}
          />
        )}

        {step === "jobs" && savedResult && (
          <JobRecommendationsPage
            apiBase={API_BASE}
            language={language}
            workerId={savedResult.worker_id}
            onBack={() => setStep("passport")}
          />
        )}
        </main>

        <footer className="site-footer">
          <div className="footer-brand">
            <span className="brand-mark">Y</span>
            <strong>yogya.</strong>
          </div>
          <span>{text.footerTagline}</span>
          <span>{text.madeForWorkers}</span>
        </footer>
        <VoiceCompanionControls language={language} />
      </div>
    </VoiceCompanionProvider>
  );
}
