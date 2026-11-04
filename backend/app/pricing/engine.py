"""Deterministic pricing: catalogue list price + "earned savings".

Every rupee comes from product_catalogue.csv and config/pricing.yaml.
The same rules apply to every customer (no willingness-to-pay pricing).
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache

import yaml
from pydantic import BaseModel

from app import config
from app.catalogue.loader import load_catalogue
from app.catalogue.models import BundleLine


def rupees(x: float | Decimal) -> int:
    """Round half up to whole rupees (Python's round() uses banker's rounding)."""
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@lru_cache(maxsize=1)
def load_pricing_config() -> dict:
    with open(config.PRICING_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


class PricingOptions(BaseModel):
    commit_extra_12m: bool = False
    selfserve_autopay: bool = False


class SavingLine(BaseModel):
    code: str
    label: str
    amount_inr: int


class QuoteLine(BaseModel):
    product_id: str
    product_name: str
    unit: str
    qty: int
    catalogue_min_inr: int
    catalogue_max_inr: int
    list_unit_inr: int
    list_monthly_inr: int
    savings_monthly_inr: int
    monthly_inr: int
    setup_unit_inr: int
    setup_total_inr: int
    min_contract_months: int
    typical_install_days: int


class PricedQuote(BaseModel):
    lines: list[QuoteLine]
    savings: list[SavingLine]
    earned_savings_fraction: float
    list_monthly_inr: int
    savings_monthly_inr: int
    monthly_subtotal_inr: int
    monthly_gst_inr: int
    monthly_total_inr: int
    one_time_subtotal_inr: int
    one_time_gst_inr: int
    one_time_total_inr: int
    contract_months: int
    gst_rate: float
    assumptions: list[str]


def earned_weights(lines: list[BundleLine], options: PricingOptions) -> dict[str, float]:
    cfg = load_pricing_config()["earned_savings"]
    weights: dict[str, float] = {}
    if options.commit_extra_12m:
        weights["commit_extra_12m"] = cfg["commit_extra_12m"]["weight"]
    if len({l.product_id for l in lines}) >= cfg["bundle_3plus"]["min_distinct_products"]:
        weights["bundle_3plus"] = cfg["bundle_3plus"]["weight"]
    if options.selfserve_autopay:
        weights["selfserve_autopay"] = cfg["selfserve_autopay"]["weight"]
    total = sum(weights.values())
    if total > 1:  # never go below the catalogue minimum
        weights = {k: v / total for k, v in weights.items()}
    return weights


def price_bundle(lines: list[BundleLine], options: PricingOptions | None = None, lang: str = "en") -> PricedQuote:
    """Price an already-validated bundle. Validation is the rules engine's job."""
    options = options or PricingOptions()
    cfg = load_pricing_config()
    catalogue = load_catalogue()
    weights = earned_weights(lines, options)
    position = Decimal(str(cfg["list_price_position"]))

    quote_lines: list[QuoteLine] = []
    saving_totals = {code: 0 for code in weights}
    for line in lines:
        p = catalogue[line.product_id]
        pmin, pmax = p.price_min_inr_per_month, p.price_max_inr_per_month
        list_unit = rupees(Decimal(pmin) + (Decimal(pmax) - Decimal(pmin)) * position)
        gap = Decimal(list_unit - pmin)
        # Round the line's total saving once (capped at the gap to the minimum), then split it
        # across reasons; the last reason absorbs the rounding remainder.
        total_w = Decimal(str(sum(weights.values())))
        line_savings = min(rupees(gap * total_w * line.qty), int(gap) * line.qty)
        allocated = 0
        codes = list(weights)
        for idx, code in enumerate(codes):
            if idx == len(codes) - 1:
                s = line_savings - allocated
            else:
                s = rupees(gap * Decimal(str(weights[code])) * line.qty)
                s = min(s, line_savings - allocated)
            saving_totals[code] += s
            allocated += s
        list_monthly = list_unit * line.qty
        quote_lines.append(QuoteLine(
            product_id=p.product_id, product_name=p.product_name, unit=p.unit, qty=line.qty,
            catalogue_min_inr=pmin, catalogue_max_inr=pmax, list_unit_inr=list_unit,
            list_monthly_inr=list_monthly, savings_monthly_inr=line_savings,
            monthly_inr=list_monthly - line_savings,
            setup_unit_inr=p.one_time_setup_inr, setup_total_inr=p.one_time_setup_inr * line.qty,
            min_contract_months=p.min_contract_months, typical_install_days=p.typical_install_days,
        ))
        # Guard: never below catalogue minimum.
        assert quote_lines[-1].monthly_inr >= pmin * line.qty, "price below catalogue minimum"

    label_key = "label_hi" if lang == "hi" else "label_en"
    savings = [SavingLine(code=c, label=cfg["earned_savings"][c][label_key], amount_inr=a)
               for c, a in saving_totals.items()]

    gst = Decimal(str(cfg["gst_rate"]))
    list_monthly = sum(l.list_monthly_inr for l in quote_lines)
    savings_monthly = sum(l.savings_monthly_inr for l in quote_lines)
    monthly_sub = list_monthly - savings_monthly
    one_time_sub = sum(l.setup_total_inr for l in quote_lines)
    base_term = max((l.min_contract_months for l in quote_lines), default=0)
    term = base_term + (cfg["commit_extra_months"] if options.commit_extra_12m else 0)

    return PricedQuote(
        lines=quote_lines, savings=savings, earned_savings_fraction=round(sum(weights.values()), 4),
        list_monthly_inr=list_monthly, savings_monthly_inr=savings_monthly,
        monthly_subtotal_inr=monthly_sub, monthly_gst_inr=rupees(monthly_sub * gst),
        monthly_total_inr=monthly_sub + rupees(monthly_sub * gst),
        one_time_subtotal_inr=one_time_sub, one_time_gst_inr=rupees(one_time_sub * gst),
        one_time_total_inr=one_time_sub + rupees(one_time_sub * gst),
        contract_months=term, gst_rate=float(gst),
        assumptions=[
            "List price = midpoint of the catalogue price range (assumption A1).",
            "Earned-savings weights are initial assumptions to be tested (A2).",
            "Catalogue prices are treated as excluding GST; 18% GST shown separately (A3).",
        ],
    )
