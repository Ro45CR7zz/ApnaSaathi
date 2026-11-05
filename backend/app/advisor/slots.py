"""What the Advisor collects about a business (no personal data)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.catalogue.models import Segment

NeedTag = Literal[
    "internet", "mobile_lines", "billing_upi", "cctv", "guest_wifi", "whatsapp_customers",
    "sms_alerts", "website", "email_office", "backup_files", "security", "uptime_backup",
    "central_management", "static_ip", "cloud_calling", "toll_free", "machines_iot", "vehicles",
]
NEED_TAGS: tuple[str, ...] = NeedTag.__args__  # type: ignore[attr-defined]

Intent = Literal["answer", "question", "human", "out_of_scope", "other"]

# Order in which the Advisor asks for missing information.
REQUIRED_SLOTS = ("business_type", "city", "employees", "sites", "has_gstin", "needs")


class Slots(BaseModel):
    business_type: Optional[str] = None
    segment: Optional[Segment] = None
    city: Optional[str] = None
    employees: Optional[int] = Field(default=None, ge=1, le=5000)
    sites: Optional[int] = Field(default=None, ge=1, le=500)
    has_gstin: Optional[bool] = None
    needs: list[str] = []
    needs_confirmed: bool = False
    fibre_available: Optional[bool] = None
    # Optional quantities the owner may mention.
    mobile_lines: Optional[int] = Field(default=None, ge=1, le=500)
    cameras: Optional[int] = Field(default=None, ge=1, le=500)
    counters: Optional[int] = Field(default=None, ge=1, le=200)
    devices: Optional[int] = Field(default=None, ge=1, le=2000)
    vehicles: Optional[int] = Field(default=None, ge=1, le=1000)
    email_users: Optional[int] = Field(default=None, ge=1, le=2000)

    def missing(self) -> list[str]:
        out = []
        for s in REQUIRED_SLOTS:
            if s == "needs":
                if not self.needs_confirmed:
                    out.append(s)
            elif getattr(self, s) is None:
                out.append(s)
        return out


class ProfileUpdate(BaseModel):
    """One turn's extracted facts. Every field optional; null = not stated."""

    business_type: Optional[str] = None
    segment: Optional[Segment] = None
    city: Optional[str] = None
    employees: Optional[int] = None
    sites: Optional[int] = None
    has_gstin: Optional[bool] = None
    needs: list[str] = []
    no_more_needs: bool = False
    fibre_available: Optional[bool] = None
    mobile_lines: Optional[int] = None
    cameras: Optional[int] = None
    counters: Optional[int] = None
    devices: Optional[int] = None
    vehicles: Optional[int] = None
    email_users: Optional[int] = None
    intent: Intent = "answer"
    user_question: Optional[str] = None
    language: Optional[Literal["en", "hi"]] = None


LIMITS = {"employees": (1, 5000), "sites": (1, 500), "mobile_lines": (1, 500), "cameras": (1, 500),
          "counters": (1, 200), "devices": (1, 2000), "vehicles": (1, 1000), "email_users": (1, 2000)}


def sanitise(update: ProfileUpdate) -> ProfileUpdate:
    """Drop out-of-range numbers and unknown need tags (LLM output is untrusted)."""
    data = update.model_dump()
    for k, (lo, hi) in LIMITS.items():
        v = data.get(k)
        if v is not None and not (isinstance(v, int) and lo <= v <= hi):
            data[k] = None
    data["needs"] = [n for n in dict.fromkeys(data.get("needs") or []) if n in NEED_TAGS]
    for k in ("business_type", "city", "user_question"):
        if data.get(k):
            data[k] = str(data[k]).strip()[:80] or None
    return ProfileUpdate(**data)


def merge(slots: Slots, upd: ProfileUpdate) -> Slots:
    data = slots.model_dump()
    for k in ("business_type", "segment", "city", "employees", "sites", "has_gstin", "fibre_available",
              "mobile_lines", "cameras", "counters", "devices", "vehicles", "email_users"):
        v = getattr(upd, k)
        if v is not None:
            data[k] = v
    if upd.needs:
        data["needs"] = list(dict.fromkeys(data["needs"] + upd.needs))
    if upd.no_more_needs or upd.needs:
        data["needs_confirmed"] = True
    return Slots(**data)
