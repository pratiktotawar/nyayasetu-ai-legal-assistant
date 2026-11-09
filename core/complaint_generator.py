"""Module 4 — Generate My Complaint.

Template-based drafting (deliberately not free LLM generation) so that every
fact in a draft comes from the user's case file and every legal reference comes
from the verified knowledge base. Missing facts are written as
[MISSING: …] and information NyayaSetu intentionally does not collect (phone,
address, signature) as [ADD: …]. Every draft is labelled as an unfiled draft and
passed through the citation validator.

Documents
  seller_email        A. Complaint email to the seller
  platform_complaint  B. Formal complaint to the e-commerce platform's grievance officer
  nch_grievance       C. National Consumer Helpline grievance text
  commission_draft    D. Consumer Commission complaint — preparation draft
"""
from __future__ import annotations

import re
from datetime import date

from core.case_builder import describe_evidence, describe_resolution, human_date
from core.intake import CATEGORIES
from core.legal_validation import validate_text
from utils.language import format_inr

DOC_TYPES = {
    "seller_email": {"en": "A. Complaint email to the seller", "hi": "क. विक्रेता को शिकायत ईमेल"},
    "platform_complaint": {"en": "B. Formal complaint to the platform (grievance officer)", "hi": "ख. प्लेटफ़ॉर्म (शिकायत अधिकारी) को औपचारिक शिकायत"},
    "nch_grievance": {"en": "C. National Consumer Helpline grievance", "hi": "ग. राष्ट्रीय उपभोक्ता हेल्पलाइन शिकायत"},
    "commission_draft": {"en": "D. Consumer Commission complaint — preparation draft", "hi": "घ. उपभोक्ता आयोग शिकायत — तैयारी मसौदा"},
}

BANNER = {
    "en": "DRAFT PREPARED WITH NYAYASETU — NOT SENT, NOT FILED. This is a draft for you to check and edit. It is not a legal notice and not a filed complaint. "
          "Verify every fact, complete each [MISSING] and [ADD] field, and remove anything that is not accurate before you use it.",
    "hi": "NYAYASETU द्वारा तैयार मसौदा — भेजा नहीं गया, दर्ज नहीं किया गया। यह जाँचने और संपादित करने के लिए मसौदा है। यह कानूनी नोटिस या दर्ज की गई शिकायत नहीं है। "
          "हर तथ्य जाँचें, हर [अनुपलब्ध] और [जोड़ें] फ़ील्ड भरें, और जो सही न हो उसे हटा दें।",
}


class _Doc:
    def __init__(self, lang: str):
        self.lang = lang
        self.blocks: list[tuple[str, object]] = []
        self.missing: list[str] = []

    def M(self, en: str, hi: str) -> str:
        label = hi if self.lang == "hi" else en
        if label not in self.missing:
            self.missing.append(label)
        return f"[{'अनुपलब्ध' if self.lang == 'hi' else 'MISSING'}: {label}]"

    def A(self, en: str, hi: str) -> str:
        return f"[{'जोड़ें' if self.lang == 'hi' else 'ADD'}: {hi if self.lang == 'hi' else en}]"

    def h(self, text):
        self.blocks.append(("h", text))

    def p(self, text):
        self.blocks.append(("p", text))

    def lst(self, items, numbered=True):
        self.blocks.append(("ol" if numbered else "ul", list(items)))

    def kv(self, pairs):
        self.blocks.append(("kv", list(pairs)))

    def render(self) -> str:
        out = []
        for kind, val in self.blocks:
            if kind == "h":
                out.append("")
                out.append(str(val))
                out.append("-" * min(max(len(str(val)), 3), 70))
            elif kind == "p":
                out.append(str(val))
                out.append("")
            elif kind == "ol":
                for i, item in enumerate(val, 1):
                    out.append(f"{i}. {item}")
                out.append("")
            elif kind == "ul":
                for item in val:
                    out.append(f"- {item}")
                out.append("")
            elif kind == "kv":
                for k, v in val:
                    out.append(f"{k}: {v}")
                out.append("")
        text = "\n".join(out)
        return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


