"""Import the supplied CSVs into SQLite and verify row counts against the dataset README.

Run:  python -m app.db.import_data
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from app import config

SOURCES = {
    "catalogue": config.CATALOGUE_CSV,
    "leads": config.LEADS_CSV,
    "gst_registry": config.GSTIN_REGISTRY_CSV,
    "udyam_registry": config.UDYAM_REGISTRY_CSV,
}


def import_all(db_path=config.DB_PATH) -> dict[str, int]:
    counts: dict[str, int] = {}
    with sqlite3.connect(db_path) as con:
        for table, path in SOURCES.items():
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            expected = config.EXPECTED_ROWS[table]
            if len(df) != expected:
                raise ValueError(f"{path.name}: expected {expected} rows, found {len(df)}")
            df.to_sql(table, con, if_exists="replace", index=False)
            counts[table] = len(df)
        con.execute("CREATE INDEX IF NOT EXISTS ix_gst ON gst_registry(gstin)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_udyam ON udyam_registry(udyam_number)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_leads ON leads(lead_id)")
    return counts


def ensure_database() -> None:
    if not config.DB_PATH.exists():
        import_all()


if __name__ == "__main__":
    for table, n in import_all().items():
        print(f"{table:<15} {n:>5} rows  OK")
    print(f"Database: {config.DB_PATH}")
