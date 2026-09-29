import pytest
from django.core.files.base import ContentFile
from django.test import override_settings

from ai.ocr.vlm_extractor import ExtractedAnnotation, ExtractedBlock, ExtractedPage
from ai.providers.mock import MockEmbeddingProvider, MockLLMProvider, MockVLMProvider
from apps.evaluation import pipeline_runner
from apps.evaluation.models import AnswerSheet, SheetPage

from .conftest import render_answer_page_png

pytestmark = pytest.mark.django_db


def test_vlm_first_page_data_reaches_persisted_evaluation(
    exam, question, enrolled_student, monkeypatch
):
    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("vlm-page.png", ContentFile(render_answer_page_png()), save=True)

    def fake_extract_page(image, vlm):
        height, width = image.shape[:2]
        concept_text = "BCNF is a normal form for relational schemas."
        return ExtractedPage(
            blocks=[
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 100, "y": 50, "w": width - 200, "h": height - 100},
                    content_type="TEXT",
                    raw_text=concept_text,
                    reconstructed_text=concept_text,
                    confidence=0.9,
                    annotations=[
                        ExtractedAnnotation(
                            kind="UNDERLINE",
                            intent="EMPHASIS",
                            bbox={"x": 140, "y": 80, "w": 120, "h": 12},
                            confidence=0.88,
                        )
                    ],
                )
            ],
            confidence=0.9,
        )

    monkeypatch.setattr(pipeline_runner, "extract_page", fake_extract_page)

    with override_settings(VLM_FIRST_EXTRACTION=True):
        pipeline_runner.create_real_evaluations(
            sheet,
            [question],
            MockEmbeddingProvider(),
            MockLLMProvider(),
            MockVLMProvider(),
        )

    evaluation = sheet.evaluations.get()
    block = evaluation.blocks.get()
    annotation = block.annotations.get()

    assert evaluation.auto_marks > 0
    assert block.ocr_engine == "VLM"
    assert block.reconstructed_text == "BCNF is a normal form for relational schemas."
    assert annotation.resolved_by == "VLM"
    assert annotation.bbox == {"x": 40.0, "y": 30.0, "w": 120.0, "h": 12.0}


def test_tiny_vlm_boxes_fall_back_to_one_full_page_crop(
    exam, question, enrolled_student, monkeypatch
):
    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("tiny-vlm-boxes.png", ContentFile(render_answer_page_png()), save=True)

    def fake_extract_page(image, vlm):
        return ExtractedPage(
            blocks=[
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 0, "y": 0, "w": 100, "h": 100},
                    content_type="TEXT",
                    raw_text="first part",
                    reconstructed_text="first part",
                    confidence=0.8,
                    annotations=[
                        ExtractedAnnotation(
                            kind="STRIKE",
                            intent="CORRECTION",
                            bbox={"x": 10, "y": 10, "w": 20, "h": 10},
                            confidence=0.8,
                        )
                    ],
                ),
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 0, "y": 100, "w": 100, "h": 100},
                    content_type="TEXT",
                    raw_text="second part",
                    reconstructed_text="second part",
                    confidence=0.8,
                    annotations=[],
                ),
            ],
            confidence=0.8,
        )

    monkeypatch.setattr(pipeline_runner, "extract_page", fake_extract_page)

    with override_settings(VLM_FIRST_EXTRACTION=True):
        pipeline_runner.create_real_evaluations(
            sheet,
            [question],
            MockEmbeddingProvider(),
            MockLLMProvider(),
            MockVLMProvider(),
        )

    block = sheet.evaluations.get().blocks.get()
    annotation = block.annotations.get()
    assert (block.image_width, block.image_height) == (1200, 900)
    assert block.reconstructed_text == "first part second part"
    assert annotation.bbox == {"x": 10.0, "y": 10.0, "w": 20.0, "h": 10.0}
