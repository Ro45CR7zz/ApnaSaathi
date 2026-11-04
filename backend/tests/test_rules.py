from app.catalogue.loader import city_tier, load_catalogue
from app.catalogue.models import BundleLine, BusinessProfile
from app.rules.engine import check_product, validate_bundle

CAT = load_catalogue()


def prof(**kw) -> BusinessProfile:
    base = dict(segment="micro", city_tier=1, employees=3, sites=1, gstin_status="Active")
    base.update(kw)
    return BusinessProfile(**base)


def codes(result) -> set[str]:
    return {i.code for i in result.issues}


def test_catalogue_loaded():
    assert len(CAT) == 25
    assert CAT["P11"].requires_one_of == ["P01", "P02", "P03"]
    assert CAT["P03"].available_city_tiers == [1]


def test_tier_rule():
    assert codes(check_product(CAT["P03"], prof(city_tier=2, employees=20))) == {"TIER_UNAVAILABLE"}
    assert check_product(CAT["P03"], prof(city_tier=1, employees=20)).eligible


def test_min_employees_and_sites():
    assert "BELOW_MIN_EMPLOYEES" in codes(check_product(CAT["P03"], prof(employees=4)))
    assert check_product(CAT["P03"], prof(employees=5)).eligible  # threshold is inclusive
    assert "BELOW_MIN_EMPLOYEES" in codes(check_product(CAT["P06"], prof(employees=24)))
    r = check_product(CAT["P10"], prof(employees=20, sites=2))
    assert codes(r) == {"BELOW_MIN_SITES"}


def test_gstin_rules():
    assert codes(check_product(CAT["P15"], prof(gstin_status="None"))) == {"GSTIN_REQUIRED"}
    assert codes(check_product(CAT["P15"], prof(gstin_status="Cancelled"))) == {"GSTIN_INACTIVE"}
    assert codes(check_product(CAT["P15"], prof(gstin_status="Suspended"))) == {"GSTIN_INACTIVE"}
    # A business without GSTIN is not rejected from everything: non-GST products stay eligible.
    no_gst = prof(gstin_status="None")
    assert check_product(CAT["P01"], no_gst).eligible
    assert check_product(CAT["P07"], no_gst).eligible


def test_hindi_message():
    r = check_product(CAT["P15"], prof(gstin_status="None"), lang="hi")
    assert "GSTIN" in r.issues[0].message and "ज़रूरी" in r.issues[0].message


def test_static_ip_with_leased_line_only_is_invalid():
    p = prof(segment="mfg", employees=30, sites=1)
    v = validate_bundle(p, [BundleLine(product_id="P05", qty=1), BundleLine(product_id="P11", qty=1)])
    assert not v.valid and codes(v) == {"DEPENDENCY_MISSING"}


def test_failover_with_airfiber_only_is_invalid():
    v = validate_bundle(prof(), [BundleLine(product_id="P04", qty=1), BundleLine(product_id="P09", qty=1)])
    assert "DEPENDENCY_MISSING" in codes(v)


def test_auto_fix_adds_cheapest_eligible_dependency():
    v = validate_bundle(prof(sites=1), [BundleLine(product_id="P22", qty=1)], auto_fix=True)
    assert v.valid
    assert [l.product_id for l in v.lines] == ["P22", "P04"]  # P04 AirFiber is the cheapest allowed base
    assert v.auto_added and v.auto_added[0].code == "DEPENDENCY_AUTO_ADDED"


def test_auto_fix_respects_eligibility():
    # P11 needs P01/P02/P03; in tier 2 P03 is excluded, so P01 is chosen.
    v = validate_bundle(prof(city_tier=2), [BundleLine(product_id="P11", qty=1)], auto_fix=True)
    assert v.valid and "P01" in [l.product_id for l in v.lines]


def test_bundle_issues_unknown_duplicate_and_qty():
    v = validate_bundle(prof(sites=1), [BundleLine(product_id="P99", qty=1),
                                        BundleLine(product_id="P01", qty=2),
                                        BundleLine(product_id="P01", qty=1)])
    assert codes(v) == {"UNKNOWN_PRODUCT", "QTY_EXCEEDS_SITES", "DUPLICATE_PRODUCT"}


def test_valid_micro_bundle():
    v = validate_bundle(prof(gstin_status="None"), [BundleLine(product_id="P01", qty=1),
                                                    BundleLine(product_id="P07", qty=2),
                                                    BundleLine(product_id="P19", qty=1)])
    assert v.valid and not v.issues


def test_city_tier_lookup():
    assert city_tier("Jaipur") == (2, True)
    assert city_tier("mumbai") == (1, True)
    assert city_tier("Shimla") == (2, False)  # unknown -> conservative tier 2 (A13)
