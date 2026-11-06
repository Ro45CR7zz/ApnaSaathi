"""Messaging channel webhooks."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.catalogue.models import Language
from app.channels import whatsapp

router = APIRouter(prefix="/api/channels", tags=["channels"])


class SimMessage(BaseModel):
    sender: str = Field(alias="from", min_length=3, max_length=64)
    text: str = Field(max_length=1000)
    language: Optional[Language] = None


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """Twilio sends form-encoded From/Body and expects TwiML; the simulator sends JSON."""
    ctype = request.headers.get("content-type", "")
    if ctype.startswith("application/x-www-form-urlencoded") or ctype.startswith("multipart/form-data"):
        form = await request.form()
        sender, text = str(form.get("From", "")), str(form.get("Body", ""))
        if not sender:
            raise HTTPException(422, "missing From")
        r = whatsapp.handle(sender, text[:1000])
        body = r.reply + ("\n\n" + " | ".join(r.quick_replies) if r.quick_replies else "")
        return Response(whatsapp.twiml(body), media_type="application/xml")
    msg = SimMessage.model_validate(await request.json())
    return whatsapp.handle(msg.sender, msg.text, msg.language)
