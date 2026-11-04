import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import config
from app.db.import_data import import_all
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_import_row_counts(tmp_path):
    db = tmp_path / "t.db"
    counts = import_all(db)
    assert counts == config.EXPECTED_ROWS
    with sqlite3.connect(db) as con:
        assert con.execute("select count(*) from gst_registry where status='Active'").fetchone()[0] == 3266


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok", "products": 25}


def test_gstin_lookup_masks_and_labels_mock(client):
    r = client.get("/api/registry/gstin/37IHKXV5167L1ZS").json()
    assert r["found"] and r["status"] == "Cancelled"
    assert r["gstin_masked"] == "37I••••••••L1ZS"
    assert "MOCK" in r["source"]


def test_gstin_lookup_returns_suggestion_without_record(client):
    r = client.get("/api/registry/gstin/19E0GXH4115Y1ZL").json()
    assert not r["found"]
    assert r["check"]["status"] == "corrected_suggestion"
    assert r["check"]["suggestion"] == "19EOGXH4115Y1ZL"


def test_udyam_lookup(client):
    assert client.get("/api/registry/udyam/UDYAM-AP-00-9751562").json()["found"]
    assert client.get("/api/registry/udyam/NOT-A-NUMBER").status_code == 422


def test_quote_end_to_end_no_gstin_kirana(client):
    body = {
        "profile": {"segment": "micro", "city": "Jaipur", "employees": 3, "sites": 1},
        "lines": [{"product_id": "P01", "qty": 1}, {"product_id": "P07", "qty": 2},
                  {"product_id": "P19", "qty": 1}],
        "options": {"selfserve_autopay": True},
        "language": "hi",
    }
    r = client.post("/api/quotes/price", json=body).json()
    assert r["resolved"]["profile"]["city_tier"] == 2
    assert r["resolved"]["profile"]["gstin_status"] == "None"
    assert r["validation"]["valid"]
    assert r["quote"]["earned_savings_fraction"] == 0.5


def test_quote_blocked_for_invalid_bundle(client):
    body = {"profile": {"segment": "micro", "city": "Jaipur", "employees": 3, "sites": 1},
            "lines": [{"product_id": "P15", "qty": 1}]}
    r = client.post("/api/quotes/price", json=body).json()
    assert not r["validation"]["valid"] and r["quote"] is None
    assert r["validation"]["issues"][0]["code"] == "GSTIN_REQUIRED"


def test_cancelled_gstin_from_registry_blocks_gst_products(client):
    body = {"profile": {"segment": "prof", "city": "Visakhapatnam", "employees": 8, "sites": 1,
                        "gstin": "37IHKXV5167L1ZS"}, "language": "en"}
    r = client.post("/api/rules/eligibility", json=body).json()
    p15 = next(p for p in r["products"] if p["product_id"] == "P15")
    assert not p15["eligible"] and p15["issues"][0]["code"] == "GSTIN_INACTIVE"


def test_unknown_city_note(client):
    body = {"profile": {"segment": "micro", "city": "Shimla", "employees": 2, "sites": 1}}
    r = client.post("/api/rules/eligibility", json=body).json()
    assert r["resolved"]["city_known"] is False and r["resolved"]["notes"]
