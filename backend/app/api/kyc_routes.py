"""Smart KYC API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app import audit
from app.catalogue.models import Language
from app.kyc import service as kyc
from app.kyc.imaging import BadUpload
from app.kyc.ocr import OcrUnavailable, available as ocr_available
from app.orders import service as orders

MAX_UPLOAD = 8 * 1024 * 1024

router = APIRouter(prefix="/api/kyc", tags=["kyc"])


def _case(case_id: str) -> kyc.CaseState:
    c = kyc.load(case_id)
    if c is None:
        raise HTTPException(404, "KYC case not found")
    return c


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except kyc.ConsentRequired as e:
        raise HTTPException(403, str(e)) from e
    except BadUpload as e:
        raise HTTPException(422, str(e)) from e
    except OcrUnavailable as e:
        raise HTTPException(503, str(e)) from e
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/status")
def status():
    return {"ocr_available": ocr_available(), "notice_version": kyc.NOTICE_VERSION,
            "retention_days": kyc.RETENTION_DAYS}


class CreateCase(BaseModel):
    order_id: str
    language: Optional[Language] = None


@router.post("/cases", response_model=kyc.CaseView)
def create(req: CreateCase):
    info = orders.contact_and_language(req.order_id)
    if info is None:
        raise HTTPException(404, "order not found")
    name, lang = info
    return kyc.view(kyc.create(req.order_id, req.language or lang or "en", name))


@router.get("/cases/{case_id}", response_model=kyc.CaseView)
def get(case_id: str):
    return kyc.view(_case(case_id))


class ConsentReq(BaseModel):
    purposes: list[str]
    notice_version: str


@router.post("/cases/{case_id}/consent", response_model=kyc.CaseView)
def consent(case_id: str, req: ConsentReq):
    return kyc.view(_guard(kyc.give_consent, _case(case_id), req.purposes, req.notice_version))


class GstinReq(BaseModel):
    gstin: Optional[str] = None
    no_gstin: bool = False


@router.post("/cases/{case_id}/gstin", response_model=kyc.GstinResult)
def gstin(case_id: str, req: GstinReq):
    return _guard(kyc.set_gstin, _case(case_id), req.gstin, req.no_gstin)


class UdyamReq(BaseModel):
    udyam_number: Optional[str] = None


@router.post("/cases/{case_id}/udyam", response_model=kyc.CaseView)
def udyam(case_id: str, req: UdyamReq):
    return kyc.view(_guard(kyc.set_udyam, _case(case_id), req.udyam_number))


@router.post("/cases/{case_id}/documents/{doc_type}", response_model=kyc.CaseView)
async def upload(case_id: str, doc_type: str, file: UploadFile = File(...)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Photo is too large (max 8 MB).")
    if not data:
        raise HTTPException(422, "Empty file.")
    return kyc.view(_guard(kyc.upload, _case(case_id), doc_type, data))


@router.post("/cases/{case_id}/evaluate", response_model=kyc.CaseView)
def evaluate(case_id: str):
    return kyc.view(_guard(kyc.run_evaluation, _case(case_id)))


@router.delete("/cases/{case_id}/documents", response_model=kyc.CaseView)
def withdraw(case_id: str):
    """Withdraw consent: stored documents are deleted immediately."""
    return kyc.view(kyc.delete_documents(_case(case_id)))


@router.get("/cases/{case_id}/audit")
def case_audit(case_id: str):
    _case(case_id)
    return audit.for_entity(case_id)


@router.get("/samples")
def samples():
    return kyc.sample_list()


@router.post("/samples/{kid}/run", response_model=kyc.CaseView)
def run_sample(kid: str, language: Language = "en"):
    """Demo/acceptance: run a specimen applicant (K01-K12) through the same pipeline. Labelled as demo."""
    return kyc.view(_guard(kyc.run_sample, kid, language))


@router.post("/cases/{case_id}/use-sample/{kid}", response_model=kyc.CaseView)
def use_sample(case_id: str, kid: str):
    return kyc.view(_guard(kyc.use_sample, _case(case_id), kid))


_THUMBS: dict[str, bytes] = {}


@router.get("/specimen/{doc_type}.png")
def specimen(doc_type: str):
    """A small picture of what each document looks like (from the synthetic specimen set), to guide owners."""
    import io

    from fastapi.responses import Response
    from PIL import Image

    from app import config

    if doc_type not in ("gst_certificate", "udyam_certificate", "address_proof", "signatory_id"):
        raise HTTPException(404, "unknown document type")
    if doc_type not in _THUMBS:
        with Image.open(config.KYC_DOCS_DIR / f"K12_{doc_type}.png") as im:
            im = im.convert("RGB")
            if doc_type != "signatory_id":
                im = im.crop((0, 0, im.width, int(im.height * 0.42)))  # the informative top of the page
            im.thumbnail((360, 360))
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)
            _THUMBS[doc_type] = buf.getvalue()
    return Response(_THUMBS[doc_type], media_type="image/png", headers={"Cache-Control": "max-age=86400"})
