"""Advisor sessions and handoffs, stored in SQLite. Only business facts are stored, no personal data."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from app import config
from app.advisor.dialogue import AdvisorState

SCHEMA = """
CREATE TABLE IF NOT EXISTS advisor_sessions (
  id TEXT PRIMARY KEY, state_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS advisor_handoffs (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, slots_json TEXT NOT NULL, language TEXT,
  channel TEXT, partner_code TEXT, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open');
"""


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB_PATH)
    con.executescript(SCHEMA)
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create(language: str = "en", channel: str = "web", partner_code: Optional[str] = None) -> AdvisorState:
    st = AdvisorState(session_id=uuid.uuid4().hex[:12], language=language, channel=channel,
                      partner_code=partner_code)
    with _con() as con:
        con.execute("INSERT INTO advisor_sessions VALUES (?,?,?,?)",
                    (st.session_id, st.model_dump_json(), _now(), _now()))
    return st


def load(session_id: str) -> Optional[AdvisorState]:
    with _con() as con:
        row = con.execute("SELECT state_json FROM advisor_sessions WHERE id=?", (session_id,)).fetchone()
    return AdvisorState.model_validate_json(row[0]) if row else None


def save(st: AdvisorState) -> None:
    with _con() as con:
        con.execute("UPDATE advisor_sessions SET state_json=?, updated_at=? WHERE id=?",
                    (st.model_dump_json(), _now(), st.session_id))


def record_handoff(st: AdvisorState) -> str:
    hid = uuid.uuid4().hex[:12]
    with _con() as con:
        con.execute("INSERT INTO advisor_handoffs (id, session_id, slots_json, language, channel, partner_code, "
                    "created_at) VALUES (?,?,?,?,?,?,?)",
                    (hid, st.session_id, json.dumps(st.slots.model_dump()), st.language, st.channel,
                     st.partner_code, _now()))
    return hid
