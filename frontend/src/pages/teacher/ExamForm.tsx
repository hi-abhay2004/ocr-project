import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { ExamInput } from '@/api/exams'
import type { Exam } from '@/types/api'

const schema = z.object({
  name: z.string().min(3, 'Give the exam a recognisable name'),
  subject: z.string().min(2, 'Subject code or name is required'),
  exam_date: z.string().min(1, 'Pick a date'),
  total_marks: z.coerce.number().int('Whole numbers only').min(1, 'Must be at least 1').max(500),
})

type Values = z.input<typeof schema>

export function ExamForm({
  open,
  onOpenChange,
  exam,
  onSubmit,
  saving,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Present → edit mode. Absent → create mode. */
  exam?: Exam
  onSubmit: (input: ExamInput) => Promise<unknown>
  saving?: boolean
}) {
  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      subject: '',
      exam_date: new Date().toISOString().slice(0, 10),
      total_marks: 30 as unknown as Values['total_marks'],
    },
  })

  const { reset } = form
  useEffect(() => {
    if (!open) return
    reset(
      exam
        ? {
            name: exam.name,
            subject: exam.subject,
            exam_date: exam.exam_date,
            total_marks: exam.total_marks as unknown as Values['total_marks'],
          }
        : {
            name: '',
            subject: '',
            exam_date: new Date().toISOString().slice(0, 10),
            total_marks: 30 as unknown as Values['total_marks'],
          },
    )
  }, [open, exam, reset])

  const errors = form.formState.errors

  async function submit(values: Values) {
    await onSubmit({
      name: values.name,
      subject: values.subject,
      exam_date: values.exam_date,
      total_marks: Number(values.total_marks),
    })
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{exam ? 'Edit exam' : 'New exam'}</DialogTitle>
          <DialogDescription>
            {exam
              ? 'Changing these details does not re-evaluate any sheets.'
              : 'Add questions and a class list after creating this.'}
          </DialogDescription>
        </DialogHeader>

        <form
          id="exam-form"
          onSubmit={form.handleSubmit(submit as never)}
          noValidate
          className="space-y-4"
        >
          <div className="space-y-2">
            <Label htmlFor="name">Exam name</Label>
            <Input
              id="name"
              placeholder="CIE-2 Database Management Systems"
              aria-invalid={!!errors.name}
              {...form.register('name')}
            />
            {errors.name && <p className="text-destructive text-sm">{errors.name.message}</p>}
          </div>

          <div className="space-y-2">
            <Label htmlFor="subject">Subject</Label>
            <Input
              id="subject"
              placeholder="22CS52 · DBMS"
              aria-invalid={!!errors.subject}
              {...form.register('subject')}
            />
            {errors.subject && <p className="text-destructive text-sm">{errors.subject.message}</p>}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="exam_date">Date</Label>
              <Input
                id="exam_date"
                type="date"
                aria-invalid={!!errors.exam_date}
                {...form.register('exam_date')}
              />
              {errors.exam_date && (
                <p className="text-destructive text-sm">{errors.exam_date.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="total_marks">Total marks</Label>
              <Input
                id="total_marks"
                type="number"
                min={1}
                aria-invalid={!!errors.total_marks}
                {...form.register('total_marks')}
              />
              {errors.total_marks && (
                <p className="text-destructive text-sm">{errors.total_marks.message}</p>
              )}
            </div>
          </div>
        </form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="exam-form" disabled={saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            {exam ? 'Save changes' : 'Create exam'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
