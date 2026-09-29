"""
L3 — underline detection.

An underline sits just BELOW a line of text: ink above, blank below — the
mirror image of ai/annotations/strikethrough.py's "ink both sides" check.
Emphasis, not deletion (ai.types.Annotation.intent="EMPHASIS").
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
from .strikethrough import _text_occupancy

MIN_LENGTH_RATIO = 0.6  # see strikethrough.py — same local-extent reasoning
# A printed ruled-paper line sitting right under a row of text has exactly
# the underline shape (ink above, blank below) and can span the block's
# full width — nothing in _confidence() below tells it apart from a real
# underline. This caps confidence just under the VLM-escalation threshold
# for anything landing on a detected ruled-paper row (_common.py), so it
# gets a real visual check (adjudicator.py's VLM prompt explicitly asks
# "is this printed paper or a hand-drawn mark") instead of auto-passing.
RULED_LINE_Y_TOLERANCE = 2


def _confidence(line: Line, binary, local_width: float) -> float:
    x1, x2 = sorted((line.x1, line.x2))
    y = int(line.mid_y)

    length_ratio = min(line.length / local_width, 1.0) if local_width > 0 else 0.0
    above = _text_occupancy(binary, y, x1, x2, above=True)
    below = _text_occupancy(binary, y, x1, x2, above=False)
    # Text above AND blank below — multiplicative on purpose. A strike
    # sitting near the top of a word's ink (common: few descenders dip
    # below it) can leave "below" only partially inked, which an additive
    # score would under-penalise; requiring blankness to genuinely hold
    # (not just "less inked than above") is what keeps this from
    # outscoring strikethrough.py's own min(above, below) on a real strike.
    shape_score = above * (1.0 - below)

    return round(0.5 * length_ratio + 0.5 * shape_score, 4)


def detect(binary) -> list[Annotation]:
    """See strikethrough.py's detect() docstring — same local-extent
    length comparison, same reasoning."""
    lines = merge_collinear([ln for ln in detect_lines(binary) if near_horizontal(ln)])
    ruled_ys = ruled_paper_line_ys(lines, binary.shape[1])
    annotations = []
    for line in lines:
        local_width = local_ink_extent(binary, int(line.mid_y), int(line.mid_x))
        if local_width > 0 and line.length / local_width < MIN_LENGTH_RATIO:
            continue
        confidence = _confidence(line, binary, local_width)
        if any(abs(int(line.mid_y) - y) <= RULED_LINE_Y_TOLERANCE for y in ruled_ys):
            confidence = min(confidence, ANNOTATION_AMBIGUITY_THRESHOLD - 0.01)
        if confidence < 0.15:
            continue
        x1, x2 = sorted((line.x1, line.x2))
        annotations.append(
            Annotation(
                kind="UNDERLINE",
                intent="EMPHASIS",
                bbox=BBox(x=float(x1), y=float(line.mid_y - 2), w=float(x2 - x1), h=4.0),
                confidence=confidence,
            )
        )
    return annotations
