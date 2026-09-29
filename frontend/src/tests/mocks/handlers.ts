import { HttpResponse, http, delay } from 'msw'
import {
  USERS,
  concepts,
  createSheet,
  enrolment,
  exams,
  nextMockId,
  questions,
  recomputeSheet,
  sheets,
  students,
  studentResultsFor,
  summaryFor,
  toListItem,
} from './db'
import type { Question, Role, Student } from '@/types/api'

/**
 * MSW handlers — a runnable stand-in for the whole Django API.
 *
 * Enabled in the browser with VITE_USE_MSW=true. Every endpoint here matches the
 * §8 contract exactly; when Phase 4 lands, flip the flag off and nothing else
 * changes. If a screen breaks at that point, the contract drifted — which is the
 * feedback this layer exists to give.
 */

const LATENCY = 250

/** Fake bearer token. Real backend issues a signed JWT; shape is irrelevant here. */
const tokenFor = (username: string) => `mock.${username}.${Date.now()}`

function userFromRequest(request: Request) {
  const auth = request.headers.get('Authorization')
  if (!auth?.startsWith('Bearer ')) return null
  const username = auth.slice(7).split('.')[1]
  const record = USERS[username]
  if (!record) return null
  const { password: _password, ...user } = record
  return user
}

function unauthorized() {
  return HttpResponse.json({ detail: 'Authentication credentials were not provided.' }, { status: 401 })
}

function forbidden() {
  return HttpResponse.json({ detail: 'You do not have permission to perform this action.' }, { status: 403 })
}

/** The logged-in STUDENT user maps to exactly one Student record.
 *  Extended at registration time so a freshly signed-up student resolves too. */
const STUDENT_RECORD_FOR_USER: Record<number, number> = { 2: 11 }

