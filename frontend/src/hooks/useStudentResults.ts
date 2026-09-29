import { useQuery } from '@tanstack/react-query'
import { getStudentResult, listStudentResults } from '@/api/results'
import { qk } from './keys'

export function useStudentResults() {
  return useQuery({ queryKey: qk.studentResults(), queryFn: listStudentResults })
}

export function useStudentResult(sheetId: number) {
  return useQuery({
    queryKey: qk.studentResult(sheetId),
    queryFn: () => getStudentResult(sheetId),
    enabled: Number.isFinite(sheetId),
  })
}
