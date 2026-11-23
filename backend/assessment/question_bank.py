"""Static occupational-knowledge question bank for Electricians and Plumbers.

Telugu and Hindi text are drafts and require review by fluent speakers before
being used with workers. Questions assess knowledge and reasoning, not practical
competence or certification. Safety-critical misconceptions are flagged
separately from numerical rubric scores.
"""

from dataclasses import dataclass
from typing import Mapping

from .adaptive_engine import Difficulty, Question, Trade


@dataclass(frozen=True)
class AssessmentQuestion(Question):
    """A question compatible with the adaptive engine plus assessment content."""

    trade: Trade
    skill_tag: str
    question_text_en: str
    question_text_te: str
    question_text_hi: str
    expected_concepts: tuple[str, ...]
    rubric_json: dict[str, str]
    safety_critical: bool
    active: bool
    telugu_review_required: bool = True
    hindi_review_required: bool = True


QuestionGroups = Mapping[Difficulty, tuple[AssessmentQuestion, ...]]
TradeQuestionBank = Mapping[Trade, QuestionGroups]


def _rubric(question_text: str, concepts: tuple[str, ...]) -> dict[str, str]:
    """Build a 0–4 rubric tied to this question's scenario and concepts."""
    concept_list = "; ".join(concepts)
    first_concept = concepts[0]
    return {
        "0": (
            f"For “{question_text}”, gives no relevant concept or gives an "
            "entirely incorrect answer."
        ),
        "1": (
            f"For “{question_text}”, names or partly describes {first_concept}, "
            "but does not explain how it answers the situation."
        ),
        "2": (
            f"For “{question_text}”, correctly explains some but not all of "
            f"these points: {concept_list}; the missing point(s) leave the "
            "occupational situation only partly addressed."
        ),
        "3": (
            f"For “{question_text}”, accurately applies all of these expected "
            f"points to the situation: {concept_list}."
        ),
        "4": (
            f"For “{question_text}”, accurately applies and connects all of "
            f"these points: {concept_list}; explains why the conclusion or "
            "next check follows, and avoids unsupported conclusions."
        ),
    }


def _question(
    question_id: str,
    trade: Trade,
    difficulty: Difficulty,
    skill_tag: str,
    question_text_en: str,
    question_text_te: str,
    question_text_hi: str,
    expected_concepts: tuple[str, ...],
    safety_critical: bool = False,
) -> AssessmentQuestion:
    return AssessmentQuestion(
        question_id=question_id,
        difficulty=difficulty,
        trade=trade,
        skill_tag=skill_tag,
        question_text_en=question_text_en,
        question_text_te=question_text_te,
        question_text_hi=question_text_hi,
        expected_concepts=expected_concepts,
        rubric_json=_rubric(question_text_en, expected_concepts),
        safety_critical=safety_critical,
        active=True,
        telugu_review_required=True,
        hindi_review_required=True,
    )


