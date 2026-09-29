"""
ai/reconstruct.py (L5) — drop struck words, splice margin notes in at
their nearest arrow, reading order.

The insertion-logic tests use hand-built Word/Annotation fixtures (not
real OCR/detector output) so the assertions are about reconstruct()'s own
matching/ordering logic, decoupled from OCR or Hough-detector precision.
One end-to-end test then proves the real L3/L3.5/L4 modules' output feeds
into it correctly.
"""

import numpy as np

import ai.reconstruct as reconstruct_module
from ai.annotations import strikethrough
from ai.ocr.tesseract_engine import OCRResult, extract_words
from ai.preprocessing import to_gray
from ai.reconstruct import reconstruct
from ai.types import Annotation, BBox, Word
from tests.unit.cv_fixtures import blank_page, crop_to_content, draw_strike, put_text, to_binary


def _word(text, x, y=10, w=30, h=20):
    return Word(text=text, bbox=BBox(x=x, y=y, w=w, h=h))


def test_reading_order_is_top_to_bottom_left_to_right():
    words = [
        _word("world", x=100, y=50),
        _word("hello", x=10, y=10),
        _word("there", x=10, y=50),
    ]
    text = reconstruct(np.zeros((100, 200), dtype=np.uint8), words, [])
    assert text == "hello there world"


def test_a_struck_word_is_dropped():
    words = [_word("keep", x=10), _word("delete", x=50), _word("this", x=90)]
    strike = Annotation(
        kind="STRIKE", intent="CORRECTION", bbox=BBox(x=48, y=8, w=34, h=4), confidence=0.9
    )
    text = reconstruct(np.zeros((100, 200), dtype=np.uint8), words, [strike])
    assert text == "keep this"


def test_a_margin_note_is_spliced_in_after_its_nearest_arrow(monkeypatch):
    monkeypatch.setattr(
        reconstruct_module, "run_psm6", lambda crop: OCRResult("also X", 1.0, "TESSERACT_6")
    )

    words = [_word("The", x=10), _word("cat", x=50), _word("sat", x=90)]
    arrow = Annotation(
        kind="ARROW", intent="INSERTION", bbox=BBox(x=120, y=10, w=150, h=10), confidence=0.9
    )
    margin = Annotation(
        kind="MARGIN", intent="INSERTION", bbox=BBox(x=300, y=10, w=50, h=20), confidence=0.9
    )

    text = reconstruct(np.zeros((100, 400), dtype=np.uint8), words, [arrow, margin])
    assert text == "The cat sat [also X]"


def test_a_margin_note_with_no_nearby_arrow_is_prepended(monkeypatch):
    monkeypatch.setattr(reconstruct_module, "_ocr_margin_note", lambda image, margin: "stray note")

    words = [_word("hello", x=10)]
    # Far outside MARGIN_ARROW_MAX_DISTANCE from any arrow — in fact there's
    # no arrow at all here.
    margin = Annotation(
        kind="MARGIN", intent="INSERTION", bbox=BBox(x=5000, y=5000, w=50, h=20), confidence=0.9
    )

    text = reconstruct(np.zeros((100, 6000), dtype=np.uint8), words, [margin])
    assert text == "stray note hello"


def test_margin_note_words_in_the_ocr_pass_are_not_double_counted():
    # `words` includes tokens that live INSIDE the margin's own bbox (as a
    # real OCR pass over the whole block would produce) — they must be
    # excluded from the body, not read once in place AND once spliced in.
    words = [_word("hello", x=10), _word("stray", x=300)]
    margin = Annotation(
        kind="MARGIN", intent="INSERTION", bbox=BBox(x=290, y=5, w=40, h=20), confidence=0.9
    )
    text = reconstruct(np.zeros((100, 400), dtype=np.uint8), words, [margin])
    assert "stray" not in text.split("hello")[0].split("[")[0]  # not read as a body word
    assert text.count("stray") <= 1


def test_end_to_end_with_real_ocr_and_a_real_strike_detector():
    img = blank_page()
    box = put_text(img, "keep this word deleted here today", 40, 100)

    # Locate the real word to strike out from a clean OCR pass first — its
    # bbox depends on actual glyph metrics, not hand-guessed coordinates.
    target = next(w for w in extract_words(to_gray(img)) if w.text == "deleted")
    draw_strike(
        img,
        {
            "x": int(target.bbox.x),
            "y": int(target.bbox.y),
            "w": int(target.bbox.w),
            "h": int(target.bbox.h),
        },
    )

    block = crop_to_content(img, box)
    gray = to_gray(block)
    binary = to_binary(block)

    annotations = strikethrough.detect(binary)
    assert annotations  # sanity: the real detector found the drawn mark

    words = extract_words(gray)
    text = reconstruct(gray, words, annotations)

    # Whatever the strike visually overlapped is gone from the result —
    # the exact tokenisation is real Tesseract output, not asserted here.
    struck_region = annotations[0].bbox
    for word in words:
        fully_inside = (
            word.bbox.x >= struck_region.x
            and word.bbox.x + word.bbox.w <= struck_region.x + struck_region.w
        )
        if fully_inside:
            assert word.text not in text.split()
