"""Masking helpers so identifiers never appear in full in the UI or logs."""
from __future__ import annotations

import re

DOT = "•"


def mask_gstin(g: str | None) -> str:
    if not g:
        return ""
    g = g.strip().upper()
    if len(g) != 15:
        return DOT * len(g)
    return g[:3] + DOT * 8 + g[11:]


def mask_udyam(u: str | None) -> str:
    if not u:
        return ""
    u = re.sub(r"\s+", "", u.upper())
    m = re.match(r"^(UDYAM-[A-Z]{2}-\d{2}-)(\d{7})$", u)
    if not m:
        return DOT * len(u)
    return m.group(1) + DOT * 3 + m.group(2)[-4:]


def mask_name(name: str | None) -> str:
    """'Neha Kaur' -> 'N. K.'"""
    if not name:
        return ""
    return " ".join(part[0].upper() + "." for part in name.split() if part)


def mask_phone(p: str | None) -> str:
    digits = re.sub(r"\D", "", p or "")
    return (DOT * (len(digits) - 2) + digits[-2:]) if len(digits) > 2 else DOT * len(digits)
