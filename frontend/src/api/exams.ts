import { api } from '@/lib/axios'
import type { Exam, ExamSummary, SheetListItem } from '@/types/api'

export interface ExamInput {
  name: string
  subject: string
  exam_date: string
  total_marks: number
}

export async function listExams() {
  const { data } = await api.get<Exam[]>('/exams/')
  return data
}

export async function getExam(examId: number) {
  const { data } = await api.get<Exam>(`/exams/${examId}/`)
  return data
}

export async function createExam(input: ExamInput) {
  const { data } = await api.post<Exam>('/exams/', input)
  return data
}

export async function updateExam(examId: number, input: ExamInput) {
  const { data } = await api.patch<Exam>(`/exams/${examId}/`, input)
  return data
}

export async function deleteExam(examId: number) {
  await api.delete(`/exams/${examId}/`)
}

export interface SheetFilters {
  band?: 'RED' | 'ORANGE' | 'GREEN'
  status?: string
}

/** §3.3 — the review queue listing. */
export async function listExamSheets(examId: number, filters: SheetFilters = {}) {
  const { data } = await api.get<SheetListItem[]>(`/exams/${examId}/sheets/`, { params: filters })
  return data
}

/** §3.2 — analytics for the summary screen. */
export async function getExamSummary(examId: number) {
  const { data } = await api.get<ExamSummary>(`/exams/${examId}/summary/`)
  return data
}
