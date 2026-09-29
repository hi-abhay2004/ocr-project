import type { SheetFilters } from '@/api/exams'

/**
 * Every query key in one place — FRONTEND_PLAN §6.
 *
 * Centralised because the invalidation map is the part that goes wrong: a
 * mutation that invalidates `['sheet', id]` while the query registered
 * `['sheets', id]` fails silently, and the screen just doesn't update.
 */
export const qk = {
  me: () => ['me'] as const,

  exams: () => ['exams'] as const,
  exam: (examId: number) => ['exam', examId] as const,
  examSummary: (examId: number) => ['examSummary', examId] as const,

  questions: (examId: number) => ['questions', examId] as const,
  concepts: (questionId: number) => ['concepts', questionId] as const,

  students: (examId: number) => ['students', examId] as const,

  sheets: (examId: number, filters?: SheetFilters) => ['sheets', examId, filters ?? {}] as const,
  /** Prefix form — invalidates every filter combination of one exam's queue. */
  sheetsAll: (examId: number) => ['sheets', examId] as const,
  sheet: (sheetId: number) => ['sheet', sheetId] as const,
  sheetStatus: (sheetId: number) => ['sheetStatus', sheetId] as const,

  studentResults: () => ['studentResults'] as const,
  studentResult: (sheetId: number) => ['studentResult', sheetId] as const,
}
