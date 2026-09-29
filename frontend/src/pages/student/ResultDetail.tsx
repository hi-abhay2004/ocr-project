import { Link, useParams } from 'react-router-dom'
import { MessageSquare } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AnnotationSummary } from '@/components/AnnotationSummary'
import { ConceptBarList } from '@/components/ConceptBarList'
import { FeedbackPanel } from '@/components/FeedbackPanel'
import { ErrorState } from '@/components/states/ErrorState'
import { Loading } from '@/components/states/Loading'
import { useStudentResult } from '@/hooks/useStudentResults'

/**
 * Read-only student view (§8 screen 12).
 *
 * Three things are deliberately absent: no override controls, no scanned crops,
 * and no retrieved evidence quotes. The server enforces all three by serialising
 * a reduced payload — this component simply never asks for them, which is the
 * correct division: the omission here is UX, the omission there is the boundary.
 */
export function ResultDetail() {
  const sheetId = Number(useParams().sheetId)
  const { data: sheet, isPending, error, refetch } = useStudentResult(sheetId)

  if (isPending) return <Loading />
  if (error) return <ErrorState error={error} title="This result is not available" onRetry={() => void refetch()} />
  if (!sheet) return null

  return (
    <div className="space-y-5">
      <div>
        <Link to="/results" className="text-muted-foreground text-sm hover:underline">
          ← All results
        </Link>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <h1 className="text-2xl font-semibold">{sheet.exam_name}</h1>
          <p className="font-mono text-2xl font-semibold">
            {sheet.total_marks}
            <span className="text-muted-foreground text-base"> / {sheet.max_marks}</span>
          </p>
        </div>
      </div>

      {sheet.evaluations.map((evaluation) => {
        const effective = evaluation.override_marks ?? evaluation.auto_marks
        const annotations = evaluation.blocks.flatMap((b) => b.annotations)

        return (
          <Card key={evaluation.id}>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <CardTitle className="text-base leading-snug">
                  <span className="text-muted-foreground font-mono">
                    Q{evaluation.question_number}
                  </span>{' '}
                  {evaluation.question_text}
                </CardTitle>
                <p className="shrink-0 font-mono text-lg font-semibold">
                  {effective}
                  <span className="text-muted-foreground text-sm"> / {evaluation.max_marks}</span>
                </p>
              </div>
            </CardHeader>

            <CardContent className="space-y-5">
              {evaluation.override_comment && (
                <div className="flex gap-2 rounded-lg border border-blue-600/30 bg-blue-50/60 p-3 dark:bg-blue-950/20">
                  <MessageSquare className="mt-0.5 size-4 shrink-0 text-blue-700 dark:text-blue-400" />
                  <div>
                    <p className="text-sm font-medium text-blue-700 dark:text-blue-400">
                      Note from your teacher
                    </p>
                    <p className="mt-0.5 text-sm">{evaluation.override_comment}</p>
                  </div>
                </div>
              )}

              <div>
                <p className="mb-2 text-sm font-medium">How your answer was marked</p>
                {/* showEvidence stays false: the retrieved chunks are the
                    teacher's audit trail, not part of the student's feedback. */}
                <ConceptBarList scores={evaluation.concept_scores} />
              </div>

              {annotations.length > 0 && (
                <div>
                  <p className="mb-2 text-sm font-medium">Corrections detected on your script</p>
                  <AnnotationSummary annotations={annotations} />
                </div>
              )}

              <div>
                <p className="mb-2 text-sm font-medium">Feedback</p>
                <FeedbackPanel feedback={evaluation.feedback} />
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