_ELECTRICIAN_QUESTIONS = (
    _question(
        "E01", Trade.ELECTRICIAN, Difficulty.FOUNDATIONAL, "Basic electrical tools",
        "Which tool would you choose to tighten a small terminal screw, and why?",
        "చిన్న టెర్మినల్ స్క్రూను బిగించడానికి ఏ పనిముట్టును ఎంచుకుంటారు? ఎందుకు?",
        "छोटे टर्मिनल स्क्रू को कसने के लिए आप कौन-सा औज़ार चुनेंगे और क्यों?",
        ("screwdriver with a suitable tip", "correct fit helps avoid damaging the screw"),
    ),
    _question(
        "E02", Trade.ELECTRICIAN, Difficulty.FOUNDATIONAL, "Switch and socket",
        "What is the purpose of a switch and a socket in a home electrical system?",
        "ఇంటి విద్యుత్ వ్యవస్థలో స్విచ్ మరియు సాకెట్ ఉపయోగం ఏమిటి?",
        "घर की विद्युत व्यवस्था में स्विच और सॉकेट का क्या काम होता है?",
        ("switch controls the electrical supply to a load", "socket provides a connection for an appliance"),
        False,
    ),
    _question(
        "E03", Trade.ELECTRICIAN, Difficulty.FOUNDATIONAL, "Electrical safety",
        "Before working on an electrical circuit, what must be checked to make sure it is safe?",
        "విద్యుత్ సర్క్యూట్‌పై పని చేసే ముందు ఏ భద్రతా విషయాన్ని నిర్ధారించాలి?",
        "विद्युत सर्किट पर काम करने से पहले, सुरक्षा सुनिश्चित करने के लिए क्या जाँचना चाहिए?",
        ("supply must be isolated", "absence of voltage must be verified with a suitable tester"),
        True,
    ),
    _question(
        "E04", Trade.ELECTRICIAN, Difficulty.FOUNDATIONAL, "Wire identification",
        "Why should you identify a wire using a suitable tester and circuit information instead of relying only on its colour?",
        "వైరు రంగును మాత్రమే నమ్మకుండా పరీక్షించి, సర్క్యూట్ వివరాలు చూసి గుర్తించడం ఎందుకు ముఖ్యం?",
        "तार की पहचान केवल उसके रंग से करने के बजाय उपयुक्त परीक्षक और सर्किट की जानकारी से क्यों करनी चाहिए?",
        ("colours may be incorrect or inconsistent", "verify conductor function before making a connection"),
        True,
    ),
    _question(
        "E05", Trade.ELECTRICIAN, Difficulty.INTERMEDIATE, "Fan installation",
        "What should be checked in the ceiling support and electrical supply before a fan is installed?",
        "ఫ్యాన్ అమర్చే ముందు పైకప్పు ఆధారం మరియు విద్యుత్ సరఫరాలో ఏమి చూడాలి?",
        "पंखा लगाने से पहले छत के सहारे और बिजली की आपूर्ति में क्या जाँचना चाहिए?",
        ("support is suitable for the fan load", "supply and controls are appropriate", "circuit is isolated before work"),
        True,
    ),
    _question(
        "E06", Trade.ELECTRICIAN, Difficulty.INTERMEDIATE, "Wiring repair",
        "A light stops working after a connection becomes loose. What should be considered before deciding the cause?",
        "ఒక కనెక్షన్ వదులైన తర్వాత లైట్ పనిచేయడం ఆగింది. కారణం నిర్ణయించే ముందు ఏమి పరిశీలించాలి?",
        "कनेक्शन ढीला होने के बाद एक लाइट काम करना बंद कर देती है। कारण तय करने से पहले किन बातों पर विचार करना चाहिए?",
        ("isolate and verify the circuit before inspection", "check the connection and conductor condition", "consider other circuit faults"),
        True,
    ),
    _question(
        "E07", Trade.ELECTRICIAN, Difficulty.INTERMEDIATE, "Circuit breaker",
        "What does a circuit breaker do, and why should it not be replaced with a higher-rated one just to stop trips?",
        "సర్క్యూట్ బ్రేకర్ పని ఏమిటి? ట్రిప్ అవకుండా చేయడానికి ఎక్కువ రేటింగ్ ఉన్న బ్రేకర్‌ను ఎందుకు పెట్టకూడదు?",
        "सर्किट ब्रेकर क्या काम करता है, और बार-बार ट्रिप होने से रोकने के लिए उसे अधिक रेटिंग वाले ब्रेकर से क्यों नहीं बदलना चाहिए?",
        ("breaker protects a circuit against excessive current", "rating must suit the circuit and conductors", "tripping cause needs investigation"),
        True,
    ),
    _question(
        "E08", Trade.ELECTRICIAN, Difficulty.INTERMEDIATE, "Overloading",
        "Several appliances are used on one circuit, and the breaker trips. How can you tell whether overloading or another fault may be causing it?",
        "ఒకే సర్క్యూట్‌పై చాలా పరికరాలు వాడినప్పుడు బ్రేకర్ ట్రిప్ అవుతోంది. అధిక లోడ్‌ను ఇతర లోపాల నుంచి ఎలా గుర్తిస్తారు?",
        "एक ही सर्किट पर कई उपकरण चलाने पर ब्रेकर ट्रिप हो जाता है। आप कैसे पता करेंगे कि इसका कारण अधिक लोड है या कोई दूसरी खराबी?",
        ("consider the combined load and circuit rating", "observe whether trips relate to simultaneous appliance use", "do not ignore wiring faults"),
        True,
    ),
    _question(
        "E09", Trade.ELECTRICIAN, Difficulty.ADVANCED, "Short circuit",
        "A breaker trips immediately when a circuit is switched on. What could indicate a short circuit, and what should happen next?",
        "సర్క్యూట్ ఆన్ చేసిన వెంటనే బ్రేకర్ ట్రిప్ అవుతోంది. షార్ట్ సర్క్యూట్‌కు ఏది సూచన కావచ్చు? తర్వాత ఏమి చేయాలి?",
        "सर्किट चालू करते ही ब्रेकर ट्रिप हो जाता है। शॉर्ट सर्किट का संकेत क्या हो सकता है, और इसके बाद क्या करना चाहिए?",
        ("a fault may create an unintended low-resistance current path", "keep the circuit isolated", "qualified diagnosis is needed before restoring supply"),
        True,
    ),
    _question(
        "E10", Trade.ELECTRICIAN, Difficulty.ADVANCED, "Earthing",
        "How does earthing help reduce electric-shock risk, and why is it not a substitute for circuit protection?",
        "ఎర్తింగ్ విద్యుత్ షాక్ ప్రమాదాన్ని ఎలా తగ్గిస్తుంది? అది సర్క్యూట్ రక్షణకు బదులు ఎందుకు కాదు?",
        "अर्थिंग से बिजली का झटका लगने का जोखिम कैसे कम होता है, और यह सर्किट सुरक्षा का विकल्प क्यों नहीं है?",
        ("earthing provides a fault-current path", "protective devices must disconnect a fault", "earthing and protection serve related but different roles"),
        True,
    ),
    _question(
        "E11", Trade.ELECTRICIAN, Difficulty.ADVANCED, "Repeated breaker trips",
        "A breaker trips repeatedly even after some appliances are unplugged. What causes should be considered before resetting it again?",
        "కొన్ని పరికరాలు తీసివేసినా బ్రేకర్ మళ్లీ మళ్లీ ట్రిప్ అవుతోంది. తిరిగి ఆన్ చేసే ముందు ఏ కారణాలు చూడాలి?",
        "कुछ उपकरणों के प्लग निकालने के बाद भी ब्रेकर बार-बार ट्रिप होता है। उसे फिर से चालू करने से पहले किन कारणों पर विचार करना चाहिए?",
        ("possible overload", "possible short circuit or earth fault", "damaged appliance or wiring", "repeated trips require investigation rather than repeated resetting"),
        True,
    ),
    _question(
        "E12", Trade.ELECTRICIAN, Difficulty.ADVANCED, "Electrical fault diagnosis",
        "Power in a room cuts out intermittently, and one outlet feels warm. What information and safety steps matter before diagnosing the fault?",
        "ఒక గదిలో విద్యుత్ అప్పుడప్పుడు పోతోంది, సాకెట్ వేడిగా ఉంది. లోపాన్ని గుర్తించే ముందు ఏ సమాచారం, భద్రతా చర్యలు ముఖ్యం?",
        "एक कमरे की बिजली बीच-बीच में चली जाती है और एक सॉकेट गर्म लगता है। खराबी की जाँच से पहले कौन-सी जानकारी और सुरक्षा सावधानियाँ ज़रूरी हैं?",
        ("stop use and isolate the affected circuit when safe to do so", "record when and where the symptom occurs", "consider loose or overloaded connections", "qualified inspection is required for a potentially hazardous fault"),
        True,
    ),
)


