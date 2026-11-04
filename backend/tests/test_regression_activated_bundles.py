"""Replay all 368 activated deals from smb_leads.csv through the rules engine.

Phase 0 analysis found 48 leads whose bundles broke catalogue rules plus 22 activated on a
cancelled/suspended GSTIN (68 distinct leads, 18% of activations). The engine must find exactly those.
Prices of real deals must also sit inside the catalogue range.
"""
import csv

from app import config
from app.catalogue.loader import load_catalogue
from app.catalogue.models import SEGMENT_CODES, BundleLine, BusinessProfile
from app.registry import store
from app.rules.engine import validate_bundle

RULE_CODES = {"TIER_UNAVAILABLE", "BELOW_MIN_EMPLOYEES", "BELOW_MIN_SITES", "GSTIN_REQUIRED", "DEPENDENCY_MISSING"}


def activated():
    with open(config.LEADS_CSV, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["outcome"] == "Activated"]


def parse(bundle: str) -> list[BundleLine]:
    out = []
    for part in bundle.split(";"):
        pid, qty = part.split("x")
        out.append(BundleLine(product_id=pid, qty=int(qty)))
    return out


def test_replay_finds_exactly_the_non_compliant_deals():
    rows = activated()
    assert len(rows) == 368
    rule_breakers, inactive_gstin = set(), set()
    for r in rows:
        profile = BusinessProfile(
            segment=SEGMENT_CODES[r["segment"]], city=r["city"], city_tier=int(r["city_tier"]),
            employees=int(r["employee_count"]), sites=int(r["num_sites"]),
            # Use the lead's declared GSTIN flag for the rule check; registry status checked separately.
            gstin_status="Active" if r["has_gstin"] == "Y" else "None",
        )
        v = validate_bundle(profile, parse(r["bundle_products"]))
        if {i.code for i in v.issues} & RULE_CODES:
            rule_breakers.add(r["lead_id"])
        if r["gstin"] and store.gstin_status(r["gstin"]) in ("Cancelled", "Suspended"):
            inactive_gstin.add(r["lead_id"])
    assert len(rule_breakers) == 48
    assert len(inactive_gstin) == 22
    assert len(rule_breakers | inactive_gstin) == 68


def test_real_deal_values_inside_catalogue_range():
    cat = load_catalogue()
    for r in activated():
        lines = parse(r["bundle_products"])
        lo = sum(cat[l.product_id].price_min_inr_per_month * l.qty for l in lines)
        hi = sum(cat[l.product_id].price_max_inr_per_month * l.qty for l in lines)
        assert lo <= float(r["monthly_bundle_value_inr"]) <= hi
        assert float(r["one_time_setup_inr"]) == sum(cat[l.product_id].one_time_setup_inr * l.qty for l in lines)
