"""Legal output validation — the hallucination guard.

Every piece of legal text the app shows or puts into a document can be passed
through `validate_text`. It extracts every statutory citation ("Section 2(47)",
"Rule 6(3)", "धारा 69"), every case-law-looking citation ("X v. Y", "AIR 2019 SC",
"(2020) 5 SCC 1"), every named Act, and every [KB:ID] tag, and checks them
against the verified knowledge base. It also flags outcome guarantees and any
request for sensitive identifiers.

For LLM output the rule is strict: if anything fails, the AI text is discarded
and the deterministic, source-quoted explanation is shown instead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.legal_retrieval import LegalKnowledgeBase, get_kb, normalise_citation

SECTION_RE = re.compile(r"(?:\bsections?|\bsec\.|धारा(?:ओं)?)\s*((?:\d+[A-Z]?(?:\s*\(\s*[0-9a-zA-Z]+\s*\))*)(?:\s*(?:,|and|और|&)\s*\d+[A-Z]?(?:\s*\(\s*[0-9a-zA-Z]+\s*\))*)*)", re.I)
RULE_RE = re.compile(r"(?:\brules?|नियम)\s*((?:\d+(?:\s*\(\s*[0-9a-zA-Z]+\s*\))*)(?:\s*(?:,|and|और|&)\s*\d+(?:\s*\(\s*[0-9a-zA-Z]+\s*\))*)*)", re.I)
SINGLE_PROVISION_RE = re.compile(r"\d+[A-Z]?(?:\s*\(\s*[0-9a-zA-Z]+\s*\))*")
CASE_LAW_RES = [
    re.compile(r"\b[A-Z][\w.&']+(?:\s+[A-Z][\w.&']+){0,5}\s+(?:v\.|vs\.?|versus)\s+[A-Z][\w.&']+(?:\s+[A-Z][\w.&']+){0,5}"),
    re.compile(r"\bAIR\s+\d{4}\b"),
    re.compile(r"\(\d{4}\)\s*\d+\s*SCC\b"),
    re.compile(r"\b\d{4}\s+SCC\s+OnLine\b", re.I),
    re.compile(r"\b(?:I|II|III|IV)\s*\(\d{4}\)\s*CPJ\b"),
    re.compile(r"\bCPJ\s+\d+"),
]
ACT_RE = re.compile(r"\b((?:[A-Z][A-Za-z]+\s+){1,6}Act),?\s*(\d{4})")
KB_TAG_RE = re.compile(r"\[KB:([A-Z0-9_]+)\]")
GUARANTEE_RES = [
    re.compile(r"\b(guarantee[sd]?|guaranteed)\b(?!\s+card)", re.I),
    re.compile(r"\b(will|shall)\s+(definitely|surely|certainly)\b", re.I),
    re.compile(r"\b(definitely|surely|certainly)\s+(get|win|receive|succeed)", re.I),
    re.compile(r"\b100\s?%\s*(sure|certain|chance|success)", re.I),
    re.compile(r"\byou (will|are going to) win\b", re.I),
    re.compile(r"निश्चित\s*(रूप से)?\s*(मिलेगा|मिलेगी|जीत)|गारंटी(?!\s*कार्ड)|ज़रूर मिलेगा|पक्का मिलेगा"),
]
SENSITIVE_REQUEST_RE = re.compile(r"(share|send|provide|enter|give)\s+(your\s+)?(aadhaar|pan|otp|cvv|password|upi pin|card number)", re.I)
ALLOWED_ACTS = {"consumer protection act"}


@dataclass
class Problem:
    kind: str
    text: str
    detail: str


@dataclass
class ValidationReport:
    ok: bool
    citations_found: list[str] = field(default_factory=list)
    citations_valid: list[str] = field(default_factory=list)
    kb_tags: list[str] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return f"All {len(self.citations_found)} legal reference(s) match verified sources; no outcome guarantees found."
        return "; ".join(f"{p.kind}: {p.text} — {p.detail}" for p in self.problems)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "citations_found": self.citations_found, "citations_valid": self.citations_valid,
                "kb_tags": self.kb_tags, "problems": [p.__dict__ for p in self.problems]}


NEGATION_BEFORE_RE = re.compile(r"\b(no|not|never|cannot|can't|cannot be|without|nothing)\b[^.!?।]{0,30}$", re.I)
NEGATION_AFTER_RE = re.compile(r"^[^.!?।]{0,12}(नहीं|न\s)")


def _negated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 40):start]
    after = text[end:end + 20]
    return bool(NEGATION_BEFORE_RE.search(before) or NEGATION_AFTER_RE.search(after))


def _expand(prefix: str, group: str) -> list[str]:
    return [f"{prefix} {m.group(0)}" for m in SINGLE_PROVISION_RE.finditer(group)]


def extract_citations(text: str) -> dict[str, list[str]]:
    sections, rules = [], []
    for m in SECTION_RE.finditer(text):
        sections.extend(_expand("Section", m.group(1)))
    for m in RULE_RE.finditer(text):
        rules.extend(_expand("Rule", m.group(1)))
    cases = []
    for rx in CASE_LAW_RES:
        cases.extend(m.group(0) for m in rx.finditer(text))
    acts = [f"{m.group(1)}, {m.group(2)}" for m in ACT_RE.finditer(text)]
    return {"sections": sections, "rules": rules, "cases": cases, "acts": acts, "kb_tags": KB_TAG_RE.findall(text)}


def _is_allowed(cite: str, allowed: set[str]) -> bool:
    n = normalise_citation(cite)
    if n in allowed:
        return True
    # citing a parent provision of a verified sub-clause is acceptable ("Section 2(47)" when 2(47)(viii) is verified)
    return any(a.startswith(n + "(") for a in allowed)


def validate_text(text: str, kb: LegalKnowledgeBase | None = None, allowed_ids: set[str] | None = None,
                  require_kb_tags: bool = False) -> ValidationReport:
    kb = kb or get_kb()
    allowed_by_scope = kb.allowed_citations(ids=allowed_ids)
    allowed_sections = allowed_by_scope.get("CPA", set())
    allowed_rules = set().union(*[v for k, v in allowed_by_scope.items() if k != "CPA"]) if allowed_by_scope else set()
    found = extract_citations(text)
    rep = ValidationReport(ok=True)
    for s in found["sections"]:
        rep.citations_found.append(s)
        if _is_allowed(s, allowed_sections):
            rep.citations_valid.append(s)
        else:
            rep.problems.append(Problem("unverified_citation", s, "Not in the verified knowledge base"
                                        + (" for the retrieved sources" if allowed_ids is not None else "")))
    for r in found["rules"]:
        rep.citations_found.append(r)
        if _is_allowed(r, allowed_rules):
            rep.citations_valid.append(r)
        else:
            rep.problems.append(Problem("unverified_citation", r, "Rule not in the verified knowledge base"))
    for c in found["cases"]:
        rep.problems.append(Problem("case_law", c, "NyayaSetu's knowledge base contains no verified case law; case citations are not allowed"))
    for a in found["acts"]:
        name = re.sub(r"^(the|of)\s+", "", a.split(",")[0].strip(), flags=re.I).lower()
        if not any(name.endswith(x) for x in ALLOWED_ACTS):
            rep.problems.append(Problem("unverified_statute", a, "This Act is outside the verified knowledge base"))
    for tag in found["kb_tags"]:
        rep.kb_tags.append(tag)
        entry = kb.get(tag)
        if entry is None:
            rep.problems.append(Problem("unknown_source_tag", f"[KB:{tag}]", "No such source in the knowledge base"))
        elif allowed_ids is not None and tag not in allowed_ids:
            rep.problems.append(Problem("unretrieved_source_tag", f"[KB:{tag}]", "Source was not among the retrieved evidence"))
    if require_kb_tags and not found["kb_tags"]:
        rep.problems.append(Problem("no_grounding", "(whole text)", "No [KB:ID] source tags — answer is not grounded"))
    for rx in GUARANTEE_RES:
        for m in rx.finditer(text):
            if _negated(text, m.start(), m.end()):
                continue  # e.g. "No outcome is guaranteed", "a target, not a guarantee", "गारंटी नहीं"
            rep.problems.append(Problem("outcome_guarantee", m.group(0), "NyayaSetu must not promise outcomes"))
    for m in SENSITIVE_REQUEST_RE.finditer(text):
        rep.problems.append(Problem("sensitive_data_request", m.group(0), "Must never ask for sensitive identifiers"))
    rep.ok = not rep.problems
    return rep


def validate_llm_explanation(text: str, retrieved_ids: set[str], kb: LegalKnowledgeBase | None = None) -> ValidationReport:
    """Strict check for model-written legal explanations."""
    kb = kb or get_kb()
    verified = {i for i in retrieved_ids if kb.is_verified(i)}
    return validate_text(text, kb=kb, allowed_ids=verified, require_kb_tags=True)
