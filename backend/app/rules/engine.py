"""Deterministic eligibility and bundle validation.

The LLM never decides eligibility: every decision here comes from product_catalogue.csv.
`target_segments` is NOT an eligibility rule (assumption A5); it is used only for ranking.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.catalogue.loader import load_catalogue
from app.catalogue.models import BundleLine, BusinessProfile, Product
from app.rules.messages import render


class Issue(BaseModel):
    code: str
    product_id: Optional[str] = None
    params: dict = {}
    message: str = ""


class EligibilityResult(BaseModel):
    product_id: str
    product_name: str
    eligible: bool
    issues: list[Issue] = []


class BundleValidation(BaseModel):
    valid: bool
    lines: list[BundleLine]
    issues: list[Issue] = []
    auto_added: list[Issue] = []


def _issue(code: str, lang: str, product: Optional[Product] = None, **params) -> Issue:
    if product is not None:
        params = {"product": product.product_name, **params}
    return Issue(
        code=code,
        product_id=product.product_id if product else params.get("product_id"),
        params=params,
        message=render(code, lang, **params),
    )


def check_product(product: Product, profile: BusinessProfile, lang: str = "en") -> EligibilityResult:
    """Check one product against a business profile (ignores bundle dependencies)."""
    issues: list[Issue] = []
    if profile.city_tier not in product.available_city_tiers:
        issues.append(_issue("TIER_UNAVAILABLE", lang, product))
    if profile.employees < product.min_employees:
        issues.append(_issue("BELOW_MIN_EMPLOYEES", lang, product,
                             min_employees=product.min_employees, employees=profile.employees))
    if profile.sites < product.min_sites:
        issues.append(_issue("BELOW_MIN_SITES", lang, product,
                             min_sites=product.min_sites, sites=profile.sites))
    if product.requires_gstin:
        if profile.gstin_status in ("None",):
            issues.append(_issue("GSTIN_REQUIRED", lang, product))
        elif profile.gstin_status != "Active":
            issues.append(_issue("GSTIN_INACTIVE", lang, product, status=profile.gstin_status))
    return EligibilityResult(product_id=product.product_id, product_name=product.product_name,
                             eligible=not issues, issues=issues)


def check_all(profile: BusinessProfile, lang: str = "en") -> list[EligibilityResult]:
    return [check_product(p, profile, lang) for p in load_catalogue().values()]


def _pick_dependency(options: list[str], profile: BusinessProfile) -> Optional[str]:
    """Cheapest eligible product among the allowed dependencies."""
    catalogue = load_catalogue()
    eligible = [catalogue[o] for o in options if o in catalogue and check_product(catalogue[o], profile).eligible]
    if not eligible:
        return None
    return min(eligible, key=lambda p: (p.price_min_inr_per_month, p.product_id)).product_id


def validate_bundle(profile: BusinessProfile, lines: list[BundleLine], lang: str = "en",
                    auto_fix: bool = False) -> BundleValidation:
    """Validate a bundle as a whole combination.

    With auto_fix=True a missing dependency is added (cheapest eligible option, one per site)
    and reported in `auto_added`; everything else is reported as an issue, never silently fixed.
    """
    catalogue = load_catalogue()
    issues: list[Issue] = []
    auto_added: list[Issue] = []
    seen: set[str] = set()
    clean: list[BundleLine] = []

    for line in lines:
        product = catalogue.get(line.product_id)
        if product is None:
            issues.append(_issue("UNKNOWN_PRODUCT", lang, product_id=line.product_id))
            continue
        if line.product_id in seen:
            issues.append(_issue("DUPLICATE_PRODUCT", lang, product))
            continue
        seen.add(line.product_id)
        clean.append(line)
        issues.extend(check_product(product, profile, lang).issues)
        if product.unit == "per site" and line.qty > profile.sites:
            issues.append(_issue("QTY_EXCEEDS_SITES", lang, product, qty=line.qty, sites=profile.sites))

    # Dependencies are checked against the whole bundle.
    for line in list(clean):
        product = catalogue[line.product_id]
        if not product.requires_one_of:
            continue
        if any(l.product_id in product.requires_one_of for l in clean):
            continue
        added_id = _pick_dependency(product.requires_one_of, profile) if auto_fix else None
        if added_id:
            clean.append(BundleLine(product_id=added_id, qty=profile.sites))
            auto_added.append(_issue("DEPENDENCY_AUTO_ADDED", lang, product,
                                     added=catalogue[added_id].product_name))
        else:
            options = ", ".join(catalogue[o].product_name for o in product.requires_one_of if o in catalogue)
            issues.append(_issue("DEPENDENCY_MISSING", lang, product, options=options))

    return BundleValidation(valid=not issues, lines=clean, issues=issues, auto_added=auto_added)
