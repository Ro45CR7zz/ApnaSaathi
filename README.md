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
| 5 | Advisor (Gemini + rule-based fallback + form) + recommender | Done |
| 6 | Quote and checkout + phone web app (welcome, Advisor, quote, order) | Done |
| 7 | Smart KYC: consent, GSTIN lookup, photo quality, OCR, checks, encrypted storage; 12 samples pass | Done |
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

## Run the web app (Phase 6)

One-time setup, from the `frontend` folder:

```powershell
cd frontend
npm install
npm run build        # builds the app into frontend/dist
```

Then start the backend as usual (`uvicorn app.main:app --reload` from `backend`) and open
**http://localhost:8000**. The backend serves the built app and the API from one address.

While changing the UI, run `npm run dev` in `frontend` and open http://localhost:5173 instead
(it forwards `/api` calls to the backend on port 8000).

Voice input works in Chrome/Edge (desktop and Android). Typing and tapping always work.

## Smart KYC needs Tesseract OCR (Phase 7)

Documents are read on your own machine with Tesseract (no document is sent to any AI service).

- **Windows:** install Tesseract from the UB Mannheim build (github.com/UB-Mannheim/tesseract/wiki).
  The default install path `C:\Program Files\Tesseract-OCR\tesseract.exe` is found automatically;
  otherwise set `TESSERACT_CMD` in `.env` to the full path of `tesseract.exe`.
- Check: `GET http://localhost:8000/api/kyc/status` should show `"ocr_available": true`.
- Without Tesseract the app still runs, but document checks return "OCR not available" and the
  12-sample KYC tests are skipped.

Document photos are encrypted at rest with a key in `backend/.kyc_key` (created on first use, never
committed) or `KYC_ENCRYPTION_KEY` in `.env`. Photos live in `backend/uploads/` (also not committed).

Demo: on the KYC screen, "Demo: try a sample applicant" runs any of the 12 supplied specimen
applicants (K01-K12) through the same pipeline.

## Try the Advisor in the terminal (Phase 5)

```powershell
python -m app.advisor.cli          # English (uses Gemini if GEMINI_API_KEY is set in .env)
python -m app.advisor.cli --hi     # Hindi
python -m app.advisor.cli --rules  # force rule-based understanding (no Gemini)
```

The Gemini model is picked automatically from the models your key can use (newest "flash" text model).
To force one, set `GEMINI_MODEL` in `.env`. Only de-identified text is sent (names, phones, GSTIN,
Udyam, PAN, email, pincode are replaced with placeholders first).

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
