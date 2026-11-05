import pytest
from fastapi.testclient import TestClient

from app.advisor.slots import Slots
from app.catalogue.display import inr
from app.main import app
from app.orders.service import Contact
from app.quotes import service as qs


def kirana(**kw):
    base = dict(business_type="Kirana store", city="Jaipur", employees=3, sites=1, has_gstin=False,
                needs=["billing_upi", "cctv"], needs_confirmed=True)
    base.update(kw)
    return Slots(**base)


def ids(v):
    return [l.product_id for l in v.lines]


def test_create_quote_logs_impression_and_has_display_info():
    v = qs.create_from_slots(kirana(), "hi")
    assert ids(v) == ["P01", "P19", "P23"]  # base first, then needs in the order stated
    assert v.lines[0].icon == "router" and "इंटरनेट" in v.lines[0].plain
    assert v.business == "किराना दुकान"
    assert not v.lines[0].removable and v.lines[1].removable
    assert [e["kind"] for e in qs.events(v.id)] == ["shown"]
    assert v.priced.earned_savings_fraction == 0.25  # 3 products


def test_toggle_addon_and_remove_back_to_addons():
    v = qs.create_from_slots(kirana())
    addon = v.addons[0].product_id
    v2 = qs.apply_change(qs.load(v.id), qs.QuoteChange(add=addon))
    assert addon in ids(v2) and addon not in [a.product_id for a in v2.addons]
    assert v2.priced.monthly_subtotal_inr > v.priced.monthly_subtotal_inr
    v3 = qs.apply_change(qs.load(v.id), qs.QuoteChange(remove=addon))
    assert addon not in ids(v3) and addon in [a.product_id for a in v3.addons]
    assert [e["kind"] for e in qs.events(v.id)] == ["shown", "change", "change"]


def test_internet_line_cannot_be_removed():
    v = qs.create_from_slots(kirana())
    with pytest.raises(ValueError):
        qs.apply_change(qs.load(v.id), qs.QuoteChange(remove="P01"))


def test_commitment_and_autopay_reach_catalogue_minimum():
    v = qs.create_from_slots(kirana())
    v2 = qs.apply_change(qs.load(v.id), qs.QuoteChange(commit_extra_12m=True, selfserve_autopay=True))
    assert v2.priced.earned_savings_fraction == 1.0
    assert v2.priced.contract_months == 24
    assert all(l.monthly_inr == l.qty * qs.load_catalogue()[l.product_id].price_min_inr_per_month for l in v2.lines)


def test_partner_channel_gets_no_selfserve_saving():
    v = qs.create_from_slots(kirana(), channel="partner")
    v2 = qs.apply_change(qs.load(v.id), qs.QuoteChange(selfserve_autopay=True))
    assert not v2.selfserve_saving_available
    assert "selfserve_autopay" not in {s.code for s in v2.priced.savings}


def test_quantity_change_and_limits():
    v = qs.create_from_slots(kirana())
    v2 = qs.apply_change(qs.load(v.id), qs.QuoteChange(set_qty={"P23": 4}))
    assert next(l for l in v2.lines if l.product_id == "P23").qty == 4
    with pytest.raises(ValueError):
        qs.apply_change(qs.load(v.id), qs.QuoteChange(set_qty={"P01": 3}))  # one per location


def test_airfiber_swap_drops_lines_that_need_fibre_and_swaps_back():
    v = qs.create_from_slots(kirana(needs=["uptime_backup", "cctv"]))
    assert "P09" in ids(v)
    v2 = qs.apply_change(qs.load(v.id), qs.QuoteChange(use_airfiber=True))
    assert v2.using_airfiber and ids(v2)[0] == "P04"
    assert "P09" not in ids(v2) and any(e.product_id == "P09" for e in v2.excluded)
    assert v2.notices  # owner is told why backup internet was removed
    v3 = qs.apply_change(qs.load(v.id), qs.QuoteChange(use_airfiber=False))
    assert ids(v3)[0] == "P01"
    assert "P09" in [a.product_id for a in v3.addons]  # offered again, not forced back in
    assert not any(e.product_id == "P09" for e in v3.excluded)


