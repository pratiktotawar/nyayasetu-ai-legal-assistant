"""Language helpers: detection, digit normalisation, date formatting and UI strings.

Adding another Indian language means adding a column to STRINGS and keyword
lists in core/intake.py; nothing else is language-specific.
"""
from __future__ import annotations

import re
from datetime import date

DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]
MONTHS_HI = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई",
             "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


def detect_language(text: str) -> str:
    """Return 'hi' if the text is mostly Devanagari, else 'en'."""
    if not text:
        return "en"
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "en"
    dev = sum(1 for c in letters if DEVANAGARI_RE.match(c))
    return "hi" if dev / len(letters) > 0.3 else "en"


def normalize_digits(text: str) -> str:
    return (text or "").translate(DEVANAGARI_DIGITS)


def format_date(iso: str | None, lang: str = "en") -> str:
    if not iso:
        return ""
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    months = MONTHS_HI if lang == "hi" else MONTHS_EN
    return f"{d.day} {months[d.month - 1]} {d.year}"


def format_inr(amount) -> str:
    """Indian digit grouping: 1234567 -> ₹12,34,567."""
    if amount is None or amount == "":
        return ""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    whole = int(round(value))
    paise = round(value - int(value), 2)
    s = str(abs(whole))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    out = f"₹{'-' if whole < 0 else ''}{s}"
    if paise and abs(paise) >= 0.01 and whole == int(value):
        out += f".{int(round(paise * 100)):02d}"
    return out


STRINGS = {
    "nav_home": {"en": "Home", "hi": "मुखपृष्ठ"},
    "nav_intake": {"en": "Start a Legal Case", "hi": "कानूनी मामला शुरू करें"},
    "nav_case": {"en": "My Case Summary", "hi": "मेरे मामले का सारांश"},
    "nav_rights": {"en": "Understand My Rights", "hi": "मेरे अधिकार समझें"},
    "nav_complaint": {"en": "Generate Complaint", "hi": "शिकायत तैयार करें"},
    "nav_steps": {"en": "Recommended Next Steps", "hi": "आगे क्या करें"},
    "nav_sources": {"en": "Legal Sources & Limitations", "hi": "कानूनी स्रोत और सीमाएँ"},
    "start_button": {"en": "Start My Legal Case", "hi": "मेरा कानूनी मामला शुरू करें"},
    "tagline": {"en": "From Consumer Problem to Legal Action.", "hi": "उपभोक्ता समस्या से कानूनी कार्रवाई तक।"},
    "hero_sub": {
        "en": "Describe what went wrong with an online purchase in your own words. NyayaSetu organises it into a case, explains your rights with official sources, drafts your complaint and tells you where to file.",
        "hi": "ऑनलाइन खरीद में क्या गलत हुआ, अपने शब्दों में बताइए। NyayaSetu इसे एक मामले में व्यवस्थित करता है, आधिकारिक स्रोतों के साथ आपके अधिकार समझाता है, शिकायत का मसौदा बनाता है और बताता है कि कहाँ दर्ज करें।",
    },
    "progress": {"en": "Your progress", "hi": "आपकी प्रगति"},
    "mode_demo": {"en": "Demo mode — rule-based responses (no AI API connected)", "hi": "डेमो मोड — नियम-आधारित उत्तर (कोई AI API जुड़ा नहीं)"},
    "mode_live": {"en": "Live AI mode", "hi": "लाइव AI मोड"},
    "privacy_note": {
        "en": "Your case stays only in this browser session. Nothing is saved on a server. Never share Aadhaar, PAN, bank passwords, card numbers or OTPs — NyayaSetu does not need them.",
        "hi": "आपका मामला केवल इस ब्राउज़र सत्र में रहता है। सर्वर पर कुछ भी सहेजा नहीं जाता। आधार, पैन, बैंक पासवर्ड, कार्ड नंबर या OTP कभी साझा न करें — NyayaSetu को इनकी ज़रूरत नहीं है।",
    },
    "clear_case": {"en": "Clear my case", "hi": "मेरा मामला हटाएँ"},
    "examples": {"en": "Try an example scenario", "hi": "एक उदाहरण आज़माएँ"},
    "skip": {"en": "Skip this question", "hi": "यह प्रश्न छोड़ें"},
    "build_now": {"en": "Build my case now", "hi": "अभी मेरा मामला बनाएँ"},
    "type_here": {"en": "Describe your problem or answer the question…", "hi": "अपनी समस्या बताइए या प्रश्न का उत्तर दीजिए…"},
    "facts_so_far": {"en": "What NyayaSetu has noted", "hi": "NyayaSetu ने क्या नोट किया"},
    "missing": {"en": "Missing", "hi": "अनुपलब्ध"},
    "save_changes": {"en": "Save corrections", "hi": "सुधार सहेजें"},
    "download_json": {"en": "Download case file (JSON)", "hi": "केस फ़ाइल डाउनलोड करें (JSON)"},
    "go_rights": {"en": "Next: Understand my rights", "hi": "आगे: मेरे अधिकार समझें"},
    "go_complaint": {"en": "Next: Generate complaint", "hi": "आगे: शिकायत तैयार करें"},
    "go_steps": {"en": "Next: What should I do next?", "hi": "आगे: अब क्या करें?"},
    "go_case": {"en": "Review my case summary", "hi": "मेरे मामले का सारांश देखें"},
    "no_case": {"en": "No case yet. Start by describing your problem.", "hi": "अभी कोई मामला नहीं है। अपनी समस्या बताकर शुरू करें।"},
    "download_txt": {"en": "Download TXT", "hi": "TXT डाउनलोड करें"},
    "download_pdf": {"en": "Download PDF", "hi": "PDF डाउनलोड करें"},
    "draft_lang": {"en": "Draft language", "hi": "मसौदे की भाषा"},
    "doc_type": {"en": "Document", "hi": "दस्तावेज़"},
    "law_says": {"en": "What the law says", "hi": "कानून क्या कहता है"},
    "how_applies": {"en": "How it may apply to you", "hi": "यह आप पर कैसे लागू हो सकता है"},
    "evidence_support": {"en": "Evidence that supports you", "hi": "आपके पक्ष में सबूत"},
    "what_next": {"en": "What you can do", "hi": "आप क्या कर सकते हैं"},
    "official_source": {"en": "Official source", "hi": "आधिकारिक स्रोत"},
    "uncertain": {"en": "Uncertain / depends on facts", "hi": "अनिश्चित / तथ्यों पर निर्भर"},
    "need_lawyer": {"en": "When you should speak to a lawyer", "hi": "आपको वकील से कब बात करनी चाहिए"},
    "ask_question": {"en": "Ask a question about your rights", "hi": "अपने अधिकारों के बारे में प्रश्न पूछें"},
}


def t(key: str, lang: str = "en") -> str:
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get("en") or key
