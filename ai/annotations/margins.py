"""
L3 — margin note detection.

A margin note is ink that sits OUTSIDE the answer's main text column — an
insertion a student/teacher wrote in the blank margin, usually linked back
into the body by an arrow (ai/annotations/arrows.py). Detected via
connected components (after a horizontal dilation that merges individual
letters into words/lines, so a whole line of body text is one blob, not
forty): components are clustered by horizontal (x-range) overlap, the
largest-area cluster is called the "main column," and any OTHER component
that sits a clear horizontal gap away from it is a margin candidate.
"""

import cv2
import numpy as np

from ai.types import Annotation, BBox

DILATE_KERNEL = (35, 15)  # merges letters -> words -> a line, without bridging a real page gap
CLUSTER_GAP_TOL = 25  # px; components closer than this belong to the same column
MIN_MARGIN_GAP = 40  # px; how far outside the main column counts as "margin," not "same column"
MIN_AREA = 150  # px^2; drops single-speck noise components


def _components(binary: np.ndarray) -> list[dict]:
    dilated = cv2.dilate(binary, cv2.getStructuringElement(cv2.MORPH_RECT, DILATE_KERNEL))
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)
    return [
        {
            "x": int(stats[i][0]),
            "y": int(stats[i][1]),
            "w": int(stats[i][2]),
            "h": int(stats[i][3]),
            "area": int(stats[i][4]),
        }
        for i in range(1, n)  # 0 is the background label
        if stats[i][4] >= MIN_AREA
    ]


def _cluster_by_x_overlap(components: list[dict]) -> list[dict]:
    """Groups components whose x-ranges are within CLUSTER_GAP_TOL of each
    other into one cluster — one per text column present on the page."""
    by_x = sorted(components, key=lambda c: c["x"])
    clusters: list[dict] = []
    for c in by_x:
        x1, x2 = c["x"], c["x"] + c["w"]
        if clusters and x1 - clusters[-1]["x2"] <= CLUSTER_GAP_TOL:
            clusters[-1]["x2"] = max(clusters[-1]["x2"], x2)
            clusters[-1]["area"] += c["area"]
            clusters[-1]["members"].append(c)
        else:
            clusters.append({"x1": x1, "x2": x2, "area": c["area"], "members": [c]})
    return clusters


def detect(binary: np.ndarray) -> list[Annotation]:
    components = _components(binary)
    if len(components) < 2:
        return []  # nothing to be "outside" of

    clusters = _cluster_by_x_overlap(components)
    main = max(clusters, key=lambda c: c["area"])

    annotations = []
    for cluster in clusters:
        if cluster is main:
            continue
        gap = max(main["x1"] - cluster["x2"], cluster["x1"] - main["x2"], 0)
        if gap < MIN_MARGIN_GAP:
            continue

        gap_score = min(gap / (MIN_MARGIN_GAP * 3), 1.0)
        # A margin cluster comparable in size to the main column is
        # probably a second real answer column, not a short note — discount it.
        size_ratio = cluster["area"] / max(main["area"], 1)
        size_score = max(1.0 - size_ratio, 0.0)
        confidence = round(0.6 * gap_score + 0.4 * size_score, 4)
        if confidence < 0.15:
            continue

        x1 = min(m["x"] for m in cluster["members"])
        y1 = min(m["y"] for m in cluster["members"])
        x2 = max(m["x"] + m["w"] for m in cluster["members"])
        y2 = max(m["y"] + m["h"] for m in cluster["members"])
        annotations.append(
            Annotation(
                kind="MARGIN",
                intent="INSERTION",
                bbox=BBox(x=float(x1), y=float(y1), w=float(x2 - x1), h=float(y2 - y1)),
                confidence=confidence,
            )
        )
    return annotations
