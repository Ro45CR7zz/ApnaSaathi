# apnaSaathi

Digital-first acquisition and onboarding for small businesses buying from **Accel Business**
(fictional operator, Project Udyam Digital, YTL Hackathon 2026 Track A).

One engine (Advisor → Quote → Smart KYC → Tracker) behind three front doors: phone web app
(chat + voice, English/Hindi), WhatsApp-style channel, and a partner/field console.

> All data is synthetic. GSTIN/Udyam lookups are **MOCK** lookups against the supplied CSVs,
> not government systems. See `docs/DESIGN.md` for the full design and assumptions.

## Status

| Phase | Scope | State |
|---|---|---|
| 4 | Data import, rules engine, pricing, GSTIN/Udyam checks, mock registry, API + tests | Done |
| 5 | Advisor (Gemini + fallback form) + recommender | Planned |
| 6 | Quote and checkout | Planned |
| 7 | Smart KYC (OCR, quality gate, checks) | Planned |
| 8 | Tracker, back office, propensity | Planned |
| 9 | Voice, WhatsApp-style channel, hardening | Planned |

## Run the backend (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.db.import_data      # loads the CSVs into SQLite and checks row counts
python -m pytest                  # run all tests
uvicorn app.main:app --reload     # then open http://localhost:8000/docs
```

macOS/Linux: use `source .venv/bin/activate` instead of the Activate.ps1 line.

## What Phase 4 provides

- **Rules engine** (`app/rules`): city tier, minimum employees/sites, GSTIN required and Active,
  bundle dependencies; every failure has a reason code with English and Hindi messages.
- **Pricing engine** (`app/pricing`, `config/pricing.yaml`): midpoint list price, "earned savings"
  toward the catalogue minimum (commitment / 3+ products / self-serve + autopay), setup fees,
  contract term, GST line. Weights are labelled assumptions.
- **GSTIN tools** (`app/registry/gstin.py`): format, checksum, and a safe 0/O, 1/I correction that is
  only *suggested* when exactly one checksum-valid candidate exists.
- **Mock registry** (`app/registry/store.py`) and **masking** helpers (`app/common/masking.py`).

## Tests

- Checksum valid for all 3,534 registry GSTINs.
- K02/K08 OCR confusions are suggested; K06's real digit mismatch is not "corrected".
- Replaying the 368 activated deals flags exactly the 68 non-compliant ones (48 rule breaks + 22
  inactive GSTINs, overlapping).
- Pricing never goes below the catalogue minimum; totals and GST add up.
