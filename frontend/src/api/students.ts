import { api } from '@/lib/axios'
import type { Student } from '@/types/api'

export interface StudentInput {
  usn: string
  name: string
  email: string
}

export async function listStudents(examId: number) {
  const { data } = await api.get<Student[]>(`/exams/${examId}/students/`)
  return data
}

export async function addStudent(examId: number, input: StudentInput) {
  const { data } = await api.post<Student>(`/exams/${examId}/students/`, input)
  return data
}

export async function removeStudent(examId: number, studentId: number) {
  await api.delete(`/exams/${examId}/students/${studentId}/`)
}

export interface ImportResult {
  created: number
  skipped: number
  errors: { row: number; message: string }[]
}

/** Bulk import. Rows are validated client-side first (§8 screen 5). */
export async function importStudents(examId: number, rows: StudentInput[]) {
  const { data } = await api.post<ImportResult>(`/exams/${examId}/students/import/`, { rows })
  return data
}
