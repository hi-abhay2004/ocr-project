import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { approveSheet, getSheet, getSheetStatus, retrySheet, uploadSheet } from '@/api/sheets'
import { errorMessage } from '@/lib/axios'
import { TERMINAL_STATUSES, type SheetStatus } from '@/types/api'
import { qk } from './keys'

export function useSheet(sheetId: number) {
  return useQuery({
    queryKey: qk.sheet(sheetId),
    queryFn: () => getSheet(sheetId),
    enabled: Number.isFinite(sheetId),
  })
}

function isTerminal(status: SheetStatus | undefined) {
  return !!status && TERMINAL_STATUSES.includes(status)
}

/**
 * The 2-second poller — FRONTEND_PLAN §6.
 *
 * Two things this must get right:
 *
 * 1. STOP on a terminal status. `refetchInterval` returning false is what ends
 *    it. A poller that never stops keeps hitting the API for every sheet the
 *    teacher has ever opened — the classic bug on this screen.
 * 2. INVALIDATE on the RUNNING → DONE edge, so the finished result appears
 *    without a manual refresh. Polling `/status/` alone only updates the
 *    lightweight status object; the full `/sheets/{id}/` payload is a separate
 *    cache entry and would otherwise stay stale.
 */
export function useSheetStatus(sheetId: number | null, examId?: number) {
  const qc = useQueryClient()
  const previous = useRef<SheetStatus | null>(null)

  const query = useQuery({
    queryKey: qk.sheetStatus(sheetId ?? -1),
    queryFn: () => getSheetStatus(sheetId!),
    enabled: sheetId !== null,
    refetchInterval: (q) => (isTerminal(q.state.data?.status) ? false : 2000),
  })

  const status = query.data?.status

  useEffect(() => {
    if (!status || sheetId === null) return
    const prev = previous.current
    previous.current = status

    if (prev !== null && prev !== status && isTerminal(status)) {
      qc.invalidateQueries({ queryKey: qk.sheet(sheetId) })
      if (examId !== undefined) {
        qc.invalidateQueries({ queryKey: qk.sheetsAll(examId) })
        qc.invalidateQueries({ queryKey: qk.examSummary(examId) })
      }
    }
  }, [status, sheetId, examId, qc])

  return { ...query, isTerminal: isTerminal(status) }
}

export function useUploadSheet(examId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      studentId,
      files,
      onProgress,
    }: {
      studentId: number
      files: File[]
      onProgress?: (p: number) => void
    }) => uploadSheet(examId, studentId, files, onProgress),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.sheetsAll(examId) })
    },
    onError: (e) => toast.error(errorMessage(e, 'Upload failed')),
  })
}

export function useRetrySheet(examId?: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sheetId: number) => retrySheet(sheetId),
    onSuccess: (sheet) => {
      qc.invalidateQueries({ queryKey: qk.sheet(sheet.id) })
      qc.invalidateQueries({ queryKey: qk.sheetStatus(sheet.id) })
      if (examId !== undefined) qc.invalidateQueries({ queryKey: qk.sheetsAll(examId) })
      toast.success('Re-queued for evaluation')
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not retry')),
  })
}

export function useApproveSheet(examId?: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sheetId: number) => approveSheet(sheetId),
    onSuccess: (sheet) => {
      qc.invalidateQueries({ queryKey: qk.sheet(sheet.id) })
      if (examId !== undefined) {
        qc.invalidateQueries({ queryKey: qk.sheetsAll(examId) })
        qc.invalidateQueries({ queryKey: qk.examSummary(examId) })
      }
      toast.success('Approved — the student can now see this result')
    },
    onError: (e) => toast.error(errorMessage(e, 'Could not approve')),
  })
}
