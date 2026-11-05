"""KYC cases: consent, GSTIN lookup, encrypted document storage, evaluation and retention.

Privacy choices (see docs/PRIVACY.md):
- Nothing is processed before the owner gives consent for the stated purposes.
- Documents are encrypted at rest (Fernet / AES) and only the extracted, masked fields are returned.
- OCR runs on our server; no document leaves it.
- Raw images are deleted when consent is withdrawn, and RETENTION_DAYS after the case closes.
- Every step is written to the audit trail with masked details.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

from cryptography.fernet import Fernet
from pydantic import BaseModel

from app import audit, config
from app.common.masking import mask_gstin, mask_name, mask_udyam
from app.kyc import samples
from app.kyc.checks import Check, Declared, DocResult, evaluate, required_docs
from app.kyc.imaging import BadUpload
from app.kyc.pipeline import process
from app.registry import store
from app.registry.gstin import check_gstin
from app.registry.udyam import is_valid_format as udyam_ok
from app.registry.udyam import normalise as udyam_norm

NOTICE_VERSION = "kyc-notice-2026-11-v1"
PURPOSES = ("verify_business", "store_documents")
RETENTION_DAYS = int(os.getenv("KYC_RETENTION_DAYS", "30"))
UPLOAD_DIR = Path(os.getenv("KYC_UPLOAD_DIR", config.BACKEND_DIR / "uploads"))
KEY_FILE = config.BACKEND_DIR / ".kyc_key"

SCHEMA = """CREATE TABLE IF NOT EXISTS kyc_cases (
  id TEXT PRIMARY KEY, order_id TEXT, sample_id TEXT, state_json TEXT NOT NULL, outcome TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, closed_at TEXT);"""

ORDER_STATE = {"VERIFIED": "KYC_VERIFIED", "NEEDS_FIX": "KYC_ACTION_NEEDED",
               "MANUAL_REVIEW": "KYC_MANUAL_REVIEW", "BLOCKED": "KYC_BLOCKED"}


class ConsentRequired(PermissionError):
    pass


class DocState(BaseModel):
    doc_type: str
    stored: bool
    found_type: Optional[str] = None
    result: DocResult
    metrics: dict = {}
    uploaded_at: str


class CaseState(BaseModel):
    id: str
    order_id: Optional[str] = None
    sample_id: Optional[str] = None
    language: str = "en"
    consents: dict[str, str] = {}       # purpose -> timestamp
    notice_version: Optional[str] = None
    declared: Declared = Declared()
    gst_prefill: Optional[dict] = None  # masked registry details shown to the owner
    docs: dict[str, DocState] = {}
    outcome: Optional[str] = None
    checks: list[Check] = []
    review: Optional[dict] = None       # set by a reviewer (Phase 8)


class CaseView(BaseModel):
    id: str
    order_id: Optional[str]
    sample_id: Optional[str]
    language: str
    consent_given: bool
    notice_version: str
    purposes: list[str]
    gstin_masked: Optional[str]
    no_gstin: bool
    udyam_masked: Optional[str]
    gst_prefill: Optional[dict]
    required_docs: list[str]
    uploaded: dict[str, dict]
    outcome: Optional[str]
    checks: list[Check]
    retention_days: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fernet() -> Fernet:
    key = os.getenv("KYC_ENCRYPTION_KEY")
    if not key:
        if not KEY_FILE.exists():
            KEY_FILE.write_bytes(Fernet.generate_key())
        key = KEY_FILE.read_bytes().decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(config.DB_PATH)
    con.execute(SCHEMA)
    return con


def _save(c: CaseState, new: bool = False) -> None:
    with _con() as con:
        if new:
            con.execute("INSERT INTO kyc_cases (id, order_id, sample_id, state_json, outcome, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?,?)", (c.id, c.order_id, c.sample_id, c.model_dump_json(), c.outcome,
                                                   _now(), _now()))
        else:
            con.execute("UPDATE kyc_cases SET state_json=?, outcome=?, updated_at=? WHERE id=?",
                        (c.model_dump_json(), c.outcome, _now(), c.id))


def load(case_id: str) -> Optional[CaseState]:
    with _con() as con:
        row = con.execute("SELECT state_json FROM kyc_cases WHERE id=?", (case_id,)).fetchone()
    return CaseState.model_validate_json(row[0]) if row else None


def _masked_fields(f: dict) -> dict:
    out = dict(f)
    if out.get("gstin"):
        out["gstin"] = mask_gstin(out["gstin"])
    if out.get("udyam_number"):
        out["udyam_number"] = mask_udyam(out["udyam_number"])
    for k in ("name",):
        if out.get(k):
            out[k] = mask_name(out[k])
    for k in ("consumer_no", "id_no"):
        if out.get(k):
            out[k] = "•••" + str(out[k])[-3:]
    return out


def view(c: CaseState) -> CaseView:
    return CaseView(
        id=c.id, order_id=c.order_id, sample_id=c.sample_id, language=c.language,
        consent_given=all(p in c.consents for p in PURPOSES), notice_version=NOTICE_VERSION, purposes=list(PURPOSES),
        gstin_masked=mask_gstin(c.declared.gstin) if c.declared.gstin else None, no_gstin=c.declared.no_gstin,
        udyam_masked=mask_udyam(c.declared.udyam_number) if c.declared.udyam_number else None,
        gst_prefill=c.gst_prefill, required_docs=required_docs(c.declared),
        uploaded={dt: {"found_type": d.found_type, "sharp": d.result.sharp, "readable": d.result.readable,
                       "deskewed": d.result.deskewed, "fields": _masked_fields(d.result.fields)}
                  for dt, d in c.docs.items()},
        outcome=c.outcome, checks=c.checks, retention_days=RETENTION_DAYS)


def create(order_id: Optional[str], language: str = "en", contact_name: Optional[str] = None,
           sample_id: Optional[str] = None) -> CaseState:
    c = CaseState(id="KYC" + uuid.uuid4().hex[:8].upper(), order_id=order_id, sample_id=sample_id, language=language,
                  declared=Declared(contact_name=contact_name))
    _save(c, new=True)
    audit.record("customer", "kyc_case_created", c.id, order_id=order_id, sample=sample_id)
    return c


def give_consent(c: CaseState, purposes: list[str], notice_version: str) -> CaseState:
    if notice_version != NOTICE_VERSION:
        raise ValueError("Please read the latest consent notice.")
    missing = [p for p in PURPOSES if p not in purposes]
    if missing:
        raise ValueError("Both permissions are needed to verify your business online.")
    for p in PURPOSES:
        c.consents[p] = _now()
    c.notice_version = notice_version
    _save(c)
    audit.record("customer", "consent_given", c.id, purposes=list(PURPOSES), notice=notice_version)
    return c


def _require_consent(c: CaseState) -> None:
    if not all(p in c.consents for p in PURPOSES):
        raise ConsentRequired("Consent is needed before we can process your details.")


class GstinResult(BaseModel):
    status: Literal["ok", "confirm", "invalid", "not_found", "inactive"]
    message: str
    suggestion: Optional[str] = None
    case: Optional[CaseView] = None


def set_gstin(c: CaseState, gstin: Optional[str], no_gstin: bool = False) -> GstinResult:
    _require_consent(c)
    if no_gstin:
        c.declared.gstin, c.declared.no_gstin, c.gst_prefill = None, True, None
        _save(c)
        audit.record("customer", "declared_no_gstin", c.id)
        return GstinResult(status="ok", message="Continuing without GST.", case=view(c))
    chk = check_gstin(gstin or "")
    if chk.status == "corrected_suggestion":
        return GstinResult(status="confirm", message=chk.message, suggestion=chk.suggestion)
    if chk.status != "valid":
        return GstinResult(status="invalid", message=chk.message)
    rec = store.lookup_gstin(chk.normalised)
    if rec is None:
        return GstinResult(status="not_found", message="This GSTIN was not found in the GST registry (mock).")
    c.declared.gstin, c.declared.no_gstin = chk.normalised, False
    c.gst_prefill = {"legal_name": rec["legal_name"], "trade_name": rec["trade_name"],
                     "constitution": rec["constitution"], "address": rec["principal_place_of_business"],
                     "status": rec["status"], "source": store.MOCK_LABEL}
    _save(c)
    audit.record("customer", "gstin_declared", c.id, gstin=mask_gstin(chk.normalised), registry_status=rec["status"])
    status = "ok" if rec["status"] == "Active" else "inactive"
    return GstinResult(status=status, message=f"Registry status: {rec['status']}", case=view(c))


def set_udyam(c: CaseState, number: Optional[str]) -> CaseState:
    _require_consent(c)
    if number:
        n = udyam_norm(number)
        if not udyam_ok(n):
            raise ValueError("A Udyam number looks like UDYAM-XX-00-1234567.")
        c.declared.udyam_number = n
    else:
        c.declared.udyam_number = None
    _save(c)
    audit.record("customer", "udyam_declared", c.id, udyam=mask_udyam(c.declared.udyam_number))
    return c


def _doc_path(case_id: str, doc_type: str) -> Path:
    return UPLOAD_DIR / case_id / f"{doc_type}.enc"


def upload(c: CaseState, doc_type: str, data: bytes, actor: str = "customer") -> CaseState:
    _require_consent(c)
    if doc_type not in ("gst_certificate", "udyam_certificate", "address_proof", "signatory_id"):
        raise ValueError("Unknown document type.")
    result, metrics = process(data, doc_type)  # raises BadUpload for non-images
    path = _doc_path(c.id, doc_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_fernet().encrypt(data))
    c.docs[doc_type] = DocState(doc_type=doc_type, stored=True, found_type=result.found_type, result=result,
                                metrics=metrics, uploaded_at=_now())
    c.outcome, c.checks = None, []
    _save(c)
    audit.record(actor, "document_uploaded", c.id, doc_type=doc_type, found_type=result.found_type,
                 sharp=result.sharp, **metrics)
    return c


def read_document(c: CaseState, doc_type: str, actor: str) -> bytes:
    """Decrypt a stored document for an authorised reviewer (role checks in Phase 8); always audited."""
    audit.record(actor, "document_viewed", c.id, doc_type=doc_type)
    return _fernet().decrypt(_doc_path(c.id, doc_type).read_bytes())


def run_evaluation(c: CaseState) -> CaseState:
    _require_consent(c)
    outcome, checks = evaluate(c.declared, {dt: d.result for dt, d in c.docs.items()}, c.language)
    c.outcome, c.checks = outcome, checks
    _save(c)
    audit.record("system", "kyc_evaluated", c.id, outcome=outcome,
                 failed=[ch.code for ch in checks if ch.status == "fail"])
    if c.order_id:
        _update_order(c.order_id, ORDER_STATE[outcome], outcome)
    return c


def _update_order(order_id: str, state: str, note: str) -> None:
    with sqlite3.connect(config.DB_PATH) as con:
        con.execute("UPDATE orders SET state=?, updated_at=? WHERE id=?", (state, _now(), order_id))
        con.execute("INSERT INTO order_events (order_id, state, note, at) VALUES (?,?,?,?)",
                    (order_id, state, note, _now()))


def delete_documents(c: CaseState, reason: str = "consent_withdrawn", actor: str = "customer") -> CaseState:
    shutil.rmtree(UPLOAD_DIR / c.id, ignore_errors=True)
    for d in c.docs.values():
        d.stored = False
    if reason == "consent_withdrawn":
        c.consents = {}
    _save(c)
    audit.record(actor, "documents_deleted", c.id, reason=reason)
    return c


def purge_expired(now: Optional[datetime] = None) -> int:
    """Delete raw images of cases closed more than RETENTION_DAYS ago. Run daily (e.g. a scheduled job)."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")
    with _con() as con:
        ids = [r[0] for r in con.execute("SELECT id FROM kyc_cases WHERE closed_at IS NOT NULL AND closed_at < ?",
                                         (cutoff,)).fetchall()]
    for cid in ids:
        c = load(cid)
        if c and any(d.stored for d in c.docs.values()):
            delete_documents(c, reason="retention_expired", actor="system")
    return len(ids)