_PLUMBER_QUESTIONS = (
    _question(
        "P01", Trade.PLUMBER, Difficulty.FOUNDATIONAL, "Plumbing tools",
        "Which tool would you choose to grip and turn a threaded pipe fitting, and why?",
        "థ్రెడ్ ఉన్న పైపు ఫిట్టింగ్‌ను పట్టుకుని తిప్పడానికి ఏ పనిముట్టును ఎంచుకుంటారు? ఎందుకు?",
        "थ्रेड वाले पाइप फिटिंग को पकड़कर घुमाने के लिए आप कौन-सा औज़ार चुनेंगे और क्यों?",
        ("pipe wrench or suitable pipe-gripping tool", "jaw size and grip should suit the fitting"),
    ),
    _question(
        "P02", Trade.PLUMBER, Difficulty.FOUNDATIONAL, "Pipe types",
        "What information would help you choose a suitable pipe type for a water supply line?",
        "నీటి సరఫరా పైపుకు సరైన రకం ఎంచుకోవడానికి ఏ సమాచారం ఉపయోగపడుతుంది?",
        "पानी की सप्लाई लाइन के लिए सही प्रकार का पाइप चुनने में कौन-सी जानकारी मदद करेगी?",
        ("intended use and water type", "pressure and temperature rating", "local requirements and compatibility"),
    ),
    _question(
        "P03", Trade.PLUMBER, Difficulty.FOUNDATIONAL, "Leakage",
        "You notice water near a pipe joint. What simple checks can help locate the source of the leak?",
        "పైపు జాయింట్ దగ్గర నీరు కనిపించింది. లీక్ ఎక్కడి నుంచి వస్తోందో తెలుసుకోవడానికి ఏ సాధారణ తనిఖీలు చేయవచ్చు?",
        "आपको पाइप के जोड़ के पास पानी दिखता है। रिसाव का स्रोत पता करने के लिए कौन-सी आसान जाँच कर सकते हैं?",
        ("dry the area and observe where water reappears", "inspect the joint and nearby pipe", "consider whether water may be running from above"),
    ),
    _question(
        "P04", Trade.PLUMBER, Difficulty.FOUNDATIONAL, "Water supply",
        "What should you find out about the water supply before investigating a tap that has no flow?",
        "ట్యాప్‌లో నీరు రాకపోతే కారణం చూసే ముందు నీటి సరఫరా గురించి ఏమి తెలుసుకోవాలి?",
        "नल में पानी न आने की जाँच से पहले पानी की सप्लाई के बारे में क्या पता करना चाहिए?",
        ("whether the supply is available to the building", "whether the local shutoff is open", "whether other outlets are also affected"),
    ),
    _question(
        "P05", Trade.PLUMBER, Difficulty.INTERMEDIATE, "Tap installation",
        "What should be checked to help prevent leaks and damage when a tap is installed?",
        "ట్యాప్ అమర్చేటప్పుడు లీక్ మరియు నష్టం రాకుండా ఏ విషయాలు చూడాలి?",
        "नल लगाते समय रिसाव और नुकसान से बचने के लिए क्या जाँचना चाहिए?",
        ("tap matches the mounting and connection", "seals are correctly placed", "connections are not overtightened", "check for leaks after supply is restored"),
    ),
    _question(
        "P06", Trade.PLUMBER, Difficulty.INTERMEDIATE, "Pipe joint repair",
        "A pipe joint leaks after repair. What possible causes should be considered?",
        "మరమ్మత్తు తర్వాత పైపు జాయింట్ లీక్ అవుతోంది. ఏ కారణాలను పరిశీలించాలి?",
        "मरम्मत के बाद पाइप के जोड़ से पानी रिस रहा है। किन संभावित कारणों पर विचार करना चाहिए?",
        ("incorrect or damaged seal", "misaligned or damaged threads", "unsuitable joint material", "excessive or insufficient tightening"),
    ),
    _question(
        "P07", Trade.PLUMBER, Difficulty.INTERMEDIATE, "Drain blockage",
        "A sink drains slowly. What signs can help distinguish a local blockage from a wider drainage problem?",
        "సింక్‌లో నీరు నెమ్మదిగా పోతోంది. స్థానిక అడ్డంకిని పెద్ద డ్రైనేజ్ సమస్య నుంచి ఎలా గుర్తించవచ్చు?",
        "सिंक का पानी धीरे निकलता है। कौन-से संकेत स्थानीय रुकावट और बड़ी ड्रेनेज समस्या में अंतर बताने में मदद करेंगे?",
        ("check whether one fixture or several are affected", "observe gurgling or backflow", "consider blockage location and safe access"),
    ),
    _question(
        "P08", Trade.PLUMBER, Difficulty.INTERMEDIATE, "Water pressure",
        "Several taps have low flow. What checks can help determine whether the cause is supply pressure or a local restriction?",
        "చాలా ట్యాప్‌లలో నీటి ప్రవాహం తక్కువగా ఉంది. సరఫరా ఒత్తిడి సమస్యా లేదా స్థానిక అడ్డంకా అని ఎలా తెలుసుకోవచ్చు?",
        "कई नलों में पानी का बहाव कम है। यह सप्लाई के दबाव की समस्या है या किसी एक जगह की रुकावट, यह जानने के लिए क्या जाँच करेंगे?",
        ("compare flow at multiple outlets", "check whether the issue is building-wide", "consider a blocked filter or valve at an individual outlet"),
    ),
    _question(
        "P09", Trade.PLUMBER, Difficulty.ADVANCED, "Hidden leakage",
        "A water meter moves when all taps are closed, but no water is visible. What might this indicate, and what evidence should be collected?",
        "ట్యాప్‌లు మూసి ఉన్నా నీటి మీటర్ కదులుతోంది, కానీ నీరు కనిపించడం లేదు. ఇది దేనిని సూచించవచ్చు? ఏ ఆధారాలు సేకరించాలి?",
        "सभी नल बंद होने पर भी पानी का मीटर चल रहा है, लेकिन पानी दिखाई नहीं देता। इससे क्या संकेत मिल सकता है और कौन-से सबूत जुटाने चाहिए?",
        ("possible hidden leak", "record meter movement with outlets closed", "look for damp areas or unexplained consumption", "avoid damaging walls before locating the likely route"),
    ),
    _question(
        "P10", Trade.PLUMBER, Difficulty.ADVANCED, "Pipe selection",
        "A pipe is being selected for a hot-water line. Which service conditions and compatibility details should guide the choice?",
        "వేడి నీటి లైన్ కోసం పైపు ఎంచుకుంటున్నారు. ఎంపికకు ఏ వినియోగ పరిస్థితులు, సరిపోలిక వివరాలు మార్గనిర్దేశం చేయాలి?",
        "गर्म पानी की लाइन के लिए पाइप चुना जा रहा है। चुनाव में किन उपयोग की स्थितियों और अनुकूलता की बातों को ध्यान में रखना चाहिए?",
        ("temperature and pressure ratings", "pipe material suitability for the water and use", "compatible fittings and joining method", "applicable local requirements"),
    ),
    _question(
        "P11", Trade.PLUMBER, Difficulty.ADVANCED, "Repeated leakage",
        "A repaired joint leaks again soon. What underlying causes should be considered instead of repeating the same repair?",
        "మరమ్మత్తు చేసిన జాయింట్ కొద్ది రోజుల్లో మళ్లీ లీక్ అవుతోంది. అదే మరమ్మత్తు మళ్లీ చేయకుండా ఏ మూల కారణాలు చూడాలి?",
        "मरम्मत किया हुआ जोड़ जल्द ही फिर से रिसने लगता है। वही मरम्मत दोहराने के बजाय किन मूल कारणों पर विचार करना चाहिए?",
        ("pipe movement or poor support", "corrosion or damaged pipe", "pressure or water-hammer effects", "incorrect material or joining method"),
    ),
    _question(
        "P12", Trade.PLUMBER, Difficulty.ADVANCED, "Drainage fault diagnosis",
        "Several fixtures drain slowly, and one makes a gurgling sound. What signs can help identify the likely drainage fault and how much of the system it affects?",
        "చాలా చోట్ల నీరు నెమ్మదిగా పోతోంది, ఒక చోట గలగల శబ్దం వస్తోంది. డ్రైనేజ్ లోపం, దాని పరిధి తెలుసుకోవడానికి ఏవి గమనించాలి?",
        "कई जगहों से पानी धीरे निकलता है और एक जगह गड़गड़ाहट की आवाज़ आती है। संभावित ड्रेनेज खराबी और उससे प्रभावित हिस्से का पता लगाने के लिए कौन-से संकेत देखें?",
        ("which fixtures are affected and in what order", "gurgling or backflow symptoms", "whether the issue points to a shared drain or vent", "protect people from contaminated water and use qualified help when needed"),
        True,
    ),
)


