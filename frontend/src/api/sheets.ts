import { api } from '@/lib/axios'
import type { Sheet, SheetStatusResponse } from '@/types/api'

/** Returns 202 immediately; evaluation happens in a Celery worker. */
export async function uploadSheet(
  examId: number,
  studentId: number,
  files: File[],
  onProgress?: (percent: number) => void,
) {
  const form = new FormData()
  form.append('student', String(studentId))
  files.forEach((f) => form.append('pages', f))

  const { data } = await api.post<Sheet>(`/exams/${examId}/sheets/`, form, {
    onUploadProgress: (e) => {
      if (e.total) onProgress?.(Math.round((e.loaded / e.total) * 100))
    },
  })
  return data
}

export async function getSheet(sheetId: number) {
  const { data } = await api.get<Sheet>(`/sheets/${sheetId}/`)
  return data
}

/** Deliberately lightweight — this is polled every 2 seconds (§6). */
export async function getSheetStatus(sheetId: number) {
  const { data } = await api.get<SheetStatusResponse>(`/sheets/${sheetId}/status/`)
  return data
}

export async function retrySheet(sheetId: number) {
  const { data } = await api.post<Sheet>(`/sheets/${sheetId}/retry/`)
  return data
}

/** Publishes the sheet to the student. Irreversible from the student's view. */
export async function approveSheet(sheetId: number) {
  const { data } = await api.post<Sheet>(`/sheets/${sheetId}/approve/`)
  return data
}
