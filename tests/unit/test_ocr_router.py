"""
ai/ocr/{quality,tesseract_engine,vlm_engine,router}.py (L4) — adaptive OCR
routing.

The happy path (clean scan -> PSM 6 -> confident, zero VLM calls) is
tested against a real rendered fixture. The two escalation branches (low
quality -> morphology+PSM11; low OCR confidence -> VLM) are tested by
injecting the branch condition directly rather than fighting to construct
a synthetic image that lands exactly below a no-reference quality metric's
threshold — that's what ai.ocr.router actually branches on, not "how
noisy does an image have to look," and it keeps the test about the
ROUTING decision, not about ai.preprocessing.quality_score's precision.
"""

from ai.ocr import router
from ai.ocr.tesseract_engine import TESSERACT_6, TESSERACT_11, OCRResult
from ai.ocr.vlm_engine import VLM
from ai.preprocessing import to_gray
from ai.providers.mock import MockVLMProvider
from tests.unit.cv_fixtures import blank_page, crop_to_content, put_text


def _clean_gray():
    img = blank_page()
    box = put_text(img, "Define BCNF and explain how it differs from third normal form", 40, 100)
    return to_gray(crop_to_content(img, box))


def test_a_clean_scan_uses_psm6_and_never_calls_the_vlm():
    vlm = MockVLMProvider()
    result = router.run(_clean_gray(), vlm)
    assert result.engine == TESSERACT_6
    assert result.confidence > 0.7
    assert vlm.call_count == 0


def test_low_quality_routes_to_morphology_plus_psm11(monkeypatch):
    monkeypatch.setattr(router, "is_high_quality", lambda gray: False)
    monkeypatch.setattr(
        router,
        "run_psm11_with_morphology",
        lambda gray: OCRResult(text="stub", confidence=0.9, engine=TESSERACT_11),
    )
    vlm = MockVLMProvider()
    result = router.run(_clean_gray(), vlm)
    assert result.engine == TESSERACT_11
    assert vlm.call_count == 0


def test_low_confidence_escalates_to_the_vlm_exactly_once(monkeypatch):
    monkeypatch.setattr(router, "is_high_quality", lambda gray: True)
    monkeypatch.setattr(
        router,
        "run_psm6",
        lambda gray: OCRResult(text="garbled", confidence=0.1, engine=TESSERACT_6),
    )
    vlm = MockVLMProvider(response="the real handwritten text")
    result = router.run(_clean_gray(), vlm)
    assert result.engine == VLM
    assert result.text == "the real handwritten text"
    assert vlm.call_count == 1


def test_a_confidence_exactly_at_the_threshold_does_not_escalate(monkeypatch):
    from ai.config import OCR_CONFIDENCE_ESCALATION_THRESHOLD

    monkeypatch.setattr(router, "is_high_quality", lambda gray: True)
    monkeypatch.setattr(
        router,
        "run_psm6",
        lambda gray: OCRResult(
            text="borderline", confidence=OCR_CONFIDENCE_ESCALATION_THRESHOLD, engine=TESSERACT_6
        ),
    )
    vlm = MockVLMProvider()
    result = router.run(_clean_gray(), vlm)
    assert result.engine == TESSERACT_6
    assert vlm.call_count == 0