def _group_by_difficulty(
    questions: tuple[AssessmentQuestion, ...],
) -> dict[Difficulty, tuple[AssessmentQuestion, ...]]:
    return {
        difficulty: tuple(
            question for question in questions if question.difficulty == difficulty
        )
        for difficulty in (
            Difficulty.FOUNDATIONAL,
            Difficulty.INTERMEDIATE,
            Difficulty.ADVANCED,
        )
    }


QUESTION_BANK: TradeQuestionBank = {
    Trade.ELECTRICIAN: _group_by_difficulty(_ELECTRICIAN_QUESTIONS),
    Trade.PLUMBER: _group_by_difficulty(_PLUMBER_QUESTIONS),
}


def validate_question_bank(bank: TradeQuestionBank = QUESTION_BANK) -> None:
    """Validate trade totals, difficulty counts, IDs, and field assignments."""
    expected_trades = {
        Trade.ELECTRICIAN: tuple(f"E{number:02d}" for number in range(1, 13)),
        Trade.PLUMBER: tuple(f"P{number:02d}" for number in range(1, 13)),
    }
    if set(bank) != set(expected_trades):
        raise ValueError("Question bank must contain exactly Electrician and Plumber.")

    all_ids: set[str] = set()
    for trade, expected_ids in expected_trades.items():
        groups = bank[trade]
        if set(groups) != set(Difficulty):
            raise ValueError(f"{trade.value} must have all three difficulty groups.")

        trade_questions: list[AssessmentQuestion] = []
        for difficulty in (
            Difficulty.FOUNDATIONAL,
            Difficulty.INTERMEDIATE,
            Difficulty.ADVANCED,
        ):
            questions = groups[difficulty]
            if len(questions) != 4:
                raise ValueError(
                    f"{trade.value} must have exactly four {difficulty.value} questions."
                )
            for question in questions:
                if not isinstance(question, AssessmentQuestion):
                    raise ValueError("Every bank entry must be an AssessmentQuestion.")
                if question.trade != trade:
                    raise ValueError(f"{question.question_id} has an incorrect trade assignment.")
                if question.difficulty != difficulty:
                    raise ValueError(
                        f"{question.question_id} has an incorrect difficulty assignment."
                    )
                if question.question_id in all_ids:
                    raise ValueError(f"Duplicate question ID: {question.question_id}.")
                all_ids.add(question.question_id)
                if not question.skill_tag or not question.question_text_en:
                    raise ValueError(f"{question.question_id} is missing question content.")
                if not question.question_text_te or not question.telugu_review_required:
                    raise ValueError(
                        f"{question.question_id} Telugu wording must be marked for review."
                    )
                if not question.question_text_hi:
                    raise ValueError(
                        f"{question.question_id} is missing Hindi question text."
                    )
                if not question.hindi_review_required:
                    raise ValueError(
                        f"{question.question_id} Hindi wording must be marked for review."
                    )
                if not question.expected_concepts:
                    raise ValueError(f"{question.question_id} has no expected concepts.")
                if set(question.rubric_json) != {"0", "1", "2", "3", "4"}:
                    raise ValueError(f"{question.question_id} rubric must cover scores 0 through 4.")
                if not isinstance(question.safety_critical, bool) or not isinstance(
                    question.active, bool
                ):
                    raise ValueError(
                        f"{question.question_id} safety_critical and active must be booleans."
                    )
                trade_questions.append(question)

        if len(trade_questions) != 12:
            raise ValueError(f"{trade.value} must have exactly 12 questions.")
        if tuple(question.question_id for question in trade_questions) != expected_ids:
            raise ValueError(f"{trade.value} IDs must be in the specified order.")

    if len(all_ids) != 24:
        raise ValueError("Question bank must contain exactly 24 unique question IDs.")


validate_question_bank()