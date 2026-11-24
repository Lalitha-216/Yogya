"""Deterministically evaluate worker answers against the stored assessment rubric."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal, Mapping

from .question_bank import AssessmentQuestion


AnswerLanguage = Literal["en", "te", "hi"]

_QUESTION_TEXT_FIELDS: dict[str, str] = {
    "en": "question_text_en",
    "te": "question_text_te",
    "hi": "question_text_hi",
}
_RUBRIC_LEVELS = {"0", "1", "2", "3", "4"}


class InputValidationError(ValueError):
    """Raised when the question, answer, or language is invalid."""


class EvaluatorConfigurationError(RuntimeError):
    """Retained for compatibility with the assessment HTTP error mapper."""


class EvaluatorServiceError(RuntimeError):
    """Retained for compatibility with the assessment HTTP error mapper."""


class EvaluationResponseValidationError(ValueError):
    """Raised when an assessment question's rubric is malformed."""


@dataclass(frozen=True)
class ConceptEvaluation:
    """Evidence-based evaluation for one expected concept."""

    concept: str
    demonstrated: bool
    evidence: str | None
    rationale: str


@dataclass(frozen=True)
class SafetyConcern:
    """A safety finding grounded in a verbatim excerpt of the answer."""

    concern: str
    evidence: str


@dataclass(frozen=True)
class EvaluationResult:
    """Validated evaluation of one answer; contains no progression authority."""

    question_id: str
    score: int
    concept_evaluations: tuple[ConceptEvaluation, ...]
    feedback: str
    safety_concerns: tuple[SafetyConcern, ...]
    safety_critical_misconception: bool


