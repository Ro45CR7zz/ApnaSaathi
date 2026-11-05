"""One uploaded image -> quality + OCR + classification + extracted fields."""
from __future__ import annotations

from app.kyc import extract as ex
from app.kyc.checks import DocResult
from app.kyc.imaging import assess, decode
from app.kyc.ocr import read_text


def process(data: bytes, expected_type: str) -> tuple[DocResult, dict]:
    """Returns the result used by the checks and quality metrics for the audit trail."""
    gray = decode(data)
    q, img = assess(gray)
    metrics = {"blur_score": q.blur_score, "skew_degrees": q.skew_degrees, "deskewed": q.deskewed}
    if not q.sharp or q.too_tilted:
        return DocResult(doc_type=expected_type, sharp=q.sharp, too_tilted=q.too_tilted, readable=False), metrics
    text = read_text(img)
    found = ex.classify(text)
    if found is None:
        return DocResult(doc_type=expected_type, readable=False, deskewed=q.deskewed), metrics
    fields = ex.extract(found, text)
    return DocResult(doc_type=expected_type, found_type=found, deskewed=q.deskewed, fields=fields), metrics
