"""
L8 — feedback generation.

One LLM call per question, given its concept-by-concept coverage results,
produces three short sections — what the answer did well, what's missing,
and one concrete suggestion. These map directly onto
apps.evaluation.models.Evaluation.feedback_{strengths,gaps,suggestions}.
"""

from ai.providers.base import LLMProvider
from ai.providers.retry import call_json

SYSTEM_PROMPT = (
    "You are giving a student feedback on one exam answer, based on which "
    "concepts from the model answer their response covered, partially "
    "covered, or missed. Be specific and concise. Reply with strict JSON "
    "only — no prose, no markdown."
)


def build_prompt(concept_results: list[dict]) -> str:
    lines = [f"- {c['text']} [{c['status']}]" for c in concept_results]
    return (
        "Concept coverage for this answer:\n" + "\n".join(lines) + "\n\n"
        'Reply with EXACTLY this JSON shape: {"strengths": "...", '
        '"gaps": "...", "suggestions": "..."} — each one or two short '
        "sentences, addressed to the student."
    )


def generate_feedback(concept_results: list[dict], llm: LLMProvider) -> dict:
    """`concept_results` is `[{"text": str, "status": "COVERED"|"PARTIAL"|"MISSING"}, ...]`."""
    prompt = build_prompt(concept_results)
    try:
        data = call_json(llm, prompt, system=SYSTEM_PROMPT)
        return {
            "strengths": str(data.get("strengths", "")).strip(),
            "gaps": str(data.get("gaps", "")).strip(),
            "suggestions": str(data.get("suggestions", "")).strip(),
        }
    except Exception:
        # Feedback is best-effort — if the model keeps returning unparseable
        # output, return empty strings so grading still completes rather than
        # failing the whole evaluation at the last step.
        return {"strengths": "", "gaps": "", "suggestions": ""}
