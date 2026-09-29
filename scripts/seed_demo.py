"""
Seeds one realistic exam end-to-end for a demo/viva: a teacher, an exam
with two questions (real concept extraction), a handful of enrolled
students, and answer sheets pushed through the REAL evaluation pipeline
(ai.pipeline, Phase B6) so the teacher review queue and student results
screens have genuine data to show, not placeholders.

Runs the pipeline functions directly (not via .delay()) so it works
without a live Celery worker — a demo seed should be a single reliable
command, not something that silently no-ops if a worker isn't running.

Usage:
    python manage.py shell -c "exec(open('scripts/seed_demo.py').read())"
    # or, with DJANGO_SETTINGS_MODULE already exported:
    python scripts/seed_demo.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django  # noqa: E402

django.setup()

from apps.accounts.models import User  # noqa: E402
from apps.evaluation.tasks import evaluate_sheet  # noqa: E402
from apps.exams.models import Exam, Question  # noqa: E402
from apps.exams.tasks import index_question_concepts  # noqa: E402
from apps.students.models import Enrollment, Student  # noqa: E402
from tests.unit.cv_fixtures import draw_strike, numbered_answer_page  # noqa: E402

TEACHER_USERNAME = "demo_teacher"
STUDENTS = [
    ("1BY22CS001", "P Charan Chandra", "charan@bmsit.in"),
    ("1BY22CS002", "R T Kesav Reddy", "kesav@bmsit.in"),
    ("1BY22CS003", "Sai Charan M M", "saicharan@bmsit.in"),
    ("1BY22CS004", "Nunna Uma Shankar", "uma@bmsit.in"),
]

QUESTIONS = [
    {
        "number": "1a",
        "text": "Define BCNF. Explain how it differs from 3NF.",
        "max_marks": 10,
        "model_answer": (
            "BCNF is a normal form for relational schemas. A relation R is in BCNF if for "
            "every non-trivial functional dependency X to Y, X must be a superkey of R. It "
            "is stricter than 3NF and removes redundancy caused by transitive dependencies "
            "that 3NF still permits."
        ),
    },
    {
        "number": "2",
        "text": "Explain deadlock prevention using wait-die and wound-wait schemes.",
        "max_marks": 10,
        "model_answer": (
            "Deadlock prevention avoids deadlocks by never letting a cycle of waiting "
            "transactions form. In wait-die, an older transaction may wait for a younger "
            "one, but a younger transaction requesting a resource held by an older one is "
            "aborted (dies). In wound-wait, an older transaction preempts (wounds) a "
            "younger one holding the resource; a younger transaction simply waits for an "
            "older one."
        ),
    },
]


def _render_demo_pages_png() -> list[bytes]:
    """One real rendered page PER question — the same rendering technique
    apps/evaluation/tests/conftest.py uses for the pytest suite, reused
    here so the demo exercises the REAL L1-L5 pipeline (segmentation,
    strike detection, OCR) exactly like a genuine upload would, not a
    canned stand-in. Separate pages, not two questions crammed onto one,
    both because that's how most real scanned submissions actually arrive
    (one photographed page per question) and because it keeps each page's
    own question-number label unambiguous for L2 segmentation to read."""
    import cv2

    from ai.ocr.tesseract_engine import extract_words
    from ai.preprocessing import to_gray

    page_1a, _ = numbered_answer_page(
        [
            (
                "1a)",
                [
                    "BCNF is a normal form for relational schemas.",
                    "A relation R is in BCNF if every determinant is a superkey.",
                ],
            )
        ]
    )

    page_2, _ = numbered_answer_page(
        [
            (
                "2)",
                [
                    "Deadlock prevention avoids deadlocks by never letting a cycle form.",
                    "In wait die an older transaction may wait for a younger one.",
                ],
            )
        ]
    )
    # One real strike mark on question 2's page — gives the L3/L3.5
    # annotation overlay something genuine to show in the demo.
    target = next(w for w in extract_words(to_gray(page_2)) if w.text == "cycle")
    draw_strike(
        page_2,
        {
            "x": int(target.bbox.x),
            "y": int(target.bbox.y),
            "w": int(target.bbox.w),
            "h": int(target.bbox.h),
        },
    )

    pages = []
    for img in (page_1a, page_2):
        ok, buf = cv2.imencode(".png", img)
        pages.append(buf.tobytes())
    return pages


def seed() -> None:
    teacher, created = User.objects.get_or_create(
        username=TEACHER_USERNAME,
        defaults={
            "role": User.Role.TEACHER,
            "full_name": "Dr Gireesh Babu C N",
            "email": "gireesh@bmsit.in",
        },
    )
    if created:
        teacher.set_password("demo-password-123")
        teacher.save()
    print(f"Teacher: {teacher.username} ({'created' if created else 'exists'})")

    exam, exam_created = Exam.objects.get_or_create(
        teacher=teacher,
        name="CIE-2 DBMS (Demo)",
        defaults={"subject": "22CS52 · DBMS", "exam_date": "2026-08-01", "total_marks": 20},
    )
    print(f"Exam: {exam.name} ({'created' if exam_created else 'exists'})")

    questions = []
    for q in QUESTIONS:
        question, q_created = Question.objects.get_or_create(
            exam=exam,
            number=q["number"],
            defaults={
                "text": q["text"],
                "max_marks": q["max_marks"],
                "model_answer": q["model_answer"],
                "model_answer_hash": Question.hash_answer(q["model_answer"]),
            },
        )
        if q_created:
            index_question_concepts(question.id)  # direct call — no worker required
            print(f"  Q{question.number}: {question.concepts.count()} concepts extracted")
        questions.append(question)

    students = []
    for usn, name, email in STUDENTS:
        student, s_created = Student.objects.get_or_create(
            usn=usn, defaults={"name": name, "email": email}
        )
        Enrollment.objects.get_or_create(exam=exam, student=student)
        students.append(student)
    print(f"Students enrolled: {len(students)}")

    sheets_created = 0
    for student in students:
        from django.core.files.base import ContentFile

        from apps.evaluation.models import AnswerSheet, SheetPage

        pages_png = _render_demo_pages_png()
        sheet, s_created = AnswerSheet.objects.get_or_create(
            exam=exam, student=student, defaults={"page_count": len(pages_png)}
        )
        if s_created:
            for i, page_png in enumerate(pages_png):
                page = SheetPage(sheet=sheet, index=i)
                page.image.save(f"page{i}.png", ContentFile(page_png), save=True)
            evaluate_sheet(sheet.id)  # direct call — runs the real L1-L8 pipeline synchronously
            sheets_created += 1
    print(f"Sheets evaluated: {sheets_created}")

    # Approve one sheet so the student-results screen has something to show.
    from apps.evaluation.models import AnswerSheet

    first_sheet = AnswerSheet.objects.filter(exam=exam, status=AnswerSheet.Status.DONE).first()
    if first_sheet:
        from django.utils import timezone

        first_sheet.status = AnswerSheet.Status.APPROVED
        first_sheet.approved_at = timezone.now()
        first_sheet.save(update_fields=["status", "approved_at"])
        print(f"Approved sheet for {first_sheet.student.usn}")

    print("\nDone. Log in as:")
    print(f"  teacher — username={TEACHER_USERNAME!r} password='demo-password-123'")
    print("  (students haven't signed up yet — their USNs above are pre-enrolled and")
    print("   ready to be claimed by signing up with the matching USN)")


if __name__ == "__main__":
    seed()