# A criterion is demonstrated only when one of its complete, curated phrases is
# present in the answer. Phrases are deliberately specific to the bank's rubric.
_CONCEPT_CUES: dict[str, tuple[str, ...]] = {
    "screwdriver with a suitable tip": (
        "screwdriver with a suitable tip", "screwdriver with the right tip",
        "సరైన టిప్ ఉన్న స్క్రూడ్రైవర్", "उपयुक्त नोक वाला पेचकस",
    ),
    "correct fit helps avoid damaging the screw": (
        "correct fit helps avoid damaging the screw", "fits the screw and prevents damage",
        "fits the screw and helps prevent damage",
        "correct size to avoid damaging the screw", "స్క్రూ పాడవకుండా సరైన పరిమాణం",
        "స్క్రూ దెబ్బతినకుండా", "स्क्रू को नुकसान से बचाने के लिए सही फिट",
        "सही आकार ताकि स्क्रू खराब न हो",
    ),
    "switch controls the electrical supply to a load": (
        "switch controls the electrical supply", "switch turns the appliance on and off",
        "స్విచ్ విద్యుత్ సరఫరాను నియంత్రిస్తుంది", "स्विच बिजली की आपूर्ति नियंत्रित करता है",
    ),
    "socket provides a connection for an appliance": (
        "socket provides a connection", "socket connects an appliance",
        "సాకెట్ పరికరానికి కనెక్షన్ ఇస్తుంది", "सॉकेट उपकरण को जोड़ने का कनेक्शन देता है",
    ),
    "supply must be isolated": (
        "isolate the supply", "disconnect the supply", "switch off the supply",
        "turn off the power", "isolate the circuit", "విద్యుత్ సరఫరా నిలిపి",
        "సరఫరాను నిలిపి", "సర్క్యూట్‌ను వేరు చేసి", "बिजली की सप्लाई बंद",
        "बिजली बंद करके", "सर्किट को अलग करके",
    ),
    "absence of voltage must be verified with a suitable tester": (
        "verify that no voltage is present", "test for absence of voltage",
        "check that the circuit is dead with a tester", "voltage tester confirms no voltage",
        "టెస్టర్‌తో వోల్టేజ్ లేదని నిర్ధారించ", "వోల్టేజ్ లేదని పరీక్షించ",
        "टेस्टर से जाँचें कि वोल्टेज नहीं है", "वोल्टेज न होने की जाँच",
    ),
    "colours may be incorrect or inconsistent": (
        "wire colours may be wrong", "wire color can be incorrect",
        "colours may be inconsistent", "colour cannot be trusted",
        "వైరు రంగులు తప్పుగా ఉండవచ్చు", "రంగును మాత్రమే నమ్మకూడదు",
        "तार के रंग गलत हो सकते हैं", "केवल रंग पर भरोसा नहीं",
    ),
    "verify conductor function before making a connection": (
        "verify the conductor function before connecting", "identify the wire with a tester",
        "test the wire before making a connection", "కనెక్షన్‌కు ముందు వైరు పనితీరును పరీక్షించ",
        "టెస్టర్‌తో వైర్‌ను గుర్తించ", "जोड़ने से पहले तार की भूमिका जाँचें",
        "टेस्टर से तार की पहचान",
    ),
    "support is suitable for the fan load": (
        "ceiling support can carry the fan load", "support is strong enough for the fan",
        "check the ceiling support", "ఫ్యాన్ బరువుకు పైకప్పు ఆధారం సరిపోతుంది",
        "పైకప్పు ఆధారాన్ని తనిఖీ", "छत का सहारा पंखे का भार उठा सकता है",
        "छत के सहारे की जाँच",
    ),
    "supply and controls are appropriate": (
        "check the supply and controls", "supply and controls are suitable",
        "విద్యుత్ సరఫరా మరియు నియంత్రణలను తనిఖీ", "सप्लाई और कंट्रोल जाँचें",
    ),
    "circuit is isolated before work": (
        "isolate the circuit before work", "disconnect the circuit before installation",
        "పని ముందు సర్క్యూట్‌ను వేరు", "काम से पहले सर्किट बंद",
    ),
    "isolate and verify the circuit before inspection": (
        "isolate and test the circuit before inspection",
        "disconnect and verify the circuit before inspection",
        "తనిఖీకి ముందు సర్క్యూట్‌ను నిలిపి పరీక్షించ",
        "जाँच से पहले सर्किट बंद करके जाँचें",
    ),
    "check the connection and conductor condition": (
        "check the connection and wire condition", "inspect the connection and conductor",
        "కనెక్షన్ మరియు వైర్ పరిస్థితిని తనిఖీ", "कनेक्शन और तार की हालत जाँचें",
    ),
    "consider other circuit faults": (
        "check for other circuit faults", "consider other electrical faults",
        "ఇతర సర్క్యూట్ లోపాలను పరిశీలించ", "दूसरे सर्किट दोषों की जाँच",
    ),
    "breaker protects a circuit against excessive current": (
        "breaker protects the circuit from excessive current",
        "circuit breaker trips when current is too high",
        "అధిక కరెంట్ నుంచి సర్క్యూట్‌ను బ్రేకర్ రక్షిస్తుంది",
        "ब्रेकर अधिक करंट से सर्किट की रक्षा करता है",
    ),
    "rating must suit the circuit and conductors": (
        "breaker rating must match the circuit and wire",
        "rating must suit the wire size", "రేటింగ్ వైర్ మరియు సర్క్యూట్‌కు సరిపోవాలి",
        "रेटिंग तार और सर्किट के अनुसार हो",
    ),
    "tripping cause needs investigation": (
        "investigate why the breaker trips", "find the cause of tripping",
        "బ్రేకర్ ఎందుకు ట్రిప్ అవుతుందో కారణం చూడాలి",
        "ब्रेकर ट्रिप होने का कारण पता करें",
    ),
    "consider the combined load and circuit rating": (
        "add the appliance loads and compare with circuit rating",
        "combined load exceeds the circuit rating", "మొత్తం లోడ్‌ను సర్క్యూట్ రేటింగ్‌తో పోల్చ",
        "कुल लोड की सर्किट रेटिंग से तुलना",
    ),
    "observe whether trips relate to simultaneous appliance use": (
        "see if it trips when appliances run together",
        "check whether simultaneous use causes tripping",
        "అన్ని పరికరాలు ఒకేసారి వాడినప్పుడు ట్రిప్ అవుతుందా చూడాలి",
        "एक साथ उपकरण चलने पर ट्रिप होता है या नहीं देखें",
    ),
    "do not ignore wiring faults": (
        "check for wiring faults as well", "do not ignore a wiring fault",
        "వైరింగ్ లోపాలను కూడా పరిశీలించ", "वायरिंग की खराबी को भी जाँचें",
    ),
    "a fault may create an unintended low-resistance current path": (
        "short circuit creates a low resistance path", "unintended low resistance path",
        "తక్కువ నిరోధం ఉన్న అనుకోని మార్గం", "अनचाहा कम प्रतिरोध वाला रास्ता",
    ),
    "keep the circuit isolated": (
        "keep the circuit isolated", "leave the circuit switched off",
        "సర్క్యూట్‌ను నిలిపి ఉంచ", "सर्किट बंद रखें",
    ),
    "qualified diagnosis is needed before restoring supply": (
        "qualified person should diagnose before restoring power",
        "do not restore supply until diagnosed by a qualified",
        "నిపుణుడు పరిశీలించే వరకు సరఫరా పునరుద్ధరించకూడదు",
        "योग्य व्यक्ति की जाँच से पहले सप्लाई चालू न करें",
    ),
    "earthing provides a fault-current path": (
        "earthing provides a path for fault current", "earth wire carries fault current",
        "ఎర్తింగ్ లోప కరెంట్‌కు మార్గం ఇస్తుంది", "अर्थिंग दोष करंट के लिए रास्ता देती है",
    ),
    "protective devices must disconnect a fault": (
        "protective device disconnects the fault", "breaker disconnects the fault",
        "రక్షణ పరికరం లోపాన్ని విడదీస్తుంది", "सुरक्षा उपकरण खराबी पर सप्लाई काटता है",
    ),
    "earthing and protection serve related but different roles": (
        "earthing is not a substitute for circuit protection",
        "earthing and breaker have different roles",
        "ఎర్తింగ్ సర్క్యూట్ రక్షణకు బదులు కాదు", "अर्थिंग सर्किट सुरक्षा का विकल्प नहीं",
    ),
    "possible overload": ("overload may be the cause", "possible overload",
                          "అధిక లోడ్ కారణం కావచ్చు", "ओवरलोड कारण हो सकता है"),
    "possible short circuit or earth fault": (
        "short circuit or earth fault", "short or earth fault",
        "షార్ట్ సర్క్యూట్ లేదా ఎర్త్ లోపం", "शॉर्ट सर्किट या अर्थ फॉल्ट",
    ),
    "damaged appliance or wiring": (
        "damaged appliance or wiring", "check damaged wiring and appliances",
        "పాడైన పరికరం లేదా వైరింగ్", "खराब उपकरण या वायरिंग",
    ),
    "repeated trips require investigation rather than repeated resetting": (
        "investigate repeated trips instead of resetting again",
        "do not keep resetting the breaker", "మళ్లీ మళ్లీ రీసెట్ చేయకుండా కారణం చూడాలి",
        "बार-बार रीसेट करने के बजाय कारण जाँचें",
    ),
    "stop use and isolate the affected circuit when safe to do so": (
        "stop using it and isolate the affected circuit",
        "stop use and switch off the affected circuit",
        "వాడటం ఆపి ప్రభావిత సర్క్యూట్‌ను నిలిపి", "उपयोग रोककर प्रभावित सर्किट बंद करें",
    ),
    "record when and where the symptom occurs": (
        "record when and where it happens", "note when and where the symptom occurs",
        "ఎప్పుడు ఎక్కడ సమస్య వస్తుందో నమోదు", "लक्षण कब और कहाँ होता है लिखें",
    ),
    "consider loose or overloaded connections": (
        "check for loose or overloaded connections", "loose connection or overloading",
        "వదులైన లేదా అధిక లోడ్ కనెక్షన్లు", "ढीले या ओवरलोडेड कनेक्शन",
    ),
    "qualified inspection is required for a potentially hazardous fault": (
        "qualified electrician should inspect the hazardous fault",
        "qualified inspection is required", "ప్రమాదకర లోపాన్ని నిపుణుడు తనిఖీ చేయాలి",
        "खतरनाक खराबी की योग्य व्यक्ति से जाँच कराएँ",
    ),
    "pipe wrench or suitable pipe-gripping tool": (
        "pipe wrench", "pipe gripping tool", "ప్లంబర్ రెంచ్", "పైప్ రెంచ్",
        "पाइप रिंच", "पाइप पकड़ने वाला औज़ार",
    ),
    "jaw size and grip should suit the fitting": (
        "jaw size should fit the pipe", "grip should suit the fitting",
        "ఫిట్టింగ్‌కు సరిపోయే జా పరిమాణం", "फिटिंग के अनुसार जबड़े का आकार",
    ),
    "intended use and water type": (
        "intended use and water type", "what the water will be used for",
        "నీటి రకం మరియు ఉపయోగం", "पानी का प्रकार और उपयोग",
    ),
    "pressure and temperature rating": (
        "pressure and temperature rating", "rated for the pressure and temperature",
        "పీడనం మరియు ఉష్ణోగ్రత రేటింగ్", "दबाव और तापमान की रेटिंग",
    ),
    "local requirements and compatibility": (
        "local requirements and compatibility", "local code and compatible materials",
        "స్థానిక నియమాలు మరియు సరిపోలిక", "स्थानीय नियम और अनुकूलता",
    ),
    "dry the area and observe where water reappears": (
        "dry the area and see where water returns", "dry it and observe where water reappears",
        "ప్రాంతాన్ని తుడిచి నీరు ఎక్కడ మళ్లీ వస్తుందో చూడాలి",
        "जगह सुखाकर देखें पानी कहाँ फिर आता है",
    ),
    "inspect the joint and nearby pipe": (
        "inspect the joint and nearby pipe", "check the joint and pipe",
        "జాయింట్ మరియు దగ్గర పైపును తనిఖీ", "जोड़ और पास के पाइप की जाँच",
    ),
    "consider whether water may be running from above": (
        "water may be coming from above", "check for water running from above",
        "పై నుంచి నీరు వస్తుందేమో చూడాలి", "ऊपर से पानी आ रहा हो सकता है",
    ),
    "whether the supply is available to the building": (
        "check whether the building has water supply", "supply to the building is available",
        "భవనానికి నీటి సరఫరా ఉందో చూడాలి", "इमारत में पानी की सप्लाई है या नहीं",
    ),
    "whether the local shutoff is open": (
        "check whether the local shutoff valve is open", "local valve is open",
        "లోకల్ వాల్వ్ తెరిచి ఉందో చూడాలి", "स्थानीय वाल्व खुला है या नहीं",
    ),
    "whether other outlets are also affected": (
        "check whether other taps are affected", "other outlets also have no flow",
        "ఇతర ట్యాప్‌లలో కూడా నీరు రావడం లేదా చూడాలి",
        "दूसरे नलों में भी पानी नहीं आ रहा है या नहीं",
    ),
    "tap matches the mounting and connection": (
        "tap matches the mounting and connection", "tap fitting suits the connection",
        "ట్యాప్ కనెక్షన్‌కు సరిపోతుంది", "नल का फिटिंग कनेक्शन के अनुसार है",
    ),
    "seals are correctly placed": (
        "seals are correctly placed", "place the seal correctly",
        "సీల్‌ను సరిగ్గా అమర్చ", "सील सही जगह लगाएँ",
    ),
    "connections are not overtightened": (
        "do not overtighten the connections", "connections are not too tight",
        "కనెక్షన్లను అతిగా బిగించకూడదు", "कनेक्शन को बहुत कसकर न बाँधें",
    ),
    "check for leaks after supply is restored": (
        "check for leaks after turning the supply back on",
        "check for leaks after supply is restored",
        "సరఫరా ప్రారంభించిన తర్వాత లీక్ ఉందో చూడాలి",
        "सप्लाई चालू करने के बाद रिसाव जाँचें",
    ),
    "incorrect or damaged seal": (
        "incorrect or damaged seal", "damaged seal", "సీల్ పాడైంది",
        "गलत या खराब सील",
    ),
    "misaligned or damaged threads": (
        "misaligned or damaged threads", "damaged pipe threads",
        "థ్రెడ్‌లు వంకరగా లేదా పాడై", "टेढ़े या खराब थ्रेड",
    ),
    "unsuitable joint material": (
        "unsuitable joint material", "wrong jointing material",
        "తగని జాయింట్ పదార్థం", "गलत जोड़ने की सामग्री",
    ),
    "excessive or insufficient tightening": (
        "too much or too little tightening", "over-tightened or loose connection",
        "అతిగా లేదా తక్కువగా బిగించ", "बहुत ज्यादा या कम कसना",
    ),
    "check whether one fixture or several are affected": (
        "check if one fixture or several are affected",
        "see whether one or multiple fixtures are affected",
        "ఒకటి లేదా ఎక్కువ ట్యాప్‌లలో సమస్య ఉందో చూడాలి",
        "एक या कई नल प्रभावित हैं या नहीं देखें",
    ),
    "observe gurgling or backflow": (
        "listen for gurgling or check for backflow", "observe gurgling or backflow",
        "గురగుర శబ్దం లేదా నీరు వెనక్కి వస్తుందా చూడాలి",
        "गड़गड़ाहट या पानी वापस आने की जाँच",
    ),
    "consider blockage location and safe access": (
        "locate the blockage and ensure safe access",
        "consider where the blockage is and safe access",
        "బ్లాకేజ్ స్థానం మరియు సురక్షిత ప్రవేశం", "रुकावट की जगह और सुरक्षित पहुँच",
    ),
    "compare flow at multiple outlets": (
        "compare water flow at several outlets", "check flow at multiple taps",
        "చాలా అవుట్‌లెట్‌లలో నీటి ప్రవాహాన్ని పోల్చాలి",
        "कई नलों के पानी के बहाव की तुलना",
    ),
    "check whether the issue is building-wide": (
        "check if the problem affects the whole building",
        "see whether the issue is building wide",
        "భవనం అంతటా సమస్య ఉందో చూడాలి", "पूरी इमारत में समस्या है या नहीं",
    ),
    "consider a blocked filter or valve at an individual outlet": (
        "check for a blocked filter or valve at that outlet",
        "individual outlet may have a blocked filter or valve",
        "ఆ అవుట్‌లెట్ ఫిల్టర్ లేదా వాల్వ్ మూసుకుపోయిందో చూడాలి",
        "नल का फिल्टर या वाल्व जाम है या नहीं",
    ),
    "possible hidden leak": (
        "there may be a hidden leak", "possible hidden leak",
        "లోపల దాచిన లీక్ ఉండవచ్చు", "छिपा हुआ रिसाव हो सकता है",
    ),
    "record meter movement with outlets closed": (
        "record the meter movement with all outlets closed",
        "watch the meter after closing all outlets",
        "అన్ని అవుట్‌లెట్‌లు మూసి మీటర్ కదలికను నమోదు",
        "सभी नल बंद करके मीटर की चाल देखें",
    ),
    "look for damp areas or unexplained consumption": (
        "look for damp patches or unexplained water use",
        "check for damp areas or unusual consumption",
        "తడి ప్రాంతాలు లేదా తెలియని నీటి వినియోగం చూడాలి",
        "नमी वाली जगह या बिना कारण पानी की खपत देखें",
    ),
    "avoid damaging walls before locating the likely route": (
        "locate the likely leak route before breaking the wall",
        "avoid damaging walls before locating the leak",
        "లీక్ దారి గుర్తించే ముందు గోడను పగలగొట్టకూడదు",
        "रिसाव का रास्ता पता करने से पहले दीवार न तोड़ें",
    ),
    "temperature and pressure ratings": (
        "temperature and pressure ratings", "rated for temperature and pressure",
        "ఉష్ణోగ్రత మరియు పీడన రేటింగ్", "तापमान और दबाव की रेटिंग",
    ),
    "pipe material suitability for the water and use": (
        "pipe material suits the water and intended use",
        "material is suitable for the water and use",
        "పైపు పదార్థం నీరు మరియు ఉపయోగానికి సరిపోతుంది",
        "पाइप की सामग्री पानी और उपयोग के लिए उपयुक्त है",
    ),
    "compatible fittings and joining method": (
        "compatible fittings and joining method",
        "fittings and joining method match the pipe",
        "సరిపోయే ఫిట్టింగ్‌లు మరియు జాయింట్ పద్ధతి",
        "अनुकूल फिटिंग और जोड़ने का तरीका",
    ),
    "applicable local requirements": (
        "follow applicable local requirements", "meet local plumbing requirements",
        "స్థానిక నియమాలను పాటించాలి", "स्थानीय नियमों का पालन",
    ),
    "pipe movement or poor support": (
        "pipe movement or poor support", "pipe is moving or not supported",
        "పైపు కదలడం లేదా సరైన ఆధారం లేకపోవడం", "पाइप हिलना या सहारा ठीक न होना",
    ),
    "corrosion or damaged pipe": (
        "corrosion or damaged pipe", "corroded or damaged pipe",
        "తుప్పు పట్టిన లేదా పాడైన పైపు", "जंग लगा या खराब पाइप",
    ),
    "pressure or water-hammer effects": (
        "pressure changes or water hammer", "water hammer effect",
        "పీడన మార్పు లేదా వాటర్ హ్యామర్", "दबाव बदलना या वॉटर हैमर",
    ),
    "incorrect material or joining method": (
        "wrong pipe material or joining method",
        "incorrect material or joining method",
        "తప్పు పదార్థం లేదా జాయింట్ పద్ధతి", "गलत सामग्री या जोड़ने का तरीका",
    ),
    "which fixtures are affected and in what order": (
        "which fixtures are affected and in what order",
        "note the order in which fixtures are affected",
        "ఏ ఫిక్చర్‌లో సమస్య వచ్చిందో క్రమంగా నమోదు",
        "कौन-से नल किस क्रम में प्रभावित हुए",
    ),
    "gurgling or backflow symptoms": (
        "gurgling or backflow symptoms", "gurgling sounds or backflow",
        "గురగుర శబ్దం లేదా వెనక్కి ప్రవాహం", "गड़गड़ाहट या उल्टा बहाव",
    ),
    "whether the issue points to a shared drain or vent": (
        "problem may be in a shared drain or vent",
        "check whether a shared drain or vent is affected",
        "సాధారణ డ్రెయిన్ లేదా వెంట్లో సమస్య ఉందా చూడాలి",
        "साझी नाली या वेंट में समस्या जाँचें",
    ),
    "protect people from contaminated water and use qualified help when needed": (
        "protect people from contaminated water and call a qualified plumber",
        "avoid contact with contaminated water and get qualified help",
        "కలుషిత నీటి నుంచి రక్షించి నిపుణుడి సహాయం తీసుకోవాలి",
        "दूषित पानी से बचाव करें और योग्य मदद लें",
    ),
}

