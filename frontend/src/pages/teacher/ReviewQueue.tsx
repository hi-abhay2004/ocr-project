import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertCircle, BarChart3, Check, ClipboardCheck, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { BandPill } from '@/components/ConfidenceBadge'
import { Empty } from '@/components/states/Empty'
import { ErrorState } from '@/components/states/ErrorState'
import { TableSkeleton } from '@/components/states/Loading'
import { useExamSheets } from '@/hooks/useExams'
import type { Band, SheetStatus } from '@/types/api'

/**
 * The queue IS the triage (§8 screen 7).
 *
 * Sorted worst-confidence-first, deliberately: a teacher with 60 sheets and an
 * hour should spend it on the ones the machine was unsure about. Sorting by
 * name or by upload time buries exactly the sheets that need a human.
 */

const BAND_ORDER: Record<Band, number> = { RED: 0, ORANGE: 1, GREEN: 2 }

const STATUS_LABEL: Record<SheetStatus, string> = {
  QUEUED: 'Queued',
  RUNNING: 'Evaluating',
  DONE: 'Awaiting review',
  FAILED: 'Failed',
  APPROVED: 'Approved',
}

export function ReviewQueue() {
  const examId = Number(useParams().examId)
  const [band, setBand] = useState<string>('all')
  const [status, setStatus] = useState<string>('all')

  const filters = useMemo(
    () => ({
      ...(band !== 'all' ? { band: band as Band } : {}),
      ...(status !== 'all' ? { status } : {}),
    }),
    [band, status],
  )

  const { data: sheets, isPending, error, refetch } = useExamSheets(examId, filters)

  const sorted = useMemo(
    () =>
      [...(sheets ?? [])].sort(
        (a, b) => BAND_ORDER[a.band] - BAND_ORDER[b.band] || a.confidence - b.confidence,
      ),
    [sheets],
  )

  const pending = sorted.filter((s) => s.status === 'DONE').length

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to={`/exams/${examId}`} className="text-muted-foreground text-sm hover:underline">
            ← Back to exam
          </Link>
          <h1 className="mt-1 text-2xl font-semibold">Review queue</h1>
          <p className="text-muted-foreground text-sm">
            Lowest confidence first — the sheets most likely to need you are at the top.
            {pending > 0 && ` ${pending} awaiting approval.`}
          </p>
        </div>
        <Button variant="outline" asChild>
          <Link to={`/exams/${examId}/summary`}>
            <BarChart3 className="size-4" />
            Class analytics
          </Link>
        </Button>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select value={band} onValueChange={setBand}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All bands" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All bands</SelectItem>
            <SelectItem value="RED">Review required</SelectItem>
            <SelectItem value="ORANGE">Needs a look</SelectItem>
            <SelectItem value="GREEN">High confidence</SelectItem>
          </SelectContent>
        </Select>

        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="DONE">Awaiting review</SelectItem>
            <SelectItem value="APPROVED">Approved</SelectItem>
            <SelectItem value="RUNNING">Evaluating</SelectItem>
            <SelectItem value="FAILED">Failed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isPending && <TableSkeleton rows={5} cols={6} />}
      {error && <ErrorState error={error} onRetry={() => void refetch()} />}

      {sheets && sorted.length === 0 && (
        <Empty
          icon={ClipboardCheck}
          title={band === 'all' && status === 'all' ? 'No sheets uploaded yet' : 'Nothing matches these filters'}
          hint={
            band === 'all' && status === 'all'
              ? 'Upload a scanned answer sheet to start.'
              : 'Try clearing the band or status filter.'
          }
          action={
            band === 'all' && status === 'all' ? (
              <Button asChild>
                <Link to={`/exams/${examId}/upload`}>Upload a sheet</Link>
              </Button>
            ) : undefined
          }
        />
      )}

      {sorted.length > 0 && (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Student</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden sm:table-cell">Confidence</TableHead>
                <TableHead className="text-right">Marks</TableHead>
                <TableHead className="w-24 text-right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((sheet) => {
                const busy = sheet.status === 'QUEUED' || sheet.status === 'RUNNING'
                return (
                  <TableRow key={sheet.id} className="hover:bg-muted/50">
                    <TableCell>
                      <span className="font-medium">{sheet.student.name}</span>
                      <span className="text-muted-foreground block font-mono text-xs">
                        {sheet.student.usn}
                      </span>
                    </TableCell>

                    <TableCell>
                      <div className="flex flex-wrap items-center gap-2">
                        {busy ? (
                          <Badge variant="secondary" className="gap-1.5">
                            <Loader2 className="size-3 animate-spin" />
                            {STATUS_LABEL[sheet.status]} · {sheet.stage}
                          </Badge>
                        ) : sheet.status === 'FAILED' ? (
                          <Badge variant="destructive" className="gap-1.5">
                            <AlertCircle className="size-3" />
                            Failed
                          </Badge>
                        ) : (
                          <>
                            <BandPill band={sheet.band} />
                            {sheet.status === 'APPROVED' && (
                              <Badge variant="secondary" className="gap-1">
                                <Check className="size-3" />
                                Approved
                              </Badge>
                            )}
                          </>
                        )}
                      </div>
                    </TableCell>

                    <TableCell className="text-muted-foreground hidden font-mono text-sm sm:table-cell">
                      {busy || sheet.status === 'FAILED' ? '—' : `${(sheet.confidence * 100).toFixed(0)}%`}
                    </TableCell>

                    <TableCell className="text-right font-mono text-sm">
                      {busy || sheet.status === 'FAILED'
                        ? '—'
                        : `${sheet.total_marks} / ${sheet.max_marks}`}
                    </TableCell>

                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" asChild>
                        <Link to={`/sheets/${sheet.id}`}>
                          {sheet.status === 'APPROVED' ? 'View' : 'Review'}
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
