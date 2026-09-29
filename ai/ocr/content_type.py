"""
L4.5 — content-type classification.

Decides whether a block is prose (normal L4 OCR routing) or something else
entirely — a diagram, a table, an equation — that OCR would mangle and
that instead gets routed to ai/ocr/specialized.py's VLM description.

The TEXT/non-TEXT split is what ai.config.TEXT_DENSITY_CUTOFF actually
gates and is the one this module's callers depend on. The three-way split
among non-text content (DIAGRAM/TABLE/EQUATION) is a secondary,
best-effort classification — matching apps.evaluation.models.AnswerBlock's
existing ContentType choices — layered on top of that same TEXT/non-TEXT
signal, not a second independent gate.
"""

import cv2
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

from ai.annotations._common import detect_lines, merge_collinear, near_horizontal
from ai.config import TEXT_DENSITY_CUTOFF

TEXT = "TEXT"
DIAGRAM = "DIAGRAM"
TABLE = "TABLE"
EQUATION = "EQUATION"

# A connected component wider or taller than this (px) is too big to be a
# single handwritten/printed character — it's part of a larger shape.
MAX_LETTER_DIMENSION = 45
MIN_GRID_LINES = 3  # a real table has several rows/columns, not just one rectangle's 4 sides

# A page's own printed furniture — a divider between columns, a boxed
# header's border, a page edge — shows up as one long, thin connected
# component. That's neither a letter NOR real evidence of a diagram; left
# in the denominator, it dilutes text_density enough to misroute a page
# that's mostly ordinary handwriting into the non-text (diagram/table/
# equation) path — verified (2026-08-26) against a real photographed page
# whose printed date-box border and column divider did exactly that to an
# otherwise normal paragraph of handwritten prose. Excluded from BOTH the
# numerator and denominator: it isn't letter ink, but it isn't diagram ink
# either, so it shouldn't count as evidence for either side of the ratio.
STRUCTURAL_LINE_MAX_THICKNESS = 6
STRUCTURAL_LINE_MIN_LENGTH_FRACTION = 0.6


def _is_structural_line(w: int, h: int, block_width: int, block_height: int) -> bool:
    if h <= STRUCTURAL_LINE_MAX_THICKNESS and w >= block_width * STRUCTURAL_LINE_MIN_LENGTH_FRACTION:
        return True  # a long horizontal rule/border
    if w <= STRUCTURAL_LINE_MAX_THICKNESS and h >= block_height * STRUCTURAL_LINE_MIN_LENGTH_FRACTION:
        return True  # a long vertical divider/border
    return False


def text_density(binary: np.ndarray) -> float:
    """Fraction of (non-structural) ink pixels that belong to letter-sized
    connected components. High for prose (many small, separate glyphs);
    low for a diagram/table/equation, which is typically one or a few
    large connected shapes."""
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n <= 1:
        return 0.0

    height, width = binary.shape[:2]
    letter_ink = 0
    structural_ink = 0
    for i in range(1, n):
        x, y, w, h, area = stats[i][:5]
        if _is_structural_line(w, h, width, height):
            structural_ink += int(area)
        elif w <= MAX_LETTER_DIMENSION and h <= MAX_LETTER_DIMENSION:
            letter_ink += int(area)

    total_ink = int((binary > 0).sum()) - structural_ink
    if total_ink <= 0:
        return 0.0
    return letter_ink / total_ink


