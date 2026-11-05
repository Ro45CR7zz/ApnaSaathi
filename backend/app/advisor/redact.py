"""Remove personal data before any text is sent to an external LLM (design decision D7)."""
from __future__ import annotations

import re

PATTERNS: list[tuple[str, str]] = [
    (r"UDYAM-?\s*[A-Z]{2}-?\s*\d{2}-?\s*\d{7}", "[UDYAM]"),
    (r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", "[GSTIN]"),
    (r"\b[A-Z]{5}\d{4}[A-Z]\b", "[PAN]"),
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "[EMAIL]"),
    (r"\b\d{4}\s?\d{4}\s?\d{4}\b", "[ID_NUMBER]"),           # Aadhaar-like 12 digits
    (r"(?:\+91[\s-]?|\b0)?[6-9]\d{4}[\s-]?\d{5}\b", "[PHONE]"),
    (r"\b\d{6}\b", "[PINCODE]"),
]
NAME_INTRO = re.compile(
    r"((?:my name is|i am|i'm|this is|mera naam|मेरा नाम)\s+)([A-Za-zऀ-ॿ]+(?:\s+[A-Za-zऀ-ॿ]+)?)",
    re.IGNORECASE)
NOT_NAMES = {"a", "an", "the", "running", "from", "in", "owner", "the owner", "having", "with"}


def redact(text: str) -> str:
    out = text
    for pat, repl in PATTERNS:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)

    def _name(m: re.Match) -> str:
        first = m.group(2).split()[0].lower()
        return m.group(0) if first in NOT_NAMES else m.group(1) + "[NAME]"

    return NAME_INTRO.sub(_name, out)