def close(c: CaseState) -> None:
    with _con() as con:
        con.execute("UPDATE kyc_cases SET closed_at=? WHERE id=?", (_now(), c.id))


def run_sample(kid: str, language: str = "en") -> CaseState:
    """Demo / acceptance path: run a specimen applicant (K01-K12) through the same pipeline."""
    if kid not in samples.sample_ids():
        raise LookupError("Unknown sample applicant.")
    d = samples.declared(kid)
    c = create(None, language, d.contact_name, sample_id=kid)
    give_consent(c, list(PURPOSES), NOTICE_VERSION)
    if d.gstin:
        set_gstin(c, d.gstin)
    else:
        set_gstin(c, None, no_gstin=True)
    if d.udyam_number:
        set_udyam(c, d.udyam_number)
    for dt, data in samples.files(kid).items():
        upload(c, dt, data, actor="demo")
    return run_evaluation(c)


def use_sample(c: CaseState, kid: str) -> CaseState:
    """Demo helper on a real order's case: load a specimen applicant's declared details and documents."""
    if kid not in samples.sample_ids():
        raise LookupError("Unknown sample applicant.")
    _require_consent(c)
    d = samples.declared(kid)
    c.sample_id, c.declared.contact_name = kid, d.contact_name
    if d.gstin:
        set_gstin(c, d.gstin)
    else:
        set_gstin(c, None, no_gstin=True)
    set_udyam(c, d.udyam_number)
    c = load(c.id)
    c.docs = {}
    for dt, data in samples.files(kid).items():
        c = upload(c, dt, data, actor="demo")
    return run_evaluation(c)


def sample_list() -> list[dict]:
    out = []
    for kid in samples.sample_ids():
        r = samples.lead(kid)
        out.append({"id": kid, "business": r["business_name"], "city": r["city"],
                    "documents": sorted(samples.files(kid).keys())})
    return out


__all__ = ["BadUpload", "ConsentRequired", "CaseState", "CaseView", "create", "give_consent", "set_gstin",
           "set_udyam", "upload", "run_evaluation", "delete_documents", "purge_expired", "run_sample", "view", "load"]
