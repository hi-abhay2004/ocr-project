import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

export interface ScoreOverrideFormProps {
  evaluationId: number
  /** The machine mark. Never mutated — an override is stored alongside it. */
  autoMarks: number
  currentOverride: number | null
  currentComment: string | null
  maxMarks: number
  onSave: (input: { override_marks: number; override_comment: string }) => void
  onClear: () => void
  saving?: boolean
}

export function ScoreOverrideForm({
  evaluationId,
  autoMarks,
  currentOverride,
  currentComment,
  maxMarks,
  onSave,
  onClear,
  saving = false,
}: ScoreOverrideFormProps) {
  // Built per-instance because maxMarks varies by question.
  const schema = z.object({
    override_marks: z.coerce
      .number({ message: 'Enter a number' })
      .min(0, 'Cannot be negative')
      .max(maxMarks, `Cannot exceed ${maxMarks}`),
    override_comment: z.string().max(500, 'Keep it under 500 characters'),
  })
  type Values = z.input<typeof schema>

  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: {
      override_marks: (currentOverride ?? autoMarks) as unknown as Values['override_marks'],
      override_comment: currentComment ?? '',
    },
  })

  // Switching questions inside ReviewDetail remounts nothing — reset explicitly
  // or the previous question's mark stays in the field.
  const { reset } = form
  useEffect(() => {
    reset({
      override_marks: (currentOverride ?? autoMarks) as unknown as Values['override_marks'],
      override_comment: currentComment ?? '',
    })
  }, [evaluationId, currentOverride, currentComment, autoMarks, reset])

  const errors = form.formState.errors

  return (
    <form
      onSubmit={form.handleSubmit((v) =>
        onSave({ override_marks: Number(v.override_marks), override_comment: v.override_comment ?? '' }),
      )}
      className="flex flex-wrap items-end gap-3"
      noValidate
    >
      <div className="w-28 space-y-1.5">
        <Label htmlFor={`marks-${evaluationId}`} className="text-xs">
          Final marks
        </Label>
        <Input
          id={`marks-${evaluationId}`}
          type="number"
          step="0.25"
          min={0}
          max={maxMarks}
          aria-invalid={!!errors.override_marks}
          {...form.register('override_marks')}
        />
      </div>

      <div className="min-w-[12rem] flex-1 space-y-1.5">
        <Label htmlFor={`comment-${evaluationId}`} className="text-xs">
          Comment <span className="text-muted-foreground">(the student sees this)</span>
        </Label>
        <Textarea
          id={`comment-${evaluationId}`}
          rows={1}
          className="min-h-9 resize-y"
          placeholder="Why you changed the mark…"
          {...form.register('override_comment')}
        />
      </div>

      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={saving}>
          {saving && <Loader2 className="size-4 animate-spin" />}
          Save override
        </Button>
        {currentOverride !== null && (
          <Button type="button" variant="outline" size="sm" onClick={onClear} disabled={saving}>
            <RotateCcw className="size-3.5" />
            Reset to {autoMarks}
          </Button>
        )}
      </div>

      {(errors.override_marks || errors.override_comment) && (
        <p className="text-destructive w-full text-sm">
          {errors.override_marks?.message ?? errors.override_comment?.message}
        </p>
      )}
    </form>
  )
}
