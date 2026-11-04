"""Loads the product catalogue and reference data (city tiers, business types).

The supplied CSVs are the source of truth; nothing here is hard-coded.
"""
from __future__ import annotations

import csv
from functools import lru_cache

from app import config
from app.catalogue.models import SEGMENT_CODES, Product


def _split(value: str, sep: str) -> list[str]:
    return [v.strip() for v in (value or "").split(sep) if v.strip()]


@lru_cache(maxsize=1)
def load_catalogue() -> dict[str, Product]:
    products: dict[str, Product] = {}
    with open(config.CATALOGUE_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            p = Product(
                product_id=row["product_id"],
                category=row["category"],
                product_name=row["product_name"],
                description=row["description"],
                unit=row["unit"],
                price_min_inr_per_month=int(row["price_min_inr_per_month"]),
                price_max_inr_per_month=int(row["price_max_inr_per_month"]),
                one_time_setup_inr=int(row["one_time_setup_inr"]),
                min_contract_months=int(row["min_contract_months"]),
                available_city_tiers=[int(t) for t in _split(row["available_city_tiers"], ";")],
                min_employees=int(row["min_employees"]),
                min_sites=int(row["min_sites"]),
                requires_gstin=row["requires_gstin"].strip().upper() == "Y",
                requires_one_of=_split(row["requires_one_of"], "|"),
                typical_install_days=int(row["typical_install_days"]),
                target_segments=_split(row["target_segments"], ";"),
            )
            products[p.product_id] = p
    return products


@lru_cache(maxsize=1)
def load_reference() -> dict:
    """City -> tier/state and business type -> segment, derived from the leads file."""
    cities: dict[str, dict] = {}
    business_types: dict[str, str] = {}
    with open(config.LEADS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cities.setdefault(row["city"], {"tier": int(row["city_tier"]), "state": row["state"]})
            business_types.setdefault(row["business_type"], SEGMENT_CODES[row["segment"]])
    return {"cities": cities, "business_types": business_types}


def city_tier(city: str | None) -> tuple[int, bool]:
    """Return (tier, known). Unknown cities are treated as tier 2 (assumption A13)."""
    if city:
        for name, info in load_reference()["cities"].items():
            if name.lower() == city.strip().lower():
                return info["tier"], True
    return 2, False
