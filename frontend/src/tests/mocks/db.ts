import type {
  Band,
  Concept,
  Exam,
  ExamSummary,
  Question,
  QuestionEvaluation,
  Sheet,
  SheetListItem,
  Stage,
  Student,
  StudentResult,
  User,
} from '@/types/api'
import { STAGES } from '@/types/api'
import {
  CROP_W,
  CROP_H,
  DIAGRAM_H,
  DIAGRAM_W,
  FIXTURE_ANNOTATIONS,
  FIXTURE_CROP_URL,
  FIXTURE_DIAGRAM_URL,
} from './fixtureImage'

/**
 * In-memory stand-in for the Django backend.
 *
 * Stateful on purpose: creating an exam, saving a question and uploading a sheet
 * all mutate this store, so every screen can be driven end-to-end before Phase 4
 * exists. It also SIMULATES THE PIPELINE — an uploaded sheet walks the 12 stages
 * on a timer, which is the only way to exercise the poller's terminal-stop rule
 * without a Celery worker.
 */

let nextId = 1000
const id = () => ++nextId

export const USERS: Record<string, User & { password: string }> = {
  teacher: {
    id: 1,
    username: 'teacher',
    full_name: 'Dr. Gireesh Babu C N',
    role: 'TEACHER',
    password: 'any',
  },
  student: {
    id: 2,
    username: 'student',
    full_name: 'P Charan Chandra',
    role: 'STUDENT',
    password: 'any',
  },
}

export const students: Student[] = [
  { id: 11, usn: '1BY22CS001', name: 'P Charan Chandra', email: 'charan@bmsit.in' },
  { id: 12, usn: '1BY22CS002', name: 'R T Kesav Reddy', email: 'kesav@bmsit.in' },
  { id: 13, usn: '1BY22CS003', name: 'Sai Charan M M', email: 'saicharan@bmsit.in' },
  { id: 14, usn: '1BY22CS004', name: 'Nunna Uma Shankar', email: 'uma@bmsit.in' },
  { id: 15, usn: '1BY22CS005', name: 'A Deepika', email: 'deepika@bmsit.in' },
]

export const exams: Exam[] = [
  {
    id: 101,
    name: 'CIE-2 Database Management Systems',
    subject: '22CS52 · DBMS',
    exam_date: '2026-07-24',
    total_marks: 30,
    question_count: 2,
    sheet_count: 4,
    avg_marks: 8.4,
    created_at: '2026-07-20T09:00:00Z',
  },
  {
    id: 102,
    name: 'CIE-1 Operating Systems',
    subject: '22CS51 · OS',
    exam_date: '2026-06-12',
    total_marks: 30,
    question_count: 0,
    sheet_count: 0,
    avg_marks: null,
    created_at: '2026-06-05T09:00:00Z',
  },
]

export const questions: Question[] = [
  {
    id: 201,
    exam: 101,
    number: '1a',
    text: 'Define BCNF. Explain how it differs from 3NF with an example.',
    max_marks: 10,
    model_answer:
      'BCNF (Boyce-Codd Normal Form) is a normal form for relational schemas. A relation R is in BCNF ' +
      'if, for every non-trivial functional dependency X -> Y that holds on R, X is a superkey of R. ' +
      'It is stricter than 3NF: 3NF permits a dependency whose right side is a prime attribute even ' +
      'when the left side is not a superkey, whereas BCNF does not. Decomposing into BCNF removes ' +
      'update, insertion and deletion anomalies but is not always dependency-preserving.',
    concepts_indexed: true,
  },
  {
    id: 202,
    exam: 101,
    number: '1b',
    text: 'Draw an ER diagram for a Student–Course enrolment system.',
    max_marks: 10,
    model_answer:
      'The diagram must show a STUDENT entity and a COURSE entity connected by an ENROLS relationship ' +
      'with an M:N cardinality. STUDENT carries a usn key attribute; COURSE carries a code key ' +
      'attribute. Participation constraints and the relationship attributes should be labelled.',
    concepts_indexed: true,
  },
]

