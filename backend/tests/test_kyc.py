"""Smart KYC tests: the 12 supplied applicants (acceptance), check logic, privacy and API."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.kyc import service as kyc
from app.kyc.checks import Declared, DocResult, evaluate, names_match, ocr_equal, pincode, split_prop
from app.kyc.ocr import available as ocr_available

needs_ocr = pytest.mark.skipif(not ocr_available(), reason="Tesseract OCR is not installed")

EXPECTED = {
    "K01": ("BLOCKED", {"GSTIN_INACTIVE", "UDYAM_NUMBER_MISSING"}),
    "K02": ("VERIFIED", {"DOC_STRAIGHTENED"}),
    "K03": ("VERIFIED", set()),
    "K04": ("NEEDS_FIX", {"DOC_BLURRY"}),
    "K05": ("NEEDS_FIX", {"DOC_MISSING"}),
    "K06": ("NEEDS_FIX", {"GSTIN_DOC_MISMATCH"}),
    "K07": ("MANUAL_REVIEW", {"GST_NAME_MISMATCH"}),
    "K08": ("VERIFIED", {"GSTIN_DOC_OCR_FIXED"}),
    "K09": ("VERIFIED", set()),
    "K10": ("MANUAL_REVIEW", {"SIGNATORY_AUTHORITY"}),
    "K11": ("NEEDS_FIX", {"BILL_TOO_OLD"}),
    "K12": ("VERIFIED", set()),
}


@pytest.fixture(autouse=True)
def tmp_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(kyc, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(kyc, "KEY_FILE", tmp_path / ".kyc_key")


@needs_ocr
@pytest.mark.parametrize("kid", list(EXPECTED))
def test_sample_applicants(kid):
    outcome, must = EXPECTED[kid]
    c = kyc.run_sample(kid)
    codes = {ch.code for ch in c.checks}
    assert c.outcome == outcome, [(ch.code, ch.status) for ch in c.checks]
    assert must <= codes


@needs_ocr
def test_k06_real_digit_difference_is_not_explained_away():
    c = kyc.run_sample("K06")
    assert "GSTIN_DOC_OCR_FIXED" not in {ch.code for ch in c.checks}


@needs_ocr
def test_hindi_messages():
    c = kyc.run_sample("K11", "hi")
    msg = next(ch.message for ch in c.checks if ch.code == "BILL_TOO_OLD")
    assert "2025-10-31" in msg and "बिल" in msg


# ---- check logic without OCR ----

def test_ocr_equal():
    assert ocr_equal("27QHIXKO658U1ZL", "27QHJXK0658U1ZL") == [4, 7]
    assert ocr_equal("08YKZXS8189L1Z0", "08YKZXS5189L1ZO") == [-1]  # 8 vs 5 is a real difference


def test_names_and_pincode():
    assert names_match("Joseph Shah (Prop. Harmony Dental! Care)", "Joseph Shah (Prop. Harmony Dental Care)")
    assert not names_match("Neha Banerjee (Prop. Shri Physio Clinic)", "Neha Banerjee (Prop. Neelgiri Physio Clinic)")
    assert split_prop("Neha Kaur (Prop. Vindhya Tours & Travels)") == ("Neha Kaur", "Vindhya Tours & Travels")
    assert pincode("Shop/Unit 38, Civil Lines, Kochi, Kerala - 752083") == "752083"
    assert pincode("Mumbai, Maharashtra570043") == "570043"


GOOD = {  # K12's real details, entered as already-extracted fields
    "gst_certificate": {"gstin": "37NBLXS1145E1ZU", "legal_name": "Pooja Agarwal (Prop. Star Electronics)",
                        "trade_name": "Star Electronics",
                        "address": "Shop/Unit 216, Nehru Nagar, Visakhapatnam, Andhra Pradesh - 762071"},
    "address_proof": {"billed_to": "Star Electronics", "address": "Visakhapatnam - 762071", "bill_date": "2026-07-06"},
    "signatory_id": {"name": "Pooja Agarwal", "business": "Star Electronics", "valid_till": "2029-03-03"},
}


def docs(**override):
    out = {k: DocResult(doc_type=k, found_type=k, fields=dict(v)) for k, v in GOOD.items()}
    for k, v in override.items():
        out[k].fields.update(v)
    return out


def test_clean_case_verified():
    o, checks = evaluate(Declared(gstin="37NBLXS1145E1ZU"), docs())
    assert o == "VERIFIED" and all(c.status != "fail" for c in checks)


def test_expired_signatory_and_old_bill_need_fix():
    o, checks = evaluate(Declared(gstin="37NBLXS1145E1ZU"),
                         docs(signatory_id={"valid_till": "2026-01-01"}, address_proof={"bill_date": "2026-01-01"}))
    assert o == "NEEDS_FIX"
    assert {"SIGNATORY_EXPIRED", "BILL_TOO_OLD"} <= {c.code for c in checks}


def test_bill_for_another_business_goes_to_review():
    o, checks = evaluate(Declared(gstin="37NBLXS1145E1ZU"), docs(address_proof={"billed_to": "Someone Else Traders"}))
    assert o == "MANUAL_REVIEW" and "BILL_NAME_MISMATCH" in {c.code for c in checks}


def test_wrong_document_in_slot():
    d = docs()
    d["signatory_id"] = DocResult(doc_type="signatory_id", found_type="address_proof", fields={})
    o, checks = evaluate(Declared(gstin="37NBLXS1145E1ZU"), d)
    assert o == "NEEDS_FIX" and "DOC_WRONG_TYPE" in {c.code for c in checks}


def test_no_registration_goes_to_review():
    d = {k: v for k, v in docs().items() if k != "gst_certificate"}
    o, checks = evaluate(Declared(no_gstin=True), d)
    assert o == "MANUAL_REVIEW" and "NO_REGISTRATION" in {c.code for c in checks}


def test_gstin_not_in_registry_blocks():
    o, _ = evaluate(Declared(gstin="37NBLXS1145E1ZV"), docs())
    assert o == "BLOCKED"


# ---- privacy and service ----

def test_nothing_processed_before_consent():
    c = kyc.create(None, "en")
    with pytest.raises(kyc.ConsentRequired):
        kyc.set_gstin(c, "37NBLXS1145E1ZU")
    with pytest.raises(kyc.ConsentRequired):
        kyc.upload(c, "signatory_id", b"x")
    with pytest.raises(ValueError):
        kyc.give_consent(c, ["verify_business"], kyc.NOTICE_VERSION)  # both purposes needed


@needs_ocr
def test_documents_encrypted_at_rest_deleted_on_withdrawal_and_audit_masked():
    from app import audit
    c = kyc.run_sample("K12")
    raw = (kyc.config.KYC_DOCS_DIR / "K12_signatory_id.png").read_bytes()
    stored = kyc._doc_path(c.id, "signatory_id").read_bytes()
    assert stored != raw and b"PNG" not in stored[:16]
    assert kyc.read_document(c, "signatory_id", actor="reviewer:test") == raw
    log = json.dumps(audit.for_entity(c.id), ensure_ascii=False)
    assert "37NBLXS1145E1ZU" not in log and "37N••••••••E1ZU" in log
    kyc.delete_documents(c)
    assert not (kyc.UPLOAD_DIR / c.id).exists()
    assert not kyc.load(c.id).consents


@needs_ocr
def test_retention_purge():
    c = kyc.run_sample("K09")
    kyc.close(c)
    assert kyc.purge_expired(now=datetime.now(timezone.utc) + timedelta(days=kyc.RETENTION_DAYS + 1)) >= 1
    assert not (kyc.UPLOAD_DIR / c.id).exists()


def test_gstin_entry_paths():
    c = kyc.create(None, "en")
    kyc.give_consent(c, list(kyc.PURPOSES), kyc.NOTICE_VERSION)
    assert kyc.set_gstin(c, "19E0GXH4115Y1ZL").status == "confirm"       # OCR-like typo -> confirm suggestion
    assert kyc.set_gstin(c, "37NBLXS1145E1ZV").status == "invalid"       # checksum fails
    assert kyc.set_gstin(c, "37IHKXV5167L1ZS").status == "inactive"      # K01 cancelled
    r = kyc.set_gstin(c, "37NBLXS1145E1ZU")
    assert r.status == "ok" and r.case.gst_prefill["trade_name"] == "Star Electronics"
    assert r.case.required_docs == ["gst_certificate", "address_proof", "signatory_id"]


def test_non_image_upload_rejected():
    c = kyc.create(None, "en")
    kyc.give_consent(c, list(kyc.PURPOSES), kyc.NOTICE_VERSION)
    with pytest.raises(kyc.BadUpload):
        kyc.upload(c, "signatory_id", b"%PDF-1.4 not an image")


@needs_ocr
def test_api_order_to_kyc_verified():
    from app.main import app
    with TestClient(app) as cl:
        sid = cl.post("/api/advisor/sessions", json={"language": "en"}).json()["session_id"]
        cl.post(f"/api/advisor/sessions/{sid}/form", json={"slots": {
            "business_type": "Kirana store", "city": "Jaipur", "employees": 3, "sites": 1, "has_gstin": True,
            "needs": ["internet"]}})
        q = cl.post("/api/quotes", json={"session_id": sid}).json()
        o = cl.post(f"/api/quotes/{q['id']}/accept",
                    json={"name": "Pooja Agarwal", "mobile": "9876543210", "consent_contact": True}).json()
        case = cl.post("/api/kyc/cases", json={"order_id": o["id"]}).json()
        cid = case["id"]
        assert cl.post(f"/api/kyc/cases/{cid}/gstin", json={"gstin": "37NBLXS1145E1ZU"}).status_code == 403
        cl.post(f"/api/kyc/cases/{cid}/consent", json={"purposes": ["verify_business", "store_documents"],
                                                      "notice_version": kyc.NOTICE_VERSION})
        r = cl.post(f"/api/kyc/cases/{cid}/gstin", json={"gstin": "37NBLXS1145E1ZU"}).json()
        assert r["status"] == "ok"
        for dt in ("gst_certificate", "address_proof", "signatory_id"):
            with open(kyc.config.KYC_DOCS_DIR / f"K12_{dt}.png", "rb") as f:
                up = cl.post(f"/api/kyc/cases/{cid}/documents/{dt}", files={"file": (f"{dt}.png", f, "image/png")})
            assert up.status_code == 200
        assert up.json()["uploaded"]["gst_certificate"]["fields"]["gstin"] == "37N••••••••E1ZU"
        res = cl.post(f"/api/kyc/cases/{cid}/evaluate").json()
        assert res["outcome"] == "VERIFIED"
        assert cl.get(f"/api/orders/{o['id']}").json()["state"] == "KYC_VERIFIED"
        bad = cl.post(f"/api/kyc/cases/{cid}/documents/signatory_id", files={"file": ("x.png", b"nope", "image/png")})
        assert bad.status_code == 422
