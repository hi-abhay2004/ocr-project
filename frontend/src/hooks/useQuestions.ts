import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  createQuestion,
  deleteQuestion,
  listConcepts,
  listQuestions,
  updateQuestion,
  type QuestionInput,
} from '@/api/questions'
import { errorMessage } from '@/lib/axios'
import { qk } from './keys'

export function useQuestions(examId: number) {
  return useQuery({
    queryKey: qk.questions(examId),
    queryFn: () => listQuestions(examId),
    enabled: Number.isFinite(examId),
  })
}

/**
 * Concept extraction is asynchronous (§6): the POST returns before the LLM has
 * run, so the list starts empty. Poll until something arrives, then stop.
 *
 * Without this the teacher saves a model answer, sees an empty table, and
 * concludes the feature is broken.
 *
 * The stop condition reads ONLY the concepts array itself — not a
 * `concepts_indexed` flag from the separate `questions` list query. That flag
 * is a snapshot from whenever `questions` last fetched (typically once, right
 * after the create/update mutation's invalidation) and is never re-polled; if
 * the backend's extraction task finishes after that snapshot, the flag is
 * permanently stale and a check against it would spin the skeleton forever
 * even once real concepts have arrived. The concepts array this hook already
 * fetches is authoritative and always fresh — no reason to trust a second,
 * staler source for the same fact.
 */
export function useConcepts(questionId: number) {
  return useQuery({
    queryKey: qk.concepts(questionId),
    queryFn: () => listConcepts(questionId),
    enabled: Number.isFinite(questionId),
    refetchInterval: (query) => {
      const data = query.state.data
      return data && data.length > 0 ? false : 2000
    },
  })
}

export function useCreateQuestion(examId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: QuestionInput) => createQuestion(examId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.questions(examId) })
      toast.success('Question saved — extracting concepts…')
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not save the question')),
  })
}

export function useUpdateQuestion(examId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: Partial<QuestionInput> }) =>
      updateQuestion(id, input),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: qk.questions(examId) })
      qc.invalidateQueries({ queryKey: qk.concepts(vars.id) })
      toast.success(
        vars.input.model_answer !== undefined
          ? 'Model answer saved — re-extracting concepts…'
          : 'Question updated',
      )
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not update the question')),
  })
}

export function useDeleteQuestion(examId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (questionId: number) => deleteQuestion(questionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.questions(examId) })
      toast.success('Question deleted')
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not delete the question')),
  })
}
