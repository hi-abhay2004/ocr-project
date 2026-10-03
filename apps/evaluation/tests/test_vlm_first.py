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
    annotations = list(block.annotations.all())

    assert evaluation.auto_marks > 0
    assert block.ocr_engine == "VLM"
    assert block.reconstructed_text == "BCNF is a normal form for relational schemas."

    vlm_annotation = next(a for a in annotations if a.resolved_by == "VLM")
    assert vlm_annotation.bbox == {"x": 40.0, "y": 30.0, "w": 120.0, "h": 12.0}

    # render_answer_page_png() (conftest.py) also draws a real struck-out
    # word into this page that the mocked VLM response above never
    # reports. pipeline_runner._cv_assist_annotations is scoped to
    # UNDERLINE only (live-verified 2026-10-04: STRIKE/ARROW stayed noisy
    # enough on real photos to mislead a teacher) — so unlike underline,
    # this real strike should NOT get backfilled. Confirms the scope
    # boundary, not just that CV assist exists.
    assert len(annotations) == 1


def test_cv_assist_finds_a_real_underline_the_vlm_missed(
    exam, question, enrolled_student, monkeypatch
):
    import cv2

    from tests.unit.cv_fixtures import clean_answer_block, draw_underline

    # One clean line with nothing below it — draw_underline() places the
    # line just below the text's own ink, and a nearby descender (e.g. a
    # 'y' in an adjacent word) can leave enough ink in the "below" sampling
    # window to tip strikethrough.py's "ink both sides" score above
    # underline.py's "blank below" score for the exact same drawn line
    # (verified directly, 2026-10-04) — a single isolated line avoids that
    # entirely and is what real underline.py/strikethrough.py unit tests
    # already use for the same reason.
    img, boxes = clean_answer_block(["BCNF removes redundancy from design."])
    draw_underline(img, boxes[0])
    ok, buf = cv2.imencode(".png", img)

    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("underlined-page.png", ContentFile(buf.tobytes()), save=True)

    def fake_extract_page(image, vlm):
        height, width = image.shape[:2]
        concept_text = "BCNF is a normal form for relational schemas."
        return ExtractedPage(
            blocks=[
                ExtractedBlock(
                    # Full image, not inset — this fixture is already
                    # tightly cropped to its own content (unlike the
                    # generous-margin full-page fixtures elsewhere in this
                    # file), so an inset bbox here would crop the drawn
                    # underline right back out before CV assist ever sees it.
                    question_number="1a",
                    bbox={"x": 0, "y": 0, "w": width, "h": height},
                    content_type="TEXT",
                    raw_text=concept_text,
                    reconstructed_text=concept_text,
                    confidence=0.9,
                    annotations=[],
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

    annotation = sheet.evaluations.get().blocks.get().annotations.get()
    assert annotation.kind == "UNDERLINE"
    assert annotation.resolved_by == "CV"


def test_cv_assist_is_skipped_entirely_on_a_block_with_a_fraction(
    exam, question, enrolled_student, monkeypatch
):
    # Live bug (2026-10-06): a real page with "Precision = TP/(TP+FP)"
    # scored its own fraction bars as confident (0.84, 0.88) CV underline
    # candidates — ink-above/blank-below over the numerator is exactly a
    # real underline's shape too, geometrically indistinguishable. This
    # fixture reuses the SAME real underline the two tests above rely on
    # (so a real mark genuinely IS present and geometrically detectable),
    # but with raw_text containing a LaTeX fraction — confirming the
    # block-level math-notation gate suppresses CV-assist entirely rather
    # than trying to tell a real underline apart from a fraction bar
    # candidate-by-candidate.
    import cv2

    from tests.unit.cv_fixtures import clean_answer_block, draw_underline

    img, boxes = clean_answer_block(["BCNF removes redundancy from design."])
    draw_underline(img, boxes[0])
    ok, buf = cv2.imencode(".png", img)

    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("fraction-block-page.png", ContentFile(buf.tobytes()), save=True)

    def fake_extract_page(image, vlm):
        height, width = image.shape[:2]
        raw_text = r"Precision = \frac{TP}{(TP + FP)}"
        return ExtractedPage(
            blocks=[
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 0, "y": 0, "w": width, "h": height},
                    content_type="TEXT",
                    raw_text=raw_text,
                    reconstructed_text=raw_text,
                    confidence=0.9,
                    annotations=[],
                    underlined_words=[],
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

    # No annotation at all: the real underline CV would otherwise have
    # found (proven by the test above, same fixture) is suppressed
    # because this block's own text looks like a formula.
    assert sheet.evaluations.get().blocks.get().annotations.count() == 0


def test_cv_assists_precise_bbox_replaces_gemini_imprecise_one_for_underline(
    exam, question, enrolled_student, monkeypatch
):
    import cv2

    from tests.unit.cv_fixtures import clean_answer_block, draw_underline

    # Same real underline as the test above (CV finds it at roughly
    # x=37,y=73,w=713,h=4 — verified directly). This time Gemini ALSO
    # reports an underline for the same word, but — live-verified
    # (2026-10-05): Gemini can correctly identify that a mark exists while
    # still drawing its box visibly offset from the real word — at a
    # nearby but imprecise position (y=70 instead of y=73, taller than
    # the real line). CV's box should win: it comes from Hough line
    # detection directly against the ink, not a vision model's pixel
    # estimate.
    img, boxes = clean_answer_block(["BCNF removes redundancy from design."])
    draw_underline(img, boxes[0])
    ok, buf = cv2.imencode(".png", img)

    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("imprecise-underline-page.png", ContentFile(buf.tobytes()), save=True)

    def fake_extract_page(image, vlm):
        height, width = image.shape[:2]
        concept_text = "BCNF is a normal form for relational schemas."
        return ExtractedPage(
            blocks=[
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 0, "y": 0, "w": width, "h": height},
                    content_type="TEXT",
                    raw_text=concept_text,
                    reconstructed_text=concept_text,
                    confidence=0.9,
                    annotations=[
                        ExtractedAnnotation(
                            kind="UNDERLINE",
                            intent="EMPHASIS",
                            bbox={"x": 37, "y": 70, "w": 713, "h": 10},
                            confidence=0.8,
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

    annotations = list(sheet.evaluations.get().blocks.get().annotations.all())
    assert len(annotations) == 1
    annotation = annotations[0]
    assert annotation.resolved_by == "CV"
    assert annotation.bbox["y"] != 70  # Gemini's offset guess didn't survive
    assert 71 <= annotation.bbox["y"] <= 75  # CV's real, precise position


def _marginal_underline_page():
    """A real underline whose own CV confidence lands around 0.50 (below
    ANNOTATION_AMBIGUITY_THRESHOLD) — verified directly, 2026-10-04/05: a
    descender in "redundancy" leaves just enough ink in underline.py's
    "below" sampling window that its score stays marginal even though the
    line really is a genuine, correctly-drawn underline under that word."""
    from tests.unit.cv_fixtures import draw_underline, numbered_answer_page

    img, _layout = numbered_answer_page(
        [
            (
                "1a)",
                [
                    "BCNF is a normal form for relational schemas.",
                    "It removes redundancy from the schema design.",
                ],
            )
        ]
    )
    draw_underline(img, {"x": 234, "y": 136, "w": 194, "h": 34})
    return img


def test_underlined_words_rescues_a_marginal_cv_candidate(
    exam, question, enrolled_student, monkeypatch
):
    import cv2

    ok, buf = cv2.imencode(".png", _marginal_underline_page())

    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("marginal-underline-page.png", ContentFile(buf.tobytes()), save=True)

    def fake_extract_page(image, vlm):
        height, width = image.shape[:2]
        concept_text = (
            "BCNF is a normal form for relational schemas. "
            "It removes redundancy from the schema design."
        )
        return ExtractedPage(
            blocks=[
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 0, "y": 0, "w": width, "h": height},
                    content_type="TEXT",
                    raw_text=concept_text,
                    reconstructed_text=concept_text,
                    confidence=0.9,
                    annotations=[],
                    # Gemini read the text and said this word is
                    # underlined — it never estimated a pixel position.
                    underlined_words=["redundancy"],
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

    annotation = sheet.evaluations.get().blocks.get().annotations.get()
    assert annotation.kind == "UNDERLINE"
    assert annotation.resolved_by == "CV"


def test_no_underlined_words_means_the_marginal_candidate_stays_dropped(
    exam, question, enrolled_student, monkeypatch
):
    # Same marginal (~0.50 confidence) real underline as the test above —
    # this time Gemini's underlined_words doesn't mention the word, so
    # there's no corroboration and the candidate should stay dropped, same
    # as before this feature existed. Confirms this isn't just a lowered
    # threshold for everyone.
    import cv2

    ok, buf = cv2.imencode(".png", _marginal_underline_page())

    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("marginal-underline-no-match.png", ContentFile(buf.tobytes()), save=True)

    def fake_extract_page(image, vlm):
        height, width = image.shape[:2]
        concept_text = (
            "BCNF is a normal form for relational schemas. "
            "It removes redundancy from the schema design."
        )
        return ExtractedPage(
            blocks=[
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 0, "y": 0, "w": width, "h": height},
                    content_type="TEXT",
                    raw_text=concept_text,
                    reconstructed_text=concept_text,
                    confidence=0.9,
                    annotations=[],
                    underlined_words=[],
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

    assert sheet.evaluations.get().blocks.get().annotations.count() == 0


def test_cv_corrects_a_genuine_underline_gemini_mislabelled_as_strike(
    exam, question, enrolled_student, monkeypatch
):
    # Live bug (2026-10-06): one real page came back with 5 genuine
    # underlines, all correctly positioned, but several mislabelled
    # STRIKE instead of UNDERLINE in Gemini's own JSON — a semantic
    # mix-up (which word, not where). underline.py/strikethrough.py
    # measure the SAME line for opposite shapes (ink-above-only vs
    # ink-both-sides); whichever one actually matches the real ink wins,
    # regardless of what Gemini claimed.
    import cv2

    from tests.unit.cv_fixtures import clean_answer_block, draw_underline

    img, boxes = clean_answer_block(["BCNF removes redundancy from design."])
    draw_underline(img, boxes[0])  # a REAL underline — ink above, blank below
    ok, buf = cv2.imencode(".png", img)

    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("mislabelled-strike-page.png", ContentFile(buf.tobytes()), save=True)

    def fake_extract_page(image, vlm):
        height, width = image.shape[:2]
        concept_text = "BCNF is a normal form for relational schemas."
        return ExtractedPage(
            blocks=[
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 0, "y": 0, "w": width, "h": height},
                    content_type="TEXT",
                    raw_text=concept_text,
                    reconstructed_text=concept_text,
                    confidence=0.9,
                    annotations=[
                        ExtractedAnnotation(
                            # Gemini's own bbox for the real underline
                            # above, but mislabelled STRIKE.
                            kind="STRIKE",
                            intent="CORRECTION",
                            bbox={"x": 37, "y": 73, "w": 713, "h": 4},
                            confidence=0.9,
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

    annotation = sheet.evaluations.get().blocks.get().annotations.get()
    assert annotation.kind == "UNDERLINE"
    assert annotation.intent == "EMPHASIS"
    assert annotation.resolved_by == "CV"


def test_cv_does_not_flip_a_genuinely_correct_strike_label(
    exam, question, enrolled_student, monkeypatch
):
    # Negative control for the test above: a REAL strike, correctly
    # labelled STRIKE by Gemini, must NOT get relabelled just because
    # this feature now exists.
    import cv2

    from tests.unit.cv_fixtures import clean_answer_block, draw_strike

    img, boxes = clean_answer_block(["BCNF removes redundancy from design."])
    draw_strike(img, boxes[0])  # a REAL strike — ink both above and below
    ok, buf = cv2.imencode(".png", img)

    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("genuine-strike-page.png", ContentFile(buf.tobytes()), save=True)

    def fake_extract_page(image, vlm):
        height, width = image.shape[:2]
        concept_text = "BCNF is a normal form for relational schemas."
        return ExtractedPage(
            blocks=[
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 0, "y": 0, "w": width, "h": height},
                    content_type="TEXT",
                    raw_text=concept_text,
                    reconstructed_text=concept_text,
                    confidence=0.9,
                    annotations=[
                        ExtractedAnnotation(
                            kind="STRIKE",
                            intent="CORRECTION",
                            bbox={"x": 37, "y": 54, "w": 713, "h": 4},
                            confidence=0.9,
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

    annotation = sheet.evaluations.get().blocks.get().annotations.get()
    assert annotation.kind == "STRIKE"
    assert annotation.resolved_by == "VLM"


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


def test_several_text_blocks_for_one_question_on_one_page_merge_into_one_block(
    exam, question, enrolled_student, monkeypatch
):
    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("sliced-vlm-blocks.png", ContentFile(render_answer_page_png()), save=True)

    def fake_extract_page(image, vlm):
        # Each block is well above the "suspicious tiny box" area cutoff
        # on its own (400*60=24000 > 1200*900*0.02=21600), so this stays
        # on the normal merge path, not the full-page fallback.
        return ExtractedPage(
            blocks=[
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 100, "y": 50, "w": 400, "h": 60},
                    content_type="TEXT",
                    raw_text="first line",
                    reconstructed_text="first line",
                    confidence=0.9,
                    annotations=[
                        ExtractedAnnotation(
                            kind="UNDERLINE",
                            intent="EMPHASIS",
                            bbox={"x": 120, "y": 60, "w": 80, "h": 6},
                            confidence=0.9,
                        )
                    ],
                ),
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 100, "y": 120, "w": 400, "h": 60},
                    content_type="TEXT",
                    raw_text="second line",
                    reconstructed_text="second line",
                    confidence=0.85,
                    annotations=[],
                ),
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 100, "y": 190, "w": 400, "h": 60},
                    content_type="TEXT",
                    raw_text="third line",
                    reconstructed_text="third line",
                    confidence=0.95,
                    annotations=[],
                ),
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

    # Three thin strips Gemini sliced one answer into collapse into ONE
    # AnswerBlock — see pipeline_runner._merge_text_blocks's docstring for
    # the live bug this fixes (reported 2026-10-04: a single short
    # paragraph came back as 6 separately-boxed blocks, rendering as 6
    # stacked thin image strips instead of one coherent answer).
    blocks = list(sheet.evaluations.get().blocks.all())
    assert len(blocks) == 1
    block = blocks[0]
    assert block.reconstructed_text == "first line second line third line"
    assert block.image_width == 400  # union of the three blocks' own x-range
    # Height extends to the page bottom (900, render_answer_page_png()'s
    # fixed size), not just to the union of the three blocks' own claimed
    # heights (which would be 200) — see _merge_text_blocks's docstring for
    # why an individual block's own height can't be trusted as a lower
    # bound; there's no second question on this page to cap it sooner.
    assert block.image_height == 900 - 50
    annotation = block.annotations.get()
    assert annotation.kind == "UNDERLINE"


def test_merge_stops_at_the_next_questions_own_top_on_the_same_page(
    exam, question, enrolled_student, monkeypatch
):
    from apps.exams.models import Question

    question2 = Question.objects.create(
        exam=exam, number="2", text="Define 3NF.", max_marks=5, model_answer="3NF text."
    )

    sheet = AnswerSheet.objects.create(exam=exam, student=enrolled_student, page_count=1)
    page = SheetPage(sheet=sheet, index=0)
    page.image.save("two-question-page.png", ContentFile(render_answer_page_png()), save=True)

    def fake_extract_page(image, vlm):
        # Live bug (2026-10-04): Gemini transcribed a longer answer's text
        # completely correctly across several blocks, but one block's own
        # reported height undershot how much of the page it actually
        # covered — text right, geometry wrong (confirmed: an identical
        # extraction call moments later produced different, correct
        # bboxes for the same image). A tight union of these two blocks'
        # own claimed heights would end at y=160, well short of where
        # Q2's real content actually starts (y=400) — the merge should
        # extend down to Q2's own top instead of trusting that union.
        return ExtractedPage(
            blocks=[
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 100, "y": 50, "w": 400, "h": 60},
                    content_type="TEXT",
                    raw_text="q1 first line",
                    reconstructed_text="q1 first line",
                    confidence=0.9,
                    annotations=[],
                ),
                ExtractedBlock(
                    question_number="1a",
                    bbox={"x": 100, "y": 120, "w": 400, "h": 40},
                    content_type="TEXT",
                    raw_text="q1 second line",
                    reconstructed_text="q1 second line",
                    confidence=0.85,
                    annotations=[],
                ),
                ExtractedBlock(
                    question_number="2",
                    bbox={"x": 100, "y": 400, "w": 400, "h": 60},
                    content_type="TEXT",
                    raw_text="q2 answer",
                    reconstructed_text="q2 answer",
                    confidence=0.9,
                    annotations=[],
                ),
            ],
            confidence=0.9,
        )

    monkeypatch.setattr(pipeline_runner, "extract_page", fake_extract_page)

    with override_settings(VLM_FIRST_EXTRACTION=True):
        pipeline_runner.create_real_evaluations(
            sheet,
            [question, question2],
            MockEmbeddingProvider(),
            MockLLMProvider(),
            MockVLMProvider(),
        )

    q1_block = sheet.evaluations.get(question_number="1a").blocks.get()
    assert q1_block.reconstructed_text == "q1 first line q1 second line"
    # Extends to Q2's own top (y=400), not to the page bottom (900) and
    # not to the two blocks' own too-short union (would be 160-50=110).
    assert q1_block.image_height == 400 - 50
