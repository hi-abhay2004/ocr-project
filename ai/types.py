"""
Shared dataclasses passed between pipeline layers (ai/pipeline.py, Phase B6).

Kept minimal and growing only as later phases need fields — these three are
the ones every layer from B5 onward already needs a name for.
"""

from dataclasses import dataclass, field


@dataclass
class BBox:
    """Crop-pixel coordinates — never page coordinates, never normalised.
    See PLAN_OF_ACTION_V2.md §8 note on the overlay contract."""

    x: float
    y: float
    w: float
    h: float


@dataclass
class Annotation:
    kind: str  # STRIKE | UNDERLINE | ARROW | MARGIN
    intent: str  # CORRECTION | EMPHASIS | INSERTION
    bbox: BBox
    confidence: float
    resolved_by: str = "CV"  # CV | VLM


@dataclass
class Word:
    """One OCR'd word and its crop-pixel bbox — what ai.reconstruct (L5)
    needs to drop struck-out words and place margin insertions in reading
    order, which a block's plain joined `reconstructed_text` alone can't
    support."""

    text: str
    bbox: BBox


@dataclass
class Block:
    question_number: str
    image_width: int
    image_height: int
    quality_score: float
    content_type: str = "TEXT"  # TEXT | DIAGRAM | TABLE | EQUATION
    ocr_engine: str = "TESSERACT_6"
    raw_text: str = ""
    reconstructed_text: str = ""
    annotations: list[Annotation] = field(default_factory=list)
