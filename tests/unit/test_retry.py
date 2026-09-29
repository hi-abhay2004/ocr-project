"""
ai/providers/retry.py — the bounded JSON-repair wrapper every structured
LLM call site (ai/concepts.py now, coverage.py/feedback.py in Phase B6)
goes through instead of hand-rolling json.loads()/except.
"""

import pytest

from ai.providers.base import LLMProvider
from ai.providers.retry import LLMJSONError, call_json


class _ScriptedLLM(LLMProvider):
    """Returns each reply in `replies` in order, one per call — lets a test
    simulate "bad JSON, then a corrected reply" without a real provider."""

    def __init__(self, replies: list[str]):
        self.replies = replies
        self.call_count = 0
        self.prompts: list[str] = []

    def chat(self, prompt: str, *, system: str | None = None, json_mode: bool = True) -> str:
        self.prompts.append(prompt)
        reply = self.replies[min(self.call_count, len(self.replies) - 1)]
        self.call_count += 1
        return reply


def test_valid_json_parses_on_the_first_call():
    llm = _ScriptedLLM(['{"ok": true}'])
    assert call_json(llm, "prompt") == {"ok": True}
    assert llm.call_count == 1


def test_strips_a_markdown_code_fence():
    llm = _ScriptedLLM(['```json\n{"ok": true}\n```'])
    assert call_json(llm, "prompt") == {"ok": True}


def test_recovers_after_one_bad_reply():
    llm = _ScriptedLLM(["not json at all", '{"ok": true}'])
    assert call_json(llm, "prompt") == {"ok": True}
    assert llm.call_count == 2


def test_raises_after_exhausting_every_attempt():
    llm = _ScriptedLLM(["still not json"])
    with pytest.raises(LLMJSONError):
        call_json(llm, "prompt", max_attempts=3)
    assert llm.call_count == 3


def test_repair_prompt_includes_the_bad_output_and_the_original_ask():
    llm = _ScriptedLLM(["garbage", '{"ok": true}'])
    call_json(llm, "extract the concepts")
    # The second call is a repair prompt built from the first bad reply and
    # the original ask — not a bare retry of the identical original prompt.
    assert llm.prompts[0] == "extract the concepts"
    assert "extract the concepts" in llm.prompts[1]
    assert "garbage" in llm.prompts[1]
