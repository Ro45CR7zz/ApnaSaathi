# apnaSaathi

Digital-first acquisition and onboarding for small businesses buying from **Accel Business**
(fictional operator, Project Udyam Digital, YTL Hackathon 2026 Track A).

One engine (Advisor → Quote → Smart KYC → Tracker) behind three front doors: phone web app
(chat + voice, English/Hindi), WhatsApp-style channel, and a partner/field console.

> All data is synthetic. GSTIN/Udyam lookups are **MOCK** lookups against the supplied CSVs,
> not government systems. See `docs/DESIGN.md` for the full design and assumptions.

![Architecture](docs/architecture.png)

## Submission material

| Item | Where |
|---|---|
| Demo video (3 min) | _add link_ |
| Architecture diagram (components and data flows) | [`docs/architecture.png`](docs/architecture.png) |
| Data privacy and security note (1 page) | [`docs/PRIVACY.md`](docs/PRIVACY.md) |
| Design spec and assumptions | [`docs/DESIGN.md`](docs/DESIGN.md) |
| Business case (7 slides) | submitted on the hackathon portal (PDF + PPTX) |

## Quick start (about 5 minutes)

1. Python 3.10+, Node 20+, and [Tesseract OCR](#smart-kyc-needs-tesseract-ocr-phase-7) for document reading.
2. `cp .env.example .env` and add a Gemini API key (optional: without it the Advisor uses its rule-based mode).
3. Backend: see [Run the backend](#run-the-backend-windows-powershell). Frontend: `cd frontend && npm install && npm run build`.
4. Open http://localhost:8000. Back office: http://localhost:8000/#/ops (token `accel-demo-ops`).
   WhatsApp simulator: http://localhost:8000/#/whatsapp.

## Status

| Phase | Scope | State |
|---|---|---|
| 4 | Data import, rules engine, pricing, GSTIN/Udyam checks, mock registry, API + tests | Done |
| 5 | Advisor (Gemini + rule-based fallback + form) + recommender | Done |
| 6 | Quote and checkout + phone web app (welcome, Advisor, quote, order) | Done |
| 7 | Smart KYC: consent, GSTIN lookup, photo quality, OCR, checks, encrypted storage; 12 samples pass | Done |
| 8 | Tracker (timeline, pending actions, simulated install events, updates) + back office (lead scores, KYC review, call requests, orders, funnel) | Done |
| 9 | Messaging channel (WhatsApp-ready webhook + simulator), quote links, hardening, end-to-end test | Done |
| UI | Redesign: Plus Jakarta Sans + Inter (Noto Sans Devanagari for Hindi), desktop split view, new KYC and tracker layouts | Done |

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

## Tracker and back office (Phase 8)

- Customer tracker: after placing an order, "Track my order" (or open `http://localhost:8000/#/track/<order id>`).
  Payment and installation events are **simulated** in this prototype.
- Back office: `http://localhost:8000/#/ops`, token `accel-demo-ops` (change with `OPS_TOKEN` in `.env`).
  Tabs: leads to call (ranked by lead score, with next best action and offer suggestion), KYC review
  (approve / ask to fix / reject, every document view audited), call requests, orders (simulate the next
  step, a 3-day delay, fibre not feasible, payment failure) and the funnel.
- Lead score: gradient boosting on profile and source fields only; 5-fold cross-validated AUC about 0.67.
  Calling the top 30% of scored leads finds about 51% of activations (out-of-fold).
- Offer suggestions use labelled assumptions in `backend/config/offers.yaml`.

## Messaging channel and hardening (Phase 9)

- Simulator: open `http://localhost:8000/#/whatsapp`. It talks to the same webhook a real number would use
  (`POST /api/channels/whatsapp`). When the Advisor has a plan, the reply carries the price summary and a link
  `#/q/<quote id>` that opens the quote in the web app to change it and order.
- Real WhatsApp (optional, not needed for the demo): point a Twilio WhatsApp sandbox "When a message comes in"
  webhook at `https://<public address>/api/channels/whatsapp` and set `PUBLIC_BASE_URL` in `.env` so quote links
  point to that address. Phone numbers are never stored, only a salted hash (`CHANNEL_HASH_SALT`).
- Hardening: security headers (CSP, no framing, no sniffing), no caching of API responses, an 8 MB request
  and photo cap, and per-IP rate limits on chat, KYC, quote and webhook calls (turn off with
  `APNASAATHI_RATE_LIMIT=0`). In production these sit in the API gateway.
- `tests/test_channel_e2e.py` runs one full journey through the API: chat → quote → change → order →
  KYC sample → payment → installation → ACTIVE.

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
