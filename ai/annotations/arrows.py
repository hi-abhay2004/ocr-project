"""
L3 — arrow detection (margin insertion pointers).

An arrow, unlike a strike or underline, isn't reliably horizontal — it
connects a margin note to a point in the body text at whatever angle that
takes. What identifies it instead is the arrowhead: one endpoint of an
otherwise-straight shaft has noticeably MORE ink packed into a small
neighbourhood than the other endpoint (the two short barb strokes an
arrowhead is made of), where a bare line has none. That asymmetry — not
line angle — is this detector's whole signal.
"""

import numpy as np

from ai.config import ANNOTATION_AMBIGUITY_THRESHOLD
from ai.types import Annotation, BBox

from ._common import (
    RULED_LINE_POSITION_TOLERANCE,
    Line,
    detect_lines,
    merge_collinear,
    near_horizontal,
    ruled_paper_line_xs,
)

MIN_LENGTH = 100  # px; a margin-to-text arrow spans real distance — short diagonal
# strokes this length or under are far more often a text/letter artifact than a mark
SPREAD_RADIUS = 18
MIN_HEAD_RATIO = 1.8  # tip must have at least this much more ink than the tail to count at all
SUPPRESSION_RADIUS = 45  # px; drops an arrowhead's own barb fragments as separate "arrows"


def _ink_spread(binary: np.ndarray, x: int, y: int, radius: int = SPREAD_RADIUS) -> float:
    """Ink-pixel fraction in a square neighbourhood around (x, y) — high
    near a converging arrowhead, low along a bare shaft."""
    y0, y1 = max(0, y - radius), y + radius
    x0, x1 = max(0, x - radius), x + radius
    roi = binary[y0:y1, x0:x1]
    if roi.size == 0:
        return 0.0
    return float((roi > 0).mean())


def tip_point(line: Line, binary: np.ndarray) -> tuple:
    """Whichever endpoint has more surrounding ink — the detected
    arrowhead end. Exposed (not just used internally) because Phase B5's
    L5 reconstruction stitches a margin note in at its nearest arrow TIP,
    not at the arrow's bbox — see ai/reconstruct.py."""
    spread_1 = _ink_spread(binary, line.x1, line.y1)
    spread_2 = _ink_spread(binary, line.x2, line.y2)
    return (line.x1, line.y1) if spread_1 >= spread_2 else (line.x2, line.y2)


def _confidence(line: Line, binary: np.ndarray) -> float | None:
    """None means "not even a candidate" — the tip isn't meaningfully more
    inked than the tail, i.e. there's no detectable arrowhead at all (an
    ordinary diagonal stroke inside a letter, for instance)."""
    spread_1 = _ink_spread(binary, line.x1, line.y1)
    spread_2 = _ink_spread(binary, line.x2, line.y2)
    tip_spread, tail_spread = max(spread_1, spread_2), min(spread_1, spread_2)

    ratio = tip_spread / max(tail_spread, 0.02)
    if ratio < MIN_HEAD_RATIO:
        return None

    length_score = min(line.length / 60.0, 1.0)
    # Saturates once the tip has ~2.5x the tail's ink — a clean arrowhead.
    head_score = min(max(ratio - 1.0, 0.0) / 1.5, 1.0)
    return round(0.5 * length_score + 0.5 * head_score, 4)


def _endpoints_close(a: Line, b: Line, radius: float) -> bool:
    ends_a = [(a.x1, a.y1), (a.x2, a.y2)]
    ends_b = [(b.x1, b.y1), (b.x2, b.y2)]
    return min(np.hypot(ax - bx, ay - by) for ax, ay in ends_a for bx, by in ends_b) <= radius


def detect(binary: np.ndarray) -> list[Annotation]:
    """`binary` is one answer block's (or the page's) ink=255 image. Unlike
    strikethrough/underline, angle is NOT filtered here — an arrow's shaft
    can point any direction.

    An arrowhead is itself made of short line fragments (the two barbs),
    which independently pass the same asymmetry test the shaft does — left
    alone, one drawn arrow would report as three. Longest-first
    non-maximum suppression keeps only the shaft: once a line is accepted,
    any shorter candidate with an endpoint near one of ITS endpoints is
    the accepted line's own arrowhead, not a second arrow.

    Near-horizontal lines are excluded outright: a long straight line
    crossing through or under a line of text is strikethrough.py's or
    underline.py's mark, not this detector's — the ink-spread asymmetry
    check alone isn't reliable enough to rule that out (a strike's two
    endpoints can land near unrelated amounts of nearby ink purely from
    which letters happen to sit closest), and a genuine margin-note arrow
    reaching across a meaningful horizontal distance is virtually never
    perfectly flat."""
    all_lines = merge_collinear(detect_lines(binary, min_length=15, max_gap=6, threshold=15))
    ruled_xs = ruled_paper_line_xs(all_lines, binary.shape[0])
    lines = [ln for ln in all_lines if not near_horizontal(ln, tol_degrees=8)]
    candidates = [(line, _confidence(line, binary)) for line in lines if line.length >= MIN_LENGTH]
    candidates = [(line, conf) for line, conf in candidates if conf is not None]
    candidates.sort(key=lambda pair: pair[0].length, reverse=True)

    accepted: list[Line] = []
    annotations = []
    for line, confidence in candidates:
        if any(_endpoints_close(line, a, SUPPRESSION_RADIUS) for a in accepted):
            continue
        accepted.append(line)
        if any(
            abs(int(line.mid_x) - x) <= RULED_LINE_POSITION_TOLERANCE for x in ruled_xs
        ):
            # Looks like it's sitting on a page-spanning vertical divider
            # or border rather than a mark the student drew — force this
            # through VLM adjudication (adjudicator.py) instead of
            # auto-accepting a high ink-asymmetry score.
            confidence = min(confidence, ANNOTATION_AMBIGUITY_THRESHOLD - 0.01)
        x1, x2 = sorted((line.x1, line.x2))
        y1, y2 = sorted((line.y1, line.y2))
        annotations.append(
            Annotation(
                kind="ARROW",
                intent="INSERTION",
                bbox=BBox(
                    x=float(x1), y=float(y1), w=float(x2 - x1) or 1.0, h=float(y2 - y1) or 1.0
                ),
                confidence=confidence,
            )
        )
    return annotations
