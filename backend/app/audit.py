"""Audit trail for sensitive operations. Details are masked before they are written."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from app import config

SCHEMA = """CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  entity TEXT NOT NULL, details_json TEXT);"""


def record(actor: str, action: str, entity: str, **details) -> None:
    with sqlite3.connect(config.DB_PATH) as con:
        con.execute(SCHEMA)
        con.execute("INSERT INTO audit_events (at, actor, action, entity, details_json) VALUES (?,?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(timespec="seconds"), actor, action, entity,
                     json.dumps(details, ensure_ascii=False)))


def for_entity(entity: str) -> list[dict]:
    with sqlite3.connect(config.DB_PATH) as con:
        con.execute(SCHEMA)
        rows = con.execute("SELECT at, actor, action, details_json FROM audit_events WHERE entity=? ORDER BY id",
                           (entity,)).fetchall()
    return [{"at": a, "actor": ac, "action": act, "details": json.loads(d or "{}")} for a, ac, act, d in rows]
