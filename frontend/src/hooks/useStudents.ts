import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  addStudent,
  importStudents,
  listStudents,
  removeStudent,
  type StudentInput,
} from '@/api/students'
import { errorMessage } from '@/lib/axios'
import { qk } from './keys'

export function useStudents(examId: number) {
  return useQuery({
    queryKey: qk.students(examId),
    queryFn: () => listStudents(examId),
    enabled: Number.isFinite(examId),
  })
}

export function useAddStudent(examId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: StudentInput) => addStudent(examId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.students(examId) })
      toast.success('Student added')
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not add the student')),
  })
}

export function useRemoveStudent(examId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (studentId: number) => removeStudent(examId, studentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.students(examId) })
      toast.success('Student removed')
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not remove the student')),
  })
}

export function useImportStudents(examId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (rows: StudentInput[]) => importStudents(examId, rows),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: qk.students(examId) })
      toast.success(
        `Imported ${result.created} student${result.created === 1 ? '' : 's'}` +
          (result.skipped ? ` · ${result.skipped} skipped` : ''),
      )
    },
    onError: (e) => toast.error(errorMessage(e, 'Import failed')),
  })
}
