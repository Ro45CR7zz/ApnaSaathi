"""Image intake: safe decoding, quality gate (blur, skew) and deskew. Runs on our server only."""
from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 25_000_000
# Calibrated on the supplied samples: the blurred K04 certificate scores ~1, sharp scans score 900+.
BLUR_MIN = 100.0
SKEW_CORRECT_MIN = 1.0   # degrees: below this, leave the image as is
SKEW_MAX = 20.0          # degrees: beyond this, ask for a retake


class BadUpload(ValueError):
    pass


@dataclass
class Quality:
    blur_score: float
    skew_degrees: float
    sharp: bool
    deskewed: bool
    too_tilted: bool


def decode(data: bytes) -> np.ndarray:
    """Decode an uploaded image safely and return a grayscale array.

    Only real PNG/JPEG/WebP images are accepted (checked by decoding, not by file name).
    Images are re-encoded through Pillow, which drops any embedded metadata or payloads.
    """
    if not data:
        raise BadUpload("The file is empty.")
    if len(data) > MAX_BYTES:
        raise BadUpload("The file is larger than 10 MB.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ("PNG", "JPEG", "WEBP"):
                raise BadUpload("Please upload a photo or scan (JPG or PNG).")
            if im.width * im.height > MAX_PIXELS:
                raise BadUpload("The image is too large.")
            im = im.convert("L")
            return np.array(im)
    except (UnidentifiedImageError, OSError) as e:
        raise BadUpload("This file is not a readable image.") from e


def _skew(gray: np.ndarray) -> float:
    # Only dark pixels (text, frame); the light pink watermark is ignored.
    pts = np.column_stack(np.where(gray < 110))
    if len(pts) < 50:
        return 0.0
    angle = cv2.minAreaRect(pts[:, ::-1].astype(np.float32))[-1] % 90
    return angle - 90 if angle > 45 else angle


def rotate(gray: np.ndarray, degrees: float) -> np.ndarray:
    h, w = gray.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def assess(gray: np.ndarray) -> tuple[Quality, np.ndarray]:
    """Return quality metrics and the image to OCR (deskewed when needed)."""
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    skew = float(_skew(gray))
    too_tilted = abs(skew) > SKEW_MAX
    deskewed = SKEW_CORRECT_MIN <= abs(skew) <= SKEW_MAX
    out = rotate(gray, skew) if deskewed else gray
    return Quality(round(blur, 1), round(skew, 2), blur >= BLUR_MIN, deskewed, too_tilted), out
