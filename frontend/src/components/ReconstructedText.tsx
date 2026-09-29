import { useMemo } from 'react'
import { wordDiff } from '@/lib/wordDiff'
import { cn } from '@/lib/utils'
import type { Block } from '@/types/api'

/**
 * The right-hand pane of the side-by-side view (§7).
 *
 * Shows what the grader actually read, with the L5 reconstruction made visible:
 * struck words appear struck, stitched-in words appear highlighted. The teacher
 * verifies the machine's reading against the scan on the left.
 */
export function ReconstructedText({ block, className }: { block: Block; className?: string }) {
  const tokens = useMemo(() => {
    // Non-text blocks have no OCR pass to diff against — the VLM description IS
    // the text, so show it plainly.
    if (!block.raw_text.trim()) return null
    return wordDiff(block.raw_text, block.reconstructed_text)
  }, [block.raw_text, block.reconstructed_text])

  if (!tokens) {
    return (
      <p className={cn('text-sm leading-relaxed', className)} data-testid="reconstructed-text">
        {block.reconstructed_text}
      </p>
    )
  }

  const removed = tokens.filter((t) => t.op === 'removed').length
  const added = tokens.filter((t) => t.op === 'added').length

  return (
    <div className={className}>
      <p className="text-sm leading-relaxed" data-testid="reconstructed-text">
        {tokens.map((token, i) => (
          <span
            key={i}
            data-op={token.op}
            className={cn(
              token.op === 'removed' &&
                'text-muted-foreground/70 decoration-red-500 decoration-2 line-through',
              token.op === 'added' &&
                'rounded bg-amber-100 px-0.5 text-amber-900 dark:bg-amber-950/50 dark:text-amber-200',
            )}
          >
            {token.text}{' '}
          </span>
        ))}
      </p>

      {(removed > 0 || added > 0) && (
        <p className="text-muted-foreground mt-3 border-t pt-2 text-xs">
          {removed > 0 && (
            <>
              <span className="decoration-red-500 line-through">Struck text</span> was excluded
              before grading.{' '}
            </>
          )}
          {added > 0 && (
            <>
              <span className="rounded bg-amber-100 px-0.5 dark:bg-amber-950/50">Highlighted</span>{' '}
              text was stitched in from the margins.
            </>
          )}
        </p>
      )}
    </div>
  )
}
