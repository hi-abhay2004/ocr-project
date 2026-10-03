import { useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { FileImage, Loader2, RotateCw, Upload, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PipelineProgress } from '@/components/PipelineProgress'
import { ErrorState } from '@/components/states/ErrorState'
import { useCancelSheet, useRetrySheet, useSheetStatus, useUploadSheet } from '@/hooks/useSheets'
import { useStudents } from '@/hooks/useStudents'
import { cn } from '@/lib/utils'

const MAX_BYTES = 10 * 1024 * 1024
const ACCEPTED = ['image/jpeg', 'image/png', 'application/pdf']

export function SheetUpload() {
  const examId = Number(useParams().examId)
  const { data: students, isPending: studentsPending, error: studentsError } = useStudents(examId)
  const upload = useUploadSheet(examId)
  const retry = useRetrySheet(examId)
  const cancel = useCancelSheet(examId)

  const [studentId, setStudentId] = useState<string>('')
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [percent, setPercent] = useState(0)
  const [sheetId, setSheetId] = useState<number | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Polling starts the moment we have a sheet id and stops itself on a terminal
  // status — see useSheetStatus.
  const status = useSheetStatus(sheetId, examId)

  function addFiles(incoming: FileList | null) {
    if (!incoming) return
    const accepted: File[] = []
    for (const file of Array.from(incoming)) {
      if (!ACCEPTED.includes(file.type)) {
        toast.error(`${file.name}: only JPG, PNG and PDF are accepted`)
        continue
      }
      if (file.size > MAX_BYTES) {
        // Checked client-side so a 10 MB upload isn't wasted before the server
        // rejects it — on a college Wi-Fi that is a minute of the teacher's time.
        toast.error(`${file.name}: larger than 10 MB`)
        continue
      }
      accepted.push(file)
    }
    setFiles((prev) => [...prev, ...accepted])
  }

  async function submit() {
    if (!studentId || files.length === 0) return
    setPercent(0)
    const sheet = await upload.mutateAsync({
      studentId: Number(studentId),
      files,
      onProgress: setPercent,
    })
    setSheetId(sheet.id)
    setFiles([])
    if (inputRef.current) inputRef.current.value = ''
  }

  function startAnother() {
    setSheetId(null)
    setStudentId('')
    setPercent(0)
  }

  const uploading = upload.isPending
  const terminal = status.isTerminal
  const failed = status.data?.status === 'FAILED'

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/exams/${examId}`} className="text-muted-foreground text-sm hover:underline">
          ← Back to exam
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">Upload answer sheets</h1>
        <p className="text-muted-foreground text-sm">
          Upload every page of one student's answer script together. Evaluation starts immediately
          and runs in the background.
        </p>
      </div>

      {studentsError && <ErrorState error={studentsError} />}

      {sheetId === null ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">New sheet</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="max-w-sm space-y-2">
              <Label htmlFor="student">Student</Label>
              <Select value={studentId} onValueChange={setStudentId} disabled={studentsPending}>
                <SelectTrigger id="student" className="w-full">
                  <SelectValue placeholder={studentsPending ? 'Loading…' : 'Choose a student'} />
                </SelectTrigger>
                <SelectContent>
                  {students?.map((student) => (
                    <SelectItem key={student.id} value={String(student.id)}>
                      <span className="font-mono text-xs">{student.usn}</span> · {student.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {students?.length === 0 && (
                <p className="text-muted-foreground text-sm">
                  No students enrolled.{' '}
                  <Link to={`/exams/${examId}/students`} className="underline">
                    Add the class list first
                  </Link>
                  .
                </p>
              )}
            </div>

            <div
              onDragOver={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                addFiles(e.dataTransfer.files)
              }}
              className={cn(
                'flex flex-col items-center gap-3 rounded-lg border-2 border-dashed p-10 text-center transition-colors',
                dragging && 'border-primary bg-primary/5',
              )}
            >
              <Upload className="text-muted-foreground size-8" />
              <p className="text-sm">Drop scanned pages here</p>
              <p className="text-muted-foreground text-xs">JPG, PNG or PDF · up to 10 MB each</p>
              <input
                ref={inputRef}
                type="file"
                multiple
                accept="image/jpeg,image/png,application/pdf"
                className="hidden"
                aria-label="Choose answer sheet pages"
                onChange={(e) => addFiles(e.target.files)}
              />
              <Button variant="secondary" size="sm" onClick={() => inputRef.current?.click()}>
                Choose files
              </Button>
            </div>

            {files.length > 0 && (
              <ul className="divide-y rounded-md border">
                {files.map((file, i) => (
                  <li key={i} className="flex items-center gap-3 px-3 py-2 text-sm">
                    <FileImage className="text-muted-foreground size-4 shrink-0" />
                    <span className="flex-1 truncate">{file.name}</span>
                    <span className="text-muted-foreground shrink-0 font-mono text-xs">
                      {(file.size / 1024 / 1024).toFixed(1)} MB
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Remove ${file.name}`}
                      onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                    >
                      <X className="size-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}

            {uploading && <Progress value={percent} />}

            <Button onClick={submit} disabled={!studentId || files.length === 0 || uploading}>
              {uploading && <Loader2 className="size-4 animate-spin" />}
              Upload {files.length > 0 && `${files.length} page${files.length === 1 ? '' : 's'}`}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Evaluating sheet #{sheetId}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {status.data && (
              <PipelineProgress
                stage={status.data.stage}
                status={status.data.status}
                startedAt={status.data.last_run_started_at ?? status.data.started_at}
                errorMessage={status.data.error_message}
              />
            )}

            <div className="flex flex-wrap gap-2">
              {terminal && !failed && (
                <Button asChild>
                  <Link to={`/sheets/${sheetId}`}>Review this sheet</Link>
                </Button>
              )}
              {failed && (
                <Button variant="outline" onClick={() => retry.mutate(sheetId)}>
                  <RotateCw className="size-4" />
                  Retry evaluation
                </Button>
              )}
              {!terminal && sheetId && (
                <Button variant="outline" onClick={() => cancel.mutate(sheetId)} disabled={cancel.isPending}>
                  Cancel evaluation
                </Button>
              )}
              <Button variant={terminal ? 'outline' : 'secondary'} onClick={startAnother}>
                Upload another sheet
              </Button>
              <Button variant="ghost" asChild>
                <Link to={`/exams/${examId}/review`}>Go to review queue</Link>
              </Button>
            </div>

            {!terminal && (
              <p className="text-muted-foreground text-xs">
                You can leave this page — evaluation continues in the background and the sheet will
                appear in the review queue when it finishes.
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
