# NyayaSetu — Quality Evaluation Report

Final runs: **8 November 2026**. Scenario reference date: **7 November 2026** (pinned so that "three weeks ago" resolves the same way every run).
Mode for every result below: **demo (deterministic rules, no LLM API connected)**.
Raw, unedited outputs: `outputs/raw_outputs/` (one folder per scenario) and `outputs/generated_complaints/` (32 PDFs).
Re-run (after `pip install -r requirements.txt`): `python tests/run_tests.py`, `python tests/test_llm_provider.py`, `python tests/test_app_journey.py`.
**Which results need which packages, and which tests were actually executed where, is in §2a.** Two of the three scripts need packages beyond the core ones (Streamlit; the `anthropic` SDK); without them those tests are reported as **NOT RUN**, never as passed.

## 1. Method

| Layer | What was checked | How |
|---|---|---|
| Scenario runs | 7 scenarios (5 required + 2 deliberately difficult), driven through the real intake engine with scripted answers to whatever questions the app chose to ask | `tests/run_tests.py` |
| Automated checks | Category; field-level extraction vs expected values; required sources present; every citation in every draft and explanation validated against the KB; forbidden over-claims absent; missing fields marked; threshold flags; **refund amount in every draft equals the amount the user confirmed, or is marked [MISSING] — never the price by default** | same script → `automated_checks.json/.md` |
| Claimed-amount paths | 7 conversations: "full", a partial amount with a reason, an unclear answer (re-asked), unclear twice, skipped, Hindi "पूरा", and "yes" to the excess on a wrong charge | same script → `claim_amount_test.json` |
| Manual review | I read every conversation, case file, rights analysis and draft looking for errors the automated checks cannot see | §3 |
| Legal re-verification | Every knowledge-base entry and URL re-checked against its source on 8 Nov 2026 | §4 |
| Hallucination injection | A scripted fake LLM returns (a) a fabricated section + fake case law, (b) another Act + a promise, (c) an untagged answer, (d) a grounded answer | validator must reject a–c and accept d |
| LLM integration | 22 checks. **16** use a recording fake client (request shape, model ID configuration, fallbacks) and need no extra package. **6** drive the **real `anthropic` SDK (2.6.0) against a local mock server** and need the `anthropic` package | `tests/test_llm_provider.py` |
| Retrieval probes | 15 user questions (English, Hindi, Hinglish) with acceptable sources | top-1 / top-3 |
| Privacy | Aadhaar, card, PAN, OTP masked; order IDs, prices and a Hindi sentence mentioning "OTP" left intact | 8 inputs with expected outcomes |
| UI journey | Three end-to-end journeys through the Streamlit app (23 steps), including entering a partial refund on the Case Summary page — **needs Streamlit**. Plus a one-off real-browser pass with screenshots (Playwright + Chromium, build environment only; not a supplied script) | `tests/test_app_journey.py`, Playwright |
| Held-out stories | 3 stories written after the test set | §5 |

Caveat: the expected values and automated checks were written by the same person (with AI help) who wrote the rules, so passing them shows internal consistency, not real-world accuracy. The manual review, legal re-verification and held-out runs are the more honest signal.

## 2. Evaluation table (final run, 8 Nov 2026)