export const concepts: Concept[] = [
  { id: 301, question: 201, text: 'BCNF is defined over functional dependencies', weight: 0.15 },
  { id: 302, question: 201, text: 'Every determinant X must be a superkey of R', weight: 0.3 },
  { id: 303, question: 201, text: 'The dependency must be non-trivial', weight: 0.1 },
  { id: 304, question: 201, text: 'BCNF is stricter than 3NF', weight: 0.2 },
  { id: 305, question: 201, text: '3NF allows a prime attribute on the right side', weight: 0.15 },
  { id: 306, question: 201, text: 'BCNF decomposition may lose dependency preservation', weight: 0.1 },
  { id: 311, question: 202, text: 'STUDENT and COURSE entities are present', weight: 0.3 },
  { id: 312, question: 202, text: 'ENROLS relationship connects them', weight: 0.25 },
  { id: 313, question: 202, text: 'Cardinality is M:N', weight: 0.25 },
  { id: 314, question: 202, text: 'Key attributes usn and code are shown', weight: 0.2 },
]

/** studentId → the exams they are enrolled in. */
export const enrolment: Record<number, number[]> = {
  11: [101],
  12: [101],
  13: [101],
  14: [101],
  15: [101],
}

/* ── Evaluation factory ───────────────────────────────────────────────── */

function bandOf(confidence: number): Band {
  return confidence >= 0.8 ? 'GREEN' : confidence >= 0.65 ? 'ORANGE' : 'RED'
}

function makeEvaluations(seed: number): QuestionEvaluation[] {
  // Deterministic per-sheet variation so the review queue has a real spread of
  // bands to triage instead of five identical rows.
  const r = (n: number) => ((seed * 9301 + n * 49297) % 233280) / 233280

  const q1Statuses = ['COVERED', 'COVERED', 'PARTIAL', 'COVERED', 'MISSING', 'MISSING'] as const
  const shift = seed % 3

  const q1Concepts = concepts
    .filter((c) => c.question === 201)
    .map((c, i) => {
      const status = q1Statuses[(i + shift) % q1Statuses.length]
      const similarity =
        status === 'COVERED' ? 0.78 + r(i) * 0.18 : status === 'PARTIAL' ? 0.55 + r(i) * 0.15 : 0.18 + r(i) * 0.2
      const maxMarks = +(c.weight * 10).toFixed(2)
      const marks = +(maxMarks * (status === 'COVERED' ? 1 : status === 'PARTIAL' ? 0.5 : 0)).toFixed(2)
      return {
        id: 400 + seed * 10 + i,
        concept_id: c.id,
        concept_text: c.text,
        status,
        similarity: +similarity.toFixed(2),
        marks,
        max_marks: maxMarks,
        evidence:
          status === 'MISSING'
            ? undefined
            : 'A relation R is in BCNF if for every functional dependency X -> Y, X must be a superkey of R.',
        disagreed: i === 2 && seed % 2 === 0,
      }
    })

  const q1Total = +q1Concepts.reduce((s, c) => s + c.marks, 0).toFixed(1)
  const q1Conf = +(0.62 + r(7) * 0.32).toFixed(2)

  const q2Concepts = concepts
    .filter((c) => c.question === 202)
    .map((c, i) => {
      const status = i < 3 - (seed % 2) ? 'COVERED' : ('PARTIAL' as const)
      const maxMarks = +(c.weight * 10).toFixed(2)
      return {
        id: 500 + seed * 10 + i,
        concept_id: c.id,
        concept_text: c.text,
        status: status as 'COVERED' | 'PARTIAL',
        similarity: status === 'COVERED' ? 0.86 : 0.61,
        marks: +(maxMarks * (status === 'COVERED' ? 1 : 0.5)).toFixed(2),
        max_marks: maxMarks,
        evidence: 'Vision model description: an M:N ENROLS relationship links STUDENT and COURSE.',
        disagreed: false,
      }
    })

  const q2Total = +q2Concepts.reduce((s, c) => s + c.marks, 0).toFixed(1)
  const q2Conf = +(0.7 + r(3) * 0.25).toFixed(2)

  return [
    {
      id: 601 + seed * 10,
      question_id: 201,
      question_number: '1a',
      question_text: questions[0].text,
      max_marks: 10,
      auto_marks: q1Total,
      override_marks: null,
      override_comment: null,
      confidence: q1Conf,
      band: bandOf(q1Conf),
      concept_scores: q1Concepts,
      feedback: {
        strengths:
          'You correctly state the superkey condition and connect it to functional dependencies. ' +
          'The definition is precise and uses the right vocabulary.',
        gaps:
          'The comparison with 3NF stops at "stricter" without saying what 3NF actually permits — ' +
          'a prime attribute on the right-hand side. The dependency-preservation trade-off is not mentioned.',
        suggestions:
          'Add one worked example where a relation is in 3NF but not in BCNF, and state explicitly ' +
          'that BCNF decomposition can lose dependency preservation.',
      },
      blocks: [
        {
          id: 700 + seed,
          question_id: 201,
          crop_image_url: FIXTURE_CROP_URL,
          image_width: CROP_W,
          image_height: CROP_H,
          quality_score: 0.71,
          content_type: 'TEXT',
          ocr_engine: 'TESSERACT_6',
          raw_text:
            'BCNF is a normal form used in database design. A relation R is in BCNF if for every ' +
            'non-trivial functional dependency X -> Y, X must be a superkey of R. It is stricter ' +
            'than 3NF and removes redundancy caused by transitive dependencies.',
          reconstructed_text:
            'BCNF is a normal form used in database design. A relation R is in BCNF if for every ' +
            'functional dependency X -> Y, X must be a superkey of R. It is stricter than 3NF and ' +
            'removes redundancy and update anomalies caused by transitive dependencies.',
          annotations: FIXTURE_ANNOTATIONS,
        },
      ],
    },
    {
      id: 602 + seed * 10,
      question_id: 202,
      question_number: '1b',
      question_text: questions[1].text,
      max_marks: 10,
      auto_marks: q2Total,
      override_marks: null,
      override_comment: null,
      confidence: q2Conf,
      band: bandOf(q2Conf),
      concept_scores: q2Concepts,
      feedback: {
        strengths: 'Both entities and the relationship are drawn, and the key attributes are labelled.',
        gaps: 'Participation constraints (total vs partial) are not indicated on either side.',
        suggestions: 'Use a double line for total participation and label the relationship attributes.',
      },
      blocks: [
        {
          id: 800 + seed,
          question_id: 202,
          crop_image_url: FIXTURE_DIAGRAM_URL,
          image_width: DIAGRAM_W,
          image_height: DIAGRAM_H,
          quality_score: 0.55,
          content_type: 'DIAGRAM',
          ocr_engine: 'VLM_SPECIALIZED',
          raw_text: '',
          reconstructed_text:
            'Hand-drawn ER diagram. A rectangle labelled STUDENT on the left is joined by a diamond ' +
            'labelled "enrols" to a rectangle labelled COURSE on the right. The connection is marked ' +
            'M on the STUDENT side and N on the COURSE side, indicating a many-to-many relationship. ' +
            'An ellipse labelled "usn" hangs below STUDENT and an ellipse labelled "code" hangs below ' +
            'COURSE, both drawn as key attributes.',
          annotations: [],
        },
      ],
    },
  ]
}

