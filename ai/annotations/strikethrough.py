"""
L3 — strikethrough detection.

A strikethrough is a roughly-horizontal line that crosses THROUGH a line of
text: ink sits both above and below it. That's what distinguishes it from
an underline (ink above, blank below — ai/annotations/underline.py), which
is the confusion this detector exists to resolve confidently enough that
most blocks never need ai/annotations/adjudicator.py's VLM call at all.
"""

from ai.config import ANNOTATION_AMBIGUITY_THRESHOLD
from ai.types import Annotation, BBox

from ._common import (
    Line,
    detect_lines,
    local_ink_extent,
    merge_collinear,
    near_horizontal,
    ruled_paper_line_ys,
)

WINDOW_HEIGHT = 16
WINDOW_GAP = 2
# A genuine strike spans most of the word(s) it crosses out — compared
# against the LOCAL word/phrase it sits over (_common.local_ink_extent),
# not the whole block. Individual glyphs (crossbars of "t"/"f", the
# horizontal stroke of "e"/"z") produce their own short near-horizontal
# Hough fragments — this ratio is what tells those apart from a real mark,
# before confidence scoring even runs.
MIN_LENGTH_RATIO = 0.6
# See underline.py — same printed-ruled-paper risk, less likely here (a
# strike needs ink both above AND below, which a ruling line under a
# line's own baseline usually doesn't have) but cheap to guard the same way.
RULED_LINE_Y_TOLERANCE = 2


def _text_occupancy(binary, y: int, x1: int, x2: int, *, above: bool) -> float:
    """Fraction of columns in [x1, x2) that have ANY ink within a window
    just above/below y — not average pixel density. A thin stroke occupies
    only a small share of its own bounding pixels, so measuring density
    directly underestimates "is there a character here" badly; whether a
    column has ink *anywhere* in a window tall enough to span an
    x-height/ascender/descender is what actually distinguishes "text is
    present here" from "this is blank"."""
    if above:
        y0, y1 = max(0, y - WINDOW_GAP - WINDOW_HEIGHT), max(0, y - WINDOW_GAP)
    else:
        y0, y1 = y + WINDOW_GAP, y + WINDOW_GAP + WINDOW_HEIGHT
    region = binary[y0:y1, x1:x2]
    if region.size == 0:
        return 0.0
    return float((region > 0).any(axis=0).mean())


def _confidence(line: Line, binary, local_width: float) -> float:
    x1, x2 = sorted((line.x1, line.x2))
    y = int(line.mid_y)

    length_ratio = min(line.length / local_width, 1.0) if local_width > 0 else 0.0
    above = _text_occupancy(binary, y, x1, x2, above=True)
    below = _text_occupancy(binary, y, x1, x2, above=False)
    # Both sides need text for this to be a strike-through-text mark, not a
    # line floating in blank space — the weaker side caps the score.
    surrounded = min(above, below)

    return round(0.5 * length_ratio + 0.5 * surrounded, 4)


def detect(binary) -> list[Annotation]:
    """`binary` is one answer block's ink=255 image (ai.preprocessing's
    convention) — a full multi-word answer line, not just a single word.
    Each candidate line's length is compared against its OWN local
    word/phrase extent (_common.local_ink_extent), not the whole block, so
    striking one word out of a long line doesn't read as "far too short to
    be a real mark"."""
    lines = merge_collinear([ln for ln in detect_lines(binary) if near_horizontal(ln)])
    ruled_ys = ruled_paper_line_ys(lines, binary.shape[1], binary.shape[0])
    annotations = []
    for line in lines:
        local_width = local_ink_extent(binary, int(line.mid_y), int(line.mid_x))
        if local_width > 0 and line.length / local_width < MIN_LENGTH_RATIO:
            continue
        confidence = _confidence(line, binary, local_width)
        if any(abs(int(line.mid_y) - y) <= RULED_LINE_Y_TOLERANCE for y in ruled_ys):
            confidence = min(confidence, ANNOTATION_AMBIGUITY_THRESHOLD - 0.01)
        if confidence < 0.15:  # not even a plausible candidate — pure noise
            continue
        x1, x2 = sorted((line.x1, line.x2))
        annotations.append(
            Annotation(
                kind="STRIKE",
                intent="CORRECTION",
                bbox=BBox(x=float(x1), y=float(line.mid_y - 2), w=float(x2 - x1), h=4.0),
                confidence=confidence,
            )
        )
    return annotations