_PARTIAL_STOP_WORDS = {
    "a", "an", "and", "are", "as", "be", "before", "by", "for", "from",
    "in", "is", "it", "may", "of", "on", "or", "should", "the", "to",
    "with", "must", "can", "when", "where", "what", "whether", "that",
    "this", "these", "those", "helps", "avoid", "against", "provide",
    "provides", "suitable", "correct", "possible", "required", "appropriate",
}

_REASONING_CUES = (
    "because", "so that", "therefore", "which means", "this prevents",
    "to avoid", "as a result", "ఎందుకంటే", "కాబట్టి", "దీనివల్ల",
    "తద్వారా", "क्योंकि", "इसलिए", "ताकि", "जिससे",
)

_UNSAFE_CUES: dict[str, tuple[str, ...]] = {
    "E03": (
        "work while the power is still on", "work while power is on",
        "work on a live circuit", "not isolate the supply", "do not isolate the supply",
        "విద్యుత్ ఆన్‌లో ఉండగా పని", "సరఫరా నిలిపివేయకుండా పని",
        "बिजली चालू रहते काम", "सप्लाई बंद किए बिना काम",
    ),
    "E04": (
        "rely only on wire colour", "rely only on wire color",
        "colour alone is enough", "color alone is enough",
        "వైరు రంగును మాత్రమే నమ్మ", "केवल तार के रंग पर भरोसा",
    ),
    "E05": (
        "install the fan while power is on", "work on the live circuit",
        "విద్యుత్ ఆన్‌లో ఉండగా ఫ్యాన్", "बिजली चालू रहते पंखा लगाएँ",
    ),
    "E06": (
        "inspect the live circuit", "work without isolating the circuit",
        "సర్క్యూట్‌ను నిలిపివేయకుండా తనిఖీ", "सर्किट बंद किए बिना जाँच",
    ),
    "E07": (
        "replace it with a higher-rated breaker", "use a higher rated breaker",
        "ట్రిప్ ఆపడానికి ఎక్కువ రేటింగ్ బ్రేకర్", "ज्यादा रेटिंग वाला ब्रेकर लगाएँ",
    ),
    "E08": (
        "ignore the wiring fault", "ignore wiring faults",
        "వైరింగ్ లోపాన్ని పట్టించుకోక", "वायरिंग की खराबी को अनदेखा",
    ),
    "E09": (
        "restore power before the fault is diagnosed", "switch it back on without diagnosis",
        "లోపాన్ని గుర్తించకుండానే సరఫరా", "खराबी जाँचे बिना सप्लाई चालू",
    ),
    "E10": (
        "earthing replaces circuit protection", "earthing is enough without a breaker",
        "ఎర్తింగ్ ఉంటే బ్రేకర్ అవసరం లేదు", "अर्थिंग से ब्रेकर की जरूरत नहीं",
    ),
    "E11": (
        "keep resetting the breaker", "repeatedly reset without checking",
        "కారణం చూడకుండా బ్రేకర్‌ను మళ్లీ మళ్లీ రీసెట్",
        "जाँच किए बिना ब्रेकर बार-बार रीसेट",
    ),
    "E12": (
        "keep using the warm outlet", "continue using the hot outlet",
        "వేడెక్కిన సాకెట్‌ను వాడుతూనే", "गर्म सॉकेट का इस्तेमाल जारी",
    ),
    "P12": (
        "touch contaminated water without protection", "ignore contaminated water",
        "కలుషిత నీటిని పట్టించుకోకుండా", "दूषित पानी को अनदेखा",
    ),
}

