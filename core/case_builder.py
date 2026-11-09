"""Module 2 — Build My Case.

Converts the intake slots into a structured, editable case file (plain JSON),
computes the timeline, financial loss, missing information and legally
relevant flags (limitation risk, possible commercial purpose, harm beyond the
product, payment-side issue). No fact is invented: anything not supplied by the
user is left empty and listed under missing information.
"""
from __future__ import annotations

import copy
import json
import re
import secrets
from datetime import date
from typing import Any

from core.intake import CATEGORIES, EVIDENCE_TYPES, RELEVANT_EVIDENCE, RESOLUTIONS
from utils.language import format_date, format_inr

CASE_SCHEMA_VERSION = "1.0"

EXPECTED_BY_CATEGORY = {
    "damaged_on_delivery": {"en": "To receive the {product} in good, undamaged condition, as described on the platform.",
                            "hi": "{product} अच्छी, बिना क्षति की स्थिति में मिले, जैसा प्लेटफ़ॉर्म पर बताया गया था।"},
    "defective_product": {"en": "A {product} that works properly and is free from defects, as described and as covered by any warranty.",
                          "hi": "ठीक से काम करने वाला, दोषरहित {product}, जैसा बताया गया था और जैसा वारंटी में शामिल है।"},
    "non_delivery": {"en": "Delivery of the {product} that was ordered and paid for.",
                     "hi": "ऑर्डर किए और भुगतान किए गए {product} की डिलीवरी।"},
    "misleading_description": {"en": "A {product} with the features and characteristics stated in the listing / advertisement.",
                               "hi": "लिस्टिंग / विज्ञापन में बताई गई विशेषताओं वाला {product}।"},
    "incorrect_charge": {"en": "To be charged only the correct price shown at checkout for the {product}.",
                         "hi": "{product} के लिए चेकआउट पर दिखाई गई सही कीमत ही ली जाए।"},
    "refund_not_received": {"en": "To receive the refund that was due for the {product}.",
                            "hi": "{product} के लिए बनने वाला रिफंड प्राप्त होना।"},
    "unknown": {"en": "That the goods or service would be as promised.", "hi": "सामान या सेवा वादे के अनुसार हो।"},
}

MISSING_LABELS = {
    "consumer.name": ("Your name", "आपका नाम", "Needed on every complaint and on the Consumer Commission filing."),
    "consumer.city": ("Your city / district", "आपका शहर / ज़िला", "Decides which District Commission you can approach (you may file where you live or work)."),
    "transaction.product": ("Product", "उत्पाद", "Identifies what the dispute is about."),
    "transaction.amount_paid": ("Amount paid", "चुकाई गई राशि", "Sets the refund claimed, the Commission's value limit and the filing fee."),
    "transaction.order_id": ("Order ID", "ऑर्डर आईडी", "The platform and seller trace your order with it."),
    "transaction.purchase_date": ("Order / purchase date", "ऑर्डर / खरीद की तिथि", "Needed for the timeline and the 2-year time limit."),
    "transaction.delivery_date": ("Delivery date", "डिलीवरी तिथि", "Shows when the problem arose and supports return-window arguments."),
    "parties.platform": ("Platform / website / app", "प्लेटफ़ॉर्म / वेबसाइट / ऐप", "The platform must handle grievances under the E-Commerce Rules."),
    "parties.seller": ("Seller name", "विक्रेता का नाम", "The seller is usually a necessary opposite party; it is on the invoice or order page."),
    "parties.seller_address": ("Seller / platform address", "विक्रेता / प्लेटफ़ॉर्म का पता", "Required on a Consumer Commission complaint; marketplaces must display seller addresses."),
    "steps_taken": ("Complaint already made to seller/platform", "विक्रेता/प्लेटफ़ॉर्म को की गई शिकायत", "A written complaint creates a record and gives the other side a chance to fix it."),
    "complaint_ref": ("Complaint / ticket number", "शिकायत / टिकट संख्या", "Proves you complained and lets the platform track it."),
    "evidence": ("Evidence", "सबूत", "Your claims must be supported by documents or photos."),
    "desired_resolution": ("Desired resolution", "वांछित समाधान", "The relief you ask for must be stated clearly."),
    "transaction.charged_amount": ("Amount actually charged", "वास्तव में कटी राशि", "Needed to show the excess charge."),
    "claim.amount": ("Amount you are claiming", "आप कितनी राशि माँग रहे हैं",
                     "NyayaSetu does not assume you want the full price back. State the exact refund you are asking for "
                     "(it can be less than the price, e.g. if only part of the order was faulty)."),
}


