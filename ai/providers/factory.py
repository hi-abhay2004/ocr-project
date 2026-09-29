"""
Provider selection by name. Reads `os.environ` directly rather than Django
settings — `ai/` has no Django imports anywhere, so it stays importable and
testable with nothing but `pytest`.

Only "mock" is wired up as of Phase B0. "nim" / "ollama" / "sbert" resolve once
their modules exist (Phase B4) — until then, selecting one raises
ModuleNotFoundError naming the missing file, which is enough to say "not built
yet" without a speculative stub class sitting unused for two phases.
"""

import os

from .base import EmbeddingProvider, LLMProvider, VLMProvider
from .mock import MockEmbeddingProvider, MockLLMProvider, MockVLMProvider


def _provider_name() -> str:
    return os.environ.get("LLM_PROVIDER", "mock").lower()


def get_llm_provider(name: str | None = None) -> LLMProvider:
    name = name or _provider_name()
    if name == "mock":
        return MockLLMProvider()
    if name == "nim":
        from .nim import NIMLLMProvider  # noqa: PLC0415 (deferred to Phase B4)

        return NIMLLMProvider()
    if name == "gemini":
        from .gemini import GeminiLLMProvider
        
        return GeminiLLMProvider()
    if name == "ollama":
        from .ollama import OllamaLLMProvider  # noqa: PLC0415

        return OllamaLLMProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {name!r}")


def get_vlm_provider(name: str | None = None) -> VLMProvider:
    name = name or _provider_name()
    if name == "mock":
        return MockVLMProvider()
    if name == "nim":
        from .nim import NIMVLMProvider  # noqa: PLC0415

        return NIMVLMProvider()
    if name == "gemini":
        from .gemini import GeminiVLMProvider
        
        return GeminiVLMProvider()
    if name == "ollama":
        from .ollama import OllamaVLMProvider  # noqa: PLC0415

        return OllamaVLMProvider()
    raise ValueError(
        f"Unknown VLM provider: {name!r} (only 'mock', 'nim', 'gemini' and 'ollama' implement vision)"
    )


def get_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    name = name or _provider_name()
    if name == "mock":
        return MockEmbeddingProvider()
    if name == "nim":
        from .nim import NIMEmbeddingProvider  # noqa: PLC0415

        return NIMEmbeddingProvider()
    if name == "gemini":
        from .gemini import GeminiEmbeddingProvider
        
        return GeminiEmbeddingProvider()
    if name == "sbert":
        from .sbert import SBERTEmbeddingProvider  # noqa: PLC0415

        return SBERTEmbeddingProvider()
    raise ValueError(f"Unknown embedding provider: {name!r}")