| Case | Facts extracted correctly? | Relevant provisions identified correctly? | Citations valid? | Complaint usable? | Next steps appropriate? | Errors / limitations observed |
|---|---|---|---|---|---|---|
| **TC01** Failed refund — damaged phone ₹18,000, refund postponed 3 weeks | Yes — 10/10 fields; "three weeks ago" → 17 Oct 2026 (approx.). User chose "Refund"; app asked how much; "full" → **₹18,000 claimed** | Yes — defect (s.2(10), 2(6)(ii)), E-Com Rule 6(3)/7(4), refund Rule 4(10), grievance officer Rules 4(4)/(5); **s.2(47)(viii) held "not yet established"** (21 days) | Yes — 23 citations in 4 drafts | Yes, after adding contact details ([ADD]) and, for the Commission draft, two addresses ([MISSING]) | Yes — grievance officer, NCH, then e-Jagriti | Whether the refund was formally "accepted" (needed for Rule 4(10)) is unknown — flagged. |
| **TC02** Non-delivery ₹4,500 — **in Hindi** | Yes — 10/10; "पूरा पैसा वापस चाहिए" recorded as **₹4,500 (full) claimed** without a further question | Yes — deficiency (s.2(11)), Rule 6(3) late-delivery limb with force-majeure proviso, grievance officer, NCH | Yes — 40 citations (Hindi + English drafts) | Yes | Yes — includes "ask for proof of delivery" | Non-delivery flow does not ask personal vs business use. English draft quotes the Hindi words untranslated. Hindi not reviewed by a native speaker. |
| **TC03** Defective washing machine ₹25,000, replacement refused | Yes — 10/10. **No money claim** (replacement requested), so no amount asked or assumed | Yes — defect, Rule 6(3), product-liability scope (harm to the product itself excluded, s.2(22)); s.2(47)(viii) **not** asserted (replacement, not refund) | Yes — 20 citations | Yes | Yes | Manufacturer/brand not suggested as an opposite party. |
| **TC04** Misleading listing — smartwatch "waterproof + GPS", ₹6,999 | Yes — 9/9; listing screenshot detected. "refund" → asked → "The full ₹6,999" → **₹6,999 claimed** | Yes — s.2(28), s.2(47)(i)(a), Rule 6(3) (*"not of the characteristics or features as advertised or as agreed to"* — wording corrected this pass), Rule 6(4)(c), s.17 | Yes — 23 citations | Yes | Yes — "screenshot the listing today"; optional report to authorities | Depends on proof of the original listing. |
| **TC05** Unresolved complaint — charged ₹2,480 for a ₹1,240 order via UPI | Yes — 10/10. "Refund of the extra ₹1,240" → **₹1,240 (excess) claimed** | Yes — s.2(6)(iv), Rule 4(10), s.2(11), RBI scheme shown only as a notice | Yes — 17 citations | Yes; every draft asks for the **excess** only | Yes — adds "raise the duplicate debit with your bank/UPI app" | No complaint date ("over the last two weeks"), so grievance-officer timing not computed. |
| **TC06 (difficult)** Vague: "bought something online, not working…" | N/A — 13 missing items listed with reasons. Outcome skipped → **nothing claimed, nothing assumed** | Partly — category guessed "defective" from "not working" | Yes — 19 citations | Skeleton only: 10–14 `[MISSING]` markers per draft | Yes — starts with preserving evidence | 12 questions, all skipped — tedious for a vague user ("Build my case now" is the escape). |
| **TC07 (difficult)** Phones bought **for resale**, March 2024, 4 of 10 defective, paid ₹1,20,000 | Yes — 4/4. "Refund for the 4 defective phones" had no amount → app asked → **₹48,000 claimed (partial)** | Yes for the threshold issues: s.2(7) commercial-purpose exclusion; **s.69 limit likely expired**; summary opens with "IMPORTANT — get legal advice"; Commission draft has two CAUTION notes | Yes — 23 citations | Not without a lawyer, by design. Prayer now reads *"Refund ₹48,000 (out of the ₹1,20,000 paid), as stated: '…4 defective phones (₹12,000 each)'"* — **previous full-price error fixed** | Yes — Commission step says get advice first | Whether the E-Commerce Rules apply to a B2B wholesale site is not flagged. |

**Automated results (final run, full install of `requirements.txt`, Python 3.11.18 and 3.13.18):** category 7/7; expected fields 53/53; scenario checks 61/61; 165 citations in 32 drafts and all rights explanations match the verified KB; **refund amount correct in all 32 drafts** (5 scenarios with a money claim, 2 without); claimed-amount paths 7/7; hallucination injection 4/4; privacy 8/8; retrieval top-1 13/15, top-3 15/15 — all from `tests/run_tests.py`, which needs no optional package. **LLM-integration checks 22/22** (16 fake-client + 6 real-SDK; the 6 need `anthropic`) and **UI journeys 23/23 steps** (needs Streamlit) were executed only where those packages were installed — see §2a. These numbers describe this test set only and are not an accuracy rate for real users.

**Remaining test failures:** two retrieval probes still rank a related source above the best one ("Can I complain about a fake advertisement?" → Rule 6(3) first; "I bought it for my shop, am I a consumer?" → s.2(6) first; the best source is in the top 3 in both). No other automated check fails.

## 2a. Which tests were executed, and where

