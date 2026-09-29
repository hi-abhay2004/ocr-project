import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { Band } from '@/types/api'

/**
 * Confidence → band. The thresholds are INCLUSIVE lower bounds:
 * 0.80 is green, 0.65 is orange. The boundary cases are asserted in the tests
 * because "≥ .80" quietly written as "> .80" moves every borderline sheet into
 * the review queue.
 */
export function bandFor(score: number): Band {
  if (score >= 0.8) return 'GREEN'
  if (score >= 0.65) return 'ORANGE'
  return 'RED'
}

const BAND_CLASS: Record<Band, string> = {
  GREEN: 'border-green-600/40 bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-400',
  ORANGE: 'border-amber-600/40 bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400',
  RED: 'border-red-600/40 bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-400',
}

const BAND_DOT: Record<Band, string> = {
  GREEN: 'bg-green-600',
  ORANGE: 'bg-amber-600',
  RED: 'bg-red-600',
}

const BAND_WORD: Record<Band, string> = {
  GREEN: 'High confidence',
  ORANGE: 'Needs a look',
  RED: 'Review required',
}

export function ConfidenceBadge({ score, showLabel = true }: { score: number; showLabel?: boolean }) {
  const band = bandFor(score)
  return (
    <Badge
      variant="outline"
      className={cn('gap-1.5', BAND_CLASS[band])}
      data-testid="confidence-badge"
      data-band={band}
      title={`${BAND_WORD[band]} — composite confidence ${(score * 100).toFixed(0)}%`}
    >
      <span className={cn('size-2 rounded-full', BAND_DOT[band])} aria-hidden />
      <span className="font-mono">{(score * 100).toFixed(0)}%</span>
      {showLabel && <span className="hidden sm:inline">{BAND_WORD[band]}</span>}
    </Badge>
  )
}

/** Compact band-only pill for dense table rows. */
export function BandPill({ band }: { band: Band }) {
  return (
    <Badge variant="outline" className={cn('gap-1.5', BAND_CLASS[band])} data-testid="band-pill" data-band={band}>
      <span className={cn('size-2 rounded-full', BAND_DOT[band])} aria-hidden />
      {BAND_WORD[band]}
    </Badge>
  )
}
