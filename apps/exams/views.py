from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions

from apps.accounts.permissions import IsTeacher

from .models import Concept, Exam, Question
from .serializers import ConceptSerializer, ExamSerializer, QuestionSerializer
from .tasks import index_question_concepts


class ExamListCreateView(generics.ListCreateAPIView):
    serializer_class = ExamSerializer
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get_queryset(self):
        # Scoped to the caller — a teacher must never see another teacher's
        # exam, in a list OR by guessing an id (BACKEND_PLAN.md §B2 gate).
        return Exam.objects.filter(teacher=self.request.user)

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)


class ExamDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ExamSerializer
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get_queryset(self):
        return Exam.objects.filter(teacher=self.request.user)


def _get_owned_exam(request, exam_id) -> Exam:
    """404s (not 403) for an exam that exists but isn't the caller's — a
    filtered-queryset 404 doesn't confirm to a probing teacher that the exam
    id even exists, which a 403 would."""
    return get_object_or_404(Exam, pk=exam_id, teacher=request.user)


class QuestionListCreateView(generics.ListCreateAPIView):
    serializer_class = QuestionSerializer
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get_queryset(self):
        exam = _get_owned_exam(self.request, self.kwargs["exam_id"])
        return Question.objects.filter(exam=exam)

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        exam = _get_owned_exam(self.request, self.kwargs["exam_id"])
        
        number = serializer.validated_data["number"]
        if Question.objects.filter(exam=exam, number=number).exists():
            raise ValidationError({"number": ["A question with this number already exists in this exam."]})

        question = serializer.save(
            exam=exam,
            model_answer_hash=Question.hash_answer(serializer.validated_data["model_answer"]),
        )
        index_question_concepts.delay(question.id)


class QuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = QuestionSerializer
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get_queryset(self):
        return Question.objects.filter(exam__teacher=self.request.user)

    def perform_update(self, serializer):
        from rest_framework.exceptions import ValidationError
        instance = self.get_object()
        
        new_number = serializer.validated_data.get("number")
        if new_number and new_number != instance.number:
            if Question.objects.filter(exam=instance.exam, number=new_number).exclude(id=instance.id).exists():
                raise ValidationError({"number": ["A question with this number already exists in this exam."]})

        new_answer = serializer.validated_data.get("model_answer")

        if new_answer is not None:
            new_hash = Question.hash_answer(new_answer)
            if new_hash != instance.model_answer_hash:
                # Idempotency guard (BACKEND_PLAN.md §B4 gate): only a REAL
                # change to the model answer clears the indexed concepts and
                # re-enqueues extraction. Saving the question with the answer
                # untouched (e.g. just editing max_marks) must not nuke and
                # re-embed concepts that are still valid.
                question = serializer.save(model_answer_hash=new_hash, concepts_indexed_at=None)
                Concept.objects.filter(question=question).delete()
                index_question_concepts.delay(question.id)
                return

        serializer.save()


class ConceptListView(generics.ListAPIView):
    serializer_class = ConceptSerializer
    permission_classes = [permissions.IsAuthenticated, IsTeacher]

    def get_queryset(self):
        question = get_object_or_404(
            Question, pk=self.kwargs["question_id"], exam__teacher=self.request.user
        )
        return Concept.objects.filter(question=question)
