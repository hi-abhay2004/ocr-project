import { useEffect, useState } from 'react'
import { AlertCircle, Check, Loader2, Sparkles } from 'lucide-react'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { STAGES, type SheetStatus, type Stage } from '@/types/api'

/**
 * The 12-stage stepper — FRONTEND_PLAN §8 screen 6.
 *
 * Stage labels are rendered from the STAGES tuple in types/api.ts verbatim, so
 * the pipeline, the API enum and this component cannot drift apart. If the
 * backend adds a stage, add it there and it appears here.
 */

const LABEL: Record<Stage, string> = {
  queued: 'Queued',
  preprocessing: 'Preprocessing',
  segmentation: 'Segmentation',
  annotations: 'Annotation detection',
  adjudication: 'Adjudication',
  ocr: 'OCR',
  specialized: 'Specialized content',
  reconstruction: 'Reconstruction',
  retrieval: 'Concept retrieval',
  coverage: 'Coverage analysis',
  scoring: 'Scoring',
  feedback: 'Feedback',
  done: 'Done',
}

const LAYER: Partial<Record<Stage, string>> = {
  preprocessing: 'L1',
  segmentation: 'L2',
  annotations: 'L3',
  adjudication: 'L3.5',
  ocr: 'L4',
  specialized: 'L4.5',
  reconstruction: 'L5',
  retrieval: 'L6',
  coverage: 'L7',
  scoring: 'L8',
  feedback: 'L8',
}

/** The three stages that can invoke the vision model. */
const VLM_STAGES = new Set<Stage>(['adjudication', 'ocr', 'specialized'])

function useElapsed(startedAt: string, running: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [running])

  const start = new Date(startedAt).getTime()
  const seconds = Math.max(0, Math.floor((now - start) / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

export function PipelineProgress({
  stage,
  status,
  startedAt,
  errorMessage,
}: {
  stage: Stage
  status: SheetStatus
  startedAt: string
  errorMessage?: string | null
}) {
  const failed = status === 'FAILED'
  const complete = status === 'DONE' || status === 'APPROVED'
  const running = !failed && !complete

  const elapsed = useElapsed(startedAt, running)
  const index = Math.max(0, STAGES.indexOf(stage))
  const percent = complete ? 100 : Math.round((index / (STAGES.length - 1)) * 100)

  return (
    <div className="space-y-4" data-testid="pipeline-progress" data-stage={stage} data-status={status}>
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="flex items-center gap-2 font-medium">
          {failed ? (
            <AlertCircle className="text-destructive size-4" />
          ) : complete ? (
            <Check className="size-4 text-green-600" />
          ) : (
            <Loader2 className="size-4 animate-spin" />
          )}
          {failed ? 'Evaluation failed' : complete ? 'Evaluation complete' : LABEL[stage]}
        </span>
        <span className="text-muted-foreground font-mono text-xs" data-testid="elapsed">
          {elapsed}
        </span>
      </div>

      <Progress value={percent} className={cn(failed && '[&>div]:bg-destructive')} />

      {failed && errorMessage && (
        <p className="text-destructive bg-destructive/10 rounded-md px-3 py-2 text-sm">
          {errorMessage}
        </p>
      )}

      <ol className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3 lg:grid-cols-4">
        {STAGES.map((s, i) => {
          const done = i < index || complete
          const current = i === index && running
          return (
            <li
              key={s}
              data-testid={`stage-${s}`}
              data-state={current ? 'current' : done ? 'done' : 'pending'}
              className={cn(
                'flex items-center gap-1.5 py-0.5 text-xs',
                current && 'text-foreground font-semibold',
                done && !current && 'text-muted-foreground',
                !done && !current && 'text-muted-foreground/50',
              )}
            >
              <span
                className={cn(
                  'flex size-4 shrink-0 items-center justify-center rounded-full border text-[9px]',
                  done && 'border-green-600 bg-green-600 text-white',
                  current && 'border-foreground',
                )}
                aria-hidden
              >
                {done ? <Check className="size-2.5" /> : current ? '' : i + 1}
              </span>
              <span className="truncate">{LABEL[s]}</span>
              {LAYER[s] && (
                <span className="text-muted-foreground/60 shrink-0 font-mono text-[9px]">
                  {LAYER[s]}
                </span>
              )}
              {VLM_STAGES.has(s) && (
                <Sparkles
                  className="size-2.5 shrink-0 text-violet-500"
                  aria-label="may invoke the vision model"
                />
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
