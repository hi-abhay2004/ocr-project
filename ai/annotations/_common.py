"""
Shared line-detection helper for the L3 annotation detectors
(strikethrough.py, underline.py, arrows.py). Not a detector itself — just
the Hough-transform plumbing every straight-line-based detector needs, so
"find straight ink strokes and merge the collinear fragments Hough returns
into one line" is written once.
"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Line:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def length(self) -> float:
        return float(np.hypot(self.x2 - self.x1, self.y2 - self.y1))

    @property
    def angle_degrees(self) -> float:
        return float(np.degrees(np.arctan2(self.y2 - self.y1, self.x2 - self.x1)))

    @property
    def mid_y(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def mid_x(self) -> float:
        return (self.x1 + self.x2) / 2


def detect_lines(
    binary: np.ndarray,
    *,
    min_length: int = 25,
    max_gap: int = 2,
    threshold: int = 25,
) -> list[Line]:
    """Straight ink strokes via the probabilistic Hough transform. `binary`
    is ink=255 (ai.preprocessing's convention). Hough tends to return a
    handwritten/printed stroke as several near-collinear fragments rather
    than one segment — callers that care about a single mark's full extent
    should merge with `merge_collinear()`.

    `max_gap` is deliberately tight (2px, not OpenCV's usual "a few
    letters' worth" default). A real strike/underline is one continuous
    drawn stroke with no internal gaps to bridge at all; ordinary printed
    or handwritten text has small gaps BETWEEN letters that a looser
    max_gap will happily bridge into one long fake "line" spanning most of
    a word — Hough finding a straight line along several letters' aligned
    tops is a real failure mode here, not a hypothetical one (verified:
    maxLineGap=8 stitched an untouched word into a 190px+ line with zero
    marks drawn). A tight max_gap costs nothing on a genuine mark, which
    never needed gap-bridging in the first place."""
    raw = cv2.HoughLinesP(
        binary,
        rho=1,
        theta=np.pi / 180,
        threshold=threshold,
        minLineLength=min_length,
        maxLineGap=max_gap,
    )
    if raw is None:
        return []
    return [Line(int(x1), int(y1), int(x2), int(y2)) for x1, y1, x2, y2 in raw[:, 0]]


def merge_collinear(
    lines: list[Line], *, angle_tol: float = 8.0, gap_tol: float = 20.0
) -> list[Line]:
    """Merges near-collinear, near-adjacent line fragments into single
    lines spanning their full extent — one strike/underline mark, not five
    overlapping Hough segments describing the same stroke."""
    remaining = list(lines)
    merged: list[Line] = []

    while remaining:
        current = remaining.pop(0)
        changed = True
        while changed:
            changed = False
            for other in list(remaining):
                if _same_stroke(current, other, angle_tol, gap_tol):
                    current = _join(current, other)
                    remaining.remove(other)
                    changed = True
        merged.append(current)

    return merged


def _same_stroke(a: Line, b: Line, angle_tol: float, gap_tol: float) -> bool:
    angle_diff = abs(a.angle_degrees - b.angle_degrees)
    angle_diff = min(angle_diff, 180 - angle_diff)
    if angle_diff > angle_tol:
        return False
    # Endpoints close enough to be the same stroke's fragments.
    ends_a = [(a.x1, a.y1), (a.x2, a.y2)]
    ends_b = [(b.x1, b.y1), (b.x2, b.y2)]
    closest = min(np.hypot(ax - bx, ay - by) for ax, ay in ends_a for bx, by in ends_b)
    return closest <= gap_tol


def _join(a: Line, b: Line) -> Line:
    points = [(a.x1, a.y1), (a.x2, a.y2), (b.x1, b.y1), (b.x2, b.y2)]
    # The two points furthest apart define the joined stroke's full extent.
    best = max(
        ((p, q) for p in points for q in points),
        key=lambda pair: np.hypot(pair[0][0] - pair[1][0], pair[0][1] - pair[1][1]),
    )
    (x1, y1), (x2, y2) = best
    return Line(x1, y1, x2, y2)


def near_horizontal(line: Line, tol_degrees: float = 12.0) -> bool:
    angle = abs(line.angle_degrees)
    angle = min(angle, 180 - angle)
    return angle <= tol_degrees


def near_vertical(line: Line, tol_degrees: float = 12.0) -> bool:
    return abs(abs(line.angle_degrees) - 90) <= tol_degrees


# Shared by underline.py, strikethrough.py, arrows.py: how close (px) a
# candidate's own position needs to be to a detected ruled-paper row/column
# to count as landing on it — a couple of px of slack for merge_collinear's
# own rounding, not a real tolerance for "nearby but different."
RULED_LINE_POSITION_TOLERANCE = 2


# A printed ruled-paper line (notebook/exam-paper ruling, or a planner
# page's divider) is geometrically indistinguishable from a genuine
# underline/strike at the level of ONE line: both are a straight,
# near-horizontal stroke sitting near a row of text. What's different is
# that real ruled paper prints SEVERAL such lines, each spanning nearly
# the block's full width — a student marking up their own answer rarely
# produces more than one or two page-wide lines.
#
# This originally also required those lines to share one consistent
# vertical pitch (real ruling being evenly spaced) — dropped after
# verifying (2026-08-26) against a real photographed page that it made
# the check too fragile for an actual camera photo: printed page
# furniture unrelated to the notebook ruling (here, a date-box header's
# own borders) sharing the same block puts a second, differently-spaced
# group of full-width lines into the same list, which broke a single
# global pitch check even though the notebook ruling itself (15 lines
# total, comfortably over the threshold below) was detected just fine.
# Simply counting is more robust to that kind of real-photo noise, and
# it's a safe trade: a candidate landing on one of these rows still only
# gets ROUTED to VLM adjudication (ai/annotations/adjudicator.py), not
# rejected outright — an occasional genuine full-width mark still gets
# confirmed correctly there, it just costs one more VLM call to do so.
RULED_LINE_MIN_WIDTH_FRACTION = 0.75
RULED_PATTERN_MIN_COUNT = 3


def ruled_paper_line_ys(lines: list[Line], block_width: int) -> set[int]:
    """Returns the (rounded) `mid_y` of every near-horizontal line spanning
    most of the block's width, once there are enough of them in one block
    to look like printed ruling rather than one or two genuine marks — so
    a caller (underline.py, strikethrough.py) can treat a candidate
    landing on one of these rows as suspect rather than a confident
    CV-resolved mark. See this function's module-level comment for why
    that's "count", not "count AND regular pitch"."""
    full_width = [
        ln
        for ln in lines
        if near_horizontal(ln) and ln.length >= block_width * RULED_LINE_MIN_WIDTH_FRACTION
    ]
    if len(full_width) < RULED_PATTERN_MIN_COUNT:
        return set()
    return {int(ln.mid_y) for ln in full_width}


def ruled_paper_line_xs(lines: list[Line], block_height: int) -> set[int]:
    """Same idea as `ruled_paper_line_ys`, for the page's own VERTICAL
    structure — a column divider, a margin rule, a page-edge border —
    which arrows.py can otherwise mistake for a long arrow shaft purely
    from coincidental ink asymmetry at its two ends (verified 2026-08-26
    against a real photographed page: a full-block-height divider at the
    page's edge scored as a confident ARROW). Only ONE such line is
    enough to flag here, unlike the horizontal case: real notebook paper
    legitimately has MANY printed rules, but a page normally has at most
    one vertical divider, and a genuine margin-note arrow is a
    short-to-medium diagonal mark that essentially never spans a block's
    FULL height."""
    full_height = [
        ln
        for ln in lines
        if near_vertical(ln) and ln.length >= block_height * RULED_LINE_MIN_WIDTH_FRACTION
    ]
    return {int(ln.mid_x) for ln in full_height}


def local_ink_extent(
    binary: np.ndarray, y: int, x_center: int, *, gap: int = 12, band: int = 10
) -> int:
    """The width (px) of the contiguous ink run at row `y` that contains
    `x_center` — expanding outward from it while gaps between ink columns
    stay under `gap` px (bridging letter-to-letter kerning within one
    word), and stopping at the first gap wider than that (a real
    word-to-word boundary).

    This is what a strike/underline mark's own length should be compared
    against, NOT the whole block's width: a block is very often a full
    multi-word answer line, and a mark drawn over just one word of it
    would otherwise always read as "way too short to be a real mark" —
    exactly backwards, since striking a single word is the common case,
    not the rare one."""
    row_band = binary[max(0, y - band) : y + band, :]
    if row_band.size == 0:
        return 0
    col_has_ink = (row_band > 0).any(axis=0)
    width = len(col_has_ink)
    x_center = int(np.clip(x_center, 0, width - 1))

    left = x_center
    blank_run = 0
    while left > 0:
        if col_has_ink[left - 1]:
            blank_run = 0
        else:
            blank_run += 1
            if blank_run > gap:
                break
        left -= 1
    left += blank_run

    right = x_center
    blank_run = 0
    while right < width - 1:
        if col_has_ink[right + 1]:
            blank_run = 0
        else:
            blank_run += 1
            if blank_run > gap:
                break
        right += 1
    right -= blank_run

    return max(right - left, 1)
