"""
ai/concepts.py — real (provider-backed) concept extraction. Deterministic
under the mock provider because MockLLMProvider (ai/providers/mock.py)
recognises this module's exact prompt shape and echoes the model answer's
own sentences back — see the docstring there for why.
"""

import pytest

from ai.concepts import extract_concepts
from ai.providers.mock import MockLLMProvider

MODEL_ANSWER = (
    "BCNF is a normal form for relational schemas. A relation R is in BCNF if for every "
    "non-trivial functional dependency X to Y, X is a superkey of R. It is stricter than 3NF."
)


def test_extracts_one_concept_per_sentence_under_the_mock_provider():
    concepts = extract_concepts("Define BCNF.", MODEL_ANSWER, MockLLMProvider())
    assert len(concepts) == 3
    assert all(c["text"] for c in concepts)


def test_weights_sum_to_exactly_one():
    concepts = extract_concepts("Define BCNF.", MODEL_ANSWER, MockLLMProvider())
    assert sum(c["weight"] for c in concepts) == pytest.approx(1.0, abs=1e-6)


def test_deterministic_for_identical_input():
    a = extract_concepts("Define BCNF.", MODEL_ANSWER, MockLLMProvider())
    b = extract_concepts("Define BCNF.", MODEL_ANSWER, MockLLMProvider())
    assert a == b


def test_a_short_answer_yields_fewer_than_five_concepts_without_failing():
    # A one-sentence answer key is real, not malformed — extraction must not
    # hard-fail just because it falls below ai.config.CONCEPT_COUNT_MIN.
    concepts = extract_concepts("Name it.", "It is called BCNF.", MockLLMProvider())
    assert len(concepts) == 1
    assert concepts[0]["weight"] == pytest.approx(1.0)


def test_raises_when_the_llm_never_returns_usable_concepts():
    with pytest.raises(ValueError, match="no concepts"):
        extract_concepts("Define BCNF.", MODEL_ANSWER, MockLLMProvider(response="{}"))


def test_more_than_the_cap_is_truncated_not_rejected():
    from ai.config import CONCEPT_COUNT_MAX

    long_answer = " ".join(f"Fact number {i} is true." for i in range(20))
    concepts = extract_concepts("List facts.", long_answer, MockLLMProvider())
    assert len(concepts) == CONCEPT_COUNT_MAX
    assert sum(c["weight"] for c in concepts) == pytest.approx(1.0, abs=1e-6)
