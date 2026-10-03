import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertCircle, Check, ImageIcon, RotateCw, ScanEye, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { AnnotationLegend } from '@/components/AnnotationLegend'
import { AnnotationOverlay } from '@/components/AnnotationOverlay'
import { ConceptBarList } from '@/components/ConceptBarList'
import { ConfidenceBadge, BandPill } from '@/components/ConfidenceBadge'
import { FeedbackPanel } from '@/components/FeedbackPanel'
import { PipelineProgress } from '@/components/PipelineProgress'
import { ReconstructedText } from '@/components/ReconstructedText'
import { ScoreOverrideForm } from '@/components/ScoreOverrideForm'
import { ErrorState } from '@/components/states/ErrorState'
import { Loading } from '@/components/states/Loading'
import { useOverrideMarks } from '@/hooks/useEvaluation'
import { useApproveSheet, useCancelSheet, useRetrySheet, useSheet, useSheetStatus } from '@/hooks/useSheets'
import { cn } from '@/lib/utils'

/**
 * ★ The big screen — FRONTEND_PLAN §8 screen 8.
 *
 * Layout choice: TABS, not one long column. Overlay + concept bars + feedback +
 * override form stacked vertically is roughly three screens tall on a laptop,
 * and the teacher ends up scrolling between the scan and the marks they are
 * setting. Tabs keep the override form and the header marks always visible
 * (§12 — "review screen too dense on a laptop").
 */
