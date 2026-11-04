"""Domain models shared by the catalogue, rules and pricing modules."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Segment = Literal["micro", "prof", "multi", "mfg"]
GstinStatus = Literal["Active", "Cancelled", "Suspended", "NotFound", "None"]
Language = Literal["en", "hi"]

SEGMENT_NAMES = {
    "micro": "Micro retail & services",
    "prof": "Professional offices",
    "multi": "Small multi-site businesses",
    "mfg": "Small manufacturers",
}
SEGMENT_CODES = {v: k for k, v in SEGMENT_NAMES.items()}


class Product(BaseModel):
    product_id: str
    category: str
    product_name: str
    description: str
    unit: str
    price_min_inr_per_month: int
    price_max_inr_per_month: int
    one_time_setup_inr: int
    min_contract_months: int
    available_city_tiers: list[int]
    min_employees: int
    min_sites: int
    requires_gstin: bool
    requires_one_of: list[str]
    typical_install_days: int
    target_segments: list[Segment]


class BusinessProfile(BaseModel):
    """What the rules engine needs to know about a business.

    `gstin_status` is resolved from the (mock) registry, never taken from the user.
    """

    segment: Segment
    city: Optional[str] = None
    city_tier: Literal[1, 2]
    employees: int = Field(ge=1)
    sites: int = Field(ge=1)
    gstin_status: GstinStatus = "None"


class BundleLine(BaseModel):
    product_id: str
    qty: int = Field(ge=1)