Every automated number in this report comes from one of the environments below; the three test scripts were run from the final zip in each of them on 8 Nov 2026. "NOT RUN" means the test did not execute; it is never counted as a pass. Re-running `run_tests.py` reproduces every saved text output in `outputs/` exactly, except each case file's randomly generated case ID.

| Test | Needs (besides Python 3.11+) | Full install: `pip install -r requirements.txt` (clean venvs, Python 3.11.18 and 3.13.18) | Core packages only, **no Streamlit, no `anthropic`** (Python 3.11.18 — same situation as the independent review) |
|---|---|---|---|
| `tests/run_tests.py` — 7 scenarios, citations, claimed amounts, hallucination injection, privacy, retrieval | `fpdf2`; `uharfbuzz` for correctly shaped Hindi PDFs | **Executed** — 61/61 scenario checks, 53/53 fields, claim paths 7/7, hallucination 4/4, privacy 8/8; retrieval top-1 13/15, top-3 15/15; exit 0 | **Executed** — identical results, exit 0. Also run with `fpdf2` alone (no `uharfbuzz`, `requests`, `python-dotenv`): identical results, plus a printed warning that the Hindi PDFs are unshaped |
| `tests/test_llm_provider.py` — 16 fake-client checks | nothing extra | **Executed** 16/16 | **Executed** 16/16 |
| `tests/test_llm_provider.py` — 6 real-SDK checks against a local mock server | `anthropic` | **Executed** 6/6 (SDK 2.6.0) → **22/22 in total** | **NOT RUN** (6 of 22) |
| `tests/test_app_journey.py` — 3 journeys, 23 steps | `streamlit` | **Executed** 23/23 steps; exit 0 | **NOT RUN** — prints the reason, exit code 2 |
| Real-browser screenshots | `streamlit`, Playwright, Chromium | Run once in the build environment (Python 3.13, 8 Nov); not a supplied script | Not run |
| Live Anthropic API call (`python -m core.llm_provider`) | `anthropic` + an API key | **Not run** — no key available | Not run |

**Reconciling 22/22 with the independent review's 17/17.** The script defines 22 checks: 16 that use a fake client and 6 that use the real `anthropic` SDK. When the SDK was not installed, the previous version of the script replaced the 6 SDK checks with one placeholder line ("real SDK test skipped") and **counted that placeholder as a passed check**: 16 real checks + 1 placeholder = "17/17". So the review environment actually executed **16 checks, all passing, and none of the 6 SDK checks**. The 22/22 in this report was measured with `anthropic` 2.6.0 installed, where all 22 execute. This report also did not previously say which results depended on optional packages. Both are corrected: the script now prints each missing check as `NOT RUN` and ends with *"16/16 LLM-integration checks executed and passed; 6 of 22 NOT RUN (anthropic package not installed …)"*. With the SDK installed it prints *"22/22 … (all 22 defined checks executed)"*. The UI-journey script now prints `NOT RUN` with exit code 2 instead of a `ModuleNotFoundError` traceback. `run_tests.py` now ends with a `SUMMARY` and a `RESULT` line and exits 1 if any gated check fails (confirmed by deliberately changing one expected value: "checks 7/8 … RESULT: FAILED", exit 1).

## 3. Errors found and fixed

### 3a. Found by manual review during the build (7 Nov)

| # | Error | Severity | Status |
|---|---|---|---|
| 1 | "Can I file a consumer complaint **now**?" read as a complaint **number** (TC07) | Medium | Fixed |
| 2 | Draft said the defect appeared "shortly after delivery" — not said by the user (TC06) | High (fabrication) | Fixed |
| 3 | s.2(47)(viii) argued for a **replacement** request (TC03) | High (over-claiming) | Fixed |
| 4 | "pho**nes**" matched the "phoned" step pattern; a question recorded as a step taken (TC07) | Medium | Fixed |
| 5 | "Mobile **repair** shop" read as "wants a repair"; evidence/outcome questions skipped (TC03) | High | Fixed — always asked, detected values pre-selected |
| 6 | Key fact dropped from the quoted narrative (TC04) | High | Fixed |
| 7 | "I have not received the **full refund**" when only the excess was wanted (TC05) | Medium | Fixed |
| 8 | Validator flagged the app's own disclaimers as guarantees | Low | Fixed (negation-aware) |
| 9 | Hindi PDFs garbled mixed Hindi/English lines | Medium | Fixed (merged font) |
| 10 | Non-delivery OTP question skipped for a 12-word story (TC02) | Medium | Fixed |
| 11 | "How long do I have to file?" retrieved the decision-time provision | Medium | Fixed for that question; 2/15 probes still miss at top-1 |
| 12 | "Missing fields" counter included fields not printed in that draft | Low | Fixed |
| 13 | Relief claimed the **full price** when the user wanted a partial refund (TC07) | High | **Fixed 8 Nov** — see §3b and §6 |

