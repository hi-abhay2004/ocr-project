"""
L4 — OCR routing decision.

Wraps ai.preprocessing.quality_score() with the specific routing call L4
needs: is this block's image clean enough to trust plain Tesseract at
PSM 6, or does it need the more aggressive morphology + PSM 11 path first?
Kept as its own module (rather than every L4 caller reaching into L1
directly) so the threshold this decision is made against lives with the
OCR layer that uses it, next to ai.config.OCR_QUALITY_ROUTING_THRESHOLD.
"""

from ai.config import OCR_QUALITY_ROUTING_THRESHOLD
from ai.preprocessing import quality_score


def is_high_quality(gray) -> bool:
    return quality_score(gray) >= OCR_QUALITY_ROUTING_THRESHOLD
