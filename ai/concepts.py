"""
Concept extraction — turns a teacher's model answer into independently
gradable, weighted concepts.

BACKEND_PLAN.md Phase B4. Called from apps/exams/tasks.py's
index_question_concepts, behind the same LLMProvider seam every other layer
uses (ai/providers/base.py) — deterministic under the mock provider
(ai/providers/mock.py recognises this module's exact prompt shape and
echoes the model answer's own sentences back as concepts), real once
LLM_PROVIDER=nim.

Does not hard-fail on concept count. ai.config.CONCEPT_COUNT_MAX caps how
many concepts a request for extraction asks for; there is no MIN enforced
here — a short model answer (a one-line definition) legitimately yields
one or two gradable concepts, and that is a real answer key, not a
malformed response.
"""

from ai.config import CONCEPT_COUNT_MAX, CONCEPT_WEIGHT_TOLERANCE
from ai.providers.base import LLMProvider
from ai.providers.retry import call_json

SYSTEM_PROMPT = (
    "You are an exam-grading assistant. You extract independently gradable "
    "concepts from a model answer so each can be checked against a "
    "student's answer separately. Reply with strict JSON only — no prose, "
    "no markdown."
)


def build_prompt(question_text: str, model_answer: str) -> str:
    return (
        f"Question: {question_text.strip()}\n\n"
        f"Extract the independently gradable concepts from the model "
        f"answer below (at most {CONCEPT_COUNT_MAX}). Each concept is one "
        "fact, definition or step that a student's answer either does or "
        "does not cover — a concept must be checkable on its own, "
        "independent of the others. A single word is NOT independently "
        "checkable: splitting an acronym expansion, a term, or a short "
        "phrase into one concept per word produces concepts that can only "
        "ever be judged together, not separately, which defeats the "
        "purpose of splitting them at all. If the model answer is one "
        "short phrase, name, formula or definition with no separate facts "
        "to tell apart, that is legitimately ONE concept — do not invent "
        "extra ones to pad the count.\n\n"
        "Wrong (splits one fact into meaningless word-fragments):\n"
        '  model answer: "Hyper Text Markup Language"\n'
        '  {"concepts": [{"text": "Hyper", "weight": 0.25}, '
        '{"text": "Text", "weight": 0.25}, {"text": "Markup", "weight": 0.25}, '
        '{"text": "Language", "weight": 0.25}]}\n'
        "Right (the expansion is one checkable fact):\n"
        '  {"concepts": [{"text": "HTML stands for Hyper Text Markup Language", '
        '"weight": 1.0}]}\n\n'
        'Give each concept a "weight" — its share of the marks — so all '
        "weights sum to 1.0.\n\n"
        'Reply with EXACTLY this JSON shape: {"concepts": '
        '[{"text": "...", "weight": 0.2}, ...]}\n\n'
        f"<model_answer>\n{model_answer.strip()}\n</model_answer>"
    )


def extract_concepts(question_text: str, model_answer: str, llm: LLMProvider) -> list[dict]:
    """Returns `[{"text": str, "weight": float}, ...]` with weights
    normalised to sum to exactly 1.0 (drift from rounding is folded into the
    last concept rather than left to accumulate)."""
    prompt = build_prompt(question_text, model_answer)
    # json_mode=False: verified (2026-08-26) that at least one real provider
    # model returns a trivially-valid-but-EMPTY {"concepts": []} for this
    # open-ended list-extraction shape under strict JSON mode — see
    # LLMProvider.chat's docstring (ai/providers/base.py).
    data = call_json(llm, prompt, system=SYSTEM_PROMPT, json_mode=False)

    concepts = data.get("concepts")
    if not isinstance(concepts, list) or not concepts:
        raise ValueError(f"LLM returned no concepts: {data!r}")

    cleaned = []
    for c in concepts[:CONCEPT_COUNT_MAX]:
        text = str(c.get("text", "")).strip()
        try:
            weight = float(c.get("weight", 0))
        except (TypeError, ValueError):
            weight = 0
        if text and weight > 0:
            cleaned.append({"text": text, "weight": weight})
    if not cleaned:
        raise ValueError(f"LLM returned no usable concepts: {data!r}")

    total = sum(c["weight"] for c in cleaned)
    for c in cleaned:
        c["weight"] = round(c["weight"] / total, 6)

    drift = round(1.0 - sum(c["weight"] for c in cleaned), 6)
    if drift:
        cleaned[-1]["weight"] = round(cleaned[-1]["weight"] + drift, 6)

    assert abs(sum(c["weight"] for c in cleaned) - 1.0) <= CONCEPT_WEIGHT_TOLERANCE
    return cleaned
