"""
Provider ABCs — the seam the whole pipeline is built behind.

Every layer that needs an LLM, a vision model or an embedding calls one of
these three interfaces, never a concrete SDK. That is what makes:

  - CI provider-free (mock.py implements all three, deterministically)
  - a provider swap (NIM -> Ollama, or a dimension change) a one-file change
  - the cost-guard tests in Phase B5 possible at all (`mock_vlm.call_count`)

`ai/` has no Django imports anywhere, including here — it must be importable
and testable with nothing but `pytest`, no DJANGO_SETTINGS_MODULE required.
"""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Text-in, text-out. Callers are responsible for parsing/repairing JSON
    (see ai/providers/retry.py, Phase B4) — this interface stays a thin string
    boundary so mock.py can return canned strings with zero JSON-shape coupling."""

    @abstractmethod
    def chat(self, prompt: str, *, system: str | None = None, json_mode: bool = True) -> str:
        """Single-turn completion. Returns raw text.

        `json_mode` asks a real provider to use the API's own strict-JSON
        response mode when it has one — a real latency win normally (see
        ai/providers/nim.py), but not safe to force everywhere: verified
        (2026-08-26) that NIM's currently-working small model returns a
        trivially-valid-but-EMPTY JSON object for concept extraction's
        open-ended "generate a list of items" shape under strict JSON mode,
        while the exact same prompt works correctly without it — a known
        failure pattern of grammar-constrained decoding on variable-length
        array generation, not something retry.py's parse-repair can detect
        (the empty response IS valid JSON). ai/concepts.py sets this False;
        every other real call site (fixed-shape objects: one verdict, one
        feedback record) leaves it at the default.
        """
        raise NotImplementedError


class VLMProvider(ABC):
    """Image-in, text-out. Used at exactly three call sites (L3.5, L4, L4.5) —
    see PLAN_OF_ACTION_V2.md §5 "Where the VLM is used"."""

    @abstractmethod
    def describe_image(self, image_bytes: bytes, prompt: str) -> str:
        """Returns the model's text response to `prompt` about the given image."""
        raise NotImplementedError


class EmbeddingProvider(ABC):
    """Text-in, vector-out, batched. The returned vectors must be exactly
    `ai.config.EMBEDDING_DIM` long — every implementation is responsible for
    its own dimension, mock included, so a provider swap can never silently
    produce vectors pgvector's VectorField(EMBEDDING_DIM) rejects at insert
    time instead of at call time."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError
