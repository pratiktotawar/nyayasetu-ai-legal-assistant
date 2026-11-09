"""Module 1 — AI Legal Intake.

Turns a consumer's free-text story (English, Hindi or Hinglish) into slots,
then asks only the follow-up questions that are relevant to the dispute type
and still unanswered — one question at a time.

Everything here is deterministic (regular expressions + keyword scoring) so the
app works in DEMO MODE with no API. When a live LLM is configured, the LLM can
fill slots the rules missed; every slot records where its value came from
("rule", "answer", "llm" or "user-edited").
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from utils.language import detect_language, format_inr, normalize_digits

# --------------------------------------------------------------------------
# Dispute categories
# --------------------------------------------------------------------------
CATEGORIES = {
    "damaged_on_delivery": {"en": "Product delivered damaged", "hi": "क्षतिग्रस्त उत्पाद की डिलीवरी"},
    "defective_product": {"en": "Defective product / stopped working", "hi": "दोषपूर्ण उत्पाद / काम करना बंद"},
    "non_delivery": {"en": "Order not delivered", "hi": "ऑर्डर डिलीवर नहीं हुआ"},
    "misleading_description": {"en": "Product not as advertised / misleading listing", "hi": "विज्ञापन के अनुसार नहीं / भ्रामक विवरण"},
    "incorrect_charge": {"en": "Incorrect or extra charge", "hi": "गलत या अतिरिक्त कटौती"},
    "refund_not_received": {"en": "Refund not received", "hi": "रिफंड नहीं मिला"},
    "unknown": {"en": "Not yet clear", "hi": "अभी स्पष्ट नहीं"},
}

CATEGORY_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "damaged_on_delivery": [
        (r"arriv\w* damaged", 3), (r"deliver\w* damaged", 3), (r"\bdamaged\b", 2), (r"\bbroken\b", 2),
        (r"\bcrack(ed|s)?\b", 2), (r"\bdent(ed)?\b", 1.5), (r"shattered", 2), (r"torn", 1),
        (r"टूट", 2.5), (r"क्षतिग्रस्त", 3), (r"फटा", 1.5), (r"\btoota\b|\btuta\b|\btoot gay", 2.5),
    ],
    "defective_product": [
        (r"stopped working", 3), (r"not working", 2.5), (r"\bdefect", 2.5), (r"malfunction", 2.5),
        (r"\bfaulty\b", 2.5), (r"error code", 2), (r"does ?n[o']t work", 2.5), (r"won'?t (turn|switch) on", 2.5),
        (r"major defect", 3), (r"खराब", 2.5), (r"काम नहीं", 2.5), (r"बंद हो ?ग", 2), (r"दोष", 2),
        (r"\bkharab\b", 2.5), (r"kaam nahi", 2.5), (r"line aa rahi|lines? (on|in) (the )?(screen|display)", 2.5),
        (r"chal nahi (raha|rahi)|band ho gaya|on nahi ho", 2.5),
    ],
    "non_delivery": [
        (r"never (received|got|arrived)", 3.5), (r"not (been )?delivered", 3), (r"did(n'?t| not) (receive|get)", 3),
        (r"(shows?|marked|showing|status (says|is)) (as )?['\"]?delivered", 3.5), (r"never delivered", 3.5),
        (r"not received", 2.5), (r"नहीं मिला", 3), (r"नहीं मिली", 3), (r"डिलीवर नहीं", 3),
        (r"डिलीवर['’\"]? दिखा", 3.5), (r"डिलीवर.{0,15}दिखा", 3.5), (r"mila nahi|nahi mila", 3),
    ],
    "misleading_description": [
        (r"wrong (size|item|product|colou?r|model|variant)", 3), (r"different (product|item|model) (was )?(delivered|sent)", 3),
        (r"galat (saman|product|item|size)", 3), (r"गलत (सामान|उत्पाद|साइज़|साइज)", 3),
        (r"advertis", 2.5), (r"listing (said|says|claimed|showed)", 3), (r"as described", 1.5),
        (r"not as (described|shown|advertised)", 3.5), (r"(claimed|promised) (it|that|to)", 2),
        (r"does(n'?t| not) have (the|that|this|a)? ?(feature|function)", 3), (r"feature", 1.5),
        (r"misleading", 3), (r"description (said|says)", 3), (r"fake", 1.5), (r"विज्ञापन", 3),
        (r"भ्रामक", 3), (r"बताया गया था", 2), (r"विवरण", 1.5), (r"फीचर", 2),
    ],
    "incorrect_charge": [
        (r"charged (me )?twice", 4), (r"double[- ]?charged", 4), (r"charged (me )?(extra|more)", 3.5),
        (r"incorrect(ly)? charg", 4), (r"wrong(ly)? charg", 3.5), (r"over-?charg", 3.5),
        (r"extra (amount|charge|money)", 3), (r"(debited|deducted) (twice|two times|extra)", 4),
        (r"\bcharged\b", 1.5), (r"\bdebited\b", 1.5), (r"\bdeducted\b", 1.5),
        (r"दो बार (पैसे )?(कट|कटे)", 4), (r"ज़?्यादा पैसे", 3), (r"अतिरिक्त (शुल्क|पैसे)", 3), (r"गलत (शुल्क|कटौती)", 3.5),
        (r"do baar (paise )?kat", 4),
    ],
    "refund_not_received": [
        (r"refund", 2), (r"money back", 2), (r"not (been )?refunded", 3), (r"refund (not|never) (received|credited|came)", 3.5),
        (r"reimburse", 1.5), (r"postpon", 1), (r"रिफंड", 2), (r"पैसे? वापस", 2), (r"पैसा वापस", 2),
        (r"paisa wapas|paise wapas", 2), (r"(not|n't) accepting (the )?return|return nahi le", 2),
    ],
}

# Product-condition categories take precedence over a pure refund complaint,
# because the refund is usually the remedy sought for the underlying problem.
PRIMARY_PRIORITY = ["incorrect_charge", "non_delivery", "misleading_description",
                    "damaged_on_delivery", "defective_product", "refund_not_received"]

# --------------------------------------------------------------------------
# Evidence types
# --------------------------------------------------------------------------
EVIDENCE_TYPES: dict[str, dict[str, Any]] = {
    "invoice": {"en": "Invoice / bill", "hi": "चालान / बिल",
                "kw": [r"invoice", r"\bbill\b", r"tax invoice", r"cash memo", r"बिल", r"चालान", r"इनवॉइस"]},
    "payment_proof": {"en": "Payment proof (receipt, bank/UPI statement)", "hi": "भुगतान का प्रमाण (रसीद, बैंक/UPI विवरण)",
                      "kw": [r"payment (receipt|proof|confirmation|screenshot)", r"bank statement", r"upi (screenshot|receipt|transaction|statement)",
                             r"transaction (id|receipt|screenshot)", r"\breceipt\b", r"रसीद", r"भुगतान (की|का) (रसीद|प्रमाण|स्क्रीनशॉट)", r"बैंक स्टेटमेंट"]},
    "order_screenshot": {"en": "Order page / confirmation (screenshot or email)", "hi": "ऑर्डर पेज / पुष्टि (स्क्रीनशॉट या ईमेल)",
                         "kw": [r"order (confirmation|page|details|screenshot)", r"confirmation (email|sms|message)", r"ऑर्डर (की|का) (पुष्टि|स्क्रीनशॉट)"]},
    "tracking_screenshot": {"en": "Tracking / delivery-status screenshot", "hi": "ट्रैकिंग / डिलीवरी स्थिति का स्क्रीनशॉट",
                            "kw": [r"tracking", r"delivery status", r"ट्रैकिंग", r"डिलीवरी (की )?स्थिति"]},
    "listing_screenshot": {"en": "Product listing / advertisement screenshot", "hi": "उत्पाद सूची / विज्ञापन का स्क्रीनशॉट",
                           "kw": [r"(screenshot|copy|capture|photo)s? of (the |my |original )*(product |item )?(listing|product page|page|advertisement|\bad\b|description)",
                                  r"listing screenshot", r"saved the (listing|product page|ad)", r"विज्ञापन का स्क्रीनशॉट", r"लिस्टिंग"]},
    "product_photos": {"en": "Photographs of the product / damage", "hi": "उत्पाद / क्षति की तस्वीरें",
                       "kw": [r"\bphoto", r"\bpicture", r"\bimages?\b", r"\bpics?\b", r"फोटो", r"तस्वीर"]},
    "unboxing_video": {"en": "Unboxing / product video", "hi": "अनबॉक्सिंग / उत्पाद का वीडियो",
                       "kw": [r"unboxing", r"\bvideo", r"वीडियो"]},
    "emails": {"en": "Emails with seller / platform", "hi": "विक्रेता / प्लेटफ़ॉर्म के साथ ईमेल",
               "kw": [r"\bemails?\b", r"\be-mails?\b", r"ईमेल"]},
    "chat_transcripts": {"en": "Chat transcripts / messages with customer care", "hi": "ग्राहक सेवा के साथ चैट / संदेश",
                         "kw": [r"\bchats?\b", r"chat (transcript|screenshot|history)", r"whatsapp (messages|chat)", r"चैट", r"मैसेज"]},
    "complaint_reference": {"en": "Complaint / ticket reference number", "hi": "शिकायत / टिकट संदर्भ संख्या",
                            "kw": [r"ticket (number|no|id)\b", r"complaint (number|no|id|reference)\b", r"reference (number|no)\b", r"टिकट", r"शिकायत (संख्या|नंबर)"]},
    "warranty_card": {"en": "Warranty card / warranty terms", "hi": "वारंटी कार्ड / वारंटी शर्तें",
                      "kw": [r"warranty", r"guarantee card", r"वारंटी", r"गारंटी कार्ड"]},
    "technician_report": {"en": "Technician / service-centre report (job sheet)", "hi": "तकनीशियन / सर्विस सेंटर रिपोर्ट (जॉब शीट)",
                          "kw": [r"job ?sheet", r"technician('s)? report", r"service (centre|center) report", r"inspection report", r"जॉब शीट", r"तकनीशियन (की )?रिपोर्ट"]},
    "call_records": {"en": "Call records / call logs", "hi": "कॉल रिकॉर्ड / कॉल लॉग",
                     "kw": [r"call (log|record|recording|history)", r"कॉल (रिकॉर्ड|लॉग)"]},
}

RELEVANT_EVIDENCE = {
    "damaged_on_delivery": ["invoice", "payment_proof", "product_photos", "unboxing_video", "complaint_reference", "chat_transcripts"],
    "defective_product": ["invoice", "payment_proof", "warranty_card", "technician_report", "product_photos", "complaint_reference"],
    "non_delivery": ["payment_proof", "order_screenshot", "tracking_screenshot", "complaint_reference", "chat_transcripts"],
    "misleading_description": ["listing_screenshot", "invoice", "product_photos", "complaint_reference", "chat_transcripts"],
    "incorrect_charge": ["payment_proof", "invoice", "order_screenshot", "complaint_reference", "chat_transcripts"],
    "refund_not_received": ["payment_proof", "order_screenshot", "complaint_reference", "emails", "chat_transcripts"],
    "unknown": ["invoice", "payment_proof", "order_screenshot", "complaint_reference"],
}

RESOLUTIONS = {
    "refund": {"en": "Refund", "hi": "रिफंड",
               "kw": [r"refund", r"money back", r"return (my|the) money", r"रिफंड", r"पैसे? वापस", r"पैसा वापस", r"paisa wapas", r"reversal", r"revers"]},
    "replacement": {"en": "Replacement", "hi": "बदलकर नया उत्पाद",
                    "kw": [r"replace", r"exchange", r"new (one|piece|unit)", r"बदल", r"रिप्लेसमेंट"]},
    "repair": {"en": "Repair", "hi": "मरम्मत", "kw": [r"\brepair (it|the|my|this)\b", r"\bget it repaired\b", r"\bwant .{0,20}repair", r"\bfix (it|the|my)\b",
                                                   r"^\s*repair\b", r"मरम्मत", r"ठीक कर"]},
    "delivery": {"en": "Deliver the ordered product", "hi": "ऑर्डर किया गया उत्पाद डिलीवर किया जाए",
                 "kw": [r"deliver (it|the product|my order)", r"send (it|the product)", r"डिलीवर कर"]},
    "compensation": {"en": "Compensation for inconvenience / loss", "hi": "असुविधा / नुकसान का मुआवज़ा",
                     "kw": [r"compensat", r"damages for", r"मुआवज", r"हर्जान"]},
}

KNOWN_PLATFORMS = [
    "Amazon", "Flipkart", "Myntra", "Meesho", "Ajio", "Nykaa", "Snapdeal", "JioMart", "Tata CLiQ", "Tata Neu",
    "Croma", "Reliance Digital", "BigBasket", "Blinkit", "Zepto", "Swiggy Instamart", "Swiggy", "Zomato",
    "FirstCry", "Lenskart", "Pepperfry", "Urban Ladder", "IndiaMART", "Shopsy", "Paytm", "PhonePe",
    "Vijay Sales", "Purplle", "Decathlon", "boAt", "Mamaearth",
]
HINDI_PLATFORM_ALIASES = {"अमेज़न": "Amazon", "अमेजन": "Amazon", "फ्लिपकार्ट": "Flipkart", "मीशो": "Meesho",
                          "मिंत्रा": "Myntra", "स्विगी": "Swiggy", "ज़ोमैटो": "Zomato", "जियोमार्ट": "JioMart"}

GENERIC_PRODUCT_WORDS = {"online order", "order", "something", "product", "item", "thing", "stuff", "it", "an online order",
                         "some product", "something online", "सामान", "कुछ"}

# --------------------------------------------------------------------------
# Questions
# --------------------------------------------------------------------------
QUESTIONS: dict[str, dict[str, Any]] = {
    "category": {
        "type": "category",
        "en": "Which of these best describes your problem?",
        "hi": "इनमें से कौन-सा आपकी समस्या का सबसे अच्छा वर्णन करता है?",
    },
    "product": {"type": "text", "en": "What product did you buy? (For example: mobile phone, washing machine, shoes.)",
                "hi": "आपने कौन-सा उत्पाद खरीदा था? (जैसे: मोबाइल फ़ोन, वॉशिंग मशीन, जूते)"},
    "amount": {"type": "amount", "en": "How much did you pay, in rupees?", "hi": "आपने कितने रुपये चुकाए?"},
    "platform_seller": {
        "type": "platform",
        "en": "Which website or app did you buy it from? If you know the seller's name (it is on the invoice or order page), please add it — e.g. “ShopNest, seller: Gupta Electronics”.",
        "hi": "आपने किस वेबसाइट या ऐप से खरीदा? अगर विक्रेता का नाम पता है (बिल या ऑर्डर पेज पर होता है), तो वह भी लिखें — जैसे “ShopNest, विक्रेता: गुप्ता इलेक्ट्रॉनिक्स”।",
    },
    "order_id": {"type": "order_id", "en": "What is the Order ID? It is on the order page or the confirmation email.",
                 "hi": "ऑर्डर आईडी क्या है? यह ऑर्डर पेज या पुष्टि ईमेल पर होती है।"},
    "purchase_date": {"type": "date", "en": "On what date did you place the order (or pay)? An approximate date is fine.",
                      "hi": "आपने किस तारीख को ऑर्डर किया (या भुगतान किया)? अनुमानित तारीख भी चलेगी।"},
    "delivery_date": {"type": "date", "en": "On what date was it delivered?", "hi": "यह किस तारीख को डिलीवर हुआ?"},
    "issue_details": {"type": "text", "en": "Please describe the problem in a sentence or two.",
                      "hi": "कृपया समस्या एक-दो वाक्यों में बताइए।"},
    "complaint_history": {
        "type": "complaint",
        "en": "Have you already complained to the seller or the platform? If yes: when, how (app, email, call, chat), and what did they say? Reply “no” if you have not complained yet.",
        "hi": "क्या आपने पहले ही विक्रेता या प्लेटफ़ॉर्म से शिकायत की है? अगर हाँ: कब, कैसे (ऐप, ईमेल, कॉल, चैट), और उन्होंने क्या कहा? अगर अभी शिकायत नहीं की है तो “नहीं” लिखें।",
    },
    "complaint_ref": {"type": "ref", "en": "Do you have a ticket or complaint reference number? Please type it (or skip).",
                      "hi": "क्या आपके पास टिकट या शिकायत संदर्भ संख्या है? कृपया लिखें (या छोड़ दें)।"},
    "evidence": {"type": "evidence", "en": "Which of these records do you have? Select all that apply — and keep the originals safe.",
                 "hi": "इनमें से कौन-से रिकॉर्ड आपके पास हैं? जो भी लागू हों, सब चुनें — और मूल प्रतियाँ सुरक्षित रखें।"},
    "desired_resolution": {"type": "resolution", "en": "What outcome do you want — refund, replacement, repair, or something else?",
                           "hi": "आप क्या समाधान चाहते हैं — रिफंड, बदलाव, मरम्मत, या कुछ और?"},
    "claim_amount": {"type": "claim", "en": "How much money are you asking to get back?", "hi": "आप कितनी राशि वापस माँग रहे हैं?"},
    "purpose": {"type": "purpose", "en": "Did you buy this for personal or household use, or for resale / business? (This affects whether consumer law applies.)",
                "hi": "क्या आपने यह निजी या घरेलू उपयोग के लिए खरीदा था, या दोबारा बेचने / व्यापार के लिए? (इससे तय होता है कि उपभोक्ता कानून लागू होगा या नहीं।)"},
    "consumer_details": {
        "type": "identity",
        "en": "Last question: what name and city/district should appear on your complaint? (For example: “Priya Sharma, Pune”.) Please do NOT share Aadhaar, PAN, card numbers, bank passwords or OTPs — they are not needed.",
        "hi": "अंतिम प्रश्न: शिकायत पर कौन-सा नाम और शहर/ज़िला लिखा जाए? (जैसे: “प्रिया शर्मा, पुणे”) कृपया आधार, पैन, कार्ड नंबर, बैंक पासवर्ड या OTP साझा न करें — इनकी ज़रूरत नहीं है।",
    },
}

ISSUE_QUESTION_BY_CATEGORY = {
    "damaged_on_delivery": {"en": "What exactly was damaged, and when did you first notice it (at delivery or on opening the box)?",
                            "hi": "ठीक-ठीक क्या क्षतिग्रस्त था, और आपने पहली बार कब देखा (डिलीवरी के समय या डिब्बा खोलने पर)?"},
    "defective_product": {"en": "What is the defect, when did it start, and is the product under warranty? Has a technician inspected it?",
                          "hi": "क्या खराबी है, कब शुरू हुई, और क्या उत्पाद वारंटी में है? क्या किसी तकनीशियन ने जाँच की है?"},
    "non_delivery": {"en": "Did anyone at your address receive a parcel, and were you asked for (or did you share) any delivery OTP?",
                     "hi": "क्या आपके पते पर किसी ने पार्सल लिया, और क्या आपसे कोई डिलीवरी OTP माँगा गया (या आपने साझा किया)?"},
    "misleading_description": {"en": "What exactly did the listing or advertisement claim, and how is the product you received different?",
                               "hi": "लिस्टिंग या विज्ञापन में ठीक-ठीक क्या दावा किया गया था, और मिला हुआ उत्पाद उससे कैसे अलग है?"},
    "incorrect_charge": {"en": "What amount should you have been charged, what amount was actually charged, and how did you pay (card, UPI, wallet, cash on delivery)?",
                         "hi": "आपसे कितनी राशि ली जानी चाहिए थी, असल में कितनी ली गई, और आपने कैसे भुगतान किया (कार्ड, UPI, वॉलेट, कैश ऑन डिलीवरी)?"},
    "refund_not_received": {"en": "Why was the refund due (return picked up, order cancelled, refund approved)? On what date was it approved or promised?",
                            "hi": "रिफंड क्यों बनता था (रिटर्न उठाया गया, ऑर्डर रद्द हुआ, रिफंड स्वीकृत हुआ)? यह किस तारीख को स्वीकृत या वादा किया गया?"},
}

DELIVERY_QUESTION_NON_DELIVERY = {"en": "On what date does the app or website show the order as “delivered”?",
                                  "hi": "ऐप या वेबसाइट पर ऑर्डर किस तारीख को “डिलीवर” दिखाया गया है?"}

FLOW = {
    "damaged_on_delivery": ["product", "amount", "platform_seller", "order_id", "purchase_date", "delivery_date", "issue_details",
                            "complaint_history", "complaint_ref", "evidence", "desired_resolution", "claim_amount", "purpose", "consumer_details"],
    "defective_product": ["product", "amount", "platform_seller", "order_id", "purchase_date", "delivery_date", "issue_details",
                          "complaint_history", "complaint_ref", "evidence", "desired_resolution", "claim_amount", "purpose", "consumer_details"],
    "non_delivery": ["product", "amount", "platform_seller", "order_id", "purchase_date", "delivery_date", "issue_details",
                     "complaint_history", "complaint_ref", "evidence", "desired_resolution", "claim_amount", "consumer_details"],
    "misleading_description": ["product", "amount", "platform_seller", "order_id", "purchase_date", "issue_details",
                               "complaint_history", "complaint_ref", "evidence", "desired_resolution", "claim_amount", "purpose", "consumer_details"],
    "incorrect_charge": ["product", "amount", "issue_details", "platform_seller", "order_id", "purchase_date",
                         "complaint_history", "complaint_ref", "evidence", "desired_resolution", "claim_amount", "consumer_details"],
    "refund_not_received": ["product", "amount", "platform_seller", "order_id", "purchase_date", "issue_details",
                            "complaint_history", "complaint_ref", "evidence", "desired_resolution", "claim_amount", "consumer_details"],
}

FULL_RE = re.compile(r"\b(full|entire|whole|all of it|complete|total|everything)\b|पूरा|पूरी|पूरे|सारा|सारी|\b(poora|pura|poori|puri|sara|saara)\b", re.I)
YES_RE = re.compile(r"^\s*(yes|yeah|yep|correct|right|ok|okay|haan|han|ha|ji|हाँ|हां|जी|सही)\b", re.I)
EXCESS_RE = re.compile(r"\b(excess|extra|difference|overcharge[d]?|additional)\b|अतिरिक्त|ज़्यादा|ज्यादा|अधिक", re.I)


def parse_claim_amount(text: str) -> float | None:
    """An explicit rupee amount in a claim answer ("₹48,000", "4800", "Rs 3,500 for 2 items")."""
    found = parse_amounts(text)
    if found:
        return found[0].value
    clean = normalize_digits(text)
    # a bare number is accepted only when it looks like money, not a count ("4 phones", "2 items")
    for m in re.finditer(r"(?<![\w-])(\d{1,3}(?:,\d{2,3})+|\d{3,9})(?:\.\d{1,2})?(?![\w-])", clean):
        tail = clean[m.end():m.end() + 12].lower()
        if re.search(r"(order|id|ticket|ref|no\.?|number|#)\s*[:#-]?\s*$", clean[max(0, m.start() - 14):m.start()], re.I):
            continue  # an order / ticket number, not money
        if re.match(r"\s*(days?|weeks?|months?|years?|items?|pieces?|pcs|units?|phones?|times?|%)", tail):
            continue
        try:
            return float(m.group(0).replace(",", ""))
        except ValueError:
            continue
    return None


SKIP_RE = re.compile(r"^\s*(skip|pass|n/?a|na|none of (these|this)|don'?t know|dont know|do not know|not sure|no idea|i don'?t remember|can'?t remember|"
                     r"पता नहीं|नहीं पता|मालूम नहीं|याद नहीं|छोड़ें|छोड़ो|skip karo|pata nahi)\s*[.!]*\s*$", re.I)
BUILD_RE = re.compile(r"^\s*(build( my case)?( now)?|done|that'?s all|that is all|finish|generate|बस|हो गया|मामला बनाएँ|मामला बनाओ)\s*[.!]*\s*$", re.I)
NO_RE = re.compile(r"^\s*(no|nope|not yet|no,? i have not|no i haven'?t|i haven'?t|नहीं|अभी नहीं|nahi|nahin)\b", re.I)
NONE_RE = re.compile(r"^\s*(none|nothing|no records?|कुछ नहीं|कोई नहीं|kuch nahi)\s*[.!]*\s*$", re.I)

# --------------------------------------------------------------------------
# Privacy: redact sensitive identifiers before anything is stored
# --------------------------------------------------------------------------
_VERHOEFF_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
               [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
               [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
               [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VERHOEFF_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
               [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
               [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def _verhoeff_ok(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def _luhn_ok(num: str) -> bool:
    total, alt = 0, False
    for ch in reversed(num):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def redact_sensitive(text: str) -> tuple[str, list[str]]:
    """Mask Aadhaar, PAN, card numbers, OTPs and passwords. Returns (text, kinds_found)."""
    found: list[str] = []
    out = text

    def _aadhaar(m):
        digits = re.sub(r"\D", "", m.group(0))
        if digits[0] not in "01" and _verhoeff_ok(digits):
            found.append("Aadhaar number")
            return "[REDACTED-AADHAAR]"
        return m.group(0)

    out = re.sub(r"(?<![\w-])\d{4}[ -]?\d{4}[ -]?\d{4}(?![\w-])", _aadhaar, out)
    # any 12-digit number written right after the word Aadhaar is masked even if the checksum fails
    if re.search(r"(aadhaa?r|आधार)\D{0,15}\d{4}[ -]?\d{4}[ -]?\d{4}", out, re.I):
        found.append("Aadhaar number")
        out = re.sub(r"((?:aadhaa?r|आधार)\D{0,15})\d{4}[ -]?\d{4}[ -]?\d{4}", r"\1[REDACTED-AADHAAR]", out, flags=re.I)

    def _card(m):
        digits = re.sub(r"\D", "", m.group(0))
        if _luhn_ok(digits):
            found.append("card number")
            return "[REDACTED-CARD]"
        return m.group(0)

    out = re.sub(r"(?<![\w-])(?:\d{4}[ -]?){3}\d{4}(?![\w-])", _card, out)
    if re.search(r"\b[A-Z]{5}\d{4}[A-Z]\b", out):
        found.append("PAN")
        out = re.sub(r"\b[A-Z]{5}\d{4}[A-Z]\b", "[REDACTED-PAN]", out)
    secret_res = [r"\b(otp|cvv|upi pin|pin)\b(\s*(?:is|was|:|-|=|no\.?)?\s*)\d{3,8}\b",
                  r"\b(password|passcode|पासवर्ड)\b(\s*(?:is|was|:|-|=|है)\s*)\S+"]
    for rx in secret_res:
        if re.search(rx, out, re.I):
            found.append("OTP / PIN / password")
            out = re.sub(rx, r"\1\2[REDACTED]", out, flags=re.I)
    return out, sorted(set(found))


# --------------------------------------------------------------------------
# Low-level parsers
# --------------------------------------------------------------------------
_MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                            "september", "october", "november", "december"])}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS.update({"sept": 9})
_MONTHS_HI = {"जनवरी": 1, "फ़रवरी": 2, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "अप्रेल": 4, "मई": 5, "जून": 6, "जुलाई": 7,
              "अगस्त": 8, "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "अक्तूबर": 10, "नवंबर": 11, "नवम्बर": 11,
              "दिसंबर": 12, "दिसम्बर": 12}
_MONTH_ALT = "|".join(sorted(list(_MONTHS.keys()) + list(_MONTHS_HI.keys()), key=len, reverse=True))
_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                 "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a couple of": 2, "couple of": 2, "few": 3,
                 "a few": 3, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "छः": 6, "सात": 7,
                 "आठ": 8, "नौ": 9, "दस": 10}


def _month_num(token: str) -> int | None:
    t = token.lower().strip(".")
    return _MONTHS.get(t) or _MONTHS_HI.get(token)


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


@dataclass
class FoundDate:
    iso: str
    approx: bool | str  # False, True (relative/approximate) or "month" (only month and year known)
    raw: str
    start: int


def parse_dates(text: str, today: date) -> list[FoundDate]:
    text = normalize_digits(text)
    found: list[FoundDate] = []
    used: list[tuple[int, int]] = []

    def _add(d: date | None, approx: bool, m: re.Match):
        if not d:
            return
        if any(not (m.end() <= a or m.start() >= b) for a, b in used):
            return
        used.append((m.start(), m.end()))
        found.append(FoundDate(d.isoformat(), approx, m.group(0).strip(), m.start()))

    def _infer_year(month: int, day: int) -> int:
        candidate = _safe_date(today.year, month, day)
        if candidate and candidate > today + timedelta(days=2):
            return today.year - 1
        return today.year

    # 12 October 2026 / 12th Oct / 12 अक्टूबर 2026
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s\-]+({_MONTH_ALT})\.?,?[\s\-]*(\d{{4}})?", text, re.I):
        mon = _month_num(m.group(2))
        if not mon:
            continue
        day = int(m.group(1))
        year = int(m.group(3)) if m.group(3) else _infer_year(mon, day)
        _add(_safe_date(year, mon, day), m.group(3) is None, m)
    # October 12, 2026
    for m in re.finditer(rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b,?\s*(\d{{4}})?", text, re.I):
        mon = _month_num(m.group(1))
        if not mon:
            continue
        day = int(m.group(2))
        if day > 31:
            continue
        year = int(m.group(3)) if m.group(3) else _infer_year(mon, day)
        _add(_safe_date(year, mon, day), m.group(3) is None, m)
    # 2026-10-12
    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text):
        _add(_safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3))), False, m)
    # 12/10/2026 or 12-10-26 (Indian day-first convention)
    for m in re.finditer(r"\b(\d{1,2})[/\.\-](\d{1,2})[/\.\-](\d{2,4})\b", text):
        y = int(m.group(3))
        y = y + 2000 if y < 100 else y
        _add(_safe_date(y, int(m.group(2)), int(m.group(1))), False, m)
    # March 2024 (month + year only)
    for m in re.finditer(rf"\b(?:in\s+)?({_MONTH_ALT})\.?,?\s+(\d{{4}})\b", text, re.I):
        mon = _month_num(m.group(1))
        if mon:
            _add(_safe_date(int(m.group(2)), mon, 1), "month", m)  # only the month is known
    # relative English
    num_alt = "|".join(sorted((k for k in _NUMBER_WORDS if re.match(r"[a-z]", k)), key=len, reverse=True))
    for m in re.finditer(rf"\b(\d+|{num_alt})\s+(day|week|month|year)s?\s+(ago|back|before)\b", text, re.I):
        n = int(m.group(1)) if m.group(1).isdigit() else _NUMBER_WORDS.get(m.group(1).lower(), 1)
        unit = m.group(2).lower()
        delta = {"day": n, "week": 7 * n, "month": 30 * n, "year": 365 * n}[unit]
        _add(today - timedelta(days=delta), True, m)
    for m in re.finditer(r"\b(yesterday|today|last week|last month)\b", text, re.I):
        delta = {"yesterday": 1, "today": 0, "last week": 7, "last month": 30}[m.group(1).lower()]
        _add(today - timedelta(days=delta), m.group(1).lower() not in ("yesterday", "today"), m)
    # relative Hindi / Hinglish
    hi_nums = "|".join(sorted((k for k in _NUMBER_WORDS if not re.match(r"[a-z]", k)), key=len, reverse=True))
    for m in re.finditer(rf"(\d+|{hi_nums})\s*(दिन|हफ़्ते|हफ्ते|हफ़्ता|हफ्ता|सप्ताह|महीने|महीना|साल)\s*(पहले|पूर्व)", text):
        n = int(m.group(1)) if m.group(1).isdigit() else _NUMBER_WORDS.get(m.group(1), 1)
        unit = m.group(2)
        mult = 1 if unit == "दिन" else 7 if unit in ("हफ़्ते", "हफ्ते", "हफ़्ता", "हफ्ता", "सप्ताह") else 365 if unit == "साल" else 30
        _add(today - timedelta(days=n * mult), True, m)
    for m in re.finditer(r"\b(\d+)\s*(din|hafte|hafta|mahine|mahina|saal)\s*(pehle|pahle)\b", text, re.I):
        unit = m.group(2).lower()
        mult = 1 if unit == "din" else 7 if unit.startswith("haft") else 365 if unit == "saal" else 30
        _add(today - timedelta(days=int(m.group(1)) * mult), True, m)
    found.sort(key=lambda f: f.start)
    return found


_AMOUNT_UNITS = {"lakh": 100000, "lakhs": 100000, "lac": 100000, "lacs": 100000, "लाख": 100000,
                 "crore": 10000000, "crores": 10000000, "करोड़": 10000000, "k": 1000, "thousand": 1000, "हज़ार": 1000, "हजार": 1000}
_CUR = r"(?:₹|rs\.?|inr|rupees?|रु\.?|रुपये|रुपए)"


@dataclass
class FoundAmount:
    value: float
    start: int
    context: str


def parse_amounts(text: str) -> list[FoundAmount]:
    text = normalize_digits(text)
    found: list[FoundAmount] = []
    spans: list[tuple[int, int]] = []
    unit_alt = "|".join(sorted(_AMOUNT_UNITS, key=len, reverse=True))
    patterns = [
        rf"{_CUR}\s*([\d,]+(?:\.\d+)?)\s*({unit_alt})?\b",
        rf"([\d,]+(?:\.\d+)?)\s*({unit_alt})?\s*(?:{_CUR}|/-)",
        rf"(?:worth|costing|priced at|price of|paid|for)\s+([\d,]+(?:\.\d+)?)\s*({unit_alt})\b",
        # bare numbers in a price context: "for 2499", "worth 1,200", Hinglish "15000 ka laptop"
        r"(?:worth|costing|priced at|paid|for)\s+([\d,]{3,9})(?![\d,]*\s*(?:days?|weeks?|months?|years?|am|pm|times?|items?|pieces?|pcs|units?)\b)()\b",
        r"\b([\d,]{3,9})()\s+(?:ka|ki|ke|का|की|के)\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            if any(not (m.end() <= a or m.start() >= b) for a, b in spans):
                continue
            raw = m.group(1).replace(",", "")
            if not raw or raw == ".":
                continue
            try:
                val = float(raw)
            except ValueError:
                continue
            unit = (m.group(2) or "").lower() if m.lastindex and m.lastindex >= 2 else ""
            if unit:
                val *= _AMOUNT_UNITS.get(unit, _AMOUNT_UNITS.get(m.group(2), 1))
            if val <= 0:
                continue
            spans.append((m.start(), m.end()))
            ctx = text[max(0, m.start() - 40): m.start()].lower()
            found.append(FoundAmount(val, m.start(), ctx))
    found.sort(key=lambda a: a.start)
    return found


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?।])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p and p.strip()]


def _first_match(patterns: list[str], text: str) -> re.Match | None:
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m
    return None


def classify(text: str) -> dict[str, float]:
    low = normalize_digits(text).lower()
    scores = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        s = 0.0
        for pat, w in kws:
            if re.search(pat, low, re.I):
                s += w
        if s:
            scores[cat] = s
    return scores


def choose_category(scores: dict[str, float]) -> tuple[str, list[str]]:
    if not scores:
        return "unknown", []
    strong = {c: s for c, s in scores.items() if s >= 2.5}
    if not strong:
        best = max(scores, key=scores.get)
        return (best if scores[best] >= 2 else "unknown"), []
    # incorrect_charge needs a strong signal of its own
    ordered = [c for c in PRIMARY_PRIORITY if c in strong]
    # if a non-refund category is strong, it is primary
    non_refund = [c for c in ordered if c != "refund_not_received"]
    if non_refund:
        primary = max(non_refund, key=lambda c: (strong[c], -PRIMARY_PRIORITY.index(c)))
    else:
        primary = ordered[0]
    secondary = [c for c in ordered if c != primary]
    return primary, secondary


def detect_evidence(text: str) -> list[str]:
    low = text.lower()
    out = []
    for key, spec in EVIDENCE_TYPES.items():
        if any(re.search(p, low, re.I) for p in spec["kw"]):
            out.append(key)
    # a "screenshot" of the listing counts as listing evidence; a generic screenshot as order screenshot
    if re.search(r"screenshot|स्क्रीनशॉट", low) and not any(k in out for k in ("listing_screenshot", "tracking_screenshot", "order_screenshot", "chat_transcripts", "payment_proof")):
        out.append("order_screenshot")
    return out


def detect_resolutions(text: str) -> list[str]:
    out = []
    for key, spec in RESOLUTIONS.items():
        if any(re.search(p, text, re.I) for p in spec["kw"]):
            out.append(key)
    return out


def detect_platform(text: str) -> str | None:
    for p in KNOWN_PLATFORMS:
        if re.search(rf"(?<![A-Za-z]){re.escape(p)}(?![A-Za-z])", text, re.I):
            return p
    for alias, p in HINDI_PLATFORM_ALIASES.items():
        if alias in text:
            return p
    m = re.search(r"\b(?:from|on|via|through|using)\s+(?:the\s+)?([A-Z][A-Za-z0-9&]+(?:\s[A-Z][A-Za-z0-9&]+)?)\s+(?:app|website|site|marketplace|platform)\b", text)
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Za-z][A-Za-z0-9\-]+\.(?:com|in|co\.in|shop))\b", text)
    if m:
        return m.group(1)
    m = re.search(r"([A-Za-z][A-Za-z0-9]+)\s+(?:ऐप|वेबसाइट)", text)
    if m:
        return m.group(1)
    return None


def detect_seller(text: str) -> str | None:
    m = re.search(r"\bseller(?:'s name)?\s*(?:is|was|:|-|named|called|name is)\s*([A-Z0-9][\w&\.\-']*(?:\s+[A-Z0-9&][\w&\.\-']*){0,4})", text)
    if m:
        return m.group(1).strip(" .,")
    m = re.search(r"(?:sold by|seller)\s+([A-Z][\w&\.\-']*(?:\s+[A-Z&][\w&\.\-']*){0,4})", text)
    if m:
        return m.group(1).strip(" .,")
    m = re.search(r"विक्रेता\s*(?:का नाम)?\s*(?:है|:|-)?\s*([^\s,।.]+(?:\s[^\s,।.]+){0,3})", text)
    if m and m.group(1) not in ("ने", "से", "को", "का", "की", "है"):
        return m.group(1).strip()
    return None


def detect_order_id(text: str) -> str | None:
    text = normalize_digits(text)
    m = re.search(r"\border\s*(?:id|no\.?|number|#)?\s*(?:is|:|#|-)?\s*([A-Z0-9][A-Z0-9\-/]{4,})", text, re.I)
    if m and re.search(r"\d", m.group(1)):
        return m.group(1).strip("-/.")
    m = re.search(r"(?:ऑर्डर|आर्डर)\s*(?:आईडी|आई\.डी\.|नंबर|संख्या)?\s*(?:है|:|#|-)?\s*([A-Z0-9][A-Z0-9\-/]{4,})", text, re.I)
    if m and re.search(r"\d", m.group(1)):
        return m.group(1).strip("-/.")
    for pat in (r"\bOD\d{10,}\b", r"\b\d{3}-\d{7}-\d{7}\b"):
        m = re.search(pat, text)
        if m:
            return m.group(0)
    return None


def detect_ticket(text: str) -> str | None:
    text = normalize_digits(text)
    m = re.search(r"\b(?:ticket|complaint|reference|ref\.?|request|case|sr)\s*(?:id|no\.?|number|#)?\s*(?:is|was|:|#|-)?\s*([A-Z0-9][A-Z0-9\-/]{3,})", text, re.I)
    if m and re.search(r"\d", m.group(1)) and not re.match(r"^\d{1,2}$", m.group(1)):
        return m.group(1).strip("-/.")
    m = re.search(r"(?:टिकट|शिकायत|संदर्भ)\s*(?:नंबर|संख्या|आईडी)?\s*(?:है|:|#|-)?\s*([A-Z0-9][A-Z0-9\-/]{3,})", text, re.I)
    if m and re.search(r"\d", m.group(1)):
        return m.group(1).strip("-/.")
    return None


def detect_product(text: str) -> str | None:
    m = re.search(
        r"\b(?:bought|purchased|ordered|buy|purchase of|order(?:ed)? for|paid .{0,25}? for)\s+(?:a|an|the|my|some|one|\d+)?\s*"
        r"([A-Za-z][A-Za-z0-9\-\s]{1,40}?)(?=\s+(?:worth|for|from|on|of|at|costing|priced|which|that|and|in|through|via|because|online)\b|[,.(₹]|$)",
        text, re.I)
    if m:
        prod = re.sub(r"\s+", " ", m.group(1)).strip()
        if prod.lower() not in GENERIC_PRODUCT_WORDS and len(prod) > 1:
            return prod
    return None


def detect_purpose(text: str) -> str | None:
    if re.search(r"resell|re-sell|resale|for my (shop|store|business)|business purpose|commercial|wholesale|in bulk|to sell|"
                 r"i run a (small )?(shop|store|business)|दोबारा बेच|दुकान के लिए|व्यापार के लिए|बेचने के लिए", text, re.I):
        return "resale_or_commercial"
    if re.search(r"self[- ]employ|my livelihood|earn(ing)? my living|आजीविका|रोज़ी|रोजी", text, re.I):
        return "livelihood"
    if re.search(r"personal|household|my own use|for (my )?(family|home|mother|father|wife|husband|son|daughter)|निजी|घरेलू|अपने इस्तेमाल|घर के लिए", text, re.I):
        return "personal"
    return None


HARM_RE = re.compile(r"electric(al)? shock|got a shock|caught fire|\bfire\b|burn(ed|t|s)?\b|injur|exploded|explosion|\bsmoke\b|"
                     r"hospital|चोट|आग लग|करंट|झुलस", re.I)
STEP_RE = re.compile(r"(contact|call|phon|email|e-mail|wrote|chat|complain|raised|request|report|escalat|visited|messag|ticket|"
                     r"शिकायत|कॉल|फ़ोन|फोन|ईमेल|संपर्क|अनुरोध|माँगा|मांगा|बताया)", re.I)
RESPONSE_RE = re.compile(r"(postpon|refus|denied|deny|reject|no response|not respond|did not respond|didn'?t respond|ignor|keeps? saying|kept saying|"
                         r"said|says|told|acknowledg|promised|auto[- ]?revers|no satisfactory|no reply|"
                         r"इनकार|मना|जवाब नहीं|टाल|कहा|कहते|बताया|कोई जवाब)", re.I)
FIRST_PERSON_STEP_RE = re.compile(r"\b(i|we|i've|i have|i had|we have)\b[^.!?।]{0,50}?\b(contact|call|phoned|email|e-mail|wrote|chat|complain|raised|request|report|escalat|visited|messag|follow)", re.I)
IMPLICIT_STEP_RE = re.compile(r"^\s*(contacted|called|emailed|e-mailed|wrote|chatted|complained|raised|requested|reported|escalated|messaged|followed up)\b", re.I)
HINDI_STEP_RE = re.compile(r"(मैंने|हमने|मैने)[^।.]{0,60}(शिकायत|कॉल|फ़ोन|फोन|ईमेल|संपर्क|अनुरोध|माँग|मांग)|(शिकायत|कॉल|ईमेल|संपर्क|अनुरोध)\s*(की|किया|किए|दर्ज की)")


def _is_own_step(sentence: str) -> bool:
    if re.search(r"^\s*(i )?(bought|purchased|ordered)\b", sentence, re.I) and not re.search(r"request|complain|contact|call|email", sentence, re.I):
        return False
    if sentence.strip().endswith("?"):
        return False  # a question ("Can I file a complaint?") is not a step already taken
    # ignore reported speech such as "they say I should contact the service centre"
    own = re.sub(r"\b(says?|said|told (me|us)|asked (me|us)|advised|suggest\w*)\b[^.!?।]*", "", sentence, flags=re.I)
    own = re.sub(r"\bI (should|must|need to|have to|ought to)\b[^.!?।]*", "", own, flags=re.I)
    return bool(FIRST_PERSON_STEP_RE.search(own) or IMPLICIT_STEP_RE.search(own) or HINDI_STEP_RE.search(sentence))


RESPONDER_RE = re.compile(r"\b(seller|they|them|support|customer care|customer service|agent|executive|platform|company|brand|"
                          r"service cent(re|er)|he|she)\b|विक्रेता|उन्होंने|उन्हों|कंपनी|कस्टमर केयर|ग्राहक सेवा|वे ", re.I)
UNRESOLVED_HINT = re.compile(r"(multiple|several|many|\d+|two|three|four|five) times|again and again|repeatedly|बार-बार|कई बार|\d+ बार", re.I)


def _date_roles() -> dict[str, list[str]]:
    return {
        "complaint_date": [r"complain", r"request", r"raised", r"contact", r"reported", r"emailed", r"called", r"wrote", r"ticket",
                           r"शिकायत", r"अनुरोध", r"माँग", r"मांग", r"कॉल", r"संपर्क", r"ईमेल"],
        "delivery_date": [r"deliver", r"arriv", r"receiv", r"got it", r"डिलीवर", r"मिला", r"मिली", r"आया", r"पहुँच", r"पहुंच"],
        "issue_date": [r"stopped", r"noticed", r"developed", r"started", r"began", r"defect", r"खराब", r"बंद"],
        "refund_approved_date": [r"approved", r"accepted", r"initiated", r"processed", r"cancel", r"स्वीकृत", r"रद्द"],
        "charge_date": [r"charged", r"debited", r"deducted", r"कट"],
        "purchase_date": [r"bought", r"purchas", r"order", r"paid", r"payment", r"खरीद", r"ऑर्डर", r"मंगवा", r"भुगतान"],
    }


def assign_date_roles(text: str, today: date) -> dict[str, dict]:
    """Assign each date in each sentence to the nearest preceding role keyword."""
    roles = _date_roles()
    out: dict[str, dict] = {}
    for sent in _split_sentences(normalize_digits(text)):
        dates = parse_dates(sent, today)
        if not dates:
            continue
        low = sent.lower()
        kw_positions: list[tuple[int, str]] = []
        for role, pats in roles.items():
            for p in pats:
                for m in re.finditer(p, low, re.I):
                    kw_positions.append((m.start(), role))
        for d in dates:
            before = [kp for kp in kw_positions if kp[0] <= d.start]
            after = [kp for kp in kw_positions if kp[0] > d.start]
            role = None
            if before:
                role = max(before, key=lambda kp: kp[0])[1]
            elif after:
                role = min(after, key=lambda kp: kp[0])[1]
            if role and role not in out:
                out[role] = {"value": d.iso, "approx": d.approx, "raw": d.raw}
    return out


# --------------------------------------------------------------------------
# Whole-message extraction
# --------------------------------------------------------------------------
def extract_facts(text: str, today: date) -> dict[str, Any]:
    """Extract every slot the rules can find in a free-text message."""
    facts: dict[str, Any] = {}
    clean = normalize_digits(text)
    scores = classify(clean)
    facts["_category_scores"] = scores

    amounts = parse_amounts(clean)
    if amounts:
        charged = [a for a in amounts if re.search(r"charg|debit|deduct|कट|लिए गए|लिया", a.context)]
        paid = [a for a in amounts if a not in charged]
        if charged:
            facts["charged_amount"] = charged[0].value
        if paid:
            facts["amount"] = paid[0].value
        elif not charged:
            facts["amount"] = amounts[0].value

    for key, fn in (("platform", detect_platform), ("seller", detect_seller), ("order_id", detect_order_id),
                    ("complaint_ref", detect_ticket), ("product", detect_product), ("purpose", detect_purpose)):
        val = fn(clean)
        if val:
            facts[key] = val
    # avoid treating the order ID as a ticket number
    if facts.get("complaint_ref") and facts.get("complaint_ref") == facts.get("order_id"):
        facts.pop("complaint_ref")

    roles = assign_date_roles(clean, today)
    for role, info in roles.items():
        facts[role] = info

    ev = detect_evidence(clean)
    if ev:
        facts["evidence"] = ev
    res = detect_resolutions(clean)
    if res:
        facts["desired_resolution"] = res
    if HARM_RE.search(clean):
        facts["harm_beyond_product"] = True
    if re.search(r"\bupi\b|यूपीआई|google pay|gpay|phonepe|paytm", clean, re.I):
        facts["payment_mode"] = "UPI"
    elif re.search(r"credit card|debit card|\bcard\b|कार्ड", clean, re.I):
        facts["payment_mode"] = "Card"
    elif re.search(r"cash on delivery|\bcod\b|कैश ऑन डिलीवरी", clean, re.I):
        facts["payment_mode"] = "Cash on delivery"
    elif re.search(r"wallet|वॉलेट", clean, re.I):
        facts["payment_mode"] = "Wallet"

    sentences = _split_sentences(text)
    steps = [s for s in sentences if _is_own_step(s)]
    if steps:
        facts["steps_taken"] = steps
    responses = [s for s in sentences if RESPONSE_RE.search(s) and RESPONDER_RE.search(s)
                 and not re.search(r"(listing|description|advertisement|\bad\b|box|label|website) (said|says|claimed)", s, re.I)]
    if responses:
        facts["seller_response"] = " ".join(responses)
    if UNRESOLVED_HINT.search(clean):
        facts["repeated_contact"] = True
    # the user's own words describing the problem: every sentence except their own complaint steps,
    # the other side's replies and bare purchase statements (those are captured as separate fields)
    issue_sents = []
    for s in sentences:
        if s in steps or (facts.get("seller_response") and s in facts["seller_response"]):
            continue
        if re.match(r"^\s*(i |मैंने )?(purchased|bought|ordered|paid|खरीद)", s, re.I) and not classify(s):
            continue
        if re.search(r"\?\s*$", s) and not classify(s):
            continue  # questions such as "What can I do?"
        issue_sents.append(s)
    if issue_sents:
        facts["issue_details"] = " ".join(issue_sents)
    return facts


# --------------------------------------------------------------------------
# Intake engine (serialisable state for Streamlit session storage)
# --------------------------------------------------------------------------
SLOT_KEYS = ["product", "amount", "charged_amount", "platform", "seller", "order_id", "purchase_date", "delivery_date",
             "issue_date", "complaint_date", "charge_date", "issue_details", "steps_taken", "seller_response", "complaint_ref",
             "evidence", "desired_resolution", "purpose", "consumer_name", "consumer_city", "payment_mode",
             "harm_beyond_product", "repeated_contact", "refund_status"]

QUESTION_SATISFIED_BY = {
    "product": ["product"], "amount": ["amount"], "platform_seller": ["platform"], "order_id": ["order_id"],
    "purchase_date": ["purchase_date"], "delivery_date": ["delivery_date"], "issue_details": ["issue_details"],
    "complaint_history": ["steps_taken"], "complaint_ref": ["complaint_ref"], "evidence": ["evidence"],
    "desired_resolution": ["desired_resolution"], "purpose": ["purpose"], "consumer_details": ["consumer_name"],
}


def new_state(lang: str = "en") -> dict:
    return {
        "lang": lang,
        "messages": [],
        "slots": {},
        "asked": [],
        "skipped": [],
        "answered_none": [],
        "pending": None,
        "category": None,
        "secondary": [],
        "scores": {},
        "narrative": "",
        "complete": False,
        "warnings": [],
        "llm_used": False,
        "llm_notes": [],
    }


class IntakeEngine:
    def __init__(self, state: dict | None = None, today: date | None = None, llm=None):
        from config import reference_date

        self.state = state or new_state()
        self.today = today or reference_date()
        self.llm = llm

    # ------------------------------------------------------------- helpers
    @property
    def lang(self) -> str:
        return self.state.get("lang", "en")

    def _set(self, key: str, value, source: str, overwrite: bool = False, **extra):
        if value in (None, "", [], {}):
            return
        slots = self.state["slots"]
        if key in slots and not overwrite:
            return
        entry = {"value": value, "source": source}
        entry.update(extra)
        slots[key] = entry

    def get(self, key: str, default=None):
        return self.state["slots"].get(key, {}).get("value", default)

    def _say(self, text: str, **meta):
        self.state["messages"].append({"role": "assistant", "text": text, "meta": meta})

    def _merge_facts(self, facts: dict, source: str, overwrite: bool = False):
        for k, v in facts.items():
            if k.startswith("_"):
                continue
            if isinstance(v, dict) and "value" in v:
                self._set(k, v["value"], source, overwrite, approx=v.get("approx", False), raw=v.get("raw"))
            elif k in ("evidence", "desired_resolution", "steps_taken"):
                existing = self.get(k) or []
                merged = list(dict.fromkeys(list(existing) + list(v)))
                self._set(k, merged, source, overwrite=True)
            else:
                self._set(k, v, source, overwrite)

    def _update_category(self, text: str):
        scores = dict(self.state.get("scores") or {})
        for c, s in classify(text).items():
            scores[c] = scores.get(c, 0) + s
        self.state["scores"] = scores
        if self.state.get("category_locked"):
            return
        cat, secondary = choose_category(scores)
        self.state["category"] = cat
        self.state["secondary"] = secondary

    # ------------------------------------------------------------- flow
    def start(self) -> None:
        if self.state["messages"]:
            return
        if self.lang == "hi":
            self._say("नमस्ते। मैं NyayaSetu हूँ। अपनी समस्या अपने शब्दों में बताइए — क्या खरीदा, कहाँ से, क्या गलत हुआ, और अब तक आपने क्या किया। "
                      "फिर मैं केवल ज़रूरी प्रश्न एक-एक करके पूछूँगा। आप कोई भी प्रश्न छोड़ सकते हैं।")
        else:
            self._say("Namaste. I'm NyayaSetu. Tell me what happened in your own words — what you bought, from where, what went wrong, "
                      "and what you have done so far. I'll then ask only the questions that matter for your case, one at a time. "
                      "You can skip any question.")

    def flow(self) -> list[str]:
        cat = self.state.get("category") or "unknown"
        if cat == "unknown":
            return ["category"]
        return FLOW.get(cat, FLOW["refund_not_received"])

    def _satisfied(self, q: str) -> bool:
        if q in self.state["asked"] or q in self.state["skipped"] or q in self.state["answered_none"]:
            return True
        if q == "complaint_ref" and (not self.get("steps_taken") or "complaint_history" in self.state["answered_none"]):
            return True
        if q == "category":
            return (self.state.get("category") or "unknown") != "unknown"
        if q == "claim_amount":
            # asked whenever a refund (or "deliver or refund") is wanted and the user has not yet stated how much;
            # NyayaSetu never assumes the full purchase price is being claimed
            wants_money = bool({"refund", "delivery"} & set(self.get("desired_resolution") or []))
            return (not wants_money) or self.get("claim_amount") is not None or self.get("claim_basis") == "full"
        if q in ("evidence", "desired_resolution"):
            # keyword hints from the story are only suggestions (e.g. "repair shop" is not a request for repair):
            # always confirm these with the user; the UI pre-selects the detected values
            return False
        keys = QUESTION_SATISFIED_BY.get(q, [q])
        if q == "issue_details":
            details = self.get("issue_details") or ""
            cat = self.state.get("category")
            # ask the category-specific question unless the user's story already answers it
            if cat == "non_delivery":
                return bool(re.search(r"\botp\b|neighbou?r|security|guard|someone (else )?(received|took)|पड़ोसी|किसी ने", details, re.I))
            if cat == "incorrect_charge":
                return bool(self.get("charged_amount")) and bool(self.get("amount"))
            if cat == "misleading_description":
                return bool(re.search(r"listing|advertis|description|claimed|said|विज्ञापन|लिस्टिंग|दावा", details, re.I)) and len(details.split()) >= 15
            return len(details.split()) >= 12
        return all(self.get(k) not in (None, "", []) for k in keys)

    def next_question(self) -> str | None:
        for q in self.flow():
            if not self._satisfied(q):
                return q
        return None

    def question_text(self, q: str) -> str:
        cat = self.state.get("category")
        if q == "issue_details" and cat in ISSUE_QUESTION_BY_CATEGORY:
            return ISSUE_QUESTION_BY_CATEGORY[cat][self.lang]
        if q == "delivery_date" and cat == "non_delivery":
            return DELIVERY_QUESTION_NON_DELIVERY[self.lang]
        if q == "claim_amount":
            return self._claim_question_text()
        return QUESTIONS[q][self.lang]

    # ------------------------------------------------------------- claimed amount
    def _excess(self) -> float | None:
        paid, charged = self.get("amount"), self.get("charged_amount")
        if self.state.get("category") == "incorrect_charge" and paid and charged and charged > paid:
            return float(charged) - float(paid)
        return None

    def _claim_question_text(self) -> str:
        hi = self.lang == "hi"
        paid, charged, ex = self.get("amount"), self.get("charged_amount"), self._excess()
        if ex:
            return (f"आपके अनुसार सही कीमत {format_inr(paid)} थी और आपसे {format_inr(charged)} लिए गए। आप कितनी राशि वापस चाहते हैं? "
                    f"अतिरिक्त {format_inr(ex)} के लिए “हाँ” लिखें, या कोई दूसरी राशि लिखें।" if hi else
                    f"You said the correct price was {format_inr(paid)} and you were charged {format_inr(charged)}. How much do you want back? "
                    f"Reply “yes” for the extra {format_inr(ex)}, or type a different amount.")
        if paid:
            return (f"आप कितनी राशि वापस माँग रहे हैं? आपने {format_inr(paid)} चुकाए थे। पूरी राशि के लिए “पूरा” लिखें, या वह राशि लिखें जो आप माँग रहे हैं "
                    "(जैसे, अगर ऑर्डर का केवल कुछ हिस्सा खराब था)। NyayaSetu अपने आप पूरी कीमत नहीं मान लेता।" if hi else
                    f"How much are you asking to get back? You paid {format_inr(paid)}. Reply “full” for the whole {format_inr(paid)}, or type the amount "
                    "you are claiming (for example, if only part of the order was faulty). NyayaSetu will not assume the full price.")
        return ("आप कितनी राशि वापस माँग रहे हैं, रुपये में? राशि लिखें (जैसे 4500), या जो भी चुकाया वह सब वापस चाहिए तो “पूरा” लिखें।" if hi else
                "How much are you asking to get back, in rupees? Type the amount (for example 4500), or “full” for everything you paid.")

    def _claim_basis_for(self, value: float) -> str:
        paid, ex = self.get("amount"), self._excess()
        if ex is not None and abs(value - ex) < 0.5:
            return "excess"
        if paid and abs(value - float(paid)) < 0.5:
            return "full"
        if paid and value < float(paid):
            return "partial"
        if paid and value > float(paid):
            return "above_paid"
        return "stated"

    def _try_set_claim(self, text: str, source: str, bare_numbers: bool, allow_yes: bool) -> str | None:
        """Record the claimed amount if the text states it clearly. Returns the basis, or None if unclear."""
        if not text:
            return None
        value = parse_claim_amount(text) if bare_numbers else (parse_amounts(text)[0].value if parse_amounts(text) else None)
        ex = self._excess()
        if value is not None and value > 0:
            basis = self._claim_basis_for(value)
            self._set("claim_amount", value, source, overwrite=True, basis=basis)
        elif ex is not None and (EXCESS_RE.search(text) or (allow_yes and YES_RE.match(text))):
            basis = "excess"
            self._set("claim_amount", ex, source, overwrite=True, basis=basis)
        elif FULL_RE.search(text) and self.state.get("category") != "incorrect_charge":
            basis = "full"
            if self.get("amount"):
                self._set("claim_amount", float(self.get("amount")), source, overwrite=True, basis=basis)
            else:
                self._set("claim_basis", "full", source, overwrite=True)
        else:
            return None
        self._set("claim_note", text, source, overwrite=True)
        return basis

    def _claim_ack(self, basis: str) -> str:
        hi = self.lang == "hi"
        amt = self.get("claim_amount")
        paid = self.get("amount")
        if basis == "full":
            if amt:
                return f"नोट कर लिया: आप चुकाई गई पूरी राशि {format_inr(amt)} माँग रहे हैं।" if hi else f"Noted: you are claiming the full {format_inr(amt)} you paid."
            return "नोट कर लिया: आप चुकाई गई पूरी राशि माँग रहे हैं।" if hi else "Noted: you are claiming the full amount you paid."
        if basis == "excess":
            return f"नोट कर लिया: आप अतिरिक्त {format_inr(amt)} वापस माँग रहे हैं।" if hi else f"Noted: you are claiming back the extra {format_inr(amt)}."
        if basis == "partial":
            return (f"नोट कर लिया: आप {format_inr(amt)} माँग रहे हैं (आपने {format_inr(paid)} चुकाए थे)।" if hi else
                    f"Noted: you are claiming {format_inr(amt)} (you paid {format_inr(paid)}).")
        if basis == "above_paid":
            return (f"नोट कर लिया: {format_inr(amt)}। यह आपके चुकाए {format_inr(paid)} से अधिक है — रिफंड सामान्यतः चुकाई गई राशि तक होता है; मुआवज़ा अलग से माँगा जाता है। "
                    "आप इसे केस सारांश पेज पर बदल सकते हैं।" if hi else
                    f"Noted: {format_inr(amt)}. That is more than the {format_inr(paid)} you paid — a refund is normally limited to what you paid, and "
                    "compensation is asked for separately. You can change this on the Case Summary page.")
        return f"नोट कर लिया: {format_inr(amt)}।" if hi else f"Noted: {format_inr(amt)}."

    def question_options(self, q: str) -> list[tuple[str, str]]:
        lang = self.lang
        if q == "category":
            return [(k, v[lang]) for k, v in CATEGORIES.items() if k != "unknown"]
        if q == "evidence":
            cat = self.state.get("category") or "unknown"
            order = RELEVANT_EVIDENCE.get(cat, []) + [k for k in EVIDENCE_TYPES if k not in RELEVANT_EVIDENCE.get(cat, [])]
            return [(k, EVIDENCE_TYPES[k][lang]) for k in order]
        if q == "desired_resolution":
            return [(k, v[lang]) for k, v in RESOLUTIONS.items()]
        if q == "purpose":
            return [("personal", "Personal / household use" if lang == "en" else "निजी / घरेलू उपयोग"),
                    ("livelihood", "To earn my own livelihood (self-employed)" if lang == "en" else "स्व-रोज़गार से अपनी आजीविका के लिए"),
                    ("resale_or_commercial", "For resale or business" if lang == "en" else "दोबारा बेचने या व्यापार के लिए")]
        return []

    def _ask_next(self, prefix: str = "") -> None:
        q = self.next_question()
        if q is None:
            self.state["pending"] = None
            self.state["complete"] = True
            done = ("धन्यवाद — आपका केस-फ़ाइल बनाने के लिए मेरे पास पर्याप्त जानकारी है। जो विवरण नहीं मिले, उन्हें चिह्नित किया जाएगा ताकि आप बाद में जोड़ सकें।"
                    if self.lang == "hi" else
                    "Thank you — I have enough to prepare your case file. Any details still missing will be clearly marked so you can add them later.")
            self._say((prefix + "\n\n" + done).strip(), kind="complete")
            return
        self.state["pending"] = q
        self._say((prefix + "\n\n" + self.question_text(q)).strip(), kind="question", question=q,
                  options=self.question_options(q))

    def _summary_of_understanding(self) -> str:
        lang = self.lang
        lines = []
        cat = self.state.get("category") or "unknown"
        label = CATEGORIES[cat][lang]
        sec = [CATEGORIES[c][lang] for c in self.state.get("secondary", [])]
        lines.append(("• समस्या: " if lang == "hi" else "• Problem: ") + label + (f" ({', '.join(sec)})" if sec else ""))
        if self.get("product"):
            lines.append(("• उत्पाद: " if lang == "hi" else "• Product: ") + str(self.get("product")))
        if self.get("amount"):
            lines.append(("• राशि: " if lang == "hi" else "• Amount paid: ") + format_inr(self.get("amount")))
        if self.get("charged_amount"):
            lines.append(("• कटी राशि: " if lang == "hi" else "• Amount charged: ") + format_inr(self.get("charged_amount")))
        if self.get("platform"):
            lines.append(("• प्लेटफ़ॉर्म: " if lang == "hi" else "• Platform: ") + str(self.get("platform")))
        for key, en, hi in (("purchase_date", "Order date", "ऑर्डर तिथि"), ("delivery_date", "Delivery date", "डिलीवरी तिथि"),
                            ("complaint_date", "Complaint/request date", "शिकायत/अनुरोध तिथि")):
            slot = self.state["slots"].get(key)
            if slot:
                from core.case_builder import human_date
                lines.append(f"• {hi if lang == 'hi' else en}: {human_date(slot['value'], slot.get('approx'), lang)}")
        if self.get("steps_taken"):
            lines.append("• अब तक उठाए कदम दर्ज किए गए" if lang == "hi" else "• Steps you have already taken: noted")
        intro = "मैंने अब तक यह समझा:" if lang == "hi" else "Here is what I understood so far:"
        outro = ("मैं कुछ छोटे प्रश्न पूछूँगा — कोई भी प्रश्न छोड़ सकते हैं।" if lang == "hi"
                 else "I'll ask a few short questions — you can skip any of them.")
        return intro + "\n" + "\n".join(lines) + "\n\n" + outro

    # ------------------------------------------------------------- input handling
    def handle_user_message(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        clean, redacted = redact_sensitive(text)
        self.state["messages"].append({"role": "user", "text": clean})
        if redacted:
            warn = (f"सुरक्षा के लिए मैंने आपके संदेश से यह हटा दिया: {', '.join(redacted)}। NyayaSetu को इसकी ज़रूरत नहीं है।"
                    if self.lang == "hi" else
                    f"For your safety I removed what looked like: {', '.join(redacted)}. NyayaSetu does not need it.")
            self.state["warnings"].append(warn)

        if not self.state["narrative"]:
            # first message: the user's story
            if detect_language(clean) == "hi":
                self.state["lang"] = "hi"
            self.state["narrative"] = clean
            facts = extract_facts(clean, self.today)
            self._merge_facts(facts, "rule")
            self._update_category(clean)
            self._llm_enrich(clean)
            prefix = self._summary_of_understanding()
            if redacted:
                prefix = self.state["warnings"][-1] + "\n\n" + prefix
            self._ask_next(prefix)
            return

        if BUILD_RE.match(clean):
            self.state["pending"] = None
            self.state["complete"] = True
            self._say("ठीक है — मैं अभी उपलब्ध जानकारी से आपका मामला बना रहा हूँ। अनुपलब्ध विवरण चिह्नित किए जाएँगे।" if self.lang == "hi"
                      else "Understood — I'll build your case now with what we have. Missing details will be marked.", kind="complete")
            return

        q = self.state.get("pending")
        if q is None:
            # conversation already complete — treat as extra information
            facts = extract_facts(clean, self.today)
            self._merge_facts(facts, "rule")
            self.state["narrative"] += "\n" + clean
            self._say("धन्यवाद, मैंने यह जानकारी जोड़ दी है।" if self.lang == "hi" else "Thanks — I've added that to your case.")
            return

        ack = self._apply_answer(q, clean)
        if redacted:
            ack = self.state["warnings"][-1] + "\n\n" + ack
        self._ask_next(ack)

    def skip_current(self) -> None:
        q = self.state.get("pending")
        if q:
            self.state["skipped"].append(q)
            self.state["messages"].append({"role": "user", "text": "(skipped)" if self.lang == "en" else "(छोड़ा गया)"})
            self._ask_next("ठीक है, छोड़ दिया।" if self.lang == "hi" else "No problem — skipped.")

    def answer_options(self, q: str, values: list[str], extra_text: str = "") -> None:
        """Structured answers from buttons / multiselects in the UI."""
        lang = self.lang
        labels = dict(self.question_options(q))
        shown = ", ".join(labels.get(v, v) for v in values) or ("कुछ नहीं" if lang == "hi" else "None")
        self.state["messages"].append({"role": "user", "text": shown + (f" — {extra_text}" if extra_text else "")})
        if q == "category" and values:
            self.state["category"] = values[0]
            self.state["category_locked"] = True
            self.state["asked"].append(q)
        elif q == "evidence":
            self._set("evidence", list(values), "answer", overwrite=True)
            if extra_text:
                self._merge_facts({"evidence": detect_evidence(extra_text)}, "answer")
            if not values and not extra_text:
                self.state["answered_none"].append("evidence")
            self.state["asked"].append(q)
        elif q == "desired_resolution":
            self._set("desired_resolution", list(values), "answer", overwrite=True)
            if extra_text:
                self._set("resolution_note", extra_text, "answer", overwrite=True)
                if {"refund", "delivery"} & set(values):
                    basis = self._try_set_claim(extra_text, "answer", bare_numbers=False, allow_yes=False)
                    if basis:
                        self.state["asked"].append(q)
                        self._ask_next(self._claim_ack(basis))
                        return
            self.state["asked"].append(q)
        elif q == "purpose" and values:
            self._set("purpose", values[0], "answer", overwrite=True)
            self.state["asked"].append(q)
        self._ask_next("नोट कर लिया।" if lang == "hi" else "Noted.")

    def _apply_answer(self, q: str, text: str) -> str:
        lang = self.lang
        noted = "नोट कर लिया" if lang == "hi" else "Noted"
        end = "।" if lang == "hi" else "."
        if SKIP_RE.match(text):
            self.state["skipped"].append(q)
            return "ठीक है, इसे अनुपलब्ध के रूप में चिह्नित किया।" if lang == "hi" else "No problem — I've marked it as missing."
        self.state["asked"].append(q)
        facts = extract_facts(text, self.today)
        if q == "category":
            scores = classify(text)
            cat, sec = choose_category(scores)
            if cat == "unknown":
                for key, labels in CATEGORIES.items():
                    if labels["en"].lower() in text.lower() or labels["hi"] in text:
                        cat = key
            if cat != "unknown":
                self.state["category"] = cat
                self.state["category_locked"] = True
                return f"{noted}: {CATEGORIES[cat][lang]}{end}"
            self.state["category"] = "refund_not_received" if re.search(r"refund|रिफंड", text, re.I) else "defective_product"
            self.state["category_locked"] = True
            self.state.setdefault("low_confidence_category", True)
            return ("मैं समस्या का प्रकार पक्का नहीं कर सका; मैंने सबसे नज़दीकी विकल्प चुना है — आप इसे केस सारांश में बदल सकते हैं।" if lang == "hi"
                    else "I couldn't classify that with confidence; I picked the closest type — you can change it on the Case Summary page.")
        if q == "product":
            prod = facts.get("product") or re.sub(r"^(i (bought|purchased|ordered)|it (is|was)|a |an |the )", "", text, flags=re.I).strip(" .")
            self._set("product", prod[:80], "answer", overwrite=True)
            self._merge_facts(facts, "rule")
            return f"{noted}: {prod[:80]}{end}"
        if q == "amount":
            amts = parse_amounts(text) or [FoundAmount(float(m.group(0).replace(",", "")), 0, "")
                                           for m in [re.search(r"[\d,]+(?:\.\d+)?", normalize_digits(text))] if m and m.group(0).strip(",")]
            if amts:
                self._set("amount", amts[0].value, "answer", overwrite=True)
                return f"{noted}: {format_inr(amts[0].value)}{end}"
            self.state["asked"].remove(q)
            self.state["skipped"].append(q)
            return "मैं राशि नहीं पढ़ सका; इसे अनुपलब्ध चिह्नित किया।" if lang == "hi" else "I couldn't read an amount there, so I've marked it as missing."
        if q == "platform_seller":
            platform = detect_platform(text)
            seller = detect_seller(text)
            if not platform:
                first = re.split(r",|;| and | और |seller|विक्रेता", text, maxsplit=1)[0].strip(" .:-")
                first = re.sub(r"^(from|on|via|i bought (it )?(from|on)|it was|मैंने|से)\s+", "", first, flags=re.I).strip()
                platform = re.sub(r"\s*(ऐप|app|website|वेबसाइट)\s*(से|पर)?$", "", first, flags=re.I).strip() or None
            if platform:
                self._set("platform", platform, "answer", overwrite=True)
            if seller:
                self._set("seller", seller, "answer", overwrite=True)
            bits = [b for b in [platform, (("विक्रेता: " if lang == "hi" else "seller: ") + seller) if seller else None] if b]
            return f"{noted}: {', '.join(bits)}{end}" if bits else noted + "."
        if q == "order_id":
            oid = detect_order_id(text)
            if not oid:
                tokens = [t.strip(".,;:") for t in normalize_digits(text).split()]
                cands = [t for t in tokens if len(t) >= 4 and re.search(r"\d", t)]
                oid = cands[0] if cands else None
            if oid:
                self._set("order_id", oid, "answer", overwrite=True)
                return f"{noted}: {oid}{end}"
            self.state["skipped"].append(q)
            return "ऑर्डर आईडी अनुपलब्ध चिह्नित की।" if lang == "hi" else "I've marked the Order ID as missing."
        if q in ("purchase_date", "delivery_date"):
            dates = parse_dates(text, self.today)
            if dates:
                d = dates[0]
                self._set(q, d.iso, "answer", overwrite=True, approx=d.approx, raw=d.raw)
                # a second date in a delivery answer is often the issue/complaint date
                for k, v in facts.items():
                    if k in ("complaint_date", "issue_date") and k not in self.state["slots"]:
                        self._set(k, v["value"], "rule", approx=v.get("approx"), raw=v.get("raw"))
                from utils.language import format_date
                return f"{noted}: {format_date(d.iso, lang)}{' (approx.)' if d.approx and lang == 'en' else ' (अनुमानित)' if d.approx else ''}{end}"
            self.state["skipped"].append(q)
            return ("मैं तारीख नहीं पढ़ सका — कृपया बाद में केस सारांश में जोड़ें (जैसे 12 अक्टूबर 2026)।" if lang == "hi"
                    else "I couldn't read a date there — you can add it on the Case Summary page (e.g. 12 October 2026).")
        if q == "issue_details":
            existing = self.get("issue_details") or ""
            combined = (existing + " " + text).strip() if existing and text not in existing else text
            self._set("issue_details", combined, "answer", overwrite=True)
            for k in ("charged_amount", "payment_mode", "issue_date", "harm_beyond_product", "evidence", "complaint_date"):
                if k in facts:
                    self._merge_facts({k: facts[k]}, "rule")
            if self.state.get("category") == "incorrect_charge":
                amts = parse_amounts(text)
                if len(amts) >= 2 and not self.get("charged_amount"):
                    self._set("charged_amount", max(a.value for a in amts), "answer")
            self._update_category(text)
            return noted + end
        if q == "complaint_history":
            if NO_RE.match(text) and len(text.split()) <= 6:
                self.state["answered_none"].append("complaint_history")
                self._set("steps_taken", [], "answer", overwrite=True)
                return ("ठीक है — अभी तक कोई शिकायत नहीं की गई। अगले चरणों में मैं बताऊँगा कि पहले लिखित शिकायत कैसे करें।" if lang == "hi"
                        else "Okay — no complaint made yet. The next-steps plan will start with a written complaint.")
            text = re.sub(r"^\s*(yes|yeah|yep|हाँ|हां|ji|जी)\s*[,.!:-]*\s*", "", text, flags=re.I) or text
            steps = list(dict.fromkeys((self.get("steps_taken") or []) + [text]))
            self._set("steps_taken", steps, "answer", overwrite=True)
            if facts.get("complaint_date"):
                self._set("complaint_date", facts["complaint_date"]["value"], "answer", overwrite=True,
                          approx=facts["complaint_date"].get("approx"), raw=facts["complaint_date"].get("raw"))
            else:
                ds = parse_dates(text, self.today)
                if ds and not self.get("complaint_date"):
                    self._set("complaint_date", ds[0].iso, "answer", approx=ds[0].approx, raw=ds[0].raw)
            if RESPONSE_RE.search(text):
                prev = self.get("seller_response") or ""
                self._set("seller_response", (prev + " " + text).strip() if text not in prev else prev, "answer", overwrite=True)
            if facts.get("complaint_ref"):
                self._set("complaint_ref", facts["complaint_ref"], "answer", overwrite=True)
            if UNRESOLVED_HINT.search(text):
                self._set("repeated_contact", True, "answer", overwrite=True)
            for k in ("evidence",):
                if k in facts:
                    self._merge_facts({k: facts[k]}, "rule")
            return noted + end
        if q == "complaint_ref":
            ref = detect_ticket(text)
            if not ref:
                tokens = [t.strip(".,;:") for t in normalize_digits(text).split()]
                cands = [t for t in tokens if len(t) >= 4 and re.search(r"\d", t)]
                ref = cands[0] if cands else None
            if ref:
                self._set("complaint_ref", ref, "answer", overwrite=True)
                return f"{noted}: {ref}{end}"
            self.state["skipped"].append(q)
            return "संदर्भ संख्या अनुपलब्ध चिह्नित की।" if lang == "hi" else "I've marked the reference number as missing."
        if q == "evidence":
            if NONE_RE.match(text):
                self.state["answered_none"].append("evidence")
                return ("ठीक है। कोई सबूत न होने पर भी आप आगे बढ़ सकते हैं, पर अपने ऐप/ईमेल से जो भी रिकॉर्ड मिलें, उन्हें सहेज लें।" if lang == "hi"
                        else "Okay. You can still proceed, but try to save whatever records you can from the app or your email.")
            ev = detect_evidence(text)
            self._merge_facts({"evidence": ev}, "answer")
            labels = ", ".join(EVIDENCE_TYPES[e][lang] for e in ev) if ev else text
            return f"{noted}: {labels}{end}"
        if q == "desired_resolution":
            res = detect_resolutions(text)
            if res:
                self._set("desired_resolution", res, "answer", overwrite=True)
            self._set("resolution_note", text, "answer", overwrite=True)
            ack = f"{noted}: " + (", ".join(RESOLUTIONS[r][lang] for r in res) if res else text) + end
            if {"refund", "delivery"} & set(res):
                basis = self._try_set_claim(text, "answer", bare_numbers=False, allow_yes=False)
                if basis:
                    ack += " " + self._claim_ack(basis)
            return ack
        if q == "claim_amount":
            basis = self._try_set_claim(text, "answer", bare_numbers=True, allow_yes=True)
            if basis:
                return self._claim_ack(basis)
            # unclear: ask once more, then leave it marked as not confirmed (never fall back to the full price)
            self.state["asked"].remove(q)
            retries = self.state.setdefault("retries", {})
            self._set("claim_note", text, "answer", overwrite=True)
            if retries.get(q, 0) < 1:
                retries[q] = 1
                return ("मैं इससे सटीक राशि नहीं समझ सका। कृपया रुपये में संख्या लिखें (जैसे 4800), या पूरी राशि के लिए “पूरा”।" if lang == "hi" else
                        "I couldn't tell the exact amount from that. Please type a number in rupees (for example 4800), or “full”.")
            self.state["skipped"].append(q)
            return ("मैंने माँगी गई राशि को ‘पुष्टि नहीं’ के रूप में छोड़ दिया है। आपके मसौदों में यह अनुपलब्ध दिखेगी — केस सारांश पेज पर जोड़ें।" if lang == "hi" else
                    "I've left the amount you are claiming as not confirmed. Your drafts will show it as missing — you can add it on the Case Summary page.")
        if q == "purpose":
            purpose = detect_purpose(text)
            if purpose is None and re.search(r"\bpersonal|own use|myself|family|home|घर|खुद", text, re.I):
                purpose = "personal"
            if purpose:
                self._set("purpose", purpose, "answer", overwrite=True)
            else:
                self._set("purpose_note", text, "answer", overwrite=True)
            return noted + end
        if q == "consumer_details":
            name, city = self._parse_identity(text)
            if name:
                self._set("consumer_name", name, "answer", overwrite=True)
            if city:
                self._set("consumer_city", city, "answer", overwrite=True)
            return noted + end
        self._set(q, text, "answer", overwrite=True)
        return noted + end

    @staticmethod
    def _parse_identity(text: str) -> tuple[str | None, str | None]:
        m = re.search(r"(?:my name is|i am|i'm|name:?)\s*([A-Za-z][A-Za-z .']{1,40}?)(?:,|\s+and\s+|\s+from\s+|\s+in\s+|$)", text, re.I)
        city_m = re.search(r"(?:from|in|live in|city:?|district:?)\s+([A-Za-z][A-Za-z .]{1,40})$", text, re.I)
        if m:
            name = m.group(1).strip(" .")
            city = city_m.group(1).strip(" .") if city_m else None
            return name, city
        parts = [p.strip(" .") for p in re.split(r",|।|;|\n", text) if p.strip(" .")]
        if len(parts) >= 2:
            return parts[0][:60], parts[1][:60]
        if parts:
            return parts[0][:60], None
        return None, None

    # ------------------------------------------------------------- optional LLM enrichment
    def _llm_enrich(self, text: str) -> None:
        if not self.llm or not getattr(self.llm, "is_live", False):
            return
        prompt = (
            "Extract facts from this Indian consumer's complaint. Return ONLY a JSON object with these keys (use null when the "
            "text does not state it — never guess): product (string), amount_paid_inr (number), charged_amount_inr (number), "
            "platform (string), seller (string), order_id (string), purchase_date (YYYY-MM-DD), delivery_date (YYYY-MM-DD), "
            "category (one of: damaged_on_delivery, defective_product, non_delivery, misleading_description, incorrect_charge, "
            f"refund_not_received, unknown). Today's date is {self.today.isoformat()}.\n\nTEXT:\n{text}"
        )
        try:
            resp = self.llm.complete(system="You are a careful information-extraction function. Output JSON only.",
                                     user=prompt, max_tokens=400)
            raw = resp.text.strip()
            raw = raw[raw.find("{"): raw.rfind("}") + 1]
            data = json.loads(raw)
        except Exception as exc:  # network errors, bad JSON — fall back silently to rules
            self.state["llm_notes"].append(f"LLM extraction skipped: {type(exc).__name__}")
            return
        mapping = {"product": "product", "amount_paid_inr": "amount", "charged_amount_inr": "charged_amount",
                   "platform": "platform", "seller": "seller", "order_id": "order_id",
                   "purchase_date": "purchase_date", "delivery_date": "delivery_date"}
        added = []
        for src, dst in mapping.items():
            val = data.get(src)
            if val in (None, "", "null"):
                continue
            if dst in ("amount", "charged_amount"):
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    continue
            if dst.endswith("_date"):
                try:
                    date.fromisoformat(str(val))
                except ValueError:
                    continue
            # the LLM may only fill gaps, and only with values that literally occur in the user's text
            if dst in ("order_id", "seller", "platform") and str(val).lower() not in text.lower():
                continue
            if dst not in self.state["slots"]:
                self._set(dst, val, "llm")
                added.append(dst)
        cat = data.get("category")
        if (self.state.get("category") in (None, "unknown")) and cat in CATEGORIES and cat != "unknown":
            self.state["category"] = cat
            added.append("category")
        if added:
            self.state["llm_used"] = True
            self.state["llm_notes"].append("LLM filled: " + ", ".join(added))
