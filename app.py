"""NyayaSetu — AI Consumer Rights Assistant (Streamlit app).

Run:  streamlit run app.py
"""
from __future__ import annotations

import hashlib
import html
import json
from datetime import date

import streamlit as st

import config
from core.case_builder import (EVIDENCE_TYPES, case_from_json, case_to_json, describe_evidence, human_date, recompute)
from core.complaint_generator import DOC_TYPES
from core.intake import CATEGORIES, RESOLUTIONS, IntakeEngine, new_state
from core.legal_retrieval import get_kb
from core.legal_validation import validate_text
from core.llm_provider import get_provider
from core.pipeline import analyse_case, mode_label
from core.case_builder import build_case
from core.rights_analyzer import answer_question
from utils.language import format_inr, t
from utils.pdf_generator import text_to_pdf

st.set_page_config(page_title="NyayaSetu — Consumer Rights Assistant", page_icon="⚖️", layout="wide",
                   initial_sidebar_state="expanded")

PAGES = ["home", "intake", "case", "rights", "complaint", "steps", "sources"]
PAGE_KEYS = {"home": "nav_home", "intake": "nav_intake", "case": "nav_case", "rights": "nav_rights",
             "complaint": "nav_complaint", "steps": "nav_steps", "sources": "nav_sources"}
WORKFLOW = ["intake", "case", "rights", "complaint", "steps"]

