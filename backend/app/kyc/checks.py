"""KYC checks: compare what the documents say with what the owner declared and the (mock) registries.

Every check returns pass / warn / fail. A failing check names the action it needs:
  block  - can't proceed with GST products (e.g. GSTIN cancelled)
  fix    - the owner can fix it (retake photo, upload missing or newer document)
  review - a person must look (names don't match, signatory authority unclear)
Outcome precedence: BLOCKED > NEEDS_FIX > MANUAL_REVIEW > VERIFIED.
Identity values are never changed silently; an OCR correction is accepted only when it equals
the GSTIN the owner typed and confirmed.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Literal, Optional

from pydantic import BaseModel

from app import config
from app.common.masking import mask_gstin, mask_name, mask_udyam
from app.registry import store
from app.registry.udyam import is_valid_format as udyam_format_ok

Status = Literal["pass", "warn", "fail"]
Action = Literal["block", "fix", "review"]
Outcome = Literal["VERIFIED", "NEEDS_FIX", "MANUAL_REVIEW", "BLOCKED"]

ADDRESS_PROOF_MAX_DAYS = 90
NAME_MATCH = 0.92

M: dict[str, tuple[str, str]] = {
    "DOC_MISSING": ("Please upload your {doc}.", "कृपया अपना {doc} अपलोड करें।"),
    "DOC_BLURRY": ("The photo of your {doc} is blurry. Hold the phone steady in good light and take it again.",
                   "आपके {doc} की फ़ोटो धुंधली है। अच्छी रोशनी में फ़ोन स्थिर रखकर दोबारा फ़ोटो लें।"),
    "DOC_TILTED": ("The photo of your {doc} is too tilted. Place it flat and take the photo from straight above.",
                   "आपके {doc} की फ़ोटो बहुत तिरछी है। डॉक्यूमेंट को सीधा रखकर ऊपर से फ़ोटो लें।"),
    "DOC_STRAIGHTENED": ("Your {doc} was slightly tilted; we straightened it automatically.",
                         "आपका {doc} थोड़ा तिरछा था; हमने उसे अपने-आप सीधा कर दिया।"),
    "DOC_WRONG_TYPE": ("This looks like a {found}, not a {doc}. Please upload your {doc}.",
                       "यह {found} लगता है, {doc} नहीं। कृपया अपना {doc} अपलोड करें।"),
    "DOC_UNREADABLE": ("We couldn't read your {doc}. Please upload a clearer photo.",
                       "आपका {doc} पढ़ा नहीं जा सका। कृपया साफ़ फ़ोटो अपलोड करें।"),
    "GSTIN_ACTIVE": ("GSTIN found in the registry and active.", "GSTIN रजिस्ट्री में मिला और सक्रिय है।"),
    "GSTIN_INACTIVE": ("This GSTIN is {reg_status} in the GST registry, so products that need GST can't be activated. "
                       "You can continue with products that don't need GST.",
                       "GST रजिस्ट्री में यह GSTIN {reg_status_hi} है, इसलिए GST वाले प्रोडक्ट चालू नहीं हो सकते। "
                       "आप बिना GST वाले प्रोडक्ट के साथ आगे बढ़ सकते हैं।"),
    "GSTIN_NOT_FOUND": ("This GSTIN was not found in the GST registry. Please check the number.",
                        "यह GSTIN GST रजिस्ट्री में नहीं मिला। कृपया नंबर जाँचें।"),
    "GSTIN_DOC_MATCH": ("The GSTIN on the certificate matches.", "सर्टिफ़िकेट पर लिखा GSTIN मेल खाता है।"),
    "GSTIN_DOC_OCR_FIXED": ("The scan read a similar-looking character ({fix}); it matches the GSTIN you confirmed.",
                            "स्कैन में मिलता-जुलता अक्षर पढ़ा गया ({fix}); यह आपके पुष्टि किए GSTIN से मेल खाता है।"),
    "GSTIN_DOC_MISMATCH": ("The GSTIN on your certificate ({doc_gstin}) doesn't match the GSTIN you gave ({gstin}). "
                           "Please upload the certificate for this GSTIN.",
                           "सर्टिफ़िकेट का GSTIN ({doc_gstin}) आपके दिए GSTIN ({gstin}) से मेल नहीं खाता। "
                           "कृपया इसी GSTIN का सर्टिफ़िकेट अपलोड करें।"),
    "GST_NAMES_MATCH": ("Business names on the certificate match the registry.",
                        "सर्टिफ़िकेट पर बिज़नेस के नाम रजिस्ट्री से मेल खाते हैं।"),
    "GST_NAME_MISMATCH": ("The {field} on the certificate doesn't match the GST registry. A specialist will check it.",
                          "सर्टिफ़िकेट पर {field_hi} GST रजिस्ट्री से मेल नहीं खाता। एक्सपर्ट इसकी जाँच करेंगे।"),
    "GST_ADDRESS_MATCH": ("Address on the certificate matches the registry.", "सर्टिफ़िकेट का पता रजिस्ट्री से मेल खाता है।"),
    "GST_ADDRESS_MISMATCH": ("The address on the certificate doesn't match the registry. A specialist will check it.",
                             "सर्टिफ़िकेट का पता रजिस्ट्री से मेल नहीं खाता। एक्सपर्ट इसकी जाँच करेंगे।"),
    "UDYAM_NUMBER_MISSING": ("The Udyam number on your certificate is missing or unreadable. Please upload a clear copy.",
                             "आपके उद्यम सर्टिफ़िकेट पर उद्यम नंबर नहीं है या पढ़ा नहीं जा सका। कृपया साफ़ कॉपी अपलोड करें।"),
    "UDYAM_NOT_FOUND": ("This Udyam number was not found in the Udyam registry.", "यह उद्यम नंबर उद्यम रजिस्ट्री में नहीं मिला।"),
    "UDYAM_NUMBER_MISMATCH": ("The Udyam number on the certificate doesn't match the one on record.",
                              "सर्टिफ़िकेट का उद्यम नंबर रिकॉर्ड से मेल नहीं खाता।"),
    "UDYAM_MATCH": ("Udyam registration found and matches your business.", "उद्यम रजिस्ट्रेशन मिला और आपके बिज़नेस से मेल खाता है।"),
    "UDYAM_NAME_MISMATCH": ("The business name on the Udyam certificate doesn't match. A specialist will check it.",
                            "उद्यम सर्टिफ़िकेट पर बिज़नेस का नाम मेल नहीं खाता। एक्सपर्ट इसकी जाँच करेंगे।"),
    "UDYAM_DETAILS_DIFFER": ("Some details on the Udyam certificate ({fields}) differ from the registry. Noted for records.",
                             "उद्यम सर्टिफ़िकेट की कुछ जानकारी ({fields}) रजिस्ट्री से अलग है। रिकॉर्ड के लिए नोट किया गया।"),
    "BILL_OK": ("Address proof is recent and matches your business address.",
                "पते का प्रमाण हाल का है और आपके बिज़नेस के पते से मेल खाता है।"),
    "BILL_TOO_OLD": ("Your address proof is dated {bill_date}, more than {days} days ago. Please upload a bill from the last 3 months.",
                     "आपके पते के प्रमाण की तारीख {bill_date} है, जो {days} दिन से पुरानी है। कृपया पिछले 3 महीने का बिल अपलोड करें।"),
    "BILL_NAME_MISMATCH": ("The bill is not in your business name. A specialist will check it.",
                           "बिल आपके बिज़नेस के नाम पर नहीं है। एक्सपर्ट इसकी जाँच करेंगे।"),
    "BILL_ADDRESS_MISMATCH": ("The bill's address doesn't match your registered address. A specialist will check it.",
                              "बिल का पता आपके रजिस्टर्ड पते से मेल नहीं खाता। एक्सपर्ट इसकी जाँच करेंगे।"),
    "SIGNATORY_OK": ("Signatory ID is valid and matches your business.", "हस्ताक्षरकर्ता की ID मान्य है और आपके बिज़नेस से मेल खाती है।"),
    "SIGNATORY_EXPIRED": ("The signatory ID expired on {valid_till}. Please upload a valid ID.",
                          "हस्ताक्षरकर्ता की ID {valid_till} को खत्म हो गई। कृपया मान्य ID अपलोड करें।"),
    "SIGNATORY_BUSINESS_MISMATCH": ("The signatory ID is for a different business. A specialist will check it.",
                                    "हस्ताक्षरकर्ता की ID किसी दूसरे बिज़नेस की है। एक्सपर्ट इसकी जाँच करेंगे।"),
    "SIGNATORY_AUTHORITY": ("The person on the signatory ID ({signatory}) is not the owner on record ({expected}). "
                            "A specialist will check; you may need an authorisation letter.",
                            "हस्ताक्षरकर्ता ID वाले व्यक्ति ({signatory}) रिकॉर्ड में मालिक ({expected}) नहीं हैं। "
                            "एक्सपर्ट जाँच करेंगे; अधिकार-पत्र (authorisation letter) की ज़रूरत हो सकती है।"),
    "NO_REGISTRATION": ("Without a GSTIN or Udyam registration we need a specialist to verify your business. "
                        "Udyam registration is free and online at udyamregistration.gov.in.",
                        "GSTIN या उद्यम रजिस्ट्रेशन के बिना बिज़नेस की जाँच एक्सपर्ट करेंगे। "
                        "उद्यम रजिस्ट्रेशन मुफ़्त है और udyamregistration.gov.in पर ऑनलाइन होता है।"),
}

DOC_NAMES = {
    "gst_certificate": ("GST certificate", "GST सर्टिफ़िकेट"),
    "udyam_certificate": ("Udyam certificate", "उद्यम सर्टिफ़िकेट"),
    "address_proof": ("address proof (electricity bill)", "पते का प्रमाण (बिजली का बिल)"),
    "signatory_id": ("signatory ID", "हस्ताक्षरकर्ता की ID"),
}
FIELD_NAMES = {"legal name": "कानूनी नाम", "trade name": "ट्रेड नाम"}
STATUS_HI = {"Cancelled": "रद्द", "Suspended": "निलंबित"}


class Check(BaseModel):
    code: str
    doc_type: Optional[str] = None
    status: Status
    action: Optional[Action] = None
    message: str


class Declared(BaseModel):
    """What the owner told us (or, for sample applicants, the lead record)."""

    gstin: Optional[str] = None
    no_gstin: bool = False
    udyam_number: Optional[str] = None
    contact_name: Optional[str] = None


class DocResult(BaseModel):
    doc_type: str
    found_type: Optional[str] = None
    sharp: bool = True
    too_tilted: bool = False
    deskewed: bool = False
    readable: bool = True
    fields: dict = {}


def norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zऀ-ॿ ]", " ", (s or "").lower())).strip()


def similar(a: Optional[str], b: Optional[str]) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    return 1.0 if a == b else SequenceMatcher(None, a, b).ratio()


def split_prop(legal: Optional[str]) -> tuple[str, Optional[str]]:
    """'Neha Kaur (Prop. Vindhya Tours & Travels)' -> ('Neha Kaur', 'Vindhya Tours & Travels')."""
    m = re.match(r"^(.*?)\s*\(\s*Prop\.?\s*(.*?)\s*\)\s*$", legal or "", re.I)
    return (m.group(1), m.group(2)) if m else ((legal or ""), None)


def names_match(a: Optional[str], b: Optional[str]) -> bool:
    pa, pb = split_prop(a), split_prop(b)
    if pa[1] is not None or pb[1] is not None:  # compare the person and the business separately
        return similar(pa[0], pb[0]) >= NAME_MATCH and similar(pa[1], pb[1]) >= NAME_MATCH
    return similar(a, b) >= NAME_MATCH


# OCR look-alikes accepted when comparing a scanned GSTIN with the one the owner typed (which already
# passed format, checksum and registry checks). S/5 and B/8 are deliberately excluded: a different
# digit there is treated as a real mismatch (sample K06).
_CONFUSABLE = [{"0", "O"}, {"1", "I"}, {"I", "J"}, {"2", "Z"}]


def ocr_equal(scanned: str, reference: str) -> list[int]:
    """Positions that differ only by OCR look-alikes, or [-1] if the strings genuinely differ."""
    if len(scanned) != len(reference):
        return [-1]
    diffs = []
    for i, (a, b) in enumerate(zip(scanned, reference)):
        if a != b:
            if not any({a, b} <= pair for pair in _CONFUSABLE):
                return [-1]
            diffs.append(i)
    return diffs


def pincode(addr: Optional[str]) -> Optional[str]:
    found = re.findall(r"(\d{6})(?!\d)", re.sub(r"\s+", "", addr or ""))
    return found[-1] if found else None


class Evaluator:
    def __init__(self, lang: str, today: Optional[date] = None):
        self.lang, self.today = lang, today or config.TODAY
        self.checks: list[Check] = []

    def add(self, code: str, status: Status, action: Optional[Action] = None, doc: Optional[str] = None, **p):
        en, hi = M[code]
        if doc:
            p.setdefault("doc", DOC_NAMES[doc][1 if self.lang == "hi" else 0])
        if "reg_status" in p:
            p.setdefault("reg_status_hi", STATUS_HI.get(p["reg_status"], p["reg_status"]))
        if "field" in p:
            p.setdefault("field_hi", FIELD_NAMES.get(p["field"], p["field"]))
        text = (hi if self.lang == "hi" else en).format(**p)
        self.checks.append(Check(code=code, doc_type=doc, status=status, action=action if status == "fail" else None,
                                 message=text))


def required_docs(d: Declared) -> list[str]:
    docs = []
    if d.gstin:
        docs.append("gst_certificate")
    if d.udyam_number:
        docs.append("udyam_certificate")
    return docs + ["address_proof", "signatory_id"]


def evaluate(declared: Declared, docs: dict[str, DocResult], lang: str = "en",
             today: Optional[date] = None) -> tuple[Outcome, list[Check]]:
    ev = Evaluator(lang, today)
    gst_rec = store.lookup_gstin(declared.gstin) if declared.gstin else None
    usable: dict[str, dict] = {}

    # 1. Presence and photo quality.
    for dt in required_docs(declared):
        if dt not in docs:
            ev.add("DOC_MISSING", "fail", "fix", dt)
    for dt, r in docs.items():
        if r.too_tilted:
            ev.add("DOC_TILTED", "fail", "fix", dt)
        elif not r.sharp:
            ev.add("DOC_BLURRY", "fail", "fix", dt)
        elif r.found_type and r.found_type != dt:
            ev.add("DOC_WRONG_TYPE", "fail", "fix", dt, found=DOC_NAMES[r.found_type][1 if lang == "hi" else 0])
        elif not r.readable:
            ev.add("DOC_UNREADABLE", "fail", "fix", dt)
        else:
            usable[dt] = r.fields
            if r.deskewed:
                ev.add("DOC_STRAIGHTENED", "pass", doc=dt)

    if not declared.gstin and not declared.udyam_number:
        ev.add("NO_REGISTRATION", "fail", "review")

    # 2. GSTIN against the registry, then the certificate against both.
    if declared.gstin:
        if gst_rec is None:
            ev.add("GSTIN_NOT_FOUND", "fail", "block")
        elif gst_rec["status"] != "Active":
            ev.add("GSTIN_INACTIVE", "fail", "block", reg_status=gst_rec["status"])
        else:
            ev.add("GSTIN_ACTIVE", "pass")
    g = usable.get("gst_certificate")
    if g is not None and declared.gstin:
        doc_gstin = (g.get("gstin") or "").upper()
        if doc_gstin == declared.gstin:
            ev.add("GSTIN_DOC_MATCH", "pass", doc="gst_certificate")
        elif (diffs := ocr_equal(doc_gstin, declared.gstin)) != [-1]:
            fix = ", ".join(f"{doc_gstin[i]}→{declared.gstin[i]}" for i in diffs)
            ev.add("GSTIN_DOC_OCR_FIXED", "pass", doc="gst_certificate", fix=fix)
        else:
            ev.add("GSTIN_DOC_MISMATCH", "fail", "fix", "gst_certificate",
                   doc_gstin=mask_gstin(doc_gstin) or "?", gstin=mask_gstin(declared.gstin))
        if gst_rec:
            bad = [f for f, a, b in (("legal name", g.get("legal_name"), gst_rec["legal_name"]),
                                      ("trade name", g.get("trade_name"), gst_rec["trade_name"]))
                   if not names_match(a, b)]
            for f in bad:
                ev.add("GST_NAME_MISMATCH", "fail", "review", "gst_certificate", field=f)
            if not bad:
                ev.add("GST_NAMES_MATCH", "pass", doc="gst_certificate")
            if pincode(g.get("address")) == pincode(gst_rec["principal_place_of_business"]):
                ev.add("GST_ADDRESS_MATCH", "pass", doc="gst_certificate")
            else:
                ev.add("GST_ADDRESS_MISMATCH", "fail", "review", "gst_certificate")

    # 3. Udyam certificate (required if the owner has a Udyam number; checked whenever uploaded).
    u = usable.get("udyam_certificate")
    if u is not None:
        num = u.get("udyam_number")
        if not num or not udyam_format_ok(num):
            ev.add("UDYAM_NUMBER_MISSING", "fail", "fix", "udyam_certificate")
        elif declared.udyam_number and num != declared.udyam_number:
            ev.add("UDYAM_NUMBER_MISMATCH", "fail", "fix", "udyam_certificate")
        else:
            rec = store.lookup_udyam(num)
            if rec is None:
                ev.add("UDYAM_NOT_FOUND", "fail", "fix", "udyam_certificate")
            elif not names_match(u.get("enterprise_name"), rec["enterprise_name"]):
                ev.add("UDYAM_NAME_MISMATCH", "fail", "review", "udyam_certificate")
            else:
                ev.add("UDYAM_MATCH", "pass", doc="udyam_certificate")
                differ = [f for f, a, b in (("date of registration", u.get("date_of_registration"), rec["date_of_registration"]),
                                            ("major activity", u.get("major_activity"), rec["major_activity"]),
                                            ("city", u.get("city"), rec["city"]))
                          if a and b and norm(a) != norm(b)]
                if differ:
                    ev.add("UDYAM_DETAILS_DIFFER", "warn", doc="udyam_certificate", fields=", ".join(differ))

    # Reference identity for the remaining checks: registry first, else the Udyam record.
    ref_names = [n for n in (gst_rec and gst_rec["trade_name"], gst_rec and gst_rec["legal_name"]) if n]
    ref_pin = pincode(gst_rec["principal_place_of_business"]) if gst_rec else None
    if not ref_names and u and u.get("udyam_number"):
        rec = store.lookup_udyam(u["udyam_number"])
        if rec:
            ref_names = [rec["enterprise_name"]]

    def is_ours(name: Optional[str]) -> bool:
        return any(names_match(name, r) or names_match(name, split_prop(r)[1]) for r in ref_names) if ref_names else True

    # 4. Address proof: our business, our address, recent.
    b = usable.get("address_proof")
    if b is not None:
        ok = True
        if not is_ours(b.get("billed_to")):
            ev.add("BILL_NAME_MISMATCH", "fail", "review", "address_proof"); ok = False
        if ref_pin and pincode(b.get("address")) != ref_pin:
            ev.add("BILL_ADDRESS_MISMATCH", "fail", "review", "address_proof"); ok = False
        bd = b.get("bill_date")
        if not bd:
            ev.add("DOC_UNREADABLE", "fail", "fix", "address_proof"); ok = False
        elif date.fromisoformat(bd) < ev.today - timedelta(days=ADDRESS_PROOF_MAX_DAYS):
            ev.add("BILL_TOO_OLD", "fail", "fix", "address_proof", bill_date=bd, days=ADDRESS_PROOF_MAX_DAYS); ok = False
        if ok:
            ev.add("BILL_OK", "pass", doc="address_proof")

    # 5. Signatory: valid, for this business, and authorised.
    s = usable.get("signatory_id")
    if s is not None:
        ok = True
        if not is_ours(s.get("business")):
            ev.add("SIGNATORY_BUSINESS_MISMATCH", "fail", "review", "signatory_id"); ok = False
        vt = s.get("valid_till")
        if vt and date.fromisoformat(vt) < ev.today:
            ev.add("SIGNATORY_EXPIRED", "fail", "fix", "signatory_id", valid_till=vt); ok = False
        proprietor = split_prop(gst_rec["legal_name"])[0] if gst_rec and gst_rec["constitution"] == "Proprietorship" else None
        expected = proprietor or declared.contact_name
        if expected and similar(s.get("name"), expected) < NAME_MATCH:
            ev.add("SIGNATORY_AUTHORITY", "fail", "review", "signatory_id",
                   signatory=mask_name(s.get("name")), expected=mask_name(expected)); ok = False
        if ok:
            ev.add("SIGNATORY_OK", "pass", doc="signatory_id")

    actions = {c.action for c in ev.checks if c.status == "fail"}
    outcome: Outcome = ("BLOCKED" if "block" in actions else "NEEDS_FIX" if "fix" in actions
                        else "MANUAL_REVIEW" if "review" in actions else "VERIFIED")
    return outcome, ev.checks
