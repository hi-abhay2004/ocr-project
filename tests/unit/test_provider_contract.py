"""
Provider contract tests — the same assertions run against every
implementation of an ABC, so a new provider (or a change to an existing
one) is checked against the interface the rest of the pipeline actually
relies on, not just "does it run."

The mock variants run under plain `pytest`. The NIM variants are marked
`slow` (deselected by pyproject.toml's default `addopts`) and skip
themselves if NIM_API_KEY isn't set — `pytest -m slow` with a real key
configured is what actually exercises the network path.
"""

import os

import pytest

from ai.config import EMBEDDING_DIM
from ai.providers.mock import MockEmbeddingProvider, MockLLMProvider, MockVLMProvider
from ai.providers.retry import call_json


def _require_nim_key():
    if not os.environ.get("NIM_API_KEY"):
        pytest.skip("NIM_API_KEY not set")


class EmbeddingContract:
    """Subclasses set `make_provider`."""

    def test_returns_one_vector_per_text(self):
        provider = self.make_provider()
        vectors = provider.embed(["hello world", "goodbye world"])
        assert len(vectors) == 2

    def test_vectors_are_the_configured_dimension(self):
        provider = self.make_provider()
        [vector] = provider.embed(["hello world"])
        assert len(vector) == EMBEDDING_DIM

    def test_batches_in_a_single_call(self):
        provider = self.make_provider()
        provider.embed(["a", "b", "c"])
        assert provider.call_count == 1


class TestMockEmbeddingContract(EmbeddingContract):
    @staticmethod
    def make_provider():
        return MockEmbeddingProvider()


@pytest.mark.slow
class TestNIMEmbeddingContract(EmbeddingContract):
    @staticmethod
    def make_provider():
        _require_nim_key()
        from ai.providers.nim import NIMEmbeddingProvider

        return NIMEmbeddingProvider()


class LLMJSONContract:
    """Subclasses set `make_provider`. Exercises the retry.py seam, not the
    raw provider — that is the contract every real call site depends on."""

    def test_a_well_formed_json_request_round_trips(self):
        llm = self.make_provider()
        result = call_json(
            llm,
            'Reply with exactly this JSON: {"ok": true}. No prose, no markdown.',
        )
        assert isinstance(result, dict)


class TestMockLLMJSONContract(LLMJSONContract):
    @staticmethod
    def make_provider():
        return MockLLMProvider(response='{"ok": true}')


@pytest.mark.slow
class TestNIMLLMJSONContract(LLMJSONContract):
    @staticmethod
    def make_provider():
        _require_nim_key()
        from ai.providers.nim import NIMLLMProvider

        return NIMLLMProvider()


class VLMContract:
    """Subclasses set `make_provider`."""

    def test_describe_image_returns_nonempty_text(self):
        vlm = self.make_provider()
        # A 1x1 PNG — content doesn't matter, only that the call completes
        # and returns text through the same interface every layer uses.
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
            "0000000c49444154789c63f8cfc0000003010100c9fe92ef0000000049454e44ae426082"
        )
        text = vlm.describe_image(png, "describe this image")
        assert isinstance(text, str) and text


class TestMockVLMContract(VLMContract):
    @staticmethod
    def make_provider():
        return MockVLMProvider()


@pytest.mark.slow
class TestNIMVLMContract(VLMContract):
    @staticmethod
    def make_provider():
        _require_nim_key()
        from ai.providers.nim import NIMVLMProvider

        return NIMVLMProvider()
