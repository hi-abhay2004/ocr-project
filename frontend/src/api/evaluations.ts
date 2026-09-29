import { api } from '@/lib/axios'
import type { QuestionEvaluation } from '@/types/api'

export interface OverrideInput {
  override_marks: number
  override_comment: string
}

/**
 * Records a teacher override. `auto_marks` is never mutated — keeping both is
 * what makes the Phase 6 agreement analysis (machine vs human) possible.
 */
export async function overrideMarks(evaluationId: number, input: OverrideInput) {
  const { data } = await api.patch<QuestionEvaluation>(`/evaluations/${evaluationId}/`, input)
  return data
}

export async function clearOverride(evaluationId: number) {
  const { data } = await api.patch<QuestionEvaluation>(`/evaluations/${evaluationId}/`, {
    override_marks: null,
    override_comment: null,
  })
  return data
}
