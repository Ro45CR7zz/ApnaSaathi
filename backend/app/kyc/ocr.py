"""OCR with Tesseract, on our own server (documents never go to an external AI service)."""
from __future__ import annotations

import os
import shutil

import numpy as np

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None

_cmd = os.getenv("TESSERACT_CMD")
if pytesseract is not None:
    if _cmd:
        pytesseract.pytesseract.tesseract_cmd = _cmd
    elif os.name == "nt" and not shutil.which("tesseract"):
        default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(default):
            pytesseract.pytesseract.tesseract_cmd = default


class OcrUnavailable(RuntimeError):
    pass


def available() -> bool:
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def read_text(gray: np.ndarray) -> str:
    if not available():
        raise OcrUnavailable("Tesseract OCR is not installed on this server.")
    return pytesseract.image_to_string(gray, lang="eng", config="--psm 4")
