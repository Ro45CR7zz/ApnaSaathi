"""Tracker (customer) and back-office (ops) API.

Back-office routes need the X-Ops-Token header (demo role token, see OPS_TOKEN in .env).
Production would use the operator's SSO with roles; documents are viewable only by reviewers and every
view is audited.
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app import audit
from app.backoffice import propensity
from app.backoffice import service as bo
from app.kyc import service as kyc
from app.orders import tracker

router = APIRouter(prefix="/api", tags=["tracker", "backoffice"])


# ---------- customer tracker ----------

@router.get("/orders/{order_id}/tracker", response_model=tracker.TrackerView)
def track(order_id: str):
    v = tracker.view(order_id)
    if v is None:
        raise HTTPException(404, "order not found")
    return v


def _wrap(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/orders/{order_id}/pay", response_model=tracker.TrackerView)
def pay(order_id: str):
    """SIMULATED payment (prototype)."""
    return _wrap(tracker.pay, order_id)


@router.post("/orders/{order_id}/switch-airfiber", response_model=tracker.TrackerView)
def switch(order_id: str):
    return _wrap(tracker.switch_to_airfiber, order_id)


# ---------- back office ----------

def ops(x_ops_token: Optional[str] = Header(None)) -> str:
    if x_ops_token != bo.ops_token():
        raise HTTPException(401, "back-office token required")
    return "ops:demo"


@router.get("/ops/leads")
def leads(limit: int = 50, segment: Optional[str] = None, stage: Optional[str] = None,
          source: Optional[str] = None, who: str = Depends(ops)):
    return bo.stalled_leads(min(limit, 200), segment, stage, source)


@router.get("/ops/model")
def model(who: str = Depends(ops)):
    return propensity.evaluation()


@router.get("/ops/handoffs")
def handoffs(who: str = Depends(ops)):
    return bo.handoffs()


@router.get("/ops/open-quotes")
def open_quotes(who: str = Depends(ops)):
    return bo.open_quotes()


@router.get("/ops/funnel")
def funnel(who: str = Depends(ops)):
    return bo.funnel()


@router.get("/ops/orders")
def orders(who: str = Depends(ops)):
    return bo.orders()


class SimReq(BaseModel):
    event: tracker.SimEvent
    reason: str = "technician"


@router.post("/ops/orders/{order_id}/simulate", response_model=tracker.TrackerView)
def simulate(order_id: str, req: SimReq, who: str = Depends(ops)):
    return _wrap(tracker.simulate, order_id, req.event, req.reason)


@router.get("/ops/kyc")
def kyc_queue(outcome: str = "MANUAL_REVIEW", who: str = Depends(ops)):
    return bo.kyc_queue(outcome)


@router.get("/ops/kyc/{case_id}", response_model=kyc.CaseView)
def kyc_case(case_id: str, who: str = Depends(ops)):
    c = kyc.load(case_id)
    if c is None:
        raise HTTPException(404, "case not found")
    audit.record(who, "kyc_case_opened", case_id)
    return kyc.view(c)


@router.get("/ops/kyc/{case_id}/documents/{doc_type}")
def kyc_document(case_id: str, doc_type: str, who: str = Depends(ops)):
    c = kyc.load(case_id)
    if c is None or doc_type not in c.docs or not c.docs[doc_type].stored:
        raise HTTPException(404, "document not available")
    return Response(kyc.read_document(c, doc_type, actor=who), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


class Decision(BaseModel):
    decision: Literal["approve", "reject", "request_fix"]
    note: str


@router.post("/ops/kyc/{case_id}/decision")
def decide(case_id: str, req: Decision, who: str = Depends(ops)):
    return _wrap(bo.kyc_decide, case_id, req.decision, req.note, who)


@router.get("/ops/audit/{entity}")
def audit_trail(entity: str, who: str = Depends(ops)):
    return audit.for_entity(entity)
