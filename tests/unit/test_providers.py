"""
No DB, no network, no Django settings needed — `ai/` is pure Python and these
tests prove it stays that way.
"""

import pytest

from ai.config import EMBEDDING_DIM
from ai.providers import get_embedding_provider, get_llm_provider, get_vlm_provider
from ai.providers.mock import MockEmbeddingProvider, MockLLMProvider, MockVLMProvider


def test_factory_returns_mock_by_default():
    assert isinstance(get_llm_provider("mock"), MockLLMProvider)
    assert isinstance(get_vlm_provider("mock"), MockVLMProvider)
    assert isinstance(get_embedding_provider("mock"), MockEmbeddingProvider)


def test_llm_call_counter(mock_llm):
    assert mock_llm.call_count == 0
    mock_llm.chat("extract concepts")
    mock_llm.chat("check coverage")
    assert mock_llm.call_count == 2
    assert mock_llm.calls == ["extract concepts", "check coverage"]


def test_vlm_call_counter_is_what_the_b5_cost_guard_depends_on(mock_vlm):
    # This is the exact assertion shape Phase B5 uses to prove the VLM is an
    # escalation target, not a blanket pass: 0 calls on a confident detection.
    assert mock_vlm.call_count == 0
    mock_vlm.describe_image(b"fake-crop-bytes", "describe this diagram")
    assert mock_vlm.call_count == 1


def test_embeddings_are_the_configured_dimension(mock_embedder):
    vectors = mock_embedder.embed(["a", "b"])
    assert len(vectors) == 2
    assert all(len(v) == EMBEDDING_DIM for v in vectors)


def test_embeddings_are_deterministic_and_content_derived(mock_embedder):
    v1 = mock_embedder.embed(["superkey concept"])[0]
    v2 = mock_embedder.embed(["superkey concept"])[0]
    v3 = mock_embedder.embed(["totally unrelated diagram text"])[0]

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert cosine(v1, v2) == pytest.approx(1.0)  # same text -> identical vector
    assert cosine(v1, v3) < 0.3  # unrelated text -> not similar
