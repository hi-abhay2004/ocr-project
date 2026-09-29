import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BarChart3, ClipboardCheck, FileQuestion, Pencil, Upload, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorState } from '@/components/states/ErrorState'
import { Loading } from '@/components/states/Loading'
import { useExam, useUpdateExam } from '@/hooks/useExams'
import { useQuestions } from '@/hooks/useQuestions'
import { useStudents } from '@/hooks/useStudents'
import { ExamForm } from './ExamForm'

/** Hub for one exam — the four things a teacher does, in the order they do them. */
export function ExamDetail() {
  const examId = Number(useParams().examId)
  const { data: exam, isPending, error, refetch } = useExam(examId)
  const { data: questions } = useQuestions(examId)
  const { data: students } = useStudents(examId)
  const update = useUpdateExam(examId)
  const [editing, setEditing] = useState(false)

  if (isPending) return <Loading />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />
  if (!exam) return null

  const steps = [
    {
      to: `/exams/${examId}/questions`,
      icon: FileQuestion,
      title: 'Questions & model answers',
      description:
        questions === undefined
          ? 'Loading…'
          : questions.length === 0
            ? 'None yet — start here'
            : `${questions.length} question${questions.length === 1 ? '' : 's'}`,
    },
    {
      to: `/exams/${examId}/students`,
      icon: Users,
      title: 'Students',
      description:
        students === undefined
          ? 'Loading…'
          : students.length === 0
            ? 'No class list yet'
            : `${students.length} enrolled`,
    },
    {
      to: `/exams/${examId}/upload`,
      icon: Upload,
      title: 'Upload answer sheets',
      description: 'Scan or photograph, then watch the pipeline run',
    },
    {
      to: `/exams/${examId}/review`,
      icon: ClipboardCheck,
      title: 'Review & approve',
      description: `${exam.sheet_count} sheet${exam.sheet_count === 1 ? '' : 's'} evaluated`,
    },
    {
      to: `/exams/${examId}/summary`,
      icon: BarChart3,
      title: 'Class analytics',
      description: 'Mark distribution and most-missed concepts',
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/exams" className="text-muted-foreground text-sm hover:underline">
            ← All exams
          </Link>
          <h1 className="mt-1 text-2xl font-semibold">{exam.name}</h1>
          <p className="text-muted-foreground text-sm">
            {exam.subject} · {exam.exam_date} · {exam.total_marks} marks
          </p>
        </div>
        <Button variant="outline" onClick={() => setEditing(true)}>
          <Pencil className="size-4" />
          Edit
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {steps.map(({ to, icon: Icon, title, description }) => (
          <Link key={to} to={to} className="group">
            <Card className="hover:border-primary/50 h-full transition-colors">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Icon className="text-muted-foreground group-hover:text-foreground size-4 transition-colors" />
                  {title}
                </CardTitle>
                <CardDescription>{description}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>

      <ExamForm
        open={editing}
        onOpenChange={setEditing}
        exam={exam}
        onSubmit={(input) => update.mutateAsync(input)}
        saving={update.isPending}
      />
    </div>
  )
}
