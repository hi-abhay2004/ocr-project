/**
 * Hand-written mirrors of the DRF serializers.
 *
 * This file IS the frontend's half of the §8 contract. When the backend track
 * changes a serializer, change it here in the same commit — a silent drift here
 * surfaces as `undefined` in a chart or a box drawn at (0,0), not as a type error.
 *
 * Source of truth: PLAN_OF_ACTION_V2.md §8, FRONTEND_PLAN.md §3.
 */

/* ── Auth ─────────────────────────────────────────────────────────────── */

export type Role = 'TEACHER' | 'STUDENT'

export interface User {
  id: number
  username: string
  full_name: string
  role: Role
}

export interface TokenPair {
  access: string
  refresh: string
}

/**
 * POST /api/auth/register/ (§8).
 *
 * Returns a TokenPair, so a successful signup logs the user straight in — there
 * is no reason to make someone who just typed their password type it again.
 * `usn` is required for STUDENT and must be absent for TEACHER; the server is
 * the authority on that, the form only mirrors it.
 */
export interface RegisterInput {
  username: string
  full_name: string
  email: string
  password: string
  role: Role
  usn?: string
}

/* ── Exams / questions / concepts ─────────────────────────────────────── */

export interface Exam {
  id: number
  name: string
  subject: string
  exam_date: string // ISO date, YYYY-MM-DD
  total_marks: number
  question_count: number
  sheet_count: number
  avg_marks: number | null // null until at least one sheet is evaluated
  created_at: string
}

export interface Question {
  id: number
  exam: number
  number: string // "1a", "2", "3b" — not an int; sub-parts are normal
  text: string
  max_marks: number
  model_answer: string
  /** False while the Celery concept-extraction task is still running (§6). */
  concepts_indexed: boolean
}

export interface Concept {
  id: number
  question: number
  text: string
  /** Normalised so that all concepts of one question sum to 1.00. */
  weight: number
}

/* ── Students ─────────────────────────────────────────────────────────── */

export interface Student {
  id: number
  usn: string
  name: string
  email: string
}

/** One parsed row from CsvImportDialog, before it is sent to the server. */
export interface CsvRow {
  usn: string
  name: string
  email: string
  /** Client-side validation message; row is not importable while set. */
  error?: string
}

/* ── Pipeline ─────────────────────────────────────────────────────────── */

/**
 * The 12 pipeline stages (FRONTEND_PLAN §3.4). PipelineProgress renders these
 * verbatim, so the order here IS the order shown in the stepper.
 */
export const STAGES = [
  'queued',
  'preprocessing',
  'segmentation',
  'annotations',
  'adjudication', // L3.5 ⟨VLM⟩
  'ocr',
  'specialized', // L4.5 ⟨VLM⟩
  'reconstruction',
  'retrieval',
  'coverage',
  'scoring',
  'feedback',
  'done',
] as const

export type Stage = (typeof STAGES)[number]

export type SheetStatus = 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED' | 'APPROVED'

/** Statuses at which useSheetStatus must stop polling (§6). */
export const TERMINAL_STATUSES: readonly SheetStatus[] = ['DONE', 'FAILED', 'APPROVED']

export type Band = 'GREEN' | 'ORANGE' | 'RED'

/* ── Blocks + annotations (§3.1 — the overlay contract) ───────────────── */

export type AnnotationKind = 'STRIKE' | 'UNDERLINE' | 'ARROW' | 'MARGIN'
export type AnnotationIntent = 'CORRECTION' | 'EMPHASIS' | 'INSERTION'
/** CV = deterministic detector was confident. VLM = L3.5 had to adjudicate. */
export type ResolvedBy = 'CV' | 'VLM'

/**
 * Bounding box in the CROP's own pixel coordinates.
 *
 * NOT page coordinates and NOT normalised 0–1. The SVG viewBox is set to the
 * crop's natural dimensions, so these numbers are used raw with zero arithmetic
 * (§7). If the backend ever sends normalised values every box collapses into the
 * top-left corner — that is the failure mode this comment exists to prevent.
 */