### 3b. Found in the final submission pass (8 Nov)

| # | Error | Severity | Fix |
|---|---|---|---|
| 14 | No field for the amount being claimed; drafts filled the refund with the purchase price | High | Explicit claimed amount: asked whenever a refund is wanted, re-asked once if unclear, never defaulted to the price; editable on the Case Summary page; drafts show `[MISSING: amount you are claiming — you paid ₹X]` until confirmed |
| 15 | For wrong-charge / refund cases with the outcome skipped, a "refund" outcome was **inferred** | Medium | Removed — now shown as missing |
| 16 | **Live Anthropic mode could never have worked:** the provider sent `temperature`, which current models (e.g. `claude-sonnet-5-5`) reject with a 400 error per Anthropic's migration guide. The app would have silently fallen back to demo text | High | Sampling parameters removed; text read only from `text` blocks (responses can start with thinking blocks); minimum `max_tokens` 4096 because it covers adaptive thinking; effort sent as `output_config.effort` with one retry without it if a model rejects it |
| 17 | KB and drafts paraphrased E-Commerce Rules 6(3)/7(4) as goods "not as advertised **or as per the description on the platform**" — the official text says *"not of the characteristics or features as advertised or as agreed to"* | High (misquoted law) | KB excerpts now verbatim; rights page and complaint grounds corrected |
| 18 | NCH described as "does not guarantee a remedy" / "cannot force a resolution" — not stated in any source checked | Medium (unsourced claim) | Replaced with verified wording: pre-litigation step, up to 30 days, convergence companies, option to approach the Commission |
| 19 | Foreign-platform limb attributed to Rule 2 generally (it is Rule 2(2)); ticket-number duty (Rule 5(3)(b)) stated for all platforms (it applies to marketplaces); s.39 excerpt simplified clause (a) and folded costs (clause (m)) into (a)–(d) | Low | Corrected |
| 20 | 2026 amendment notice listed a change ("join the NCH convergence process") not in the source summary | Low | Removed |
| 21 | Jurisdiction Rules URL contained raw spaces | Low | Percent-encoded; link verified |
| 22 | Retrieval regression after the corrected (longer) e-Jagriti excerpt: "Which court should I go to?" ranked e-Jagriti first | Low | Intent weight aligned with the other intents; back to 13/15 |
| 23 | My own LLM test first assumed the SDK sends `x-api-key`; SDK 2.6.0 sends `authorization: Bearer` | Test bug | Test accepts either |
| 24 | `test_llm_provider.py` counted its "SDK not installed" placeholder as a passed check, so a run without `anthropic` printed 17/17 although only 16 checks executed (found by the independent review) | Test-reporting bug | Missing checks are listed as `NOT RUN` and excluded from the pass count; §2a |
| 25 | `test_app_journey.py` crashed with a traceback when Streamlit was missing, and the report did not say which tests need which packages | Test-reporting gap | Clear `NOT RUN` message, exit code 2; §2a added |
| 26 | `run_tests.py` printed per-case results but always exited 0, even if a check failed | Test-reporting gap | `SUMMARY` + `RESULT` lines; exit 1 on any failed gated check |

## 4. Legal re-verification (8 Nov 2026)

