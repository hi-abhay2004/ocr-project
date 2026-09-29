# API Reference

All endpoints are under `/api/`. Auth is a JWT bearer token (`Authorization: Bearer <access>`), except
where marked public. `TEACHER`/`STUDENT` mark the required `request.user.role`. A cross-owner request
(another teacher's exam, another student's result) 404s rather than 403s — a filtered-queryset 404 doesn't
confirm to a probing user that the resource even exists.

The authoritative, exhaustive contract (status codes, request/response shapes, field-keyed error bodies)
is `frontend/src/tests/mocks/handlers.ts` and `frontend/src/types/api.ts` — this file is a map, not a spec.

## Auth (`apps.accounts`) — public

| Method & path | Notes |
|---|---|
| `POST /auth/register/` | Role-conditional (`usn` required for STUDENT, rejected for TEACHER). Create-or-link a pre-imported `Student` row by USN. Returns a token pair. |
| `POST /auth/login/` | Returns `{access, refresh}`. Throttled (`auth` scope, 20/min). |
| `POST /auth/refresh/` | Rotates + blacklists the old refresh token. Throttled. |
| `GET /auth/me/` | Auth required (any role). |

## Exams, questions, concepts (`apps.exams`) — TEACHER

| Method & path | Notes |
|---|---|
| `GET/POST /exams/` | List/create. `question_count`/`sheet_count`/`avg_marks` computed live. |
| `GET/PATCH/DELETE /exams/<id>/` | |
| `GET/POST /exams/<id>/questions/` | Saving `model_answer` enqueues real concept extraction (`ai.concepts`). |
| `GET/PATCH/DELETE /questions/<id>/` | Re-indexes concepts only if `model_answer` actually changed (sha256 guard). |
| `GET /questions/<id>/concepts/` | Empty until extraction finishes; the frontend polls this. |

## Students & enrolment (`apps.students`) — TEACHER

| Method & path | Notes |
|---|---|
| `GET/POST /exams/<id>/students/` | POST rejects a USN that exists anywhere (manual add = assumed new person). |
| `DELETE /exams/<id>/students/<student_id>/` | Removes enrolment only — the `Student` row (and any linked account) survives. |
| `POST /exams/<id>/students/import/` | CSV import. Row-by-row (one bad row never blocks the rest). Links an existing USN rather than rejecting it. Returns `{created, skipped, errors: [{row, message}]}`. |

## Sheets, review, evaluation (`apps.evaluation`)

| Method & path | Role | Notes |
|---|---|---|
| `GET /exams/<id>/sheets/?band=&status=` | TEACHER | The review queue. |
| `POST /exams/<id>/sheets/` | TEACHER | Multipart `pages[]`. Returns 202; evaluation runs async (Celery). |
| `GET /sheets/<id>/status/` | TEACHER | Lightweight — polled every 2s by the stepper UI. |
| `GET /sheets/<id>/` | TEACHER | Full nested tree: evaluations → blocks → annotations, concept scores. |
| `POST /sheets/<id>/retry/` | TEACHER | Re-queues; clears and recreates evaluations. |
| `POST /sheets/<id>/approve/` | TEACHER | Only from `DONE` (or already `APPROVED`, idempotent). |
| `GET /exams/<id>/summary/` | TEACHER | Band distribution, mark histogram, concept miss-rate, avg confidence, VLM escalation rate. |
| `PATCH /evaluations/<id>/` | TEACHER | Sets/clears `override_marks`. `auto_marks` is never mutated. |
| `GET /results/` | STUDENT | Approved-only, own-only. |
| `GET /results/<sheet_id>/` | STUDENT | Same shape as the teacher detail view, with `evidence` and raw crop URLs stripped. |

## Evaluation pipeline (not HTTP — Celery, `apps.evaluation.tasks.evaluate_sheet`)

Runs the 13-stage pipeline against `ai/`:

1. **L1–L2** preprocess + segment each page (`ai.preprocessing`, `ai.segmentation`)
2. **L3–L3.5** detect strike/underline/arrow/margin marks, escalate ambiguous ones to the VLM
   (`ai.annotations`)
3. **L4–L4.5** adaptive OCR routing / non-text description (`ai.ocr`)
4. **L5** reconstruct final answer text, dropping deletions, splicing margin insertions (`ai.reconstruct`)
5. **L6–L8** chunk → retrieve → triple-pass LLM coverage vote → band → confidence → feedback
   (`ai.pipeline.evaluate_question`)

Always resolves to `DONE` or `FAILED` — never left `RUNNING` (see `apps/evaluation/tests/test_pipeline.py`'s
failure-path tests: a broken provider, malformed LLM JSON, and a Celery soft-time-limit are all covered).
