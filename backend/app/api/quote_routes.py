"""Quote and checkout API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.advisor import store as advisor_store
from app.advisor.slots import Slots
from app.catalogue.models import Language
from app.orders import service as orders
from app.quotes import service as quotes

router = APIRouter(prefix="/api", tags=["quotes"])


class CreateQuote(BaseModel):
    session_id: Optional[str] = None
    slots: Optional[Slots] = None  # direct use (partner console); session_id is the normal path
    language: Optional[Language] = None


@router.post("/quotes", response_model=quotes.QuoteView)
def create(req: CreateQuote):
    if req.session_id:
        st = advisor_store.load(req.session_id)
        if st is None:
            raise HTTPException(404, "session not found")
        if st.slots.missing():
            raise HTTPException(409, f"still need: {', '.join(st.slots.missing())}")
        return quotes.create_from_slots(st.slots, req.language or st.language, st.session_id, st.channel,
                                        st.partner_code)
    if req.slots:
        missing = req.slots.missing()
        if missing:
            raise HTTPException(422, f"still need: {', '.join(missing)}")
        return quotes.create_from_slots(req.slots, req.language or "en", channel="partner")
    raise HTTPException(422, "send session_id or slots")


def _q(quote_id: str) -> quotes.QuoteState:
    q = quotes.load(quote_id)
    if q is None:
        raise HTTPException(404, "quote not found")
    return q


@router.get("/quotes/{quote_id}", response_model=quotes.QuoteView)
def get(quote_id: str, language: Optional[Language] = None):
    q = _q(quote_id)
    if language:
        q.language = language
    return quotes.view(q)


@router.patch("/quotes/{quote_id}", response_model=quotes.QuoteView)
def change(quote_id: str, ch: quotes.QuoteChange):
    try:
        return quotes.apply_change(_q(quote_id), ch)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/quotes/{quote_id}/share")
def share(quote_id: str, language: Optional[Language] = None):
    q = _q(quote_id)
    if language:
        q.language = language
    return {"text": quotes.share_text(q)}


@router.get("/quotes/{quote_id}/events")
def quote_events(quote_id: str):
    _q(quote_id)
    return quotes.events(quote_id)


@router.post("/quotes/{quote_id}/accept", response_model=orders.OrderView)
def accept(quote_id: str, contact: orders.Contact):
    try:
        return orders.accept(quote_id, contact)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/orders/{order_id}", response_model=orders.OrderView)
def order(order_id: str):
    o = orders.get(order_id)
    if o is None:
        raise HTTPException(404, "order not found")
    return o