# ---------------------------------------------------------------- styling
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@400;500;600;700&family=Noto+Serif:wght@600;700&display=swap');
:root{--navy:#14325C;--ink:#1A2230;--muted:#5A626E;--line:#DDE2E9;--paper:#FFFFFF;--page:#F6F7F9;
      --saffron:#E8892B;--saffron-bg:#FDECD6;--green:#1E7B3A;--green-bg:#E6F2EA;--grey-bg:#EEF1F5;}
html, body, [class*="css"], .stMarkdown, .stTextInput, .stTextArea, button, input, textarea, select {
  font-family:'Noto Sans','Noto Sans Devanagari',system-ui,sans-serif !important;}
h1, h2, h3 {font-family:'Noto Serif','Noto Sans Devanagari',Georgia,serif !important; color:var(--navy) !important; letter-spacing:-0.01em;}
h1 {font-size:2.05rem !important; line-height:1.18 !important;}
h2 {font-size:1.45rem !important;} h3 {font-size:1.15rem !important;}
.block-container {padding-top:1.4rem; max-width:1180px;}
.tricolor {height:4px; background:linear-gradient(90deg,#FF9933 0 33.3%, var(--navy) 33.3% 66.6%, #138808 66.6% 100%); border-radius:2px; margin:-0.4rem 0 1rem 0;}
.tracker {display:flex; gap:0; margin:0 0 1.4rem 0; border:1px solid var(--line); border-radius:8px; overflow:hidden; background:var(--paper);}
.tracker .st {flex:1; padding:.55rem .7rem; font-size:.84rem; color:var(--muted); border-right:1px solid var(--line); line-height:1.25;}
.tracker .st:last-child {border-right:none;}
.tracker .st b {display:block; font-size:1.05rem; color:var(--muted); font-family:'Noto Serif',serif;}
.tracker .st.done {background:#F1F5FA; color:var(--navy);} .tracker .st.done b {color:var(--green);}
.tracker .st.now {background:var(--navy); color:#fff;} .tracker .st.now b {color:#fff;}
.panel {background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:1rem 1.15rem; margin-bottom:.9rem;}
.muted {color:var(--muted); font-size:.92rem;}
.disclaimer {background:var(--grey-bg); border-left:4px solid var(--navy); padding:.75rem 1rem; font-size:.88rem; color:var(--ink); border-radius:4px;}
.mode {display:inline-block; padding:.18rem .55rem; border-radius:4px; font-size:.78rem; font-weight:600;}
.mode.demo {background:var(--grey-bg); color:var(--navy); border:1px solid var(--line);}
.mode.live {background:var(--green-bg); color:var(--green);}
.turn {padding:.6rem .1rem; border-bottom:1px solid var(--line);}
.turn .who {font-size:.78rem; font-weight:600; color:var(--muted); margin-bottom:.15rem;}
.turn.bot .who {color:var(--navy);}
.turn.user .txt {color:var(--ink); background:#F1F5FA; padding:.45rem .65rem; border-radius:6px; display:inline-block;}
.turn .txt {white-space:pre-wrap; font-size:.95rem; line-height:1.5;}
.fact {display:flex; justify-content:space-between; gap:.6rem; padding:.32rem 0; border-bottom:1px dashed var(--line); font-size:.88rem;}
.fact span:first-child {color:var(--muted);} .fact .v {text-align:right; color:var(--ink); font-weight:500;}
.fact .miss {color:#9A5410; background:var(--saffron-bg); padding:0 .35rem; border-radius:3px; font-weight:500;}
.issue {background:var(--paper); border:1px solid var(--line); border-left:5px solid var(--navy); border-radius:6px; padding:.9rem 1.1rem; margin-bottom:.9rem;}
.issue.argument {border-left-color:var(--saffron);} .issue.procedure {border-left-color:#7B8794;}
.issue.remedy {border-left-color:var(--green);} .issue.practical {border-left-color:#7B8794;} .issue.notice {border-left-color:#B0B7C3; background:#FBFCFD;}
.issue h4 {margin:.05rem 0 .3rem 0; font-family:'Noto Serif','Noto Sans Devanagari',serif; color:var(--navy); font-size:1.08rem;}
.chip {display:inline-block; font-size:.76rem; padding:.12rem .5rem; border-radius:4px; margin-right:.35rem; background:var(--grey-bg); color:var(--navy); font-weight:600;}
.chip.argument {background:var(--saffron-bg); color:#8A4A0B;} .chip.remedy {background:var(--green-bg); color:var(--green);}
.chip.conf {background:#fff; border:1px solid var(--line); color:var(--muted); font-weight:500;}
.sec {font-size:.8rem; font-weight:700; color:var(--muted); margin:.65rem 0 .15rem 0;}
.src {font-size:.84rem; padding:.4rem .55rem; background:#F8FAFC; border:1px solid var(--line); border-radius:5px; margin:.3rem 0;}
.src .ex {color:var(--muted); font-size:.8rem; margin-top:.25rem;}
.status {font-size:.72rem; font-weight:700; padding:.05rem .4rem; border-radius:3px; margin-left:.3rem;}
.status.verified {background:var(--green-bg); color:var(--green);} .status.verified_secondary {background:var(--saffron-bg); color:#8A4A0B;}
.status.needs_verification {background:#FBE4E4; color:#9B1C1C;}
.warnbox {background:var(--saffron-bg); border-left:4px solid var(--saffron); padding:.7rem 1rem; border-radius:4px; font-size:.92rem; margin-bottom:.8rem;}
.okbox {background:var(--green-bg); border-left:4px solid var(--green); padding:.6rem 1rem; border-radius:4px; font-size:.9rem; margin-bottom:.8rem;}
.step {display:flex; gap:1rem; background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:.9rem 1.1rem; margin-bottom:.8rem;}
.step .n {font-family:'Noto Serif',serif; font-size:1.6rem; color:var(--navy); min-width:2rem; line-height:1;}
.step.done .n {color:var(--green);}
.example {background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:.75rem .9rem; height:100%;}
.example .tt {font-weight:600; color:var(--navy); font-size:.93rem; margin-bottom:.25rem;}
.example .tx {font-size:.84rem; color:var(--muted);}
[data-testid="stSidebar"] {background:#FFFFFF; border-right:1px solid var(--line);}
[data-testid="stSidebar"] .stButton button {justify-content:flex-start; text-align:left; border:none; background:transparent; color:var(--ink); padding:.3rem .5rem; width:100%;}
[data-testid="stSidebar"] .stButton button > div, [data-testid="stSidebar"] .stButton button p {justify-content:flex-start !important; text-align:left !important; width:100%;}
[data-testid="stSidebar"] .stButton button:hover {background:#F1F5FA; color:var(--navy);}
[data-testid="stSidebar"] .stButton button:focus-visible {outline:2px solid var(--navy);}
.brand {font-family:'Noto Serif',serif; font-size:1.5rem; color:var(--navy); font-weight:700; line-height:1.1;}
.brand small {display:block; font-family:'Noto Sans',sans-serif; font-size:.78rem; color:var(--muted); font-weight:500; margin-top:.2rem;}
@media (max-width: 640px){ .tracker .st {font-size:.7rem; padding:.4rem .35rem;} h1{font-size:1.6rem !important;} }
@media (prefers-reduced-motion: reduce){ * {transition:none !important; animation:none !important;} }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- state
def init_state():
    ss = st.session_state
    ss.setdefault("lang", "en")
    ss.setdefault("page", "home")
    ss.setdefault("intake", None)
    ss.setdefault("case", None)
    ss.setdefault("analysis", None)
    ss.setdefault("analysis_key", None)
    ss.setdefault("visited", set())
    ss.setdefault("doc_edits", {})
    ss.setdefault("steps_done", set())
    ss.setdefault("example_answers", None)
    ss.setdefault("qa", None)
    if "llm" not in ss:
        ss.llm = get_provider()


init_state()
SS = st.session_state
LANG = SS.lang
TODAY = config.reference_date()
KB = get_kb()


def L(en: str, hi: str) -> str:
    return hi if SS.lang == "hi" else en


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def go(page: str):
    SS.page = page
    st.rerun()


def reset_case():
    for k in ("intake", "case", "analysis", "analysis_key", "qa", "example_answers"):
        SS[k] = None
    SS.visited = set()
    SS.doc_edits = {}
    SS.steps_done = set()


@st.cache_data
def load_examples() -> list[dict]:
    with open(config.BASE_DIR / "tests" / "test_cases.json", encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def get_analysis(lang: str) -> dict | None:
    if SS.case is None:
        return None
    key = hashlib.sha1((case_to_json(SS.case) + lang).encode()).hexdigest()
    if SS.analysis_key != key:
        with st.spinner(L("Checking your case against the verified legal sources…", "आपके मामले को सत्यापित कानूनी स्रोतों से जाँचा जा रहा है…")):
            SS.analysis = analyse_case(SS.case, TODAY, lang, SS.llm)
        SS.analysis_key = key
        SS.case = SS.analysis["case"]
        SS.analysis_key = hashlib.sha1((case_to_json(SS.case) + lang).encode()).hexdigest()
    return SS.analysis


def build_case_from_intake():
    SS.case = build_case(SS.intake, TODAY, mode_label(SS.llm))
    SS.analysis_key = None
    SS.doc_edits = {}


# ---------------------------------------------------------------- chrome
def sidebar():
    with st.sidebar:
        st.markdown(f"<div class='brand'>NyayaSetu<small>{esc(L('Your AI consumer rights assistant', 'आपका AI उपभोक्ता अधिकार सहायक'))}</small></div>",
                    unsafe_allow_html=True)
        st.write("")
        choice = st.radio(L("Language", "भाषा"), ["English", "हिंदी"], index=0 if SS.lang == "en" else 1, horizontal=True)
        new_lang = "en" if choice == "English" else "hi"
        if new_lang != SS.lang:
            SS.lang = new_lang
            if SS.intake and not SS.intake.get("narrative"):
                SS.intake["lang"] = new_lang
                SS.intake["messages"] = []
                IntakeEngine(SS.intake, today=TODAY).start()
            st.rerun()
        st.write("")
        for p in PAGES:
            done = p in SS.visited and p in WORKFLOW
            label = ("✓ " if done else "") + t(PAGE_KEYS[p], SS.lang)
            if p == SS.page:
                label = "▸ " + t(PAGE_KEYS[p], SS.lang)
            if st.button(label, key=f"nav_{p}", width="stretch"):
                go(p)
        st.divider()
        done_count = sum(1 for p in WORKFLOW if p in SS.visited)
        st.caption(f"{t('progress', SS.lang)}: {done_count}/5")
        st.progress(done_count / 5)
        live = getattr(SS.llm, "is_live", False)
        cls = "live" if live else "demo"
        txt = (t("mode_live", SS.lang) + f": {SS.llm.label()}") if live else t("mode_demo", SS.lang)
        st.markdown(f"<span class='mode {cls}'>{esc(txt)}</span>", unsafe_allow_html=True)
        reason = getattr(SS.llm, "reason", "")
        if reason:
            st.caption(reason)
        st.write("")
        st.caption(t("privacy_note", SS.lang))
        if SS.intake or SS.case:
            if st.button(t("clear_case", SS.lang), key="clear"):
                reset_case()
                go("home")


def tracker():
    labels = [L("Describe", "बताइए"), L("Case file", "केस फ़ाइल"), L("Your rights", "आपके अधिकार"),
              L("Complaint", "शिकायत"), L("Next steps", "आगे के कदम")]
    cells = []
    for i, (p, lab) in enumerate(zip(WORKFLOW, labels), 1):
        cls = "now" if SS.page == p else ("done" if p in SS.visited else "")
        mark = "✓" if (p in SS.visited and SS.page != p) else str(i)
        cells.append(f"<div class='st {cls}'><b>{mark}</b>{esc(lab)}</div>")
    st.markdown("<div class='tricolor'></div><div class='tracker'>" + "".join(cells) + "</div>", unsafe_allow_html=True)


def disclaimer():
    st.markdown(f"<div class='disclaimer'>{esc(config.DISCLAIMER_HI if SS.lang == 'hi' else config.DISCLAIMER_EN)}</div>", unsafe_allow_html=True)


def need_case() -> bool:
    if SS.case is None:
        st.info(t("no_case", SS.lang))
        if st.button(t("start_button", SS.lang), type="primary"):
            go("intake")
        return False
    return True


# ---------------------------------------------------------------- pages
def page_home():
    st.markdown("<div class='tricolor'></div>", unsafe_allow_html=True)
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        st.markdown(f"# {esc(L('From consumer problem to legal action.', 'उपभोक्ता समस्या से कानूनी कार्रवाई तक।'))}")
        st.markdown(f"<p style='font-size:1.05rem;line-height:1.6;max-width:60ch'>{esc(t('hero_sub', SS.lang))}</p>", unsafe_allow_html=True)
        if st.button(t("start_button", SS.lang) if SS.lang == "hi" else "Start My Legal Case", type="primary", key="hero_start"):
            if SS.intake is None:
                SS.intake = new_state(SS.lang)
            go("intake")
        st.caption(L("Free to use. No sign-up. Takes about five minutes. English or Hindi.",
                     "निःशुल्क। साइन-अप नहीं। लगभग पाँच मिनट। अंग्रेज़ी या हिंदी।"))
    with right:
        st.markdown(f"""<div class='panel'><h3 style='margin-top:0'>{esc(L('What NyayaSetu helps with', 'NyayaSetu किसमें मदद करता है'))}</h3>
<div class='muted'>{esc(L('Problems with things you bought online in India:', 'भारत में ऑनलाइन खरीदे गए सामान से जुड़ी समस्याएँ:'))}</div>
<ul style='margin:.4rem 0 .6rem 1.1rem;font-size:.92rem;line-height:1.7'>
<li>{esc(L('Refund never arrived', 'रिफंड नहीं आया'))}</li><li>{esc(L('Delivered damaged or defective', 'क्षतिग्रस्त या खराब सामान मिला'))}</li>
<li>{esc(L('Shown as delivered but never received', 'डिलीवर दिखाया पर मिला नहीं'))}</li><li>{esc(L('Not as advertised', 'विज्ञापन के अनुसार नहीं'))}</li>
<li>{esc(L('Charged twice or charged extra', 'दो बार या ज़्यादा पैसे कटे'))}</li></ul>
<div class='muted' style='font-size:.85rem'>{esc(L('Not covered: banking, insurance, housing, employment, criminal fraud. For those, see a lawyer.', 'शामिल नहीं: बैंकिंग, बीमा, आवास, नौकरी, आपराधिक धोखाधड़ी। इनके लिए वकील से मिलें।'))}</div></div>""",
                    unsafe_allow_html=True)

    st.markdown(f"### {esc(L('How it works', 'यह कैसे काम करता है'))}")
    steps = [(L("Describe", "बताइए"), L("Tell your story in your own words. Answer a few short questions.", "अपनी बात अपने शब्दों में बताइए। कुछ छोटे प्रश्नों के उत्तर दीजिए।")),
             (L("Case file", "केस फ़ाइल"), L("Check the facts NyayaSetu organised and correct anything wrong.", "NyayaSetu द्वारा व्यवस्थित तथ्य जाँचें और जो गलत हो उसे सुधारें।")),
             (L("Your rights", "आपके अधिकार"), L("See which rules apply, with the official source for each one.", "देखें कौन-से नियम लागू होते हैं, हर एक के आधिकारिक स्रोत के साथ।")),
             (L("Complaint", "शिकायत"), L("Get ready-to-edit drafts for the seller, the platform, the helpline and the Commission.", "विक्रेता, प्लेटफ़ॉर्म, हेल्पलाइन और आयोग के लिए संपादन योग्य मसौदे पाएँ।")),
             (L("Next steps", "आगे के कदम"), L("Follow a practical plan, with the official websites to use.", "उपयोग करने योग्य आधिकारिक वेबसाइटों के साथ व्यावहारिक योजना अपनाएँ।"))]
    cols = st.columns(5)
    for i, (c, (h, d)) in enumerate(zip(cols, steps), 1):
        c.markdown(f"<div class='panel' style='min-height:150px'><div style='font-family:Noto Serif,serif;font-size:1.5rem;color:#14325C'>{i}</div>"
                   f"<div style='font-weight:600;margin:.2rem 0'>{esc(h)}</div><div class='muted' style='font-size:.85rem'>{esc(d)}</div></div>",
                   unsafe_allow_html=True)

    st.markdown(f"### {esc(t('examples', SS.lang))}")
    st.caption(L("Fictional cases you can load to test the app. The two marked 'difficult' show how NyayaSetu handles missing facts and legally uncertain claims.",
                 "ऐप जाँचने के लिए काल्पनिक मामले। 'कठिन' चिह्नित दो मामले दिखाते हैं कि NyayaSetu अधूरे तथ्यों और कानूनी रूप से अनिश्चित दावों को कैसे संभालता है।"))
    examples = load_examples()
    for row in range(0, len(examples), 4):
        cols = st.columns(4)
        for c, ex in zip(cols, examples[row:row + 4]):
            with c:
                tag = L(" (difficult)", " (कठिन)") if ex["difficulty"] == "difficult" else ""
                lang_tag = " · हिंदी" if ex["language"] == "hi" else ""
                st.markdown(f"<div class='example'><div class='tt'>{esc(ex['id'])}{esc(tag)}{esc(lang_tag)}</div>"
                            f"<div class='tx'>{esc(ex['opening_message'][:150])}{'…' if len(ex['opening_message']) > 150 else ''}</div></div>",
                            unsafe_allow_html=True)
                if st.button(L("Load this example", "यह उदाहरण लोड करें"), key=f"ex_{ex['id']}", width="stretch"):
                    reset_case()
                    SS.lang = ex["language"]
                    SS.intake = new_state(ex["language"])
                    eng = IntakeEngine(SS.intake, today=TODAY, llm=SS.llm)
                    eng.start()
                    eng.handle_user_message(ex["opening_message"])
                    SS.example_answers = ex["answers"]
                    go("intake")
    st.write("")
    disclaimer()


def facts_panel(engine: IntakeEngine):
    slots = engine.state["slots"]
    lang = SS.lang
    cat = engine.state.get("category") or "unknown"

    def row(label, val, key=None):
        ai = " (AI)" if key and slots.get(key, {}).get("source") == "llm" else ""  # value suggested by a live model
        v = f"<span class='v'>{esc(val)}{esc(ai)}</span>" if val not in (None, "", []) else f"<span class='miss'>{esc(t('missing', lang))}</span>"
        return f"<div class='fact'><span>{esc(label)}</span>{v}</div>"

    def sv(k):
        return slots.get(k, {}).get("value")

    wants_money = bool({"refund", "delivery"} & set(sv("desired_resolution") or []))
    claim_txt = (format_inr(sv("claim_amount")) if sv("claim_amount") else
                 (L("Full amount paid", "चुकाई गई पूरी राशि") if sv("claim_basis") == "full" else None))

    rows = [row(L("Problem", "समस्या"), CATEGORIES[cat][lang] if cat != "unknown" else None),
            row(L("Product", "उत्पाद"), sv("product")),
            row(L("Amount paid", "चुकाई गई राशि"), format_inr(sv("amount")) if sv("amount") else None, "amount"),
            *([row(L("Refund claimed", "माँगा गया रिफंड"), claim_txt)] if wants_money else []),
            row(L("Platform", "प्लेटफ़ॉर्म"), sv("platform"), "platform"),
            row(L("Seller", "विक्रेता"), sv("seller"), "seller"),
            row(L("Order ID", "ऑर्डर आईडी"), sv("order_id"), "order_id"),
            row(L("Order date", "ऑर्डर तिथि"), human_date(sv("purchase_date"), slots.get("purchase_date", {}).get("approx"), lang)),
            row(L("Complaint made", "शिकायत की गई"), L("Yes", "हाँ") if sv("steps_taken") else (L("Not yet", "अभी नहीं") if "complaint_history" in engine.state["answered_none"] else None)),
            row(L("Evidence", "सबूत"), ", ".join(describe_evidence(sv("evidence") or [], lang)) or None),
            row(L("Name / city", "नाम / शहर"), ", ".join(x for x in [sv("consumer_name"), sv("consumer_city")] if x) or None)]
    st.markdown(f"<div class='panel'><div style='font-weight:600;color:#14325C;margin-bottom:.3rem'>{esc(t('facts_so_far', lang))}</div>"
                + "".join(rows) + "</div>", unsafe_allow_html=True)


def page_intake():
    SS.visited.add("intake")
    tracker()
    if SS.intake is None:
        SS.intake = new_state(SS.lang)
    engine = IntakeEngine(SS.intake, today=TODAY, llm=SS.llm)
    engine.start()
    if engine.state.get("lang") != SS.lang and engine.state.get("narrative"):
        SS.lang = engine.state["lang"]
        st.rerun()
    st.markdown(f"# {esc(t('nav_intake', SS.lang))}")
    st.caption(L("Tell NyayaSetu what happened. It asks only the questions that matter for your type of problem. You can skip any question.",
                 "NyayaSetu को बताइए क्या हुआ। यह केवल आपकी समस्या से जुड़े प्रश्न पूछता है। आप कोई भी प्रश्न छोड़ सकते हैं।"))
    left, right = st.columns([1.6, 1], gap="large")
    with left:
        turns = []
        for m in engine.state["messages"]:
            who = "NyayaSetu" if m["role"] == "assistant" else L("You", "आप")
            cls = "bot" if m["role"] == "assistant" else "user"
            turns.append(f"<div class='turn {cls}'><div class='who'>{esc(who)}</div><div class='txt'>{esc(m['text'])}</div></div>")
        st.markdown("<div class='panel'>" + "".join(turns) + "</div>", unsafe_allow_html=True)
        for w in engine.state.get("warnings", [])[-1:]:
            st.markdown(f"<div class='warnbox'>{esc(w)}</div>", unsafe_allow_html=True)

        pending = engine.state.get("pending")
        if engine.state.get("complete"):
            st.markdown(f"<div class='okbox'>{esc(L('Your answers are recorded. Next, check the case file NyayaSetu prepared.', 'आपके उत्तर दर्ज हो गए। अब NyayaSetu द्वारा तैयार केस फ़ाइल जाँचें।'))}</div>",
                        unsafe_allow_html=True)
            if st.button(t("go_case", SS.lang), type="primary"):
                build_case_from_intake()
                go("case")
            with st.form("extra", clear_on_submit=True):
                extra = st.text_area(L("Add anything else (optional)", "कुछ और जोड़ें (वैकल्पिक)"), height=80)
                if st.form_submit_button(L("Add to my case", "मेरे मामले में जोड़ें")) and extra.strip():
                    engine.handle_user_message(extra)
                    st.rerun()
        elif pending in ("category", "evidence", "desired_resolution", "purpose"):
            opts = engine.question_options(pending)
            labels = {k: v for k, v in opts}
            with st.form(f"opt_{pending}_{len(engine.state['messages'])}"):
                if pending in ("evidence", "desired_resolution"):
                    detected = [v for v in (engine.get(pending) or []) if v in labels]
                    picked = st.multiselect(L("Select all that apply", "जो लागू हों, चुनें"), list(labels), default=detected,
                                            format_func=lambda k: labels[k])
                    if detected:
                        st.caption(L("Pre-selected from what you wrote — remove anything that is wrong.", "आपने जो लिखा उसके आधार पर पहले से चुना गया — जो गलत हो उसे हटा दें।"))
                else:
                    picked = [st.radio(L("Choose one", "एक चुनें"), list(labels), format_func=lambda k: labels[k])]
                extra = st.text_input(L("Anything to add? (optional)", "कुछ जोड़ना है? (वैकल्पिक)"))
                c1, c2, c3 = st.columns([1, 1, 1.2])
                send = c1.form_submit_button(L("Save answer", "उत्तर सहेजें"), type="primary")
                skip = c2.form_submit_button(t("skip", SS.lang))
                build = c3.form_submit_button(t("build_now", SS.lang))
            if send:
                engine.answer_options(pending, picked, extra.strip())
                st.rerun()
            if skip:
                engine.skip_current()
                st.rerun()
            if build:
                engine.handle_user_message("build my case now")
                st.rerun()
        else:
            first = not engine.state.get("narrative")
            with st.form(f"msg_{len(engine.state['messages'])}", clear_on_submit=True):
                text = st.text_area(L("Describe your problem", "अपनी समस्या बताइए") if first else L("Your answer", "आपका उत्तर"),
                                    placeholder=t("type_here", SS.lang), height=130 if first else 80)
                c1, c2, c3 = st.columns([1, 1, 1.2])
                send = c1.form_submit_button(L("Send", "भेजें"), type="primary")
                skip = c2.form_submit_button(t("skip", SS.lang), disabled=first)
                build = c3.form_submit_button(t("build_now", SS.lang), disabled=first)
            if send and text.strip():
                engine.handle_user_message(text)
                st.rerun()
            if skip:
                engine.skip_current()
                st.rerun()
            if build:
                engine.handle_user_message("build my case now")
                st.rerun()
        if SS.example_answers and not engine.state.get("complete"):
            if st.button(L("Answer the remaining questions with this example's sample answers", "बाकी प्रश्नों के उत्तर इस उदाहरण के नमूना उत्तरों से भरें")):
                for _ in range(30):
                    q = engine.state.get("pending")
                    if not q:
                        break
                    ans = SS.example_answers.get(q)
                    if ans is None:
                        engine.skip_current()
                    elif isinstance(ans, dict):
                        engine.answer_options(q, ans.get("options", []), ans.get("text", ""))
                    else:
                        engine.handle_user_message(ans)
                st.rerun()
        if engine.state.get("llm_notes"):
            st.caption(" · ".join(engine.state["llm_notes"]))
    with right:
        facts_panel(engine)
        st.markdown(f"<div class='muted' style='font-size:.84rem'>{esc(t('privacy_note', SS.lang))}</div>", unsafe_allow_html=True)


def page_case():
    if not need_case():
        return
    SS.visited.add("case")
    tracker()
    case = SS.case
    lang = SS.lang
    st.markdown(f"# {esc(t('nav_case', lang))}")
    st.caption(L("This is the case file built from your answers. Correct anything that is wrong — your rights analysis and complaint drafts update automatically.",
                 "यह आपके उत्तरों से बनी केस फ़ाइल है। जो गलत हो उसे सुधारें — आपके अधिकारों का विश्लेषण और शिकायत मसौदे अपने आप अपडेट होंगे।"))
    miss = case["missing_info"]
    if miss:
        items = "".join(f"<li><b>{esc(m['label_hi'] if lang == 'hi' else m['label_en'])}</b> — {esc(m['why'])}</li>" for m in miss)
        st.markdown(f"<div class='warnbox'><b>{esc(L('Missing information', 'अनुपलब्ध जानकारी'))} ({len(miss)})</b>"
                    f"<ul style='margin:.3rem 0 0 1.1rem'>{items}</ul></div>", unsafe_allow_html=True)
    t_ = case["transaction"]
    cat_keys = [k for k in CATEGORIES if k != "unknown"] + ["unknown"]
    with st.form("case_form"):
        st.markdown(f"### {esc(L('Nature of dispute', 'विवाद की प्रकृति'))}")
        c1, c2 = st.columns(2)
        category = c1.selectbox(L("Type of problem", "समस्या का प्रकार"), cat_keys, index=cat_keys.index(case["dispute"]["category"]),
                                format_func=lambda k: CATEGORIES[k][lang])
        purpose_opts = ["", "personal", "livelihood", "resale_or_commercial"]
        purpose_lbl = {"": L("Not stated", "नहीं बताया"), "personal": L("Personal / household use", "निजी / घरेलू उपयोग"),
                       "livelihood": L("Own livelihood (self-employed)", "अपनी आजीविका (स्व-रोज़गार)"), "resale_or_commercial": L("Resale / business", "दोबारा बेचना / व्यापार")}
        purpose = c2.selectbox(L("Why you bought it", "क्यों खरीदा"), purpose_opts, index=purpose_opts.index(case["consumer"].get("purpose") or ""),
                               format_func=lambda k: purpose_lbl[k])
        st.markdown(f"### {esc(L('Parties', 'पक्षकार'))}")
        c1, c2 = st.columns(2)
        name = c1.text_input(L("Your name", "आपका नाम"), case["consumer"].get("name", ""))
        city = c2.text_input(L("Your city / district", "आपका शहर / ज़िला"), case["consumer"].get("city", ""))
        c1, c2, c3 = st.columns(3)
        platform = c1.text_input(L("Platform / website / app", "प्लेटफ़ॉर्म / वेबसाइट / ऐप"), case["parties"].get("platform", ""))
        seller = c2.text_input(L("Seller", "विक्रेता"), case["parties"].get("seller", ""))
        seller_addr = c3.text_input(L("Seller / platform address", "विक्रेता / प्लेटफ़ॉर्म का पता"), case["parties"].get("seller_address", ""))
        st.markdown(f"### {esc(L('Order and payment', 'ऑर्डर और भुगतान'))}")
        c1, c2, c3 = st.columns(3)
        product = c1.text_input(L("Product", "उत्पाद"), t_.get("product", ""))
        order_id = c2.text_input(L("Order ID", "ऑर्डर आईडी"), t_.get("order_id", ""))
        amount = c3.number_input(L("Amount paid (₹)", "चुकाई गई राशि (₹)"), min_value=0.0, value=float(t_.get("amount_paid") or 0.0), step=100.0)
        c1, c2, c3 = st.columns(3)
        pdate = c1.date_input(L("Order date", "ऑर्डर तिथि"), value=date.fromisoformat(t_["purchase_date"]) if t_.get("purchase_date") else None, max_value=TODAY, format="DD/MM/YYYY")
        ddate = c2.date_input(L("Delivery date", "डिलीवरी तिथि"), value=date.fromisoformat(t_["delivery_date"]) if t_.get("delivery_date") else None, max_value=TODAY, format="DD/MM/YYYY")
        charged = c3.number_input(L("Amount actually charged (₹, only for wrong charges)", "वास्तव में कटी राशि (₹, केवल गलत कटौती के लिए)"), min_value=0.0,
                                  value=float(t_.get("charged_amount") or 0.0), step=100.0)
        st.markdown(f"### {esc(L('What happened', 'क्या हुआ'))}")
        expected = st.text_area(L("What you expected", "आपने क्या अपेक्षा की थी"), case.get("what_was_expected", ""), height=70)
        details = st.text_area(L("What actually happened (your words — this is quoted in your complaint)", "वास्तव में क्या हुआ (आपके शब्द — यह शिकायत में उद्धृत होगा)"),
                               case.get("issue_details", ""), height=110)
        steps = st.text_area(L("Steps you have already taken (one per line)", "आपने अब तक क्या किया (हर पंक्ति में एक)"), "\n".join(case.get("steps_taken", [])), height=90)
        c1, c2 = st.columns(2)
        cdate = c1.date_input(L("Date you first complained", "पहली शिकायत की तिथि"), value=date.fromisoformat(case["complaint_date"]) if case.get("complaint_date") else None,
                              max_value=TODAY, format="DD/MM/YYYY")
        ref = c2.text_input(L("Complaint / ticket number", "शिकायत / टिकट संख्या"), case.get("complaint_ref", ""))
        response = st.text_area(L("What the seller / platform said", "विक्रेता / प्लेटफ़ॉर्म ने क्या कहा"), case.get("seller_response", ""), height=70)
        st.markdown(f"### {esc(L('Evidence and resolution', 'सबूत और समाधान'))}")
        c1, c2 = st.columns(2)
        evidence = c1.multiselect(L("Evidence you have", "आपके पास सबूत"), list(EVIDENCE_TYPES), default=[e for e in case.get("evidence", []) if e in EVIDENCE_TYPES],
                                  format_func=lambda k: EVIDENCE_TYPES[k][lang])
        resolution = c2.multiselect(L("What you want", "आप क्या चाहते हैं"), list(RESOLUTIONS), default=[r for r in case.get("desired_resolution", []) if r in RESOLUTIONS],
                                    format_func=lambda k: RESOLUTIONS[k][lang])
        claim = case.get("claim") or {}
        claim_val = st.number_input(L("Refund amount you are claiming (₹) — leave 0 if not decided or not asking for money back",
                                      "आप कितना रिफंड माँग रहे हैं (₹) — तय न हो या पैसे वापस नहीं चाहिए तो 0 छोड़ें"),
                                    min_value=0.0, value=float(claim.get("amount") or 0.0), step=100.0)
        st.caption(L("NyayaSetu never assumes you want the full price back. Your drafts use exactly this amount; if it is 0 they show it as missing.",
                     "NyayaSetu अपने आप पूरी कीमत नहीं मान लेता। आपके मसौदे ठीक यही राशि इस्तेमाल करते हैं; 0 होने पर इसे अनुपलब्ध दिखाया जाता है।"))
        harm = st.checkbox(L("The product injured someone or damaged other property", "उत्पाद से किसी को चोट लगी या अन्य संपत्ति को नुकसान हुआ"), value=bool(case.get("harm_beyond_product")))
        saved = st.form_submit_button(t("save_changes", lang), type="primary")
    if saved:
        c = json.loads(case_to_json(case))
        prov = c.setdefault("provenance", {})

        def setv(path, new):
            obj = c
            keys = path.split(".")
            for k in keys[:-1]:
                obj = obj[k]
            if obj.get(keys[-1]) != new:
                obj[keys[-1]] = new
                prov[path] = "user-edited"
        c["dispute"]["category"] = category
        c["dispute"]["low_confidence"] = False
        setv("consumer.purpose", purpose)
        setv("consumer.name", name.strip())
        setv("consumer.city", city.strip())
        setv("parties.platform", platform.strip())
        setv("parties.seller", seller.strip())
        setv("parties.seller_address", seller_addr.strip())
        setv("transaction.product", product.strip())
        setv("transaction.order_id", order_id.strip())
        setv("transaction.amount_paid", amount or None)
        setv("transaction.charged_amount", charged or None)
        if pdate and pdate.isoformat() != t_.get("purchase_date"):
            setv("transaction.purchase_date", pdate.isoformat())
            c["transaction"]["purchase_date_approx"] = False
        if ddate and ddate.isoformat() != t_.get("delivery_date"):
            setv("transaction.delivery_date", ddate.isoformat())
            c["transaction"]["delivery_date_approx"] = False
        if cdate and cdate.isoformat() != case.get("complaint_date"):
            setv("complaint_date", cdate.isoformat())
            c["complaint_date_approx"] = False
        setv("what_was_expected", expected.strip())
        setv("issue_details", details.strip())
        setv("steps_taken", [s.strip() for s in steps.splitlines() if s.strip()])
        c["no_complaint_yet"] = not c["steps_taken"]
        setv("complaint_ref", ref.strip())
        setv("seller_response", response.strip())
        if ref.strip() and "complaint_reference" not in evidence:
            evidence = evidence + ["complaint_reference"]
        setv("evidence", evidence)
        setv("desired_resolution", resolution)
        setv("harm_beyond_product", harm)
        old_claim = float(claim.get("amount") or 0.0)
        if abs(claim_val - old_claim) > 0.004:
            cl = c.setdefault("claim", {})
            if claim_val > 0:
                paid_now = c["transaction"].get("amount_paid")
                charged_now = c["transaction"].get("charged_amount")
                ex = (charged_now - paid_now) if (c["dispute"]["category"] == "incorrect_charge" and paid_now and charged_now
                                                   and charged_now > paid_now) else None
                basis = "excess" if ex and abs(claim_val - ex) < 0.5 else ("full" if paid_now and abs(claim_val - paid_now) < 0.5 else "stated")
                cl.update({"amount": claim_val, "basis": basis, "confirmed": True, "source": "user-edited"})
            else:
                cl.update({"amount": None, "basis": "", "confirmed": False, "source": "user-edited"})
            prov["claim.amount"] = "user-edited"
        SS.case = recompute(c, TODAY)
        SS.analysis_key = None
        SS.doc_edits = {}
        st.success(L("Saved. Your rights analysis and drafts will use the corrected facts.", "सहेजा गया। आपके अधिकारों का विश्लेषण और मसौदे सुधरे हुए तथ्यों का उपयोग करेंगे।"))
        st.rerun()

    st.markdown(f"### {esc(L('Timeline', 'समयरेखा'))}")
    tl = [{L("Date", "तिथि"): human_date(e["date"], e.get("approx"), lang) or L("date not known", "तिथि ज्ञात नहीं"), L("Event", "घटना"): e["event"]} for e in case["timeline"]]
    if tl:
        st.dataframe(tl, width="stretch", hide_index=True)
    cl = case.get("claim") or {}
    if cl.get("refund_requested"):
        if cl.get("confirmed") and cl.get("amount"):
            part = (L(f" — part of the {format_inr(case['transaction']['amount_paid'])} you paid", f" — चुकाए गए {format_inr(case['transaction']['amount_paid'])} का हिस्सा")
                    if cl.get("is_partial") else "")
            if cl.get("exceeds_paid"):
                st.markdown(f"<div class='warnbox'>{esc(L('The refund you entered is more than the price you paid. A refund is normally limited to what you paid; ask for compensation separately (select it under What you want).', 'आपकी दर्ज की गई रिफंड राशि चुकाई गई कीमत से अधिक है। रिफंड सामान्यतः चुकाई गई राशि तक होता है; मुआवज़ा अलग से माँगें (आप क्या चाहते हैं में चुनें)।'))}</div>",
                            unsafe_allow_html=True)
            st.markdown(f"<div class='okbox'><b>{esc(L('Refund you are claiming', 'आप जो रिफंड माँग रहे हैं'))}:</b> {esc(format_inr(cl['amount']))}{esc(part)} "
                        f"<span class='muted'>({esc(L('confirmed by you', 'आपने पुष्टि की'))})</span></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='warnbox'>{esc(L('You asked for a refund but have not confirmed how much. Your drafts show the amount as [MISSING] until you enter it above.', 'आपने रिफंड माँगा है पर राशि की पुष्टि नहीं की। जब तक आप ऊपर राशि नहीं भरते, मसौदों में यह [अनुपलब्ध] दिखेगी।'))}</div>",
                        unsafe_allow_html=True)
    fl = case["financial_loss"]
    st.markdown(f"<div class='panel'><b>{esc(L('Financial loss', 'आर्थिक नुकसान'))}:</b> {esc(format_inr(fl['amount']) if fl.get('amount') else L('not known yet', 'अभी ज्ञात नहीं'))} "
                f"<span class='muted'>({esc(fl['basis_hi'] if lang == 'hi' else fl['basis_en'])})</span></div>", unsafe_allow_html=True)
    edited = [k for k, v in case.get("provenance", {}).items() if v == "user-edited"]
    llm_fields = [k for k, v in case.get("provenance", {}).items() if v == "llm"]
    st.caption(L("Where each fact came from: extracted by rules from your words, your direct answers, or your corrections",
                 "हर तथ्य का स्रोत: आपके शब्दों से नियमों द्वारा निकाला गया, आपके सीधे उत्तर, या आपके सुधार")
               + (f" · {L('corrected by you', 'आपके द्वारा सुधारा गया')}: {', '.join(edited)}" if edited else "")
               + (f" · {L('suggested by AI', 'AI द्वारा सुझाया गया')}: {', '.join(llm_fields)}" if llm_fields else ""))
    c1, c2, c3 = st.columns([1, 1, 1.4])
    c1.download_button(t("download_json", lang), case_to_json(case).encode("utf-8"), file_name=f"{case['case_id']}.json", mime="application/json")
    up = c2.file_uploader(L("Restore a saved case file", "सहेजी गई केस फ़ाइल वापस लाएँ"), type=["json"], label_visibility="collapsed")
    if up is not None:
        try:
            SS.case = case_from_json(up.read().decode("utf-8"), TODAY)
            SS.analysis_key = None
            st.success(L("Case file restored.", "केस फ़ाइल वापस लाई गई।"))
        except Exception as exc:  # malformed upload
            st.error(L(f"That file could not be read as a NyayaSetu case file ({exc}).", f"यह फ़ाइल NyayaSetu केस फ़ाइल के रूप में नहीं पढ़ी जा सकी ({exc})।"))
    if c3.button(t("go_rights", lang), type="primary"):
        go("rights")


def render_source(s: dict) -> str:
    status_txt = {"verified": L("verified", "सत्यापित"), "verified_secondary": L("verify before relying", "भरोसे से पहले जाँचें"),
                  "needs_verification": L("not verified", "सत्यापित नहीं")}[s["status"]]
    return (f"<div class='src'><b>{esc(s['short_cite'])}</b><span class='status {s['status']}'>{esc(status_txt)}</span><br>{esc(s['plain'])}"
            f"<div class='ex'>{esc(L('Official text', 'आधिकारिक पाठ'))}: {esc(s['excerpt'][:420])}{'…' if len(s['excerpt']) > 420 else ''}</div>"
            f"<div class='ex'>{esc(s['issuing_authority'])} · {esc(L('checked', 'जाँचा गया'))} {esc(s['verified_on'])} · "
            f"<a href='{esc(s['url'])}' target='_blank' rel='noopener'>{esc(L('open source', 'स्रोत खोलें'))}</a></div></div>")


def page_rights():
    if not need_case():
        return
    SS.visited.add("rights")
    tracker()
    a = get_analysis(SS.lang)
    r = a["rights"]
    st.markdown(f"# {esc(t('nav_rights', SS.lang))}")
    gen = r["summary"]["generated_by"]
    badge = (L("Rule-based explanation (demo mode — no AI model used)", "नियम-आधारित स्पष्टीकरण (डेमो मोड — कोई AI मॉडल नहीं)") if gen == "rules"
             else L(f"AI-written ({gen.split(':', 2)[-1]}) and checked against the verified sources", f"AI द्वारा लिखा गया ({gen.split(':', 2)[-1]}) और सत्यापित स्रोतों से जाँचा गया"))
    st.markdown(f"<div class='panel'><span class='mode {'demo' if gen == 'rules' else 'live'}'>{esc(badge)}</span>"
                f"<p style='margin:.6rem 0 0 0;line-height:1.6'>{esc(r['summary']['text'])}</p>"
                + (f"<div class='muted' style='margin-top:.4rem;font-size:.82rem'>{esc(r['summary']['note'])}</div>" if r["summary"].get("note") else "")
                + "</div>", unsafe_allow_html=True)
    st.caption(L("Each point below is labelled: what the law requires, a possible argument that depends on your evidence, a procedure, or a possible remedy. Nothing here guarantees an outcome.",
                 "नीचे हर बिंदु पर लेबल है: कानून क्या अपेक्षा करता है, सबूत पर निर्भर संभावित तर्क, प्रक्रिया, या संभावित राहत। यहाँ कुछ भी किसी परिणाम की गारंटी नहीं है।"))
    for i in r["issues"]:
        law = "".join(render_source(s) for s in i["law"])
        ev_have = ", ".join(i["evidence_have"]) or "—"
        ev_miss = ", ".join(i["evidence_missing"])
        unc = "".join(f"<li>{esc(u)}</li>" for u in i["uncertain"])
        st.markdown(f"""<div class='issue {i['label']}'>
<span class='chip {i['label']}'>{esc(i['label_text'])}</span><span class='chip conf'>{esc(i['confidence_text'])}</span>
<h4>{esc(i['title'])}</h4>
<div class='sec'>{esc(t('how_applies', SS.lang))}</div><div style='line-height:1.55'>{esc(i['how_applies'])}</div>
<div class='sec'>{esc(t('evidence_support', SS.lang))}</div><div>{esc(ev_have)}{('<br><span class="muted">' + esc(L('Still useful to get: ', 'यह भी उपयोगी होगा: ') + ev_miss) + '</span>') if ev_miss else ''}</div>
<div class='sec'>{esc(t('what_next', SS.lang))}</div><div>{esc(i['next_step'])}</div>
{('<div class="sec">' + esc(t('uncertain', SS.lang)) + '</div><ul style="margin:.1rem 0 0 1.1rem">' + unc + '</ul>') if unc else ''}
<div class='sec'>{esc(t('law_says', SS.lang))} · {esc(t('official_source', SS.lang))}</div>{law}
</div>""", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        items = "".join(f"<li>{esc(u)}</li>" for u in r["uncertainties"]) or f"<li>{esc(L('None flagged.', 'कुछ चिह्नित नहीं।'))}</li>"
        st.markdown(f"<div class='warnbox'><b>{esc(t('uncertain', SS.lang))}</b><ul style='margin:.3rem 0 0 1.1rem'>{items}</ul></div>", unsafe_allow_html=True)
    with c2:
        items = "".join(f"<li>{esc(u)}</li>" for u in r["lawyer_triggers"])
        st.markdown(f"<div class='disclaimer'><b>{esc(t('need_lawyer', SS.lang))}</b><ul style='margin:.3rem 0 0 1.1rem'>{items}</ul></div>", unsafe_allow_html=True)
    for n in r["notices"]:
        st.markdown(f"<div class='issue notice'><span class='chip'>{esc(L('Notice', 'सूचना'))}</span><h4>{esc(n['title'])}</h4>{render_source(n)}</div>",
                    unsafe_allow_html=True)
    st.markdown(f"### {esc(t('ask_question', SS.lang))}")
    with st.form("qa_form"):
        q = st.text_input(L("For example: How long do I have to file? Do I need a lawyer? Is there a fee?",
                            "उदाहरण: शिकायत कब तक कर सकता हूँ? क्या वकील ज़रूरी है? क्या शुल्क लगता है?"))
        asked = st.form_submit_button(L("Find the answer in verified sources", "सत्यापित स्रोतों में उत्तर खोजें"))
    if asked and q.strip():
        SS.qa = answer_question(q.strip(), SS.case, SS.lang, KB, SS.llm)
    if SS.qa:
        qa = SS.qa
        if qa.get("answer"):
            st.markdown(f"<div class='okbox'>{esc(qa['answer'])}<div class='muted' style='font-size:.8rem'>{esc(L('AI answer, checked against the sources below', 'AI उत्तर, नीचे के स्रोतों से जाँचा गया'))}</div></div>",
                        unsafe_allow_html=True)
        else:
            st.caption(L("Demo mode: showing the verified source passages most relevant to your question (no AI-written answer).",
                         "डेमो मोड: आपके प्रश्न से सबसे संबंधित सत्यापित स्रोत अंश दिखाए जा रहे हैं (AI द्वारा लिखा उत्तर नहीं)।") if not qa.get("note") else qa["note"])
        for p in qa["passages"]:
            src = KB.get(p["id"])
            st.markdown(render_source({"short_cite": src["short_cite"], "status": src["verification_status"], "plain": p["plain"], "excerpt": src["excerpt"],
                                       "issuing_authority": src["issuing_authority"], "verified_on": src["verified_on"], "url": src["url"]}), unsafe_allow_html=True)
    if st.button(t("go_complaint", SS.lang), type="primary"):
        go("complaint")


def page_complaint():
    if not need_case():
        return
    SS.visited.add("complaint")
    tracker()
    st.markdown(f"# {esc(t('nav_complaint', SS.lang))}")
    st.caption(L("Drafts are built only from your case file and the verified sources. They are not sent or filed. Edit them freely before downloading.",
                 "मसौदे केवल आपकी केस फ़ाइल और सत्यापित स्रोतों से बनते हैं। ये भेजे या दर्ज नहीं किए जाते। डाउनलोड से पहले इन्हें संपादित करें।"))
    c1, c2 = st.columns([2, 1])
    doc_labels = {DOC_TYPES[k][SS.lang]: k for k in DOC_TYPES}
    doc_type = doc_labels[c1.radio(t("doc_type", SS.lang), list(doc_labels))]
    lang_labels = {"English": "en", "हिंदी": "hi"}
    dlang = lang_labels[c2.selectbox(t("draft_lang", SS.lang), list(lang_labels), index=0 if SS.lang == "en" else 1)]
    a = get_analysis(dlang)
    d = a["documents"][doc_type]
    appr = d["appropriateness"]
    for note in appr["notes"]:
        st.markdown(f"<div class='warnbox'>{esc(note)}</div>", unsafe_allow_html=True)
    key = f"{SS.analysis_key}:{doc_type}:{dlang}"
    if key not in SS.doc_edits:
        SS.doc_edits[key] = d["text"]
    m1, m2 = st.columns(2)
    m1.markdown(f"<div class='panel'><b>{d['missing_count']}</b> {esc(L('field(s) still missing — highlighted as [MISSING] in the draft', 'फ़ील्ड अभी अनुपलब्ध — मसौदे में [अनुपलब्ध] के रूप में चिह्नित'))}"
                f"<br><span class='mode demo'>{esc(L('Template draft — built from your case file; no AI-written text (in every mode)', 'टेम्पलेट मसौदा — आपकी केस फ़ाइल से बना; कोई AI-लिखित पाठ नहीं (हर मोड में)'))}</span></div>",
                unsafe_allow_html=True)
    text = st.text_area(L("Your draft (editable)", "आपका मसौदा (संपादन योग्य)"), value=SS.doc_edits[key], height=520, key=f"ta_{key}")
    SS.doc_edits[key] = text
    rep = validate_text(text)
    if rep.ok:
        m2.markdown(f"<div class='okbox'>{esc(L(f'All {len(rep.citations_found)} legal references in this draft match verified sources.', f'इस मसौदे के सभी {len(rep.citations_found)} कानूनी संदर्भ सत्यापित स्रोतों से मेल खाते हैं।'))}</div>",
                    unsafe_allow_html=True)
    else:
        probs = "; ".join(f"{p.text} — {p.detail}" for p in rep.problems[:5])
        m2.markdown(f"<div class='warnbox'>{esc(L('Check your edits: ', 'अपने बदलाव जाँचें: ') + probs)}</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1, 1.4])
    fname = f"{SS.case['case_id']}_{doc_type}_{dlang}"
    c1.download_button(t("download_txt", SS.lang), text.encode("utf-8"), file_name=f"{fname}.txt", mime="text/plain")
    try:
        pdf = text_to_pdf(text, d["title"], dlang)
        c2.download_button(t("download_pdf", SS.lang), pdf, file_name=f"{fname}.pdf", mime="application/pdf")
    except Exception as exc:
        c2.error(f"PDF could not be generated: {exc}")
    if c3.button(L("Discard my edits and regenerate", "मेरे बदलाव हटाकर फिर से बनाएँ")):
        SS.doc_edits.pop(key, None)
        st.session_state.pop(f"ta_{key}", None)
        st.rerun()
    st.markdown(f"<div class='disclaimer'>{esc(L('This is a draft prepared by software, not a legal notice and not a filed complaint. Read it fully and correct anything inaccurate before you send or file it.', 'यह सॉफ़्टवेयर द्वारा तैयार मसौदा है, कानूनी नोटिस या दर्ज की गई शिकायत नहीं। भेजने या दर्ज करने से पहले इसे पूरा पढ़ें और जो गलत हो उसे सुधारें।'))}</div>",
                unsafe_allow_html=True)
    st.write("")
    if st.button(t("go_steps", SS.lang), type="primary"):
        go("steps")


def page_steps():
    if not need_case():
        return
    SS.visited.add("steps")
    tracker()
    a = get_analysis(SS.lang)
    st.markdown(f"# {esc(t('nav_steps', SS.lang))}")
    st.caption(L("A practical order of steps. NyayaSetu does not invent waiting periods: the only timelines mentioned come from the verified sources.",
                 "कदमों का व्यावहारिक क्रम। NyayaSetu कोई प्रतीक्षा अवधि नहीं गढ़ता: बताई गई समय-सीमाएँ केवल सत्यापित स्रोतों से हैं।"))
    for n, s in enumerate(a["plan"], 1):
        done = s["key"] in SS.steps_done
        site = ""
        if s["website"]:
            site = (f"<a href='{esc(s['website']['url'])}' target='_blank' rel='noopener'>{esc(s['website']['label'])}</a>" if s["website"].get("url")
                    else esc(s["website"]["label"]))
        status = {"partly_done": L("Partly done", "आंशिक रूप से किया"), "optional": L("Optional", "वैकल्पिक"), "todo": ""}.get(s["status"], "")
        st.markdown(f"""<div class='step {'done' if done else ''}'><div class='n'>{'✓' if done else n}</div><div style='flex:1'>
<div style='font-weight:600;color:#14325C;font-size:1.02rem'>{esc(s['title'])} {('<span class="chip">' + esc(status) + '</span>') if status else ''}</div>
<div class='sec'>{esc(L('What to do', 'क्या करें'))}</div><div>{esc(s['what'])}</div>
<div class='sec'>{esc(L('Why it matters', 'यह क्यों ज़रूरी है'))}</div><div>{esc(s['why'])}</div>
{('<div class="sec">' + esc(L('Official website', 'आधिकारिक वेबसाइट')) + '</div><div>' + site + '</div>') if site else ''}
<div class='sec'>{esc(L('Evidence to keep', 'कौन-से सबूत रखें'))}</div><div>{esc(', '.join(s['evidence']))}</div></div></div>""", unsafe_allow_html=True)
        if st.checkbox(L("Mark as done", "पूरा हुआ"), value=done, key=f"done_{s['key']}"):
            SS.steps_done.add(s["key"])
        else:
            SS.steps_done.discard(s["key"])
    disclaimer()


def page_sources():
    st.markdown("<div class='tricolor'></div>", unsafe_allow_html=True)
    st.markdown(f"# {esc(t('nav_sources', SS.lang))}")
    meta = KB.meta
    st.markdown(f"<div class='panel'><b>{esc(L('Scope', 'दायरा'))}:</b> {esc(meta['scope'])}<br><span class='muted'>"
                f"{esc(L('Knowledge base compiled and checked on', 'ज्ञान-आधार संकलित और जाँचा गया'))} {esc(meta['compiled_on'])} · {len(KB.entries)} "
                f"{esc(L('entries', 'प्रविष्टियाँ'))}</span></div>", unsafe_allow_html=True)
    st.markdown(f"### {esc(L('How NyayaSetu avoids made-up law', 'NyayaSetu गढ़े हुए कानून से कैसे बचता है'))}")
    st.markdown(L("""
1. **Curated sources only.** Every legal point comes from the small knowledge base below, each entry with its official URL, issuing authority, excerpt and the date it was checked.
2. **Retrieve, then explain.** Legal explanations are assembled from those entries; the app never answers legal questions from a model's memory.
3. **Validator on every output.** Each draft and AI response is scanned for section/rule numbers, case citations and other Acts. Anything not in the verified knowledge base is flagged; AI text that fails is discarded and the rule-based text is shown instead.
4. **Labels on every conclusion.** Statutory rule, possible argument, procedure, possible remedy, or notice — so you can see what is certain and what depends on facts.
5. **No case law.** The knowledge base contains no court judgments, so NyayaSetu cites none.
""", """
1. **केवल चुने हुए स्रोत।** हर कानूनी बिंदु नीचे के छोटे ज्ञान-आधार से आता है — हर प्रविष्टि के साथ आधिकारिक URL, जारीकर्ता, अंश और जाँच की तारीख।
2. **पहले खोज, फिर स्पष्टीकरण।** कानूनी स्पष्टीकरण इन्हीं प्रविष्टियों से बनते हैं; ऐप किसी मॉडल की याददाश्त से कानूनी उत्तर नहीं देता।
3. **हर आउटपुट पर जाँच।** हर मसौदे और AI उत्तर में धारा/नियम संख्या, केस उद्धरण और अन्य अधिनियम खोजे जाते हैं। जो सत्यापित ज्ञान-आधार में नहीं, वह चिह्नित होता है; विफल AI पाठ हटाकर नियम-आधारित पाठ दिखाया जाता है।
4. **हर निष्कर्ष पर लेबल।** कानूनी नियम, संभावित तर्क, प्रक्रिया, संभावित राहत, या सूचना।
5. **कोई केस-लॉ नहीं।** ज्ञान-आधार में कोई न्यायिक निर्णय नहीं है, इसलिए NyayaSetu कोई उद्धृत नहीं करता।
"""))
    kind = {"primary_statute": L("Statute (law)", "अधिनियम (कानून)"), "primary_rules": L("Rules (law)", "नियम (कानून)"),
            "official_guidance": L("Official guidance (practical, not law)", "आधिकारिक मार्गदर्शन (व्यावहारिक, कानून नहीं)"),
            "official_press_release": L("Notice — verify before relying", "सूचना — भरोसे से पहले जाँचें"),
            "secondary_report": L("Notice — verify before relying", "सूचना — भरोसे से पहले जाँचें")}
    rows = [{"ID": e["id"], L("Kind", "प्रकार"): kind.get(e.get("source_type"), e.get("source_type")),
             L("Provision", "प्रावधान"): e["short_cite"], L("Status", "स्थिति"): e["verification_status"],
             L("Checked on", "जाँच तिथि"): e["verified_on"], L("Issued by", "जारीकर्ता"): e["issuing_authority"], "URL": e["url"]} for e in KB.entries]
    st.dataframe(rows, width="stretch", hide_index=True, column_config={"URL": st.column_config.LinkColumn("URL")})
    with st.expander(L("Verification log and corrections made during research", "सत्यापन लॉग और शोध के दौरान किए गए सुधार")):
        for v in meta.get("verification_log", []):
            st.markdown(f"- **{v['item']}** ({v['date']}): {v['method']}")
        st.markdown("**" + L("Corrections", "सुधार") + "**")
        for c in meta.get("builder_corrections", []):
            st.markdown(f"- {c}")
    st.markdown(f"### {esc(L('Known limitations', 'ज्ञात सीमाएँ'))}")
    st.markdown(L("""
- Covers online consumer purchases only (damaged, defective, non-delivery, misleading listing, wrong charge, refund). Not banking, insurance, housing, employment or criminal matters.
- The knowledge base is small and was checked on one date. Laws change: the E-Commerce Rules have amendments taking effect on 1 January 2027.
- In demo mode, fact extraction uses keyword rules. Unusual phrasing, typos, Hinglish and long stories can be misread — always check the case file.
- Drafts quote your words; they cannot verify that your facts are true or complete.
- NyayaSetu does not know the outcome of any case and cannot predict one. It cannot represent you or file anything for you.
""", """
- केवल ऑनलाइन उपभोक्ता खरीद (क्षतिग्रस्त, दोषपूर्ण, डिलीवरी नहीं, भ्रामक लिस्टिंग, गलत कटौती, रिफंड)। बैंकिंग, बीमा, आवास, रोज़गार या आपराधिक मामले नहीं।
- ज्ञान-आधार छोटा है और एक तारीख को जाँचा गया। कानून बदलते हैं: ई-कॉमर्स नियमों के संशोधन 1 जनवरी 2027 से लागू होंगे।
- डेमो मोड में तथ्य-निष्कर्षण कीवर्ड नियमों पर आधारित है। असामान्य भाषा, टाइपो, हिंग्लिश और लंबी कहानियाँ गलत पढ़ी जा सकती हैं — केस फ़ाइल हमेशा जाँचें।
- मसौदे आपके शब्द उद्धृत करते हैं; वे यह जाँच नहीं सकते कि आपके तथ्य सही या पूरे हैं।
- NyayaSetu किसी मामले का परिणाम नहीं जानता और अनुमान नहीं लगा सकता। यह आपका प्रतिनिधित्व या आपकी ओर से कुछ दर्ज नहीं कर सकता।
"""))
    st.markdown(f"### {esc(L('How your information is handled', 'आपकी जानकारी कैसे संभाली जाती है'))}")
    st.markdown(L("""
- Your case lives only in this browser session; the app writes nothing to disk and keeps no logs of conversations. Closing the tab or pressing *Clear my case* removes it.
- Downloads (JSON, TXT, PDF) are generated in memory and go straight to your device.
- NyayaSetu never asks for Aadhaar, PAN, card numbers, bank passwords or OTPs, and masks them if typed.
- In demo mode nothing leaves this computer. If an AI API is configured, your case facts (not identity numbers) are sent to that provider to write explanations.
""", """
- आपका मामला केवल इस ब्राउज़र सत्र में रहता है; ऐप डिस्क पर कुछ नहीं लिखता और बातचीत का लॉग नहीं रखता। टैब बंद करने या *मेरा मामला हटाएँ* दबाने पर यह मिट जाता है।
- डाउनलोड (JSON, TXT, PDF) मेमोरी में बनते हैं और सीधे आपके डिवाइस पर जाते हैं।
- NyayaSetu कभी आधार, पैन, कार्ड नंबर, बैंक पासवर्ड या OTP नहीं माँगता, और लिखे जाने पर उन्हें छिपा देता है।
- डेमो मोड में कुछ भी इस कंप्यूटर से बाहर नहीं जाता। AI API सेट होने पर, स्पष्टीकरण लिखने के लिए आपके मामले के तथ्य (पहचान संख्याएँ नहीं) उस प्रदाता को भेजे जाते हैं।
"""))
    disclaimer()


# ---------------------------------------------------------------- router
if SS.page in WORKFLOW and (SS.page == "intake" or SS.case is not None):
    SS.visited.add(SS.page)  # mark before the sidebar renders so the progress count is current
sidebar()
{"home": page_home, "intake": page_intake, "case": page_case, "rights": page_rights,
 "complaint": page_complaint, "steps": page_steps, "sources": page_sources}[SS.page]()
