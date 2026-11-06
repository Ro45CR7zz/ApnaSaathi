from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.advisor.slots import Slots
from app.backoffice import service as bo
from app.kyc import service as kyc
from app.kyc.ocr import available as ocr_available
from app.main import app
from app.orders import service as orders
from app.orders import tracker
from app.orders.service import Contact
from app.quotes import service as qs

TOKEN = {"X-Ops-Token": bo.ops_token()}


def new_order(lang="en", needs=("uptime_backup", "cctv")):
    q = qs.create_from_slots(Slots(business_type="Kirana store", city="Jaipur", employees=3, sites=1, has_gstin=True,
                                   needs=list(needs), needs_confirmed=True), lang)
    return orders.accept(q.id, Contact(name="Pooja Agarwal", mobile="9876543210", consent_contact=True)).id


def verified_order(lang="en", **kw):
    oid = new_order(lang, **kw)
    kyc._update_order(oid, "KYC_VERIFIED", "test")
    return oid


def test_full_lifecycle_with_notifications():
    oid = new_order()
    v = tracker.view(oid)
    assert v.state == "KYC_PENDING" and v.pending[0].kind == "upload_documents"
    assert v.steps[0].status == "done" and v.steps[1].status == "current"
    kyc._update_order(oid, "KYC_VERIFIED", "test")
    v = tracker.view(oid)
    assert v.pending[0].kind == "pay" and v.pending[0].amount_inr == v.bill.first_payment_inr
    v = tracker.pay(oid, today=date(2026, 11, 6))
    assert v.state == "CONFIRMED" and v.steps[2].status == "done"
    fibre = next(l for l in v.lines if l.product_id == "P01")
    assert fibre.expected_ready == "2026-11-13"  # 5 install days + 2 tier-2 buffer
    v = tracker.simulate(oid, "advance")
    assert v.state == "FULFILLING" and any(l.state == "INSTALL_VISIT" for l in v.lines)
    v = tracker.simulate(oid, "advance")
    assert all(l.state in ("INSTALLED", "ACTIVE") for l in v.lines)
    v = tracker.simulate(oid, "advance")
    assert v.state == "ACTIVE" and all(s.status == "done" for s in v.steps)
    assert v.bill.next_bill_date is not None
    texts = [n.text for n in v.notifications]
    assert any("All services are working" in t for t in texts) and any("placed" in t for t in texts)
    with pytest.raises(ValueError):
        tracker.simulate(oid, "advance")


def test_feasibility_failure_and_switch_to_airfiber():
    oid = verified_order()
    tracker.pay(oid)
    before = tracker.view(oid).bill.monthly_total_inr
    v = tracker.simulate(oid, "feasibility_failed")
    assert v.state == "ON_HOLD" and v.pending[0].kind == "switch_airfiber"
    v = tracker.switch_to_airfiber(oid)
    ids = {l.product_id: l.state for l in v.lines}
    assert "P04" in ids and ids["P09"] == "CANCELLED"  # backup internet needs a fibre line
    assert v.bill.monthly_total_inr < before
    assert v.state == "FULFILLING"


def test_delay_moves_eta_and_tells_owner_in_hindi():
    oid = verified_order("hi")
    tracker.pay(oid)
    eta = tracker.view(oid).expected_activation
    v = tracker.simulate(oid, "delay", reason="permission")
    assert v.expected_activation > eta
    assert "बिल्डिंग की अनुमति" in v.notifications[0].text


def test_payment_failure_then_retry():
    oid = verified_order()
    v = tracker.simulate(oid, "payment_failed")
    assert v.state == "PAYMENT_FAILED" and v.pending[0].kind == "retry_payment"
    assert v.steps[2].status == "attention"
    assert tracker.pay(oid).state == "CONFIRMED"


def test_kyc_rerun_never_moves_paid_order_backwards():
    oid = verified_order()
    tracker.pay(oid)
    kyc._update_order(oid, "KYC_ACTION_NEEDED", "late re-check")
    assert tracker.view(oid).state == "CONFIRMED"


def test_offer_suggestions_respect_margin_floor():
    s = bo.offer_suggestion(0.3, "Micro retail & services")
    assert s["recommended"] in {o["offer"] for o in s["options"] if o["allowed"]}
    assert all(o["margin_after_discount"] >= 0.30 for o in s["options"] if o["allowed"])
    assert "assumption" in s["assumptions"].lower()


def test_ops_endpoints_need_token_and_rank_leads():
    with TestClient(app) as c:
        assert c.get("/api/ops/leads").status_code == 401
        r = c.get("/api/ops/leads?limit=20", headers=TOKEN).json()
        scores = [x["score"] for x in r["rows"]]
        assert scores == sorted(scores, reverse=True) and r["total"] > 4000
        assert 0.6 < r["model"]["cv_auc"] < 0.8
        f = c.get("/api/ops/funnel", headers=TOKEN).json()
        assert f["baseline_q2_2026"][0]["count"] == 5000 and f["baseline_q2_2026"][-1]["count"] == 368


def test_handoff_appears_in_back_office():
    with TestClient(app) as c:
        sid = c.post("/api/advisor/sessions", json={"language": "hi"}).json()["session_id"]
        c.post(f"/api/advisor/sessions/{sid}/message", json={"text": "किराना दुकान, 3 लोग"})
        c.post(f"/api/advisor/sessions/{sid}/message", json={"text": "talk to a person"})
        h = c.get("/api/ops/handoffs", headers=TOKEN).json()
        mine = next(x for x in h if x["session_id"] == sid)
        assert mine["known"]["employees"] == 3 and 0 <= mine["score"] <= 1


@pytest.mark.skipif(not ocr_available(), reason="Tesseract OCR is not installed")
def test_manual_review_queue_decision_flows_to_order(tmp_path, monkeypatch):
    monkeypatch.setattr(kyc, "UPLOAD_DIR", tmp_path / "up")
    monkeypatch.setattr(kyc, "KEY_FILE", tmp_path / ".k")
    oid = new_order()
    with TestClient(app) as c:
        cid = c.post("/api/kyc/cases", json={"order_id": oid}).json()["id"]
        c.post(f"/api/kyc/cases/{cid}/consent", json={"purposes": list(kyc.PURPOSES), "notice_version": kyc.NOTICE_VERSION})
        r = c.post(f"/api/kyc/cases/{cid}/use-sample/K07").json()
        assert r["outcome"] == "MANUAL_REVIEW"
        assert tracker.view(oid).state == "KYC_MANUAL_REVIEW"
        q = c.get("/api/ops/kyc", headers=TOKEN).json()
        assert any(x["id"] == cid for x in q)
        img = c.get(f"/api/ops/kyc/{cid}/documents/gst_certificate", headers=TOKEN)
        assert img.status_code == 200 and img.content[:4] == b"\x89PNG"
        assert c.post(f"/api/ops/kyc/{cid}/decision", headers=TOKEN, json={"decision": "approve", "note": " "}).status_code == 409
        d = c.post(f"/api/ops/kyc/{cid}/decision", headers=TOKEN,
                   json={"decision": "approve", "note": "Trade name verified by phone with owner"}).json()
        assert d["outcome"] == "VERIFIED"
        assert tracker.view(oid).state == "KYC_VERIFIED"
        trail = c.get(f"/api/ops/audit/{cid}", headers=TOKEN).json()
        actions = [e["action"] for e in trail]
        assert "document_viewed" in actions and "kyc_review_approve" in actions
