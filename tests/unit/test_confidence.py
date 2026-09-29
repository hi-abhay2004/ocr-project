"""
ai/confidence.py (L8) — weighted composite + banding, table-driven over
the boundaries (ai.config.CONFIDENCE_BAND_GREEN=0.80, ORANGE=0.65).
"""

import pytest

from ai.confidence import band_for, composite_confidence, retrieval_agreement


def test_perfect_signals_give_full_confidence():
    assert composite_confidence(1.0, 1.0, 1.0) == 1.0


def test_zero_signals_give_zero_confidence():
    assert composite_confidence(0.0, 0.0, 0.0) == 0.0


def test_weights_sum_to_the_documented_split():
    # 0.35 OCR + 0.40 pass-agreement + 0.25 retrieval-verify.
    only_ocr = composite_confidence(1.0, 0.0, 0.0)
    only_agreement = composite_confidence(0.0, 1.0, 0.0)
    only_retrieval = composite_confidence(0.0, 0.0, 1.0)
    assert only_ocr == pytest.approx(0.35)
    assert only_agreement == pytest.approx(0.40)
    assert only_retrieval == pytest.approx(0.25)
    assert only_ocr + only_agreement + only_retrieval == pytest.approx(1.0)


@pytest.mark.parametrize(
    "confidence,expected_band",
    [
        (1.0, "GREEN"),
        (0.80, "GREEN"),  # boundary: inclusive
        (0.7999, "ORANGE"),
        (0.65, "ORANGE"),  # boundary: inclusive
        (0.6499, "RED"),
        (0.0, "RED"),
    ],
)
def test_band_for(confidence, expected_band):
    assert band_for(confidence) == expected_band


def test_retrieval_agreement_is_the_fraction_matching():
    llm_verdicts = ["COVERED", "COVERED", "MISSING", "PARTIAL"]
    similarity_verdicts = ["COVERED", "MISSING", "MISSING", "MISSING"]
    # matches at index 0 and 2 -> 2/4
    assert retrieval_agreement(llm_verdicts, similarity_verdicts) == 0.5


def test_retrieval_agreement_with_no_concepts_is_zero():
    assert retrieval_agreement([], []) == 0.0


def test_retrieval_agreement_full_match():
    assert retrieval_agreement(["COVERED", "MISSING"], ["COVERED", "MISSING"]) == 1.0
