"""GSTIN format, checksum and safe OCR-confusion correction.

GSTIN layout (15 chars): 2-digit state code, 10-char PAN (5 letters, 4 digits, 1 letter),
1 entity code (1-9 or A-Z), the letter 'Z', 1 check character.
The dataset uses 'X' as the PAN's 4th character (README); the generic pattern allows it.
"""
from __future__ import annotations

import itertools
import re
from typing import Literal, Optional

from pydantic import BaseModel

CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

# Only the classic OCR confusions. S/5 and B/8 are deliberately NOT included, so a genuinely
# different digit (e.g. K06: ...S8189... vs registry ...S5189...) is never "corrected" into a match.
TO_DIGIT = {"O": "0", "I": "1"}
TO_LETTER = {"0": "O", "1": "I"}
DIGIT_POS = {0, 1, 7, 8, 9, 10}
LETTER_POS = {2, 3, 4, 5, 6, 11}
FREE_POS = {12, 14}  # entity code and check char can be a digit or a letter
Z_POS = 13


def normalise(raw: str) -> str:
    return re.sub(r"[\s\-\.]", "", (raw or "").upper())


def checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        v = CHARSET.index(ch) * (2 if i % 2 else 1)
        total += v // 36 + v % 36
    return CHARSET[(36 - total % 36) % 36]


def is_valid_format(gstin: str) -> bool:
    if not GSTIN_RE.match(gstin):
        return False
    return 1 <= int(gstin[:2]) <= 38


def is_valid(gstin: str) -> bool:
    """Format + state code + checksum."""
    return is_valid_format(gstin) and checksum_char(gstin[:14]) == gstin[14]


def _candidates_for(i: int, ch: str) -> list[str]:
    if i in DIGIT_POS:
        return [TO_DIGIT.get(ch, ch)]
    if i in LETTER_POS:
        return [TO_LETTER.get(ch, ch)]
    if i == Z_POS:
        return ["Z"] if ch in ("Z", "2") else [ch]
    if i in FREE_POS:
        alts = {ch}
        if ch in TO_DIGIT:
            alts.add(TO_DIGIT[ch])
        if ch in TO_LETTER:
            alts.add(TO_LETTER[ch])
        return sorted(alts)
    return [ch]


class GstinCheck(BaseModel):
    input: str
    normalised: str
    status: Literal["valid", "corrected_suggestion", "ambiguous", "invalid"]
    suggestion: Optional[str] = None
    candidates: list[str] = []
    changed_positions: list[int] = []
    message: str


def check_gstin(raw: str) -> GstinCheck:
    """Validate a GSTIN and, if invalid, look for exactly one checksum-valid OCR correction.

    A suggestion must always be confirmed by the user; it is never applied silently.
    """
    g = normalise(raw)
    if len(g) == 15 and all(c in CHARSET for c in g) and is_valid(g):
        return GstinCheck(input=raw, normalised=g, status="valid", message="GSTIN format and checksum are valid.")
    if len(g) != 15 or not all(c in CHARSET for c in g):
        return GstinCheck(input=raw, normalised=g, status="invalid",
                          message="A GSTIN has exactly 15 letters and digits.")

    options = [_candidates_for(i, ch) for i, ch in enumerate(g)]
    valid = sorted({"".join(c) for c in itertools.product(*options) if is_valid("".join(c))} - {g})
    if len(valid) == 1:
        s = valid[0]
        changed = [i for i in range(15) if s[i] != g[i]]
        return GstinCheck(input=raw, normalised=g, status="corrected_suggestion", suggestion=s,
                          candidates=valid, changed_positions=changed,
                          message="This looks like a scanning mix-up between similar characters "
                                  f"(e.g. 0/O). Did you mean {s}? Please confirm.")
    if len(valid) > 1:
        return GstinCheck(input=raw, normalised=g, status="ambiguous", candidates=valid,
                          message="We could not read this GSTIN reliably. Please type it in.")
    return GstinCheck(input=raw, normalised=g, status="invalid",
                      message="This GSTIN is not valid (the check digit does not match). Please check the number.")
