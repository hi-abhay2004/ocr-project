"""
L4 — Tesseract OCR, both routing paths.

`run_psm6()` is the clean-scan path: PSM 6 assumes a single uniform block
of text, which is right when ai.ocr.quality.is_high_quality() says the
image doesn't need help first. `run_psm11_with_morphology()` is the
low-quality path: a morphological closing reconnects broken/thin strokes
before OCR, and PSM 11 ("sparse text, no particular order") copes better
than PSM 6 with a noisier, less uniform result.

Both return the SAME OCRResult shape so ai.ocr.router can pick between
them (and escalate to the VLM) without caring which one ran.
"""

from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract
from pytesseract import Output

from ai.types import BBox, Word

TESSERACT_6 = "TESSERACT_6"
TESSERACT_11 = "TESSERACT_11"


@dataclass
class OCRResult:
    text: str
    confidence: float  # 0-1, Tesseract's own mean word confidence
    engine: str


def _to_tesseract_input(gray: np.ndarray) -> np.ndarray:
    """Tesseract expects dark ink on a light background. Callers here pass
    a plain (non-inverted) grayscale crop — NOT the ink=255 binary
    convention the rest of ai/ uses after L1 — since OCR engines read the
    original scan directly, not a thresholded mask."""
    return gray


def _run(gray: np.ndarray, *, psm: int, engine: str) -> OCRResult:
    config = f"--psm {psm}"
    data = pytesseract.image_to_data(
        _to_tesseract_input(gray), config=config, output_type=Output.DICT
    )
    words = []
    confidences = []
    for text, conf in zip(data["text"], data["conf"], strict=True):
        text = text.strip()
        conf = float(conf)
        if text and conf >= 0:
            words.append(text)
            confidences.append(conf)

    mean_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
    return OCRResult(text=" ".join(words), confidence=round(mean_confidence, 4), engine=engine)


def run_psm6(gray: np.ndarray) -> OCRResult:
    return _run(gray, psm=6, engine=TESSERACT_6)


def run_psm11_with_morphology(gray: np.ndarray) -> OCRResult:
    # A small closing (dilate then erode) reconnects strokes broken by
    # noise/low contrast without fattening characters enough to merge
    # adjacent ones — this is what the "aggressive" path adds over PSM 11
    # alone.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    return _run(closed, psm=11, engine=TESSERACT_11)


def extract_words(gray: np.ndarray, *, psm: int = 6) -> list[Word]:
    """Word-level bboxes, in crop-pixel coordinates — what ai.reconstruct
    (L5) needs to drop struck-out words and place margin insertions, which
    OCRResult's plain joined text can't support."""
    data = pytesseract.image_to_data(
        _to_tesseract_input(gray), config=f"--psm {psm}", output_type=Output.DICT
    )
    words = []
    for text, conf, x, y, w, h in zip(
        data["text"],
        data["conf"],
        data["left"],
        data["top"],
        data["width"],
        data["height"],
        strict=True,
    ):
        text = text.strip()
        if text and float(conf) >= 0:
            words.append(Word(text=text, bbox=BBox(x=float(x), y=float(y), w=float(w), h=float(h))))
    return words
