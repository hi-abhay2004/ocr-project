import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { AlertTriangle, FileQuestion, Loader2, Plus, Sparkles, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Empty } from '@/components/states/Empty'
import { ErrorState } from '@/components/states/ErrorState'
import { Loading } from '@/components/states/Loading'
import {
  useConcepts,
  useCreateQuestion,
  useDeleteQuestion,
  useQuestions,
  useUpdateQuestion,
} from '@/hooks/useQuestions'
import type { Question } from '@/types/api'

const schema = z.object({
  number: z.string().min(1, 'e.g. 1a'),
  text: z.string().min(5, 'Write the question as it appeared on the paper'),
  max_marks: z.coerce.number().min(0.5, 'At least 0.5').max(100),
  model_answer: z.string().min(30, 'The model answer needs enough substance to extract concepts from'),
})
type Values = z.input<typeof schema>

export function QuestionEditor() {
  const examId = Number(useParams().examId)
  const { data: questions, isPending, error, refetch } = useQuestions(examId)
  const create = useCreateQuestion(examId)
  const [adding, setAdding] = useState(false)

  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: {
      number: '',
      text: '',
      max_marks: 10 as unknown as Values['max_marks'],
      model_answer: '',
    },
  })

  async function submit(values: Values) {
    await create.mutateAsync({
      number: values.number,
      text: values.text,
      max_marks: Number(values.max_marks),
      model_answer: values.model_answer,
    })
    form.reset()
    setAdding(false)
  }

  const errors = form.formState.errors

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to={`/exams/${examId}`} className="text-muted-foreground text-sm hover:underline">
            ← Back to exam
          </Link>
          <h1 className="mt-1 text-2xl font-semibold">Questions & model answers</h1>
          <p className="text-muted-foreground text-sm">
            Each model answer is broken into weighted concepts by the language model. Those concepts
            are what every student answer is scored against.
          </p>
        </div>
        {!adding && (
          <Button onClick={() => setAdding(true)}>
            <Plus className="size-4" />
            Add question
          </Button>
        )}
      </div>

      {adding && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">New question</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={form.handleSubmit(submit as never)} noValidate className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-[8rem_1fr]">
                <div className="space-y-2">
                  <Label htmlFor="number">Number</Label>
                  <Input id="number" placeholder="1a" {...form.register('number')} />
                  {errors.number && (
                    <p className="text-destructive text-sm">{errors.number.message}</p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="max_marks">Max marks</Label>
                  <Input
                    id="max_marks"
                    type="number"
                    step="0.5"
                    className="sm:w-32"
                    {...form.register('max_marks')}
                  />
                  {errors.max_marks && (
                    <p className="text-destructive text-sm">{errors.max_marks.message}</p>
                  )}
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="text">Question</Label>
                <Textarea id="text" rows={2} {...form.register('text')} />
                {errors.text && <p className="text-destructive text-sm">{errors.text.message}</p>}
              </div>

              <div className="space-y-2">
                <Label htmlFor="model_answer">Model answer</Label>
                <Textarea
                  id="model_answer"
                  rows={6}
                  placeholder="Write the full expected answer. Concepts are extracted from this text."
                  {...form.register('model_answer')}
                />
                {errors.model_answer && (
                  <p className="text-destructive text-sm">{errors.model_answer.message}</p>
                )}
              </div>

              <div className="flex gap-2">
                <Button type="submit" disabled={create.isPending}>
                  {create.isPending && <Loader2 className="size-4 animate-spin" />}
                  Save question
                </Button>
                <Button type="button" variant="ghost" onClick={() => setAdding(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {isPending && <Loading />}
      {error && <ErrorState error={error} onRetry={() => void refetch()} />}

      {questions && questions.length === 0 && !adding && (
        <Empty
          icon={FileQuestion}
          title="No questions yet"
          hint="Add each question from the paper along with the answer you would accept for full marks."
          action={
            <Button onClick={() => setAdding(true)}>
              <Plus className="size-4" />
              Add the first question
            </Button>
          }
        />
      )}

      <div className="space-y-4">
        {questions?.map((question) => (
          <QuestionCard key={question.id} examId={examId} question={question} />
        ))}
      </div>
    </div>
  )
}

/* ── One question, with its concept table ─────────────────────────────── */

function QuestionCard({ examId, question }: { examId: number; question: Question }) {
  const { data: concepts, isPending } = useConcepts(question.id)
  const update = useUpdateQuestion(examId)
  const remove = useDeleteQuestion(examId)
  const [draft, setDraft] = useState(question.model_answer)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const dirty = draft !== question.model_answer
  // Extraction is in flight until the concepts array itself is non-empty —
  // see the comment on useConcepts for why this must not also check
  // question.concepts_indexed.
  const extracting = isPending || (concepts?.length ?? 0) === 0
  const weightSum = concepts?.reduce((s, c) => s + c.weight, 0) ?? 0

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">
              <span className="text-muted-foreground font-mono">Q{question.number}</span>{' '}
              {question.text}
            </CardTitle>
            <p className="text-muted-foreground mt-1 text-sm">{question.max_marks} marks</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive"
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor={`ma-${question.id}`}>Model answer</Label>
          <Textarea
            id={`ma-${question.id}`}
            rows={5}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          {dirty && (
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={() => setConfirmOpen(true)} disabled={update.isPending}>
                {update.isPending && <Loader2 className="size-4 animate-spin" />}
                Save model answer
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setDraft(question.model_answer)}>
                Discard
              </Button>
            </div>
          )}
        </div>

        {/* ── Extracted concepts ─────────────────────────────────────── */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <Sparkles className="size-4 text-violet-500" />
              Extracted concepts
            </p>
            {!extracting && (
              <Badge
                variant={Math.abs(weightSum - 1) < 0.01 ? 'secondary' : 'destructive'}
                className="font-mono text-xs"
              >
                Σ weight {weightSum.toFixed(2)}
              </Badge>
            )}
          </div>

          {extracting ? (
            // The skeleton is not decoration. Extraction runs in a Celery task
            // and the POST returns before the LLM has produced anything; without
            // this the teacher sees an empty table and assumes the save failed.
            <div className="space-y-2" data-testid="extracting-skeleton">
              <p className="text-muted-foreground flex items-center gap-2 text-sm">
                <Loader2 className="size-3.5 animate-spin" />
                Extracting concepts from the model answer…
              </p>
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-3">
                  <Skeleton className="h-4 flex-1" />
                  <Skeleton className="h-4 w-16" />
                </div>
              ))}
            </div>
          ) : (
            <div className="divide-y rounded-md border">
              {concepts?.map((concept) => (
                <div key={concept.id} className="flex items-center gap-3 px-3 py-2">
                  <span className="flex-1 text-sm">{concept.text}</span>
                  <div className="bg-muted h-1.5 w-24 overflow-hidden rounded-full">
                    <div
                      className="h-full rounded-full bg-violet-500"
                      style={{ width: `${concept.weight * 100}%` }}
                    />
                  </div>
                  <span className="text-muted-foreground w-10 text-right font-mono text-xs">
                    {concept.weight.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>

      {/* Re-index warning — the consequence is not obvious from the button. */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="size-5 text-amber-600" />
              This re-indexes concepts for every student
            </DialogTitle>
            <DialogDescription>
              Saving a new model answer discards the current concepts, extracts a fresh set, and
              re-embeds them. Sheets already evaluated against the old concepts keep their marks —
              re-run them if you want the new concepts applied.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={async () => {
                await update.mutateAsync({ id: question.id, input: { model_answer: draft } })
                setConfirmOpen(false)
              }}
            >
              Save and re-index
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete question {question.number}?</DialogTitle>
            <DialogDescription>
              Its concepts and every score derived from them are removed. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                await remove.mutateAsync(question.id)
                setConfirmDelete(false)
              }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
