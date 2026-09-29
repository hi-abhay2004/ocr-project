"""
L4 — adaptive OCR routing.

quality_score() >= ai.config.OCR_QUALITY_ROUTING_THRESHOLD -> plain
Tesseract PSM 6. Below it -> morphology + PSM 11 first. Either way, if the
engine that ran reports confidence below
ai.config.OCR_CONFIDENCE_ESCALATION_THRESHOLD, the VLM transcribes the
block directly instead — Tesseract's own confidence is the signal that
decides this, not quality_score() a second time, since a low-quality image
CAN still OCR confidently (the morphology step exists for exactly that
case) and a high-quality image can still OCR badly (unusual handwriting).
"""

import numpy as np

from ai.config import OCR_CONFIDENCE_ESCALATION_THRESHOLD
from ai.providers.base import VLMProvider

from . import vlm_engine
from .quality import is_high_quality
from .tesseract_engine import OCRResult, run_psm6, run_psm11_with_morphology


def run(gray: np.ndarray, vlm: VLMProvider) -> OCRResult:
    result = run_psm6(gray) if is_high_quality(gray) else run_psm11_with_morphology(gray)

    if result.confidence < OCR_CONFIDENCE_ESCALATION_THRESHOLD:
        return vlm_engine.transcribe(gray, vlm)
    return result
