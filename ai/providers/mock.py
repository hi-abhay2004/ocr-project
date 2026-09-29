"""
Deterministic, network-free implementations of the three provider ABCs.

CI runs entirely against these (config/settings/test.py forces LLM_PROVIDER to
"mock" no matter what). Two things make that trustworthy rather than a rubber
stamp:

  1. Call counters. Phase B5's cost-guard tests assert `mock_vlm.call_count == 0`
     on a clean sheet and `== 1` on an ambiguous one — the mechanism that catches
     a regression that would otherwise only show up as a real NIM bill.
  2. Embeddings are content-derived, not zeroed or random-per-call. The same
     text always maps to the same unit vector, so cosine similarity behaves
     sanely in tests: identical text -> similarity 1.0, unrelated text -> low
     similarity. A provider that returned e.g. all-zero vectors would make
     every retrieval test pass by accident.
"""

import json
import math
import random
import re
import threading
import zlib

from ai.config import CONCEPT_COUNT_MAX, EMBEDDING_DIM

from .base import EmbeddingProvider, LLMProvider, VLMProvider

_MODEL_ANSWER_TAG_RE = re.compile(r"<model_answer>\s*(.*?)\s*</model_answer>", re.DOTALL)
_CONCEPT_TAG_RE = re.compile(r"<concept>\s*(.*?)\s*</concept>", re.DOTALL)
_EXCERPT_TAG_RE = re.compile(r"<excerpt>\s*(.*?)\s*</excerpt>", re.DOTALL)
_FEEDBACK_LINE_RE = re.compile(r"^- (.+?) \[(COVERED|PARTIAL|MISSING)\]$", re.MULTILINE)
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "of", "in", "on", "to", "for",
    "and", "or", "it", "its", "that", "this", "as", "by", "with", "be",
}  # fmt: skip


class MockLLMProvider(LLMProvider):
    """`response=None` (the default) makes replies content-derived rather
    than a fixed canned string — the same philosophy MockEmbeddingProvider
    already uses for vectors. Recognises three prompt shapes and answers
    each one for real rather than returning a fixed stand-in:

      - ai/concepts.py's extraction prompt (`<model_answer>` + "concepts")
        — echoes the source sentences back as concepts.
      - ai/coverage.py's check (`<concept>` + `<excerpt>` + "verdict") —
        answers from actual word overlap between the two, not a coin flip.
      - ai/feedback.py's request ("Concept coverage for this answer:" +
        "strengths") — built from the concept/status lines in the prompt.

    Anything else falls back to "{}". Thread-safe: ai.coverage.check_coverage
    (Phase B6) runs its three passes concurrently via ThreadPoolExecutor,
    and an unlocked `call_count += 1` can lose increments across threads."""

    def __init__(self, response: str | None = None):
        self.response = response
        self.call_count = 0
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def chat(self, prompt: str, *, system: str | None = None, json_mode: bool = True) -> str:
        with self._lock:
            self.call_count += 1
            self.calls.append(prompt)
        if self.response is not None:
            return self.response
        return self._auto_respond(prompt)

    def _auto_respond(self, prompt: str) -> str:
        model_answer_match = _MODEL_ANSWER_TAG_RE.search(prompt)
        if model_answer_match and '"concepts"' in prompt:
            return json.dumps({"concepts": _sentences_as_concepts(model_answer_match.group(1))})

        concept_match = _CONCEPT_TAG_RE.search(prompt)
        excerpt_match = _EXCERPT_TAG_RE.search(prompt)
        if concept_match and excerpt_match and '"verdict"' in prompt:
            verdict = _verdict_for(concept_match.group(1), excerpt_match.group(1))
            return json.dumps({"verdict": verdict})

        if "Concept coverage for this answer:" in prompt and '"strengths"' in prompt:
            return json.dumps(_feedback_for(prompt))

        return "{}"


def _sentences_as_concepts(text: str) -> list[dict]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    sentences = sentences[:CONCEPT_COUNT_MAX] or [text.strip()]
    weight = round(1 / len(sentences), 6)
    return [{"text": s, "weight": weight} for s in sentences]


def _keywords(text: str) -> set:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOPWORDS}


def _verdict_for(concept_text: str, excerpt_text: str) -> str:
    """Word-overlap heuristic — content-derived like everything else this
    mock does, not a fixed answer. Real enough that a genuinely unrelated
    excerpt reads as MISSING and a paraphrase with real term overlap reads
    as at least PARTIAL, which is what Phase B6's coverage tests need to
    hold without per-test response wiring."""
    concept_words = _keywords(concept_text)
    if not concept_words:
        return "MISSING"
    excerpt_words = _keywords(excerpt_text)
    overlap = len(concept_words & excerpt_words) / len(concept_words)
    if overlap >= 0.5:
        return "COVERED"
    if overlap >= 0.2:
        return "PARTIAL"
    return "MISSING"


def _feedback_for(prompt: str) -> dict:
    lines = _FEEDBACK_LINE_RE.findall(prompt)
    covered = [text for text, status in lines if status == "COVERED"]
    weak = [text for text, status in lines if status != "COVERED"]
    strengths = (
        "The answer clearly covers: " + "; ".join(covered) + "."
        if covered
        else "The answer engages with the question but doesn't clearly cover a scored concept."
    )
    gaps = (
        "Missing or only partially covered: " + "; ".join(weak) + "."
        if weak
        else "No concepts were missed."
    )
    suggestions = (
        f"Revisit and add detail on: {weak[0]}."
        if weak
        else "Keep reinforcing the concepts already covered with a worked example."
    )
    return {"strengths": strengths, "gaps": gaps, "suggestions": suggestions}


class MockVLMProvider(VLMProvider):
    def __init__(self, response: str = "mock vision description"):
        self.response = response
        self.call_count = 0
        self.calls: list[tuple[bytes, str]] = []

    def describe_image(self, image_bytes: bytes, prompt: str) -> str:
        self.call_count += 1
        self.calls.append((image_bytes, prompt))
        return self.response


class MockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dim: int = EMBEDDING_DIM):
        self.dim = dim
        self.call_count = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        return [self._vector_for(t) for t in texts]

    def _vector_for(self, text: str) -> list[float]:
        # crc32 keeps this stdlib-only and stable across processes/platforms —
        # same input text always seeds the same unit vector.
        seed = zlib.crc32(text.strip().lower().encode())
        rng = random.Random(seed)
        vector = [rng.uniform(-1.0, 1.0) for _ in range(self.dim)]
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]
