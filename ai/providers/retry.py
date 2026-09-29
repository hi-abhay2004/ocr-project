"""
Bounded JSON-repair retry wrapper around LLMProvider.chat().

Providers are free-text in, free-text out on purpose (ai/providers/base.py) —
every call site that actually needs structured output (ai/concepts.py now,
ai/coverage.py + ai/feedback.py in Phase B6) goes through here instead of
each one hand-rolling its own json.loads()/except block. That turns "the
model wrapped its JSON in a markdown fence" or "the model added a sentence
of prose" into a bounded number of self-correcting re-prompts instead of a
bare exception three layers away from the LLM call.
"""

import ast
import json
import re

from .base import LLMProvider

MAX_ATTEMPTS = 3

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


class LLMJSONError(Exception):
    """Raised when a provider still hasn't returned parseable JSON after
    every retry attempt is exhausted."""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    match = _CODE_FENCE_RE.match(text)
    return match.group(1).strip() if match else text


def _parse_json(raw: str) -> dict:
    """Parse the model's reply as JSON with two fallbacks:

    1. json.loads — the normal path (model replied with valid JSON).
    2. ast.literal_eval — catches the common failure where the model
       returns Python-dict syntax with single quotes instead of double
       quotes, e.g. ``{'verdict': 'COVERED'}`` instead of
       ``{"verdict": "COVERED"}``.  ast.literal_eval is safe (no code
       execution) and handles exactly this shape.

    Both paths operate on the code-fence-stripped text so markdown
    wrappers don't interfere with either method.
    """
    text = _strip_code_fence(raw)
    # Fast path: valid JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: Python dict syntax (single-quoted keys/values).
    try:
        value = ast.literal_eval(text)
        if isinstance(value, dict):
            return value
    except (ValueError, SyntaxError):
        pass
    # If there's a JSON-like object buried in prose, extract it.
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"not valid JSON: {raw!r:.120}")


def call_json(
    llm: LLMProvider,
    prompt: str,
    *,
    system: str | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    json_mode: bool = True,
) -> dict:
    """Calls `llm.chat()` and parses the reply as JSON. On a parse failure,
    re-prompts the SAME provider with its bad output and the parse error,
    asking for a corrected reply — up to `max_attempts` total calls.

    `json_mode` is forwarded to `llm.chat()` as-is — see
    `LLMProvider.chat`'s docstring for why a caller (ai/concepts.py) might
    need it off even though it's normally a real speed win.

    Raises `LLMJSONError` if every attempt fails to parse."""
    last_error: Exception | None = None
    current_prompt = prompt

    for _ in range(max_attempts):
        raw = llm.chat(current_prompt, system=system, json_mode=json_mode)
        try:
            return _parse_json(raw)
        except ValueError as exc:
            last_error = exc
            current_prompt = (
                f"{prompt}\n\nYour previous reply was:\n{raw}\n\n"
                f"That was not valid JSON ({exc}). Reply again with ONLY "
                "valid JSON — no prose, no markdown code fences."
            )

    raise LLMJSONError(
        f"provider did not return valid JSON after {max_attempts} attempts: {last_error}"
    )
