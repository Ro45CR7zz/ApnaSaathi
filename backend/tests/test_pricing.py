from app.catalogue.models import BundleLine
from app.pricing.engine import PricingOptions, price_bundle

MICRO = [BundleLine(product_id="P01", qty=1), BundleLine(product_id="P07", qty=2)]
MICRO3 = MICRO + [BundleLine(product_id="P19", qty=1)]


def test_list_price_is_midpoint():
    q = price_bundle(MICRO)
    # P01 (999+1199)/2 = 1099 ; P07 (299+399)/2 = 349 x 2
    assert q.list_monthly_inr == 1099 + 698
    assert q.savings_monthly_inr == 0 and q.monthly_subtotal_inr == 1797
    assert q.contract_months == 12
    assert q.one_time_subtotal_inr == 0


def test_commitment_saving_moves_halfway_to_min():
    q = price_bundle(MICRO, PricingOptions(commit_extra_12m=True))
    # P01: 1099 - 0.5*100 = 1049 ; P07: 349 - 0.5*50 = 324 (x2)
    assert q.monthly_subtotal_inr == 1049 + 648
    assert q.contract_months == 24
    assert {s.code for s in q.savings} == {"commit_extra_12m"}


def test_bundle_3plus_saving_applies_only_with_three_products():
    assert price_bundle(MICRO).earned_savings_fraction == 0
    q = price_bundle(MICRO3)
    assert q.earned_savings_fraction == 0.25
    # P19 (599+899)/2 = 749, gap 150 -> 37.5 -> rounds half up to 38
    p19 = next(l for l in q.lines if l.product_id == "P19")
    assert p19.list_unit_inr == 749 and p19.savings_monthly_inr == 38
    assert q.one_time_subtotal_inr == 2500


def test_all_savings_reach_catalogue_minimum_never_below():
    q = price_bundle(MICRO3, PricingOptions(commit_extra_12m=True, selfserve_autopay=True))
    assert q.earned_savings_fraction == 1.0
    for line in q.lines:
        assert line.monthly_inr == line.catalogue_min_inr * line.qty


def test_totals_add_up_and_gst():
    q = price_bundle(MICRO3, PricingOptions(selfserve_autopay=True))
    assert q.monthly_subtotal_inr == sum(l.monthly_inr for l in q.lines)
    assert q.savings_monthly_inr == sum(s.amount_inr for s in q.savings)
    assert q.list_monthly_inr - q.savings_monthly_inr == q.monthly_subtotal_inr
    assert q.monthly_gst_inr == round(q.monthly_subtotal_inr * 0.18)
    assert q.monthly_total_inr == q.monthly_subtotal_inr + q.monthly_gst_inr
    assert q.one_time_total_inr == 2500 + 450


def test_term_is_longest_minimum_contract():
    q = price_bundle([BundleLine(product_id="P05", qty=1), BundleLine(product_id="P06", qty=1)])
    assert q.contract_months == 24
    assert q.one_time_subtotal_inr == 25000


def test_hindi_labels():
    q = price_bundle(MICRO3, lang="hi")
    assert q.savings[0].label == "3 या अधिक प्रोडक्ट का बंडल"