_UNSAFE_RATIONALE = {
    "en": "This statement describes an unsafe action that may cause harm.",
    "te": "ఈ వాక్యం హాని కలిగించగల అసురక్షిత చర్యను సూచిస్తోంది.",
    "hi": "यह कथन नुकसान पहुँचा सकने वाली असुरक्षित कार्रवाई बताता है।",
}
_FEEDBACK = {
    "en": {
        0: "The answer does not include clear evidence for the rubric concepts. Review the question and explain the relevant checks.",
        1: "The answer mentions a relevant idea, but the rubric evidence is incomplete. Explain how it applies to the situation.",
        2: "The answer supports some rubric concepts, but other expected points are missing. Add the missing checks.",
        3: "The answer provides evidence for all expected rubric concepts. Explain why the checks matter to strengthen it.",
        4: "The answer supports all expected rubric concepts and explains the reasoning connecting them.",
    },
    "te": {
        0: "సమాధానంలో రుబ్రిక్ అంశాలకు స్పష్టమైన ఆధారం లేదు. ప్రశ్నను పరిశీలించి సంబంధిత తనిఖీలను వివరించండి.",
        1: "సంబంధిత అంశం ప్రస్తావించారు, కానీ రుబ్రిక్‌కు ఆధారం పూర్తి కాలేదు. అది ఈ పరిస్థితికి ఎలా వర్తిస్తుందో వివరించండి.",
        2: "కొన్ని రుబ్రిక్ అంశాలకు ఆధారం ఉంది, కానీ ఇతర అంశాలు లేవు. మిగిలిన తనిఖీలను చేర్చండి.",
        3: "అన్ని రుబ్రిక్ అంశాలకు సమాధానంలో ఆధారం ఉంది. తనిఖీలు ఎందుకు ముఖ్యమో వివరిస్తే మరింత బలంగా ఉంటుంది.",
        4: "అన్ని రుబ్రిక్ అంశాలకు ఆధారం ఇచ్చి, వాటి మధ్య కారణ సంబంధాన్ని కూడా వివరించారు.",
    },
    "hi": {
        0: "उत्तर में रूब्रिक के बिंदुओं का स्पष्ट साक्ष्य नहीं है। प्रश्न देखकर संबंधित जाँचों को समझाएँ।",
        1: "उत्तर में एक प्रासंगिक बात है, लेकिन रूब्रिक का साक्ष्य अधूरा है। बताएँ कि वह इस स्थिति में कैसे लागू होती है।",
        2: "उत्तर कुछ रूब्रिक बिंदुओं का समर्थन करता है, लेकिन दूसरे अपेक्षित बिंदु छूट गए हैं। बाकी जाँचें जोड़ें।",
        3: "उत्तर में सभी अपेक्षित रूब्रिक बिंदुओं का साक्ष्य है। जाँचें क्यों ज़रूरी हैं, यह बताने से उत्तर और स्पष्ट होगा।",
        4: "उत्तर सभी अपेक्षित रूब्रिक बिंदुओं का साक्ष्य देता है और उनके बीच का तर्क भी समझाता है।",
    },
}


