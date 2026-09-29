import { api } from '@/lib/axios'
import type { Sheet, StudentResult } from '@/types/api'

/** Server-side filtered to APPROVED sheets owned by the requesting student. */
export async function listStudentResults() {
  const { data } = await api.get<StudentResult[]>('/results/')
  return data
}

/**
 * Same Sheet shape as the teacher endpoint, but the serializer omits
 * `evidence` and the raw crop URLs for students (§8 screen 12).
 */
export async function getStudentResult(sheetId: number) {
  const { data } = await api.get<Sheet>(`/results/${sheetId}/`)
  return data
}
