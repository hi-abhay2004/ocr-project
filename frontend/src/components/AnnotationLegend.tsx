import { Sparkles } from 'lucide-react'
import { ANNOTATION_KINDS, KIND_STYLE } from './AnnotationOverlay'
import { cn } from '@/lib/utils'

const MEANING: Record<(typeof ANNOTATION_KINDS)[number], string> = {
  STRIKE: 'text was excluded before grading',
  UNDERLINE: 'keyword weight boosted ×1.10',
  ARROW: 'insertion pointer followed',
  MARGIN: 'margin text stitched into the answer',
}

export function AnnotationLegend({ className }: { className?: string }) {
  return (
    <div className={cn('text-muted-foreground space-y-1.5 text-xs', className)}>
      {ANNOTATION_KINDS.map((kind) => (
        <div key={kind} className="flex items-center gap-2">
          <span className={cn('size-3 shrink-0 rounded-sm', KIND_STYLE[kind].swatch)} aria-hidden />
          <span className="text-foreground font-medium">{KIND_STYLE[kind].label}</span>
          <span>— {MEANING[kind]}</span>
        </div>
      ))}
      <div className="flex items-center gap-2 border-t pt-1.5">
        <span
          className="size-3 shrink-0 rounded-sm border-2 border-dashed border-current"
          aria-hidden
        />
        <span className="text-foreground flex items-center gap-1 font-medium">
          <Sparkles className="size-3" />
          Dashed
        </span>
        <span>— vision model adjudicated (L3.5)</span>
      </div>
    </div>
  )
}
