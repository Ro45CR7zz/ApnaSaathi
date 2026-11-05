"""Classify a document from its OCR text and pull out the labelled fields.

The specimen formats are "label  value" lines (certificates, bill) or "label / next-line value"
(signatory ID). Values are OCR output: treated as untrusted and uncertain, never as verified facts.
"""
from __future__ import annotations

import re
from typing import Optional

DOC_TYPES = ("gst_certificate", "udyam_certificate", "address_proof", "signatory_id")

_HEADERS = [
    ("gst_certificate", re.compile(r"gst\s*registration\s*certificate|gstin", re.I)),
    ("udyam_certificate", re.compile(r"udyam", re.I)),
    ("address_proof", re.compile(r"electricity\s*bill|consumer\s*no|billed\s*to|supply\s*address", re.I)),
    ("signatory_id", re.compile(r"signatory|valid\s*till", re.I)),
]


def classify(text: str) -> Optional[str]:
    head = "\n".join(text.splitlines()[:4])
    for doc_type, pat in _HEADERS:  # header lines first: most reliable
        if pat.search(head):
            return doc_type
    for doc_type, pat in _HEADERS:
        if pat.search(text):
            return doc_type
    return None


def _lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", l).strip() for l in text.splitlines() if l.strip()]


def _after(lines: list[str], label: str) -> tuple[Optional[str], int]:
    """Value on the same line after `label` (case-insensitive). Returns (value, line index)."""
    pat = re.compile(r"^" + label + r"\s*[:\-]?\s*(.*)$", re.I)
    for i, l in enumerate(lines):
        m = pat.match(l)
        if m:
            return (m.group(1).strip() or None), i
    return None, -1


def _continuation(lines: list[str], i: int, stop_labels: list[str]) -> str:
    """The next line if it continues a wrapped value (i.e. it is not another label)."""
    if 0 <= i + 1 < len(lines):
        nxt = lines[i + 1]
        if not any(re.match(s, nxt, re.I) for s in stop_labels):
            return nxt
    return ""


_DATE = re.compile(r"(\d{4})\s*-\s*(\d{2})\s*-\s*(\d{2})")


def _date(v: Optional[str]) -> Optional[str]:
    m = _DATE.search(v or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _join_wrapped(a: str, b: str) -> str:
    # The specimens wrap long values mid-word ("...Maharashtr" + "a - 411231"), so join without a space.
    return (a + b) if a and b else (a or b)


def parse_gst(text: str) -> dict:
    L = _lines(text)
    gstin, _ = _after(L, r"GSTIN")
    legal, _ = _after(L, r"Legal\s*name")
    trade, _ = _after(L, r"Trade\s*name")
    constitution, _ = _after(L, r"Constitution")
    addr1, i = _after(L, r"Address\s*of\s*princip\w*")
    addr2, _ = _after(L, r"place\s*of\s*business")
    liability, _ = _after(L, r"Date\s*of\s*liability")
    return {
        "gstin": re.sub(r"[^0-9A-Za-z]", "", gstin or "").upper() or None,
        "legal_name": legal, "trade_name": trade, "constitution": constitution,
        "address": _join_wrapped(addr1 or "", addr2 or "") or None,
        "date_of_liability": _date(liability),
    }


def parse_udyam(text: str) -> dict:
    L = _lines(text)
    number, _ = _after(L, r"Udyam\s*reg\.?\s*number")
    name, _ = _after(L, r"Enterprise\s*name")
    activity, _ = _after(L, r"Major\s*activity")
    city, _ = _after(L, r"City")
    state, _ = _after(L, r"State")
    reg, _ = _after(L, r"Date\s*of\s*registration")
    num = re.sub(r"\s+", "", number or "").upper()
    return {"udyam_number": num if num.startswith("UDYAM") else None, "enterprise_name": name,
            "major_activity": activity, "city": city, "state": state, "date_of_registration": _date(reg)}


def parse_bill(text: str) -> dict:
    L = _lines(text)
    consumer, _ = _after(L, r"Consumer\s*no\.?")
    billed, _ = _after(L, r"Billed\s*to")
    addr, i = _after(L, r"Supply\s*address")
    cont = _continuation(L, i, [r"Bill\s*date", r"Units", r"Amount", r"Accel"])
    bill_date, _ = _after(L, r"Bill\s*date")
    return {"consumer_no": consumer, "billed_to": billed, "address": _join_wrapped(addr or "", cont) or None,
            "bill_date": _date(bill_date)}


def parse_signatory(text: str) -> dict:
    L = _lines(text)

    def below(label: str) -> Optional[str]:
        for i, l in enumerate(L):
            if re.fullmatch(label, l, re.I) and i + 1 < len(L):
                return L[i + 1]
        return None

    return {"name": below(r"Name"), "designation": below(r"Designation"), "business": below(r"For\s*business"),
            "id_no": below(r"ID\s*no\.?"), "valid_till": _date(below(r"Valid\s*till"))}


PARSERS = {"gst_certificate": parse_gst, "udyam_certificate": parse_udyam, "address_proof": parse_bill,
           "signatory_id": parse_signatory}


def extract(doc_type: str, text: str) -> dict:
    return PARSERS[doc_type](text)