export const handlers = [
  /* ── Auth ───────────────────────────────────────────────────────────── */

  http.post('/api/auth/login/', async ({ request }) => {
    await delay(LATENCY)
    const { username } = (await request.json()) as { username: string; password: string }
    const record = USERS[username]
    if (!record) {
      return HttpResponse.json({ detail: 'No active account found with the given credentials' }, { status: 401 })
    }
    return HttpResponse.json({ access: tokenFor(username), refresh: `refresh.${username}` })
  }),

  http.post('/api/auth/register/', async ({ request }) => {
    await delay(LATENCY)
    const body = (await request.json()) as {
      username: string
      full_name: string
      email: string
      password: string
      role: Role
      usn?: string
    }

    // Field-keyed 400s, matching DRF's error shape — errorMessage() in
    // lib/axios.ts unwraps exactly this, so the signup form shows the real
    // reason rather than a generic failure.
    if (USERS[body.username]) {
      return HttpResponse.json({ username: ['A user with that username already exists.'] }, { status: 400 })
    }
    if (body.role === 'STUDENT' && !body.usn) {
      return HttpResponse.json({ usn: ['This field is required for students.'] }, { status: 400 })
    }
    if (body.role === 'STUDENT' && students.some((s) => s.usn.toUpperCase() === body.usn?.toUpperCase())) {
      return HttpResponse.json({ usn: ['A student with this USN is already registered.'] }, { status: 400 })
    }

    const id = nextMockId()
    USERS[body.username] = {
      id,
      username: body.username,
      full_name: body.full_name,
      role: body.role,
      password: body.password,
    }

    if (body.role === 'STUDENT' && body.usn) {
      const student = { id: nextMockId(), usn: body.usn, name: body.full_name, email: body.email }
      students.push(student)
      enrolment[student.id] = []
      STUDENT_RECORD_FOR_USER[id] = student.id
    }

    return HttpResponse.json(
      { access: tokenFor(body.username), refresh: `refresh.${body.username}` },
      { status: 201 },
    )
  }),

  http.post('/api/auth/refresh/', async ({ request }) => {
    const { refresh } = (await request.json()) as { refresh: string }
    const username = refresh.split('.')[1]
    if (!USERS[username]) return HttpResponse.json({ detail: 'Token is invalid' }, { status: 401 })
    return HttpResponse.json({ access: tokenFor(username), refresh })
  }),

  http.get('/api/auth/me/', ({ request }) => {
    const user = userFromRequest(request)
    return user ? HttpResponse.json(user) : unauthorized()
  }),

  /* ── Exams ──────────────────────────────────────────────────────────── */

  http.get('/api/exams/', async ({ request }) => {
    const user = userFromRequest(request)
    if (!user) return unauthorized()
    if (user.role !== 'TEACHER') return forbidden()
    await delay(LATENCY)
    return HttpResponse.json(exams)
  }),

  http.get('/api/exams/:examId/', ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    const exam = exams.find((e) => e.id === Number(params.examId))
    return exam ? HttpResponse.json(exam) : HttpResponse.json({ detail: 'Not found.' }, { status: 404 })
  }),

  http.post('/api/exams/', async ({ request }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(LATENCY)
    const body = (await request.json()) as Record<string, never>
    const exam = {
      id: nextMockId(),
      ...body,
      question_count: 0,
      sheet_count: 0,
      avg_marks: null,
      created_at: new Date().toISOString(),
    } as (typeof exams)[number]
    exams.unshift(exam)
    return HttpResponse.json(exam, { status: 201 })
  }),

  http.patch('/api/exams/:examId/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    const exam = exams.find((e) => e.id === Number(params.examId))
    if (!exam) return HttpResponse.json({ detail: 'Not found.' }, { status: 404 })
    Object.assign(exam, await request.json())
    return HttpResponse.json(exam)
  }),

  http.delete('/api/exams/:examId/', ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    const i = exams.findIndex((e) => e.id === Number(params.examId))
    if (i >= 0) exams.splice(i, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/exams/:examId/summary/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(LATENCY)
    return HttpResponse.json(summaryFor(Number(params.examId)))
  }),

  http.get('/api/exams/:examId/sheets/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(LATENCY)
    const url = new URL(request.url)
    const band = url.searchParams.get('band')
    const status = url.searchParams.get('status')
    let rows = sheets.filter((s) => s.exam === Number(params.examId))
    if (band) rows = rows.filter((s) => s.band === band)
    if (status) rows = rows.filter((s) => s.status === status)
    return HttpResponse.json(rows.map(toListItem))
  }),

  /* ── Questions + concepts ───────────────────────────────────────────── */

  http.get('/api/exams/:examId/questions/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(LATENCY)
    return HttpResponse.json(questions.filter((q) => q.exam === Number(params.examId)))
  }),

  http.post('/api/exams/:examId/questions/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(LATENCY)
    const examId = Number(params.examId)
    const body = (await request.json()) as Record<string, never>
    const question = { id: nextMockId(), exam: examId, ...body, concepts_indexed: false } as Question
    questions.push(question)

    const exam = exams.find((e) => e.id === examId)
    if (exam) exam.question_count += 1

    // Mirrors the real async extraction: concepts do not exist when this returns.
    // QuestionEditor polls until they do — this delay is what makes that path
    // visible instead of instantly resolving.
    setTimeout(() => {
      const weights = [0.35, 0.3, 0.2, 0.15]
      weights.forEach((w, i) =>
        concepts.push({
          id: nextMockId(),
          question: question.id,
          text: `Key point ${i + 1} extracted from the model answer`,
          weight: w,
        }),
      )
      question.concepts_indexed = true
    }, 4000)

    return HttpResponse.json(question, { status: 201 })
  }),

  http.patch('/api/questions/:questionId/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    const q = questions.find((x) => x.id === Number(params.questionId))
    if (!q) return HttpResponse.json({ detail: 'Not found.' }, { status: 404 })
    const body = (await request.json()) as Partial<Question>
    Object.assign(q, body)
    if (body.model_answer !== undefined) {
      // Re-indexing invalidates the old concepts.
      q.concepts_indexed = false
      for (let i = concepts.length - 1; i >= 0; i--) {
        if (concepts[i].question === q.id) concepts.splice(i, 1)
      }
      setTimeout(() => {
        ;[0.4, 0.35, 0.25].forEach((w, i) =>
          concepts.push({
            id: nextMockId(),
            question: q.id,
            text: `Re-extracted key point ${i + 1}`,
            weight: w,
          }),
        )
        q.concepts_indexed = true
      }, 4000)
    }
    return HttpResponse.json(q)
  }),

  http.delete('/api/questions/:questionId/', ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    const i = questions.findIndex((q) => q.id === Number(params.questionId))
    if (i >= 0) {
      const examId = questions[i].exam
      questions.splice(i, 1)
      const exam = exams.find((e) => e.id === examId)
      if (exam) exam.question_count = Math.max(0, exam.question_count - 1)
    }
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/questions/:questionId/concepts/', ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    return HttpResponse.json(concepts.filter((c) => c.question === Number(params.questionId)))
  }),

  /* ── Students ───────────────────────────────────────────────────────── */

  http.get('/api/exams/:examId/students/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(LATENCY)
    const examId = Number(params.examId)
    return HttpResponse.json(students.filter((s) => (enrolment[s.id] ?? []).includes(examId)))
  }),

  http.post('/api/exams/:examId/students/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    const examId = Number(params.examId)
    const body = (await request.json()) as Omit<Student, 'id'>
    if (students.some((s) => s.usn === body.usn)) {
      return HttpResponse.json({ usn: ['A student with this USN already exists.'] }, { status: 400 })
    }
    const student = { id: nextMockId(), ...body }
    students.push(student)
    enrolment[student.id] = [examId]
    return HttpResponse.json(student, { status: 201 })
  }),

  http.delete('/api/exams/:examId/students/:studentId/', ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    const examId = Number(params.examId)
    const studentId = Number(params.studentId)
    enrolment[studentId] = (enrolment[studentId] ?? []).filter((e) => e !== examId)
    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/exams/:examId/students/import/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(LATENCY * 2)
    const examId = Number(params.examId)
    const { rows } = (await request.json()) as { rows: Omit<Student, 'id'>[] }
    let created = 0
    let skipped = 0
    const errors: { row: number; message: string }[] = []
    rows.forEach((row, i) => {
      const existing = students.find((s) => s.usn === row.usn)
      if (existing) {
        if (!(enrolment[existing.id] ?? []).includes(examId)) {
          enrolment[existing.id] = [...(enrolment[existing.id] ?? []), examId]
          created += 1
        } else {
          skipped += 1
          errors.push({ row: i + 1, message: `${row.usn} is already enrolled` })
        }
        return
      }
      const student = { id: nextMockId(), ...row }
      students.push(student)
      enrolment[student.id] = [examId]
      created += 1
    })
    return HttpResponse.json({ created, skipped, errors })
  }),

  /* ── Sheets ─────────────────────────────────────────────────────────── */

  http.post('/api/exams/:examId/sheets/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(LATENCY * 2)
    const form = await request.formData()
    const studentId = Number(form.get('student'))
    const sheet = createSheet(Number(params.examId), studentId)
    return HttpResponse.json(sheet, { status: 202 })
  }),

  http.get('/api/sheets/:sheetId/status/', ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    const sheet = sheets.find((s) => s.id === Number(params.sheetId))
    if (!sheet) return HttpResponse.json({ detail: 'Not found.' }, { status: 404 })
    return HttpResponse.json({
      id: sheet.id,
      status: sheet.status,
      stage: sheet.stage,
      started_at: sheet.started_at,
      error_message: sheet.error_message,
    })
  }),

  http.get('/api/sheets/:sheetId/', async ({ request, params }) => {
    const user = userFromRequest(request)
    if (!user) return unauthorized()
    if (user.role !== 'TEACHER') return forbidden()
    await delay(LATENCY)
    const sheet = sheets.find((s) => s.id === Number(params.sheetId))
    return sheet ? HttpResponse.json(sheet) : HttpResponse.json({ detail: 'Not found.' }, { status: 404 })
  }),

  http.post('/api/sheets/:sheetId/retry/', ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    const sheet = sheets.find((s) => s.id === Number(params.sheetId))
    if (!sheet) return HttpResponse.json({ detail: 'Not found.' }, { status: 404 })
    sheet.error_message = null
    createSheetRetry(sheet.id)
    return HttpResponse.json(sheet)
  }),

  http.post('/api/sheets/:sheetId/approve/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(LATENCY)
    const sheet = sheets.find((s) => s.id === Number(params.sheetId))
    if (!sheet) return HttpResponse.json({ detail: 'Not found.' }, { status: 404 })
    sheet.status = 'APPROVED'
    sheet.approved_at = new Date().toISOString()
    return HttpResponse.json(sheet)
  }),

  /* ── Evaluations ────────────────────────────────────────────────────── */

  http.patch('/api/evaluations/:evaluationId/', async ({ request, params }) => {
    if (!userFromRequest(request)) return unauthorized()
    await delay(LATENCY)
    const evaluationId = Number(params.evaluationId)
    const sheet = sheets.find((s) => s.evaluations.some((e) => e.id === evaluationId))
    const evaluation = sheet?.evaluations.find((e) => e.id === evaluationId)
    if (!sheet || !evaluation) return HttpResponse.json({ detail: 'Not found.' }, { status: 404 })

    const body = (await request.json()) as { override_marks: number | null; override_comment: string | null }
    if (body.override_marks !== null && body.override_marks !== undefined) {
      if (body.override_marks < 0 || body.override_marks > evaluation.max_marks) {
        return HttpResponse.json(
          { override_marks: [`Must be between 0 and ${evaluation.max_marks}.`] },
          { status: 400 },
        )
      }
    }
    evaluation.override_marks = body.override_marks ?? null
    evaluation.override_comment = body.override_comment ?? null
    recomputeSheet(sheet)
    return HttpResponse.json(evaluation)
  }),

  /* ── Student-facing ─────────────────────────────────────────────────── */

  http.get('/api/results/', async ({ request }) => {
    const user = userFromRequest(request)
    if (!user) return unauthorized()
    if (user.role !== 'STUDENT') return forbidden()
    await delay(LATENCY)
    return HttpResponse.json(studentResultsFor(STUDENT_RECORD_FOR_USER[user.id] ?? -1))
  }),

  http.get('/api/results/:sheetId/', async ({ request, params }) => {
    const user = userFromRequest(request)
    if (!user) return unauthorized()
    if (user.role !== 'STUDENT') return forbidden()
    await delay(LATENCY)
    const sheet = sheets.find((s) => s.id === Number(params.sheetId))
    // The two boundaries that MUST hold: another student's sheet is invisible,
    // and an unapproved sheet is invisible even to its owner.
    if (!sheet || sheet.student.id !== STUDENT_RECORD_FOR_USER[user.id] || sheet.status !== 'APPROVED') {
      return HttpResponse.json({ detail: 'Not found.' }, { status: 404 })
    }
    // Students never receive evidence quotes or raw crops (§8 screen 12).
    return HttpResponse.json({
      ...sheet,
      evaluations: sheet.evaluations.map((e) => ({
        ...e,
        concept_scores: e.concept_scores.map(({ evidence: _evidence, ...cs }) => cs),
        blocks: e.blocks.map((b) => ({ ...b, crop_image_url: '', raw_text: '' })),
      })),
    })
  }),
]

/** Re-runs the pipeline simulation for a retried sheet. */
function createSheetRetry(sheetId: number) {
  void import('./db').then(({ simulatePipeline }) => simulatePipeline(sheetId))
}
