import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Empty } from '@/components/states/Empty'
import { ErrorState } from '@/components/states/ErrorState'
import { TableSkeleton } from '@/components/states/Loading'
import { useCreateExam, useExams } from '@/hooks/useExams'
import { ExamForm } from './ExamForm'

export function ExamList() {
  const { data: exams, isPending, error, refetch } = useExams()
  const create = useCreateExam()
  const [formOpen, setFormOpen] = useState(false)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Exams</h1>
          <p className="text-muted-foreground text-sm">
            Create an exam, add its questions and model answers, then upload answer sheets.
          </p>
        </div>
        <Button onClick={() => setFormOpen(true)}>
          <Plus className="size-4" />
          New exam
        </Button>
      </div>

      {isPending && <TableSkeleton rows={4} cols={5} />}
      {error && <ErrorState error={error} onRetry={() => void refetch()} />}

      {exams && exams.length === 0 && (
        <Empty
          icon={BookOpen}
          title="No exams yet"
          hint="An exam holds the questions, the class list and every uploaded answer sheet."
          action={
            <Button onClick={() => setFormOpen(true)}>
              <Plus className="size-4" />
              Create the first exam
            </Button>
          }
        />
      )}

      {exams && exams.length > 0 && (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Exam</TableHead>
                <TableHead className="hidden sm:table-cell">Subject</TableHead>
                <TableHead className="hidden md:table-cell">Date</TableHead>
                <TableHead className="text-right">Questions</TableHead>
                <TableHead className="text-right">Sheets</TableHead>
                <TableHead className="text-right">Avg mark</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {exams.map((exam) => (
                <TableRow key={exam.id} className="hover:bg-muted/50">
                  <TableCell className="font-medium">
                    <Link to={`/exams/${exam.id}`} className="hover:underline">
                      {exam.name}
                    </Link>
                    <span className="text-muted-foreground block text-xs sm:hidden">
                      {exam.subject}
                    </span>
                  </TableCell>
                  <TableCell className="text-muted-foreground hidden text-sm sm:table-cell">
                    {exam.subject}
                  </TableCell>
                  <TableCell className="text-muted-foreground hidden font-mono text-xs md:table-cell">
                    {exam.exam_date}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {exam.question_count}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">{exam.sheet_count}</TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {exam.avg_marks === null ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      `${exam.avg_marks.toFixed(1)} / ${exam.total_marks}`
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <ExamForm
        open={formOpen}
        onOpenChange={setFormOpen}
        onSubmit={(input) => create.mutateAsync(input)}
        saving={create.isPending}
      />
    </div>
  )
}
