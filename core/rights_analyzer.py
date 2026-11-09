"""Module 3 — Understand My Rights.

Deterministic, source-grounded analysis. Every issue card carries:
  * what the law says        — plain-language text + official excerpt from the verified KB
  * how it may apply         — conditional reasoning built from the user's own facts
  * evidence that supports   — what the user has vs what is still missing
  * what you can do next
  * official source(s)       — URL, issuing authority, verification date and status

Each card is labelled so a user can tell a statutory rule from a possible
argument, a procedural rule, a possible remedy or a practical step. Nothing here
guarantees an outcome. When a live LLM is configured it may rewrite the overall
summary in friendlier words, but only from the retrieved sources, and its text
is discarded unless it passes core.legal_validation.
"""
from __future__ import annotations

import re
from datetime import date

from core.case_builder import describe_evidence, human_date
from core.intake import CATEGORIES
from core.legal_retrieval import LegalKnowledgeBase, get_kb
from core.legal_validation import validate_llm_explanation
from utils.language import format_inr

LABELS = {
    "statutory": {"en": "What the law requires", "hi": "कानून क्या अपेक्षा करता है"},
    "argument": {"en": "Possible legal argument — depends on facts and proof", "hi": "संभावित कानूनी तर्क — तथ्यों और सबूत पर निर्भर"},
    "procedure": {"en": "Procedure", "hi": "प्रक्रिया"},
    "remedy": {"en": "Possible remedy — decided by the Commission", "hi": "संभावित राहत — आयोग तय करता है"},
    "practical": {"en": "Recommended practical step", "hi": "सुझाया गया व्यावहारिक कदम"},
    "notice": {"en": "Notice — verify before relying", "hi": "सूचना — भरोसा करने से पहले जाँचें"},
}
CONFIDENCE = {
    "clear": {"en": "Clear rule", "hi": "स्पष्ट नियम"},
    "arguable": {"en": "Arguable — depends on facts", "hi": "तर्कसंगत — तथ्यों पर निर्भर"},
    "evidence": {"en": "Depends mainly on your evidence", "hi": "मुख्यतः आपके सबूत पर निर्भर"},
    "not_yet": {"en": "Not yet established", "hi": "अभी स्थापित नहीं"},
    "uncertain": {"en": "Uncertain — get legal advice", "hi": "अनिश्चित — कानूनी सलाह लें"},
    "info": {"en": "Information", "hi": "जानकारी"},
}


def _L(lang: str, en: str, hi: str) -> str:
    return hi if lang == "hi" else en


