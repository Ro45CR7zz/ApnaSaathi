"""Back office for sales, partners and operations.

- Stalled leads ranked by propensity, each with a next best action (who to call, what to send).
- Offer suggestions (Layer 3): expected value of each PUBLISHED offer under labelled assumptions.
- Manual KYC review queue with audited document viewing and decisions.
- "Call me" requests from the Advisor, and the live funnel.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

import pandas as pd
import yaml
from pydantic import BaseModel

from app import audit, config
from app.backoffice import propensity

OFFERS_CONFIG = config.CONFIG_DIR / "offers.yaml"

NBA = {  # next best action by recorded drop reason (dataset leads)
    "Owner had no time for a visit": "Send the apnaSaathi link on WhatsApp: no visit needed",
    "Visit not scheduled by sales": "Send the self-serve link today; book a visit only if asked",
    "Quote too complex to understand": "Send an apnaSaathi quote: one monthly price, plain words",
    "Quote took too long to arrive": "Send an instant quote link now",
    "Price too high": "Call: show the 24-month and autopay savings (published offers)",
    "Competitor offered cheaper plan": "Call: compare like-for-like; show earned savings",
    "Decided to wait": "WhatsApp reminder in 2 weeks with their saved quote",
    "Missing GST or Udyam document": "Offer the non-GST bundle; share free Udyam registration link",
    "Found paperwork too long": "Send the lookup-first KYC link (GSTIN pre-fills details)",
    "Authorised signatory not available": "Explain authorisation letter; let owner finish on phone later",
    "Document details did not match": "Assisted KYC call: check GSTIN and certificate together",
    "Unreachable after 3 attempts": "Try WhatsApp instead of calls",
    "Wrong or invalid number": "Re-confirm contact via partner/source",
    "Not interested on first call": "Low priority: add to WhatsApp campaign",
    "Locked in with current provider": "Note contract end date; reach out before renewal",
    "Only wanted a mobile plan": "Offer business SIMs online; suggest add-ons later",
    "Installation delayed beyond 21 days": "Escalate to field ops; apologise with a firm date",
    "Customer cancelled before install": "Call to understand why; offer wireless 5G if install was the issue",
    "Site not feasible for fibre": "Offer wireless 5G internet (AirFiber)",
    "First payment failed": "Send payment link with autopay option",
}

SEGMENT_MRR = {"Micro retail & services": 2470, "Professional offices": 6575,  # median activated MRR in the data
               "Small multi-site businesses": 28080, "Small manufacturers": 15910}


class LeadRow(BaseModel):
    lead_id: str
    business_name: str
    business_type: str
    segment: str
    city: str
    lead_source: str
    stage_reached: str
    drop_reason: Optional[str]
    score: float
    next_best_action: str
    offer: Optional[dict] = None


def _con() -> sqlite3.Connection:
    return sqlite3.connect(config.DB_PATH)


def _offers_cfg() -> dict:
    with open(OFFERS_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def offer_suggestion(score: float, segment: str) -> dict:
    """Layer 3: expected contribution of each published offer, under labelled assumptions.

    EV(offer) = P(convert) x uplift x monthly_value x (margin - discount) x months - acquisition_cost
    Offers below the margin floor are never suggested. The same offers are open to every customer;
    the score only decides which one a salesperson leads with.
    """
    c = _offers_cfg()
    mrr = SEGMENT_MRR.get(segment, 5000)
    rows = []
    for key, o in c["offers"].items():
        p = min(score * o["uplift"], 0.95)
        margin_after = c["contribution_margin"] - o["discount_pct"]
        ev = p * mrr * margin_after * o["months"] - c["acquisition_cost_per_attempt_inr"]
        rows.append({"offer": key, "label": o["label"], "p_convert": round(p, 3), "expected_value_inr": round(ev),
                     "margin_after_discount": round(margin_after, 3), "allowed": margin_after >= c["margin_floor"]})
    allowed = [r for r in rows if r["allowed"]]
    best = max(allowed, key=lambda r: r["expected_value_inr"]) if allowed else None
    return {"recommended": best["offer"] if best else None, "options": rows,
            "assumptions": c["assumptions_note"]}


def stalled_leads(limit: int = 50, segment: Optional[str] = None, stage: Optional[str] = None,
                  source: Optional[str] = None, with_offers: bool = True) -> dict:
    df = pd.read_csv(config.LEADS_CSV)
    df = df[df["outcome"] == "Dropped"].copy()
    df["score"] = propensity.score_dataset().reindex(df["lead_id"]).to_numpy()
    if segment:
        df = df[df["segment"] == segment]
    if stage:
        df = df[df["stage_reached"] == stage]
    if source:
        df = df[df["lead_source"] == source]
    total = len(df)
    df = df.sort_values("score", ascending=False).head(limit)
    rows = []
    for r in df.itertuples():
        rows.append(LeadRow(lead_id=r.lead_id, business_name=r.business_name, business_type=r.business_type,
                            segment=r.segment, city=r.city, lead_source=r.lead_source, stage_reached=r.stage_reached,
                            drop_reason=r.drop_reason if isinstance(r.drop_reason, str) else None,
                            score=round(float(r.score), 3),
                            next_best_action=NBA.get(r.drop_reason, "Call and ask what's missing"),
                            offer=offer_suggestion(float(r.score), r.segment) if with_offers else None))
    return {"total": total, "rows": rows, "model": propensity.evaluation()}


def handoffs() -> list[dict]:
    try:
        with _con() as con:
            rows = con.execute("SELECT id, session_id, slots_json, language, channel, partner_code, created_at, status "
                               "FROM advisor_handoffs ORDER BY created_at DESC").fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for hid, sid, slots, lang, channel, partner, at, status in rows:
        s = json.loads(slots)
        profile = {"lead_source": "Inbound call", "segment": None, "city_tier": None,
                   "employee_count": s.get("employees"), "num_sites": s.get("sites"),
                   "has_gstin": {True: "Y", False: "N"}.get(s.get("has_gstin"), "unknown")}
        out.append({"id": hid, "session_id": sid, "known": {k: v for k, v in s.items() if v not in (None, [], False)},
                    "language": lang, "channel": channel, "partner_code": partner, "requested_at": at,
                    "status": status, "score": round(propensity.score_one(profile), 3)})
    return out


def open_quotes() -> list[dict]:
    """Quotes shown but not accepted: the leads the advisor couldn't close (yet)."""
    try:
        with _con() as con:
            rows = con.execute("SELECT q.id, q.state_json, q.updated_at, "
                               "(SELECT COUNT(*) FROM quote_events e WHERE e.quote_id=q.id) "
                               "FROM quotes q WHERE q.status='open' ORDER BY q.updated_at DESC LIMIT 100").fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for qid, state, at, n_events in rows:
        s = json.loads(state)
        out.append({"quote_id": qid, "business_type": s.get("business_type"), "city": s["profile"].get("city"),
                    "segment": s.get("segment"), "channel": s.get("channel"), "partner_code": s.get("partner_code"),
                    "lines": [l["product_id"] for l in s["lines"]], "events": n_events, "updated_at": at})
    return out


