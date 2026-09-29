"""
L8 — composite confidence.

Three independent signals, weighted (ai.config.CONFIDENCE_WEIGHT_*):
OCR quality (was the source text even read reliably), triple-pass
agreement (how sure was the LLM about ITS OWN verdicts), and retrieval
corroboration (did similarity search back up what the LLM said,
independent of whether the LLM agreed with itself). One 0-1 score,
banded GREEN/ORANGE/RED (ai.config.CONFIDENCE_BAND_GREEN/ORANGE) — what
decides whether a sheet can auto-publish, publish with a note, or needs a
forced review.
"""

from ai.config import (
    CONFIDENCE_BAND_GREEN,
    CONFIDENCE_BAND_ORANGE,
    CONFIDENCE_WEIGHT_OCR_QUALITY,
    CONFIDENCE_WEIGHT_PASS_AGREEMENT,
    CONFIDENCE_WEIGHT_RETRIEVAL_VERIFY,
)

GREEN = "GREEN"
ORANGE = "ORANGE"
RED = "RED"


def retrieval_agreement(llm_verdicts: list[str], similarity_verdicts: list[str]) -> float:
    """Fraction of concepts where the LLM's coverage verdict
    (ai.coverage) and pure-similarity banding (ai.scoring.similarity_only_band)
    land on the SAME status — independent corroboration, not the LLM
    agreeing with its own three passes (that's pass agreement)."""
    if not llm_verdicts:
        return 0.0
    agreeing = sum(1 for a, b in zip(llm_verdicts, similarity_verdicts, strict=True) if a == b)
    return round(agreeing / len(llm_verdicts), 4)


def composite_confidence(
    ocr_quality: float, pass_agreement: float, retrieval_verify: float
) -> float:
    score = (
        CONFIDENCE_WEIGHT_OCR_QUALITY * ocr_quality
        + CONFIDENCE_WEIGHT_PASS_AGREEMENT * pass_agreement
        + CONFIDENCE_WEIGHT_RETRIEVAL_VERIFY * retrieval_verify
    )
    return round(min(max(score, 0.0), 1.0), 4)


def band_for(confidence: float) -> str:
    if confidence >= CONFIDENCE_BAND_GREEN:
        return GREEN
    if confidence >= CONFIDENCE_BAND_ORANGE:
        return ORANGE
    return RED
