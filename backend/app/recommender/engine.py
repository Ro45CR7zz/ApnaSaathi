"""Recommender: business profile -> one recommended bundle, optional add-ons, and exclusions.

Deterministic. Needs are mapped to catalogue products by fixed rules; every candidate is checked
by the rules engine, and the final bundle is validated as a whole before pricing.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.advisor.slots import Slots
from app.catalogue.loader import city_tier, load_catalogue
from app.catalogue.models import BundleLine, BusinessProfile
from app.pricing.engine import PricedQuote, price_bundle
from app.recommender.segment import infer_segment
from app.recommender.why import why
from app.rules.engine import check_product, validate_bundle
from app.rules.messages import render

# Suggested (not pre-selected) add-ons per segment, in order of relevance.
SEGMENT_ADDONS = {
    "micro": ["mobile_lines", "billing_upi", "cctv", "guest_wifi", "whatsapp_customers", "website"],
    "prof": ["mobile_lines", "email_office", "backup_files", "security", "uptime_backup", "static_ip"],
    "multi": ["mobile_lines", "uptime_backup", "cctv", "billing_upi", "central_management", "toll_free"],
    "mfg": ["mobile_lines", "email_office", "security", "uptime_backup", "machines_iot", "cctv"],
}
MAX_ADDONS = 4


class RecLine(BaseModel):
    product_id: str
    product_name: str
    qty: int
    need: str
    why: str
    list_monthly_inr: Optional[int] = None


class Excluded(BaseModel):
    product_id: str
    product_name: str
    need: str
    reason_code: str
    message: str


class Recommendation(BaseModel):
    segment: str
    business_type: Optional[str]
    profile: BusinessProfile
    lines: list[RecLine]
    addons: list[RecLine]
    excluded: list[Excluded]
    notes: list[str]
    quote: PricedQuote


def _profile(s: Slots, lang: str) -> tuple[BusinessProfile, list[str], str]:
    tier, known = city_tier(s.city)
    sites = s.sites or 1
    seg = infer_segment(s.business_type, sites, s.segment)
    # GSTIN status is only *declared* here; it is verified against the registry at KYC.
    status = "Active" if s.has_gstin else "None"
    notes = [] if known or not s.city else [render("UNVERIFIED_CITY", lang, city=s.city)]
    return (BusinessProfile(segment=seg, city=s.city, city_tier=tier, employees=s.employees or 1,
                            sites=sites, gstin_status=status), notes, seg)


def _base(p: BusinessProfile, s: Slots, lang: str) -> RecLine:
    cat = load_catalogue()
    emp, gst = p.employees, p.gstin_status == "Active"

    def ok(pid: str) -> bool:
        return check_product(cat[pid], p).eligible

    # Thresholds follow what real buyers in smb_leads.csv chose (assumption A7):
    # leased lines went to manufacturers (10th percentile ~37 staff, median ~74);
    # P03 to professional offices / manufacturers around 15 staff; multi-site chains took
    # P02 or P01 per outlet (median ~10 staff per outlet), never P03.
    per_site = emp / max(p.sites, 1)
    if p.segment == "mfg" and emp >= 100 and ok("P06"):
        pid, code = "P06", "base_leased"
    elif p.segment == "mfg" and emp >= 30 and ok("P05"):
        pid, code = "P05", "base_leased"
    elif s.fibre_available is False:
        pid, code = "P04", "base_airfiber"
    elif p.segment in ("prof", "mfg") and emp >= 15 and gst and ok("P03"):
        pid, code = "P03", "base_fast"
    elif p.segment == "mfg" or (p.segment == "prof" and emp >= 5) or (p.segment == "multi" and per_site >= 5):
        pid, code = "P02", "base_fast"
    else:
        pid, code = "P01", "base_fibre"
    return RecLine(product_id=pid, product_name=cat[pid].product_name, qty=p.sites, need="internet",
                   why=why(code, lang, sites=p.sites, employees=emp))


def _for_need(need: str, p: BusinessProfile, s: Slots, lang: str) -> list[tuple[str, int, str]]:
    """Return [(product_id, qty, why_text)] for one need tag."""
    emp, sites = p.employees, p.sites
    big = p.segment in ("mfg", "multi")
    if need == "mobile_lines":
        qty = s.mobile_lines or min(emp, 2)
        pid = "P07" if p.segment == "micro" else "P08"
        return [(pid, qty, why("mobile_lines", lang, qty=qty))]
    if need == "billing_upi":
        return [("P19", s.counters or sites, why("billing_upi", lang))]
    if need == "cctv":
        qty = s.cameras or 2 * sites
        return [("P23", qty, why("cctv", lang, qty=qty))]
    if need == "guest_wifi":
        return [("P22", sites, why("guest_wifi", lang))]
    if need == "whatsapp_customers":
        return [("P15", 1, why("whatsapp_customers", lang))]
    if need == "sms_alerts":
        return [("P14", 1, why("sms_alerts", lang))]
    if need == "website":
        return [("P18", 1, why("website", lang))]
    if need == "email_office":
        qty = s.email_users or min(emp, 50)
        return [("P16", qty, why("email_office", lang, qty=qty))]
    if need == "backup_files":
        return [("P17", 1, why("backup_files", lang))]
    if need == "security":
        qty = s.devices or min(emp, 50)
        out = [("P20", qty, why("security_endpoint", lang, qty=qty))]
        if big and emp >= 10:
            out.append(("P21", sites, why("security_firewall", lang)))
        return out
    if need == "uptime_backup":
        return [("P09", sites, why("uptime_backup", lang))]
    if need == "central_management":
        return [("P10", sites, why("central_management", lang, sites=sites))]
    if need == "static_ip":
        return [("P11", 1, why("static_ip", lang))]
    if need == "cloud_calling":
        return [("P12", 2, why("cloud_calling", lang))]
    if need == "toll_free":
        return [("P13", 1, why("toll_free", lang))]
    if need == "machines_iot":
        qty = s.devices or 5
        return [("P24", qty, why("machines_iot", lang, qty=qty))]
    if need == "vehicles":
        qty = s.vehicles or 1
        return [("P25", qty, why("vehicles", lang, qty=qty))]
    return []


def _try_add(pid: str, qty: int, need: str, text: str, p: BusinessProfile, chosen: list[RecLine],
             excluded: list[Excluded], lang: str, report_exclusion: bool = True) -> Optional[RecLine]:
    cat = load_catalogue()
    prod = cat[pid]
    if any(l.product_id == pid for l in chosen):
        return None
    elig = check_product(prod, p, lang)
    if not elig.eligible:
        if report_exclusion:
            i = elig.issues[0]
            excluded.append(Excluded(product_id=pid, product_name=prod.product_name, need=need,
                                     reason_code=i.code, message=i.message))
        return None
    if prod.requires_one_of and not any(l.product_id in prod.requires_one_of for l in chosen):
        if report_exclusion:
            options = ", ".join(cat[o].product_name for o in prod.requires_one_of)
            excluded.append(Excluded(product_id=pid, product_name=prod.product_name, need=need,
                                     reason_code="DEPENDENCY_MISSING",
                                     message=render("DEPENDENCY_MISSING", lang, product=prod.product_name,
                                                    options=options)))
        return None
    if prod.unit == "per site":
        qty = min(qty, p.sites)
    return RecLine(product_id=pid, product_name=prod.product_name, qty=qty, need=need, why=text)


def recommend(s: Slots, lang: str = "en") -> Recommendation:
    p, notes, seg = _profile(s, lang)
    lines: list[RecLine] = [_base(p, s, lang)]
    excluded: list[Excluded] = []

    for need in s.needs:
        if need == "internet":
            continue
        for pid, qty, text in _for_need(need, p, s, lang):
            line = _try_add(pid, qty, need, text, p, lines, excluded, lang)
            if line:
                lines.append(line)

    # Final whole-bundle validation (defence in depth; should already be clean).
    v = validate_bundle(p, [BundleLine(product_id=l.product_id, qty=l.qty) for l in lines], lang)
    if not v.valid:
        bad = {i.product_id for i in v.issues}
        for l in [l for l in lines if l.product_id in bad and l.need != "internet"]:
            issue = next(i for i in v.issues if i.product_id == l.product_id)
            excluded.append(Excluded(product_id=l.product_id, product_name=l.product_name, need=l.need,
                                     reason_code=issue.code, message=issue.message))
        lines = [l for l in lines if l.product_id not in bad or l.need == "internet"]

    quote = price_bundle([BundleLine(product_id=l.product_id, qty=l.qty) for l in lines], lang=lang)
    by_id = {q.product_id: q for q in quote.lines}
    for l in lines:
        l.list_monthly_inr = by_id[l.product_id].list_monthly_inr

    # Suggested add-ons: segment-typical, eligible, not already chosen. Not pre-selected.
    addons: list[RecLine] = []
    for need in SEGMENT_ADDONS[seg]:
        if need in s.needs:
            continue
        for pid, qty, text in _for_need(need, p, s, lang):
            line = _try_add(pid, qty, need, text, p, lines + addons, [], lang, report_exclusion=False)
            if line and len(addons) < MAX_ADDONS:
                line.list_monthly_inr = price_bundle([BundleLine(product_id=pid, qty=line.qty)]).list_monthly_inr
                addons.append(line)

    return Recommendation(segment=seg, business_type=s.business_type, profile=p, lines=lines,
                          addons=addons, excluded=excluded, notes=notes, quote=quote)
