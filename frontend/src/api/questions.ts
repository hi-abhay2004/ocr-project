import { api } from '@/lib/axios'
import type { Concept, Question } from '@/types/api'

export interface QuestionInput {
  number: string
  text: string
  max_marks: number
  model_answer: string
}

export async function listQuestions(examId: number) {
  const { data } = await api.get<Question[]>(`/exams/${examId}/questions/`)
  return data
}

export async function createQuestion(examId: number, input: QuestionInput) {
  const { data } = await api.post<Question>(`/exams/${examId}/questions/`, input)
  return data
}

/**
 * Saving a model answer re-enqueues concept extraction + embedding for that
 * question, which invalidates every stored ConceptScore derived from the old
 * concepts. The UI warns before calling this (§8 screen 4).
 */
export async function updateQuestion(questionId: number, input: Partial<QuestionInput>) {
  const { data } = await api.patch<Question>(`/questions/${questionId}/`, input)
  return data
}

export async function deleteQuestion(questionId: number) {
  await api.delete(`/questions/${questionId}/`)
}

/** Empty until the Celery extraction task finishes — the UI polls this (§6). */
export async function listConcepts(questionId: number) {
  const { data } = await api.get<Concept[]>(`/questions/${questionId}/concepts/`)
  return data
}
