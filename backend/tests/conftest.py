import os

# Tests never call the real Gemini API: no quota use, no network, same result every run.
# Set before app modules load, so .env can't override it.
os.environ["GEMINI_API_KEY"] = ""
