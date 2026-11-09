"""Source-grounded legal knowledge module (lightweight RAG retriever).

The knowledge base (data/legal_sources.json) is a small, hand-verified set of
provisions with their official URL, issuing authority, excerpt and verification
date. Retrieval is a BM25 keyword ranker with a small synonym map — enough for a
30-entry corpus and fully deterministic. A vector index can replace `search()`
later without touching the rest of the app.

Only entries whose verification_status is "verified" may be presented as
established law. "verified_secondary" entries are shown as dated notices with a
"verify before relying" label.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from config import LEGAL_SOURCES_PATH

SYNONYMS = {
    "money": ["refund"], "back": ["refund"], "paisa": ["refund"], "wapas": ["refund"], "reimburse": ["refund"],
    "broken": ["damaged", "defect"], "cracked": ["damaged", "defect"], "faulty": ["defect"], "kharab": ["defect"],
    "stopped": ["defect"], "working": ["defect"], "delivered": ["delivery"], "received": ["delivery"],
    "court": ["commission", "file"], "forum": ["commission"], "case": ["complaint", "file"], "sue": ["complaint", "file"],
    "lawyer": ["file", "advocate"], "deadline": ["limitation"], "late": ["limitation", "delay"], "old": ["limitation"],
    "fees": ["fee"], "cost": ["fee"], "charge": ["fee", "charged"], "ad": ["advertisement"], "ads": ["advertisement"],
    "advertised": ["advertisement"], "listing": ["advertisement", "description"], "fake": ["spurious", "misleading"],
    "helpline": ["nch"], "1915": ["nch"], "ombudsman": ["rbi"], "upi": ["rbi", "payment"], "bank": ["rbi", "payment"],
    "रिफंड": ["refund"], "पैसे": ["refund"], "वापस": ["refund"], "खराब": ["defect"], "टूटा": ["damaged"],
    "शिकायत": ["complaint"], "अदालत": ["commission"], "आयोग": ["commission"], "वकील": ["advocate", "file"],
    "विज्ञापन": ["advertisement"], "शुल्क": ["fee"], "फीस": ["fee"], "समय": ["limitation"], "हेल्पलाइन": ["nch"],
}
# Small intent layer for common question shapes that bag-of-words ranking confuses
# (e.g. "how long do I have to file" = time limit, "how long will it take" = disposal time).
INTENT_BOOSTS = [
    (re.compile(r"how long (do|have|can) i|time limit|deadline|too late|last date|within how|कब तक|समय सीमा", re.I), "CPA_69", 2.0),
    (re.compile(r"how long (will|does|would) (it|the case|the complaint|this)|how much time .* (take|decide)|कितना समय लगेगा", re.I), "CPA_38_7", 2.0),
    (re.compile(r"\bfees?\b|cost to file|pay to file|शुल्क|फीस", re.I), "FEE_RULE_7", 2.0),
    (re.compile(r"which (court|commission|forum)|where (do|can|should) i (file|complain|go)|कहाँ (दर्ज|शिकायत)", re.I), "CPA_34", 2.0),
]

STOP = set("a an the of to and or in on for is are was were be been it this that with by as at from my i me you your can do does "
           "what how when where which who will would should could have has had not no".split())


@dataclass
class Retrieved:
    entry: dict
    score: float

    @property
    def id(self) -> str:
        return self.entry["id"]


def _tokens(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+|[ऀ-ॿ]+", (text or "").lower())
    out = []
    for t in toks:
        if t in STOP:
            continue
        out.append(t)
        out.extend(SYNONYMS.get(t, []))
    return out


class LegalKnowledgeBase:
    def __init__(self, path: Path | str = LEGAL_SOURCES_PATH):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.meta = {k: v for k, v in data.items() if k != "sources"}
        self.entries: list[dict] = data["sources"]
        self.by_id = {e["id"]: e for e in self.entries}
        self._docs = [self._doc_tokens(e) for e in self.entries]
        self._df = Counter()
        for d in self._docs:
            self._df.update(set(d))
        self._avgdl = sum(len(d) for d in self._docs) / max(1, len(self._docs))
        self._check_integrity()

    @staticmethod
    def _doc_tokens(e: dict) -> list[str]:
        parts = [e.get("title", ""), e.get("short_cite", ""), " ".join(e.get("keywords", [])) * 2,
                 e.get("plain_language", {}).get("en", ""), e.get("plain_language", {}).get("hi", ""),
                 e.get("excerpt", ""), " ".join(e.get("applies_to", []))]
        return _tokens(" ".join(parts))

    def _check_integrity(self):
        required = {"id", "short_cite", "url", "issuing_authority", "verification_status", "verified_on", "excerpt", "plain_language"}
        for e in self.entries:
            missing = required - set(e)
            if missing:
                raise ValueError(f"Knowledge-base entry {e.get('id')} is missing {missing}")
            if e["verification_status"] not in ("verified", "verified_secondary", "needs_verification"):
                raise ValueError(f"Bad verification_status in {e['id']}")

    # ----------------------------------------------------------- access
    def get(self, source_id: str) -> dict | None:
        return self.by_id.get(source_id)

    def is_verified(self, source_id: str) -> bool:
        e = self.get(source_id)
        return bool(e and e["verification_status"] == "verified")

    def verified_ids(self) -> set[str]:
        return {e["id"] for e in self.entries if e["verification_status"] == "verified"}

    def for_category(self, category: str) -> list[dict]:
        return [e for e in self.entries if category in e.get("applies_to", []) or "all" in e.get("applies_to", [])]

    # ----------------------------------------------------------- search
    def search(self, query: str, k: int = 5, categories: list[str] | None = None,
               include_unverified: bool = False) -> list[Retrieved]:
        q = _tokens(query)
        if categories:
            q += [c for c in categories]
        n = len(self.entries)
        results = []
        for e, doc in zip(self.entries, self._docs):
            if not include_unverified and e["verification_status"] == "needs_verification":
                continue
            tf = Counter(doc)
            score = 0.0
            for term in set(q):
                if term not in tf:
                    continue
                idf = math.log(1 + (n - self._df[term] + 0.5) / (self._df[term] + 0.5))
                f = tf[term]
                score += idf * (f * 2.2) / (f + 1.2 * (0.25 + 0.75 * len(doc) / self._avgdl))
            if categories and any(c in e.get("applies_to", []) for c in categories):
                score *= 1.3
            for rx, sid, mult in INTENT_BOOSTS:
                if e["id"] == sid and rx.search(query):
                    score = (score + 1.0) * mult
            if score > 0:
                results.append(Retrieved(e, round(score, 3)))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    # ----------------------------------------------------------- citations
    def allowed_citations(self, ids: set[str] | None = None, statuses=("verified",)) -> dict[str, set[str]]:
        """Normalised citation strings allowed for each instrument scope."""
        allowed: dict[str, set[str]] = {}
        for e in self.entries:
            if e["verification_status"] not in statuses:
                continue
            if ids is not None and e["id"] not in ids:
                continue
            scope = e.get("citation_scope") or ("CPA" if e["id"].startswith("CPA") else "OTHER")
            for c in e.get("citations", []):
                allowed.setdefault(scope, set()).add(normalise_citation(c))
        return allowed


def normalise_citation(c: str) -> str:
    c = c.strip().lower()
    c = re.sub(r"^(sec\.?|s\.)\s*", "section ", c)
    c = re.sub(r"^(r\.)\s*", "rule ", c)
    c = re.sub(r"धारा\s*", "section ", c)
    c = re.sub(r"नियम\s*", "rule ", c)
    c = re.sub(r"\s+", "", c)
    return c


@lru_cache(maxsize=1)
def get_kb() -> LegalKnowledgeBase:
    return LegalKnowledgeBase()
