"""
ai/ocr/content_type.py (L4.5) — the TEXT vs non-text split
ai.config.TEXT_DENSITY_CUTOFF actually gates, plus its best-effort
secondary classification among non-text content.
"""

import cv2
import numpy as np

from ai.ocr.content_type import DIAGRAM, TABLE, TEXT, classify, text_density
from tests.unit.cv_fixtures import blank_page, crop_to_content, put_text, to_binary


def test_prose_is_classified_as_text_with_high_density():
    img = blank_page()
    box = put_text(img, "Define BCNF and explain the difference from 3NF", 40, 100)
    binary = to_binary(crop_to_content(img, box))
    assert text_density(binary) > 0.8
    assert classify(binary) == TEXT


def test_a_drawn_shape_is_not_classified_as_text():
    img = blank_page(600, 400)
    cv2.rectangle(img, (50, 50), (250, 200), (20, 20, 20), 3)
    cv2.ellipse(img, (400, 120), (80, 50), 0, 0, 360, (20, 20, 20), 3)
    binary = to_binary(img)
    assert text_density(binary) < 0.15
    assert classify(binary) == DIAGRAM


def test_a_real_grid_is_classified_as_a_table():
    img = blank_page(500, 400)
    for y in range(50, 350, 60):
        cv2.line(img, (50, y), (450, y), (20, 20, 20), 2)
    for x in range(50, 450, 80):
        cv2.line(img, (x, 50), (x, 350), (20, 20, 20), 2)
    binary = to_binary(img)
    assert classify(binary) == TABLE


def test_a_printed_divider_line_does_not_misclassify_real_prose_as_a_diagram():
    # A page's own printed furniture (a column divider, a box border) can
    # otherwise dilute text_density enough to misroute ordinary
    # handwriting into the diagram path — verified (2026-08-26) against a
    # real photographed page whose printed divider did exactly this to an
    # otherwise normal paragraph.
    img = blank_page()
    put_text(img, "Define BCNF and explain the difference from 3NF", 40, 100)
    cv2.line(img, (600, 0), (600, img.shape[0] - 1), (20, 20, 20), 3)
    binary = to_binary(img)
    assert classify(binary) == TEXT


def test_merged_cursive_handwriting_across_several_lines_is_still_text():
    # Real cursive/thick-ink handwriting often binarizes into a few large
    # connected blobs rather than separate letter-sized glyphs — dilating
    # a normal multi-line synthetic page simulates that. text_density()
    # alone reads the result as "not text" (verified: it was exactly this
    # that misclassified a real photographed page as a DIAGRAM on
    # 2026-08-26, even after excluding printed structural lines), but the
    # multi-line row structure survives for
    # _has_regular_text_line_structure() to catch instead.
    img = blank_page()
    lines = [
        "Deadlock prevention uses wait-die and wound-wait schemes",
        "to stop circular wait from ever forming in the system",
        "Mutual exclusion means only one process holds the resource",
        "Hold and wait means a process keeps resources while waiting",
        "No preemption means resources cannot be forcibly taken away",
    ]
    for i, line in enumerate(lines):
        put_text(img, line, 40, 100 + i * 50)
    binary = to_binary(img)
    dilated = cv2.dilate(binary, np.ones((9, 9), np.uint8))
    assert text_density(dilated) < 0.15  # confirms the failure mode is really reproduced here
    assert classify(dilated) == TEXT


def test_a_single_rectangle_is_not_a_table():
    # One rectangle has 2 horizontal + 2 vertical edges — nowhere near a
    # real grid's row/column count. Confirms _is_grid() isn't just "are
    # there any axis-aligned lines at all."
    img = blank_page(400, 300)
    cv2.rectangle(img, (50, 50), (350, 250), (20, 20, 20), 3)
    binary = to_binary(img)
    assert classify(binary) == DIAGRAM
