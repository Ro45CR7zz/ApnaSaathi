"""Quotes: a recommendation the owner can adjust, always re-validated and re-priced.

Every quote shown and every change is logged to `quote_events`. That is the data the
pricing experiments (Layer 3) need, which today does not exist for dropped leads.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app import config
from app.advisor.slots import Slots
from app.catalogue.display import business_label, inr, product_display, unit_word
from app.catalogue.loader import load_catalogue
from app.catalogue.models import BundleLine, BusinessProfile
from app.pricing.engine import PricedQuote, PricingOptions, price_bundle
from app.recommender.engine import Excluded, RecLine, recommend
from app.rules.engine import check_product, validate_bundle

SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes (
  id TEXT PRIMARY KEY, session_id TEXT, state_json TEXT NOT NULL, status TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quote_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id TEXT NOT NULL, kind TEXT NOT NULL,
  payload_json TEXT, monthly_total_inr INTEGER, savings_inr INTEGER, at TEXT NOT NULL);
"""

Source = Literal["recommended", "addon", "auto"]


class QLine(BaseModel):
    product_id: str
    qty: int
    need: str
    why: str
    source: Source = "recommended"


class QuoteState(BaseModel):
    id: str
    session_id: Optional[str] = None
    language: str = "en"
    channel: str = "web"
    partner_code: Optional[str] = None
    business_type: Optional[str] = None
    segment: str
    profile: BusinessProfile
    lines: list[QLine]
    available_addons: list[RecLine] = []
    excluded: list[Excluded] = []
    notes: list[str] = []
    options: PricingOptions = PricingOptions()
    base_product: str
    fibre_base: Optional[str] = None  # remembered when switching to wireless, to switch back
    status: Literal["open", "accepted"] = "open"
    order_id: Optional[str] = None


class LineView(BaseModel):
    product_id: str
    product_name: str
    plain: str
    icon: str
    qty: int
    unit: str
    unit_price_inr: int
    monthly_inr: int
    list_monthly_inr: int
    setup_inr: int
    why: str
    source: Source
    removable: bool
    adjustable_qty: bool
    max_qty: int


class AddonView(BaseModel):
    product_id: str
    product_name: str
    plain: str
    icon: str
    qty: int
    unit: str
    list_monthly_inr: int
    why: str


class QuoteView(BaseModel):
    id: str
    status: str
    language: str
    business: str
    city: Optional[str]
    city_tier: int
    segment: str
    lines: list[LineView]
    addons: list[AddonView]
    excluded: list[Excluded]
    notes: list[str]
    notices: list[str] = []
    options: PricingOptions
    selfserve_saving_available: bool
    airfiber_available: bool
    using_airfiber: bool
    priced: PricedQuote
    order_id: Optional[str] = None


class QuoteChange(BaseModel):
    add: Optional[str] = Field(None, description="product_id of an add-on to add")
    remove: Optional[str] = Field(None, description="product_id to remove (not the internet line)")
    set_qty: Optional[dict[str, int]] = Field(None, description="{product_id: qty}")
    commit_extra_12m: Optional[bool] = None
    selfserve_autopay: Optional[bool] = None
    use_airfiber: Optional[bool] = None
    language: Optional[Literal["en", "hi"]] = None


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB_PATH)
    con.executescript(SCHEMA)
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save(q: QuoteState, new: bool = False) -> None:
    with _con() as con:
        if new:
            con.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?)",
                        (q.id, q.session_id, q.model_dump_json(), q.status, _now(), _now()))
        else:
            con.execute("UPDATE quotes SET state_json=?, status=?, updated_at=? WHERE id=?",
                        (q.model_dump_json(), q.status, _now(), q.id))


def log_event(q: QuoteState, kind: str, payload: dict, priced: Optional[PricedQuote] = None) -> None:
    with _con() as con:
        con.execute("INSERT INTO quote_events (quote_id, kind, payload_json, monthly_total_inr, savings_inr, at) "
                    "VALUES (?,?,?,?,?,?)",
                    (q.id, kind, json.dumps(payload, ensure_ascii=False),
                     priced.monthly_total_inr if priced else None,
                     priced.savings_monthly_inr if priced else None, _now()))


def load(quote_id: str) -> Optional[QuoteState]:
    with _con() as con:
        row = con.execute("SELECT state_json FROM quotes WHERE id=?", (quote_id,)).fetchone()
    return QuoteState.model_validate_json(row[0]) if row else None


def events(quote_id: str) -> list[dict]:
    with _con() as con:
        rows = con.execute("SELECT kind, payload_json, monthly_total_inr, savings_inr, at FROM quote_events "
                           "WHERE quote_id=? ORDER BY id", (quote_id,)).fetchall()
    return [{"kind": k, "payload": json.loads(p or "{}"), "monthly_total_inr": m, "savings_inr": s, "at": a}
            for k, p, m, s, a in rows]


