import hashlib

from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from ai.config import EMBEDDING_DIM


class Exam(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exams"
    )
    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=100)
    exam_date = models.DateField()
    total_marks = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.teacher.username})"


class Question(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    number = models.CharField(max_length=10)  # "1a", "2", "3b" — not an int, sub-parts are normal
    text = models.TextField()
    max_marks = models.DecimalField(max_digits=5, decimal_places=2)
    model_answer = models.TextField()
    # sha256 of model_answer — the idempotency guard: re-saving unchanged text
    # must not re-trigger concept extraction (BACKEND_PLAN.md §B4 gate).
    model_answer_hash = models.CharField(max_length=64, blank=True, default="")
    # Null until index_question_concepts finishes — the frontend polls
    # GET /questions/{id}/concepts/ until this is non-null and non-empty.
    concepts_indexed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "number"], name="unique_question_number_per_exam"
            )
        ]

    def __str__(self):
        return f"Q{self.number} — {self.exam.name}"

    @staticmethod
    def hash_answer(text: str) -> str:
        return hashlib.sha256(text.strip().encode()).hexdigest()


class Concept(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="concepts")
    text = models.TextField()
    # Normalised so all concepts of one question sum to 1.0 ± ai.config.CONCEPT_WEIGHT_TOLERANCE.
    weight = models.FloatField()
    order = models.PositiveSmallIntegerField(default=0)
    # No ivfflat/hnsw index: both pgvector index types cap out at 2000
    # dimensions, and the working embedding model (see ai/providers/nim.py,
    # 2026-08-26) is 2048-dim. Not a real loss — the actual similarity
    # query has always run in pure Python (ai/rag/store.py's cosine_similarity
    # / top_k over a per-evaluation candidate list, not a Postgres `<=>`
    # query against this column), so there was never a live query path
    # this index accelerated. A future move to real in-DB ANN search would
    # need a sub-2000-dim embedding model.
    embedding = VectorField(dimensions=EMBEDDING_DIM)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.text[:40]} (w={self.weight:.2f})"
