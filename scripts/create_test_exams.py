import os
import sys
import django
import time
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from django.contrib.auth import get_user_model
from apps.exams.models import Exam, Question
from apps.exams.tasks import index_question_concepts
from apps.students.models import Student, Enrollment

User = get_user_model()
teacher = User.objects.get(username="demo_teacher")
student, _ = Student.objects.get_or_create(usn="TEST001", defaults={"name": "Test Student"})

with open("docs/handwritten_test_cases.md", "r") as f:
    content = f.read()

tests = re.split(r'\n## Test ', content)[1:]

for i, test_content in enumerate(tests):
    title = test_content.split('\n')[0].strip()
    exam_name = f"Test {title}"
    print(f"\nProcessing: {exam_name}")
    
    # Extract Question
    q_match = re.search(r'### Question[s]?\n\n```text\n(.*?)\n```', test_content, re.DOTALL)
    if not q_match:
        print("Could not find Question text. Skipping.")
        continue
    question_text = q_match.group(1).strip()
    
    # Extract Model Answer
    a_match = re.search(r'### Model Answer\n\n```text\n(.*?)\n```', test_content, re.DOTALL)
    if not a_match:
        print("Could not find Model Answer text. Skipping.")
        continue
    model_answer = a_match.group(1).strip()
    
    # Create Exam
    exam, created = Exam.objects.get_or_create(name=exam_name, defaults={
        "subject": "Testing",
        "exam_date": "2026-09-25",
        "teacher": teacher, "total_marks": 10.0
    })
    
    Enrollment.objects.get_or_create(exam=exam, student=student)
    
    # Check if question already exists
    if Question.objects.filter(exam=exam, number="1").exists():
        print("Question 1 already exists. Skipping.")
        continue
    
    question = Question.objects.create(
        exam=exam,
        number="1",
        text=question_text[:1000],  # truncate if needed
        max_marks=10.0,
        model_answer=model_answer[:2000],
        model_answer_hash=Question.hash_answer(model_answer)
    )
    
    print("Indexing concepts...")
    index_question_concepts(question.id)
    print("Done indexing concepts. Sleeping for 15s to respect NIM rate limits...")
    time.sleep(15)

print("\nAll done!")
