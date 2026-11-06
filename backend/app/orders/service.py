"""Orders: created when the owner accepts a quote. The Tracker (Phase 8) builds on this.

Only the minimum contact details are kept (name + mobile), and they are masked in every response.
"""
from __future__ import annotations

import json
import random
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app import config
from app.catalogue.display import business_label, product_display
from app.catalogue.loader import load_catalogue
from app.common.masking import mask_name, mask_phone
from app.quotes import service as quotes

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY, quote_id TEXT NOT NULL, state TEXT NOT NULL, contact_name TEXT NOT NULL,
  contact_mobile TEXT NOT NULL, language TEXT, channel TEXT, partner_code TEXT,
  snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL, state TEXT NOT NULL, note TEXT, at TEXT NOT NULL);
"""

KYC_DAYS_ESTIMATE = 1   # lookup-first KYC target (Phase 7)
TIER2_BUFFER_DAYS = 2   # assumption A8: tier-2 installs took ~1.8 days longer in the data


class Contact(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    mobile: str
    consent_contact: bool

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v).strip()
        if not re.fullmatch(r"[A-Za-zऀ-ॿ .'-]{2,60}", v):
            raise ValueError("Please enter a name using letters only.")
        return v

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            raise ValueError("Please enter a 10-digit Indian mobile number.")
        return digits

    @field_validator("consent_contact")
    @classmethod
    def _consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("We need your permission to contact you about this order.")
        return v


class OrderLineView(BaseModel):
    product_id: str
    product_name: str
    plain: str
    icon: str
    qty: int
    monthly_inr: int
    install_days: int
    expected_ready: date


class OrderView(BaseModel):
    id: str
    quote_id: str
    state: str
    business: str
    city: Optional[str]
    contact_name_masked: str
    contact_mobile_masked: str
    lines: list[OrderLineView]
    monthly_total_inr: int
    one_time_total_inr: int
    contract_months: int
    expected_activation: date
    next_step: str
    created_at: str


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB_PATH)
    con.executescript(SCHEMA)
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return "AS" + "".join(random.choices("0123456789", k=7))


def accept(quote_id: str, contact: Contact, today: Optional[date] = None) -> OrderView:
    q = quotes.load(quote_id)
    if q is None:
        raise LookupError("quote not found")
    if q.status != "open":
        raise ValueError("This quote is already accepted.")
    today = today or date.today()
    v = quotes.view(q)
    buffer = TIER2_BUFFER_DAYS if q.profile.city_tier == 2 else 0
    cat = load_catalogue()
    lines = []
    for l in v.lines:
        days = cat[l.product_id].typical_install_days
        lines.append({"product_id": l.product_id, "qty": l.qty, "monthly_inr": l.monthly_inr,
                      "install_days": days,
                      "expected_ready": (today + timedelta(days=KYC_DAYS_ESTIMATE + days + buffer)).isoformat()})
    snapshot = {"lines": lines, "business_type": q.business_type, "city": q.profile.city,
                "language": q.language, "monthly_total_inr": v.priced.monthly_total_inr,
                "one_time_total_inr": v.priced.one_time_total_inr, "contract_months": v.priced.contract_months,
                "options": q.options.model_dump(), "segment": q.segment, "profile": q.profile.model_dump()}
    order_id = _new_id()
    with _con() as con:
        con.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (order_id, q.id, "KYC_PENDING", contact.name, contact.mobile, q.language, q.channel,
                     q.partner_code, json.dumps(snapshot, ensure_ascii=False), _now(), _now()))
        con.execute("INSERT INTO order_events (order_id, state, note, at) VALUES (?,?,?,?)",
                    (order_id, "QUOTE_ACCEPTED", None, _now()))
        con.execute("INSERT INTO order_events (order_id, state, note, at) VALUES (?,?,?,?)",
                    (order_id, "KYC_PENDING", None, _now()))
    q.status, q.order_id = "accepted", order_id
    quotes._save(q)
    from app.orders import tracker  # local import: tracker imports this module's tables
    tracker.notify(order_id, "placed", q.language if q.language in ("en", "hi") else "en", id=order_id)
    quotes.log_event(q, "accepted", {"order_id": order_id}, v.priced)
    return get(order_id)


def get(order_id: str) -> Optional[OrderView]:
    with _con() as con:
        row = con.execute("SELECT id, quote_id, state, contact_name, contact_mobile, language, snapshot_json, "
                          "created_at FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        return None
    oid, qid, state, name, mobile, lang, snap, created = row
    s = json.loads(snap)
    cat = load_catalogue()
    lines = [OrderLineView(product_id=l["product_id"], product_name=cat[l["product_id"]].product_name,
                           plain=product_display(l["product_id"], lang)["plain"],
                           icon=product_display(l["product_id"], lang)["icon"], qty=l["qty"],
                           monthly_inr=l["monthly_inr"], install_days=l["install_days"],
                           expected_ready=date.fromisoformat(l["expected_ready"])) for l in s["lines"]]
    next_step = {"en": "Upload your documents to start installation.",
                 "hi": "इंस्टॉलेशन शुरू करने के लिए अपने डॉक्यूमेंट अपलोड करें।"}[lang if lang in ("en", "hi") else "en"]
    return OrderView(id=oid, quote_id=qid, state=state, business=business_label(s.get("business_type"), lang),
                     city=s.get("city"), contact_name_masked=mask_name(name), contact_mobile_masked=mask_phone(mobile),
                     lines=lines, monthly_total_inr=s["monthly_total_inr"], one_time_total_inr=s["one_time_total_inr"],
                     contract_months=s["contract_months"],
                     expected_activation=max(l.expected_ready for l in lines), next_step=next_step,
                     created_at=created)


def contact_and_language(order_id: str) -> Optional[tuple[str, str]]:
    """Raw contact name (for the signatory check) and language. Never returned by the API."""
    with _con() as con:
        row = con.execute("SELECT contact_name, language FROM orders WHERE id=?", (order_id,)).fetchone()
    return (row[0], row[1]) if row else None