export function ReviewDetail() {
  const sheetId = Number(useParams().sheetId)
  const { data: sheet, isPending, error, refetch } = useSheet(sheetId)
  const examId = sheet?.exam

  // Keeps a still-running sheet live without a manual refresh, and stops on its
  // own once the status goes terminal.
  useSheetStatus(sheet && (sheet.status === 'QUEUED' || sheet.status === 'RUNNING') ? sheetId : null, examId)

  const override = useOverrideMarks(sheetId, examId)
  const approve = useApproveSheet(examId)
  const retry = useRetrySheet(examId)
  const cancel = useCancelSheet(examId)

  const [activeQuestion, setActiveQuestion] = useState<string>('')
  const [approveOpen, setApproveOpen] = useState(false)

  useEffect(() => {
    if (sheet && !activeQuestion && sheet.evaluations.length > 0) {
      setActiveQuestion(String(sheet.evaluations[0].id))
    }
  }, [sheet, activeQuestion])

  if (isPending) return <Loading />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />
  if (!sheet) return null

  if (sheet.status === 'QUEUED' || sheet.status === 'RUNNING') {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Evaluating {sheet.student.name}'s sheet — results appear here automatically
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <PipelineProgress
            stage={sheet.stage}
            status={sheet.status}
            startedAt={sheet.last_run_started_at ?? sheet.started_at}
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => cancel.mutate(sheet.id)}
            disabled={cancel.isPending}
          >
            Cancel evaluation
          </Button>
        </CardContent>
      </Card>
    )
  }

  if (sheet.status === 'FAILED') {
    return (
      <div className="space-y-4">
        <Link to={`/exams/${sheet.exam}/review`} className="text-muted-foreground text-sm hover:underline">
          ← Back to the queue
        </Link>
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle className="text-destructive flex items-center gap-2 text-base">
              <AlertCircle className="size-5" />
              Evaluation failed at the {sheet.stage} stage
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm">{sheet.error_message}</p>
            <Button onClick={() => retry.mutate(sheet.id)}>
              <RotateCw className="size-4" />
              Retry evaluation
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const current = sheet.evaluations.find((e) => String(e.id) === activeQuestion) ?? sheet.evaluations[0]
  const approved = sheet.status === 'APPROVED'
  const escalatedCount = sheet.evaluations
    .flatMap((e) => e.blocks)
    .flatMap((b) => b.annotations)
    .filter((a) => a.resolved_by === 'VLM').length

  return (
    <div className="space-y-5 pb-32">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link
            to={`/exams/${sheet.exam}/review`}
            className="text-muted-foreground text-sm hover:underline"
          >
            ← Back to the queue
          </Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-2 text-2xl font-semibold">
            {sheet.student.name}
            <span className="text-muted-foreground font-mono text-sm">{sheet.student.usn}</span>
          </h1>
          <p className="text-muted-foreground text-sm">{sheet.exam_name}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* The per-block crops below are the grader's own view of each
              answer region — the VLM's own bbox for one can be narrower
              than the real content, and a page with several answer blocks
              shows as several separate crops rather than one sheet. This
              opens the actual uploaded file(s), unmodified, so a teacher
              can always see exactly what the student submitted. */}
          {sheet.pages.map((page) => (
            <Button key={page.id} variant="outline" size="sm" asChild>
              <a href={page.image_url} target="_blank" rel="noopener noreferrer">
                <ImageIcon className="size-4" />
                {sheet.pages.length > 1 ? `View page ${page.index + 1}` : 'View uploaded booklet'}
              </a>
            </Button>
          ))}
          <ConfidenceBadge score={sheet.confidence} />
          <BandPill band={sheet.band} />
          {escalatedCount > 0 && (
            <Badge variant="outline" className="gap-1 border-violet-400 text-violet-600 dark:text-violet-400">
              <Sparkles className="size-3" />
              {escalatedCount} VLM-adjudicated
            </Badge>
          )}
          {approved ? (
            <Badge variant="secondary" className="gap-1">
              <Check className="size-3" />
              Approved
            </Badge>
          ) : (
            <Button onClick={() => setApproveOpen(true)}>
              <Check className="size-4" />
              Approve & publish
            </Button>
          )}
        </div>
      </div>

      {/* ── Question switcher ──────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-2">
        {sheet.evaluations.map((evaluation) => {
          const effective = evaluation.override_marks ?? evaluation.auto_marks
          const active = String(evaluation.id) === activeQuestion
          return (
            <button
              key={evaluation.id}
              onClick={() => setActiveQuestion(String(evaluation.id))}
              className={cn(
                'rounded-lg border px-3 py-2 text-left transition-colors',
                active ? 'border-primary bg-primary/5' : 'hover:bg-muted/50',
              )}
            >
              <span className="block font-mono text-xs">Q{evaluation.question_number}</span>
              <span className="block text-sm font-medium">
                {effective} / {evaluation.max_marks}
                {evaluation.override_marks !== null && (
                  <span className="text-muted-foreground ml-1 text-xs">(overridden)</span>
                )}
              </span>
            </button>
          )
        })}
      </div>

      {current && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base leading-snug">
              <span className="text-muted-foreground font-mono">Q{current.question_number}</span>{' '}
              {current.question_text}
            </CardTitle>
          </CardHeader>

          <CardContent>
            <Tabs defaultValue="overlay" className="w-full">
              <TabsList>
                <TabsTrigger value="overlay">
                  <ScanEye className="size-4" />
                  Answer & annotations
                </TabsTrigger>
                <TabsTrigger value="concepts">
                  Concepts ({current.concept_scores.length})
                </TabsTrigger>
                <TabsTrigger value="feedback">Feedback</TabsTrigger>
              </TabsList>

              {/* ── Overlay ─────────────────────────────────────────── */}
              {/* One question's answer can span several detected blocks
                  (the VLM splits a page by visual region, not by question) —
                  these render as ONE continuous answer, not a separate
                  framed card per block with its own repeated badges/"What
                  the grader read" box/legend (reported 2026-10-01: looked
                  like the image had been "divided"). Each block keeps its
                  own AnnotationOverlay (its bbox coordinates are only valid
                  within its own crop) and its own small OCR/quality tag, but
                  everything else — the legend, the "what the grader read"
                  label — appears exactly once for the whole question. */}
              <TabsContent value="overlay" className="grid gap-4 pt-4 md:grid-cols-2">
                <div className="space-y-0 overflow-hidden rounded-md border">
                  {current.blocks.map((block) => (
                    <div key={block.id} className="border-b last:border-b-0">
                      <div className="flex flex-wrap items-center gap-2 px-3 py-1.5 text-xs">
                        <Badge variant="outline" className="font-mono">
                          {block.ocr_engine}
                        </Badge>
                        <Badge variant="outline" className="font-mono">
                          quality {block.quality_score.toFixed(2)}
                        </Badge>
                      </div>
                      <AnnotationOverlay block={block} frameless />
                    </div>
                  ))}
                </div>

                <div className="space-y-4">
                  <div className="bg-muted/30 rounded-lg border p-3">
                    <p className="text-muted-foreground mb-2 text-xs font-medium">
                      What the grader read
                    </p>
                    <div className="divide-y">
                      {current.blocks.map((block) => (
                        <ReconstructedText key={block.id} block={block} className="py-2 first:pt-0 last:pb-0" />
                      ))}
                    </div>
                  </div>
                  <AnnotationLegend />
                </div>
              </TabsContent>

              {/* ── Concepts ────────────────────────────────────────── */}
              <TabsContent value="concepts" className="pt-4">
                <ConceptBarList scores={current.concept_scores} showEvidence />
              </TabsContent>

              {/* ── Feedback ────────────────────────────────────────── */}
              <TabsContent value="feedback" className="pt-4">
                <FeedbackPanel feedback={current.feedback} />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}

      {/* ── Sticky override footer ─────────────────────────────────────── */}
      {current && !approved && (
        <div className="bg-background/95 fixed inset-x-0 bottom-0 z-30 border-t backdrop-blur supports-[backdrop-filter]:bg-background/80">
          <div className="mx-auto max-w-7xl px-4 py-3">
            <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
              <span className="font-medium">Q{current.question_number}</span>
              <span className="text-muted-foreground">
                machine mark <span className="font-mono">{current.auto_marks}</span> of{' '}
                {current.max_marks}
              </span>
              <ConfidenceBadge score={current.confidence} showLabel={false} />
              <span className="text-muted-foreground ml-auto font-mono">
                sheet total {sheet.total_marks} / {sheet.max_marks}
              </span>
            </div>
            <ScoreOverrideForm
              evaluationId={current.id}
              autoMarks={current.auto_marks}
              currentOverride={current.override_marks}
              currentComment={current.override_comment}
              maxMarks={current.max_marks}
              saving={override.save.isPending || override.clear.isPending}
              onSave={(input) => override.save.mutate({ evaluationId: current.id, input })}
              onClear={() => override.clear.mutate(current.id)}
            />
          </div>
        </div>
      )}

      {/* ── Approve confirmation ───────────────────────────────────────── */}
      <Dialog open={approveOpen} onOpenChange={setApproveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Publish this result to {sheet.student.name}?</DialogTitle>
            <DialogDescription>
              The student will see their marks, the concept breakdown and the feedback — including
              any comment you wrote. They will not see the scanned pages or the retrieved evidence
              quotes. Review every question before approving.
            </DialogDescription>
          </DialogHeader>
          <div className="text-sm">
            Final total: <span className="font-mono font-medium">{sheet.total_marks}</span> /{' '}
            {sheet.max_marks}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproveOpen(false)}>
              Not yet
            </Button>
            <Button
              onClick={async () => {
                await approve.mutateAsync(sheet.id)
                setApproveOpen(false)
              }}
              disabled={approve.isPending}
            >
              <Check className="size-4" />
              Approve & publish
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
