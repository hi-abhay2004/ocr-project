import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  createExam,
  deleteExam,
  getExam,
  getExamSummary,
  listExamSheets,
  listExams,
  updateExam,
  type ExamInput,
  type SheetFilters,
} from '@/api/exams'
import { errorMessage } from '@/lib/axios'
import { qk } from './keys'

export function useExams() {
  return useQuery({ queryKey: qk.exams(), queryFn: listExams })
}

export function useExam(examId: number) {
  return useQuery({
    queryKey: qk.exam(examId),
    queryFn: () => getExam(examId),
    enabled: Number.isFinite(examId),
  })
}

export function useCreateExam() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: ExamInput) => createExam(input),
    onSuccess: (exam) => {
      qc.invalidateQueries({ queryKey: qk.exams() })
      toast.success(`Exam "${exam.name}" created`)
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not create the exam')),
  })
}

export function useUpdateExam(examId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: ExamInput) => updateExam(examId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.exams() })
      qc.invalidateQueries({ queryKey: qk.exam(examId) })
      toast.success('Exam updated')
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not update the exam')),
  })
}

export function useDeleteExam() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (examId: number) => deleteExam(examId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.exams() })
      toast.success('Exam deleted')
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not delete the exam')),
  })
}

export function useExamSheets(examId: number, filters: SheetFilters = {}) {
  return useQuery({
    queryKey: qk.sheets(examId, filters),
    queryFn: () => listExamSheets(examId, filters),
    enabled: Number.isFinite(examId),
  })
}

export function useExamSummary(examId: number) {
  return useQuery({
    queryKey: qk.examSummary(examId),
    queryFn: () => getExamSummary(examId),
    enabled: Number.isFinite(examId),
  })
}
