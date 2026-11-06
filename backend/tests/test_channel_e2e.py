"""Phase 9: messaging webhook, hardening, and one end-to-end journey through the public API."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import config, security
from app.backoffice import service as bo
from app.channels import whatsapp
from app.kyc import service as kyc
from app.kyc.ocr import available as ocr_available
from app.main import app
from app.quotes import service as qs

TOKEN = {"X-Ops-Token": bo.ops_token()}
HI_CHAT = ["नया", "किराना दुकान, जयपुर, 3 लोग", "एक", "GST नहीं है", "UPI बिलिंग और CCTV"]


def test_twilio_form_post_gets_twiml_and_phone_is_not_stored():
    phone = "whatsapp:+919811122233"
    with TestClient(app) as c:
        r = c.post("/api/channels/whatsapp", data={"From": phone, "Body": "hello"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
        assert r.text.startswith("<?xml") and "<Message>" in r.text and "Accel" in r.text
        assert c.post("/api/channels/whatsapp", data={"Body": "hi"}).status_code == 422
    con = sqlite3.connect(config.DB_PATH)
    dump = "\n".join(con.iterdump())
    assert "9811122233" not in dump  # only a salted hash of the sender is kept


def test_hindi_chat_ends_with_quote_and_deep_link():
    with TestClient(app) as c:
        r = None
        for t in HI_CHAT:
            r = c.post("/api/channels/whatsapp", json={"from": "sim:test-hi", "text": t, "language": "hi"}).json()
        assert r["quote_id"] and r["quote_link"].endswith(f"/#/q/{r['quote_id']}")
        assert "₹" in r["reply"] and "GST" in r["reply"] and r["language"] == "hi"
        q = c.get(f"/api/quotes/{r['quote_id']}?language=hi").json()
        assert q["status"] == "open" and qs.load(r["quote_id"]).channel == "whatsapp"


def test_quick_replies_are_understood_and_session_survives():
    s = "sim:test-chips"
    first = whatsapp.handle(s, "restart", "en")
    assert first.quick_replies and first.language == "en"
    nxt = whatsapp.handle(s, first.quick_replies[0], "en")  # tapping a chip sends its label
    assert nxt.session_id == first.session_id and nxt.reply != first.reply


def test_security_headers_and_size_cap():
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
        assert "default-src 'self'" in r.headers["content-security-policy"]
        assert r.headers["cache-control"] == "no-store"
        big = c.post("/api/channels/whatsapp", content=b"x", headers={"content-length": str(20 * 1024 * 1024),
                                                                       "content-type": "application/json"})
        assert big.status_code == 413


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setenv("APNASAATHI_RATE_LIMIT", "1")
    monkeypatch.setattr(security, "LIMITS", [("/api/channels/", "POST", 3, 60)])
    monkeypatch.setattr(security, "limiter", security.RateLimiter())
    with TestClient(app) as c:
        codes = [c.post("/api/channels/whatsapp", json={"from": "sim:rl", "text": "hi"}).status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3:] == [429, 429]


@pytest.mark.skipif(not ocr_available(), reason="Tesseract OCR is not installed")
def test_end_to_end_web_journey(tmp_path, monkeypatch):
    """Advisor text -> quote -> change -> order -> KYC (sample) -> pay -> installation -> ACTIVE."""
    monkeypatch.setattr(kyc, "UPLOAD_DIR", tmp_path / "up")
    monkeypatch.setattr(kyc, "KEY_FILE", tmp_path / ".k")
    with TestClient(app) as c:
        sid = c.post("/api/advisor/sessions", json={"language": "en"}).json()["session_id"]
        r = None
        for t in ["I run a kirana store in Jaipur with 3 staff", "one shop", "yes we have GST",
                  "UPI billing and CCTV"]:
            r = c.post(f"/api/advisor/sessions/{sid}/message", json={"text": t}).json()
        assert r["recommendation"], r["text"]
        q = c.post("/api/quotes", json={"session_id": sid, "language": "en"}).json()
        q2 = c.patch(f"/api/quotes/{q['id']}", json={"commit_extra_12m": True, "selfserve_autopay": True}).json()
        assert q2["priced"]["monthly_total_inr"] < q["priced"]["monthly_total_inr"]
        o = c.post(f"/api/quotes/{q['id']}/accept",
                   json={"name": "Pooja Agarwal", "mobile": "9876543210", "consent_contact": True}).json()
        oid = o["id"]
        cid = c.post("/api/kyc/cases", json={"order_id": oid}).json()["id"]
        c.post(f"/api/kyc/cases/{cid}/consent", json={"purposes": list(kyc.PURPOSES), "notice_version": kyc.NOTICE_VERSION})
        assert c.post(f"/api/kyc/cases/{cid}/use-sample/K03").json()["outcome"] == "VERIFIED"
        t = c.post(f"/api/orders/{oid}/pay").json()
        assert t["state"] == "CONFIRMED"
        for _ in range(8):
            t = c.post(f"/api/ops/orders/{oid}/simulate", headers=TOKEN, json={"event": "advance"}).json()
            if t["state"] == "ACTIVE":
                break
        assert t["state"] == "ACTIVE"
        assert all(s["status"] == "done" for s in t["steps"])
