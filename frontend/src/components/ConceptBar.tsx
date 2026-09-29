import { AlertTriangle, Quote } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { ConceptScore, ConceptStatus } from '@/types/api'

const STATUS_STYLE: Record<ConceptStatus, { bar: string; text: string; label: string }> = {
  COVERED: { bar: 'bg-green-600', text: 'text-green-700 dark:text-green-400', label: 'Covered' },
  PARTIAL: { bar: 'bg-amber-500', text: 'text-amber-700 dark:text-amber-400', label: 'Partial' },
  MISSING: { bar: 'bg-red-600', text: 'text-red-700 dark:text-red-400', label: 'Missing' },
}

export interface ConceptBarProps {
  score: ConceptScore
  /** Teachers see the retrieved evidence chunk; students never do (§8). */
  showEvidence?: boolean
}

export function ConceptBar({ score, showEvidence = false }: ConceptBarProps) {
  const style = STATUS_STYLE[score.status]
  // Bar width tracks SIMILARITY, not marks: it shows how close the retrieved
  // evidence was to the concept, which is what the status was decided from.
  const width = Math.max(2, Math.min(100, score.similarity * 100))

  return (
    <div className="space-y-1.5 py-2" data-testid="concept-bar" data-status={score.status}>
      <div className="flex items-start gap-2">
        <p className="flex-1 text-sm leading-snug">{score.concept_text}</p>

        {score.disagreed && (
          <Tooltip>
            <TooltipTrigger asChild>
              <AlertTriangle
                className="mt-0.5 size-4 shrink-0 text-amber-600"
                data-testid="disagreed-icon"
                aria-label="The three evaluation passes disagreed on this concept"
              />
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              The three independent passes did not agree on this concept. The majority verdict was
              used — worth checking by hand.
            </TooltipContent>
          </Tooltip>
        )}

        <span className={cn('shrink-0 text-xs font-medium', style.text)}>{style.label}</span>
        <span className="text-muted-foreground w-16 shrink-0 text-right font-mono text-xs">
          {score.marks.toFixed(2)} / {score.max_marks.toFixed(2)}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <div className="bg-muted h-1.5 flex-1 overflow-hidden rounded-full">
          <div
            className={cn('h-full rounded-full transition-all', style.bar)}
            style={{ width: `${width}%` }}
            data-testid="concept-bar-fill"
            role="meter"
            aria-valuenow={Math.round(score.similarity * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Similarity for ${score.concept_text}`}
          />
        </div>
        <span className="text-muted-foreground w-10 shrink-0 text-right font-mono text-[11px]">
          {score.similarity.toFixed(2)}
        </span>
      </div>

      {showEvidence && score.evidence && (
        <p className="text-muted-foreground bg-muted/50 flex gap-1.5 rounded-md px-2 py-1.5 text-xs italic">
          <Quote className="mt-0.5 size-3 shrink-0" />
          {score.evidence}
        </p>
      )}
    </div>
  )
}
