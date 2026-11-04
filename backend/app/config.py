"""Central settings. Values can be overridden with environment variables (see .env.example)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("APNASAATHI_DATA_DIR", BACKEND_DIR / "data"))
CONFIG_DIR = BACKEND_DIR / "config"
DB_PATH = Path(os.getenv("APNASAATHI_DB_PATH", BACKEND_DIR / "apnasaathi.db"))

CATALOGUE_CSV = DATA_DIR / "product_catalogue.csv"
LEADS_CSV = DATA_DIR / "smb_leads.csv"
GSTIN_REGISTRY_CSV = DATA_DIR / "mock_gstin_registry.csv"
UDYAM_REGISTRY_CSV = DATA_DIR / "mock_udyam_registry.csv"
KYC_DOCS_DIR = DATA_DIR / "kyc_documents"

PRICING_CONFIG = CONFIG_DIR / "pricing.yaml"

# The dataset README says to use 2026-07-15 as "today" for date-based checks.
TODAY = date.fromisoformat(os.getenv("APNASAATHI_TODAY", "2026-07-15"))

# Expected row counts from the dataset README; checked when importing.
EXPECTED_ROWS = {
    "catalogue": 25,
    "leads": 5000,
    "gst_registry": 3534,
    "udyam_registry": 2723,
}

SUPPORTED_LANGUAGES = ("en", "hi")
