from celery import shared_task
from django.utils import timezone

from ai.concepts import extract_concepts
from ai.providers import get_embedding_provider, get_llm_provider
from ai.rag.embedder import embed_texts


@shared_task
def index_question_concepts(question_id: int):
    """
    Phase B4: a real LLM call extracts independently gradable, weighted
    concepts from the model answer (ai/concepts.py), each embedded for
    later RAG retrieval (Phase B6). Runs against whatever LLM_PROVIDER
    resolves to — mock under every test and under local dev without a NIM
    key, so the frontend's "Extracting concepts..." poll
    (useConcepts in frontend/src/hooks/useQuestions.ts) always has
    something real to resolve to.
    """
    from .models import Concept, Question  # local import: avoids a circular

    question = Question.objects.select_related("exam").get(pk=question_id)

    llm = get_llm_provider()
    concepts = extract_concepts(question.text, question.model_answer, llm)

    embedder = get_embedding_provider()
    vectors = embed_texts([c["text"] for c in concepts], embedder)

    Concept.objects.filter(question=question).delete()
    Concept.objects.bulk_create(
        [
            Concept(question=question, text=c["text"], weight=c["weight"], order=i, embedding=v)
            for i, (c, v) in enumerate(zip(concepts, vectors, strict=True))
        ]
    )

    question.concepts_indexed_at = timezone.now()
    question.save(update_fields=["concepts_indexed_at"])
