import { Badge } from '@/components/ui/badge'
import { ANNOTATION_KINDS, KIND_STYLE } from './AnnotationOverlay'
import { cn } from '@/lib/utils'
import type { Annotation } from '@/types/api'

/**
 * Counts-only view of what the CV layer found.
 *
 * This is the STUDENT-side substitute for the overlay: it tells them their
 * corrections were understood, without exposing the raw crop.
 */
export function AnnotationSummary({
  annotations,
  className,
}: {
  annotations: Annotation[]
  className?: string
}) {
  const present = ANNOTATION_KINDS.map((kind) => ({
    kind,
    count: annotations.filter((a) => a.kind === kind).length,
  })).filter((x) => x.count > 0)

  if (present.length === 0) {
    return (
      <p className={cn('text-muted-foreground text-sm', className)}>
        No corrections or emphasis marks were detected on this answer.
      </p>
    )
  }

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {present.map(({ kind, count }) => (
        <Badge key={kind} variant="secondary" className="gap-1.5">
          <span className={cn('size-2 rounded-sm', KIND_STYLE[kind].swatch)} aria-hidden />
          {KIND_STYLE[kind].label}
          <span className="text-muted-foreground">×{count}</span>
        </Badge>
      ))}
    </div>
  )
}
