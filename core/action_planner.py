"""Module 5 — What should I do next?

A practical, ordered action plan built from the case state. Every step says
what to do, why it matters, which official website to use and what evidence to
keep. No mandatory waiting periods are invented: the only timelines mentioned
are ones found in the verified sources, and they are described as duties on the
other side or as targets, not as conditions the consumer must satisfy.
"""
from __future__ import annotations

from core.case_builder import describe_evidence
from core.intake import RELEVANT_EVIDENCE


def _L(lang, en, hi):
    return hi if lang == "hi" else en


def build_action_plan(case: dict, lang: str = "en") -> list[dict]:
    fl = case["flags"]
    cat = case["dispute"]["category"]
    platform = case["parties"].get("platform") or _L(lang, "the platform", "प्लेटफ़ॉर्म")
    have = describe_evidence([e for e in RELEVANT_EVIDENCE.get(cat, []) if e in case.get("evidence", [])], lang)
    missing = describe_evidence([e for e in RELEVANT_EVIDENCE.get(cat, []) if e not in case.get("evidence", [])], lang)
    steps: list[dict] = []

    def add(key, title, what, why, site, evidence, status="todo", sources=None):
        steps.append({"key": key, "title": title, "what": what, "why": why, "website": site, "evidence": evidence,
                      "status": status, "sources": sources or []})

    # 1. preserve evidence
    what_en = "Save copies of everything now, outside the app: " + (", ".join(have) if have else "invoice, payment proof, order page, photos") + "."
    what_hi = "अभी सब कुछ ऐप के बाहर सहेज लें: " + (", ".join(have) if have else "बिल, भुगतान प्रमाण, ऑर्डर पेज, फोटो") + "।"
    if missing:
        what_en += " Also try to obtain: " + ", ".join(missing) + "."
        what_hi += " यह भी प्राप्त करने का प्रयास करें: " + ", ".join(missing) + "।"
    if cat == "misleading_description":
        what_en += " Take a dated screenshot of the listing today in case it is edited."
        what_hi += " लिस्टिंग का आज ही दिनांकित स्क्रीनशॉट लें, ताकि बदलाव होने पर भी सबूत रहे।"
    if cat in ("damaged_on_delivery", "defective_product", "misleading_description"):
        what_en += " Keep the product and its packaging; do not repair or dispose of it."
        what_hi += " उत्पाद और उसकी पैकेजिंग संभालकर रखें; उसे ठीक न कराएँ और फेंकें नहीं।"
    add("preserve", _L(lang, "Preserve your evidence", "अपने सबूत सुरक्षित रखें"),
        _L(lang, what_en, what_hi),
        _L(lang, "Apps can change order pages and listings, and chats can disappear. Whoever decides your complaint will rely on documents, not memory.",
           "ऐप ऑर्डर पेज और लिस्टिंग बदल सकते हैं, और चैट गायब हो सकती है। आपकी शिकायत का निर्णय करने वाला दस्तावेज़ों पर भरोसा करेगा, याददाश्त पर नहीं।"),
        None, have + missing, "todo")

    # 2. written complaint to seller/platform
    done = not fl.get("no_complaint_yet")
    if done:
        what_en = (f"You have already complained. Now send the formal written complaint (NyayaSetu draft B) to {platform}'s grievance officer, quoting your "
                   "earlier ticket number, and copy the seller (draft A).")
        what_hi = (f"आप पहले ही शिकायत कर चुके हैं। अब {platform} के शिकायत अधिकारी को औपचारिक लिखित शिकायत (NyayaSetu मसौदा ख) भेजें, पिछला टिकट नंबर लिखें, "
                   "और विक्रेता को प्रतिलिपि दें (मसौदा क)।")
    else:
        what_en = f"Send NyayaSetu draft A to the seller and draft B to {platform}'s grievance officer, through the app's help/complaint section or by email."
        what_hi = f"NyayaSetu का मसौदा क विक्रेता को और मसौदा ख {platform} के शिकायत अधिकारी को ऐप के सहायता/शिकायत सेक्शन या ईमेल से भेजें।"
    add("written_complaint", _L(lang, "Escalate in writing to the seller and the platform's grievance officer", "विक्रेता और प्लेटफ़ॉर्म के शिकायत अधिकारी को लिखित शिकायत"),
        _L(lang, what_en, what_hi),
        _L(lang, "A written complaint creates a dated record and gives the other side a chance to fix the problem. The E-Commerce Rules require the platform's "
                 "grievance officer to acknowledge a complaint within 48 hours and redress it within one month — these are duties on the platform.",
           "लिखित शिकायत से दिनांकित रिकॉर्ड बनता है और दूसरे पक्ष को समस्या ठीक करने का अवसर मिलता है। ई-कॉमर्स नियमों के अनुसार प्लेटफ़ॉर्म के शिकायत अधिकारी को 48 घंटे "
           "में पावती देनी होती है और एक महीने में निवारण करना होता है — ये प्लेटफ़ॉर्म के कर्तव्य हैं।"),
        {"label": _L(lang, f"Grievance officer details are displayed on {platform}'s own website/app", f"शिकायत अधिकारी का विवरण {platform} की अपनी वेबसाइट/ऐप पर होता है"), "url": ""},
        [_L(lang, "Copy of what you sent and the date", "भेजी गई शिकायत की प्रति और तारीख"), _L(lang, "Acknowledgement / ticket number", "पावती / टिकट नंबर")],
        "partly_done" if done else "todo", ["ECOM_R4_GRIEVANCE", "ECOM_R5_3"])

    # 3. keep reference numbers
    add("keep_refs", _L(lang, "Keep every reference number and reply", "हर संदर्भ संख्या और उत्तर संभालें"),
        _L(lang, "Write down a simple log: date, how you contacted them, ticket number, name of the agent, what they said. Save emails as PDF.",
           "एक सरल लॉग बनाएँ: तारीख, संपर्क का माध्यम, टिकट नंबर, एजेंट का नाम, उन्होंने क्या कहा। ईमेल को PDF में सहेजें।"),
        _L(lang, "These references prove you tried to resolve the matter and show how long the other side took.",
           "ये संदर्भ साबित करते हैं कि आपने मामला सुलझाने का प्रयास किया और दिखाते हैं कि दूसरे पक्ष ने कितना समय लिया।"),
        None, [_L(lang, "Contact log", "संपर्क लॉग"), _L(lang, "Ticket numbers", "टिकट नंबर"), _L(lang, "Replies (emails / chat screenshots)", "उत्तर (ईमेल / चैट स्क्रीनशॉट)")],
        "partly_done" if case.get("complaint_ref") else "todo")

    # optional category-specific steps
    if cat == "non_delivery":
        add("proof_of_delivery", _L(lang, "Ask the platform for proof of delivery", "प्लेटफ़ॉर्म से डिलीवरी का प्रमाण माँगें"),
            _L(lang, "In writing, ask for the delivery photo, OTP verification record, delivery location and the delivery agent's details for your order.",
               "लिखित में अपने ऑर्डर के लिए डिलीवरी फोटो, OTP सत्यापन रिकॉर्ड, डिलीवरी स्थान और डिलीवरी एजेंट का विवरण माँगें।"),
            _L(lang, "The dispute turns on whether delivery happened; the platform holds that evidence.", "विवाद इस पर टिका है कि डिलीवरी हुई या नहीं; वह सबूत प्लेटफ़ॉर्म के पास है।"),
            None, [_L(lang, "Their reply", "उनका उत्तर"), _L(lang, "Tracking screenshot", "ट्रैकिंग स्क्रीनशॉट")], "todo")
    if cat == "incorrect_charge":
        add("bank_dispute", _L(lang, "Raise the duplicate debit with your bank / UPI app too", "दोहरी कटौती बैंक / UPI ऐप में भी उठाएँ"),
            _L(lang, "Use your bank's or payment app's dispute option for the extra debit and note its reference number.",
               "अतिरिक्त कटौती के लिए अपने बैंक या भुगतान ऐप में विवाद/शिकायत दर्ज करें और संदर्भ संख्या नोट करें।"),
            _L(lang, "If the extra amount never reached the merchant, only the payment provider can reverse it. Banking disputes are outside NyayaSetu's verified scope.",
               "अगर अतिरिक्त राशि व्यापारी तक पहुँची ही नहीं, तो केवल भुगतान प्रदाता ही उसे वापस कर सकता है। बैंकिंग विवाद NyayaSetu के सत्यापित दायरे से बाहर हैं।"),
            {"label": _L(lang, "Reserve Bank of India (check current complaint scheme)", "भारतीय रिज़र्व बैंक (वर्तमान शिकायत योजना देखें)"), "url": "https://www.rbi.org.in/"},
            [_L(lang, "Bank / UPI statement", "बैंक / UPI विवरण"), _L(lang, "Bank complaint reference", "बैंक शिकायत संदर्भ")], "todo", ["RBI_IOS_2026"])

    # 4. NCH
    add("nch", _L(lang, "If unresolved: register with the National Consumer Helpline", "समाधान न हो: राष्ट्रीय उपभोक्ता हेल्पलाइन में दर्ज करें"),
        _L(lang, "Register your grievance (NyayaSetu draft C) by calling 1915, on WhatsApp 8800001915, through the NCH or UMANG app, or online.",
           "अपनी शिकायत (NyayaSetu मसौदा ग) 1915 पर कॉल करके, व्हाट्सऐप 8800001915 पर, NCH या UMANG ऐप से, या ऑनलाइन दर्ज करें।"),
        _L(lang, "NCH is the Department of Consumer Affairs' pre-litigation grievance channel. Grievances against its partner (convergence) companies are "
                 "sent to them for resolution, and the portal says it may take up to 30 days to reach a conclusion. If your grievance is not resolved, you "
                 "can still approach the Consumer Commission. NyayaSetu found no rule in the sources it checked that makes NCH compulsory before going to a Commission.",
           "NCH उपभोक्ता मामले विभाग का मुकदमे-पूर्व शिकायत माध्यम है। इसकी सहयोगी (कन्वर्जेंस) कंपनियों से जुड़ी शिकायतें समाधान के लिए सीधे उन्हें भेजी जाती हैं, और पोर्टल के "
           "अनुसार निष्कर्ष तक पहुँचने में अधिकतम 30 दिन लग सकते हैं। समाधान न हो तो आप फिर भी उपभोक्ता आयोग जा सकते हैं। NyayaSetu को जाँचे गए "
           "स्रोतों में ऐसा कोई नियम नहीं मिला जो आयोग जाने से पहले NCH को अनिवार्य बनाता हो।"),
        {"label": "consumerhelpline.gov.in", "url": "https://consumerhelpline.gov.in/"},
        [_L(lang, "NCH docket / grievance number", "NCH डॉकेट / शिकायत संख्या"), _L(lang, "Company's reply via NCH", "NCH के ज़रिए कंपनी का उत्तर")], "todo", ["NCH"])

    if cat == "misleading_description":
        add("report_ad", _L(lang, "Optional: report the misleading listing to the authorities", "वैकल्पिक: भ्रामक लिस्टिंग की अधिकारियों को सूचना दें"),
            _L(lang, "If the listing is likely to mislead other buyers too, you can send a complaint in writing or electronically to the District Collector, the "
                     "regional Commissioner or the Central Consumer Protection Authority.",
               "अगर लिस्टिंग अन्य खरीदारों को भी गुमराह कर सकती है, तो आप ज़िला कलेक्टर, क्षेत्रीय आयुक्त या केंद्रीय उपभोक्ता संरक्षण प्राधिकरण को लिखित या इलेक्ट्रॉनिक शिकायत भेज सकते हैं।"),
            _L(lang, "This can stop the practice for everyone; it is separate from getting your own money back.", "इससे सबके लिए यह व्यवहार रुक सकता है; यह आपका पैसा वापस पाने से अलग है।"),
            {"label": _L(lang, "Department of Consumer Affairs", "उपभोक्ता मामले विभाग"), "url": "https://consumeraffairs.nic.in/"},
            [_L(lang, "Listing screenshot", "लिस्टिंग स्क्रीनशॉट")], "optional", ["CPA_17"])

    # 5. Consumer Commission via e-Jagriti
    band = fl.get("value_band")
    forum_en = {"district": "the District Consumer Commission", "state": "the State Commission", "national": "the National Commission"}.get(band, "the appropriate Consumer Commission")
    forum_hi = {"district": "ज़िला उपभोक्ता आयोग", "state": "राज्य आयोग", "national": "राष्ट्रीय आयोग"}.get(band, "उपयुक्त उपभोक्ता आयोग")
    caution_en = caution_hi = ""
    if fl.get("possible_commercial_purpose") or fl.get("limitation_risk"):
        caution_en = " Before this step, get legal advice — your case has a threshold issue (consumer status or time limit)."
        caution_hi = " इस कदम से पहले कानूनी सलाह लें — आपके मामले में एक प्रारंभिक मुद्दा है (उपभोक्ता स्थिति या समय सीमा)।"
    add("commission", _L(lang, f"If still unresolved: file before {forum_en} on e-Jagriti", f"फिर भी समाधान न हो: ई-जागृति पर {forum_hi} में दर्ज करें"),
        _L(lang, "Use NyayaSetu draft D to prepare, then file online on e-Jagriti, where you can upload documents, pay any fee and track the case. You can file "
                 "yourself; an advocate or a recognised consumer association can also help." + caution_en,
           "तैयारी के लिए NyayaSetu मसौदा घ का उपयोग करें, फिर ई-जागृति पर ऑनलाइन दर्ज करें, जहाँ दस्तावेज़ अपलोड, शुल्क भुगतान (यदि हो) और केस ट्रैक कर सकते हैं। आप स्वयं दर्ज "
           "कर सकते हैं; कोई अधिवक्ता या मान्यता प्राप्त उपभोक्ता संघ भी मदद कर सकता है।" + caution_hi),
        _L(lang, "The Commission can order a refund, replacement, compensation and costs if it finds in your favour. Complaints must normally be filed within 2 "
                 "years of the cause of action; no fee applies for value up to ₹5 lakh (check the portal).",
           "आयोग आपके पक्ष में पाए तो रिफंड, बदलाव, मुआवज़ा और खर्च का आदेश दे सकता है। शिकायत सामान्यतः वाद के कारण से 2 साल में दर्ज करनी होती है; ₹5 लाख तक कोई शुल्क नहीं (पोर्टल पर जाँचें)।"),
        {"label": "e-jagriti.gov.in", "url": "https://e-jagriti.gov.in/"},
        [_L(lang, "All documents above, indexed as annexures", "ऊपर के सभी दस्तावेज़, अनुलग्नक के रूप में क्रमबद्ध"),
         _L(lang, "Copies of your complaints and their replies", "आपकी शिकायतों और उनके उत्तरों की प्रतियाँ")],
        "todo", ["EJAGRITI", "CPA_34", "JUR_RULES_2021", "FEE_RULE_7", "CPA_69", "CPA_39"])
    return steps
