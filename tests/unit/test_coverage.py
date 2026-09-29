"""
ai/coverage.py (L7) — triple-pass voting and agreement.
"""

import threading

from ai.config import COVERAGE_PASS_COUNT
from ai.coverage import check_coverage
from ai.providers.base import LLMProvider
from ai.providers.mock import MockLLMProvider


class _ScriptedLLM(LLMProvider):
    """Returns each scripted reply exactly once, across however many
    threads call it concurrently (ai.coverage.check_coverage runs all
    three passes via ThreadPoolExecutor) — a lock around the counter is
    what keeps "2 COVERED, 1 MISSING" an exact, deterministic distribution
    instead of a race between threads reading the same unlocked index."""

    def __init__(self, replies: list[str]):
        self.replies = replies
        self.call_count = 0
        self._lock = threading.Lock()

    def chat(self, prompt: str, *, system: str | None = None, json_mode: bool = True) -> str:
        with self._lock:
            reply = self.replies[self.call_count % len(self.replies)]
            self.call_count += 1
        return reply


def test_unanimous_votes_agree_completely():
    llm = _ScriptedLLM(['{"verdict": "COVERED"}'] * 3)
    result = check_coverage("BCNF", "some excerpt", llm)
    assert result.verdict == "COVERED"
    assert result.agreement == 1.0
    assert len(result.votes) == COVERAGE_PASS_COUNT


def test_majority_vote_wins_with_partial_agreement():
    llm = _ScriptedLLM(
        ['{"verdict": "COVERED"}', '{"verdict": "COVERED"}', '{"verdict": "MISSING"}']
    )
    result = check_coverage("BCNF", "some excerpt", llm)
    assert result.verdict == "COVERED"
    assert result.agreement == round(2 / 3, 4)


def test_makes_exactly_three_llm_calls():
    llm = _ScriptedLLM(['{"verdict": "PARTIAL"}'])
    check_coverage("BCNF", "some excerpt", llm)
    assert llm.call_count == COVERAGE_PASS_COUNT


def test_an_unrecognised_verdict_string_falls_back_to_missing():
    llm = _ScriptedLLM(['{"verdict": "MAYBE"}'] * 3)
    result = check_coverage("BCNF", "some excerpt", llm)
    assert result.verdict == "MISSING"


def test_mock_provider_word_overlap_reads_a_covering_excerpt_as_covered():
    llm = MockLLMProvider()
    result = check_coverage(
        "BCNF requires every determinant to be a superkey",
        "A relation is in BCNF if every determinant is a superkey of the relation.",
        llm,
    )
    assert result.verdict == "COVERED"


def test_mock_provider_word_overlap_reads_an_unrelated_excerpt_as_missing():
    llm = MockLLMProvider()
    result = check_coverage(
        "Deadlock prevention uses wait-die and wound-wait schemes",
        "The cat sat on the mat in the garden.",
        llm,
    )
    assert result.verdict == "MISSING"


def test_no_retrieved_text_at_all_is_handled_without_crashing():
    llm = MockLLMProvider()
    result = check_coverage("BCNF requires every determinant to be a superkey", "", llm)
    assert result.verdict == "MISSING"
