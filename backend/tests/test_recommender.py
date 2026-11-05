from app.advisor.slots import Slots
from app.recommender.engine import recommend
from app.recommender.segment import infer_segment
from app.rules.engine import validate_bundle
from app.catalogue.models import BundleLine


def S(**kw) -> Slots:
    kw.setdefault("needs_confirmed", True)
    return Slots(**kw)


def ids(rec):
    return [l.product_id for l in rec.lines]


def assert_valid(rec):
    v = validate_bundle(rec.profile, [BundleLine(product_id=l.product_id, qty=l.qty) for l in rec.lines])
    assert v.valid, v.issues


def test_kirana_without_gstin_gets_non_gst_bundle_and_reason():
    rec = recommend(S(business_type="Kirana store", city="Jaipur", employees=3, sites=1, has_gstin=False,
                      needs=["billing_upi", "cctv", "whatsapp_customers", "mobile_lines"]))
    assert rec.segment == "micro"
    assert ids(rec) == ["P01", "P19", "P23", "P07"]
    assert [(e.product_id, e.reason_code) for e in rec.excluded] == [("P15", "GSTIN_REQUIRED")]
    assert rec.quote.monthly_subtotal_inr > 0 and rec.quote.one_time_subtotal_inr == 2500 + 2 * 1800
    assert_valid(rec)


def test_tier2_never_gets_1gbps():
    rec = recommend(S(business_type="CA firm", city="Lucknow", employees=20, sites=1, has_gstin=True,
                      needs=["email_office"]))
    assert "P03" not in ids(rec) and ids(rec)[0] == "P02"
    assert_valid(rec)


def test_tier1_professional_office_with_15_staff_gets_1gbps():
    rec = recommend(S(business_type="Dental clinic", city="Pune", employees=16, sites=1, has_gstin=True,
                      needs=["email_office", "security"]))
    assert ids(rec)[0] == "P03"
    assert_valid(rec)


def test_restaurant_chain_per_outlet_fibre_and_central_management():
    rec = recommend(S(business_type="Restaurant", city="Bengaluru", employees=60, sites=6, has_gstin=True,
                      needs=["uptime_backup", "cctv", "billing_upi", "central_management"]))
    assert rec.segment == "multi"
    lines = {l.product_id: l.qty for l in rec.lines}
    assert lines["P02"] == 6 and lines["P09"] == 6 and lines["P10"] == 6 and lines["P23"] == 12
    assert_valid(rec)


def test_two_site_business_cannot_get_sdwan():
    rec = recommend(S(business_type="Pharmacy", city="Delhi", employees=12, sites=2, has_gstin=True,
                      needs=["central_management"]))
    assert "P10" not in ids(rec)
    assert rec.excluded[0].reason_code == "BELOW_MIN_SITES"


def test_factory_leased_line_and_static_ip_dependency():
    rec = recommend(S(business_type="Textile unit", city="Surat", employees=40, sites=1, has_gstin=True,
                      needs=["machines_iot", "static_ip", "security"]))
    assert rec.segment == "mfg" and ids(rec)[0] == "P05"
    assert ("P11", "DEPENDENCY_MISSING") in [(e.product_id, e.reason_code) for e in rec.excluded]
    assert "P21" in ids(rec)  # firewall for a 40-person unit asking for security
    assert_valid(rec)


def test_factory_without_gstin_falls_back_to_fibre():
    rec = recommend(S(business_type="Furniture workshop", city="Nagpur", employees=35, sites=1, has_gstin=False,
                      needs=["machines_iot"]))
    assert ids(rec)[0] == "P02"
    assert rec.excluded[0].reason_code == "GSTIN_REQUIRED"  # P24 needs GSTIN


def test_no_fibre_uses_airfiber_and_blocks_failover():
    rec = recommend(S(business_type="Salon", city="Indore", employees=4, sites=1, has_gstin=False,
                      fibre_available=False, needs=["guest_wifi", "uptime_backup"]))
    assert ids(rec)[:2] == ["P04", "P22"]
    assert ("P09", "DEPENDENCY_MISSING") in [(e.product_id, e.reason_code) for e in rec.excluded]


def test_only_internet_gets_base_plus_suggested_addons():
    rec = recommend(S(business_type="Boutique", city="Mumbai", employees=2, sites=1, has_gstin=True,
                      needs=["internet"]))
    assert ids(rec) == ["P01"]
    assert rec.addons and all(a.list_monthly_inr for a in rec.addons)
    assert len(rec.addons) <= 4


def test_unknown_city_note_and_tier2():
    rec = recommend(S(business_type="Kirana store", city="Shimla", employees=2, sites=1, has_gstin=False,
                      needs=["internet"]))
    assert rec.profile.city_tier == 2 and rec.notes


def test_hindi_reasons():
    rec = recommend(S(business_type="Salon", city="Jaipur", employees=3, sites=1, has_gstin=False,
                      needs=["billing_upi"]), lang="hi")
    assert "बिलिंग" in rec.lines[1].why


def test_segment_inference():
    assert infer_segment("Kirana store", 4) == "multi"       # 3+ outlets
    assert infer_segment("Restaurant chain", 1) == "micro"   # a 'chain' with one outlet
    assert infer_segment("Textile unit", 5) == "mfg"
    assert infer_segment("CA firm", 1) == "prof"
    assert infer_segment("Something new", 1, hint="prof") == "prof"
