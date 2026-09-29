import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { clearOverride, overrideMarks, type OverrideInput } from '@/api/evaluations'
import { errorMessage } from '@/lib/axios'
import { qk } from './keys'

export function useOverrideMarks(sheetId: number, examId?: number) {
  const qc = useQueryClient()

  function invalidate() {
    qc.invalidateQueries({ queryKey: qk.sheet(sheetId) })
    if (examId !== undefined) {
      qc.invalidateQueries({ queryKey: qk.sheetsAll(examId) })
      qc.invalidateQueries({ queryKey: qk.examSummary(examId) })
    }
  }

  const save = useMutation({
    mutationFn: ({ evaluationId, input }: { evaluationId: number; input: OverrideInput }) =>
      overrideMarks(evaluationId, input),
    onSuccess: () => {
      invalidate()
      toast.success('Marks overridden')
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not save the override')),
  })

  const clear = useMutation({
    mutationFn: (evaluationId: number) => clearOverride(evaluationId),
    onSuccess: () => {
      invalidate()
      toast.success('Override removed — machine mark restored')
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not clear the override')),
  })

  return { save, clear }
}
