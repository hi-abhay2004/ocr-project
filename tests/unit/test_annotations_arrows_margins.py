"""
ai/annotations/arrows.py and margins.py (L3) — synthetic fixtures with a
known arrowhead end / a known spatially-separated margin note.
"""

from ai.annotations import arrows, margins
from tests.unit.cv_fixtures import blank_page, draw_arrow, put_text, to_binary


def test_arrow_is_detected_with_a_clear_arrowhead():
    img = blank_page()
    draw_arrow(img, (200, 320), (430, 230))
    binary = to_binary(img)

    results = arrows.detect(binary)
    assert len(results) == 1
    assert results[0].kind == "ARROW"
    assert results[0].confidence > 0.5


def test_a_bare_line_with_no_arrowhead_scores_lower_than_a_real_arrow():
    import cv2

    img_arrow = blank_page()
    draw_arrow(img_arrow, (200, 320), (430, 230))
    arrow_binary = to_binary(img_arrow)
    arrow_result = max(arrows.detect(arrow_binary), key=lambda a: a.confidence)

    img_bare = blank_page()
    cv2.line(img_bare, (200, 320), (430, 230), (20, 20, 20), 2, cv2.LINE_AA)
    bare_binary = to_binary(img_bare)
    bare_results = arrows.detect(bare_binary)
    bare_confidence = bare_results[0].confidence if bare_results else 0.0

    assert arrow_result.confidence > bare_confidence


def test_no_arrows_on_a_page_of_clean_text():
    img = blank_page()
    put_text(img, "clean printed text with no marks at all", 40, 100)
    binary = to_binary(img)
    assert arrows.detect(binary) == []


def test_tip_point_picks_the_more_inked_endpoint():
    from ai.annotations._common import detect_lines, merge_collinear

    img = blank_page()
    draw_arrow(img, (200, 320), (430, 230))
    binary = to_binary(img)
    all_lines = merge_collinear(detect_lines(binary, min_length=15, max_gap=6, threshold=15))
    lines = [ln for ln in all_lines if ln.length > 100]
    assert lines
    tip = arrows.tip_point(lines[0], binary)
    # The tip should land near the arrow's drawn head (430, 250), not its tail.
    assert abs(tip[0] - 430) < abs(tip[0] - 200)


def _two_column_page():
    img = blank_page()
    put_text(img, "A relation is in BCNF if every determinant", 60, 100)
    put_text(img, "is a superkey of the relation schema.", 60, 150)
    margin_box = put_text(img, "also: 3NF", 950, 120, scale=0.7, thickness=1)
    return to_binary(img), margin_box


def test_margin_note_is_detected_outside_the_main_column():
    binary, margin_box = _two_column_page()
    results = margins.detect(binary)
    assert len(results) == 1
    assert results[0].kind == "MARGIN"
    # The detected bbox should sit near the margin note's own x position,
    # not the main text column starting at x=60.
    assert results[0].bbox.x > margin_box["x"] - 50


def test_no_margin_note_on_a_single_column_page():
    img = blank_page()
    put_text(img, "A relation is in BCNF if every determinant", 60, 100)
    put_text(img, "is a superkey of the relation schema.", 60, 150)
    binary = to_binary(img)
    assert margins.detect(binary) == []
