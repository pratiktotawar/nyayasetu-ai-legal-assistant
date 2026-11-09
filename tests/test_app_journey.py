"""Drives the Streamlit app end-to-end with streamlit.testing (no browser needed).

    python tests/test_app_journey.py

Needs Streamlit (installed by `pip install -r requirements.txt`). Without it the
script prints NOT RUN and exits with code 2 — it never reports a pass it did not run.
Exit codes: 0 = all steps passed, 1 = a step failed, 2 = not run.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("NYAYASETU_REFERENCE_DATE", "2026-11-07")
try:
    import streamlit  # noqa: E402
    from streamlit.testing.v1 import AppTest  # noqa: E402
except ImportError:
    print("NOT RUN: tests/test_app_journey.py needs Streamlit, which is not installed in this environment.\n"
          "Install the project requirements first:  pip install -r requirements.txt\n"
          "0 app-journey steps executed.")
    raise SystemExit(2)

log = []


def check(at, step):
    if at.exception:
        raise SystemExit(f"[{step}] EXCEPTION: {at.exception[0].value}")
    log.append(f"ok  {step}")


def click(at, label_part, step):
    for b in at.button:
        if label_part.lower() in (b.label or "").lower():
            b.click().run(timeout=60)
            check(at, step)
            return
    raise SystemExit(f"[{step}] button containing '{label_part}' not found; buttons: {[b.label for b in at.button]}")


at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
check(at, "home renders")
assert any("From consumer problem" in m.value for m in at.markdown), "hero missing"

# --- journey A: type a fresh story (the evaluator path) ---------------------------------
click(at, "Start My Legal Case", "start button -> intake")
at.text_area[0].input("I purchased a mobile phone worth ₹18,000 from an online shopping platform. The product arrived damaged. "
                      "I requested a refund three weeks ago, but the seller keeps postponing it.")
click(at, "Send", "send opening story")
assert any("Here is what I understood" in m.value for m in at.markdown), "no understanding summary"
at.text_area[0].input("Flipkart, seller: Gupta Mobile World")
click(at, "Send", "answer platform")
click(at, "Skip this question", "skip order id")
click(at, "Build my case now", "build now")
click(at, "Review my case summary", "go to case summary")
assert any("Missing information" in m.value for m in at.markdown), "missing-info box not shown"
# the story mentions a refund but no amount was confirmed: the app must not assume the full price
assert at.session_state["case"]["claim"]["refund_requested"] and not at.session_state["case"]["claim"]["confirmed"]
assert any("have not confirmed how much" in m.value for m in at.markdown), "unconfirmed-claim warning missing"
assert any(m["field"] == "claim.amount" for m in at.session_state["case"]["missing_info"]), "claim not in missing info"
# correct facts, and enter a partial refund amount
claim_inputs = [w for w in at.number_input if w.label.startswith("Refund amount you are claiming")]
claim_inputs[0].set_value(12000.0)

name_inputs = [w for w in at.text_input if "Your name" in w.label]
name_inputs[0].input("Rahul Verma")
order_inputs = [w for w in at.text_input if w.label == "Order ID"]
order_inputs[0].input("FK-1234-5678")
for b in at.button:
    if "Save corrections" in b.label:
        b.click().run(timeout=60)
check(at, "save corrections")
assert at.session_state["case"]["consumer"]["name"] == "Rahul Verma"
assert at.session_state["case"]["transaction"]["order_id"] == "FK-1234-5678"
assert at.session_state["case"]["provenance"]["transaction.order_id"] == "user-edited"
cl = at.session_state["case"]["claim"]
assert cl["confirmed"] and cl["amount"] == 12000.0 and cl["is_partial"] and cl["source"] == "user-edited", cl
assert any("Refund you are claiming" in m.value and "₹12,000" in m.value for m in at.markdown), "claim confirmation not shown"
log.append("    claimed amount entered on case page: ₹12,000 of ₹18,000 (partial, user-edited)")
click(at, "Understand my rights", "go to rights")
assert any("Rule-based explanation" in m.value for m in at.markdown), "demo-mode label missing"
assert any("indiacode.nic.in" in m.value for m in at.markdown), "official source links missing"
# question box
qa = [w for w in at.text_input if "For example" in w.label][0]
qa.input("How long do I have to file a complaint?")
for b in at.button:
    if "Find the answer" in b.label:
        b.click().run(timeout=60)
check(at, "ask a question")
assert at.session_state["qa"]["passages"], "no retrieved passages"
log.append("    top passage for limitation question: " + at.session_state["qa"]["passages"][0]["id"])
click(at, "Generate complaint", "go to complaint")
assert any("match verified sources" in m.value for m in at.markdown), "validation badge missing"
draft = at.text_area[0].value
assert "FK-1234-5678" in draft and "Rahul Verma" in draft, "edited facts not in draft"
assert "DRAFT PREPARED WITH NYAYASETU" in draft
assert "₹12,000" in draft and "out of the ₹18,000 paid" in draft, "claimed amount not used in draft"
assert "full amount of ₹18,000" not in draft, "draft assumed the full price"
assert any("Template draft" in m.value for m in at.markdown), "template-draft label missing"
# switch document type and language
[r for r in at.radio if r.label == "Document"][0].set_value("D. Consumer Commission complaint — preparation draft").run(timeout=60)
check(at, "commission draft")
assert "CONSUMER DISPUTES REDRESSAL COMMISSION" in at.text_area[0].value
assert "Refund ₹12,000 (out of the ₹18,000 paid)" in at.text_area[0].value, "commission prayer does not use the claimed amount"
[x for x in at.selectbox if x.label == "Draft language"][0].set_value("हिंदी").run(timeout=60)
check(at, "hindi draft")
assert "उपभोक्ता" in at.text_area[0].value
# user adds a fabricated citation -> validator warns
at.text_area[0].input(at.text_area[0].value + "\nसाथ ही Section 72A of the Act के तहत।").run(timeout=60)
check(at, "edit draft with fake citation")
assert any("72A" in m.value for m in at.markdown), "validator did not flag edited fake section"
dl = [d for d in at.get("download_button")]
log.append(f"    download buttons on complaint page: {len(dl)}")
click(at, "What should I do next", "go to next steps")
assert any("consumerhelpline.gov.in" in m.value for m in at.markdown)
assert any("e-jagriti.gov.in" in m.value for m in at.markdown)
for b in at.button:
    if b.label.endswith("Legal Sources & Limitations"):
        b.click().run(timeout=60)
check(at, "sources page")

# --- journey B: Hindi example loaded from the home page ---------------------------------
at2 = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
for b in at2.button:
    if b.key == "ex_TC02":
        b.click().run(timeout=60)
check(at2, "load Hindi example TC02")
assert at2.session_state["lang"] == "hi"
click(at2, "नमूना उत्तरों", "auto-answer Hindi example")
assert at2.session_state["intake"]["complete"]
click(at2, "मेरे मामले का सारांश देखें", "Hindi case summary")
click(at2, "आगे: मेरे अधिकार समझें", "Hindi rights page")
assert any("सत्यापित" in m.value for m in at2.markdown)

# --- journey C: difficult example with legal uncertainty --------------------------------
at3 = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
for b in at3.button:
    if b.key == "ex_TC07":
        b.click().run(timeout=60)
click(at3, "sample answers", "auto-answer TC07")
click(at3, "Review my case summary", "TC07 case")
click(at3, "Understand my rights", "TC07 rights")
assert any("IMPORTANT" in m.value and "consumer" in m.value for m in at3.markdown), "threshold warning missing"
assert at3.session_state["case"]["claim"]["amount"] == 48000.0, at3.session_state["case"]["claim"]
log.append("    TC07 example: partial claim ₹48,000 of ₹1,20,000 recorded from the user's answer")
steps = sum(1 for line in log if line.startswith("ok  "))
log.append(f"ALL APP JOURNEY CHECKS PASSED: {steps}/{steps} steps executed (Python {sys.version.split()[0]}, streamlit {streamlit.__version__})")
print("\n".join(log))
