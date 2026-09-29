import { useMemo, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { Annotation, AnnotationKind, Block } from '@/types/api'

/**
 * ★ The demo centrepiece — FRONTEND_PLAN §7.
 *
 * THE SCALING TRICK
 * -----------------
 * The crop is e.g. 1240 px wide but renders at whatever width the layout gives
 * it. Rather than measuring the rendered <img> and multiplying every coordinate
 * in JS — which needs a ResizeObserver, re-renders on every resize, and is wrong
 * for one frame after layout — the <svg> is given a viewBox in the image's
 * NATURAL coordinates and stretched over the same box. The browser then maps
 * bbox pixels to screen pixels itself.
 *
 * Consequence: `x={a.bbox.x}` is used raw. No arithmetic anywhere in this file.
 * Responsive at every breakpoint for free, and correct on the first paint.
 *
 * The one contract this depends on: bbox MUST be in the crop's own pixel space
 * (§3.1). Page coordinates put boxes off-screen; normalised 0–1 coordinates
 * collapse them all into the top-left corner.
 */

export const ANNOTATION_KINDS: AnnotationKind[] = ['STRIKE', 'UNDERLINE', 'ARROW', 'MARGIN']

/** Stroke + fill per kind. Also used by AnnotationLegend so the two never drift. */
export const KIND_STYLE: Record<AnnotationKind, { stroke: string; fill: string; label: string; swatch: string }> = {
  STRIKE: { stroke: '#dc2626', fill: 'rgba(220,38,38,0.12)', label: 'Struck out', swatch: 'bg-red-600' },
  UNDERLINE: { stroke: '#2563eb', fill: 'rgba(37,99,235,0.12)', label: 'Underlined', swatch: 'bg-blue-600' },
  ARROW: { stroke: '#16a34a', fill: 'rgba(22,163,74,0.12)', label: 'Insertion arrow', swatch: 'bg-green-600' },
  MARGIN: { stroke: '#d97706', fill: 'rgba(217,119,6,0.12)', label: 'Margin note', swatch: 'bg-amber-600' },
}

const INTENT_LABEL: Record<Annotation['intent'], string> = {
  CORRECTION: 'excluded from the answer',
  EMPHASIS: 'weighted up as a keyword',
  INSERTION: 'stitched into the answer',
}

export function AnnotationOverlay({ block, className }: { block: Block; className?: string }) {
  const [hidden, setHidden] = useState<Set<AnnotationKind>>(new Set())
  const [hovered, setHovered] = useState<Annotation | null>(null)

  const visible = useMemo(
    () => block.annotations.filter((a) => !hidden.has(a.kind)),
    [block.annotations, hidden],
  )

  const present = useMemo(
    () => ANNOTATION_KINDS.filter((k) => block.annotations.some((a) => a.kind === k)),
    [block.annotations],
  )

  function toggle(kind: AnnotationKind) {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(kind)) next.delete(kind)
      else next.add(kind)
      return next
    })
  }

  const isNonText = block.content_type !== 'TEXT'

  return (
    <div className={cn('space-y-3', className)}>
      {isNonText && (
        <div className="flex items-start gap-2 rounded-md border border-violet-300 bg-violet-50 px-3 py-2 text-sm text-violet-900 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-200">
          <Sparkles className="mt-0.5 size-4 shrink-0" />
          <span>
            <strong>{block.content_type.toLowerCase()}</strong> — this block is not text. It was
            described by the vision model ({block.ocr_engine}), and that description is what the
            grader read.
          </span>
        </div>
      )}

      {/* Layer toggles — isolate one annotation type at a time. */}
      {present.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {present.map((kind) => (
            <label key={kind} className="flex cursor-pointer items-center gap-2 text-sm select-none">
              <Checkbox
                checked={!hidden.has(kind)}
                onCheckedChange={() => toggle(kind)}
                aria-label={`Show ${KIND_STYLE[kind].label.toLowerCase()} annotations`}
              />
              <span className={cn('size-3 rounded-sm', KIND_STYLE[kind].swatch)} aria-hidden />
              {KIND_STYLE[kind].label}
              <span className="text-muted-foreground">
                ({block.annotations.filter((a) => a.kind === kind).length})
              </span>
            </label>
          ))}
        </div>
      )}

      <div className="relative inline-block w-full overflow-hidden rounded-md border bg-white">
        <img
          src={block.crop_image_url}
          alt={`Answer crop for question block ${block.id}`}
          className="block h-auto w-full"
          draggable={false}
        />

        <svg
          // The whole trick, in one attribute.
          viewBox={`0 0 ${block.image_width} ${block.image_height}`}
          preserveAspectRatio="none"
          className="pointer-events-none absolute inset-0 h-full w-full"
          data-testid="annotation-svg"
          role="group"
          aria-label="Detected annotations"
        >
          {visible.map((a) => {
            const style = KIND_STYLE[a.kind]
            const escalated = a.resolved_by === 'VLM'
            return (
              <rect
                key={a.id}
                data-testid="annotation-rect"
                data-kind={a.kind}
                data-resolved-by={a.resolved_by}
                x={a.bbox.x}
                y={a.bbox.y}
                width={a.bbox.w}
                height={a.bbox.h}
                rx={3}
                fill={hovered?.id === a.id ? style.stroke : style.fill}
                fillOpacity={hovered?.id === a.id ? 0.22 : 1}
                stroke={style.stroke}
                strokeWidth={hovered?.id === a.id ? 4 : 2.5}
                // Dashed = the CV detector was below threshold and L3.5 asked the
                // VLM. This is the single mark on screen that turns "adaptive VLM
                // sensitivity" from a claim in the report into something an
                // examiner can point at.
                strokeDasharray={escalated ? '10 6' : undefined}
                vectorEffect="non-scaling-stroke"
                style={{ pointerEvents: 'all', cursor: 'help' }}
                onMouseEnter={() => setHovered(a)}
                onMouseLeave={() => setHovered((h) => (h?.id === a.id ? null : h))}
              />
            )
          })}
        </svg>

        {hovered && (
          <div className="bg-popover text-popover-foreground pointer-events-none absolute right-2 bottom-2 z-10 max-w-[min(20rem,90%)] rounded-md border p-2.5 text-xs shadow-lg">
            <div className="flex items-center gap-2 font-medium">
              <span className={cn('size-2.5 rounded-sm', KIND_STYLE[hovered.kind].swatch)} aria-hidden />
              {KIND_STYLE[hovered.kind].label}
              <Badge variant="outline" className="ml-auto font-mono text-[10px]">
                {(hovered.confidence * 100).toFixed(0)}%
              </Badge>
            </div>
            <p className="text-muted-foreground mt-1">Text {INTENT_LABEL[hovered.intent]}.</p>
            {hovered.resolved_by === 'VLM' && (
              <p className="mt-1 flex items-center gap-1 font-medium text-violet-600 dark:text-violet-400">
                <Sparkles className="size-3" />
                Decided by the vision model — CV confidence was below threshold
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
