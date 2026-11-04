"""Phase 4 API: catalogue, eligibility, bundle validation, pricing and MOCK registry lookups."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.catalogue.loader import city_tier, load_catalogue, load_reference
from app.catalogue.models import BundleLine, BusinessProfile, Language, Segment
from app.common.masking import mask_gstin, mask_udyam
from app.pricing.engine import PricedQuote, PricingOptions, price_bundle
from app.registry import store
from app.registry.gstin import check_gstin
from app.registry.udyam import is_valid_format as udyam_valid
from app.rules.engine import BundleValidation, EligibilityResult, check_all, validate_bundle
from app.rules.messages import render

router = APIRouter(prefix="/api")


class ProfileIn(BaseModel):
    """What a caller sends. City tier and GSTIN status are resolved server-side."""

    segment: Segment
    city: str
    employees: int = Field(ge=1)
    sites: int = Field(ge=1)
    gstin: Optional[str] = None


class ResolvedProfile(BaseModel):
    profile: BusinessProfile
    city_known: bool
    notes: list[str] = []


def resolve(p: ProfileIn, lang: str) -> ResolvedProfile:
    tier, known = city_tier(p.city)
    status = store.gstin_status(p.gstin)
    notes = [] if known else [render("UNVERIFIED_CITY", lang, city=p.city)]
    return ResolvedProfile(
        profile=BusinessProfile(segment=p.segment, city=p.city, city_tier=tier,
                                employees=p.employees, sites=p.sites, gstin_status=status),
        city_known=known, notes=notes)


@router.get("/health")
def health():
    return {"status": "ok", "products": len(load_catalogue())}


@router.get("/catalogue")
def catalogue():
    return list(load_catalogue().values())


@router.get("/reference")
def reference():
    return load_reference()


class EligibilityRequest(BaseModel):
    profile: ProfileIn
    language: Language = "en"


class EligibilityResponse(BaseModel):
    resolved: ResolvedProfile
    products: list[EligibilityResult]


@router.post("/rules/eligibility", response_model=EligibilityResponse)
def eligibility(req: EligibilityRequest):
    r = resolve(req.profile, req.language)
    return EligibilityResponse(resolved=r, products=check_all(r.profile, req.language))


class BundleRequest(BaseModel):
    profile: ProfileIn
    lines: list[BundleLine]
    auto_fix: bool = False
    language: Language = "en"


class BundleResponse(BaseModel):
    resolved: ResolvedProfile
    validation: BundleValidation


@router.post("/bundles/validate", response_model=BundleResponse)
def bundles_validate(req: BundleRequest):
    r = resolve(req.profile, req.language)
    return BundleResponse(resolved=r, validation=validate_bundle(r.profile, req.lines, req.language, req.auto_fix))


class QuoteRequest(BundleRequest):
    options: PricingOptions = PricingOptions()


class QuoteResponse(BaseModel):
    resolved: ResolvedProfile
    validation: BundleValidation
    quote: Optional[PricedQuote] = None


@router.post("/quotes/price", response_model=QuoteResponse)
def quotes_price(req: QuoteRequest):
    """Validate first; a quote is produced only for a valid bundle."""
    r = resolve(req.profile, req.language)
    v = validate_bundle(r.profile, req.lines, req.language, req.auto_fix)
    quote = price_bundle(v.lines, req.options, req.language) if v.valid else None
    return QuoteResponse(resolved=r, validation=v, quote=quote)


class GstinLookup(BaseModel):
    source: str = store.MOCK_LABEL
    check: dict
    gstin_masked: str
    found: bool
    status: Optional[str] = None
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    constitution: Optional[str] = None
    principal_place_of_business: Optional[str] = None
    state: Optional[str] = None
    registration_date: Optional[str] = None


@router.get("/registry/gstin/{number}", response_model=GstinLookup)
def registry_gstin(number: str):
    chk = check_gstin(number)
    if chk.status != "valid":
        return GstinLookup(check=chk.model_dump(), gstin_masked=mask_gstin(chk.normalised), found=False)
    rec = store.lookup_gstin(chk.normalised)
    if not rec:
        return GstinLookup(check=chk.model_dump(), gstin_masked=mask_gstin(chk.normalised), found=False,
                           status="NotFound")
    return GstinLookup(check=chk.model_dump(), gstin_masked=mask_gstin(rec["gstin"]), found=True,
                       **{k: rec[k] for k in ("status", "legal_name", "trade_name", "constitution",
                                              "principal_place_of_business", "state", "registration_date")})


@router.get("/registry/udyam/{number}")
def registry_udyam(number: str):
    if not udyam_valid(number):
        raise HTTPException(422, "Udyam number must look like UDYAM-XX-00-1234567")
    rec = store.lookup_udyam(number)
    base = {"source": store.MOCK_LABEL, "udyam_masked": mask_udyam(number), "found": bool(rec)}
    if rec:
        base.update({k: v for k, v in rec.items() if k != "udyam_number"})
    return base
