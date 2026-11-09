"""Glue: run the whole workflow (case -> rights -> documents -> plan) for a case.

Used by both the Streamlit app and the test harness so they exercise exactly
the same code path.
"""
from __future__ import annotations

from datetime import date

from core.action_planner import build_action_plan
from core.case_builder import build_case, recompute
from core.complaint_generator import ComplaintGenerator
from core.llm_provider import DemoProvider
from core.rights_analyzer import RightsAnalyzer


def mode_label(llm) -> str:
    if llm is None or not getattr(llm, "is_live", False):
        return "demo (deterministic rules)"
    return f"live LLM ({llm.label()})"


def analyse_case(case: dict, today: date, lang: str | None = None, llm=None) -> dict:
    lang = lang or case.get("language", "en")
    llm = llm or DemoProvider()
    case = recompute(case, today)
    rights = RightsAnalyzer(llm=llm).analyse(case, lang, today)
    gen = ComplaintGenerator(case, rights, today)
    return {"case": case, "rights": rights, "documents": gen.generate_all(lang), "plan": build_action_plan(case, lang)}


def run_from_intake(intake_state: dict, today: date, llm=None, lang: str | None = None) -> dict:
    llm = llm or DemoProvider()
    case = build_case(intake_state, today, mode_label(llm))
    return analyse_case(case, today, lang, llm)
