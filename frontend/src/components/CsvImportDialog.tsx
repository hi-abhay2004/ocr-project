import { useRef, useState } from 'react'
import { AlertTriangle, FileUp, Loader2, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { CsvRow } from '@/types/api'

/**
 * CSV import with a MANDATORY preview step (§8 screen 5).
 *
 * The preview is the whole point: a class list pasted from a spreadsheet
 * routinely carries a header row, trailing blank lines, or a USN column that is
 * actually a roll number. Importing blind creates students nobody can match to
 * a sheet later, and unpicking that is worse than re-importing.
 */

const HEADER_ALIASES: Record<string, keyof Omit<CsvRow, 'error'>> = {
  usn: 'usn',
  'usn no': 'usn',
  'university seat number': 'usn',
  reg: 'usn',
  'reg no': 'usn',
  name: 'name',
  'student name': 'name',
  'full name': 'name',
  email: 'email',
  'email id': 'email',
  mail: 'email',
}

const USN_RE = /^[0-9A-Z]{6,15}$/i
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Handles quoted fields, which Excel emits whenever a name contains a comma. */
function splitCsvLine(line: string): string[] {
  const out: string[] = []
  let cur = ''
  let quoted = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') {
        cur += '"'
        i++
      } else if (ch === '"') quoted = false
      else cur += ch
    } else if (ch === '"') quoted = true
    else if (ch === ',') {
      out.push(cur.trim())
      cur = ''
    } else cur += ch
  }
  out.push(cur.trim())
  return out
}

export function parseCsv(text: string): CsvRow[] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0)
  if (lines.length === 0) return []

  const first = splitCsvLine(lines[0]).map((h) => h.toLowerCase().replace(/[_-]+/g, ' ').trim())
  const mapped = first.map((h) => HEADER_ALIASES[h])
  const hasHeader = mapped.filter(Boolean).length >= 2

  // No recognisable header → assume positional usn,name,email.
  const columns: (keyof Omit<CsvRow, 'error'> | undefined)[] = hasHeader
    ? mapped
    : ['usn', 'name', 'email']

  const body = hasHeader ? lines.slice(1) : lines
  const seen = new Set<string>()

  return body.map((line) => {
    const cells = splitCsvLine(line)
    const row: CsvRow = { usn: '', name: '', email: '' }
    columns.forEach((key, i) => {
      if (key) row[key] = cells[i] ?? ''
    })

    if (!row.usn) row.error = 'USN is missing'
    else if (!USN_RE.test(row.usn)) row.error = 'USN looks malformed'
    else if (seen.has(row.usn.toUpperCase())) row.error = 'Duplicate USN in this file'
    else if (!row.name) row.error = 'Name is missing'
    else if (row.email && !EMAIL_RE.test(row.email)) row.error = 'Email is not valid'

    if (!row.error) seen.add(row.usn.toUpperCase())
    return row
  })
}

export function CsvImportDialog({
  onImport,
  importing = false,
}: {
  onImport: (rows: { usn: string; name: string; email: string }[]) => Promise<unknown> | unknown
  importing?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState<CsvRow[] | null>(null)
  const [fileName, setFileName] = useState('')
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const valid = rows?.filter((r) => !r.error) ?? []
  const invalid = rows?.filter((r) => r.error) ?? []

  async function handleFile(file: File) {
    setFileName(file.name)
    setRows(parseCsv(await file.text()))
  }

  function reset() {
    setRows(null)
    setFileName('')
    if (inputRef.current) inputRef.current.value = ''
  }

  async function confirm() {
    await onImport(valid.map(({ usn, name, email }) => ({ usn, name, email })))
    reset()
    setOpen(false)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (!o) reset()
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <FileUp className="size-4" />
          Import CSV
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import students from CSV</DialogTitle>
          <DialogDescription>
            Columns <code className="font-mono">usn, name, email</code>. A header row is detected
            automatically. Nothing is sent until you confirm the preview.
          </DialogDescription>
        </DialogHeader>

        {!rows ? (
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              const file = e.dataTransfer.files[0]
              if (file) void handleFile(file)
            }}
            className={cn(
              'flex flex-col items-center gap-3 rounded-lg border-2 border-dashed p-10 text-center transition-colors',
              dragging && 'border-primary bg-primary/5',
            )}
          >
            <Upload className="text-muted-foreground size-8" />
            <p className="text-sm">Drop a .csv file here</p>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              aria-label="Choose a CSV file"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void handleFile(file)
              }}
            />
            <Button variant="secondary" size="sm" onClick={() => inputRef.current?.click()}>
              Choose file
            </Button>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="font-medium">{fileName}</span>
              <span className="text-green-700 dark:text-green-400">{valid.length} importable</span>
              {invalid.length > 0 && (
                <span className="flex items-center gap-1 text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="size-3.5" />
                  {invalid.length} will be skipped
                </span>
              )}
              <Button variant="ghost" size="sm" className="ml-auto" onClick={reset}>
                Choose a different file
              </Button>
            </div>

            <div className="max-h-72 overflow-auto rounded-md border">
              <Table>
                <TableHeader className="bg-muted/50 sticky top-0">
                  <TableRow>
                    <TableHead className="w-10">#</TableHead>
                    <TableHead>USN</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row, i) => (
                    <TableRow key={i} className={cn(row.error && 'bg-destructive/5')}>
                      <TableCell className="text-muted-foreground font-mono text-xs">{i + 1}</TableCell>
                      <TableCell className="font-mono text-xs">{row.usn || '—'}</TableCell>
                      <TableCell className="text-sm">{row.name || '—'}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">{row.email || '—'}</TableCell>
                      <TableCell className="text-xs">
                        {row.error ? (
                          <span className="text-destructive">{row.error}</span>
                        ) : (
                          <span className="text-green-700 dark:text-green-400">OK</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={confirm} disabled={valid.length === 0 || importing}>
            {importing && <Loader2 className="size-4 animate-spin" />}
            Import {valid.length} student{valid.length === 1 ? '' : 's'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
