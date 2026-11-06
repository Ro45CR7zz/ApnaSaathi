"""WhatsApp channel adapter: the same Advisor, reached through a messaging webhook.

- Twilio-compatible: form fields From/Body in, TwiML <Response><Message> out (sandbox-ready).
- JSON mode for the in-app simulator: {"from": ..., "text": ...} in, {"reply", "quick_replies", ...} out.
Phone numbers are never stored: sessions are keyed by a salted SHA-256 hash of the sender id.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from xml.sax.saxutils import escape

from pydantic import BaseModel

from app import config
from app.advisor import store
from app.advisor.dialogue import AdvisorReply, greeting, handle_message
from app.quotes import service as quotes

SCHEMA = """CREATE TABLE IF NOT EXISTS channel_sessions (
  sender_hash TEXT PRIMARY KEY, session_id TEXT NOT NULL, quote_id TEXT, updated_at TEXT NOT NULL);"""
RESTART = {"restart", "start", "new", "hi", "hello", "namaste", "नमस्ते", "नया", "शुरू"}


class WaReply(BaseModel):
    reply: str
    quick_replies: list[str] = []
    session_id: str
    quote_id: Optional[str] = None
    quote_link: Optional[str] = None
    language: str


def _hash(sender: str) -> str:
    salt = os.getenv("CHANNEL_HASH_SALT", "apnasaathi-demo-salt")
    return hashlib.sha256((salt + sender.strip()).encode()).hexdigest()


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB_PATH)
    con.execute(SCHEMA)
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")


def _chips(r: AdvisorReply) -> list[str]:
    return [c.label for c in r.chips][:10]


def handle(sender: str, text: str, language: Optional[str] = None) -> WaReply:
    h = _hash(sender)
    with _con() as con:
        row = con.execute("SELECT session_id FROM channel_sessions WHERE sender_hash=?", (h,)).fetchone()
    lang = language or ("hi" if any("ऀ" <= ch <= "ॿ" for ch in text) else "en")
    st = store.load(row[0]) if row else None
    if st is None or text.strip().lower() in RESTART:
        st = store.create(lang, "whatsapp")
        with _con() as con:
            con.execute("INSERT OR REPLACE INTO channel_sessions VALUES (?,?,?,?)", (h, st.session_id, None, _now()))
        g = greeting(st)
        store.save(st)
        if text.strip().lower() in RESTART or not text.strip():
            return WaReply(reply=g.text, quick_replies=_chips(g), session_id=st.session_id, language=st.language)
    # Quick-reply labels come back as text; the Advisor understands them like typed words.
    r = handle_message(st, text)
    if r.handoff:
        store.record_handoff(st)
    store.save(st)
    if r.recommendation:
        q = quotes.create_from_slots(st.slots, st.language, st.session_id, "whatsapp", st.partner_code)
        summary = quotes.share_text(quotes.load(q.id))
        link = f"{_base_url()}/#/q/{q.id}"
        tail = ("\n\nपूरा कोटेशन देखें, बदलें और ऑर्डर करें:\n" if st.language == "hi"
                else "\n\nSee, change and order your quote here:\n") + link
        with _con() as con:
            con.execute("UPDATE channel_sessions SET quote_id=?, updated_at=? WHERE sender_hash=?", (q.id, _now(), h))
        return WaReply(reply=summary + tail, session_id=st.session_id, quote_id=q.id, quote_link=link,
                       language=st.language)
    return WaReply(reply=r.text, quick_replies=_chips(r), session_id=st.session_id, language=st.language)


def twiml(text: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(text)}</Message></Response>'
