import csv

import pytest

from app import config
from app.common.masking import mask_gstin, mask_name, mask_udyam
from app.registry import store
from app.registry.gstin import check_gstin, checksum_char, is_valid
from app.registry.udyam import is_valid_format, normalise


def test_checksum_valid_for_every_registry_gstin():
    with open(config.GSTIN_REGISTRY_CSV, newline="", encoding="utf-8") as f:
        gstins = [r["gstin"] for r in csv.DictReader(f)]
    assert len(gstins) == 3534
    assert all(is_valid(g) for g in gstins)


def test_checksum_rejects_single_character_change():
    g = "37NBLXS1145E1ZU"  # K12, clean sample
    assert is_valid(g)
    wrong = g[:14] + ("A" if g[14] != "A" else "B")
    assert not is_valid(wrong)
    assert checksum_char(g[:14]) == "U"


@pytest.mark.parametrize("read,expected", [
    ("19E0GXH4115Y1ZL", "19EOGXH4115Y1ZL"),  # K02: zero read where the PAN needs a letter O
    ("24X0RXG9365M1Z3", "24XORXG9365M1Z3"),  # K08: same confusion
])
def test_confusable_correction_is_suggested_not_applied(read, expected):
    r = check_gstin(read)
    assert r.status == "corrected_suggestion"
    assert r.suggestion == expected
    assert r.normalised == read  # original value is preserved; user must confirm
    assert store.lookup_gstin(expected) is not None


def test_k06_real_digit_mismatch_is_not_corrected():
    # Certificate shows ...S8189...; registry has ...S5189... . This must NOT become a match.
    r = check_gstin("08YKZXS8189L1Z0")
    assert r.status == "invalid"
    assert r.suggestion is None


def test_valid_gstin_passes_unchanged():
    r = check_gstin(" 37ihkxv5167l1zs ")
    assert r.status == "valid" and r.normalised == "37IHKXV5167L1ZS"


@pytest.mark.parametrize("bad", ["", "37IHKXV5167L1Z", "37IHKXV5167L1ZSX", "99IHKXV5167L1ZS", "37IHK@V5167L1ZS"])
def test_bad_format(bad):
    assert check_gstin(bad).status == "invalid"


def test_registry_status_values():
    assert store.gstin_status("37IHKXV5167L1ZS") == "Cancelled"   # K01
    assert store.gstin_status("37NBLXS1145E1ZU") == "Active"      # K12
    assert store.gstin_status(None) == "None"
    assert store.gstin_status("37NBLXS1145E1ZV") == "NotFound"


def test_udyam_format_and_ocr_spaces():
    assert is_valid_format("UDYAM-MH- 00-6131836")  # K04 OCR output with a stray space
    assert normalise("udyam-mh- 00-6131836") == "UDYAM-MH-00-6131836"
    assert not is_valid_format("UDYAM-MH-00-613183")
    assert store.lookup_udyam("UDYAM-WB-00-5053330")["enterprise_name"] == "Harmony Dental Care"


def test_masking():
    assert mask_gstin("37IHKXV5167L1ZS") == "37I••••••••L1ZS"
    assert mask_udyam("UDYAM-AP-00-9751562") == "UDYAM-AP-00-•••1562"
    assert mask_name("Neha Kaur") == "N. K."