/* ── Sheets ───────────────────────────────────────────────────────────── */

function makeSheet(sheetId: number, studentId: number, seed: number, status: Sheet['status']): Sheet {
  const student = students.find((s) => s.id === studentId)!
  const evaluations = makeEvaluations(seed)
  const total = +evaluations.reduce((s, e) => s + (e.override_marks ?? e.auto_marks), 0).toFixed(1)
  const confidence = +(evaluations.reduce((s, e) => s + e.confidence, 0) / evaluations.length).toFixed(2)
  return {
    id: sheetId,
    exam: 101,
    exam_name: exams[0].name,
    student,
    status,
    stage: status === 'FAILED' ? 'ocr' : 'done',
    page_count: 2,
    total_marks: total,
    max_marks: 20,
    confidence,
    band: bandOf(confidence),
    error_message:
      status === 'FAILED' ? 'OCR returned no text for page 2 — the scan may be blank or upside down.' : null,
    started_at: '2026-07-25T10:15:00Z',
    approved_at: status === 'APPROVED' ? '2026-07-25T11:02:00Z' : null,
    evaluations,
  }
}

export const sheets: Sheet[] = [
  makeSheet(901, 11, 1, 'APPROVED'),
  makeSheet(902, 12, 2, 'DONE'),
  makeSheet(903, 13, 4, 'DONE'),
  makeSheet(904, 14, 5, 'FAILED'),
]

/* ── Pipeline simulation ──────────────────────────────────────────────── */

const STAGE_MS = 900

