"""MOCK registry lookups backed by the supplied CSVs.

These are simulations for the hackathon. They are NOT connected to the GST or Udyam portals.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from typing import Optional

from app import config
from app.registry import gstin as gstin_mod
from app.registry import udyam as udyam_mod

MOCK_LABEL = "MOCK registry (synthetic hackathon data, not a government system)"


@lru_cache(maxsize=1)
def _gst() -> dict[str, dict]:
    with open(config.GSTIN_REGISTRY_CSV, newline="", encoding="utf-8") as f:
        return {r["gstin"]: r for r in csv.DictReader(f)}


@lru_cache(maxsize=1)
def _udyam() -> dict[str, dict]:
    with open(config.UDYAM_REGISTRY_CSV, newline="", encoding="utf-8") as f:
        return {r["udyam_number"]: r for r in csv.DictReader(f)}


def lookup_gstin(number: str) -> Optional[dict]:
    return _gst().get(gstin_mod.normalise(number))


def lookup_udyam(number: str) -> Optional[dict]:
    return _udyam().get(udyam_mod.normalise(number))


def gstin_status(number: Optional[str]) -> str:
    """Status for the rules engine: Active / Cancelled / Suspended / NotFound / None."""
    if not number:
        return "None"
    rec = lookup_gstin(number)
    return rec["status"] if rec else "NotFound"
