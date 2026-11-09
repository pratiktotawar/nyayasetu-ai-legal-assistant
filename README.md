# NyayaSetu — Your AI Consumer Rights Assistant

*From consumer problem to legal action.*

NyayaSetu helps an ordinary person in India who has a problem with something they bought online — a refund that never came, a damaged or defective product, an order marked "delivered" that never arrived, a misleading listing, or a wrong charge. It turns their story (English or Hindi) into a structured case file, explains where they stand using **verified official sources only**, drafts four ready-to-edit documents, and gives a practical action plan.

> **Legal disclaimer.** NyayaSetu is an AI-assisted legal information and document-preparation tool. It does not replace a qualified advocate or constitute a lawyer-client relationship. Legal outcomes depend on facts and applicable law. Verify important legal decisions with a qualified professional.

---

## 1. Problem statement

Built for the Kuku AI Generalist Assignment, **Problem 2: Build an AI Lawyer** — a conversational AI that an ordinary person in India can talk to about a legal problem, which helps them act on it, is honest about what it does not know, says when they need a real lawyer, and does not invent laws, sections or past cases.

Most people never get help with everyday legal problems: a lawyer feels expensive, the process is confusing and the paperwork is intimidating, so they give up. NyayaSetu covers **one kind of problem in depth — online consumer disputes** — under the Consumer Protection Act, 2019 and the Consumer Protection (E-Commerce) Rules, 2020.

## 2. Main features

| Step | Page | What happens |
|---|---|---|
| 1 | **Start a Legal Case** | The user describes the problem in their own words (English or Hindi). Rules extract amount, dates ("three weeks ago" → a date), platform, seller, order ID, ticket number, evidence and steps taken, and classify the dispute. NyayaSetu then asks **only the questions still missing for that dispute type**, one at a time; every question can be skipped. If a refund is wanted, it asks **how much is being claimed** (full price, a partial amount, or only the excess on a wrong charge) and re-asks once if unclear — it never assumes the full price. Aadhaar/PAN/card numbers/OTPs typed by mistake are masked. |
| 2 | **My Case Summary** | Editable case file: nature of dispute, parties, timeline, financial loss, expected vs what happened, steps taken, evidence, desired resolution, **refund amount being claimed**, and a **missing-information list** explaining why each item matters. Every field records where it came from (rules / your answer / your correction / AI). Download or restore as JSON. |
| 3 | **Understand My Rights** | Issue cards labelled *What the law requires*, *Possible legal argument*, *Procedure*, *Possible remedy* or *Notice*, with a confidence label: plain-language explanation + official excerpt, how it may apply, evidence you have/still need, what to do, and the official source (URL, authority, date checked, verification status). Plus uncertainties, "when to speak to a lawyer", and a question box that retrieves verified passages. |
| 4 | **Generate Complaint** | A. email to the seller · B. complaint to the platform's grievance officer · C. National Consumer Helpline grievance · D. Consumer Commission preparation draft — in English or Hindi; editable; download as TXT or PDF. The relief asks for exactly the confirmed refund amount (or shows `[MISSING: amount you are claiming — you paid ₹X]`). Every draft is labelled as an unfiled draft; edits are re-validated live (adding a fake section number triggers a warning). |
| 5 | **Recommended Next Steps** | Preserve evidence → written complaint/grievance officer → keep references → category-specific steps → National Consumer Helpline → Consumer Commission via e-Jagriti. Each step: what to do, why, official website, evidence to keep. |

The **Home** page offers seven example scenarios, and **Legal Sources & Limitations** shows the full knowledge base, its verification log, known limitations and how data is handled. A lawyer referral warning appears for complex cases (commercial purchase, limitation period likely expired, injury/harm, high value, fraud).

## 3. Technology stack

| Layer | Technology |
|---|---|
| UI | Streamlit 1.67 (session-state only; nothing written to disk) |
| Language | Python 3.11+ (tested on 3.11, 3.12 and 3.13) |
| Intake, classification, legal rules | Deterministic Python rules (regex + keyword scoring) — `core/` |
| Legal knowledge base | `data/legal_sources.json` — 30 hand-checked entries with official URLs |
| Retrieval | BM25 + intent boosts (pure Python) — `core/legal_retrieval.py` |
| Hallucination guard | Citation / case-law / other-Act / guarantee validator — `core/legal_validation.py` |
| PDFs | fpdf2 + uharfbuzz (HarfBuzz text shaping) + bundled Noto fonts (OFL) for Hindi and English |
| Optional LLM | Anthropic SDK (`claude-sonnet-5-5` by default) or any OpenAI-compatible endpoint via `requests` — off by default |