/**
 * Walks a freshly uploaded sheet through the 12 stages on a timer.
 *
 * This is what makes PipelineProgress and the poller testable with no Celery:
 * the stepper visibly advances, then the status goes terminal and the poller
 * must stop. If the poller keeps firing after this resolves, that is the bug.
 */
export function simulatePipeline(sheetId: number) {
  const sheet = sheets.find((s) => s.id === sheetId)
  if (!sheet) return

  let i = 0
  sheet.status = 'QUEUED'
  sheet.stage = 'queued'

  const timer = setInterval(() => {
    i += 1
    if (i >= STAGES.length - 1) {
      clearInterval(timer)
      sheet.stage = 'done'
      sheet.status = 'DONE'
      return
    }
    sheet.stage = STAGES[i] as Stage
    sheet.status = 'RUNNING'
  }, STAGE_MS)
}

export function createSheet(examId: number, studentId: number): Sheet {
  const sheetId = id()
  const seed = sheets.length + 3
  const sheet = makeSheet(sheetId, studentId, seed, 'QUEUED')
  sheet.exam = examId
  sheet.stage = 'queued'
  sheets.push(sheet)
  simulatePipeline(sheetId)
  return sheet
}

/* ── Derived views ────────────────────────────────────────────────────── */

export function toListItem(s: Sheet): SheetListItem {
  return {
    id: s.id,
    student: s.student,
    status: s.status,
    stage: s.stage,
    band: s.band,
    confidence: s.confidence,
    total_marks: s.total_marks,
    max_marks: s.max_marks,
    approved_at: s.approved_at,
  }
}

export function recomputeSheet(sheet: Sheet) {
  sheet.total_marks = +sheet.evaluations
    .reduce((s, e) => s + (e.override_marks ?? e.auto_marks), 0)
    .toFixed(1)
}

export function summaryFor(examId: number): ExamSummary {
  const rows = sheets.filter((s) => s.exam === examId && s.status !== 'FAILED')
  const bands = { green: 0, orange: 0, red: 0 }
  for (const s of rows) bands[s.band.toLowerCase() as keyof typeof bands] += 1

  // Half-open edges, not inclusive string ranges. Marks are fractional (5.25,
  // 16.5), so `>= 13 && <= 16` plus `>= 17` leaves a hole between 16 and 17 that
  // silently drops sheets out of the histogram.
  const EDGES = [0, 5, 9, 13, 17, 21]
  const mark_distribution = EDGES.slice(0, -1).map((lo, i) => {
    const hi = EDGES[i + 1]
    return {
      bucket: `${lo}-${hi - 1}`,
      count: rows.filter((s) => s.total_marks >= lo && s.total_marks < hi).length,
    }
  })

  const byConcept = new Map<string, { missing: number; partial: number; covered: number }>()
  for (const s of rows) {
    for (const e of s.evaluations) {
      for (const cs of e.concept_scores) {
        const cur = byConcept.get(cs.concept_text) ?? { missing: 0, partial: 0, covered: 0 }
        if (cs.status === 'MISSING') cur.missing += 1
        else if (cs.status === 'PARTIAL') cur.partial += 1
        else cur.covered += 1
        byConcept.set(cs.concept_text, cur)
      }
    }
  }

  return {
    sheet_count: rows.length,
    approved_count: rows.filter((s) => s.status === 'APPROVED').length,
    bands,
    mark_distribution,
    concept_miss_rate: [...byConcept.entries()]
      .map(([concept, v]) => ({ concept, ...v }))
      .sort((a, b) => b.missing - a.missing),
    avg_confidence: rows.length
      ? +(rows.reduce((s, r) => s + r.confidence, 0) / rows.length).toFixed(2)
      : 0,
    vlm_escalation_rate: 0.17,
  }
}

export function studentResultsFor(studentId: number): StudentResult[] {
  return sheets
    .filter((s) => s.student.id === studentId && s.status === 'APPROVED')
    .map((s) => {
      const exam = exams.find((e) => e.id === s.exam)!
      return {
        sheet_id: s.id,
        exam_id: exam.id,
        exam_name: exam.name,
        subject: exam.subject,
        exam_date: exam.exam_date,
        total_marks: s.total_marks,
        max_marks: s.max_marks,
        approved_at: s.approved_at!,
      }
    })
}

export { id as nextMockId, makeEvaluations }