def _effective_options(q: QuoteState) -> PricingOptions:
    """Self-serve + autopay saving applies only when the owner completes the journey themselves."""
    return PricingOptions(commit_extra_12m=q.options.commit_extra_12m,
                          selfserve_autopay=q.options.selfserve_autopay and q.channel != "partner")


def _airfiber_ok(q: QuoteState) -> bool:
    return check_product(load_catalogue()["P04"], q.profile).eligible and q.base_product in ("P01", "P02", "P03", "P04")


def view(q: QuoteState, notices: Optional[list[str]] = None) -> QuoteView:
    cat = load_catalogue()
    lang = q.language
    priced = price_bundle([BundleLine(product_id=l.product_id, qty=l.qty) for l in q.lines],
                          _effective_options(q), lang)
    by_id = {p.product_id: p for p in priced.lines}
    lines = []
    for l in q.lines:
        p, pl, d = cat[l.product_id], by_id[l.product_id], product_display(l.product_id, lang)
        is_base = l.product_id == q.base_product
        max_qty = q.profile.sites if p.unit == "per site" else 500
        lines.append(LineView(
            product_id=l.product_id, product_name=p.product_name, plain=d["plain"], icon=d["icon"], qty=l.qty,
            unit=unit_word(p.unit, lang), unit_price_inr=round(pl.monthly_inr / l.qty) if l.qty else 0,
            monthly_inr=pl.monthly_inr, list_monthly_inr=pl.list_monthly_inr, setup_inr=pl.setup_total_inr,
            why=l.why, source=l.source, removable=not is_base,
            adjustable_qty=p.unit != "per site" and p.unit not in ("per account", "per pack"), max_qty=max_qty))
    addons = []
    for a in q.available_addons:
        d = product_display(a.product_id, lang)
        addons.append(AddonView(product_id=a.product_id, product_name=a.product_name, plain=d["plain"],
                                icon=d["icon"], qty=a.qty, unit=unit_word(cat[a.product_id].unit, lang),
                                list_monthly_inr=a.list_monthly_inr or 0, why=a.why))
    return QuoteView(
        id=q.id, status=q.status, language=lang, business=business_label(q.business_type, lang),
        city=q.profile.city, city_tier=q.profile.city_tier, segment=q.segment, lines=lines, addons=addons,
        excluded=q.excluded, notes=q.notes, notices=notices or [], options=q.options,
        selfserve_saving_available=q.channel != "partner", airfiber_available=_airfiber_ok(q),
        using_airfiber=q.base_product == "P04", priced=priced, order_id=q.order_id)


def create_from_slots(slots: Slots, language: str = "en", session_id: Optional[str] = None,
                      channel: str = "web", partner_code: Optional[str] = None) -> QuoteView:
    rec = recommend(slots, language)
    q = QuoteState(
        id="Q" + uuid.uuid4().hex[:9].upper(), session_id=session_id, language=language, channel=channel,
        partner_code=partner_code, business_type=slots.business_type, segment=rec.segment, profile=rec.profile,
        lines=[QLine(product_id=l.product_id, qty=l.qty, need=l.need, why=l.why) for l in rec.lines],
        available_addons=rec.addons, excluded=rec.excluded, notes=rec.notes,
        base_product=rec.lines[0].product_id,
    )
    _save(q, new=True)
    v = view(q)
    log_event(q, "shown", {"lines": [(l.product_id, l.qty) for l in q.lines], "segment": q.segment,
                           "channel": channel}, v.priced)
    return v


def _revalidate(q: QuoteState) -> list[str]:
    """Re-check the whole bundle after a change. Lines that can't work any more (e.g. backup internet
    after switching to wireless) are removed and the owner is told why. We never fix a quote by
    silently adding another internet connection."""
    notices: list[str] = []
    cat = load_catalogue()
    v = validate_bundle(q.profile, [BundleLine(product_id=l.product_id, qty=l.qty) for l in q.lines], q.language)
    for issue in v.issues:
        if issue.product_id and issue.product_id != q.base_product:
            removed = next((l for l in q.lines if l.product_id == issue.product_id), None)
            if removed:
                q.lines.remove(removed)
                q.available_addons = [a for a in q.available_addons if a.product_id != removed.product_id]
                q.excluded.append(Excluded(product_id=removed.product_id,
                                           product_name=cat[removed.product_id].product_name,
                                           need=removed.need, reason_code=issue.code, message=issue.message))
                notices.append(issue.message)
    # Add-ons that can no longer work with the current internet line are hidden too.
    have = {l.product_id for l in q.lines}
    q.available_addons = [a for a in q.available_addons
                          if not cat[a.product_id].requires_one_of or have & set(cat[a.product_id].requires_one_of)]
    return notices