export interface BBox {
  x: number
  y: number
  w: number
  h: number
}

export interface Annotation {
  id: number
  kind: AnnotationKind
  intent: AnnotationIntent
  bbox: BBox
  confidence: number // 0–1
  resolved_by: ResolvedBy
}

export type ContentType = 'TEXT' | 'DIAGRAM' | 'TABLE' | 'EQUATION'
export type OcrEngine = 'TESSERACT_6' | 'TESSERACT_11' | 'VLM' | 'VLM_SPECIALIZED'

export interface Block {
  id: number
  question_id: number
  crop_image_url: string
  /** Natural pixel dimensions — required for the SVG viewBox. */
  image_width: number
  image_height: number
  quality_score: number // 0–1, drives the L4 OCR routing decision
  content_type: ContentType
  ocr_engine: OcrEngine
  raw_text: string
  reconstructed_text: string
  annotations: Annotation[]
}

/* ── Evaluation results ───────────────────────────────────────────────── */

export type ConceptStatus = 'COVERED' | 'PARTIAL' | 'MISSING'

export interface ConceptScore {
  id: number
  concept_id: number
  concept_text: string
  status: ConceptStatus
  similarity: number // 0–1, cosine against the retrieved chunk
  marks: number
  max_marks: number
  /** The retrieved chunk the LLM justified its decision with. Teacher-only. */
  evidence?: string
  /** True when the three majority-vote passes did not agree (§ triple-pass). */
  disagreed?: boolean
}

export interface Feedback {
  strengths: string
  gaps: string
  suggestions: string
}

export interface QuestionEvaluation {
  id: number
  question_id: number
  question_number: string
  question_text: string
  max_marks: number
  /** Machine mark. Never overwritten — an override is recorded separately. */
  auto_marks: number
  /** Teacher's override, null when untouched. Effective mark is `?? auto_marks`. */
  override_marks: number | null
  override_comment: string | null
  confidence: number // 0–1 composite
  band: Band
  concept_scores: ConceptScore[]
  feedback: Feedback
  blocks: Block[]
}

export interface Sheet {
  id: number
  exam: number
  exam_name: string
  student: Student
  status: SheetStatus
  stage: Stage
  page_count: number
  total_marks: number
  max_marks: number
  confidence: number
  band: Band
  error_message: string | null
  started_at: string
  approved_at: string | null
  evaluations: QuestionEvaluation[]
}

/** Row shape of GET /api/exams/{id}/sheets/ — the review queue (§3.3). */
export interface SheetListItem {
  id: number
  student: Student
  status: SheetStatus
  stage: Stage
  band: Band
  confidence: number
  total_marks: number
  max_marks: number
  approved_at: string | null
}

/** Response of GET /api/sheets/{id}/status/ — polled every 2s. */
export interface SheetStatusResponse {
  id: number
  status: SheetStatus
  stage: Stage
  started_at: string
  error_message: string | null
}

/* ── Analytics (§3.2) ─────────────────────────────────────────────────── */

export interface ExamSummary {
  sheet_count: number
  approved_count: number
  bands: { green: number; orange: number; red: number }
  mark_distribution: { bucket: string; count: number }[]
  concept_miss_rate: {
    concept: string
    missing: number
    partial: number
    covered: number
  }[]
  avg_confidence: number
  /** Share of blocks that escalated CV → VLM. The novelty metric. */
  vlm_escalation_rate: number
}

/* ── Student-facing ───────────────────────────────────────────────────── */

/** Only ever returned for APPROVED sheets belonging to the requesting student. */
export interface StudentResult {
  sheet_id: number
  exam_id: number
  exam_name: string
  subject: string
  exam_date: string
  total_marks: number
  max_marks: number
  approved_at: string
}