```
            ┌───────────────────────── app.py (Streamlit UI, session-only state) ─────────────────────────┐
user text → │ core/intake.py ──► core/case_builder.py ──► core/rights_analyzer.py ──► core/complaint_generator.py
            │  rules: classify,     structured JSON case,    issue rules keyed to      template drafts (EN/HI)
            │  extract, ask next    timeline, missing info,  category + facts;          facts quoted from user;
            │  relevant question    flags (limitation,       sources from KB only       citations from KB only
            │        │              commercial purpose…)            │                           │
            │        └─(optional) llm_provider: fills gaps          ├── legal_retrieval.py (BM25 + intent boosts over data/legal_sources.json)
            │                                                       ├── legal_validation.py (citation / case-law / other-Act / guarantee checker)
            │                                                       └─(optional) llm_provider: friendlier summary, kept only if validator passes
            │ core/action_planner.py ─► next steps        utils/pdf_generator.py ─► PDF (fpdf2 + HarfBuzz, merged Noto font)
            └──────────────────────────────────────────────────────────────────────────────────────────────┘
```

`core/pipeline.py` runs the same path for the app and the test harness.

## 4. Folder structure

```
nyayasetu/
├── app.py                         Streamlit entry point (7 pages)
├── config.py                      settings, paths, environment variables
├── requirements.txt               pinned, tested dependency versions
├── README.md  EVALUATION_REPORT.md
├── .gitignore  .env.example       (.env and .streamlit/secrets.toml are ignored by git)
├── .streamlit/config.toml         theme; usage statistics disabled
├── core/                          application logic
│   ├── intake.py  case_builder.py  rights_analyzer.py  complaint_generator.py
│   ├── action_planner.py  legal_retrieval.py  legal_validation.py
│   └── llm_provider.py  pipeline.py  __init__.py
├── data/legal_sources.json        verified legal knowledge base (30 entries + verification log)
├── utils/                         pdf_generator.py  language.py (EN/HI strings, ₹ formatting)  __init__.py
├── assets/fonts/                  Noto fonts + merged NyayaSetuSans font, OFL.txt licence, README.md
├── tests/
│   ├── test_cases.json            7 scenarios — ALSO read by the app for the Home-page examples
│   ├── run_tests.py  test_llm_provider.py  test_app_journey.py  __init__.py
├── docs/
│   ├── NyayaSetu_Kuku_Solution.pdf               two-page solution document
│   ├── sample_complaint_TC01_platform_complaint.pdf
│   └── build_solution_pdf.py                     rebuilds the solution PDF
└── outputs/                       saved results of tests/run_tests.py (unedited)
    ├── raw_outputs/               per-scenario conversation, case file, rights analysis, plan, drafts + test summaries
    └── generated_complaints/      32 PDFs (7 scenarios × 4 drafts + English versions of the Hindi case)
```

## 5. Installation

Requirements: **Python 3.11 or newer** (Streamlit 1.67 needs 3.11+). No API key, no paid service and no internet access are needed to run the app in its default demo mode.

