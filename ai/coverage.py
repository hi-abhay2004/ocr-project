"""
L7 — coverage verification.

Three independent LLM passes per concept (ai.config.COVERAGE_PASS_COUNT),
run in parallel via ThreadPoolExecutor, majority-voted into one verdict.
Triple-pass, not single-pass, is what makes "how sure was the LLM"
measurable (`CoverageResult.agreement`) instead of a single opaque
answer — and it's what apps.evaluation.models.EvaluationRun exists to
keep an audit trail of, one row per pass, once Phase B6's Django glue
persists them.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ai.config import COVERAGE_PASS_COUNT
from ai.providers.base import LLMProvider
from ai.providers.retry import call_json

SYSTEM_PROMPT = (
    "You are grading one concept of a student's exam answer against a "
    "retrieved excerpt of their answer. Reply with strict JSON only — no "
    "prose, no markdown."
)

VALID_VERDICTS = ("COVERED", "PARTIAL", "MISSING")
_VERDICT_RE = re.compile(r"\b(COVERED|PARTIAL|MISSING)\b", re.IGNORECASE)


@dataclass
class CoverageVote:
    verdict: str
    raw_response: dict = field(default_factory=dict)


@dataclass
class CoverageResult:
    verdict: str  # the majority vote
    votes: list[CoverageVote]
    agreement: float  # fraction of passes agreeing with the majority, in [0, 1]


def build_prompt(concept_text: str, retrieved_text: str) -> str:
    excerpt = retrieved_text.strip() or "(nothing relevant was retrieved from the answer)"
    return (
        f"<concept>\n{concept_text.strip()}\n</concept>\n\n"
        f"<excerpt>\n{excerpt}\n</excerpt>\n\n"
        "Does the excerpt cover the concept? Reply with EXACTLY this JSON "
        'shape: {"verdict": "COVERED" | "PARTIAL" | "MISSING"}'
    )


def _single_pass(concept_text: str, retrieved_text: str, llm: LLMProvider) -> CoverageVote:
    prompt = build_prompt(concept_text, retrieved_text)
    try:
        data = call_json(llm, prompt, system=SYSTEM_PROMPT)
        verdict = str(data.get("verdict", "")).upper()
        match = _VERDICT_RE.search(verdict)
        verdict = match.group(1) if match else "MISSING"
        return CoverageVote(verdict=verdict, raw_response=data)
    except Exception:
        # Last resort: the model returned something unparseable even after
        # all retries (e.g. plain prose). Scan the raw text for a verdict
        # keyword rather than crashing the whole evaluation.
        raw = llm.chat(prompt, system=SYSTEM_PROMPT, json_mode=False)
        match = _VERDICT_RE.search(raw)
        verdict = match.group(1).upper() if match else "MISSING"
        return CoverageVote(verdict=verdict, raw_response={"raw": raw})


def check_coverage(
    concept_text: str,
    retrieved_text: str,
    llm: LLMProvider,
    *,
    pass_count: int = COVERAGE_PASS_COUNT,
) -> CoverageResult:
    with ThreadPoolExecutor(max_workers=pass_count) as pool:
        votes = list(
            pool.map(lambda _: _single_pass(concept_text, retrieved_text, llm), range(pass_count))
        )

    tally: dict[str, int] = {}
    for vote in votes:
        tally[vote.verdict] = tally.get(vote.verdict, 0) + 1
    majority = max(tally, key=tally.get)
    agreement = round(tally[majority] / len(votes), 4)
    return CoverageResult(verdict=majority, votes=votes, agreement=agreement)
