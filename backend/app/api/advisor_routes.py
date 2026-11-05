"""Advisor API: start a session, send messages (chat/voice text), or submit the fallback form."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.advisor import store
from app.advisor.dialogue import AdvisorReply, greeting, handle_form, handle_message
from app.advisor.llm import get_llm
from app.advisor.slots import Slots
from app.catalogue.models import Language
from app.recommender.engine import Recommendation, recommend

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


class StartRequest(BaseModel):
    language: Language = "en"
    channel: str = Field("web", pattern="^(web|whatsapp|partner|voice)$")
    partner_code: Optional[str] = Field(None, max_length=20)


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    language: Optional[Language] = None  # the owner switched language in the UI


class FormRequest(BaseModel):
    slots: Slots
    language: Optional[Language] = None


@router.get("/status")
def status():
    llm = get_llm()
    return {"understanding": llm.name if llm else "rules (no Gemini key or Gemini unreachable)"}


@router.post("/sessions", response_model=AdvisorReply)
def start(req: StartRequest):
    st = store.create(req.language, req.channel, req.partner_code)
    return greeting(st)


def _get(session_id: str):
    st = store.load(session_id)
    if st is None:
        raise HTTPException(404, "session not found")
    return st


@router.post("/sessions/{session_id}/message", response_model=AdvisorReply)
def message(session_id: str, req: MessageRequest):
    st = _get(session_id)
    if req.language:
        st.language = req.language
    reply = handle_message(st, req.text)
    if reply.handoff:
        store.record_handoff(st)
    store.save(st)
    return reply


@router.post("/sessions/{session_id}/form", response_model=AdvisorReply)
def form(session_id: str, req: FormRequest):
    st = _get(session_id)
    if req.language:
        st.language = req.language
    reply = handle_form(st, req.slots)
    store.save(st)
    return reply


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    return _get(session_id)


class RecommendRequest(BaseModel):
    slots: Slots
    language: Language = "en"


@router.post("/recommend", response_model=Recommendation)
def recommend_direct(req: RecommendRequest):
    """Deterministic recommendation from known facts (used by the partner console and tests)."""
    return recommend(req.slots, req.language)