def _slot(slots: dict, key: str, default=None):
    return slots.get(key, {}).get("value", default)


def _approx(slots: dict, key: str):
    return slots.get(key, {}).get("approx") or False


def new_case_id(today: date) -> str:
    return f"NS-{today.strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"


def build_case(intake_state: dict, today: date, mode_label: str = "demo") -> dict:
    slots = intake_state.get("slots", {})
    lang = intake_state.get("lang", "en")
    category = intake_state.get("category") or "unknown"
    product = _slot(slots, "product") or ""
    case: dict[str, Any] = {
        "schema_version": CASE_SCHEMA_VERSION,
        "case_id": new_case_id(today),
        "created_on": today.isoformat(),
        "reference_date": today.isoformat(),
        "language": lang,
        "generation_mode": mode_label,
        "dispute": {
            "category": category,
            "category_label": CATEGORIES.get(category, CATEGORIES["unknown"])["en"],
            "secondary": list(intake_state.get("secondary", [])),
            "low_confidence": bool(intake_state.get("low_confidence_category")) or category == "unknown",
        },
        "consumer": {
            "name": _slot(slots, "consumer_name", ""),
            "city": _slot(slots, "consumer_city", ""),
            "purpose": _slot(slots, "purpose", ""),
            "purpose_note": _slot(slots, "purpose_note", ""),
        },
        "parties": {
            "platform": _slot(slots, "platform", ""),
            "seller": _slot(slots, "seller", ""),
            "seller_address": "",
        },
        "transaction": {
            "product": product,
            "amount_paid": _slot(slots, "amount"),
            "charged_amount": _slot(slots, "charged_amount"),
            "order_id": _slot(slots, "order_id", ""),
            "purchase_date": _slot(slots, "purchase_date", ""),
            "purchase_date_approx": _approx(slots, "purchase_date"),
            "delivery_date": _slot(slots, "delivery_date", ""),
            "delivery_date_approx": _approx(slots, "delivery_date"),
            "payment_mode": _slot(slots, "payment_mode", ""),
        },
        "issue_details": _slot(slots, "issue_details", "") or "",
        "what_happened": "",
        "what_was_expected": "",
        "steps_taken": list(_slot(slots, "steps_taken", []) or []),
        "complaint_date": _slot(slots, "complaint_date", ""),
        "complaint_date_approx": _approx(slots, "complaint_date"),
        "issue_date": _slot(slots, "issue_date", ""),
        "refund_approved_date": _slot(slots, "refund_approved_date", ""),
        "complaint_ref": _slot(slots, "complaint_ref", ""),
        "seller_response": _slot(slots, "seller_response", "") or "",
        "evidence": list(_slot(slots, "evidence", []) or []),
        "desired_resolution": list(_slot(slots, "desired_resolution", []) or []),
        "resolution_note": _slot(slots, "resolution_note", "") or "",
        "claim": {
            # the refund amount the consumer asks for; only ever set from the consumer's own answer or correction
            "amount": _slot(slots, "claim_amount"),
            "basis": slots.get("claim_amount", {}).get("basis") or ("full" if _slot(slots, "claim_basis") == "full" else ""),
            "confirmed": "claim_amount" in slots or _slot(slots, "claim_basis") == "full",
            "source": (slots.get("claim_amount") or slots.get("claim_basis") or {}).get("source", ""),
            "note": _slot(slots, "claim_note", "") or "",
        },
        "harm_beyond_product": bool(_slot(slots, "harm_beyond_product", False)),
        "repeated_contact": bool(_slot(slots, "repeated_contact", False)),
        "no_complaint_yet": "complaint_history" in intake_state.get("answered_none", []),
        "narrative": intake_state.get("narrative", ""),
        "provenance": {k: v.get("source") for k, v in slots.items()},
        "timeline": [],
        "missing_info": [],
        "flags": {},
    }
    case["what_happened"] = case["issue_details"] or case["narrative"]
    tmpl = EXPECTED_BY_CATEGORY.get(category, EXPECTED_BY_CATEGORY["unknown"])[lang]
    case["what_was_expected"] = tmpl.format(product=product or ("उत्पाद" if lang == "hi" else "product"))
    if case["complaint_ref"] and "complaint_reference" not in case["evidence"]:
        case["evidence"].append("complaint_reference")  # the user holds a reference number for their complaint
    return recompute(case, today)


