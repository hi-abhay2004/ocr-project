"""
ai/feedback.py (L8) — three-section feedback generation.
"""

from ai.feedback import generate_feedback
from ai.providers.mock import MockLLMProvider


def test_generate_feedback_returns_the_three_sections():
    llm = MockLLMProvider(
        response='{"strengths": "Good definition.", "gaps": "Missing an example.", '
        '"suggestions": "Add a worked example."}'
    )
    result = generate_feedback([{"text": "BCNF definition", "status": "COVERED"}], llm)
    assert result == {
        "strengths": "Good definition.",
        "gaps": "Missing an example.",
        "suggestions": "Add a worked example.",
    }


def test_mock_auto_response_names_covered_concepts_as_strengths():
    llm = MockLLMProvider()
    result = generate_feedback(
        [
            {"text": "BCNF requires a superkey determinant", "status": "COVERED"},
            {"text": "Deadlock prevention schemes", "status": "MISSING"},
        ],
        llm,
    )
    assert "BCNF requires a superkey determinant" in result["strengths"]
    assert "Deadlock prevention schemes" in result["gaps"]
    assert "Deadlock prevention schemes" in result["suggestions"]


def test_mock_auto_response_handles_everything_covered():
    llm = MockLLMProvider()
    result = generate_feedback([{"text": "BCNF", "status": "COVERED"}], llm)
    assert "BCNF" in result["strengths"]
    assert result["gaps"] == "No concepts were missed."


def test_mock_auto_response_handles_nothing_covered():
    llm = MockLLMProvider()
    result = generate_feedback([{"text": "BCNF", "status": "MISSING"}], llm)
    assert "doesn't clearly cover" in result["strengths"]
    assert "BCNF" in result["gaps"]
