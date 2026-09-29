import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, Plus, Trash2, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Card, CardContent } from '@/components/ui/card'
import { CsvImportDialog } from '@/components/CsvImportDialog'
import { Empty } from '@/components/states/Empty'
import { ErrorState } from '@/components/states/ErrorState'
import { TableSkeleton } from '@/components/states/Loading'
import { useAddStudent, useImportStudents, useRemoveStudent, useStudents } from '@/hooks/useStudents'

const schema = z.object({
  usn: z.string().regex(/^[0-9A-Za-z]{6,15}$/, 'USN looks malformed'),
  name: z.string().min(2, 'Name is required'),
  email: z.email('Not a valid email').or(z.literal('')),
})
type Values = z.infer<typeof schema>

export function StudentManage() {
  const examId = Number(useParams().examId)
  const { data: students, isPending, error, refetch } = useStudents(examId)
  const add = useAddStudent(examId)
  const importStudents = useImportStudents(examId)
  const remove = useRemoveStudent(examId)
  const [adding, setAdding] = useState(false)

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { usn: '', name: '', email: '' },
  })

  async function submit(values: Values) {
    await add.mutateAsync(values)
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
          <h1 className="mt-1 text-2xl font-semibold">Students</h1>
          <p className="text-muted-foreground text-sm">
            Every uploaded answer sheet is attached to one of these students.
          </p>
        </div>
        <div className="flex gap-2">
          <CsvImportDialog
            onImport={(rows) => importStudents.mutateAsync(rows)}
            importing={importStudents.isPending}
          />
          <Button onClick={() => setAdding((a) => !a)}>
            <Plus className="size-4" />
            Add student
          </Button>
        </div>
      </div>

      {adding && (
        <Card>
          <CardContent>
            <form
              onSubmit={form.handleSubmit(submit)}
              noValidate
              className="flex flex-wrap items-end gap-3"
            >
              <div className="w-40 space-y-1.5">
                <Label htmlFor="usn">USN</Label>
                <Input id="usn" placeholder="1BY22CS001" {...form.register('usn')} />
              </div>
              <div className="min-w-40 flex-1 space-y-1.5">
                <Label htmlFor="name">Name</Label>
                <Input id="name" {...form.register('name')} />
              </div>
              <div className="min-w-48 flex-1 space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" {...form.register('email')} />
              </div>
              <Button type="submit" disabled={add.isPending}>
                {add.isPending && <Loader2 className="size-4 animate-spin" />}
                Add
              </Button>
              {(errors.usn || errors.name || errors.email) && (
                <p className="text-destructive w-full text-sm">
                  {errors.usn?.message ?? errors.name?.message ?? errors.email?.message}
                </p>
              )}
            </form>
          </CardContent>
        </Card>
      )}

      {isPending && <TableSkeleton rows={5} cols={4} />}
      {error && <ErrorState error={error} onRetry={() => void refetch()} />}

      {students && students.length === 0 && (
        <Empty
          icon={Users}
          title="No students enrolled"
          hint="Import the class list as CSV — you get a preview of every parsed row before anything is saved."
        />
      )}

      {students && students.length > 0 && (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>USN</TableHead>
                <TableHead>Name</TableHead>
                <TableHead className="hidden sm:table-cell">Email</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {students.map((student) => (
                <TableRow key={student.id}>
                  <TableCell className="font-mono text-xs">{student.usn}</TableCell>
                  <TableCell className="text-sm font-medium">{student.name}</TableCell>
                  <TableCell className="text-muted-foreground hidden text-xs sm:table-cell">
                    {student.email || '—'}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      aria-label={`Remove ${student.name}`}
                      onClick={() => remove.mutate(student.id)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
