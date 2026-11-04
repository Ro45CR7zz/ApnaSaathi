"""Udyam registration number format checks."""
from __future__ import annotations

import re

UDYAM_RE = re.compile(r"^UDYAM-([A-Z]{2})-(\d{2})-(\d{7})$")


def normalise(raw: str) -> str:
    # OCR often inserts spaces around hyphens, e.g. "UDYAM-MH- 00-6131836".
    return re.sub(r"\s+", "", (raw or "").upper())


def is_valid_format(number: str) -> bool:
    return bool(UDYAM_RE.match(normalise(number)))


def state_code(number: str) -> str | None:
    m = UDYAM_RE.match(normalise(number))
    return m.group(1) if m else None