class RightsAnalyzer:
    def __init__(self, kb: LegalKnowledgeBase | None = None, llm=None):
        self.kb = kb or get_kb()
        self.llm = llm

    # ------------------------------------------------------------------ public
    def analyse(self, case: dict, lang: str | None = None, today: date | None = None) -> dict:
        lang = lang or case.get("language", "en")
        today = today or date.fromisoformat(case.get("reference_date", date.today().isoformat()))
        f = self._facts(case, lang)
        issues: list[dict] = []
        cat = case["dispute"]["category"]
        cats = [cat] + list(case["dispute"].get("secondary", []))

        issues.append(self._consumer_status(case, f, lang))
        if cat in ("damaged_on_delivery", "defective_product"):
            issues.append(self._defect(case, f, lang))
            issues.append(self._ecom_takeback(case, f, lang))
            issues.append(self._utp_refusal(case, f, lang))
            if case["flags"].get("harm_beyond_product"):
                issues.append(self._product_liability(case, f, lang))
        elif cat == "non_delivery":
            issues.append(self._non_delivery(case, f, lang))
            issues.append(self._ecom_takeback(case, f, lang))
        elif cat == "misleading_description":
            issues.append(self._misleading(case, f, lang))
            issues.append(self._ecom_takeback(case, f, lang))
            issues.append(self._regulator_route(case, f, lang))
        elif cat == "incorrect_charge":
            issues.append(self._excess_charge(case, f, lang))
            issues.append(self._refund_rule(case, f, lang))
            issues.append(self._deficiency_support(case, f, lang))
            issues.append(self._payment_route(case, f, lang))
        elif cat == "refund_not_received":
            issues.append(self._refund_rule(case, f, lang))
            issues.append(self._deficiency_support(case, f, lang))
        else:
            issues.append(self._unknown_category(case, f, lang))
        if cat != "refund_not_received" and "refund_not_received" in cats and cat != "incorrect_charge":
            issues.append(self._refund_rule(case, f, lang))
        issues.append(self._grievance_officer(case, f, lang))
        issues.append(self._forum(case, f, lang, today))
        issues.append(self._remedies(case, f, lang))
        issues = [self._attach_sources(i, lang) for i in issues if i]

        notices = [self._source_view(self.kb.get("ECOM_AMENDMENT_2026"), lang)]
        uncertainties = self._uncertainties(case, issues, lang)
        lawyer = self._lawyer_triggers(case, lang)
        query = " ".join([CATEGORIES.get(cat, {}).get("en", ""), case.get("issue_details", ""), case.get("seller_response", "")])
        retrieved = [{"id": r.id, "score": r.score, "short_cite": r.entry["short_cite"]}
                     for r in self.kb.search(query, k=8, categories=cats + ["all", "forum", "ecommerce"])]
        summary = self._deterministic_summary(case, issues, lang)
        result = {
            "language": lang,
            "summary": {"text": summary, "generated_by": "rules", "note": ""},
            "issues": issues,
            "notices": notices,
            "uncertainties": uncertainties,
            "lawyer_triggers": lawyer,
            "retrieved": retrieved,
        }
        if self.llm is not None and getattr(self.llm, "is_live", False):
            self._llm_summary(case, result, lang)
        return result

    # ------------------------------------------------------------------ helpers
    def _facts(self, case: dict, lang: str) -> dict:
        t = case["transaction"]
        product = t.get("product") or _L(lang, "the product", "उत्पाद")
        platform = case["parties"].get("platform") or _L(lang, "the platform", "प्लेटफ़ॉर्म")
        seller = case["parties"].get("seller") or _L(lang, "the seller", "विक्रेता")
        amount = format_inr(t.get("amount_paid")) if t.get("amount_paid") else ""
        days = case["flags"].get("days_since_complaint")
        return {"product": product, "platform": platform, "seller": seller, "amount": amount, "days": days,
                "complaint_on": human_date(case.get("complaint_date"), case.get("complaint_date_approx"), lang)}

    def _ev(self, case: dict, wanted: list[str]) -> tuple[list[str], list[str]]:
        have = [e for e in wanted if e in case.get("evidence", [])]
        miss = [e for e in wanted if e not in case.get("evidence", [])]
        return have, miss

    def _issue(self, iid, title_en, title_hi, label, confidence, sources, how, evidence_wanted, next_step, lang,
               case, uncertain: list[str] | None = None) -> dict:
        have, miss = self._ev(case, evidence_wanted)
        return {
            "id": iid,
            "title": _L(lang, title_en, title_hi),
            "label": label,
            "label_text": LABELS[label][lang],
            "confidence": confidence,
            "confidence_text": CONFIDENCE[confidence][lang],
            "source_ids": sources,
            "how_applies": how,
            "evidence_have": describe_evidence(have, lang),
            "evidence_missing": describe_evidence(miss, lang),
            "next_step": next_step,
            "uncertain": uncertain or [],
        }

    def _source_view(self, e: dict | None, lang: str) -> dict:
        if not e:
            return {}
        return {
            "id": e["id"], "short_cite": e["short_cite"], "title": e.get("title", ""),
            "plain": e["plain_language"].get(lang) or e["plain_language"]["en"],
            "excerpt": e["excerpt"], "excerpt_type": e.get("excerpt_type", ""),
            "url": e["url"], "secondary_url": e.get("secondary_url", ""),
            "issuing_authority": e["issuing_authority"], "verified_on": e["verified_on"],
            "status": e["verification_status"],
        }

    def _attach_sources(self, issue: dict, lang: str) -> dict:
        views, unverified = [], []
        for sid in issue["source_ids"]:
            e = self.kb.get(sid)
            if e is None:
                unverified.append(sid)
                continue
            views.append(self._source_view(e, lang))
            if e["verification_status"] == "needs_verification":
                unverified.append(sid)
        issue["law"] = views
        issue["verification_needed"] = unverified
        if unverified:
            issue["uncertain"].append(_L(lang, "Some sources for this point could not be verified; do not rely on it as established law.",
                                         "इस बिंदु के कुछ स्रोत सत्यापित नहीं हो सके; इसे स्थापित कानून न मानें।"))
        return issue

    # ------------------------------------------------------------------ issues
    def _consumer_status(self, case, f, lang):
        purpose = case["consumer"].get("purpose")
        if purpose == "resale_or_commercial":
            how = _L(lang,
                     f"You indicated that the goods ({f['product']}) were bought for resale or business. The Act excludes a person who buys goods "
                     "“for resale or for any commercial purpose” from the definition of consumer, except goods bought and used exclusively "
                     "to earn a livelihood by self-employment. If that exclusion applies, a Consumer Commission may not hear your complaint "
                     "at all. This is a threshold question to discuss with a lawyer before filing; other remedies (for example a civil claim) "
                     "may be more appropriate but are outside NyayaSetu's scope.",
                     f"आपने बताया कि {f['product']} दोबारा बेचने या व्यापार के लिए खरीदा गया था। अधिनियम “दोबारा बेचने या किसी व्यावसायिक "
                     "उद्देश्य” से खरीदने वाले व्यक्ति को उपभोक्ता की परिभाषा से बाहर रखता है — सिवाय स्व-रोज़गार से आजीविका के लिए खरीदे गए सामान के। "
                     "अगर यह अपवाद लागू होता है, तो उपभोक्ता आयोग आपकी शिकायत शायद सुने ही नहीं। दर्ज करने से पहले इस प्रश्न पर वकील से बात करें; "
                     "अन्य उपाय (जैसे दीवानी दावा) अधिक उपयुक्त हो सकते हैं, जो NyayaSetu के दायरे से बाहर हैं।")
            return self._issue("consumer_status", "Are you a 'consumer' under the Act?", "क्या आप अधिनियम के तहत 'उपभोक्ता' हैं?",
                               "argument", "uncertain", ["CPA_2_7"], how, ["invoice"],
                               _L(lang, "Get legal advice on whether the commercial-purpose exclusion applies before filing.",
                                  "दर्ज करने से पहले कानूनी सलाह लें कि व्यावसायिक-उद्देश्य वाला अपवाद लागू होता है या नहीं।"), lang, case,
                               [_L(lang, "Whether the purchase was for a 'commercial purpose' (which would exclude you) is uncertain.",
                                   "खरीद 'व्यावसायिक उद्देश्य' से थी या नहीं (जिससे आप बाहर हो जाएँगे), यह अनिश्चित है।")])
        if purpose == "livelihood":
            extra_en = ("You said the goods were bought to earn your own livelihood through self-employment. The Act's Explanation keeps such "
                        "buyers within the definition, but you may need to show the goods were used exclusively for that purpose.")
            extra_hi = ("आपने बताया कि सामान स्व-रोज़गार से अपनी आजीविका के लिए खरीदा गया। अधिनियम का स्पष्टीकरण ऐसे खरीदारों को परिभाषा में रखता है, "
                        "पर आपको दिखाना पड़ सकता है कि सामान केवल उसी उद्देश्य से इस्तेमाल हुआ।")
            conf, label = "arguable", "argument"
        elif purpose == "personal":
            extra_en = "You told us it was for personal or household use, so you would ordinarily fall within the definition."
            extra_hi = "आपने बताया कि यह निजी या घरेलू उपयोग के लिए था, इसलिए आप सामान्यतः परिभाषा के भीतर आएँगे।"
            conf, label = "clear", "statutory"
        else:
            extra_en = ("This assumes you bought it for personal or household use. If it was bought for resale or business, consumer law "
                        "may not apply — tell NyayaSetu on the Case Summary page.")
            extra_hi = ("यह मानकर चलता है कि आपने इसे निजी या घरेलू उपयोग के लिए खरीदा। अगर यह दोबारा बेचने या व्यापार के लिए था, तो उपभोक्ता कानून "
                        "शायद लागू न हो — केस सारांश पेज पर बताएँ।")
            conf, label = "clear", "statutory"
        how = _L(lang, f"You paid {(f['amount'] + ' for') if f['amount'] else 'for'} {f['product']} through an online platform. Online purchases are expressly included "
                       f"in the definition of 'consumer'. {extra_en}",
                 f"आपने ऑनलाइन प्लेटफ़ॉर्म से {f['product']} {('के लिए ' + f['amount'] + ' चुकाए') if f['amount'] else 'खरीदा'}। ऑनलाइन खरीद "
                 f"'उपभोक्ता' की परिभाषा में स्पष्ट रूप से शामिल है। {extra_hi}")
        return self._issue("consumer_status", "You are likely a 'consumer' under the Act", "आप संभवतः अधिनियम के तहत 'उपभोक्ता' हैं",
                           label, conf, ["CPA_2_7", "CPA_2_9"], how, ["invoice", "payment_proof"],
                           _L(lang, "Keep the invoice and payment record — they prove you bought and paid.",
                              "बिल और भुगतान का रिकॉर्ड संभाल कर रखें — इनसे खरीद और भुगतान साबित होता है।"), lang, case)

    def _defect(self, case, f, lang):
        cat = case["dispute"]["category"]
        detail = (case.get("issue_details") or "").strip()
        detail_q = f" (“{detail[:160]}{'…' if len(detail) > 160 else ''}”)" if detail else ""
        if cat == "damaged_on_delivery":
            how = _L(lang,
                     f"You say {f['product']} arrived damaged{detail_q}. Damage of that kind would ordinarily be a 'fault, imperfection or "
                     "shortcoming in quality' — a defect — and a complaint can allege that goods you bought suffer from a defect. The main "
                     "question will be proof that the damage existed at delivery and was not caused afterwards; photos or an unboxing video "
                     "taken at delivery, and the date you reported it, are the strongest evidence.",
                     f"आपके अनुसार {f['product']} क्षतिग्रस्त हालत में पहुँचा{detail_q}। ऐसी क्षति सामान्यतः 'गुणवत्ता में खराबी या कमी' — यानी दोष — "
                     "मानी जाएगी, और शिकायत में कहा जा सकता है कि खरीदे गए सामान में दोष है। मुख्य प्रश्न यह होगा कि क्षति डिलीवरी के समय मौजूद थी, बाद में "
                     "नहीं हुई — डिलीवरी के समय ली गई फोटो या अनबॉक्सिंग वीडियो, और शिकायत की तारीख सबसे मज़बूत सबूत हैं।")
            wanted = ["product_photos", "unboxing_video", "invoice", "complaint_reference"]
        else:
            how = _L(lang,
                     f"You describe a defect in {f['product']}{detail_q}. A fault that appears shortly after delivery in normal use may be "
                     "argued to be a defect in quality. You will need to show the fault is in the product and not caused by misuse — a "
                     "technician or service-centre report is the most useful evidence. Note: the Act's separate 'product liability' chapter "
                     "deals with harm a product causes beyond itself (injury, damage to other property); harm to the product itself is "
                     "excluded, so for a faulty appliance alone the ordinary defect complaint is usually the relevant route.",
                     f"आप {f['product']} में दोष बता रहे हैं{detail_q}। सामान्य उपयोग में डिलीवरी के तुरंत बाद आई खराबी को गुणवत्ता का दोष कहा जा सकता है। "
                     "आपको दिखाना होगा कि खराबी उत्पाद में है, गलत उपयोग से नहीं — तकनीशियन या सर्विस सेंटर की रिपोर्ट सबसे उपयोगी सबूत है। ध्यान दें: "
                     "अधिनियम का अलग 'उत्पाद दायित्व' अध्याय उस नुकसान के बारे में है जो उत्पाद अपने अलावा पहुँचाता है (चोट, अन्य संपत्ति को नुकसान); "
                     "उत्पाद को स्वयं हुआ नुकसान इसमें शामिल नहीं, इसलिए केवल खराब उपकरण के लिए सामान्य दोष वाली शिकायत ही आमतौर पर उपयुक्त रास्ता है।")
            wanted = ["technician_report", "warranty_card", "invoice", "product_photos", "complaint_reference"]
        has_key = any(e in case.get("evidence", []) for e in wanted[:2])
        sources = ["CPA_2_10", "CPA_2_6"] + (["CPA_PRODUCT_LIABILITY"] if cat == "defective_product" else [])
        return self._issue("defect", "The product appears to have a 'defect'", "उत्पाद में 'दोष' प्रतीत होता है", "argument",
                           "evidence" if not has_key else "arguable", sources, how, wanted,
                           _L(lang, "Do not discard or repair the product yourself; keep it in its current condition with all packaging and photos.",
                              "उत्पाद को फेंकें या स्वयं ठीक न कराएँ; पैकेजिंग और फोटो सहित उसे इसी हालत में रखें।"), lang, case,
                           [] if has_key else [_L(lang, "Key evidence of the defect is not yet listed in your case.",
                                                  "दोष का मुख्य सबूत अभी आपके मामले में दर्ज नहीं है।")])

    def _ecom_takeback(self, case, f, lang):
        cat = case["dispute"]["category"]
        resp = case.get("seller_response") or ""
        refused = case["flags"].get("refused_explicitly")
        ground_en = {"damaged_on_delivery": "defective", "defective_product": "defective",
                     "misleading_description": "not of the characteristics or features as advertised or as agreed to", "non_delivery": "delivered late (or not at all)"}[cat]
        ground_hi = {"damaged_on_delivery": "दोषपूर्ण", "defective_product": "दोषपूर्ण",
                     "misleading_description": "विज्ञापित या तय की गई विशेषताओं के अनुसार नहीं", "non_delivery": "देर से (या बिल्कुल नहीं) पहुँचाया गया"}[cat]
        if refused:
            pos_en = f"The seller's response{(' (“' + resp[:140] + '”)') if resp else ''} appears to be a refusal, which would conflict with this duty if the goods are shown to be {ground_en}."
            pos_hi = f"विक्रेता का उत्तर{(' (“' + resp[:140] + '”)') if resp else ''} इनकार जैसा लगता है, जो इस कर्तव्य के विरुद्ध होगा अगर सामान {ground_hi} साबित होता है।"
            conf = "arguable"
        elif resp:
            pos_en = (f"The seller has not clearly refused but has not resolved it (“{resp[:140]}”). The Rule prohibits refusal; whether a long "
                      "delay amounts to refusal depends on the facts.")
            pos_hi = f"विक्रेता ने साफ़ इनकार नहीं किया पर समाधान भी नहीं किया (“{resp[:140]}”)। नियम इनकार को रोकता है; लंबी देरी इनकार मानी जाएगी या नहीं, यह तथ्यों पर निर्भर है।"
            conf = "arguable"
        else:
            pos_en = "You have not yet recorded how the seller responded. If they refuse, this Rule is directly relevant."
            pos_hi = "आपने अभी दर्ज नहीं किया कि विक्रेता ने क्या उत्तर दिया। अगर वे इनकार करते हैं, तो यह नियम सीधे लागू होता है।"
            conf = "arguable"
        if cat == "non_delivery":
            pos_en += (" For non-delivery, the Rule covers goods 'delivered late from the stated delivery schedule' unless the delay was due to "
                       "force majeure; goods never received are, at the least, not delivered on schedule.")
            pos_hi += " डिलीवरी न होने पर, नियम 'निर्धारित समय से देर से डिलीवरी' को कवर करता है जब तक देरी अप्रत्याशित परिस्थिति से न हो; जो सामान मिला ही नहीं, वह कम से कम समय पर डिलीवर नहीं हुआ।"
        how = _L(lang,
                 f"A seller on an online marketplace must not refuse to take back goods or refund the price if the goods are {ground_en}. "
                 f"{pos_en} If {f['platform']} itself sold the goods from its own stock (check the invoice), the parallel duty in Rule 7(4) applies instead.",
                 f"ऑनलाइन मार्केटप्लेस का विक्रेता सामान वापस लेने या कीमत लौटाने से इनकार नहीं कर सकता अगर सामान {ground_hi} है। {pos_hi} "
                 f"अगर {f['platform']} ने स्वयं अपने स्टॉक से सामान बेचा (बिल देखें), तो उसकी जगह नियम 7(4) का समान कर्तव्य लागू होता है।")
        wanted = {"damaged_on_delivery": ["product_photos", "unboxing_video", "complaint_reference", "chat_transcripts"],
                  "defective_product": ["technician_report", "complaint_reference", "emails", "chat_transcripts"],
                  "misleading_description": ["listing_screenshot", "complaint_reference", "chat_transcripts"],
                  "non_delivery": ["tracking_screenshot", "order_screenshot", "complaint_reference"]}[cat]
        return self._issue("ecom_takeback", "Online sellers must not refuse return or refund in these situations",
                           "ऑनलाइन विक्रेता इन स्थितियों में वापसी या रिफंड से इनकार नहीं कर सकते", "statutory", conf,
                           ["ECOM_R6_3", "ECOM_R7_4", "ECOM_R2"], how, wanted,
                           _L(lang, "Ask the seller and platform in writing to take the product back and refund, quoting your order ID, and keep their written reply.",
                              "ऑर्डर आईडी लिखते हुए विक्रेता और प्लेटफ़ॉर्म से लिखित में उत्पाद वापस लेने और रिफंड का अनुरोध करें, और उनका लिखित उत्तर संभालें।"),
                           lang, case)

    def _utp_refusal(self, case, f, lang):
        days = f["days"]
        refused = case["flags"].get("refused_explicitly")
        wants_refund = "refund" in case.get("desired_resolution", []) or bool(
            re.search(r"refund|return|take (it )?back|money back|रिफंड|वापस", " ".join(case.get("steps_taken", [])) + " " + (case.get("narrative") or ""), re.I))
        if not wants_refund:
            how = _L(lang, "This clause is about refusing to take back defective goods and refund the price (within the bill's period, or 30 days). "
                           "You have asked for a replacement or repair rather than a refund, so NyayaSetu does not treat this clause as applying yet. "
                           "If you ask to return the product for a refund and that is refused, it may become relevant.",
                     "यह खंड दोषपूर्ण सामान वापस लेकर कीमत लौटाने से इनकार (बिल की अवधि या 30 दिन में) के बारे में है। आपने रिफंड के बजाय बदलाव या मरम्मत माँगी है, "
                     "इसलिए NyayaSetu अभी इस खंड को लागू नहीं मानता। अगर आप रिफंड के लिए उत्पाद लौटाना चाहें और इनकार हो, तो यह प्रासंगिक हो सकता है।")
            return self._issue("utp_refusal", "Is this an 'unfair trade practice'?", "क्या यह 'अनुचित व्यापार व्यवहार' है?", "argument", "not_yet",
                               ["CPA_2_47_VIII"], how, ["invoice", "complaint_reference"],
                               _L(lang, "Decide whether you want a refund or a replacement, and ask for it in writing.",
                                  "तय करें कि आप रिफंड चाहते हैं या बदलाव, और लिखित में माँगें।"), lang, case,
                               [_L(lang, "Refusal of a refund has not been shown, so the unfair-trade-practice clause is not established.",
                                   "रिफंड से इनकार नहीं दिखाया गया, इसलिए अनुचित व्यापार व्यवहार खंड स्थापित नहीं है।")])
        if refused:
            how = _L(lang, "The Act lists 'refusing ... to take back or withdraw defective goods ... and to refund' within the period on the bill "
                           "(or 30 days if none is stated) as an unfair trade practice. Because the seller appears to have refused, you may argue "
                           "this clause applies — but only if the goods are shown to be defective. It is an argument, not an established finding.",
                     "अधिनियम बिल में लिखी अवधि (या अवधि न हो तो 30 दिन) में 'दोषपूर्ण सामान वापस लेने ... और रिफंड करने से इनकार' को अनुचित व्यापार व्यवहार "
                     "मानता है। चूँकि विक्रेता ने इनकार किया प्रतीत होता है, आप तर्क दे सकते हैं कि यह खंड लागू होता है — पर केवल तब जब सामान दोषपूर्ण साबित हो। "
                     "यह तर्क है, स्थापित निष्कर्ष नहीं।")
            conf = "arguable"
            unc = []
        elif days is not None and days < 30:
            how = _L(lang, f"You first raised this about {days} days ago ({f['complaint_on']}). This clause concerns refusing to take back defective goods "
                           "and refund within the period on the bill, or within 30 days if the bill states none. Unless your bill states a shorter period, "
                           "that 30-day period may not have passed yet, so NyayaSetu does NOT treat the delay as an unfair trade practice at this stage. "
                           "How the 30 days are counted can depend on the facts.",
                     f"आपने लगभग {days} दिन पहले ({f['complaint_on']}) यह मुद्दा उठाया। यह खंड दोषपूर्ण सामान को बिल में लिखी अवधि, या अवधि न होने पर 30 दिन के "
                     "भीतर वापस लेने और रिफंड करने से इनकार के बारे में है। जब तक आपके बिल में कम अवधि न लिखी हो, 30 दिन शायद अभी पूरे नहीं हुए, इसलिए NyayaSetu "
                     "इस देरी को अभी अनुचित व्यापार व्यवहार नहीं मानता। 30 दिन कैसे गिने जाएँ, यह तथ्यों पर निर्भर हो सकता है।")
            conf = "not_yet"
            unc = [_L(lang, "Too early to say the 30-day 'refusal' clause is breached.", "30 दिन वाले 'इनकार' खंड का उल्लंघन कहना अभी जल्दी है।")]
        elif days is not None:
            how = _L(lang, f"About {days} days have passed since you raised it ({f['complaint_on']}). If the goods are defective and the bill states no shorter "
                           "period, a continued failure to take them back and refund within 30 days may be argued to fall within this clause. Whether "
                           "a delay (rather than an express refusal) counts as 'refusing' is fact-dependent.",
                     f"आपके मुद्दा उठाने के बाद लगभग {days} दिन बीत चुके हैं ({f['complaint_on']})। अगर सामान दोषपूर्ण है और बिल में कम अवधि नहीं लिखी, तो 30 दिन में "
                     "वापस लेकर रिफंड न करना इस खंड के अंतर्गत तर्क के रूप में रखा जा सकता है। देरी (स्पष्ट इनकार के बजाय) 'इनकार' मानी जाएगी या नहीं, यह तथ्यों पर निर्भर है।")
            conf = "arguable"
            unc = [_L(lang, "Whether a delay amounts to 'refusing' under Section 2(47)(viii).", "क्या देरी धारा 2(47)(viii) के तहत 'इनकार' मानी जाएगी।")]
        else:
            how = _L(lang, "This clause applies only if the seller refuses (within the bill's period, or 30 days) to take back defective goods and refund. "
                           "Add the date you first asked for a return/refund so NyayaSetu can check the timing.",
                     "यह खंड तभी लागू होता है जब विक्रेता (बिल की अवधि या 30 दिन में) दोषपूर्ण सामान वापस लेने और रिफंड करने से इनकार करे। समय की जाँच के "
                     "लिए वह तारीख जोड़ें जब आपने पहली बार वापसी/रिफंड माँगा।")
            conf = "not_yet"
            unc = [_L(lang, "Date of your first return/refund request is missing.", "पहली वापसी/रिफंड अनुरोध की तारीख अनुपलब्ध है।")]
        return self._issue("utp_refusal", "Is this an 'unfair trade practice'?", "क्या यह 'अनुचित व्यापार व्यवहार' है?", "argument", conf,
                           ["CPA_2_47_VIII"], how, ["invoice", "complaint_reference", "emails", "chat_transcripts"],
                           _L(lang, "Check whether your invoice states a return/refund period, and keep every dated message showing what you asked for and when.",
                              "देखें कि आपके बिल में वापसी/रिफंड की अवधि लिखी है या नहीं, और हर दिनांकित संदेश संभालें जिससे पता चले कि आपने क्या और कब माँगा।"),
                           lang, case, unc)

    def _product_liability(self, case, f, lang):
        how = _L(lang, "You mentioned harm beyond the product itself (for example injury, fire or damage to other property). The Act allows a product "
                       "liability action against the manufacturer or seller for harm caused by a defective product, on grounds such as a manufacturing "
                       "or design defect or inadequate warnings. Claims involving injury are serious and fact-heavy — consult a lawyer, and seek medical "
                       "help and keep medical records if anyone was hurt.",
                 "आपने उत्पाद के अलावा नुकसान (जैसे चोट, आग, या अन्य संपत्ति को नुकसान) का उल्लेख किया। अधिनियम दोषपूर्ण उत्पाद से हुए नुकसान के लिए "
                 "निर्माता या विक्रेता के विरुद्ध उत्पाद दायित्व कार्रवाई की अनुमति देता है (जैसे निर्माण या डिज़ाइन दोष, अपर्याप्त चेतावनी)। चोट वाले दावे गंभीर "
                 "और तथ्यों पर निर्भर होते हैं — वकील से सलाह लें, और अगर किसी को चोट लगी है तो चिकित्सा सहायता लें और रिकॉर्ड रखें।")
        return self._issue("product_liability", "Harm caused by the product: product liability", "उत्पाद से हुआ नुकसान: उत्पाद दायित्व",
                           "argument", "uncertain", ["CPA_PRODUCT_LIABILITY"], how, ["product_photos", "invoice", "technician_report"],
                           _L(lang, "Speak to a lawyer before filing; preserve the product and all medical or repair records.",
                              "दर्ज करने से पहले वकील से बात करें; उत्पाद और सभी चिकित्सा या मरम्मत रिकॉर्ड सुरक्षित रखें।"), lang, case,
                           [_L(lang, "Product-liability claims need expert evidence and legal advice.", "उत्पाद दायित्व के दावों में विशेषज्ञ सबूत और कानूनी सलाह चाहिए।")])

    def _non_delivery(self, case, f, lang):
        detail = case.get("issue_details") or ""
        otp_risk = bool(re.search(r"\botp\b.*(shared|gave|told|दिया|बताया)|(shared|gave).{0,20}\botp\b|someone (received|took)|पड़ोसी|किसी ने (लिया|ले)", detail, re.I))
        how = _L(lang,
                 f"You paid {f['amount'] or 'for the order'} but say you never received {f['product']}, although the app shows it as delivered. "
                 "A failure to deliver goods that were paid for may be argued to be a 'deficiency' in the delivery service, and you can complain "
                 "about it. The disputed fact will be whether delivery actually happened: the platform holds the proof-of-delivery records "
                 "(delivery photo, OTP log, location, signature). Ask for them in writing."
                 + (" You mentioned an OTP being shared or someone else receiving a parcel — that makes the position harder and fact-dependent." if otp_risk else ""),
                 f"आपने {f['amount'] or 'ऑर्डर के लिए'} भुगतान किया पर आपके अनुसार {f['product']} मिला नहीं, जबकि ऐप पर डिलीवर दिखाया गया है। भुगतान किए गए "
                 "सामान की डिलीवरी न होना डिलीवरी सेवा में 'कमी' के रूप में तर्क दिया जा सकता है, और आप इसकी शिकायत कर सकते हैं। विवादित तथ्य यह होगा कि डिलीवरी "
                 "वास्तव में हुई या नहीं: डिलीवरी के प्रमाण (फोटो, OTP लॉग, लोकेशन, हस्ताक्षर) प्लेटफ़ॉर्म के पास होते हैं। उन्हें लिखित में माँगें।"
                 + (" आपने OTP साझा होने या किसी और के पार्सल लेने का उल्लेख किया — इससे स्थिति कठिन और तथ्यों पर निर्भर हो जाती है।" if otp_risk else ""))
        unc = [_L(lang, "The platform's records say 'delivered'; the outcome depends on delivery evidence.",
                  "प्लेटफ़ॉर्म के रिकॉर्ड में 'डिलीवर' लिखा है; परिणाम डिलीवरी के सबूत पर निर्भर है।")]
        return self._issue("non_delivery", "Paid but not delivered: possible deficiency in service", "भुगतान हुआ पर डिलीवरी नहीं: सेवा में संभावित कमी",
                           "argument", "evidence", ["CPA_2_11", "CPA_2_6"], how,
                           ["payment_proof", "tracking_screenshot", "order_screenshot", "complaint_reference"],
                           _L(lang, "Write to the platform asking for proof of delivery and a refund; note that you did not receive the parcel.",
                              "प्लेटफ़ॉर्म को लिखकर डिलीवरी का प्रमाण और रिफंड माँगें; स्पष्ट लिखें कि आपको पार्सल नहीं मिला।"), lang, case, unc)

    def _misleading(self, case, f, lang):
        detail = (case.get("issue_details") or "").strip()
        has_listing = "listing_screenshot" in case.get("evidence", [])
        how = _L(lang,
                 f"You say the listing or advertisement claimed something {f['product']} does not have"
                 + (f" (“{detail[:180]}{'…' if len(detail) > 180 else ''}”)" if detail else "") + ". An advertisement that falsely describes a "
                 "product, or a statement that falsely represents goods to be of a particular standard or model, can be a misleading advertisement "
                 "and an unfair trade practice. Your claim depends on proving exactly what was claimed at the time you bought: sellers can edit "
                 "listings later, so a dated screenshot of the original listing is critical."
                 + ("" if has_listing else " You have not yet listed a screenshot of the listing — try to recover it (order page, app history, archived page, emails)."),
                 f"आपके अनुसार लिस्टिंग या विज्ञापन में ऐसा दावा था जो {f['product']} में नहीं है"
                 + (f" (“{detail[:180]}{'…' if len(detail) > 180 else ''}”)" if detail else "") + "। उत्पाद का झूठा वर्णन करने वाला विज्ञापन, या सामान को झूठे "
                 "तौर पर किसी विशेष मानक या मॉडल का बताने वाला बयान, भ्रामक विज्ञापन और अनुचित व्यापार व्यवहार हो सकता है। आपका दावा इस पर निर्भर है कि खरीद के समय "
                 "ठीक-ठीक क्या दावा किया गया था: विक्रेता बाद में लिस्टिंग बदल सकते हैं, इसलिए मूल लिस्टिंग का दिनांकित स्क्रीनशॉट बहुत ज़रूरी है।"
                 + ("" if has_listing else " आपने अभी लिस्टिंग का स्क्रीनशॉट दर्ज नहीं किया — उसे खोजने का प्रयास करें (ऑर्डर पेज, ऐप इतिहास, ईमेल)।"))
        return self._issue("misleading", "The product may not match what was advertised", "उत्पाद शायद विज्ञापन के अनुसार नहीं है",
                           "argument", "evidence" if not has_listing else "arguable", ["CPA_2_28", "CPA_2_47_I_A", "ECOM_R6_4"], how,
                           ["listing_screenshot", "product_photos", "invoice"],
                           _L(lang, "Photograph the product and its box/label showing the missing feature, next to your screenshot of the listing.",
                              "उत्पाद और उसके डिब्बे/लेबल की फोटो लें जिसमें गायब फीचर दिखे, साथ में लिस्टिंग का स्क्रीनशॉट रखें।"), lang, case,
                           [] if has_listing else [_L(lang, "Without a copy of the original listing the claim may be hard to prove.",
                                                      "मूल लिस्टिंग की प्रति के बिना दावा साबित करना कठिन हो सकता है।")])

    def _regulator_route(self, case, f, lang):
        how = _L(lang, "If the same misleading listing is likely to affect other buyers too, a complaint about a misleading advertisement can also be "
                       "sent in writing or electronically to the District Collector, the regional Commissioner or the Central Consumer Protection "
                       "Authority. This is a regulatory route that can stop the practice; it does not by itself get your money back. The CCPA has also "
                       "issued 2022 guidelines on misleading advertisements (NyayaSetu has not reviewed their full text).",
                 "अगर वही भ्रामक लिस्टिंग अन्य खरीदारों को भी प्रभावित कर सकती है, तो भ्रामक विज्ञापन की शिकायत ज़िला कलेक्टर, क्षेत्रीय आयुक्त या केंद्रीय उपभोक्ता "
                 "संरक्षण प्राधिकरण को लिखित या इलेक्ट्रॉनिक रूप से भी भेजी जा सकती है। यह नियामक रास्ता व्यवहार को रोक सकता है; इससे आपका पैसा अपने आप वापस "
                 "नहीं मिलता। CCPA ने 2022 में भ्रामक विज्ञापनों पर दिशानिर्देश भी जारी किए हैं (NyayaSetu ने उनका पूरा पाठ नहीं देखा)।")
        return self._issue("regulator", "Reporting a misleading advertisement to the authorities", "भ्रामक विज्ञापन की अधिकारियों को शिकायत",
                           "procedure", "info", ["CPA_17", "CCPA_ADS_GUIDELINES_2022"], how, ["listing_screenshot"],
                           _L(lang, "Optional: after your own complaint, consider reporting the listing to the authorities.",
                              "वैकल्पिक: अपनी शिकायत के बाद, लिस्टिंग की अधिकारियों को सूचना देने पर विचार करें।"), lang, case)

    def _excess_charge(self, case, f, lang):
        t = case["transaction"]
        paid = format_inr(t.get("amount_paid")) if t.get("amount_paid") else _L(lang, "[correct price not given]", "[सही कीमत नहीं बताई]")
        charged = format_inr(t.get("charged_amount")) if t.get("charged_amount") else _L(lang, "[amount charged not given]", "[कटी राशि नहीं बताई]")
        how = _L(lang, f"You say the correct price was {paid} but you were charged {charged}. A complaint can allege that a trader charged more than the "
                       "price agreed between the parties or displayed. But a double debit can also be a payment-processing error by the bank or payment "
                       "app rather than an overcharge by the platform — which one it is affects who is responsible and where to complain.",
                 f"आपके अनुसार सही कीमत {paid} थी पर आपसे {charged} लिए गए। शिकायत में कहा जा सकता है कि व्यापारी ने पक्षों के बीच तय या प्रदर्शित कीमत से "
                 "अधिक लिया। पर दोहरी कटौती बैंक या भुगतान ऐप की प्रोसेसिंग त्रुटि भी हो सकती है, न कि प्लेटफ़ॉर्म का अधिक शुल्क — यह किसकी ज़िम्मेदारी है और "
                 "शिकायत कहाँ करें, यह इसी पर निर्भर करता है।")
        return self._issue("excess_charge", "Charged more than the agreed price", "तय कीमत से अधिक कटौती", "argument", "arguable",
                           ["CPA_2_6"], how, ["payment_proof", "invoice", "order_screenshot"],
                           _L(lang, "Download your bank/UPI statement showing both debits, and the order invoice showing the correct total.",
                              "दोनों कटौतियाँ दिखाने वाला बैंक/UPI विवरण और सही कुल राशि दिखाने वाला ऑर्डर बिल डाउनलोड करें।"), lang, case,
                           [_L(lang, "Whether the extra debit is the platform's charge or a payment-system error.", "अतिरिक्त कटौती प्लेटफ़ॉर्म का शुल्क है या भुगतान प्रणाली की त्रुटि।")])

    def _refund_rule(self, case, f, lang):
        how = _L(lang, "If the platform has accepted that a refund is due, the E-Commerce Rules require it to pay accepted refund requests within a "
                       "reasonable period of time (or as prescribed by the RBI or other law). The Rule does not fix a number of days, so NyayaSetu "
                       "cannot tell you the refund is 'overdue' by a specific date. A written acceptance or refund-approval message is the key evidence.",
                 "अगर प्लेटफ़ॉर्म ने मान लिया है कि रिफंड बनता है, तो ई-कॉमर्स नियमों के अनुसार उसे स्वीकृत रिफंड अनुरोधों का भुगतान उचित समय के भीतर (या RBI/अन्य "
                 "कानून के अनुसार) करना होगा। नियम में दिनों की संख्या तय नहीं है, इसलिए NyayaSetu किसी निश्चित तारीख से रिफंड को 'बकाया' नहीं कह सकता। लिखित "
                 "स्वीकृति या रिफंड-अनुमोदन का संदेश मुख्य सबूत है।")
        unc = [_L(lang, "Whether your refund request was formally 'accepted' by the platform.", "क्या प्लेटफ़ॉर्म ने आपका रिफंड अनुरोध औपचारिक रूप से 'स्वीकार' किया।")]
        return self._issue("refund_rule", "Accepted refunds must be paid within a reasonable time", "स्वीकृत रिफंड उचित समय में चुकाने होंगे",
                           "statutory", "arguable", ["ECOM_R4_10"], how, ["emails", "chat_transcripts", "complaint_reference", "payment_proof"],
                           _L(lang, "Ask the platform in writing to confirm the refund status, amount and date, and keep the reply.",
                              "प्लेटफ़ॉर्म से लिखित में रिफंड की स्थिति, राशि और तारीख की पुष्टि माँगें, और उत्तर संभालें।"), lang, case, unc)

    def _deficiency_support(self, case, f, lang):
        rep = case["flags"].get("repeated_contact")
        how = _L(lang, ("You contacted support repeatedly without a satisfactory answer. " if rep else "")
                 + "A persistent failure to resolve a legitimate complaint — for example not reversing an amount that should not have been taken — may "
                   "be argued to be a 'deficiency' in service. Whether it is depends on what was promised, what was done and how long it took.",
                 ("आपने बार-बार सहायता से संपर्क किया पर संतोषजनक उत्तर नहीं मिला। " if rep else "")
                 + "किसी वैध शिकायत का लगातार समाधान न करना — जैसे गलत ली गई राशि वापस न करना — सेवा में 'कमी' के रूप में तर्क दिया जा सकता है। यह कमी है या नहीं, "
                   "यह इस पर निर्भर है कि क्या वादा किया गया, क्या किया गया और कितना समय लगा।")
        return self._issue("deficiency_support", "Unresolved complaints: possible deficiency in service", "अनसुलझी शिकायतें: सेवा में संभावित कमी",
                           "argument", "arguable", ["CPA_2_11"], how, ["complaint_reference", "chat_transcripts", "emails", "call_records"],
                           _L(lang, "Make a list of every contact: date, channel, ticket number and what you were told.",
                              "हर संपर्क की सूची बनाएँ: तारीख, माध्यम, टिकट नंबर और आपको क्या बताया गया।"), lang, case)

    def _payment_route(self, case, f, lang):
        e = self.kb.get("RBI_IOS_2026")
        how = _L(lang, "If the extra amount was debited by your bank, card or UPI app (for example a duplicate debit that the merchant never received), the "
                       "payment provider's own grievance process applies first, and the RBI runs an ombudsman scheme for unresolved complaints. News "
                       "reports say a revised RBI Integrated Ombudsman Scheme took effect on 1 July 2026. NyayaSetu does not cover banking disputes and has "
                       "not verified that scheme's official text — check rbi.org.in before relying on it.",
                 "अगर अतिरिक्त राशि आपके बैंक, कार्ड या UPI ऐप ने काटी (जैसे दोहरी कटौती जो व्यापारी तक पहुँची ही नहीं), तो पहले भुगतान प्रदाता की अपनी शिकायत "
                 "प्रक्रिया लागू होती है, और अनसुलझी शिकायतों के लिए RBI की लोकपाल योजना है। समाचारों के अनुसार संशोधित RBI एकीकृत लोकपाल योजना 1 जुलाई 2026 से "
                 "लागू है। NyayaSetu बैंकिंग विवाद कवर नहीं करता और उस योजना का आधिकारिक पाठ सत्यापित नहीं किया — भरोसा करने से पहले rbi.org.in देखें।")
        return self._issue("payment_route", "If it is a payment-system error: your bank's route", "अगर यह भुगतान प्रणाली की त्रुटि है: बैंक का रास्ता",
                           "notice", "info", [e["id"]] if e else [], how, ["payment_proof"],
                           _L(lang, "Also raise a dispute with your bank or UPI app for the duplicate debit and keep its reference number.",
                              "दोहरी कटौती के लिए अपने बैंक या UPI ऐप में भी शिकायत करें और उसकी संदर्भ संख्या रखें।"), lang, case,
                           [_L(lang, "Banking remedies are outside NyayaSetu's verified scope.", "बैंकिंग उपाय NyayaSetu के सत्यापित दायरे से बाहर हैं।")])

    def _unknown_category(self, case, f, lang):
        how = _L(lang, "NyayaSetu could not identify the type of problem from the information given, so it cannot point to specific provisions yet. "
                       "Add what went wrong (damaged, defective, not delivered, not as advertised, wrong charge, refund pending) on the Case Summary page.",
                 "दी गई जानकारी से NyayaSetu समस्या का प्रकार नहीं पहचान सका, इसलिए अभी विशेष प्रावधान नहीं बता सकता। केस सारांश पेज पर बताएँ कि क्या गलत हुआ "
                 "(क्षतिग्रस्त, दोषपूर्ण, डिलीवरी नहीं, विज्ञापन के अनुसार नहीं, गलत कटौती, रिफंड लंबित)।")
        return self._issue("unknown", "Type of problem not yet clear", "समस्या का प्रकार अभी स्पष्ट नहीं", "practical", "uncertain",
                           ["CPA_2_6"], how, ["invoice", "payment_proof"],
                           _L(lang, "Describe the problem in more detail on the Case Summary page.", "केस सारांश पेज पर समस्या का विस्तार से वर्णन करें।"),
                           lang, case, [_L(lang, "Dispute type unknown.", "विवाद का प्रकार अज्ञात।")])

    def _grievance_officer(self, case, f, lang):
        days = f["days"]
        if case["flags"].get("no_complaint_yet"):
            status_en, status_hi = "You have not yet complained in writing — this is the first step.", "आपने अभी तक लिखित शिकायत नहीं की — यह पहला कदम है।"
        elif days is not None and days > 31:
            status_en = (f"You complained about {days} days ago. If that complaint reached the platform's grievance mechanism, the one-month period for "
                         "redressal has passed — you can point this out when you escalate.")
            status_hi = f"आपने लगभग {days} दिन पहले शिकायत की। अगर वह शिकायत प्लेटफ़ॉर्म की शिकायत प्रणाली तक पहुँची, तो निवारण की एक महीने की अवधि बीत चुकी है — आगे शिकायत करते समय इसका उल्लेख करें।"
        elif days is not None:
            status_en = (f"You complained about {days} days ago. The one-month redressal period for the grievance officer may still be running; this is a "
                         "duty on the platform, not a waiting period imposed on you.")
            status_hi = f"आपने लगभग {days} दिन पहले शिकायत की। शिकायत अधिकारी की एक महीने की निवारण अवधि शायद अभी चल रही है; यह प्लेटफ़ॉर्म का कर्तव्य है, आप पर लगाई गई प्रतीक्षा अवधि नहीं।"
        else:
            status_en, status_hi = "Add the date of your complaint so NyayaSetu can check the timing.", "समय की जाँच के लिए अपनी शिकायत की तारीख जोड़ें।"
        how = _L(lang, f"{f['platform']} must have a grievance officer whose name and contact details are displayed on the platform, must acknowledge a "
                       f"complaint within 48 hours and redress it within one month. If it is a marketplace (third-party sellers), it must also give you a ticket "
                       f"number to track the complaint. {status_en}",
                 f"{f['platform']} में एक शिकायत अधिकारी होना ज़रूरी है जिसका नाम और संपर्क प्लेटफ़ॉर्म पर दिखाया गया हो; उसे 48 घंटे में शिकायत की पावती देनी होगी, "
                 f"एक महीने में निवारण करना होगा। अगर यह मार्केटप्लेस है (तीसरे पक्ष के विक्रेता), तो उसे शिकायत ट्रैक करने के लिए टिकट नंबर भी देना होगा। {status_hi}")
        return self._issue("grievance_officer", "Escalate to the platform's grievance officer", "प्लेटफ़ॉर्म के शिकायत अधिकारी तक शिकायत ले जाएँ",
                           "statutory", "clear", ["ECOM_R4_GRIEVANCE", "ECOM_R5_3"], how, ["complaint_reference", "emails"],
                           _L(lang, "Find the grievance officer's details on the platform (usually in the help or legal pages) and send them the formal complaint NyayaSetu drafts.",
                              "प्लेटफ़ॉर्म पर शिकायत अधिकारी का विवरण खोजें (आमतौर पर सहायता या कानूनी पेज में) और NyayaSetu द्वारा तैयार औपचारिक शिकायत उन्हें भेजें।"),
                           lang, case)

    def _forum(self, case, f, lang, today):
        fl = case["flags"]
        city = case["consumer"].get("city") or _L(lang, "[your district]", "[आपका ज़िला]")
        band = fl.get("value_band")
        band_en = {"district": "District Commission (value paid up to ₹50 lakh)", "state": "State Commission", "national": "National Commission",
                   "unknown": "the Commission matching the value you paid"}[band]
        band_hi = {"district": "ज़िला आयोग (चुकाई गई कीमत ₹50 लाख तक)", "state": "राज्य आयोग", "national": "राष्ट्रीय आयोग",
                   "unknown": "चुकाई गई कीमत के अनुसार उपयुक्त आयोग"}[band]
        fee_en = "No filing fee applies for value up to ₹5 lakh (check e-Jagriti for the current fee)." if fl.get("fee_nil") else "A filing fee may apply — check e-Jagriti."
        fee_hi = "₹5 लाख तक की कीमत के लिए कोई फ़ाइलिंग शुल्क नहीं (वर्तमान शुल्क ई-जागृति पर जाँचें)।" if fl.get("fee_nil") else "फ़ाइलिंग शुल्क लग सकता है — ई-जागृति पर जाँचें।"
        age = fl.get("days_since_earliest_event")
        if fl.get("limitation_expired_likely"):
            lim_en = (f"Your earliest relevant date is about {age // 30} months ago. The 2-year limit from the cause of action may already have passed; a "
                      "late complaint is admitted only if the Commission accepts there was sufficient cause for the delay. Get legal advice urgently.")
            lim_hi = (f"आपकी सबसे पुरानी संबंधित तारीख लगभग {age // 30} महीने पहले की है। विवाद के कारण से 2 साल की सीमा शायद बीत चुकी है; देरी से की गई शिकायत तभी "
                      "स्वीकार होती है जब आयोग देरी का पर्याप्त कारण माने। तुरंत कानूनी सलाह लें।")
            conf = "uncertain"
        elif fl.get("limitation_risk"):
            lim_en = "You are close to the 2-year limit from the cause of action. Act quickly and get legal advice on when the period started."
            lim_hi = "आप विवाद के कारण से 2 साल की सीमा के क़रीब हैं। जल्दी करें और कानूनी सलाह लें कि अवधि कब शुरू हुई।"
            conf = "uncertain"
        elif age is not None:
            lim_en = f"Your earliest relevant date is about {max(age, 0)} days ago, well within the 2-year limit (the exact start of the cause of action can be a legal question)."
            lim_hi = f"आपकी सबसे पुरानी संबंधित तारीख लगभग {max(age, 0)} दिन पहले की है, जो 2 साल की सीमा के भीतर है (विवाद का कारण ठीक कब शुरू हुआ, यह कानूनी प्रश्न हो सकता है)।"
            conf = "clear"
        else:
            lim_en = "Add your purchase or delivery date so NyayaSetu can check the 2-year time limit."
            lim_hi = "2 साल की समय सीमा जाँचने के लिए खरीद या डिलीवरी की तारीख जोड़ें।"
            conf = "clear"
        how = _L(lang, "Before going to a Commission you can use the National Consumer Helpline (toll-free 1915 / consumerhelpline.gov.in), a pre-litigation "
                       "grievance channel; if it does not resolve your grievance, you can still approach the Commission. "
                       f"If the matter is not resolved, you can file a consumer complaint yourself before the {band_en}. You may file where you live or work "
                       f"({city}), where the opposite party carries on business, or where the cause of action arose. Complaints can be filed online "
                       f"through e-Jagriti. {fee_en} {lim_en} Commissions are asked to try to decide within 3 months of notice to the other side "
                       "(5 months if testing is needed) — a target, not a guarantee.",
                 "आयोग जाने से पहले आप राष्ट्रीय उपभोक्ता हेल्पलाइन (टोल-फ़्री 1915 / consumerhelpline.gov.in) का उपयोग कर सकते हैं — यह मुकदमे-पूर्व "
                 "शिकायत माध्यम है; इससे समाधान न हो तो भी आप आयोग जा सकते हैं। "
                 f"अगर मामला नहीं सुलझता, तो आप स्वयं {band_hi} में उपभोक्ता शिकायत दर्ज कर सकते हैं। आप वहाँ दर्ज कर सकते हैं जहाँ आप रहते या काम करते हैं ({city}), "
                 f"जहाँ विपक्षी पक्ष व्यवसाय करता है, या जहाँ विवाद का कारण उत्पन्न हुआ। शिकायत ई-जागृति के ज़रिए ऑनलाइन दर्ज हो सकती है। {fee_hi} {lim_hi} "
                 "आयोगों से अपेक्षा है कि वे दूसरे पक्ष को नोटिस के 3 महीने (जाँच ज़रूरी हो तो 5 महीने) में निर्णय का प्रयास करें — यह लक्ष्य है, गारंटी नहीं।")
        unc = []
        if conf == "uncertain":
            unc.append(_L(lang, "Time limit (Section 69) may be an issue.", "समय सीमा (धारा 69) एक समस्या हो सकती है।"))
        if band in ("state", "national"):
            unc.append(_L(lang, "High-value claim — a lawyer is strongly advised.", "अधिक मूल्य का दावा — वकील की सलाह ज़रूर लें।"))
        return self._issue("forum", "Where and how to file if it is not resolved", "समाधान न हो तो कहाँ और कैसे दर्ज करें", "procedure", conf,
                           ["NCH", "CPA_34", "JUR_RULES_2021", "FEE_RULE_7", "CPA_35", "EJAGRITI", "CPA_69", "CPA_38_7"], how,
                           ["invoice", "payment_proof", "complaint_reference"],
                           _L(lang, "Use NyayaSetu's Consumer Commission preparation draft, then file on e-Jagriti (or ask a lawyer or a recognised consumer association to help).",
                              "NyayaSetu का उपभोक्ता आयोग तैयारी मसौदा इस्तेमाल करें, फिर ई-जागृति पर दर्ज करें (या किसी वकील या मान्यता प्राप्त उपभोक्ता संघ की मदद लें)।"),
                           lang, case, unc)

    def _remedies(self, case, f, lang):
        how = _L(lang, "If a Commission finds in your favour it can order, among other things, removal of the defect, replacement, return of the price with "
                       "interest, compensation for loss caused by the other side's negligence, and costs. These are possible orders; the Commission "
                       "decides on the evidence, and NyayaSetu cannot predict what, if anything, will be awarded.",
                 "अगर आयोग आपके पक्ष में पाता है, तो वह अन्य बातों के साथ दोष दूर करने, बदलने, ब्याज सहित कीमत लौटाने, दूसरे पक्ष की लापरवाही से हुए नुकसान के "
                 "मुआवज़े और खर्च का आदेश दे सकता है। ये संभावित आदेश हैं; आयोग सबूतों पर निर्णय करता है, और NyayaSetu अनुमान नहीं लगा सकता कि क्या मिलेगा।")
        return self._issue("remedies", "What a Commission can order", "आयोग क्या आदेश दे सकता है", "remedy", "info", ["CPA_39"], how, [],
                           _L(lang, "Ask for specific, realistic relief: the price paid, a replacement, and reasonable compensation and costs.",
                              "विशिष्ट, यथार्थवादी राहत माँगें: चुकाई गई कीमत, बदलाव, और उचित मुआवज़ा व खर्च।"), lang, case)

    # ------------------------------------------------------------------ aggregates
    def _uncertainties(self, case, issues, lang):
        out = []
        for i in issues:
            for u in i.get("uncertain", []):
                if u not in out:
                    out.append(u)
        key_missing = [m for m in case.get("missing_info", []) if m["field"] in
                       ("transaction.amount_paid", "transaction.purchase_date", "parties.platform", "evidence", "transaction.order_id")]
        if key_missing:
            labels = ", ".join(m["label_hi"] if lang == "hi" else m["label_en"] for m in key_missing)
            out.append(_L(lang, f"Important details are missing ({labels}); conclusions above may change once you add them.",
                          f"महत्वपूर्ण विवरण अनुपलब्ध हैं ({labels}); इन्हें जोड़ने पर ऊपर के निष्कर्ष बदल सकते हैं।"))
        if case["dispute"].get("low_confidence"):
            out.append(_L(lang, "NyayaSetu is not confident about the type of dispute — check it on the Case Summary page.",
                          "NyayaSetu विवाद के प्रकार को लेकर आश्वस्त नहीं है — केस सारांश पेज पर जाँचें।"))
        return out

    def _lawyer_triggers(self, case, lang):
        fl = case["flags"]
        out = []
        if fl.get("possible_commercial_purpose"):
            out.append(_L(lang, "You bought for resale or business — whether consumer law applies at all needs a lawyer's view.",
                          "आपने दोबारा बेचने या व्यापार के लिए खरीदा — उपभोक्ता कानून लागू होता है या नहीं, इस पर वकील की राय ज़रूरी है।"))
        if fl.get("limitation_risk"):
            out.append(_L(lang, "You may be near or past the 2-year time limit — get advice before filing.",
                          "आप 2 साल की समय सीमा के क़रीब या उसके बाद हो सकते हैं — दर्ज करने से पहले सलाह लें।"))
        if fl.get("harm_beyond_product"):
            out.append(_L(lang, "Someone was hurt or other property was damaged — product-liability claims need legal help.",
                          "किसी को चोट लगी या अन्य संपत्ति को नुकसान हुआ — उत्पाद दायित्व के दावों में कानूनी मदद चाहिए।"))
        if fl.get("value_band") in ("state", "national"):
            out.append(_L(lang, "The value is above ₹50 lakh — the case goes to a State or National Commission; use a lawyer.",
                          "कीमत ₹50 लाख से अधिक है — मामला राज्य या राष्ट्रीय आयोग में जाएगा; वकील की मदद लें।"))
        if re.search(r"scam|fraud|cheat|fake (seller|website|app)|ठगी|धोखा", case.get("narrative", ""), re.I):
            out.append(_L(lang, "You mention a scam or fraud — that can be a criminal matter outside NyayaSetu's scope; contact the police or a lawyer.",
                          "आपने ठगी या धोखाधड़ी का उल्लेख किया — यह आपराधिक मामला हो सकता है जो NyayaSetu के दायरे से बाहर है; पुलिस या वकील से संपर्क करें।"))
        out.append(_L(lang, "If the other side contests the facts, files a reply, or the matter goes to hearing, an advocate (or a recognised consumer association) can help you present evidence.",
                      "अगर दूसरा पक्ष तथ्यों का विरोध करे, जवाब दाखिल करे, या सुनवाई हो, तो अधिवक्ता (या मान्यता प्राप्त उपभोक्ता संघ) सबूत पेश करने में मदद कर सकता है।"))
        return out

    def _deterministic_summary(self, case, issues, lang):
        cat = case["dispute"]["category"]
        label = CATEGORIES.get(cat, CATEGORIES["unknown"])[lang]
        strong = [i["title"] for i in issues if i["label"] == "statutory" and i["id"] not in ("grievance_officer",)]
        args = [i["title"] for i in issues if i["label"] == "argument" and i["confidence"] in ("arguable", "evidence")]
        weak = [i["title"] for i in issues if i["confidence"] in ("not_yet", "uncertain")]
        parts = [_L(lang, f"Your dispute: {label}.", f"आपका विवाद: {label}।")]
        fl = case["flags"]
        threshold = []
        if fl.get("possible_commercial_purpose"):
            threshold.append(_L(lang, "you bought for resale/business, so you may not count as a 'consumer'", "आपने दोबारा बेचने/व्यापार के लिए खरीदा, इसलिए आप शायद 'उपभोक्ता' न माने जाएँ"))
        if fl.get("limitation_expired_likely"):
            threshold.append(_L(lang, "the 2-year time limit may already have passed", "2 साल की समय सीमा शायद बीत चुकी है"))
        elif fl.get("limitation_risk"):
            threshold.append(_L(lang, "you are close to the 2-year time limit", "आप 2 साल की समय सीमा के क़रीब हैं"))
        if fl.get("harm_beyond_product"):
            threshold.append(_L(lang, "someone was hurt or other property was damaged", "किसी को चोट लगी या अन्य संपत्ति को नुकसान हुआ"))
        if threshold:
            parts.append(_L(lang, "IMPORTANT — get legal advice before acting, because " + "; ".join(threshold) + ". The points below matter only if these hurdles are overcome.",
                            "महत्वपूर्ण — कार्रवाई से पहले कानूनी सलाह लें, क्योंकि " + "; ".join(threshold) + "। नीचे के बिंदु तभी मायने रखते हैं जब ये बाधाएँ पार हों।"))
        if strong:
            parts.append(_L(lang, "Rules that support you if your facts are proved: ", "अगर आपके तथ्य साबित हों तो आपके पक्ष के नियम: ") + "; ".join(strong).rstrip(".?") + ".")
        if args:
            parts.append(_L(lang, "Arguments you can make (they depend on evidence): ", "आप ये तर्क रख सकते हैं (सबूत पर निर्भर): ") + "; ".join(args).rstrip(".?") + ".")
        if weak:
            parts.append(_L(lang, "Not yet established or uncertain: ", "अभी स्थापित नहीं या अनिश्चित: ") + "; ".join(t.rstrip("?") for t in weak) + ".")
        parts.append(_L(lang, "Start with a written complaint to the seller and platform; if unresolved, use the National Consumer Helpline and then the Consumer Commission. "
                              "No outcome is guaranteed.",
                        "विक्रेता और प्लेटफ़ॉर्म को लिखित शिकायत से शुरू करें; समाधान न हो तो राष्ट्रीय उपभोक्ता हेल्पलाइन और फिर उपभोक्ता आयोग जाएँ। किसी परिणाम की गारंटी नहीं है।"))
        return " ".join(parts)

    # ------------------------------------------------------------------ optional LLM
    def _llm_summary(self, case: dict, result: dict, lang: str) -> None:
        ids = []
        for i in result["issues"]:
            for sid in i["source_ids"]:
                if self.kb.is_verified(sid) and sid not in ids:
                    ids.append(sid)
        sources_block = "\n\n".join(
            f"[KB:{sid}] {self.kb.get(sid)['short_cite']}\n{self.kb.get(sid)['plain_language']['en']}\nOfficial text: {self.kb.get(sid)['excerpt']}"
            for sid in ids)
        facts = {k: case[k] for k in ("dispute", "transaction", "parties", "steps_taken", "seller_response", "evidence", "desired_resolution")}
        facts["flags"] = {k: v for k, v in case["flags"].items() if k in ("days_since_complaint", "refused_explicitly", "possible_commercial_purpose",
                                                                          "limitation_risk", "harm_beyond_product", "payment_side_issue")}
        system = ("You are NyayaSetu's explanation writer for ordinary Indian consumers. Write in plain "
                  + ("Hindi (Devanagari)" if lang == "hi" else "English") +
                  ". Rules: (1) State a legal rule ONLY if it appears in SOURCES, and put its tag like [KB:CPA_2_10] right after the sentence. "
                  "(2) Never mention any section, rule, Act, case or authority that is not in SOURCES. (3) Do not promise or predict outcomes; "
                  "say 'may', 'can argue', 'depends on evidence'. (4) Separate what the law says from how it may apply to these facts. "
                  "(5) Do not invent facts; if a fact is missing, say it is missing. (6) Maximum 170 words, no headings.")
        user = f"CASE FACTS (JSON):\n{facts}\n\nSOURCES:\n{sources_block}\n\nWrite a short personalised explanation of where this consumer stands."
        try:
            resp = self.llm.complete(system=system, user=user, max_tokens=500)
        except Exception as exc:
            result["summary"]["note"] = f"AI explanation unavailable ({type(exc).__name__}); showing rule-based summary."
            return
        report = validate_llm_explanation(resp.text, set(ids), kb=self.kb)
        result["summary"]["llm_validation"] = report.to_dict()
        if report.ok:
            result["summary"].update({"text": resp.text.strip(), "generated_by": f"llm:{resp.provider}:{resp.model}",
                                      "note": "AI-written; every legal reference was checked against the verified sources."})
        else:
            result["summary"]["note"] = ("AI explanation rejected by the validator (" + report.summary()[:300] +
                                         "); showing the rule-based summary instead.")