def test_adding_wifi_after_airfiber_still_valid():
    v = qs.create_from_slots(kirana(needs=["internet"]))
    qs.apply_change(qs.load(v.id), qs.QuoteChange(use_airfiber=True))
    v2 = qs.load(v.id)
    wifi = next((a for a in v2.available_addons if a.product_id == "P22"), None)
    if wifi:
        v3 = qs.apply_change(v2, qs.QuoteChange(add="P22"))
        assert "P22" in ids(v3)  # P22 works with P04


def test_share_text_hindi_indian_digits():
    v = qs.create_from_slots(kirana(employees=60, sites=6, business_type="Restaurant", city="Bengaluru",
                                    has_gstin=True, needs=["cctv", "uptime_backup"]), "hi")
    t = qs.share_text(qs.load(v.id))
    assert "हर महीने" in t and v.id in t
    assert inr(v.priced.monthly_total_inr) in t


def test_accept_creates_order_masks_contact_and_locks_quote():
    from app.orders import service as orders
    from datetime import date
    v = qs.create_from_slots(kirana())
    o = orders.accept(v.id, Contact(name="Ramesh Gupta", mobile="+91 98765 43210", consent_contact=True),
                      today=date(2026, 7, 15))
    assert o.state == "KYC_PENDING"
    assert o.contact_name_masked == "R. G." and o.contact_mobile_masked.endswith("10")
    assert "98765" not in o.contact_mobile_masked
    # tier 2 Jaipur: 1 KYC day + 5 install days (fibre) + 2 buffer
    assert o.expected_activation == date(2026, 7, 23)
    with pytest.raises(ValueError):
        qs.apply_change(qs.load(v.id), qs.QuoteChange(commit_extra_12m=True))
    with pytest.raises(ValueError):
        orders.accept(v.id, Contact(name="Ramesh", mobile="9876543210", consent_contact=True))


@pytest.mark.parametrize("bad", [dict(name="R", mobile="9876543210", consent_contact=True),
                                 dict(name="Ramesh", mobile="12345", consent_contact=True),
                                 dict(name="Ramesh", mobile="9876543210", consent_contact=False),
                                 dict(name="Ramesh <script>", mobile="9876543210", consent_contact=True)])
def test_contact_validation(bad):
    with pytest.raises(Exception):
        Contact(**bad)


def test_api_full_journey():
    with TestClient(app) as c:
        sid = c.post("/api/advisor/sessions", json={"language": "hi"}).json()["session_id"]
        r = c.post(f"/api/advisor/sessions/{sid}/form", json={"slots": {"business_type": "Salon"}}).json()
        assert r["expecting"] == "city" and r["slots"]["needs_confirmed"] is False
        r = c.post(f"/api/advisor/sessions/{sid}/form",
                   json={"slots": {"city": "Lucknow", "employees": 4, "sites": 1, "has_gstin": False,
                                   "needs": ["billing_upi", "guest_wifi"]}}).json()
        assert r["recommendation"]
        q = c.post("/api/quotes", json={"session_id": sid}).json()
        assert q["language"] == "hi" and q["business"] == "सैलून"
        q2 = c.patch(f"/api/quotes/{q['id']}", json={"commit_extra_12m": True}).json()
        assert q2["priced"]["contract_months"] == 24
        assert c.patch(f"/api/quotes/{q['id']}", json={"remove": "P01"}).status_code == 409
        assert "apnaSaathi" in c.get(f"/api/quotes/{q['id']}/share").json()["text"]
        bad = c.post(f"/api/quotes/{q['id']}/accept", json={"name": "A", "mobile": "1", "consent_contact": True})
        assert bad.status_code == 422
        o = c.post(f"/api/quotes/{q['id']}/accept",
                   json={"name": "Sunita Verma", "mobile": "9876543210", "consent_contact": True}).json()
        assert o["state"] == "KYC_PENDING" and c.get(f"/api/orders/{o['id']}").status_code == 200
        kinds = [e["kind"] for e in c.get(f"/api/quotes/{q['id']}/events").json()]
        assert kinds == ["shown", "change", "share", "accepted"]


def test_create_quote_before_advisor_finished_is_rejected():
    with TestClient(app) as c:
        sid = c.post("/api/advisor/sessions", json={}).json()["session_id"]
        assert c.post("/api/quotes", json={"session_id": sid}).status_code == 409