# text_density() assumes prose breaks into separate letter-sized ink
# blobs — true for the machine-printed fixtures this module was tested
# against, false for a lot of real cursive/messy handwriting: adjacent
# strokes bridge into one large connected blob once binarized, which
# reads as "one big shape" exactly like a diagram would. Verified
# (2026-08-26) against a real photographed page: the whole handwritten
# paragraph merged into a single 899x573 connected component, scoring
# text_density near zero despite being ordinary prose.
#
# The independent signal that survives this: real prose is still laid out
# in several roughly-evenly-spaced horizontal bands (lines of writing),
# even when the ink WITHIN a line fuses together — a diagram's ink isn't
# organized that way. A raw peak COUNT isn't specific enough on its own
# (a rectangle's top/bottom edges, or a real table's gridlines, also
# produce a handful of evenly-spaced peaks) — what a real multi-line
# answer has that those don't is a LONG RUN of consecutive peaks sharing
# close to the same pitch, since handwritten line spacing stays roughly
# constant across many lines in a row, not just two or three unrelated
# shape edges.
LINE_PEAK_MIN_HEIGHT_FRACTION = 0.15
LINE_PEAK_MIN_DISTANCE = 20
LINE_PEAK_SMOOTHING = 15
MIN_CONSECUTIVE_TEXT_LINES = 5
TEXT_LINE_PITCH_TOLERANCE = 0.4


def _has_regular_text_line_structure(binary: np.ndarray) -> bool:
    profile = (binary > 0).sum(axis=1).astype(float)
    smoothed = uniform_filter1d(profile, size=LINE_PEAK_SMOOTHING)
    peak_height = smoothed.max() * LINE_PEAK_MIN_HEIGHT_FRACTION if smoothed.max() > 0 else 0
    peaks, _ = find_peaks(smoothed, height=peak_height, distance=LINE_PEAK_MIN_DISTANCE)
    if len(peaks) < MIN_CONSECUTIVE_TEXT_LINES:
        return False

    gaps = [b - a for a, b in zip(peaks, peaks[1:], strict=False)]
    best_run, run = 1, 1
    for i in range(1, len(gaps)):
        similar = abs(gaps[i] - gaps[i - 1]) <= max(gaps[i - 1], gaps[i]) * TEXT_LINE_PITCH_TOLERANCE
        run = run + 1 if similar else 1
        best_run = max(best_run, run)
    return best_run + 1 >= MIN_CONSECUTIVE_TEXT_LINES  # +1: `run` counts gaps, not peaks


def _is_grid(binary: np.ndarray) -> bool:
    """A real table's gridlines each span most of the table's own width or
    height. A curved shape (an ellipse, say) can produce short
    near-axis-aligned Hough fragments purely from how it's polygonally
    approximated — requiring each candidate line to span a real fraction
    of the block is what tells an actual grid apart from that noise, since
    a stray 40px curve fragment never does."""
    height, width = binary.shape[:2]
    lines = merge_collinear(detect_lines(binary, min_length=30, max_gap=6, threshold=25))

    horizontal = sum(
        1 for ln in lines if near_horizontal(ln, tol_degrees=10) and ln.length >= width * 0.4
    )
    vertical = sum(
        1
        for ln in lines
        if not near_horizontal(ln, tol_degrees=10)
        and 80 <= abs(ln.angle_degrees) <= 100
        and ln.length >= height * 0.4
    )
    return horizontal >= MIN_GRID_LINES and vertical >= MIN_GRID_LINES


def classify(binary: np.ndarray) -> str:
    # _is_grid() runs BEFORE the text checks: a real table's own gridlines
    # are evenly spaced too, so _has_regular_text_line_structure() would
    # otherwise mistake one for prose before this function got a chance to
    # call it a TABLE.
    if _is_grid(binary):
        return TABLE
    if text_density(binary) >= TEXT_DENSITY_CUTOFF or _has_regular_text_line_structure(binary):
        return TEXT

    # A handful of small, scattered symbol-sized components with no
    # dominant large shape reads as an equation; a single big connected
    # blob (or a few) reads as a diagram. Neither is a precise test — this
    # is the best-effort secondary split described in the module docstring.
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n <= 1:
        return DIAGRAM
    areas = [int(stats[i][4]) for i in range(1, n)]
    largest_share = max(areas) / sum(areas)
    if largest_share < 0.5 and len(areas) >= 3:
        return EQUATION
    return DIAGRAM