def _validate_question(
    question: AssessmentQuestion,
    answer_language: str,
) -> tuple[tuple[str, ...], dict[str, str]]:
    if not isinstance(question, AssessmentQuestion):
        raise InputValidationError("question must be an AssessmentQuestion.")
    question_text_field = _QUESTION_TEXT_FIELDS.get(answer_language)
    if question_text_field is None:
        raise InputValidationError("answer_language must be 'en', 'te', or 'hi'.")
    question_text = getattr(question, question_text_field)
    if not isinstance(question_text, str) or not question_text.strip():
        raise InputValidationError(
            f"The question has no usable {answer_language} question text."
        )
    concepts = question.expected_concepts
    if (
        not isinstance(concepts, (tuple, list))
        or not concepts
        or any(not isinstance(item, str) or not item.strip() for item in concepts)
        or len(set(concepts)) != len(concepts)
    ):
        raise InputValidationError(
            "expected_concepts must be unique, non-empty strings."
        )
    rubric = question.rubric_json
    if not isinstance(rubric, Mapping) or set(rubric) != _RUBRIC_LEVELS:
        raise EvaluationResponseValidationError(
            'rubric_json must contain exactly the levels "0" through "4".'
        )
    if any(not isinstance(text, str) or not text.strip() for text in rubric.values()):
        raise EvaluationResponseValidationError(
            "Every rubric level must have a non-empty description."
        )
    if not isinstance(question.question_id, str) or not question.question_id.strip():
        raise InputValidationError("question must have a non-empty question_id.")
    if not isinstance(question.safety_critical, bool):
        raise InputValidationError("question.safety_critical must be a Boolean.")
    return tuple(concepts), dict(rubric)