class ComplaintGenerator:
    def __init__(self, case: dict, rights: dict, today: date | None = None):
        self.case = case
        self.rights = rights
        self.today = today or date.fromisoformat(case.get("reference_date", date.today().isoformat()))
        self.issue_ids = {i["id"]: i for i in rights.get("issues", [])}

    # ------------------------------------------------------------------ public
    def generate(self, doc_type: str, lang: str = "en") -> dict:
        builder = {"seller_email": self._seller_email, "platform_complaint": self._platform_complaint,
                   "nch_grievance": self._nch, "commission_draft": self._commission}[doc_type]
        doc = _Doc(lang)
        title = builder(doc)
        text = doc.render()
        # count only the gaps that actually appear in this draft
        shown = list(dict.fromkeys(re.findall(r"\[(?:MISSING|अनुपलब्ध): ([^\]]+)\]", text)))
        doc.missing = shown
        report = validate_text(text)
        return {
            "doc_type": doc_type,
            "language": lang,
            "generated_by": "template",  # drafts are never written by an LLM, in any mode
            "claim_amount": (self.case.get("claim") or {}).get("amount"),
            "title": title,
            "text": text,
            "missing_fields": doc.missing,
            "missing_count": len(doc.missing),
            "validation": report.to_dict(),
            "appropriateness": self.appropriateness(doc_type, lang),
        }

    def generate_all(self, lang: str = "en") -> dict:
        return {k: self.generate(k, lang) for k in DOC_TYPES}

    def appropriateness(self, doc_type: str, lang: str) -> dict:
        fl = self.case["flags"]
        L = (lambda en, hi: hi if lang == "hi" else en)
        if doc_type != "commission_draft":
            return {"recommended": True, "notes": []}
        notes = []
        if fl.get("no_complaint_yet"):
            notes.append(L("You have not yet complained in writing to the seller/platform. NyayaSetu recommends doing that first so there is a record "
                           "and a chance to resolve it (practical advice, not a legal precondition found in the sources).",
                           "आपने अभी विक्रेता/प्लेटफ़ॉर्म को लिखित शिकायत नहीं की है। NyayaSetu पहले यह करने की सलाह देता है ताकि रिकॉर्ड बने और समाधान का मौका मिले "
                           "(यह व्यावहारिक सलाह है, स्रोतों में मिली कोई कानूनी पूर्व-शर्त नहीं)।"))
        if fl.get("possible_commercial_purpose"):
            notes.append(L("You said the purchase was for resale/business — consumer status is doubtful. Take legal advice before filing.",
                           "आपने बताया कि खरीद दोबारा बेचने/व्यापार के लिए थी — उपभोक्ता होने पर संदेह है। दर्ज करने से पहले कानूनी सलाह लें।"))
        if fl.get("limitation_risk"):
            notes.append(L("The 2-year time limit may be an issue. Take legal advice before filing.", "2 साल की समय सीमा समस्या हो सकती है। दर्ज करने से पहले कानूनी सलाह लें।"))
        if fl.get("value_band") in ("state", "national"):
            notes.append(L("High-value claim — State/National Commission; use a lawyer.", "अधिक मूल्य का दावा — राज्य/राष्ट्रीय आयोग; वकील की मदद लें।"))
        return {"recommended": not notes, "notes": notes}

    # ------------------------------------------------------------------ shared pieces
    def _L(self, doc: _Doc, en: str, hi: str) -> str:
        return hi if doc.lang == "hi" else en

    def _f(self, doc: _Doc) -> dict:
        c, t, p = self.case, self.case["transaction"], self.case["parties"]
        lang = doc.lang
        return {
            "name": c["consumer"].get("name") or doc.M("your name", "आपका नाम"),
            "city": c["consumer"].get("city") or doc.M("city / district", "शहर / ज़िला"),
            "product": t.get("product") or doc.M("product", "उत्पाद"),
            "platform": p.get("platform") or doc.M("platform / website", "प्लेटफ़ॉर्म / वेबसाइट"),
            "seller": p.get("seller") or doc.M("seller name (see invoice)", "विक्रेता का नाम (बिल देखें)"),
            "order_id": t.get("order_id") or doc.M("Order ID", "ऑर्डर आईडी"),
            "order_date": human_date(t.get("purchase_date"), t.get("purchase_date_approx"), lang) or doc.M("order date", "ऑर्डर तिथि"),
            "delivery_date": human_date(t.get("delivery_date"), t.get("delivery_date_approx"), lang) or doc.M("delivery date", "डिलीवरी तिथि"),
            "amount": format_inr(t.get("amount_paid")) if t.get("amount_paid") else doc.M("amount paid", "चुकाई गई राशि"),
            "charged": (format_inr(t.get("charged_amount")) if t.get("charged_amount") else
                        (doc.M("amount actually charged", "वास्तव में कटी राशि") if c["dispute"]["category"] == "incorrect_charge" else "")),
            "payment_mode": t.get("payment_mode") or "",
            "complaint_date": human_date(c.get("complaint_date"), c.get("complaint_date_approx"), lang),
            "ref": c.get("complaint_ref") or "",
            "details": (c.get("issue_details") or "").strip(),
            "response": (c.get("seller_response") or "").strip(),
            "steps": c.get("steps_taken") or [],
            "claim": self._claim_text(doc),
        }

    def _claim_text(self, doc: _Doc) -> str:
        """The refund amount exactly as confirmed by the user — never defaulted to the price paid."""
        claim = self.case.get("claim") or {}
        if claim.get("confirmed") and claim.get("amount"):
            return format_inr(claim["amount"])
        if claim.get("confirmed") and claim.get("basis") == "full":  # "full" confirmed but the price itself is unknown
            return doc.M("amount paid", "चुकाई गई राशि")
        paid = self.case["transaction"].get("amount_paid")
        hint_en = f"amount you are claiming — you paid {format_inr(paid)}" if paid else "amount you are claiming"
        hint_hi = f"आप कितनी राशि माँग रहे हैं — आपने {format_inr(paid)} चुकाए" if paid else "आप कितनी राशि माँग रहे हैं"
        return doc.M(hint_en, hint_hi)

    def _facts_list(self, doc: _Doc, f: dict) -> list[str]:
        L = lambda en, hi: self._L(doc, en, hi)  # noqa: E731
        cat = self.case["dispute"]["category"]
        pay = f" ({L('paid via', 'भुगतान माध्यम')} {f['payment_mode']})" if f["payment_mode"] else ""
        seller_part = L(f", sold by {f['seller']}", f" (विक्रेता: {f['seller']})")
        on_word = "In" if self.case["transaction"].get("purchase_date_approx") == "month" else "On"
        facts = [L(f"{on_word} {f['order_date']}, I placed an order for {f['product']} on {f['platform']}{seller_part} (Order ID: {f['order_id']}) and paid {f['amount']}{pay}.",
                   f"{f['order_date']} को मैंने {f['platform']} पर {f['product']} का ऑर्डर दिया{seller_part} (ऑर्डर आईडी: {f['order_id']}) और {f['amount']} का भुगतान किया{pay}।")]
        norm = lambda s: re.sub(r"\W+", " ", s).strip().lower()  # noqa: E731
        step_norms = {norm(s) for s in f["steps"]}
        detail_sents = [s for s in re.split(r"(?<=[.!?।])\s+", f["details"]) if s.strip()]
        kept = [s for s in detail_sents if norm(s) not in step_norms] or detail_sents
        details = " ".join(kept).strip()
        d = f"“{details}”" if details else doc.M("description of the problem", "समस्या का विवरण")
        if cat == "damaged_on_delivery":
            facts.append(L(f"The product was delivered on {f['delivery_date']} and was found to be damaged. In my words: {d}",
                           f"उत्पाद {f['delivery_date']} को डिलीवर हुआ और क्षतिग्रस्त पाया गया। मेरे शब्दों में: {d}"))
        elif cat == "defective_product":
            facts.append(L(f"The product was delivered on {f['delivery_date']}. After delivery it developed a defect. In my words: {d}",
                           f"उत्पाद {f['delivery_date']} को डिलीवर हुआ। डिलीवरी के बाद उसमें दोष आ गया। मेरे शब्दों में: {d}"))
        elif cat == "non_delivery":
            facts.append(L(f"The platform shows the order as delivered on {f['delivery_date']}. However, I have not received the product. In my words: {d}",
                           f"प्लेटफ़ॉर्म पर ऑर्डर {f['delivery_date']} को डिलीवर दिखाया गया है। लेकिन मुझे उत्पाद नहीं मिला। मेरे शब्दों में: {d}"))
        elif cat == "misleading_description":
            facts.append(L(f"I bought the product relying on its listing/advertisement. The product supplied does not match what was described. In my words: {d}",
                           f"मैंने उत्पाद उसकी लिस्टिंग/विज्ञापन पर भरोसा करके खरीदा। मिला हुआ उत्पाद बताए गए विवरण से मेल नहीं खाता। मेरे शब्दों में: {d}"))
        elif cat == "incorrect_charge":
            facts.append(L(f"I was charged {f['charged']} although the correct amount for this order was {f['amount']}. In my words: {d}",
                           f"इस ऑर्डर की सही राशि {f['amount']} थी, फिर भी मुझसे {f['charged']} लिए गए। मेरे शब्दों में: {d}"))
        else:
            facts.append(L(f"In my words: {d}", f"मेरे शब्दों में: {d}"))
        if f["steps"]:
            when = f" {L('on', '')} {f['complaint_date']}".rstrip() if f["complaint_date"] else ""
            ref = L(f" (reference: {f['ref']})", f" (संदर्भ: {f['ref']})") if f["ref"] else ""
            steps_txt = " / ".join(f"“{s.strip()}”" for s in f["steps"][:3])
            facts.append(L(f"I raised the matter with the seller/platform{when}{ref}. What I did: {steps_txt}",
                           f"मैंने{(' ' + f['complaint_date'] + ' को') if f['complaint_date'] else ''} यह मामला विक्रेता/प्लेटफ़ॉर्म के सामने उठाया{ref}। मैंने क्या किया: {steps_txt}"))
        resp_sents = [s for s in re.split(r"(?<=[.!?।])\s+", f["response"]) if s.strip() and norm(s) not in step_norms
                      and not any(norm(s) in sn for sn in step_norms)]
        if resp_sents:
            resp = " ".join(resp_sents)[:400]
            facts.append(L(f"The response I received: “{resp}”", f"मुझे मिला उत्तर: “{resp}”"))
        keys = self.case.get("desired_resolution", [])
        res = []
        for k in keys:
            if k == "refund":
                res.append(L(f"refund of {f['claim']}", f"{f['claim']} का रिफंड"))
            else:
                res.extend(describe_resolution([k], doc.lang))
        facts.append(L(f"As of {self._today(doc)}, the matter remains unresolved" + (f" and I have not received the {', '.join(r if r.startswith('refund') else r.lower() for r in res)} I asked for." if res else "."),
                       f"{self._today(doc)} तक मामला अनसुलझा है" + (f" और मुझे माँगा गया समाधान ({', '.join(res)}) नहीं मिला।" if res else "।")))
        return facts

    def _grounds(self, doc: _Doc, full: bool) -> list[str]:
        L = lambda en, hi: self._L(doc, en, hi)  # noqa: E731
        ii = self.issue_ids
        cat = self.case["dispute"]["category"]
        g = []
        if "defect" in ii:
            g.append(L("The goods supplied suffer from a defect within the meaning of Section 2(10) of the Consumer Protection Act, 2019, which is a ground of complaint under Section 2(6)(ii).",
                       "आपूर्ति किए गए सामान में उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 2(10) के अर्थ में दोष है, जो धारा 2(6)(ii) के तहत शिकायत का आधार है।"))
        if "ecom_takeback" in ii:
            ground = {"damaged_on_delivery": L("defective", "दोषपूर्ण"), "defective_product": L("defective", "दोषपूर्ण"),
                      "misleading_description": L("not of the characteristics or features as advertised or as agreed to", "विज्ञापित या तय की गई विशेषताओं के अनुसार नहीं"),
                      "non_delivery": L("not delivered as per the stated delivery schedule", "निर्धारित डिलीवरी समय के अनुसार डिलीवर नहीं")}.get(cat, "")
            g.append(L(f"Under Rule 6(3) of the Consumer Protection (E-Commerce) Rules, 2020, a seller on a marketplace shall not refuse to take back goods or refund the consideration where the goods are {ground}. Where the platform itself is the seller, Rule 7(4) imposes the same duty.",
                       f"उपभोक्ता संरक्षण (ई-कॉमर्स) नियम, 2020 के नियम 6(3) के अनुसार मार्केटप्लेस पर विक्रेता सामान वापस लेने या राशि लौटाने से इनकार नहीं कर सकता जब सामान {ground} हो। जहाँ प्लेटफ़ॉर्म स्वयं विक्रेता है, वहाँ नियम 7(4) यही कर्तव्य लगाता है।"))
        utp = ii.get("utp_refusal")
        if utp and utp["confidence"] == "arguable":
            g.append(L("I submit that the refusal or failure to take back the defective goods and refund the price within the applicable period may amount to an unfair trade practice under Section 2(47)(viii) of the Consumer Protection Act, 2019.",
                       "मेरा निवेदन है कि लागू अवधि के भीतर दोषपूर्ण सामान वापस लेने और कीमत लौटाने से इनकार या चूक उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 2(47)(viii) के तहत अनुचित व्यापार व्यवहार हो सकती है।"))
        if "non_delivery" in ii:
            g.append(L("I submit that the failure to deliver goods that were paid for, while the order is shown as delivered, amounts to a deficiency in service under Section 2(11) of the Consumer Protection Act, 2019, which is a ground of complaint under Section 2(6)(iii).",
                       "मेरा निवेदन है कि भुगतान किए गए सामान की डिलीवरी न होना, जबकि ऑर्डर डिलीवर दिखाया गया है, उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 2(11) के तहत सेवा में कमी है, जो धारा 2(6)(iii) के तहत शिकायत का आधार है।"))
        if "misleading" in ii:
            g.append(L("I submit that the listing falsely described the product, which may amount to a misleading advertisement under Section 2(28) and an unfair trade practice under Section 2(47)(i)(a) of the Consumer Protection Act, 2019; sellers must also ensure advertisements are consistent with the actual characteristics of goods (Rule 6(4) of the E-Commerce Rules).",
                       "मेरा निवेदन है कि लिस्टिंग में उत्पाद का गलत वर्णन किया गया, जो उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 2(28) के तहत भ्रामक विज्ञापन और धारा 2(47)(i)(a) के तहत अनुचित व्यापार व्यवहार हो सकता है; विक्रेताओं को यह भी सुनिश्चित करना होता है कि विज्ञापन सामान की वास्तविक विशेषताओं के अनुरूप हों (ई-कॉमर्स नियमों का नियम 6(4))।"))
        if "excess_charge" in ii:
            g.append(L("Charging an amount in excess of the price agreed and displayed at checkout is a ground of complaint under Section 2(6)(iv) of the Consumer Protection Act, 2019.",
                       "चेकआउट पर तय और प्रदर्शित कीमत से अधिक राशि लेना उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 2(6)(iv) के तहत शिकायत का आधार है।"))
        if "refund_rule" in ii:
            g.append(L("Under Rule 4(10) of the E-Commerce Rules, payments towards accepted refund requests must be made within a reasonable period of time.",
                       "ई-कॉमर्स नियमों के नियम 4(10) के अनुसार स्वीकृत रिफंड अनुरोधों का भुगतान उचित समय के भीतर किया जाना चाहिए।"))
        if "deficiency_support" in ii:
            g.append(L("I submit that the repeated failure to resolve my complaint amounts to a deficiency in service under Section 2(11) of the Consumer Protection Act, 2019.",
                       "मेरा निवेदन है कि मेरी शिकायत का बार-बार समाधान न करना उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 2(11) के तहत सेवा में कमी है।"))
        if not full:
            g.append(L("Under Rules 4(4) and 4(5) of the E-Commerce Rules, the platform's grievance officer must acknowledge a consumer complaint within 48 hours and redress it within one month; under Rule 5(3)(b) a marketplace must provide a ticket number for each complaint so that it can be tracked.",
                       "ई-कॉमर्स नियमों के नियम 4(4) और 4(5) के अनुसार प्लेटफ़ॉर्म के शिकायत अधिकारी को 48 घंटे में शिकायत की पावती देनी होती है और एक महीने में निवारण करना होता है; नियम 5(3)(b) के अनुसार मार्केटप्लेस को हर शिकायत के लिए ट्रैक करने योग्य टिकट नंबर देना होता है।"))
        return g

    def _relief(self, doc: _Doc, f: dict, commission: bool) -> list[str]:
        L = lambda en, hi: self._L(doc, en, hi)  # noqa: E731
        res = self.case.get("desired_resolution", [])
        cat = self.case["dispute"]["category"]
        out = []
        claim = self.case.get("claim") or {}
        amt = f["claim"]  # confirmed amount, or a [MISSING] marker — never the price by default
        if "refund" in res:
            who = L("their", "अपने") if commission else L("your", "अपने")
            goods = cat in ("damaged_on_delivery", "defective_product", "misleading_description")
            if cat == "incorrect_charge" and claim.get("basis") == "excess":
                out.append(L(f"Refund / reverse the excess amount of {amt} charged.", f"अधिक ली गई राशि {amt} वापस करें।"))
            elif claim.get("confirmed") and claim.get("basis") == "full":
                take_back = L(f" and take back the product at {who} own cost", " और अपने खर्च पर उत्पाद वापस लें") if goods else ""
                out.append(L(f"Refund the full amount of {amt} paid{take_back}.", f"चुकाई गई पूरी राशि {amt} लौटाएँ{take_back}।"))
            elif claim.get("confirmed") and claim.get("is_partial"):
                note = (claim.get("note") or "").strip()
                # quote the user's reason only if they gave one beyond the number itself
                if not re.search(r"[A-Za-z\u0900-\u097F]{3,}", re.sub(r"(?i)\b(rs|inr|rupees?|only|full)\b|रुपये|रुपए", "", note)):
                    note = ""
                why = L(f", as stated: “{note[:140]}”", f", जैसा बताया: “{note[:140]}”") if note else ""
                out.append(L(f"Refund {amt} (out of the {f['amount']} paid){why}.", f"{amt} लौटाएँ (चुकाए गए {f['amount']} में से){why}।"))
            else:
                out.append(L(f"Refund {amt}.", f"{amt} लौटाएँ।"))
        if "replacement" in res:
            out.append(L(f"Replace the {f['product']} with a new, defect-free unit of the same description.", f"{f['product']} को उसी विवरण के नए, दोषरहित उत्पाद से बदलें।"))
        if "repair" in res:
            out.append(L("Repair the product free of charge so that it works as it should.", "उत्पाद की निःशुल्क मरम्मत करें ताकि वह ठीक से काम करे।"))
        if "delivery" in res:
            out.append(L(f"Deliver the {f['product']} ordered, or refund {amt}.", f"ऑर्डर किया गया {f['product']} डिलीवर करें, या {amt} लौटाएँ।"))
        if not out:
            out.append(doc.M("the resolution you want (refund / replacement / repair)", "आप क्या समाधान चाहते हैं (रिफंड / बदलाव / मरम्मत)"))
        if commission:
            if "compensation" in res:
                out.append(L("Pay compensation for the loss and inconvenience caused: " + doc.A("amount you claim and why", "आप कितना मुआवज़ा माँगते हैं और क्यों") + ".",
                             "हुए नुकसान और असुविधा का मुआवज़ा दें: " + doc.A("amount you claim and why", "आप कितना मुआवज़ा माँगते हैं और क्यों") + "।"))
            out.append(L("Pay interest on the amount refunded and the costs of this complaint, as the Hon'ble Commission may deem fit.",
                         "लौटाई गई राशि पर ब्याज और इस शिकायत का खर्च दें, जैसा माननीय आयोग उचित समझे।"))
            out.append(L("Grant any other relief the Hon'ble Commission considers appropriate.", "कोई अन्य राहत जो माननीय आयोग उचित समझे।"))
        elif "compensation" in res:
            out.append(L("Pay reasonable compensation for the inconvenience caused.", "हुई असुविधा का उचित मुआवज़ा दें।"))
        return out

    def _annexures(self, doc: _Doc) -> list[str]:
        ev = describe_evidence(self.case.get("evidence", []), doc.lang)
        if not ev:
            return [doc.M("list of documents you can attach (invoice, payment proof, photos, emails)", "संलग्न किए जा सकने वाले दस्तावेज़ (बिल, भुगतान प्रमाण, फोटो, ईमेल)")]
        return [f"{'अनुलग्नक' if doc.lang == 'hi' else 'Annexure'} A-{i}: {e}" for i, e in enumerate(ev, 1)]

    def _today(self, doc: _Doc) -> str:
        from utils.language import format_date
        return format_date(self.today.isoformat(), doc.lang)

    def _cat_short(self, lang: str) -> str:
        return CATEGORIES.get(self.case["dispute"]["category"], CATEGORIES["unknown"])[lang]

    # ------------------------------------------------------------------ A. seller email
    def _seller_email(self, doc: _Doc) -> str:
        f = self._f(doc)
        L = lambda en, hi: self._L(doc, en, hi)  # noqa: E731
        doc.p(BANNER[doc.lang])
        res = ", ".join(describe_resolution(self.case.get("desired_resolution", []), doc.lang)) or L("resolution", "समाधान")
        doc.kv([(L("To", "प्रति"), f"{f['seller']} — " + doc.A("seller's customer-care email (from the invoice or order page)", "विक्रेता का ग्राहक-सेवा ईमेल (बिल या ऑर्डर पेज से)")),
                (L("Cc", "प्रतिलिपि"), f"{f['platform']} — " + doc.A("platform customer-care / grievance officer email", "प्लेटफ़ॉर्म ग्राहक-सेवा / शिकायत अधिकारी ईमेल")),
                (L("Subject", "विषय"), L(f"Complaint regarding Order {f['order_id']} — {self._cat_short('en')} — request for {res.lower()}",
                                          f"ऑर्डर {f['order_id']} के संबंध में शिकायत — {self._cat_short('hi')} — {res} का अनुरोध"))])
        doc.p(L("Dear Sir/Madam,", "महोदय/महोदया,"))
        doc.p(L(f"I am writing about my order {f['order_id']} for {f['product']}. The facts are:",
                f"मैं {f['product']} के अपने ऑर्डर {f['order_id']} के बारे में लिख रहा/रही हूँ। तथ्य इस प्रकार हैं:"))
        doc.lst(self._facts_list(doc, f))
        grounds = [g for g in self._grounds(doc, full=True)]
        if grounds:
            doc.p(L("I would like to draw your attention to the following:", "मैं आपका ध्यान निम्नलिखित की ओर दिलाना चाहता/चाहती हूँ:"))
            doc.lst(grounds[:3], numbered=False)
        doc.p(L("I request you to:", "मेरा अनुरोध है कि:"))
        doc.lst(self._relief(doc, f, commission=False))
        doc.p(L("Please resolve this promptly and confirm in writing, quoting a reference number. If the matter is not resolved, I may pursue the remedies available to me, including the National Consumer Helpline and the Consumer Commission.",
                "कृपया इसका शीघ्र समाधान करें और संदर्भ संख्या सहित लिखित में पुष्टि करें। समाधान न होने पर मैं उपलब्ध उपायों का सहारा ले सकता/सकती हूँ, जिनमें राष्ट्रीय उपभोक्ता हेल्पलाइन और उपभोक्ता आयोग शामिल हैं।"))
        doc.p(L("Documents I can share on request:", "अनुरोध पर साझा किए जा सकने वाले दस्तावेज़:"))
        doc.lst(self._annexures(doc), numbered=False)
        doc.p(L("Regards,", "सादर,"))
        doc.p(f"{f['name']}\n{f['city']}\n" + doc.A("phone / email", "फ़ोन / ईमेल"))
        return DOC_TYPES["seller_email"][doc.lang]

    # ------------------------------------------------------------------ B. platform complaint
    def _platform_complaint(self, doc: _Doc) -> str:
        f = self._f(doc)
        L = lambda en, hi: self._L(doc, en, hi)  # noqa: E731
        doc.p(BANNER[doc.lang])
        doc.kv([(L("To", "प्रति"), L(f"The Grievance Officer, {f['platform']}", f"शिकायत अधिकारी, {f['platform']}")),
                (L("Grievance officer's name / email", "शिकायत अधिकारी का नाम / ईमेल"), doc.A("as displayed on the platform (help or legal pages)", "प्लेटफ़ॉर्म पर दिखाए अनुसार (सहायता या कानूनी पेज)")),
                (L("From", "प्रेषक"), f"{f['name']}, {f['city']}"),
                (L("Date", "तिथि"), self._today(doc)),
                (L("Subject", "विषय"), L(f"Formal consumer complaint — Order {f['order_id']} — {self._cat_short('en')}",
                                          f"औपचारिक उपभोक्ता शिकायत — ऑर्डर {f['order_id']} — {self._cat_short('hi')}"))])
        doc.h(L("1. Order details", "1. ऑर्डर का विवरण"))
        doc.kv([(L("Product", "उत्पाद"), f["product"]), (L("Order ID", "ऑर्डर आईडी"), f["order_id"]),
                (L("Order date", "ऑर्डर तिथि"), f["order_date"]), (L("Amount paid", "चुकाई गई राशि"), f["amount"]),
                *([(L("Refund claimed", "माँगा गया रिफंड"), f["claim"])] if (self.case.get("claim") or {}).get("refund_requested") else []),
                (L("Seller", "विक्रेता"), f["seller"]),
                (L("Earlier complaint / ticket", "पिछली शिकायत / टिकट"), f["ref"] or (L("none recorded", "दर्ज नहीं") if self.case.get("no_complaint_yet") else doc.M("ticket number of earlier complaint", "पिछली शिकायत का टिकट नंबर")))])
        doc.h(L("2. Facts", "2. तथ्य"))
        doc.lst(self._facts_list(doc, f))
        doc.h(L("3. Grievance and grounds", "3. शिकायत और आधार"))
        doc.lst(self._grounds(doc, full=False))
        doc.h(L("4. Relief requested", "4. माँगी गई राहत"))
        doc.lst(self._relief(doc, f, commission=False))
        doc.p(L("Please acknowledge this complaint, share a ticket number, and let me know the action taken.",
                "कृपया इस शिकायत की पावती दें, टिकट नंबर साझा करें, और की गई कार्रवाई बताएँ।"))
        doc.h(L("5. Documents available (annexures)", "5. उपलब्ध दस्तावेज़ (अनुलग्नक)"))
        doc.lst(self._annexures(doc), numbered=False)
        doc.p(L("Yours faithfully,", "भवदीय,"))
        doc.p(f"{f['name']}\n{f['city']}\n" + doc.A("phone / registered email on the account", "फ़ोन / खाते पर पंजीकृत ईमेल"))
        return DOC_TYPES["platform_complaint"][doc.lang]

    # ------------------------------------------------------------------ C. NCH grievance
    def _nch(self, doc: _Doc) -> str:
        f = self._f(doc)
        L = lambda en, hi: self._L(doc, en, hi)  # noqa: E731
        doc.p(BANNER[doc.lang])
        doc.p(L("How to register: call toll-free 1915, SMS/WhatsApp 8800001915, use the NCH app or UMANG, or register at consumerhelpline.gov.in. "
                "The portal's form may ask for these details in a different order — copy the relevant parts.",
                "कैसे दर्ज करें: 1915 पर कॉल करें, 8800001915 पर व्हाट्सऐप करें, NCH ऐप या UMANG का उपयोग करें, या consumerhelpline.gov.in पर दर्ज करें। "
                "पोर्टल का फ़ॉर्म ये विवरण अलग क्रम में माँग सकता है — संबंधित हिस्से कॉपी करें।"))
        doc.h(L("Grievance details", "शिकायत का विवरण"))
        ref_line = f["ref"] or (L("No complaint made yet", "अभी कोई शिकायत नहीं की") if self.case.get("no_complaint_yet") else doc.M("ticket number of complaint to the company", "कंपनी को की गई शिकायत का टिकट नंबर"))
        doc.kv([(L("Sector", "क्षेत्र"), L("E-Commerce", "ई-कॉमर्स")),
                (L("Company / platform", "कंपनी / प्लेटफ़ॉर्म"), f["platform"]),
                (L("Seller", "विक्रेता"), f["seller"]),
                (L("Nature of grievance", "शिकायत की प्रकृति"), self._cat_short(doc.lang)),
                (L("Product", "उत्पाद"), f["product"]),
                (L("Order ID", "ऑर्डर आईडी"), f["order_id"]),
                (L("Order date", "ऑर्डर तिथि"), f["order_date"]),
                (L("Amount paid", "चुकाई गई राशि"), f["amount"]),
                *([(L("Refund claimed", "माँगा गया रिफंड"), f["claim"])] if (self.case.get("claim") or {}).get("refund_requested") else []),
                (L("Complaint already made to company (date / reference)", "कंपनी को पहले की गई शिकायत (तिथि / संदर्भ)"),
                 " / ".join(x for x in [f["complaint_date"], ref_line] if x))])
        doc.h(L("Description", "विवरण"))
        doc.lst(self._facts_list(doc, f))
        doc.h(L("Expected resolution", "अपेक्षित समाधान"))
        doc.lst(self._relief(doc, f, commission=False), numbered=False)
        doc.h(L("Documents I can upload", "अपलोड किए जा सकने वाले दस्तावेज़"))
        doc.lst(self._annexures(doc), numbered=False)
        doc.p(L("Note: NCH is a pre-litigation step. The portal says it may take up to 30 days to reach a conclusion; if your grievance is not "
                "resolved, you can approach the Consumer Commission.",
                "ध्यान दें: NCH मुकदमे से पहले का कदम है। पोर्टल के अनुसार निष्कर्ष तक पहुँचने में अधिकतम 30 दिन लग सकते हैं; शिकायत का समाधान न हो तो आप उपभोक्ता आयोग जा सकते हैं।"))
        return DOC_TYPES["nch_grievance"][doc.lang]

    # ------------------------------------------------------------------ D. Commission draft
    def _commission(self, doc: _Doc) -> str:
        f = self._f(doc)
        L = lambda en, hi: self._L(doc, en, hi)  # noqa: E731
        fl = self.case["flags"]
        doc.p(BANNER[doc.lang])
        doc.p(L("PREPARATION DRAFT ONLY. Consumer Commissions have their own format, affidavit and document requirements, and complaints are filed "
                "through e-Jagriti (e-jagriti.gov.in). Use this to organise your facts; check the portal's requirements, and consider asking an advocate "
                "or a recognised consumer association to review it before filing.",
                "केवल तैयारी मसौदा। उपभोक्ता आयोगों का अपना प्रारूप, शपथ-पत्र और दस्तावेज़ आवश्यकताएँ होती हैं, और शिकायतें ई-जागृति (e-jagriti.gov.in) से दर्ज होती हैं। "
                "इसे अपने तथ्य व्यवस्थित करने के लिए इस्तेमाल करें; पोर्टल की आवश्यकताएँ जाँचें, और दर्ज करने से पहले किसी अधिवक्ता या मान्यता प्राप्त उपभोक्ता संघ से समीक्षा कराने पर विचार करें।"))
        for note in self.appropriateness("commission_draft", doc.lang)["notes"]:
            doc.p(L("CAUTION: ", "सावधानी: ") + note)
        band = fl.get("value_band")
        forum = {"district": L("DISTRICT CONSUMER DISPUTES REDRESSAL COMMISSION", "ज़िला उपभोक्ता विवाद प्रतितोष आयोग"),
                 "state": L("STATE CONSUMER DISPUTES REDRESSAL COMMISSION", "राज्य उपभोक्ता विवाद प्रतितोष आयोग"),
                 "national": L("NATIONAL CONSUMER DISPUTES REDRESSAL COMMISSION", "राष्ट्रीय उपभोक्ता विवाद प्रतितोष आयोग"),
                 "unknown": L("[DISTRICT / STATE] CONSUMER DISPUTES REDRESSAL COMMISSION", "[ज़िला / राज्य] उपभोक्ता विवाद प्रतितोष आयोग")}[band]
        doc.h(L(f"BEFORE THE {forum}, {f['city']}", f"समक्ष: {forum}, {f['city']}"))
        doc.p(L("Consumer Complaint No. ______ of 20___ (to be assigned)", "उपभोक्ता शिकायत संख्या ______ / 20___ (आयोग द्वारा दी जाएगी)"))
        doc.p(L("IN THE MATTER OF:", "मामले में:"))
        doc.p(f"{f['name']}, " + doc.A("full address", "पूरा पता") + f", {f['city']} — " + L("Complainant", "शिकायतकर्ता"))
        doc.p(L("VERSUS", "बनाम"))
        doc.lst([f"{f['seller']}, " + doc.M("seller's registered address (from the invoice / platform seller page)", "विक्रेता का पंजीकृत पता (बिल / प्लेटफ़ॉर्म विक्रेता पेज से)") + " — " + L("Opposite Party No. 1", "विपक्षी पक्ष संख्या 1"),
                 f"{f['platform']}, " + doc.M("platform's registered office address", "प्लेटफ़ॉर्म के पंजीकृत कार्यालय का पता") + " — " + L("Opposite Party No. 2", "विपक्षी पक्ष संख्या 2")])
        doc.p(L("COMPLAINT UNDER SECTION 35 OF THE CONSUMER PROTECTION ACT, 2019", "उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 35 के अंतर्गत शिकायत"))
        doc.h(L("1. The Complainant is a consumer", "1. शिकायतकर्ता उपभोक्ता है"))
        purpose = self.case["consumer"].get("purpose")
        if purpose == "personal":
            doc.p(L("The Complainant bought the goods for consideration through an online transaction for personal use and is a 'consumer' under Section 2(7) of the Consumer Protection Act, 2019.",
                    "शिकायतकर्ता ने निजी उपयोग के लिए ऑनलाइन लेन-देन से मूल्य देकर सामान खरीदा और वह उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 2(7) के तहत 'उपभोक्ता' है।"))
        elif purpose == "livelihood":
            doc.p(L("The Complainant bought the goods for consideration through an online transaction and used them exclusively to earn a livelihood by self-employment; such use is not a 'commercial purpose' under the Explanation to Section 2(7) of the Consumer Protection Act, 2019.",
                    "शिकायतकर्ता ने ऑनलाइन लेन-देन से मूल्य देकर सामान खरीदा और उसे केवल स्व-रोज़गार से आजीविका कमाने के लिए इस्तेमाल किया; उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 2(7) के स्पष्टीकरण के अनुसार ऐसा उपयोग 'व्यावसायिक उद्देश्य' नहीं है।"))
        elif purpose == "resale_or_commercial":
            doc.p(L("CAUTION: You told NyayaSetu the goods were bought for resale or business. Section 2(7) excludes such buyers from the definition of consumer. Do not file this without legal advice.",
                    "सावधानी: आपने NyayaSetu को बताया कि सामान दोबारा बेचने या व्यापार के लिए खरीदा गया था। धारा 2(7) ऐसे खरीदारों को उपभोक्ता की परिभाषा से बाहर रखती है। कानूनी सलाह के बिना इसे दर्ज न करें।"))
        else:
            doc.p(L("The Complainant bought the goods for consideration through an online transaction and is a 'consumer' under Section 2(7) of the Consumer Protection Act, 2019. ",
                    "शिकायतकर्ता ने ऑनलाइन लेन-देन से मूल्य देकर सामान खरीदा और वह उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 2(7) के तहत 'उपभोक्ता' है। ")
                  + doc.M("confirm the goods were bought for personal / household use", "पुष्टि करें कि सामान निजी / घरेलू उपयोग के लिए खरीदा गया था"))
        doc.h(L("2. Facts of the case", "2. मामले के तथ्य"))
        doc.lst(self._facts_list(doc, f))
        doc.h(L("3. Grounds", "3. आधार"))
        doc.lst(self._grounds(doc, full=True) or [doc.M("legal grounds (none identified from the verified sources)", "कानूनी आधार (सत्यापित स्रोतों से कोई नहीं मिला)")])
        doc.h(L("4. Cause of action", "4. वाद का कारण"))
        doc.p(L(f"The cause of action arose {'in' if self.case['transaction'].get('purchase_date_approx') == 'month' else 'on'} {f['order_date']} when the order was placed, and further on {f['delivery_date'] if self.case['dispute']['category'] in ('damaged_on_delivery', 'defective_product', 'non_delivery') else f['order_date']} and on each date the Opposite Parties failed to resolve the complaint, and it is continuing.",
                f"वाद का कारण {f['order_date']} को ऑर्डर देने पर उत्पन्न हुआ, और आगे {f['delivery_date'] if self.case['dispute']['category'] in ('damaged_on_delivery', 'defective_product', 'non_delivery') else f['order_date']} को तथा हर उस तिथि को जब विपक्षी पक्षों ने शिकायत का समाधान नहीं किया, और यह जारी है।"))
        doc.h(L("5. Jurisdiction", "5. क्षेत्राधिकार"))
        amt = f["amount"]
        if band == "district":
            doc.p(L(f"Pecuniary: the value of goods paid as consideration is {amt}, which does not exceed ₹50 lakh; this Commission has jurisdiction under Rule 3 of the Consumer Protection (Jurisdiction of the District Commission, the State Commission and the National Commission) Rules, 2021.",
                    f"आर्थिक: प्रतिफल के रूप में चुकाया गया सामान का मूल्य {amt} है, जो ₹50 लाख से अधिक नहीं; उपभोक्ता संरक्षण (ज़िला आयोग, राज्य आयोग और राष्ट्रीय आयोग का क्षेत्राधिकार) नियम, 2021 के नियम 3 के तहत इस आयोग को क्षेत्राधिकार है।"))
        else:
            doc.p(L(f"Pecuniary: value of goods paid as consideration {amt} — " + doc.A("confirm the correct Commission under the Jurisdiction Rules, 2021", "क्षेत्राधिकार नियम, 2021 के तहत सही आयोग की पुष्टि करें"),
                    f"आर्थिक: प्रतिफल के रूप में चुकाया गया मूल्य {amt} — " + doc.A("confirm the correct Commission under the Jurisdiction Rules, 2021", "क्षेत्राधिकार नियम, 2021 के तहत सही आयोग की पुष्टि करें")))
        doc.p(L(f"Territorial: the Complainant resides / personally works for gain at {f['city']}, within the limits of this Commission (Section 34(2)(d) of the Act).",
                f"क्षेत्रीय: शिकायतकर्ता {f['city']} में रहता/रहती है / वहाँ काम करता/करती है, जो इस आयोग की सीमा में है (उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 34(2)(d))।"))
        doc.h(L("6. Limitation", "6. परिसीमा"))
        if fl.get("limitation_expired_likely") or fl.get("limitation_risk"):
            doc.p(L("CAUTION: The earliest relevant date appears to be close to or more than two years ago. Section 69 requires filing within two years of the cause of action; a delay can be condoned only for sufficient cause. Take legal advice and, if needed, an application for condonation of delay.",
                    "सावधानी: सबसे पुरानी संबंधित तिथि दो साल के क़रीब या उससे पहले की लगती है। धारा 69 के अनुसार वाद के कारण से दो साल में दर्ज करना होता है; देरी केवल पर्याप्त कारण होने पर माफ़ हो सकती है। कानूनी सलाह लें और ज़रूरत हो तो देरी माफ़ी का आवेदन दें।"))
        else:
            doc.p(L("The complaint is filed within two years of the cause of action, as required by Section 69 of the Consumer Protection Act, 2019.",
                    "शिकायत उपभोक्ता संरक्षण अधिनियम, 2019 की धारा 69 के अनुसार वाद के कारण से दो साल के भीतर दर्ज की जा रही है।"))
        doc.h(L("7. Prayer", "7. प्रार्थना"))
        doc.p(L("The Complainant respectfully prays that the Hon'ble Commission may direct the Opposite Parties, jointly and/or severally, to:",
                "शिकायतकर्ता सम्मानपूर्वक प्रार्थना करता/करती है कि माननीय आयोग विपक्षी पक्षों को संयुक्त रूप से और/या अलग-अलग निर्देश दे कि:"))
        doc.lst(self._relief(doc, f, commission=True))
        doc.h(L("8. List of documents", "8. दस्तावेज़ों की सूची"))
        doc.lst(self._annexures(doc), numbered=False)
        doc.h(L("9. Verification", "9. सत्यापन"))
        doc.p(L("I, " + f["name"] + ", the Complainant, state that the facts above are true to my knowledge and belief. " + doc.A("place, date and signature; affidavit as required by the Commission", "स्थान, तिथि और हस्ताक्षर; आयोग की आवश्यकता अनुसार शपथ-पत्र"),
                "मैं, " + f["name"] + ", शिकायतकर्ता, कहता/कहती हूँ कि ऊपर दिए तथ्य मेरी जानकारी और विश्वास के अनुसार सत्य हैं। " + doc.A("place, date and signature; affidavit as required by the Commission", "स्थान, तिथि और हस्ताक्षर; आयोग की आवश्यकता अनुसार शपथ-पत्र")))
        return DOC_TYPES["commission_draft"][doc.lang]
