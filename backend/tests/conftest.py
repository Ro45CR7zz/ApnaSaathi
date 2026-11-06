import os

# Tests never call the real Gemini API: no quota use, no network, same result every run.
# Set before app modules load, so .env can't override it.
os.environ["GEMINI_API_KEY"] = ""
# Rate limits are tested on their own; the rest of the suite makes many quick calls.
os.environ.setdefault("APNASAATHI_RATE_LIMIT", "0")
