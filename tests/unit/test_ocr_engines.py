"""
ai/ocr/{quality,tesseract_engine,vlm_engine}.py (L4) — the individual
engines router.py picks between.
"""

from ai.ocr.quality import is_high_quality
from ai.ocr.tesseract_engine import TESSERACT_6, TESSERACT_11, run_psm6, run_psm11_with_morphology
from ai.ocr.vlm_engine import VLM, transcribe
from ai.preprocessing import to_gray
from ai.providers.mock import MockVLMProvider
from tests.unit.cv_fixtures import blank_page, crop_to_content, put_text


def _clean_gray():
    img = blank_page()
    box = put_text(img, "Define BCNF and explain the difference from 3NF", 40, 100)
    return to_gray(crop_to_content(img, box))


def test_is_high_quality_true_for_a_clean_crop():
    assert is_high_quality(_clean_gray()) is True


def test_run_psm6_transcribes_clean_text_with_high_confidence():
    result = run_psm6(_clean_gray())
    assert result.engine == TESSERACT_6
    assert "BCNF" in result.text
    assert result.confidence > 0.7


def test_run_psm11_with_morphology_returns_the_right_engine_label():
    result = run_psm11_with_morphology(_clean_gray())
    assert result.engine == TESSERACT_11
    assert isinstance(result.confidence, float)


def test_vlm_transcribe_calls_the_provider_exactly_once():
    vlm = MockVLMProvider(response="A relation is in BCNF if every determinant is a superkey.")
    result = transcribe(_clean_gray(), vlm)
    assert vlm.call_count == 1
    assert result.engine == VLM
    assert result.confidence == 1.0
    assert result.text == "A relation is in BCNF if every determinant is a superkey."
