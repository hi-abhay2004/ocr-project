"""
Synthetic page-image generator for CV pipeline tests (Phase B5).

Real handwriting is hard to synthesize honestly. Printed text plus drawn
annotation lines/arrows at known pixel coordinates is not a lesser
substitute — BACKEND_PLAN.md's B5 section calls for exactly this
technique, the same one frontend/src/tests/mocks/fixtureImage.ts uses for
the frontend's own overlay tests. It keeps the assertion "did the detector
find the line at (x, y)" separate from "is this fixture a convincing
forgery of handwriting," which no detector here needs to care about.

Not part of `ai/` itself — these are test doubles, imported only from
tests/.
"""

import cv2
import numpy as np

PAGE_W, PAGE_H = 1200, 900
INK = (20, 20, 20)


def blank_page(w: int = PAGE_W, h: int = PAGE_H) -> np.ndarray:
    return np.full((h, w, 3), 255, dtype=np.uint8)


def to_binary(img: np.ndarray) -> np.ndarray:
    """BGR/gray -> ink=255 binary, the convention every ai/ CV module after
    L1 expects (ai.preprocessing.adaptive_threshold's own convention)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]


def put_text(
    img: np.ndarray, text: str, x: int, y: int, scale: float = 1.1, thickness: int = 2
) -> dict:
    """Draws `text` with its baseline at (x, y). Returns the text's own
    bounding box as {x, y, w, h} in the same top-left-origin convention as
    ai.types.BBox, computed from the same cv2.getTextSize() call OpenCV
    used to lay out the glyphs — not eyeballed."""
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, INK, thickness, cv2.LINE_AA)
    return {"x": x, "y": y - th, "w": tw, "h": th + baseline}


def _ink_row_range(img: np.ndarray, bbox: dict) -> tuple:
    """The actual top/bottom ink rows within `bbox`'s columns — NOT the
    nominal cv2.getTextSize() box, which pads for a baseline/descender
    that a given string may barely use. A strike drawn at
    `(bbox.y + bbox.h) / 2` can land above most of a glyph's real ink for
    text with few descenders; this finds where the ink actually is."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    x1, x2 = bbox["x"], bbox["x"] + bbox["w"]
    region = gray[:, x1:x2] < 128
    rows = np.nonzero(region.any(axis=1))[0]
    if len(rows) == 0:
        return bbox["y"], bbox["y"] + bbox["h"]
    return int(rows.min()), int(rows.max())


def draw_strike(img: np.ndarray, bbox: dict, thickness: int = 2) -> None:
    """A line through the vertical middle of `bbox`'s ACTUAL ink — a
    strikethrough."""
    top, bottom = _ink_row_range(img, bbox)
    y = (top + bottom) // 2
    cv2.line(img, (bbox["x"] - 4, y), (bbox["x"] + bbox["w"] + 4, y), INK, thickness, cv2.LINE_AA)


def draw_underline(img: np.ndarray, bbox: dict, thickness: int = 2) -> None:
    """A line just below `bbox`'s actual ink — an underline, not a
    strike."""
    _, bottom = _ink_row_range(img, bbox)
    y = bottom + 6
    cv2.line(img, (bbox["x"] - 2, y), (bbox["x"] + bbox["w"] + 2, y), INK, thickness, cv2.LINE_AA)


def draw_arrow(img: np.ndarray, start: tuple, end: tuple, thickness: int = 2) -> None:
    cv2.arrowedLine(img, start, end, INK, thickness, cv2.LINE_AA, tipLength=0.2)


def draw_margin_blob(img: np.ndarray, x: int, y: int, text: str = "insert: also X") -> dict:
    """A short note written outside the main text column — what an arrow
    from the body text points to."""
    return put_text(img, text, x, y, scale=0.7, thickness=1)


def add_noise(img: np.ndarray, sigma: float = 18) -> np.ndarray:
    noise = np.random.default_rng(0).normal(0, sigma, img.shape)
    return np.clip(img.astype(np.float64) + noise, 0, 255).astype(np.uint8)


def blur(img: np.ndarray, k: int = 5) -> np.ndarray:
    return cv2.GaussianBlur(img, (k, k), 0)


def rotate(img: np.ndarray, angle_degrees: float) -> np.ndarray:
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle_degrees, 1.0)
    return cv2.warpAffine(img, matrix, (w, h), borderValue=(255, 255, 255))


def crop_to_content(img: np.ndarray, box: dict, pad: int = 25) -> np.ndarray:
    """Crops `img` down to `box` plus a small margin — what a real L2
    (ai.segmentation) block actually looks like: tightly bound to its own
    content width, not the full page. Detectors that compare a mark's
    length against the block's own width (strikethrough.py, underline.py)
    need this, not a full ~1200px blank-page canvas, or "spans most of the
    row" is measured against the wrong denominator."""
    h, w = img.shape[:2]
    x0 = max(0, box["x"] - pad)
    y0 = max(0, box["y"] - pad)
    x1 = min(w, box["x"] + box["w"] + pad)
    y1 = min(h, box["y"] + box["h"] + pad)
    return img[y0:y1, x0:x1]


def clean_answer_block(lines: list[str], x: int = 40, y: int = 60, line_gap: int = 55) -> tuple:
    """A block of `lines` of clean printed text, no noise, no skew. Returns
    (image, [bbox, ...]) — one bbox per line, in drawing order."""
    img = blank_page()
    boxes = []
    for i, line in enumerate(lines):
        boxes.append(put_text(img, line, x, y + i * line_gap))
    return img, boxes


def numbered_answer_page(
    blocks: list[tuple], x: int = 30, block_gap: int = 120, line_gap: int = 50
) -> tuple:
    """A full page laid out as `[(question_number_label, [lines...]), ...]`,
    each block starting with its number label on its own first line, e.g.
    `("1a)", ["First line.", "Second line."])`. Blocks are separated by a
    wide vertical gap; lines within a block use the normal line pitch — the
    exact distinction ai.segmentation.segment_rows() has to recover.
    Returns (image, [(question_number_label, top, bottom), ...])."""
    img = blank_page()
    y = 60
    layout = []
    for number, lines in blocks:
        top = y - 30
        put_text(img, number, x, y)
        y += line_gap
        for line in lines:
            put_text(img, line, x, y)
            y += line_gap
        layout.append((number, top, y - line_gap + 20))
        y += block_gap
    return img, layout
