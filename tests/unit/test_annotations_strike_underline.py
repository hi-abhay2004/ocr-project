"""
ai/annotations/strikethrough.py and underline.py (L3) — synthetic fixtures
with a mark drawn at a known position, so the assertion is "did the
detector find THIS mark," not "does it look plausible."

`local_row_width` is passed explicitly in every call here, matching how the
real pipeline invokes these — with the L2 segment's own bbox.w — rather
than the full synthetic page width the fixtures happen to be canvased on.
"""

import cv2

from ai.annotations import strikethrough, underline
from ai.config import ANNOTATION_AMBIGUITY_THRESHOLD
from tests.unit.cv_fixtures import (
    INK,
    blank_page,
    draw_strike,
    draw_underline,
    put_text,
    to_binary,
)

TEXT = "redundancy and update anomalies caused by transitive dependencies"


def _strike_fixture():
    img = blank_page()
    box = put_text(img, TEXT, 40, 100)
    draw_strike(img, box)
    return to_binary(img), box


def _underline_fixture():
    img = blank_page()
    box = put_text(img, TEXT, 40, 100)
    draw_underline(img, box)
    return to_binary(img), box


def _clean_fixture():
    img = blank_page()
    box = put_text(img, TEXT, 40, 100)
    return to_binary(img), box


def test_strikethrough_finds_the_mark_and_scores_it_above_ambiguity_threshold():
    binary, box = _strike_fixture()
    results = strikethrough.detect(binary)
    assert len(results) == 1
    assert results[0].kind == "STRIKE"
    assert results[0].confidence >= 0.70


def test_strikethrough_bbox_overlaps_the_drawn_line_position():
    binary, box = _strike_fixture()
    [result] = strikethrough.detect(binary)
    mid_y = box["y"] + box["h"] / 2
    assert abs(result.bbox.y - mid_y) < 15
    assert result.bbox.w > box["w"] * 0.5


def test_strikethrough_scores_higher_than_underline_on_a_strike_mark():
    binary, box = _strike_fixture()
    [strike_result] = strikethrough.detect(binary)
    [underline_result] = underline.detect(binary)
    assert strike_result.confidence > underline_result.confidence


def test_underline_finds_the_mark_and_scores_it_above_ambiguity_threshold():
    binary, box = _underline_fixture()
    results = underline.detect(binary)
    assert len(results) == 1
    assert results[0].kind == "UNDERLINE"
    assert results[0].confidence >= 0.70


def test_underline_scores_higher_than_strikethrough_on_an_underline_mark():
    binary, box = _underline_fixture()
    [underline_result] = underline.detect(binary)
    [strike_result] = strikethrough.detect(binary)
    assert underline_result.confidence > strike_result.confidence


def test_neither_detector_fires_on_clean_text():
    binary, box = _clean_fixture()
    assert strikethrough.detect(binary) == []
    assert underline.detect(binary) == []


def test_a_short_stray_mark_does_not_pass_the_length_prefilter():
    # A mark's length is compared against its OWN local word/phrase extent
    # (ai.annotations._common.local_ink_extent), not the whole row — a
    # single struck word is the common case, not "too short to be real"
    # (see test_a_single_struck_word_is_detected_within_a_long_line).
    # What SHOULD still fail the prefilter is a short stroke that covers
    # only a small fraction of the (much wider) word it sits inside.
    img = blank_page()
    put_text(img, TEXT, 40, 100)
    from ai.ocr.tesseract_engine import extract_words
    from ai.preprocessing import to_gray

    target = next(w for w in extract_words(to_gray(img)) if w.text == "transitive")
    y = int(target.bbox.y + target.bbox.h / 2)
    x0 = int(target.bbox.x + 10)
    import cv2

    cv2.line(img, (x0, y), (x0 + 20, y), (10, 10, 10), 2, cv2.LINE_AA)
    binary = to_binary(img)
    assert strikethrough.detect(binary) == []


def test_a_single_struck_word_is_detected_within_a_long_line():
    # The realistic case: one word crossed out in an otherwise-long
    # answer line. Its length is nowhere near the FULL line's width, but
    # it spans nearly all of ITS OWN word — that's what should matter.
    img = blank_page()
    put_text(img, TEXT, 40, 100)
    from ai.ocr.tesseract_engine import extract_words
    from ai.preprocessing import to_gray

    target = next(w for w in extract_words(to_gray(img)) if w.text == "anomalies")
    draw_strike(
        img,
        {
            "x": int(target.bbox.x),
            "y": int(target.bbox.y),
            "w": int(target.bbox.w),
            "h": int(target.bbox.h),
        },
    )
    binary = to_binary(img)
    results = strikethrough.detect(binary)
    assert len(results) == 1
    assert results[0].confidence >= 0.70


def test_underline_confidence_is_suppressed_on_a_printed_ruled_paper_pattern():
    # Several full-width, evenly-spaced horizontal lines simulate printed
    # ruled paper — including one sitting right where a real underline
    # would (just below the text's own baseline), which is geometrically
    # identical to a genuine hand-drawn mark. Verified (2026-08-26) against
    # a real photographed lined page: this pattern was scoring as a
    # confident UNDERLINE with nothing to tell it apart from the real
    # thing using one line's shape alone.
    img = blank_page()
    put_text(img, TEXT, 40, 100)
    for y in (25, 55, 85, 115, 145, 175):
        cv2.line(img, (5, y), (img.shape[1] - 5, y), INK, 1, cv2.LINE_AA)
    binary = to_binary(img)
    results = underline.detect(binary)
    assert results  # still surfaced as a candidate for VLM adjudication...
    assert all(r.confidence < ANNOTATION_AMBIGUITY_THRESHOLD for r in results)  # ...not auto-accepted
