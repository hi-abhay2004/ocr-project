"""
L5 — answer reconstruction.

Turns a block's OCR'd words plus its adjudicated annotations
(ai.annotations, L3/L3.5) into one final reading-order string:
struck-out words are dropped, margin notes are OCR'd separately and
spliced in at the point their nearest arrow connects to (a KD-tree over
arrow positions, per BACKEND_PLAN.md's B5 section), and everything else
reads top-to-bottom, left-to-right.

This is what apps.evaluation.models.AnswerBlock.reconstructed_text
actually is, once Phase B6 wires the real pipeline in place of the B3 stub.
"""

import numpy as np
from scipy.spatial import KDTree

from ai.ocr.tesseract_engine import run_psm6
from ai.types import Annotation, BBox, Word

LINE_TOLERANCE = 12  # px; words within this y-distance are treated as the same line
MARGIN_ARROW_MAX_DISTANCE = 300  # px; beyond this, a margin note has no plausible linked arrow


def _center(bbox: BBox) -> tuple:
    return (bbox.x + bbox.w / 2, bbox.y + bbox.h / 2)


def _overlaps(a: BBox, b: BBox, *, y_pad: float = 0.0) -> bool:
    return not (
        a.x + a.w < b.x or b.x + b.w < a.x or a.y + a.h < b.y - y_pad or b.y + b.h < a.y - y_pad
    )


def _reading_order(words: list[Word]) -> list[Word]:
    """Groups words into lines by CHAINED y-proximity (each word compared
    to the last word added to the current line), not by rounding y into
    fixed-size buckets. A hard bucket boundary can split two words on the
    same visual line into different "lines" purely because their y values
    straddle a multiple of LINE_TOLERANCE (e.g. a short, descender-free
    word OCR's with a slightly different baseline than its neighbours) —
    chaining only cares about the actual gap between consecutive words."""
    by_y = sorted(words, key=lambda w: w.bbox.y)
    lines: list[list[Word]] = []
    for word in by_y:
        if lines and abs(word.bbox.y - lines[-1][-1].bbox.y) <= LINE_TOLERANCE:
            lines[-1].append(word)
        else:
            lines.append([word])

    ordered: list[Word] = []
    for line in lines:
        ordered.extend(sorted(line, key=lambda w: w.bbox.x))
    return ordered


STRIKE_OVERLAP_Y_PAD = 12  # px; see _body_words — VERTICAL tolerance only. A strike's
# own bbox is a thin geometric line (ai.annotations.strikethrough draws it ~4px tall
# at the Hough line's own midpoint); a word's bbox comes from a completely separate
# algorithm (Tesseract). The two measuring the "same" mark on real (not
# hand-injected-for-a-test) data rarely align on the y-axis to the pixel — a strike
# landing a few px above or below the word it visibly crosses out is normal, not a
# detector bug. X stays exact: padding that axis too would start swallowing the
# NEXT word over on a tightly-kerned line, which is a real failure mode, not a
# hypothetical one.


def _body_words(words: list[Word], annotations: list[Annotation]) -> list[Word]:
    """Drops words that are (a) struck out, or (b) actually part of a
    margin note's own text rather than the main body — `words` is expected
    to come from OCR-ing the WHOLE block, margin note included, so this is
    what keeps a margin note from being read twice: once in place, once
    spliced back in at its arrow."""
    strikes = [a.bbox for a in annotations if a.kind == "STRIKE"]
    margins = [a.bbox for a in annotations if a.kind == "MARGIN"]
    if not strikes and not margins:
        return words
    return [
        w
        for w in words
        if not any(_overlaps(w.bbox, region, y_pad=STRIKE_OVERLAP_Y_PAD) for region in strikes)
        and not any(_overlaps(w.bbox, region) for region in margins)
    ]


def _crop(image: np.ndarray, bbox: BBox, pad: int = 6) -> np.ndarray:
    x0 = max(0, int(bbox.x) - pad)
    y0 = max(0, int(bbox.y) - pad)
    x1 = min(image.shape[1], int(bbox.x + bbox.w) + pad)
    y1 = min(image.shape[0], int(bbox.y + bbox.h) + pad)
    return image[y0:y1, x0:x1]


def _ocr_margin_note(image: np.ndarray, margin: Annotation) -> str:
    crop = _crop(image, margin.bbox)
    if crop.size == 0:
        return ""
    return run_psm6(crop).text


def _nearest_word(point: tuple, words: list[Word]) -> tuple:
    """Returns (index, distance) of the closest word to `point`, or
    (None, inf) if `words` is empty."""
    if not words:
        return None, float("inf")
    tree = KDTree([_center(w.bbox) for w in words])
    distance, index = tree.query(point)
    return int(index), float(distance)


def _match_margins_to_arrows(margins: list[Annotation], arrows: list[Annotation]) -> dict:
    """Nearest-arrow-to-each-margin via a KD-tree over arrow positions.
    Bboxes, not exact tip coordinates: by the time an Annotation has been
    through dedup/adjudication (ai.annotations.adjudicator) it no longer
    carries which literal endpoint was the arrowhead, so the arrow's own
    bbox center is the best position information left — close enough to
    anchor a margin note near the right WORD, which is all this needs."""
    if not arrows:
        return {}
    tree = KDTree([_center(a.bbox) for a in arrows])
    matches = {}
    for i, margin in enumerate(margins):
        distance, index = tree.query(_center(margin.bbox))
        if distance <= MARGIN_ARROW_MAX_DISTANCE:
            matches[i] = arrows[int(index)]
    return matches


def reconstruct(image: np.ndarray, words: list[Word], annotations: list[Annotation]) -> str:
    """`image` is the block's own crop (grayscale or BGR) — used only to
    OCR each margin note's own text, separately from `words` (the main
    body's OCR pass). `words` may include margin-note words; they're
    excluded from the body automatically (see `_body_words`)."""
    kept = _reading_order(_body_words(words, annotations))

    margins = [a for a in annotations if a.kind == "MARGIN"]
    arrows = [a for a in annotations if a.kind == "ARROW"]
    matches = _match_margins_to_arrows(margins, arrows)

    insertions: dict[int, list[str]] = {}
    unanchored: list[str] = []
    for i, margin in enumerate(margins):
        text = _ocr_margin_note(image, margin)
        if not text:
            continue
        arrow = matches.get(i)
        anchor = _center(arrow.bbox) if arrow else _center(margin.bbox)
        word_index, distance = _nearest_word(anchor, kept)
        if word_index is None or distance > MARGIN_ARROW_MAX_DISTANCE:
            unanchored.append(text)
        else:
            insertions.setdefault(word_index, []).append(text)

    pieces = list(unanchored)
    for i, word in enumerate(kept):
        pieces.append(word.text)
        if i in insertions:
            pieces.extend(f"[{t}]" for t in insertions[i])
    return " ".join(pieces)