def apply_change(q: QuoteState, ch: QuoteChange) -> QuoteView:
    if q.status != "open":
        raise ValueError("This quote is already accepted.")
    cat = load_catalogue()
    if ch.language:
        q.language = ch.language
    if ch.add:
        addon = next((a for a in q.available_addons if a.product_id == ch.add), None)
        if addon is None:
            raise ValueError(f"{ch.add} is not an available add-on for this quote.")
        q.available_addons.remove(addon)
        q.lines.append(QLine(product_id=addon.product_id, qty=addon.qty, need=addon.need, why=addon.why,
                             source="addon"))
    if ch.remove:
        if ch.remove == q.base_product:
            raise ValueError("The internet line can't be removed; you can switch to wireless instead.")
        line = next((l for l in q.lines if l.product_id == ch.remove), None)
        if line is None:
            raise ValueError(f"{ch.remove} is not in this quote.")
        q.lines.remove(line)
        priced = price_bundle([BundleLine(product_id=line.product_id, qty=line.qty)])
        q.available_addons.insert(0, RecLine(product_id=line.product_id, product_name=cat[line.product_id].product_name,
                                             qty=line.qty, need=line.need, why=line.why,
                                             list_monthly_inr=priced.list_monthly_inr))
    if ch.set_qty:
        for pid, qty in ch.set_qty.items():
            line = next((l for l in q.lines if l.product_id == pid), None)
            if line is None:
                raise ValueError(f"{pid} is not in this quote.")
            if not 1 <= qty <= 500:
                raise ValueError("Quantity must be between 1 and 500.")
            if cat[pid].unit == "per site" and qty > q.profile.sites:
                raise ValueError("This item is one per location.")
            line.qty = qty
    if ch.commit_extra_12m is not None:
        q.options.commit_extra_12m = ch.commit_extra_12m
    if ch.selfserve_autopay is not None:
        q.options.selfserve_autopay = ch.selfserve_autopay
    if ch.use_airfiber is not None:
        if ch.use_airfiber and not _airfiber_ok(q):
            raise ValueError("Wireless 5G internet isn't available for this business.")
        base = next(l for l in q.lines if l.product_id == q.base_product)
        if ch.use_airfiber and q.base_product != "P04":
            q.fibre_base = q.base_product
            base.product_id, q.base_product = "P04", "P04"
            base.why = product_display("P04", q.language)["plain"]
        elif not ch.use_airfiber and q.base_product == "P04":
            prev = q.fibre_base or "P01"
            base.product_id, q.base_product = prev, prev
            base.why = product_display(prev, q.language)["plain"]
            # Items removed only because of the wireless switch become available again as add-ons.
            back = [e for e in q.excluded if e.reason_code == "DEPENDENCY_MISSING"
                    and prev in cat[e.product_id].requires_one_of]
            for e in back:
                q.excluded.remove(e)
                qty = q.profile.sites if cat[e.product_id].unit == "per site" else 1
                q.available_addons.insert(0, RecLine(
                    product_id=e.product_id, product_name=e.product_name, qty=qty, need=e.need,
                    why=product_display(e.product_id, q.language)["plain"],
                    list_monthly_inr=price_bundle([BundleLine(product_id=e.product_id, qty=qty)]).list_monthly_inr))
    notices = _revalidate(q)
    _save(q)
    v = view(q, notices)
    log_event(q, "change", ch.model_dump(exclude_none=True), v.priced)
    return v


def share_text(q: QuoteState) -> str:
    v = view(q)
    p = v.priced
    if q.language == "hi":
        head = f"apnaSaathi कोटेशन ({v.business}, {v.city})"
        lines = [f"• {l.plain} ({l.product_name}) × {l.qty}: ₹{inr(l.monthly_inr)}/महीना" for l in v.lines]
        tail = [f"हर महीने: ₹{inr(p.monthly_total_inr)} (GST सहित)", f"एक बार का सेटअप: ₹{inr(p.one_time_total_inr)} (GST सहित)",
                f"कॉन्ट्रैक्ट: {p.contract_months} महीने", f"कोटेशन नंबर: {q.id}"]
    else:
        head = f"apnaSaathi quote ({v.business}, {v.city})"
        lines = [f"• {l.plain} ({l.product_name}) × {l.qty}: ₹{inr(l.monthly_inr)}/month" for l in v.lines]
        tail = [f"Every month: ₹{inr(p.monthly_total_inr)} incl. GST", f"One-time setup: ₹{inr(p.one_time_total_inr)} incl. GST",
                f"Contract: {p.contract_months} months", f"Quote number: {q.id}"]
    log_event(q, "share", {}, p)
    return "\n".join([head, *lines, "", *tail])
