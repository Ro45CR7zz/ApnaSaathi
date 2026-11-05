"""The 12 supplied specimen applicants (K01-K12), for demos and acceptance tests.

Each specimen set is linked to its lead in smb_leads.csv by business name + city (found in Phase 0);
the lead provides what the applicant would have declared: GSTIN, Udyam number and contact name.
"""
from __future__ import annotations

import csv
from functools import lru_cache

from app import config
from app.kyc.checks import Declared

SAMPLE_LEADS = {
    "K01": "L00045", "K02": "L01287", "K03": "L03571", "K04": "L01014", "K05": "L04014", "K06": "L00115",
    "K07": "L03349", "K08": "L03473", "K09": "L04779", "K10": "L04525", "K11": "L03485", "K12": "L03558",
}
DOC_FILES = ("gst_certificate", "udyam_certificate", "address_proof", "signatory_id")


@lru_cache(maxsize=1)
def _leads() -> dict[str, dict]:
    with open(config.LEADS_CSV, newline="", encoding="utf-8") as f:
        return {r["lead_id"]: r for r in csv.DictReader(f) if r["lead_id"] in SAMPLE_LEADS.values()}


def sample_ids() -> list[str]:
    return list(SAMPLE_LEADS)


def lead(kid: str) -> dict:
    return _leads()[SAMPLE_LEADS[kid]]


def declared(kid: str) -> Declared:
    r = lead(kid)
    return Declared(gstin=r["gstin"] or None, no_gstin=r["has_gstin"] != "Y",
                    udyam_number=r["udyam_number"] or None, contact_name=r["contact_name"])


def files(kid: str) -> dict[str, bytes]:
    out = {}
    for dt in DOC_FILES:
        p = config.KYC_DOCS_DIR / f"{kid}_{dt}.png"
        if p.exists():
            out[dt] = p.read_bytes()
    return out
