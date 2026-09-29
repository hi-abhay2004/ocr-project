# Backend Implementation Plan — Django

**Companion to `PLAN_OF_ACTION_V2.md` §5–§11 and `FRONTEND_PLAN.md`.**

---

## 1. Context

The frontend is **finished**: 74 source files, 63 unit tests, 7 Playwright specs, all green. It currently
runs against an in-browser MSW mock of the entire API. That mock is not a throwaway — it is a **complete,
executable specification of 28 endpoints**, and `frontend/src/types/api.ts` is the contract in TypeScript
form.

This plan builds the Django backend that replaces it. The organising principle follows from that fact:

> **Make the API real first, with a stub evaluator. Get the frontend off MSW as early as possible.
> Then replace the stub with the real AI pipeline, layer by layer.**

Front-loading the API means contract drift surfaces in week one rather than at integration. It also means
every later phase is verified by a test suite that **already exists** — after Phase B3, running
`npx playwright test` against Django is a genuine end-to-end regression net for all backend work that
follows.

### Decisions locked in

| Decision | Choice |
|---|---|
| Build order | **API first with a stub evaluator**; real pipeline swapped in later |
| Infra | **Docker Compose** — `pgvector/pgvector:pg16` + `redis:7-alpine` |
| Providers | **Mock-first.** Every phase testable with no network; NIM wired in at B8 |
| Datasets | **STS-B** (threshold calibration) + **own 20–50 graded sheets** (Pearson *r*) |

---

## 2. The contract is the frontend

`frontend/src/tests/mocks/handlers.ts` is authoritative for all 28 endpoints — exact status codes (202 on
upload, 201 on create, 204 on delete), field-keyed 400 bodies, and permission behaviour. Where
`PLAN_OF_ACTION_V2.md` §8's prose drifted from what the (already-built, already-tested) frontend actually
calls, the frontend won.

---

## 3. Stack

Django 5 · DRF · SimpleJWT (rotation + blacklist) · django-cors-headers · django-filter · psycopg[binary] ·
pgvector · Celery + Redis · OpenCV/numpy/scipy/scikit-image/Pillow · pytesseract + system `tesseract-ocr` ·
`openai` SDK (NIM is OpenAI-compatible) · django-environ · pytest/pytest-django/pytest-cov/ruff/black.

`torch` is **not** a default dependency — SBERT is a fallback provider only, installed on demand with the
CPU wheel.

---

## 4. Phases

```
B0 Foundation
 ├─ B1 Auth ──────────── FE login/signup live
 ├─ B2 Exams/students ── FE setup screens live
 └─ B3 Sheets + review ─ FE 100% OFF MSW  ★ (stub evaluator)
                          │
                          ├─ B4 Providers + RAG index
                          ├─ B5 CV pipeline L1–L5
                          └─ B6 Scoring L6–L8 ── stub deleted
                                   │
                                   ├─ B7 Hardening
                                   └─ B8 Calibration + demo
```

### B0 — Foundation
Docker Compose, Django project skeleton, DRF + SimpleJWT, pgvector extension migration, `ai/config.py`
(every threshold in one place), `ai/providers/{base,mock,factory}.py`, health check, pytest scaffolding.

### B1 — Accounts & auth
`apps.accounts.User(role, department)`, `apps.students.Student(usn↑, user→User?)`. Create-or-link on USN.
Field-keyed errors. Token pair on register.

### B2 — Exams, questions, students
`Exam`, `Question`, `Concept(embedding VectorField)` with an ivfflat cosine index. CSV import mirroring
`CsvImportDialog.tsx`'s row-by-row rules. Every queryset scoped to the caller.

### B3 — Sheets, review, results + stub evaluator ★
Upload → stub `evaluate_sheet` Celery task walks all 13 stages, synthesises blocks/annotations/concept
scores from real `Concept` rows using content-derived mock embeddings. Review queue, override, approve,
retry, student results with evidence stripped. **Gate:** all 7 Playwright specs pass against Django.

### B4 — Providers + concept extraction + RAG index
`ai/providers/retry.py` (JSON-repair retry), `ai/concepts.py` (real LLM-backed extraction), `ai/rag/
{embedder,store}.py`, `ai/providers/{nim,ollama,sbert}.py`. Idempotency guard on re-saving an unchanged
model answer.

### B5 — CV pipeline L1–L5
`ai/preprocessing.py` (L1) · `ai/segmentation.py` (L2) · `ai/annotations/{strikethrough,underline,arrows,
margins,adjudicator}.py` (L3/L3.5) · `ai/ocr/{quality,tesseract_engine,vlm_engine,router,content_type,
specialized}.py` (L4/L4.5) · `ai/reconstruct.py` (L5). Golden synthetic fixtures, not real scans — the
assertion is about the detector, not the fixture. **Gate:** image in → reconstructed_text + typed
`Annotation[]` with crop-pixel bboxes; VLM cost guard (0 calls clean, 1 call ambiguous).

### B6 — RAG query + scoring L6–L8
`ai/rag/{chunker,retriever}.py` · `ai/coverage.py` (triple-pass LLM voting) · `ai/scoring.py` (band table) ·
`ai/confidence.py` · `ai/feedback.py` · `ai/pipeline.py` (orchestrator). Replaces the B3 stub's *scoring*
inside `apps.evaluation.tasks.evaluate_sheet` — the stub's fixture-rendered block/annotation geometry is
kept deliberately (see the docstring in `tasks.py`), since it has no "correct" answer for a general CV
pipeline to reproduce and is already what the E2E overlay test pins against.

### B7 — Failure paths, permissions, security
Nothing may hang or silently zero the marks — LLM JSON failure, Celery soft-time-limit, provider outage
all resolve the sheet to `FAILED` with a readable message, never left `RUNNING`. Cross-teacher and
cross-student permission boundaries tested explicitly. Upload validation (MIME, size, UUID filenames —
path traversal is structurally impossible, not just filtered). Auth endpoints throttled (20/min).

### B8 — Calibration, benchmarking, delivery
`scripts/download_datasets.py` (STS-B, size-capped) · `scripts/calibrate_thresholds.py` (measures
correlation, does **not** auto-write `ai/config.py` — a mock/non-semantic embedding provider has no reason
to correlate with human similarity judgements, and the script says so rather than silently producing
garbage numbers) · `scripts/seed_demo.py` (one full exam, real pipeline, no worker required).

> Wiring a **real NIM key** and benchmarking against **20–50 teacher-graded sheets** are both real, external
> inputs this project doesn't have in this environment. `ai/providers/nim.py` is fully built and unit-tested
> against a scripted OpenAI-compatible client shape; it has simply never been smoke-tested against the live
> NIM endpoint, and no `docs/benchmarking_report.md` with real Pearson-*r* numbers exists. Both are one
> `.env` key / one folder of sheets away from being runnable, not a code gap.

---

## 5. Verification

```bash
docker compose up -d
python manage.py migrate
python manage.py runserver          # :8000
celery -A config worker -l info     # separate terminal

pytest                              # apps/* + ai/ — 249 passing as of Phase B7
python scripts/seed_demo.py         # one real exam, real pipeline, no worker needed

cd frontend && VITE_USE_MSW=false npm run dev
npx playwright test                 # the real acceptance test — 7/7
```