def funnel() -> dict:
    df = pd.read_csv(config.LEADS_CSV)
    order = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
    rank = {s: i for i, s in enumerate(order)}
    reached = df["stage_reached"].map(rank)
    baseline = [{"stage": s, "count": int((reached >= i).sum())} for i, s in enumerate(order)]

    def q(sql: str) -> int:
        try:
            with _con() as con:
                return int(con.execute(sql).fetchone()[0])
        except sqlite3.OperationalError:
            return 0

    live = [
        {"stage": "Advisor sessions", "count": q("SELECT COUNT(*) FROM advisor_sessions")},
        {"stage": "Quotes shown", "count": q("SELECT COUNT(*) FROM quotes")},
        {"stage": "Orders placed", "count": q("SELECT COUNT(*) FROM orders")},
        {"stage": "KYC verified", "count": q("SELECT COUNT(*) FROM order_events WHERE state='KYC_VERIFIED'")},
        {"stage": "Active", "count": q("SELECT COUNT(*) FROM orders WHERE state='ACTIVE'")},
    ]
    return {"baseline_q2_2026": baseline, "live_prototype": live}


def orders(limit: int = 50) -> list[dict]:
    try:
        with _con() as con:
            rows = con.execute("SELECT id, state, language, channel, created_at, updated_at, snapshot_json FROM orders "
                               "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"id": i, "state": s, "language": l, "channel": c, "created_at": ca, "updated_at": ua,
             "business_type": json.loads(sn).get("business_type"), "city": json.loads(sn).get("city"),
             "monthly_total_inr": json.loads(sn)["monthly_total_inr"]} for i, s, l, c, ca, ua, sn in rows]


# ---- KYC review queue ----

def kyc_queue(outcome: str = "MANUAL_REVIEW") -> list[dict]:
    from app.kyc import service as kyc
    try:
        with _con() as con:
            rows = con.execute("SELECT id FROM kyc_cases WHERE outcome=? ORDER BY updated_at DESC", (outcome,)).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for (cid,) in rows:
        c = kyc.load(cid)
        v = kyc.view(c)
        out.append({"id": cid, "order_id": c.order_id, "sample_id": c.sample_id, "outcome": c.outcome,
                    "business": (c.gst_prefill or {}).get("trade_name"),
                    "reasons": [ch.message for ch in c.checks if ch.status == "fail"],
                    "review": c.review, "uploaded": list(v.uploaded)})
    return out


def kyc_decide(case_id: str, decision: str, note: str, reviewer: str) -> dict:
    """Reviewer decision. approve -> VERIFIED; reject -> order KYC_REJECTED; request_fix -> NEEDS_FIX."""
    from app.kyc import service as kyc
    from app.orders import tracker
    if decision not in ("approve", "reject", "request_fix"):
        raise ValueError("decision must be approve, reject or request_fix")
    if not note.strip():
        raise ValueError("A short note is required for every decision (audit).")
    c = kyc.load(case_id)
    if c is None:
        raise LookupError("case not found")
    c.review = {"decision": decision, "note": note.strip()[:500], "reviewer": reviewer}
    c.outcome = {"approve": "VERIFIED", "reject": "MANUAL_REVIEW", "request_fix": "NEEDS_FIX"}[decision]
    kyc._save(c)
    audit.record(reviewer, f"kyc_review_{decision}", case_id, note=note.strip()[:200])
    if c.order_id:
        state = {"approve": "KYC_VERIFIED", "reject": "KYC_REJECTED", "request_fix": "KYC_ACTION_NEEDED"}[decision]
        with _con() as con:
            con.execute("UPDATE orders SET state=? WHERE id=?", (state, c.order_id))
            con.execute("INSERT INTO order_events (order_id, state, note, at) VALUES (?,?,?,datetime('now'))",
                        (c.order_id, state, f"reviewer: {decision}"))
            lang = (con.execute("SELECT language FROM orders WHERE id=?", (c.order_id,)).fetchone() or ["en"])[0]
        tracker.notify(c.order_id, state, lang if lang in ("en", "hi") else "en")
    return {"id": case_id, "outcome": c.outcome, "review": c.review}


def ops_token() -> str:
    return os.getenv("OPS_TOKEN", "accel-demo-ops")