def build_timeline(case: dict, lang: str = "en") -> list[dict]:
    t = case["transaction"]
    events = []

    def add(iso, approx, en, hi, source="user statement"):
        events.append({"date": iso or "", "approx": approx or False, "event": hi if lang == "hi" else en, "source": source})

    product = t.get("product") or ("the product" if lang == "en" else "उत्पाद")
    platform = case["parties"].get("platform") or ""
    amount = format_inr(t.get("amount_paid")) if t.get("amount_paid") else ""
    if t.get("purchase_date") or t.get("order_id") or amount:
        add(t.get("purchase_date"), t.get("purchase_date_approx"),
            f"Order placed for {product}" + (f" on {platform}" if platform else "") + (f" ({amount})" if amount else "") +
            (f", Order ID {t['order_id']}" if t.get("order_id") else ""),
            f"{product} का ऑर्डर दिया" + (f" ({platform})" if platform else "") + (f", राशि {amount}" if amount else "") +
            (f", ऑर्डर आईडी {t['order_id']}" if t.get("order_id") else ""))
    if case["dispute"]["category"] == "incorrect_charge" and t.get("charged_amount"):
        add(t.get("purchase_date"), t.get("purchase_date_approx"),
            f"Charged {format_inr(t['charged_amount'])}" + (f" via {t['payment_mode']}" if t.get("payment_mode") else ""),
            f"{format_inr(t['charged_amount'])} की कटौती" + (f" ({t['payment_mode']})" if t.get("payment_mode") else ""))
    if t.get("delivery_date"):
        if case["dispute"]["category"] == "non_delivery":
            add(t["delivery_date"], t.get("delivery_date_approx"), "Platform shows the order as “delivered” (consumer says it was not received)",
                "प्लेटफ़ॉर्म पर ऑर्डर “डिलीवर” दिखाया गया (उपभोक्ता के अनुसार प्राप्त नहीं हुआ)")
        else:
            add(t["delivery_date"], t.get("delivery_date_approx"), "Product delivered", "उत्पाद डिलीवर हुआ")
    if case.get("issue_date"):
        add(case["issue_date"], False, "Problem noticed", "समस्या का पता चला")
    if case.get("refund_approved_date"):
        add(case["refund_approved_date"], False, "Refund approved / order cancelled (as stated by consumer)", "रिफंड स्वीकृत / ऑर्डर रद्द (उपभोक्ता के अनुसार)")
    if case.get("steps_taken"):
        ref = f" (ref. {case['complaint_ref']})" if case.get("complaint_ref") else ""
        add(case.get("complaint_date"), case.get("complaint_date_approx"),
            "Consumer complained / requested resolution" + ref, "उपभोक्ता ने शिकायत / समाधान का अनुरोध किया" + ref)
    if case.get("seller_response"):
        add("", False, "Response from seller/platform: " + case["seller_response"][:200],
            "विक्रेता/प्लेटफ़ॉर्म का उत्तर: " + case["seller_response"][:200])
    dated = sorted([e for e in events if e["date"]], key=lambda e: e["date"])
    undated = [e for e in events if not e["date"]]
    return dated + undated