**macOS / Linux**
```bash
cd nyayasetu                      # the project folder (nyayasetu-github-ready if you unzipped it)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**
```powershell
cd nyayasetu                      # the project folder (nyayasetu-github-ready if you unzipped it)
py -3.12 -m venv .venv            # any installed 3.11+ works: py -3.11 / py -3.13
.venv\Scripts\Activate.ps1        # if blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install -r requirements.txt
```

## 6. Run locally

```bash
streamlit run app.py
```

The app opens at http://localhost:8501 in **Demo mode** (shown in the sidebar). Click an example scenario on the Home page, or **Start My Legal Case** and type your own story.

## 7. Run the tests

With the virtual environment active and `pip install -r requirements.txt` done:
```bash
python tests/run_tests.py          # 7 scenarios + claimed-amount, hallucination, retrieval and privacy tests -> outputs/
python tests/test_llm_provider.py  # 22 optional-LLM checks (fake client + real SDK against a local mock; no key, no network)
python tests/test_app_journey.py   # drives the Streamlit UI end-to-end (no browser needed)
```
Expected with the full requirements installed: `RESULT: all gated checks passed for 7/7 scenarios`, `22/22 LLM-integration checks executed and passed`, `ALL APP JOURNEY CHECKS PASSED: 23/23 steps executed`. `run_tests.py` rewrites `outputs/` (only the random case IDs and PDF timestamps change).

| Script | Needs | If the package is missing |
|---|---|---|
| `run_tests.py` | `fpdf2` (+ `uharfbuzz` for correctly shaped Hindi PDFs) | Without `uharfbuzz`: runs and warns that Hindi PDFs are unshaped. Exits 1 if any gated check fails |
| `test_llm_provider.py` | 16 checks: nothing extra · 6 checks: `anthropic` | The 6 SDK checks are listed as `NOT RUN`; never counted as passed |
| `test_app_journey.py` | `streamlit` | Prints `NOT RUN` and exits with code 2 |

Which tests ran in which environment, and the results, are in `EVALUATION_REPORT.md` §2a.

## 8. Demo mode vs live LLM mode

| | Demo mode (default) | Live LLM mode (optional) |
|---|---|---|
| Needs | nothing | `NYAYASETU_LLM_PROVIDER` + an API key |
| Fact extraction | Regex + keyword rules | Rules first; the model may fill **empty** fields only; order ID / seller / platform accepted only if the string appears in the user's text |
| Dispute classification | Weighted keyword scoring | Model used only if rules return "unknown" |
| Legal analysis (issue cards) | Deterministic rules + KB | Same — never delegated to the model |
| Plain-language summary / question box | Rule-built text / retrieved passages | Model writes from retrieved KB entries and must tag every rule with `[KB:ID]`; rejected (fallback to rules) if it cites anything unverified, cites case law or another Act, or promises an outcome |
| Complaint drafts | Templates | Templates — no model-written text in legal documents, in any mode |

**How to tell them apart.** The sidebar shows *Demo mode* or *Live AI mode: provider · model*. The rights summary is labelled *Rule-based explanation* or *AI-written (model) and checked against the verified sources*. Facts filled by a model are marked "(AI)". If a provider is selected but its key is missing, or a live call fails, the app falls back to the rule-based output and says why on screen — it does not crash.

**Honest disclosure:** no live LLM API call has been made while building and testing this prototype (no API key was available). All saved outputs come from demo mode. The LLM path and its validator were exercised with a scripted fake model, and the Anthropic request was checked with the real `anthropic` SDK against a local mock server — not against the real API.

**Trying a real Anthropic key locally**
```bash
export NYAYASETU_LLM_PROVIDER=anthropic          # PowerShell: $env:NYAYASETU_LLM_PROVIDER="anthropic"
export ANTHROPIC_API_KEY=sk-ant-...              # your own key; never commit it
python -m core.llm_provider                      # sends one tiny test request; prints OK or the exact API error
streamlit run app.py
```
The provider follows Anthropic's current API guidance: no `temperature`/`top_p`/`top_k` (current models reject them), only `text` blocks are read (responses may start with thinking blocks), and `max_tokens` has a floor because it covers adaptive thinking plus text.

## 9. Environment variables (all optional)

Locally, copy `.env.example` to `.env` (git ignores `.env`). On Streamlit Community Cloud use the **Secrets** box instead (section 10). With nothing set, the app runs in demo mode.

| Variable | Purpose |
|---|---|
| `NYAYASETU_LLM_PROVIDER` | `demo` (default), `anthropic`, or `openai_compatible` |
| `ANTHROPIC_API_KEY` | Anthropic API key from the Claude Console (a Claude chat subscription does not include API access) |
| `NYAYASETU_ANTHROPIC_MODEL` | Model ID, default `claude-sonnet-5-5` (listed as current on Anthropic's models page, checked 8 Nov 2026); e.g. `claude-haiku-5-5` is cheaper |
| `NYAYASETU_ANTHROPIC_EFFORT`, `NYAYASETU_ANTHROPIC_MIN_MAX_TOKENS` | Default `low` and `4096`. Effort is sent as `output_config.effort` (empty = not sent) |
| `NYAYASETU_OPENAI_BASE_URL`, `NYAYASETU_OPENAI_API_KEY`, `NYAYASETU_OPENAI_MODEL`, `NYAYASETU_OPENAI_TEMPERATURE` | Any OpenAI-compatible endpoint (OpenAI, Groq, Together, local Ollama…). Temperature is sent only if set |
| `NYAYASETU_LLM_TIMEOUT` | Seconds per live call (default 60) |
| `NYAYASETU_REFERENCE_DATE` | Pin "today" (YYYY-MM-DD) so "three weeks ago" resolves reproducibly in demos/tests |

Keys are never hard-coded. An empty or malformed numeric setting falls back to its default instead of stopping the app.

## 10. Deploy on Streamlit Community Cloud

The app is ready for Community Cloud: `app.py` is the entry point at the repository root, `requirements.txt` is at the root, no system packages (`packages.txt`) are needed, fonts are bundled, and the app writes nothing to disk. It was tested the way Community Cloud runs it (fresh `git clone`, clean install of `requirements.txt` on Python 3.12, `streamlit run app.py`), but **an actual Community Cloud deployment has not been performed at the time of writing.**

1. Push this folder to a GitHub repository (public or private).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub and click **Create app** → **Yup, I have an app**.
3. Repository: `your-username/your-repo` · Branch: `main` · Main file path: `app.py`. Optionally choose an App URL.
4. Click **Advanced settings** → **Python version: 3.12** (the tested default).
5. **Secrets:** leave empty for demo mode (recommended for a public app). For live mode paste TOML — note the quotes; do not paste `.env.example`, which is not TOML:
   ```toml
   NYAYASETU_LLM_PROVIDER = "anthropic"
   ANTHROPIC_API_KEY = "your-key-here"
   NYAYASETU_ANTHROPIC_MODEL = "claude-sonnet-5-5"
   ```
   Root-level secrets become environment variables, which is how `config.py` reads them (verified locally with a `.streamlit/secrets.toml`). A public app in live mode spends **your** API credits for every visitor.
6. Click **Save**, then deploy. The first build takes a few minutes. The sidebar should show *Demo mode* (or *Live AI mode* if you added secrets).

## 11. How legal hallucinations are prevented

1. **Curated KB, verified against official text** (India Code, Gazette, DoCA, NCH, PIB, Lok Sabha answer), re-verified on 8 Nov 2026 (corrections are logged in the KB and in `EVALUATION_REPORT.md` §4); statuses `verified` / `verified_secondary` (shown only as notices) / `needs_verification` (never shown as law).
2. **Rules choose the law, not a model.** Each issue card references KB IDs; legal text shown is the KB's.
3. **Validator** (`core/legal_validation.py`) extracts every Section/Rule/धारा/नियम, case-law pattern (`X v. Y`, `AIR`, `SCC`, `CPJ`), other named Acts, and `[KB:…]` tags; anything not in the verified KB fails. Runs on every draft (and live on user edits) and on every AI output.
4. **Over-claiming guards in the rules**, e.g. the 30-day unfair-trade-practice clause (Section 2(47)(viii)) is *not* asserted when fewer than 30 days have passed or when the consumer asked for a replacement rather than a refund; product liability is explained as covering harm beyond the product itself.
5. **No guarantees**: outcome-promise language is detected (negation-aware) and blocked.
6. **No invented money claims**: the refund in every draft is the amount the user confirmed, or a `[MISSING]` marker; an automated check enforces this on all 32 test drafts.

## 12. Privacy

* Case data lives only in the Streamlit session (`st.session_state`); the app writes nothing to disk and keeps no conversation logs. "Clear my case" wipes it.
* Downloads are generated in memory.
* NyayaSetu never asks for Aadhaar, PAN, card numbers, bank passwords or OTPs; if typed, they are masked before storage (checksum-validated Aadhaar/card detection to avoid masking order IDs).
* Streamlit usage statistics are disabled in `.streamlit/config.toml`.
* In live-LLM mode the case facts are sent to the chosen provider; identity numbers are already masked.
* All people, sellers and platforms in the test scenarios and sample outputs are fictional.

## 13. Known limitations

* Scope: online consumer purchases only. Not banking, insurance, real estate, medical, employment, criminal fraud. Text input only (no voice); English and Hindi only.
* Extraction is rule-based in demo mode: unusual phrasing, typos, Hinglish and long stories can be misread; the user must check the case file. Platforms not in the known list are found only through the follow-up question.
* The KB is small (30 entries), last checked on 8 Nov 2026. The E-Commerce (Amendment) Rules 2026 take effect on 1 Jan 2027 and may change rule text/numbering; the RBI Ombudsman scheme and the CCPA advertising guidelines were verified only from secondary/press sources and are shown as notices.
* The refund claimed is a single total: no per-item breakdown, and for a partial refund the drafts do not say whether goods will be returned.
* Retrieval for the question box is BM25 + a few intent rules: 13/15 probe questions get the best source first, 15/15 in the top 3.
* Drafts quote the user's words; they cannot check truthfulness. The Commission draft is a preparation aid, not a filing-ready pleading (affidavit, addresses, format must be completed on e-Jagriti).
* No live LLM call has been made; run `python -m core.llm_provider` with a key to test one.
* Hindi wording has not been reviewed by a native speaker or a lawyer, and nothing has been reviewed by a practising advocate.

## 14. Legal disclaimer

NyayaSetu provides general legal information and draft documents, not legal advice. It does not create a lawyer-client relationship, does not file anything on your behalf, and cannot guarantee a refund, compensation or any outcome. Laws and procedures change; check every provision against the official source linked in the app, and consult a qualified advocate for important decisions — especially for commercial purchases, large amounts, injuries, fraud, or when a time limit may have passed.

## 15. Licences

Fonts in `assets/fonts/` are Noto fonts (and a merged derivative) under the SIL Open Font License 1.1 — see `assets/fonts/OFL.txt`. No licence has yet been chosen for the NyayaSetu code itself.