| Group | Entries | Result |
|---|---|---|
| Consumer Protection Act, 2019 (India Code PDF) | 16 | All cited sections/clauses confirmed: 2(6)(i)–(iv),(vii); 2(7) + Explanations; 2(9); 2(10); 2(11); 2(22); 2(28); 2(34); 2(47)(i)(a),(vii),(viii); 17; 34(2); 35(1); 38(7); 39(1); 69; 83; 84(1); 86. One excerpt refined (s.39) |
| E-Commerce Rules, 2020 (G.S.R. 462(E), 23 Jul 2020) | 7 | Rules 4(4), 4(5), 4(10), 5(3), 6(4) confirmed; **6(3), 7(4), 2 corrected** (above) |
| Jurisdiction Rules, 2021 (G.S.R. 912(E)) and fee table (G.S.R. 606(E), 17 Aug 2023) | 2 | Confirmed: ₹50 lakh / ₹2 crore limits; nil fee up to ₹5 lakh |
| NCH, e-Jagriti | 2 | Confirmed from consumerhelpline.gov.in, PIB (14 Mar 2025, 23 Dec 2025) and Lok Sabha USQ 4546; NCH wording corrected; e-jagriti.gov.in confirmed as the official address |
| Notices (verify before relying) | 3 | E-Commerce (Amendment) Rules 2026 — dates confirmed (notified 9 Sep 2026, in force 1 Jan 2027) via SCC Online/TaxHeal; not yet listed on consumeraffairs.nic.in. CCPA ad guidelines (9 Jun 2022) and s.21(2) penalties confirmed via official press release; guidelines' full text not reviewed. RB-IOS 2026 (1 Jul 2026) from a news report only |

No new legal provisions were added. The statute/rules vs guidance vs notice distinction is shown on every issue card and, now, as a "Kind" column on the Legal Sources page. Lawyer-referral warnings are unchanged and still trigger for TC07 (commercial purpose, limitation) and for harm, high value and fraud.

## 5. Held-out stories (written after the test set, 7 Nov)

| Story | First result | After rule additions |
|---|---|---|
| "Ordered shoes from Myntra for 2499, got the wrong size…" | Category unknown; amount missed | "Not as described"; ₹2,499 found (label fits a wrong-size delivery only loosely) |
| Hinglish laptop story | Category unknown; amount missed | Defective; ₹15,000 found |
| "Refund of Rs. 3,200 … approved on 1 Oct" | 1 Oct stored as purchase date | Stored as refund-approval date |

Two of three unseen stories failed classification on first contact. **Rule-based extraction is brittle outside the phrasing it was built for**; the fallback category question and the editable case file are what keep a user on track in demo mode.

## 6. How the claimed amount works (new)

* Asked only when the user wants a refund (or "deliver or refund"). Wording adapts: "You paid ₹18,000. Reply 'full' … or type the amount you are claiming"; for wrong charges: "Reply 'yes' for the extra ₹1,240".
* Accepted answers: an amount (₹/Rs/rupees or a bare number that is not a count or order number), "full"/"पूरा", "yes"/"extra" (wrong charges only). An amount stated with the outcome ("Refund of the extra ₹1,240", "पूरा पैसा वापस") is accepted without asking again.
* Unclear answer → asked once more with an explanation; still unclear or skipped → left **unconfirmed**, listed in missing information, and every draft shows `[MISSING: amount you are claiming — you paid ₹X]`.
* A claim above the price is accepted with a warning that compensation is asked for separately.
* "Full" and "excess" follow the price/charges if the user later corrects them; any other confirmed amount is kept exactly as stated.

## 7. Remaining limitations

1. Demo-mode extraction is keyword-based (§5); Hinglish and unusual phrasing are weak; dates attach to the nearest keyword in a sentence.
2. The claimed amount is a single total: no per-item breakdown, and for a partial refund the drafts do not say whether goods will be returned.
3. Marketplace vs inventory model is not determined; drafts mention Rule 6(3) and Rule 7(4).
4. The manufacturer/brand is never suggested as an opposite party.
5. KB: 30 entries (27 verified against official text, 3 notices), checked on 8 Nov 2026; the E-Commerce amendments in force from 1 Jan 2027 will need a KB update.
6. Hindi wording has not been reviewed by a native speaker or a lawyer.
7. **No live LLM call has been made.** The Anthropic path is verified only with a fake client and with the real SDK against a local mock server (the latter only where `anthropic` is installed); `python -m core.llm_provider` performs a real one-line test once a key is set.
8. The UI-journey test and the 6 real-SDK checks only execute with the full `requirements.txt` installed; in a minimal environment they are reported as NOT RUN (§2a).
9. Nothing here has been reviewed by a practising advocate.
