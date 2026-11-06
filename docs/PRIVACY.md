# apnaSaathi: data privacy and security note

One page on the privacy and security choices in the design. Written against the Digital Personal Data
Protection Act, 2023 and the DPDP Rules, 2025 (notified 14 Nov 2025, with up to 18 months for most
obligations). All data in the prototype is synthetic; registry lookups, payments and installation
events are simulated.

## 1. Collect only what each step needs (data minimisation)

| Step | What we ask for | What we do not ask for |
|---|---|---|
| Advisor and quote | Business type, city, people, locations, GST yes/no, needs | Name, phone, any ID or document |
| Order | Name, mobile number, consent to be contacted about this order | Documents, payment details |
| Smart KYC | GSTIN (Udyam optional), 4 photos: GST certificate, Udyam certificate, address proof, signatory ID | Aadhaar number, bank details, extra IDs |

No document is requested before the owner has seen and accepted a price.

## 2. Consent and purpose limitation

- A versioned notice (`kyc-notice-2026-11-v1`) is shown before any document is collected, in Hindi or English.
- Consent is taken **separately for each purpose**: "verify my business" and "store my documents until
  installation". Both are recorded with the notice version and time in the audit log.
- Contact consent at checkout covers this order only. The mobile number is not used for marketing.
- The owner can **delete their documents at any time** from the KYC screen; this is logged.

## 3. Where personal data goes

- **Documents never leave Accel's servers.** OCR (Tesseract) and photo checks (OpenCV) run on our own
  server. No document image or ID number is sent to any AI service.
- **The LLM sees de-identified text only.** Before a message reaches Google Gemini, names, phone
  numbers, GSTIN, Udyam, PAN, email and pincode are replaced with placeholders. Gemini only returns
  structured fields; it never sets a price or makes a KYC decision. If Gemini is unavailable, a
  rule-based layer and a tap-through form take over.
- **WhatsApp:** the sender's phone number is never stored; sessions are keyed by a salted SHA-256 hash.

## 4. Protection

- Document photos are **encrypted at rest** (Fernet / AES-128 + HMAC). The key lives outside the code
  (`.kyc_key` or `KYC_ENCRYPTION_KEY`) and is never committed. Production: object storage with a
  cloud KMS, India region.
- GSTIN, Udyam and names are **masked** in the UI, logs and back office (e.g. `37I••••••••L1ZS`).
- **Every document view and every KYC decision is audited** (who, when, which case). Back-office access
  needs a token; a reviewer must write a note to approve, ask for a fix, or reject.
- Web hardening: Content-Security-Policy, no framing, no MIME sniffing, no-referrer, no caching of API
  responses, 8 MB request and photo cap, per-IP rate limits on chat, KYC, quote and webhook calls.
- Secrets (`.env`, API keys, encryption key, uploads) are excluded from the repository.

## 5. Retention

- Raw document images are deleted **30 days after the KYC case closes** (configurable,
  `KYC_RETENTION_DAYS`), by a daily purge job, or immediately if the owner withdraws consent.
- What remains after that: the outcome, masked identifiers and the audit trail, which the operator
  needs as proof of KYC.

## 6. Accuracy and fairness

- Every rule and KYC check gives a plain reason in Hindi or English, so the owner can fix the problem
  instead of being silently rejected. Unclear cases go to a person (manual review), not to auto-reject.
- Prices are the same for everyone (published list price minus published savings). The lead score is
  used only to decide whom to call first, never to change a price or approve KYC.

## 7. Next steps for production

- **DigiLocker** to fetch verified documents with consent (fewer photos, fewer OCR errors) and
  **Aadhaar e-sign** for the order. Store only masked Aadhaar, as UIDAI requires.
- **Per-SIM-user KYC** for business mobile connections, as DoT requires for each SIM user.
- Real GSTN and Udyam APIs instead of the mock registry; UPI autopay through a payment gateway.
- A named Data Protection Officer contact, a grievance and correction flow for owners, breach
  notification to the Data Protection Board and affected owners as the DPDP Rules require, and
  periodic access reviews of the back office.