def compute_missing(case: dict) -> list[dict]:
    missing = []
    cat = case["dispute"]["category"]

    def need(path: str, value):
        if value in (None, "", [], 0):
            en, hi, why = MISSING_LABELS[path]
            missing.append({"field": path, "label_en": en, "label_hi": hi, "why": why})

    need("consumer.name", case["consumer"].get("name"))
    need("consumer.city", case["consumer"].get("city"))
    need("transaction.product", case["transaction"].get("product"))
    need("transaction.amount_paid", case["transaction"].get("amount_paid"))
    if cat == "incorrect_charge":
        need("transaction.charged_amount", case["transaction"].get("charged_amount"))
    need("parties.platform", case["parties"].get("platform"))
    need("parties.seller", case["parties"].get("seller"))
    need("transaction.order_id", case["transaction"].get("order_id"))
    need("transaction.purchase_date", case["transaction"].get("purchase_date"))
    if cat in ("damaged_on_delivery", "defective_product", "non_delivery"):
        need("transaction.delivery_date", case["transaction"].get("delivery_date"))
    if not case.get("no_complaint_yet"):
        need("steps_taken", case.get("steps_taken"))
        if case.get("steps_taken"):
            need("complaint_ref", case.get("complaint_ref"))
    need("evidence", case.get("evidence"))
    need("desired_resolution", case.get("desired_resolution"))
    claim = case.get("claim") or {}
    if claim.get("refund_requested") and not claim.get("confirmed"):
        need("claim.amount", None)
    need("parties.seller_address", case["parties"].get("seller_address"))
    return missing


def compute_flags(case: dict, today: date) -> dict:
    t = case["transaction"]
    flags: dict[str, Any] = {}
    purpose = case["consumer"].get("purpose") or ""
    flags["possible_commercial_purpose"] = purpose == "resale_or_commercial"
    flags["livelihood_purpose"] = purpose == "livelihood"
    flags["harm_beyond_product"] = bool(case.get("harm_beyond_product"))
    flags["payment_side_issue"] = case["dispute"]["category"] == "incorrect_charge" and (t.get("payment_mode") in ("UPI", "Card", "Wallet"))
    flags["no_complaint_yet"] = bool(case.get("no_complaint_yet")) or not case.get("steps_taken")
    flags["repeated_contact"] = bool(case.get("repeated_contact"))
    # days since the complaint / refund request (used to avoid over-claiming the 30-day UTP clause)
    ref_iso = case.get("complaint_date") or ""
    flags["days_since_complaint"] = (today - date.fromisoformat(ref_iso)).days if ref_iso else None
    flags["refused_explicitly"] = bool(re.search(r"refus|denied|reject|won'?t|will not|not possible|इनकार|मना",
                                            (case.get("seller_response") or "") + " " + (case.get("narrative") or ""), re.I))
    # limitation (Section 69): 2 years from the cause of action — approximated from the earliest relevant date
    candidates = [d for d in (t.get("delivery_date"), case.get("issue_date"), t.get("purchase_date")) if d]
    earliest = min(candidates) if candidates else None
    if earliest:
        age_days = (today - date.fromisoformat(earliest)).days
        flags["days_since_earliest_event"] = age_days
        flags["limitation_risk"] = age_days > 700  # close to or beyond 2 years — needs a lawyer's view
        flags["limitation_expired_likely"] = age_days > 730
    else:
        flags["days_since_earliest_event"] = None
        flags["limitation_risk"] = False
        flags["limitation_expired_likely"] = False
    amount = t.get("amount_paid") or 0
    flags["value_band"] = ("district" if amount <= 50_00_000 else "state" if amount <= 2_00_00_000 else "national") if amount else "unknown"
    flags["fee_nil"] = bool(amount) and amount <= 5_00_000
    rel = RELEVANT_EVIDENCE.get(case["dispute"]["category"], RELEVANT_EVIDENCE["unknown"])
    flags["evidence_have"] = [e for e in rel if e in case.get("evidence", [])]
    flags["evidence_missing"] = [e for e in rel if e not in case.get("evidence", [])]
    flags["low_confidence_category"] = bool(case["dispute"].get("low_confidence"))
    return flags