def _phrase_match(answer: str, phrase: str) -> re.Match[str] | None:
    escaped = r"\s+".join(re.escape(part) for part in phrase.split())
    return re.search(escaped, answer, flags=re.IGNORECASE)


def _is_negated(answer: str, match: re.Match[str]) -> bool:
    prefix = answer[max(0, match.start() - 36):match.start()]
    suffix = answer[match.end():match.end() + 24]
    return bool(
        re.search(
            r"\b(?:not|never|don't|doesn't|didn't|cannot|can't|no)\s*$"
            r"|(?:లేదు|కాదు|చేయలేదు|చేయను|नहीं|मत)\s*$",
            prefix,
            flags=re.IGNORECASE,
        )
        or re.match(
            r"^\s*(?:isn't|aren't|wasn't|were not|చేయలేదు|కాదు|नहीं)",
            suffix,
            flags=re.IGNORECASE,
        )
    )


def _concept_evidence(answer: str, concept: str) -> tuple[str | None, str | None]:
    for cue in _CONCEPT_CUES.get(concept, ()):
        match = _phrase_match(answer, cue)
        if match and not _is_negated(answer, match):
            return match.group(0), match.group(0)

    words = [
        word for word in re.findall(r"[a-z0-9]+", concept.casefold())
        if len(word) > 3 and word not in _PARTIAL_STOP_WORDS
    ]
    if not words:
        return None, None
    partial_matches = []
    for word in dict.fromkeys(words):
        match = re.search(rf"\b{re.escape(word)}\b", answer, re.IGNORECASE)
        if match and not _is_negated(answer, match):
            partial_matches.append(match)
    threshold = 1 if len(set(words)) == 1 else max(2, (len(set(words)) + 1) // 2)
    if len(partial_matches) >= threshold:
        first = min(match.start() for match in partial_matches)
        last = max(match.end() for match in partial_matches)
        return None, answer[first:last]
    return None, None


def _safety_findings(
    question: AssessmentQuestion,
    answer: str,
) -> tuple[SafetyConcern, ...]:
    if not question.safety_critical:
        return ()
    for cue in _UNSAFE_CUES.get(question.question_id, ()):
        match = _phrase_match(answer, cue)
        if match and not _is_negated(answer, match):
            return (
                SafetyConcern(
                    concern=f'"{match.group(0)}" — {_UNSAFE_RATIONALE["en"]}',
                    evidence=match.group(0),
                ),
            )
    return ()


def _has_reasoning_after_evidence(
    answer: str,
    concept_evaluations: list[ConceptEvaluation],
) -> bool:
    evidence_spans = [
        (answer.find(item.evidence), answer.find(item.evidence) + len(item.evidence))
        for item in concept_evaluations
        if item.demonstrated and item.evidence is not None
    ]
    first = min(start for start, _ in evidence_spans)
    last = max(end for _, end in evidence_spans)
    left_boundary = max(
        (answer.rfind(mark, 0, first) for mark in ".!?;\n"),
        default=-1,
    )
    right_candidates = [
        answer.find(mark, last)
        for mark in ".!?;\n"
        if answer.find(mark, last) >= 0
    ]
    right_boundary = min(right_candidates) if right_candidates else len(answer)
    evidence_sentence = answer[left_boundary + 1:right_boundary]
    return any(_phrase_match(evidence_sentence, cue) for cue in _REASONING_CUES)


def evaluate_answer(
    question: AssessmentQuestion,
    answer: str,
    answer_language: Literal["en", "te", "hi"],
) -> EvaluationResult:
    """Score only explicit rubric evidence; this path makes no provider calls."""
    if not isinstance(answer_language, str) or answer_language not in _QUESTION_TEXT_FIELDS:
        raise InputValidationError("answer_language must be 'en', 'te', or 'hi'.")
    if not isinstance(answer, str) or not answer.strip():
        raise InputValidationError("answer must be a non-empty string.")

    concepts, rubric = _validate_question(question, answer_language)
    concept_results = []
    complete_count = 0
    partial_count = 0
    for concept in concepts:
        evidence, partial_evidence = _concept_evidence(answer, concept)
        demonstrated = evidence is not None
        complete_count += int(demonstrated)
        partial_count += int(partial_evidence is not None)
        if demonstrated:
            rationale = f'The answer explicitly states "{evidence}", supporting {concept}.'
        elif partial_evidence:
            rationale = (
                f'The answer mentions "{partial_evidence}", but does not provide '
                f'enough evidence for {concept}.'
            )
        else:
            rationale = f"The answer does not provide explicit evidence for {concept}."
        concept_results.append(
            ConceptEvaluation(
                concept=concept,
                demonstrated=demonstrated,
                evidence=evidence if demonstrated else partial_evidence,
                rationale=rationale,
            )
        )

    if complete_count == 0:
        score = 1 if partial_count else 0
    elif complete_count < len(concepts):
        score = 2
    else:
        score = 3
        if _has_reasoning_after_evidence(answer, concept_results):
            score = 4

    # Keep the rubric descriptions authoritative and fail closed if the bank no
    # longer expresses the deterministic level rules this evaluator implements.
    if score == 0 and "no relevant concept" not in rubric["0"].casefold():
        raise EvaluationResponseValidationError("Rubric level 0 is not supported.")
    if score == 1 and not any(
        marker in rubric["1"].casefold()
        for marker in ("names or partly describes", "partly describes")
    ):
        raise EvaluationResponseValidationError("Rubric level 1 is not supported.")
    if score == 2 and "some but not all" not in rubric["2"].casefold():
        raise EvaluationResponseValidationError("Rubric level 2 is not supported.")
    if score == 3 and "all of these expected points" not in rubric["3"].casefold():
        raise EvaluationResponseValidationError("Rubric level 3 is not supported.")
    if score == 4 and "explains why" not in rubric["4"].casefold():
        raise EvaluationResponseValidationError("Rubric level 4 is not supported.")

    safety_concerns = _safety_findings(question, answer)
    return EvaluationResult(
        question_id=question.question_id,
        score=score,
        concept_evaluations=tuple(concept_results),
        feedback=_FEEDBACK[answer_language][score],
        safety_concerns=safety_concerns,
        safety_critical_misconception=bool(safety_concerns),
    )
