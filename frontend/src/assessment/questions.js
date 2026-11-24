// Phase 1 question bank: 6 multiple-choice questions per trade, in en / te / hi.
//
// Deliberately NO answer key here. Phase 1 does no scoring, and a correct-answer
// field shipped in frontend code is readable by anyone, so the key should live on
// the backend once scoring exists. Option positions are varied on purpose so the
// right answer is not always "A" when scoring is added.

const L = (en, te, hi) => ({ en, te, hi });

const opts = (...texts) =>
  texts.map((text, i) => ({ id: "abcd"[i], text }));

export const QUESTIONS = {
  Electrician: [
    {
      id: "el-1",
      text: L(
        "What is the safest first step before working on a socket or switch?",
        "సాకెట్ లేదా స్విచ్ మీద పని మొదలుపెట్టే ముందు అత్యంత సురక్షితమైన మొదటి చర్య ఏది?",
        "सॉकेट या स्विच पर काम शुरू करने से पहले सबसे सुरक्षित पहला कदम क्या है?"
      ),
      options: opts(
        L("Switch off only the wall switch", "గోడ మీద ఉన్న స్విచ్ మాత్రమే ఆఫ్ చేయడం", "सिर्फ़ दीवार का स्विच बंद करना"),
        L("Wear slippers and work carefully", "చెప్పులు వేసుకుని జాగ్రత్తగా పని చేయడం", "चप्पल पहनकर सावधानी से काम करना"),
        L(
          "Switch off the circuit at the MCB/main switch and confirm with a tester that it is dead",
          "MCB / మెయిన్ స్విచ్ దగ్గర సర్క్యూట్ ఆఫ్ చేసి, టెస్టర్‌తో కరెంట్ లేదని నిర్ధారించుకోవడం",
          "MCB / मेन स्विच से सर्किट बंद करना और टेस्टर से जाँचना कि करंट नहीं है"
        ),
        L("Ask someone to hold the wire", "ఎవరినైనా వైరు పట్టుకోమని చెప్పడం", "किसी से तार पकड़ने को कहना")
      ),
    },
    {
      id: "el-2",
      text: L(
        "Which device protects a circuit from overload and short circuit?",
        "ఓవర్‌లోడ్, షార్ట్ సర్క్యూట్ నుండి సర్క్యూట్‌ను ఏ పరికరం రక్షిస్తుంది?",
        "ओवरलोड और शॉर्ट सर्किट से सर्किट की सुरक्षा कौन-सा उपकरण करता है?"
      ),
      options: opts(
        L("Regulator", "రెగ్యులేటర్", "रेगुलेटर"),
        L("MCB (miniature circuit breaker)", "MCB (మినియేచర్ సర్క్యూట్ బ్రేకర్)", "MCB (मिनिएचर सर्किट ब्रेकर)"),
        L("Capacitor", "కెపాసిటర్", "कैपेसिटर"),
        L("Bulb holder", "బల్బ్ హోల్డర్", "बल्ब होल्डर")
      ),
    },
    {
      id: "el-3",
      text: L(
        "In household wiring, what colour is the earth wire usually?",
        "ఇంటి వైరింగ్‌లో ఎర్త్ వైరు సాధారణంగా ఏ రంగులో ఉంటుంది?",
        "घरेलू वायरिंग में अर्थ तार आमतौर पर किस रंग का होता है?"
      ),
      options: opts(
        L("Red", "ఎరుపు", "लाल"),
        L("Black", "నలుపు", "काला"),
        L("Blue", "నీలం", "नीला"),
        L("Green", "ఆకుపచ్చ", "हरा")
      ),
    },
    {
      id: "el-4",
      text: L(
        "Which tool is used to measure voltage and check continuity?",
        "వోల్టేజ్ కొలవడానికి, కంటిన్యూటీ చెక్ చేయడానికి ఏ పరికరం వాడతారు?",
        "वोल्टेज मापने और कंटिन्युटी जाँचने के लिए कौन-सा उपकरण इस्तेमाल होता है?"
      ),
      options: opts(
        L("Multimeter", "మల్టీమీటర్", "मल्टीमीटर"),
        L("Wire stripper", "వైర్ స్ట్రిప్పర్", "वायर स्ट्रिपर"),
        L("Pliers", "ప్లయర్", "प्लास"),
        L("Screwdriver", "స్క్రూడ్రైవర్", "पेचकस")
      ),
    },
    {
      id: "el-5",
      text: L(
        "A ceiling fan runs very slowly. Which part most commonly fails?",
        "సీలింగ్ ఫ్యాన్ చాలా నెమ్మదిగా తిరుగుతోంది. సాధారణంగా ఏ భాగం పాడవుతుంది?",
        "सीलिंग फैन बहुत धीमा चल रहा है। आमतौर पर कौन-सा हिस्सा खराब होता है?"
      ),
      options: opts(
        L("Blade nut", "బ్లేడ్ నట్", "ब्लेड का नट"),
        L("Ceiling hook", "సీలింగ్ హుక్", "सीलिंग हुक"),
        L("Capacitor", "కెపాసిటర్", "कैपेसिटर"),
        L("Switch plate", "స్విచ్ ప్లేట్", "स्विच प्लेट")
      ),
    },
    {
      id: "el-6",
      text: L(
        "What is the main purpose of earthing?",
        "ఎర్తింగ్ ముఖ్య ఉద్దేశ్యం ఏమిటి?",
        "अर्थिंग का मुख्य उद्देश्य क्या है?"
      ),
      options: opts(
        L("To increase the voltage", "వోల్టేజ్ పెంచడం", "वोल्टेज बढ़ाना"),
        L(
          "To send leakage current safely to the ground and prevent shocks",
          "లీకేజీ కరెంట్‌ను సురక్షితంగా భూమిలోకి పంపి షాక్ రాకుండా కాపాడటం",
          "लीकेज करंट को सुरक्षित रूप से ज़मीन में भेजकर झटके से बचाना"
        ),
        L("To make the bulb glow brighter", "బల్బ్ ఎక్కువ వెలిగేలా చేయడం", "बल्ब को ज़्यादा तेज़ जलाना"),
        L("To reduce the electricity bill", "కరెంట్ బిల్లు తగ్గించడం", "बिजली का बिल कम करना")
      ),
    },
  ],

  Plumber: [
    {
      id: "pl-1",
      text: L(
        "Which tape is used to seal threaded pipe joints?",
        "థ్రెడ్ ఉన్న పైపు జాయింట్లను సీల్ చేయడానికి ఏ టేప్ వాడతారు?",
        "धागेदार (थ्रेडेड) पाइप जोड़ों को सील करने के लिए कौन-सा टेप इस्तेमाल होता है?"
      ),
      options: opts(
        L("Insulation tape", "ఇన్సులేషన్ టేప్", "इंसुलेशन टेप"),
        L("PTFE (Teflon) tape", "PTFE (టెఫ్లాన్) టేప్", "PTFE (टेफ़लॉन) टेप"),
        L("Masking tape", "మాస్కింగ్ టేప్", "मास्किंग टेप"),
        L("Cello tape", "సెల్లో టేప్", "सेलो टेप")
      ),
    },
    {
      id: "pl-2",
      text: L(
        "Water keeps dripping from a tap spout even when it is closed. What is the most common cause?",
        "నల్లా మూసినా కూడా స్పౌట్ నుండి నీరు కారుతోంది. అత్యంత సాధారణ కారణం ఏమిటి?",
        "नल बंद करने के बाद भी टोंटी से पानी टपक रहा है। सबसे आम कारण क्या है?"
      ),
      options: opts(
        L("A worn-out washer or cartridge", "అరిగిపోయిన వాషర్ లేదా కార్ట్రిడ్జ్", "घिसा हुआ वॉशर या कार्ट्रिज"),
        L("A small overhead tank", "చిన్న ఓవర్‌హెడ్ ట్యాంక్", "छोटी ऊपरी टंकी"),
        L("A cracked bucket", "పగిలిన బకెట్", "फटी बाल्टी"),
        L("The paint on the wall", "గోడకు వేసిన రంగు", "दीवार का रंग")
      ),
    },
    {
      id: "pl-3",
      text: L(
        "Which tool is used to tighten or loosen round pipes and fittings?",
        "గుండ్రని పైపులు, ఫిట్టింగ్‌లను బిగించడానికి లేదా విప్పడానికి ఏ టూల్ వాడతారు?",
        "गोल पाइप और फिटिंग कसने या खोलने के लिए कौन-सा औज़ार इस्तेमाल होता है?"
      ),
      options: opts(
        L("Spirit level", "స్పిరిట్ లెవెల్", "स्पिरिट लेवल"),
        L("Trowel", "తాపీ (ట్రోవెల్)", "करनी (ट्रॉवेल)"),
        L("Voltage tester", "వోల్టేజ్ టెస్టర్", "वोल्टेज टेस्टर"),
        L("Pipe wrench", "పైప్ రెంచ్", "पाइप रिंच")
      ),
    },
    {
      id: "pl-4",
      text: L(
        "What is the purpose of a P-trap (water seal) under a sink?",
        "సింక్ కింద P-ట్రాప్ (వాటర్ సీల్) ఉద్దేశ్యం ఏమిటి?",
        "सिंक के नीचे पी-ट्रैप (वॉटर सील) का उद्देश्य क्या है?"
      ),
      options: opts(
        L("To increase water pressure", "నీటి ఒత్తిడి పెంచడం", "पानी का दबाव बढ़ाना"),
        L("To heat the water", "నీటిని వేడి చేయడం", "पानी गरम करना"),
        L(
          "To hold water that stops drain smell and gas from coming back up",
          "నీటిని నిలిపి ఉంచి డ్రైన్ నుండి దుర్వాసన, గ్యాస్ తిరిగి రాకుండా ఆపడం",
          "पानी रोककर नाली की बदबू और गैस को वापस आने से रोकना"
        ),
        L("To filter the water", "నీటిని ఫిల్టర్ చేయడం", "पानी साफ़ करना")
      ),
    },
    {
      id: "pl-5",
      text: L(
        "Which pipe is commonly used for hot water supply?",
        "వేడి నీటి సరఫరాకు సాధారణంగా ఏ పైపు వాడతారు?",
        "गरम पानी की सप्लाई के लिए आमतौर पर कौन-सा पाइप इस्तेमाल होता है?"
      ),
      options: opts(
        L("Plain PVC drainage pipe", "సాధారణ PVC డ్రైనేజీ పైపు", "साधारण PVC ड्रेनेज पाइप"),
        L("CPVC pipe", "CPVC పైపు", "CPVC पाइप"),
        L("Rubber garden hose", "రబ్బరు గార్డెన్ గొట్టం", "रबर का गार्डन पाइप"),
        L("Earthen pipe", "మట్టి పైపు", "मिट्टी का पाइप")
      ),
    },
    {
      id: "pl-6",
      text: L(
        "What should you do first before replacing a tap or fitting?",
        "నల్లా లేదా ఫిట్టింగ్ మార్చే ముందు మొదట ఏం చేయాలి?",
        "नल या फिटिंग बदलने से पहले सबसे पहले क्या करना चाहिए?"
      ),
      options: opts(
        L(
          "Close the water supply valve and drain the remaining water",
          "నీటి సరఫరా వాల్వ్ మూసి, మిగిలిన నీటిని వదిలేయడం",
          "पानी का सप्लाई वाल्व बंद करना और बचा हुआ पानी निकालना"
        ),
        L("Open all the taps", "అన్ని నల్లాలు తెరవడం", "सभी नल खोल देना"),
        L("Cut the pipe immediately", "వెంటనే పైపు కోయడం", "तुरंत पाइप काट देना"),
        L("Increase the water pressure", "నీటి ఒత్తిడి పెంచడం", "पानी का दबाव बढ़ाना")
      ),
    },
  ],
};
