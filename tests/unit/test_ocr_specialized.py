"""
ai/ocr/specialized.py (L4.5) — non-text blocks skip every OCR engine and
go straight to the VLM, with a prompt suited to the classified content type.
"""

from ai.ocr.content_type import DIAGRAM, EQUATION, TABLE
from ai.ocr.specialized import VLM_SPECIALIZED, describe
from ai.providers.mock import MockVLMProvider
from tests.unit.cv_fixtures import blank_page, to_binary


def test_describe_calls_the_vlm_exactly_once_and_tags_the_engine():
    binary = to_binary(blank_page(200, 150))
    vlm = MockVLMProvider(response="A rectangle labelled STUDENT joined to COURSE by 'enrols'.")
    result = describe(binary, DIAGRAM, vlm)
    assert vlm.call_count == 1
    assert result.engine == VLM_SPECIALIZED
    assert result.confidence == 1.0
    assert "STUDENT" in result.text


def test_different_content_types_use_different_prompts():
    binary = to_binary(blank_page(200, 150))
    vlm = MockVLMProvider(response="ok")

    describe(binary, DIAGRAM, vlm)
    describe(binary, TABLE, vlm)
    describe(binary, EQUATION, vlm)

    prompts = [call[1] for call in vlm.calls]
    assert len(set(prompts)) == 3  # each content type got its own prompt


def test_an_unrecognised_content_type_falls_back_to_the_diagram_prompt():
    from ai.ocr.specialized import _PROMPTS

    binary = to_binary(blank_page(200, 150))
    vlm = MockVLMProvider(response="ok")
    describe(binary, "SOMETHING_UNKNOWN", vlm)
    assert vlm.calls[0][1] == _PROMPTS[DIAGRAM]
