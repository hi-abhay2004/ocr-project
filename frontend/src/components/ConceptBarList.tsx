import { ConceptBar } from './ConceptBar'
import type { ConceptScore } from '@/types/api'

const ORDER = { MISSING: 0, PARTIAL: 1, COVERED: 2 } as const

export function ConceptBarList({
  scores,
  showEvidence = false,
}: {
  scores: ConceptScore[]
  showEvidence?: boolean
}) {
  // Worst first — the teacher is looking for what went wrong, not confirming
  // what went right. Same triage logic as the review queue.
  const sorted = [...scores].sort(
    (a, b) => ORDER[a.status] - ORDER[b.status] || b.max_marks - a.max_marks,
  )

  const covered = scores.filter((s) => s.status === 'COVERED').length
  const earned = scores.reduce((s, c) => s + c.marks, 0)
  const total = scores.reduce((s, c) => s + c.max_marks, 0)

  return (
    <div>
      <div className="text-muted-foreground flex items-center justify-between border-b pb-2 text-xs">
        <span>
          {covered} of {scores.length} concepts covered
        </span>
        <span className="font-mono">
          {earned.toFixed(2)} / {total.toFixed(2)} from concepts
        </span>
      </div>
      <div className="divide-y">
        {sorted.map((score) => (
          <ConceptBar key={score.id} score={score} showEvidence={showEvidence} />
        ))}
      </div>
    </div>
  )
}
