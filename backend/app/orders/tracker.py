"""Order tracker: one place where the owner sees status, dates, pending actions and their bill.

Installation and payment events are SIMULATED in this prototype (back-office demo controls);
in production they would come from field-force, payment and provisioning systems.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel

from app import audit, config
from app.catalogue.display import business_label, inr, product_display
from app.catalogue.loader import load_catalogue
from app.catalogue.models import BundleLine
from app.pricing.engine import PricingOptions, price_bundle

NOTIF_SCHEMA = """CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL, channel TEXT NOT NULL, language TEXT,
  text TEXT NOT NULL, at TEXT NOT NULL);"""

TIER2_BUFFER_DAYS = 2
FIBRE = {"P01", "P02", "P03"}
NEEDS_FIBRE_OR_LINE = {"P09", "P10", "P11", "P21"}  # dependants that can't run on wireless 5G

Step = Literal["done", "current", "upcoming", "attention"]

MSG: dict[str, tuple[str, str]] = {
    "placed": ("Order {id} placed. Next: upload your documents.", "ऑर्डर {id} हो गया। अगला कदम: डॉक्यूमेंट अपलोड करें।"),
    "KYC_VERIFIED": ("Documents verified. Pay the first bill to schedule installation.",
                     "डॉक्यूमेंट की जाँच पूरी। इंस्टॉलेशन तय करने के लिए पहला बिल भरें।"),
    "KYC_ACTION_NEEDED": ("Some documents need fixing. Open apnaSaathi to see what to do.",
                          "कुछ डॉक्यूमेंट ठीक करने हैं। क्या करना है, apnaSaathi में देखें।"),
    "KYC_MANUAL_REVIEW": ("A specialist is checking your documents, usually within one working day.",
                          "एक्सपर्ट आपके डॉक्यूमेंट जाँच रहे हैं, आमतौर पर एक कामकाजी दिन में।"),
    "KYC_BLOCKED": ("Your GSTIN can't be used. You can continue with products that don't need GST.",
                    "आपका GSTIN इस्तेमाल नहीं हो सकता। बिना GST वाले प्रोडक्ट के साथ आगे बढ़ सकते हैं।"),
    "KYC_REJECTED": ("We couldn't verify your documents. Our team will call you.",
                     "आपके डॉक्यूमेंट वेरिफ़ाई नहीं हो सके। हमारी टीम आपको कॉल करेगी।"),
    "CONFIRMED": ("Payment received. Everything should be working by {eta}.", "पेमेंट मिल गया। {eta} तक सब चालू होने की उम्मीद है।"),
    "PAYMENT_FAILED": ("Payment didn't go through. Please try again; nothing was charged.",
                       "पेमेंट नहीं हो पाया। कृपया फिर से कोशिश करें; कोई पैसा नहीं कटा।"),
    "FULFILLING": ("Technician visit booked for {visit}. You don't need to do anything else.",
                   "टेक्नीशियन {visit} को आएँगे। आपको और कुछ नहीं करना है।"),
    "DELAYED": ("Sorry, installation moved to {eta} ({reason}).", "माफ़ कीजिए, इंस्टॉलेशन अब {eta} को होगा ({reason})।"),
    "FEASIBILITY_FAILED": ("Fibre can't reach your shop. Switch to wireless 5G internet in one tap; it costs less.",
                           "आपकी दुकान तक फ़ाइबर नहीं पहुँच सकता। एक टैप में बिना तार वाले 5G इंटरनेट पर जाएँ; यह सस्ता है।"),
    "SWAPPED": ("Switched to wireless 5G internet. New monthly total {total}.",
                "बिना तार वाले 5G इंटरनेट पर बदल दिया। नया मासिक बिल {total}।"),
    "ACTIVE": ("All services are working. Your first monthly bill: {total} on {bill}.",
               "सारी सेवाएँ चालू हैं। पहला मासिक बिल: {total}, {bill} को।"),
}
REASONS = {"technician": ("technician unavailable", "टेक्नीशियन उपलब्ध नहीं"),
           "permission": ("building permission pending", "बिल्डिंग की अनुमति बाकी"),
           "material": ("equipment delayed", "उपकरण आने में देरी")}

STEPS = [("placed", "Order placed", "ऑर्डर हुआ"), ("docs", "Documents verified", "डॉक्यूमेंट जाँचे गए"),
         ("paid", "Payment", "पेमेंट"), ("scheduled", "Installation booked", "इंस्टॉलेशन तय"),
         ("installed", "Installed", "लग गया"), ("active", "Service working", "सेवा चालू")]


class TrackerStep(BaseModel):
    key: str
    label: str
    status: Step
    date: Optional[str] = None


class TrackerLine(BaseModel):
    product_id: str
    product_name: str
    plain: str
    icon: str
    qty: int
    monthly_inr: int
    state: str
    expected_ready: str
    note: Optional[str] = None


class PendingAction(BaseModel):
    kind: Literal["upload_documents", "fix_documents", "pay", "retry_payment", "switch_airfiber", "wait", "call_us"]
    text: str
    amount_inr: Optional[int] = None


class Notification(BaseModel):
    text: str
    at: str
    channel: str


class Bill(BaseModel):
    monthly_total_inr: int
    one_time_total_inr: int
    first_payment_inr: int
    contract_months: int
    next_bill_date: Optional[str] = None


class TrackerView(BaseModel):
    order_id: str
    state: str
    language: str
    business: str
    city: Optional[str]
    steps: list[TrackerStep]
    lines: list[TrackerLine]
    pending: list[PendingAction]
    expected_activation: str
    notifications: list[Notification]
    bill: Bill
    simulated: bool = True


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB_PATH)
    con.execute(NOTIF_SCHEMA)
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(order_id: str) -> Optional[dict]:
    with _con() as con:
        row = con.execute("SELECT state, language, snapshot_json, channel FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        return None
    state, lang, snap, channel = row
    s = json.loads(snap)
    for l in s["lines"]:
        l.setdefault("state", "WAITING")
    return {"id": order_id, "state": state, "lang": lang if lang in ("en", "hi") else "en", "snap": s, "channel": channel}


def _store(o: dict, state: str, note: Optional[str] = None) -> None:
    with _con() as con:
        con.execute("UPDATE orders SET state=?, snapshot_json=?, updated_at=? WHERE id=?",
                    (state, json.dumps(o["snap"], ensure_ascii=False), _now(), o["id"]))
        con.execute("INSERT INTO order_events (order_id, state, note, at) VALUES (?,?,?,?)", (o["id"], state, note, _now()))
    o["state"] = state


def notify(order_id: str, key: str, lang: str, **p) -> None:
    """Proactive update. Prototype: stored and shown in-app and in the WhatsApp-style simulator (no SMS sent)."""
    en, hi = MSG[key]
    text = (hi if lang == "hi" else en).format(**p)
    with _con() as con:
        con.execute("INSERT INTO notifications (order_id, channel, language, text, at) VALUES (?,?,?,?,?)",
                    (order_id, "whatsapp", lang, text, _now()))


def _fmt_date(d: str, lang: str) -> str:
    dt = date.fromisoformat(d)
    months_hi = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
    return f"{dt.day} {months_hi[dt.month - 1]}" if lang == "hi" else dt.strftime("%d %b").lstrip("0")


def _eta(o: dict) -> str:
    return max(l["expected_ready"] for l in o["snap"]["lines"] if l["state"] != "CANCELLED")


def _events(order_id: str) -> dict[str, str]:
    with _con() as con:
        rows = con.execute("SELECT state, at FROM order_events WHERE order_id=? ORDER BY id", (order_id,)).fetchall()
    first: dict[str, str] = {}
    for st, at in rows:
        first.setdefault(st, at[:10])
    return first


def _kyc_fix_message(order_id: str, lang: str) -> Optional[str]:
    with _con() as con:
        try:
            row = con.execute("SELECT state_json FROM kyc_cases WHERE order_id=? ORDER BY updated_at DESC LIMIT 1",
                              (order_id,)).fetchone()
        except sqlite3.OperationalError:
            return None
    if not row:
        return None
    checks = json.loads(row[0]).get("checks", [])
    fails = [c["message"] for c in checks if c["status"] == "fail" and c.get("action") == "fix"]
    return fails[0] if fails else None


def view(order_id: str) -> Optional[TrackerView]:
    o = _load(order_id)
    if o is None:
        return None
    lang, s, state = o["lang"], o["snap"], o["state"]
    ev = _events(order_id)
    cat = load_catalogue()
    first_payment = s["one_time_total_inr"] + s["monthly_total_inr"]

    # Timeline.
    order_rank = {"KYC_PENDING": 1, "KYC_ACTION_NEEDED": 1, "KYC_MANUAL_REVIEW": 1, "KYC_BLOCKED": 1, "KYC_REJECTED": 1,
                  "KYC_VERIFIED": 2, "PAYMENT_FAILED": 2, "CONFIRMED": 3, "FULFILLING": 4, "ON_HOLD": 4, "ACTIVE": 6}
    rank = order_rank.get(state, 1)
    if state == "FULFILLING" and any(l["state"] == "INSTALLED" for l in s["lines"]):
        rank = 5
    attention = state in ("KYC_ACTION_NEEDED", "KYC_BLOCKED", "KYC_REJECTED", "PAYMENT_FAILED", "ON_HOLD")
    dates = {"placed": ev.get("QUOTE_ACCEPTED"), "docs": ev.get("KYC_VERIFIED"), "paid": ev.get("CONFIRMED"),
             "scheduled": ev.get("FULFILLING"), "installed": None, "active": ev.get("ACTIVE")}
    steps = []
    for i, (key, en, hi) in enumerate(STEPS):
        status: Step = "done" if i < rank else "current" if i == rank else "upcoming"
        if status == "current" and attention:
            status = "attention"
        if state == "ACTIVE":
            status = "done"
        steps.append(TrackerStep(key=key, label=hi if lang == "hi" else en, status=status, date=dates.get(key)))

    lines = [TrackerLine(product_id=l["product_id"], product_name=cat[l["product_id"]].product_name,
                         plain=product_display(l["product_id"], lang)["plain"], icon=product_display(l["product_id"], lang)["icon"],
                         qty=l["qty"], monthly_inr=l["monthly_inr"], state=l["state"], expected_ready=l["expected_ready"],
                         note=l.get("note")) for l in s["lines"]]

    def T(en: str, hi: str) -> str:
        return hi if lang == "hi" else en

    pending: list[PendingAction] = []
    if state == "KYC_PENDING":
        pending.append(PendingAction(kind="upload_documents", text=T("Upload your documents", "अपने डॉक्यूमेंट अपलोड करें")))
    elif state == "KYC_ACTION_NEEDED":
        pending.append(PendingAction(kind="fix_documents", text=_kyc_fix_message(order_id, lang)
                                     or T("Fix your documents", "अपने डॉक्यूमेंट ठीक करें")))
    elif state == "KYC_MANUAL_REVIEW":
        pending.append(PendingAction(kind="wait", text=T("A specialist is checking your documents. Nothing to do now.",
                                                         "एक्सपर्ट डॉक्यूमेंट जाँच रहे हैं। अभी कुछ करने की ज़रूरत नहीं।")))
    elif state in ("KYC_BLOCKED", "KYC_REJECTED"):
        pending.append(PendingAction(kind="call_us", text=T("Talk to us about your options", "अपने विकल्पों के बारे में हमसे बात करें")))
    elif state in ("KYC_VERIFIED", "PAYMENT_FAILED"):
        pending.append(PendingAction(kind="pay" if state == "KYC_VERIFIED" else "retry_payment", amount_inr=first_payment,
                                     text=T(f"Pay ₹{inr(first_payment)} (setup + first month) to book installation",
                                            f"इंस्टॉलेशन तय करने के लिए ₹{inr(first_payment)} (सेटअप + पहला महीना) भरें")))
    elif state == "ON_HOLD" and any(l["state"] == "FEASIBILITY_FAILED" for l in s["lines"]):
        pending.append(PendingAction(kind="switch_airfiber", text=MSG["FEASIBILITY_FAILED"][1 if lang == "hi" else 0]))

    with _con() as con:
        notes = con.execute("SELECT text, at, channel FROM notifications WHERE order_id=? ORDER BY id DESC",
                            (order_id,)).fetchall()
    next_bill = (date.fromisoformat(ev["ACTIVE"]) + timedelta(days=30)).isoformat() if "ACTIVE" in ev else None
    return TrackerView(order_id=order_id, state=state, language=lang, business=business_label(s.get("business_type"), lang),
                       city=s.get("city"), steps=steps, lines=lines, pending=pending, expected_activation=_eta(o),
                       notifications=[Notification(text=t, at=a, channel=c) for t, a, c in notes],
                       bill=Bill(monthly_total_inr=s["monthly_total_inr"], one_time_total_inr=s["one_time_total_inr"],
                                 first_payment_inr=first_payment, contract_months=s["contract_months"],
                                 next_bill_date=next_bill))


def _schedule_from_today(o: dict, today: date) -> None:
    buffer = TIER2_BUFFER_DAYS if o["snap"].get("profile", {}).get("city_tier") == 2 else 0
    for l in o["snap"]["lines"]:
        if l["state"] in ("CANCELLED", "ACTIVE"):
            continue
        l["expected_ready"] = (today + timedelta(days=l["install_days"] + (buffer if l["install_days"] > 1 else 0))).isoformat()
        l["state"] = "SCHEDULED"


def pay(order_id: str, succeed: bool = True, today: Optional[date] = None, actor: str = "customer") -> TrackerView:
    """SIMULATED payment of setup + first month."""
    o = _load(order_id)
    if o is None:
        raise LookupError("order not found")
    if o["state"] not in ("KYC_VERIFIED", "PAYMENT_FAILED"):
        raise ValueError("Payment is not due for this order.")
    if not succeed:
        _store(o, "PAYMENT_FAILED", "simulated payment failure")
        notify(order_id, "PAYMENT_FAILED", o["lang"])
    else:
        _schedule_from_today(o, today or date.today())
        _store(o, "CONFIRMED", "simulated payment")
        notify(order_id, "CONFIRMED", o["lang"], eta=_fmt_date(_eta(o), o["lang"]))
    audit.record(actor, "payment_simulated", order_id, success=succeed)
    return view(order_id)


def switch_to_airfiber(order_id: str, actor: str = "customer") -> TrackerView:
    o = _load(order_id)
    if o is None:
        raise LookupError("order not found")
    s = o["snap"]
    failed = next((l for l in s["lines"] if l["state"] == "FEASIBILITY_FAILED"), None)
    if failed is None:
        raise ValueError("Nothing to switch.")
    failed.update(product_id="P04", install_days=load_catalogue()["P04"].typical_install_days, state="SCHEDULED", note=None)
    failed["expected_ready"] = (date.today() + timedelta(days=failed["install_days"])).isoformat()
    for l in s["lines"]:
        if l["product_id"] in NEEDS_FIBRE_OR_LINE and l["state"] != "CANCELLED":
            l["state"], l["note"] = "CANCELLED", "needs a fibre line"
    active = [l for l in s["lines"] if l["state"] != "CANCELLED"]
    priced = price_bundle([BundleLine(product_id=l["product_id"], qty=l["qty"]) for l in active],
                          PricingOptions(**s.get("options", {})), o["lang"])
    by = {p.product_id: p.monthly_inr for p in priced.lines}
    for l in active:
        l["monthly_inr"] = by[l["product_id"]]
    s["monthly_total_inr"] = priced.monthly_total_inr
    _store(o, "FULFILLING", "switched to wireless 5G")
    notify(order_id, "SWAPPED", o["lang"], total=f"₹{inr(priced.monthly_total_inr)}")
    audit.record(actor, "switched_to_airfiber", order_id)
    return view(order_id)


SimEvent = Literal["advance", "delay", "feasibility_failed", "payment_failed"]


def simulate(order_id: str, event: SimEvent, reason: str = "technician", today: Optional[date] = None) -> TrackerView:
    """Back-office demo control. Every call is audited and labelled as simulated."""
    o = _load(order_id)
    if o is None:
        raise LookupError("order not found")
    today = today or date.today()
    lang, s, state = o["lang"], o["snap"], o["state"]
    live = [l for l in s["lines"] if l["state"] != "CANCELLED"]
    if event == "payment_failed":
        return pay(order_id, succeed=False, actor="ops:simulated")
    if event == "delay":
        for l in live:
            if l["state"] != "ACTIVE":
                l["expected_ready"] = (date.fromisoformat(l["expected_ready"]) + timedelta(days=3)).isoformat()
        en, hi = REASONS.get(reason, REASONS["technician"])
        _store(o, state, f"delay: {en}")
        notify(order_id, "DELAYED", lang, eta=_fmt_date(_eta(o), lang), reason=hi if lang == "hi" else en)
    elif event == "feasibility_failed":
        fibre = next((l for l in live if l["product_id"] in FIBRE and l["state"] != "ACTIVE"), None)
        if fibre is None:
            raise ValueError("No fibre line waiting for installation.")
        fibre["state"], fibre["note"] = "FEASIBILITY_FAILED", "fibre not available at this address"
        _store(o, "ON_HOLD", "site not feasible for fibre")
        notify(order_id, "FEASIBILITY_FAILED", lang)
    elif event == "advance":
        if state in ("KYC_VERIFIED", "PAYMENT_FAILED"):
            return pay(order_id, today=today, actor="ops:simulated")
        if state == "CONFIRMED":
            physical = [l for l in live if l["install_days"] > 1]
            visit = min((l["expected_ready"] for l in physical), default=_eta(o))
            for l in live:
                l["state"] = "INSTALL_VISIT" if l["install_days"] > 1 else "ACTIVE"
            _store(o, "FULFILLING", "installation booked")
            notify(order_id, "FULFILLING", lang, visit=_fmt_date(visit, lang))
        elif state == "FULFILLING":
            if any(l["state"] == "INSTALL_VISIT" for l in live):
                for l in live:
                    if l["state"] == "INSTALL_VISIT":
                        l["state"] = "INSTALLED"
                _store(o, "FULFILLING", "installed")
            else:
                for l in live:
                    l["state"] = "ACTIVE"
                _store(o, "ACTIVE", "all services active")
                next_bill = (today + timedelta(days=30)).isoformat()
                notify(order_id, "ACTIVE", lang, total=f"₹{inr(s['monthly_total_inr'])}", bill=_fmt_date(next_bill, lang))
        else:
            raise ValueError(f"Nothing to advance from {state}.")
    audit.record("ops:simulated", f"simulated_{event}", order_id)
    return view(order_id)