def excess_charge(case: dict) -> float | None:
    t = case["transaction"]
    if case["dispute"]["category"] == "incorrect_charge" and t.get("charged_amount") and t.get("amount_paid"):
        ex = float(t["charged_amount"]) - float(t["amount_paid"])
        return ex if ex > 0 else None
    return None


def resolve_claim(case: dict) -> dict:
    """Keep the claimed amount consistent with the facts without ever inventing it.

    'full' and 'excess' follow the amounts the user gave (so correcting the price updates the claim);
    any other confirmed amount is kept exactly as the user stated it.
    """
    c = case.setdefault("claim", {})
    for k, v in (("amount", None), ("basis", ""), ("confirmed", False), ("source", ""), ("note", "")):
        c.setdefault(k, v)
    t = case["transaction"]
    paid = t.get("amount_paid")
    if c["confirmed"] and c["basis"] == "full":
        c["amount"] = float(paid) if paid else None
    elif c["confirmed"] and c["basis"] == "excess":
        c["amount"] = excess_charge(case) or c["amount"]
    if not c["confirmed"]:
        c["amount"] = None
    amt = c["amount"]
    c["refund_requested"] = bool({"refund", "delivery"} & set(case.get("desired_resolution") or []))
    c["is_partial"] = bool(amt and paid and amt < float(paid) - 0.5 and c["basis"] != "excess")
    c["exceeds_paid"] = bool(amt and paid and amt > float(paid) + 0.5 and c["basis"] != "excess")
    return c


def financial_loss(case: dict) -> dict:
    t = case["transaction"]
    claim = case.get("claim") or {}
    if claim.get("confirmed") and claim.get("amount"):
        return {"amount": float(claim["amount"]), "basis_en": "Refund amount you are claiming (confirmed by you)",
                "basis_hi": "आपके द्वारा माँगी गई रिफंड राशि (आपने पुष्टि की)"}
    ex = excess_charge(case)
    if ex:
        return {"amount": ex, "basis_en": "Amount charged minus the correct price — not yet confirmed as your claim",
                "basis_hi": "कटी राशि में से सही कीमत घटाकर — अभी आपके दावे के रूप में पुष्टि नहीं"}
    if t.get("amount_paid"):
        return {"amount": float(t["amount_paid"]), "basis_en": "Price paid — the amount you are claiming is not confirmed yet",
                "basis_hi": "चुकाई गई कीमत — माँगी गई राशि की अभी पुष्टि नहीं"}
    return {"amount": None, "basis_en": "Not known yet", "basis_hi": "अभी ज्ञात नहीं"}


def recompute(case: dict, today: date) -> dict:
    case = copy.deepcopy(case)
    lang = case.get("language", "en")
    case["dispute"]["category_label"] = CATEGORIES.get(case["dispute"]["category"], CATEGORIES["unknown"])["en"]
    resolve_claim(case)
    if not case.get("timeline_user_edited"):
        case["timeline"] = build_timeline(case, lang)
    case["missing_info"] = compute_missing(case)
    case["flags"] = compute_flags(case, today)
    case["financial_loss"] = financial_loss(case)
    return case


def case_to_json(case: dict) -> str:
    return json.dumps(case, ensure_ascii=False, indent=2, default=str)


def case_from_json(text: str, today: date) -> dict:
    data = json.loads(text)
    required = {"dispute", "consumer", "parties", "transaction"}
    if not required.issubset(data):
        raise ValueError("This file is not a NyayaSetu case file.")
    return recompute(data, today)


def describe_evidence(keys: list[str], lang: str = "en") -> list[str]:
    return [EVIDENCE_TYPES[k][lang] if k in EVIDENCE_TYPES else k for k in keys]


def describe_resolution(keys: list[str], lang: str = "en") -> list[str]:
    return [RESOLUTIONS[k][lang] if k in RESOLUTIONS else k for k in keys]


def human_date(iso: str, approx, lang: str) -> str:
    if not iso:
        return ""
    s = format_date(iso, lang)
    if approx == "month":  # only the month and year were given
        s = s.split(" ", 1)[1]
    if approx:
        s += " (अनुमानित)" if lang == "hi" else " (approx.)"
    return s