def answer_question(question: str, case: dict | None, lang: str, kb: LegalKnowledgeBase | None = None, llm=None) -> dict:
    """Free-text question box: retrieve verified passages; optionally let an LLM answer from them (validated)."""
    kb = kb or get_kb()
    cats = []
    if case:
        cats = [case["dispute"]["category"]] + case["dispute"].get("secondary", [])
    hits = kb.search(question, k=4, categories=cats or None)
    hits = [h for h in hits if h.entry["verification_status"] in ("verified", "verified_secondary")][:3]
    passages = [{"id": h.id, "short_cite": h.entry["short_cite"], "plain": h.entry["plain_language"].get(lang) or h.entry["plain_language"]["en"],
                 "url": h.entry["url"], "status": h.entry["verification_status"], "score": h.score} for h in hits]
    out = {"question": question, "passages": passages, "answer": None, "generated_by": "retrieval-only", "note": ""}
    if not passages:
        out["note"] = _L(lang, "NyayaSetu could not find a verified source for this question. It may be outside the consumer-law scope covered here — "
                               "please consult a lawyer or an official source.",
                         "NyayaSetu को इस प्रश्न के लिए कोई सत्यापित स्रोत नहीं मिला। यह यहाँ कवर किए गए उपभोक्ता कानून के दायरे से बाहर हो सकता है — कृपया वकील या आधिकारिक स्रोत से सलाह लें।")
        return out
    if llm is not None and getattr(llm, "is_live", False):
        ids = {p["id"] for p in passages if p["status"] == "verified"}
        src = "\n\n".join(f"[KB:{p['id']}] {p['short_cite']}: {kb.get(p['id'])['plain_language']['en']} Official text: {kb.get(p['id'])['excerpt']}"
                          for p in passages if p["id"] in ids)
        system = ("Answer the consumer's question in plain " + ("Hindi" if lang == "hi" else "English") +
                  " using ONLY the SOURCES. Tag each legal statement with its [KB:ID]. If the sources do not answer the question, say "
                  "'NyayaSetu could not verify this.' Never mention other laws or cases. Never promise outcomes. Max 120 words.")
        try:
            resp = llm.complete(system=system, user=f"QUESTION: {question}\n\nSOURCES:\n{src}", max_tokens=350)
            rep = validate_llm_explanation(resp.text, ids, kb=kb)
            if rep.ok:
                out.update({"answer": resp.text.strip(), "generated_by": f"llm:{resp.provider}:{resp.model}"})
            else:
                out["note"] = "AI answer rejected by the validator: " + rep.summary()[:200]
        except Exception as exc:
            out["note"] = f"AI answer unavailable ({type(exc).__name__})."
    return out
