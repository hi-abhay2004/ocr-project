# AI-Driven Answer Sheet Evaluation System — Plan of Action

**BMS Institute of Technology & Management · CSE · Major Project Phase 2 (2025–26)**
**Team:** P Charan Chandra · R T Kesav Reddy · Sai Charan M M · Nunna Uma Shankar
**Guide:** Dr. Gireesh Babu C N
**Mode:** continuous build — see §9 for phase order and gates

---

## 1. Context

The source material (`AI-Generated-Answer-Sheet-Evaluation (2)_choladeck.pptx`, `project_workflow.pdf`,
`objectives.jpeg`, `workflow.jpeg`) defines a system that grades **handwritten** student answer sheets by
reading them the way a human examiner does — understanding strike-throughs, underlines, arrows and margin
notes rather than treating the page as flat text — then grading by **meaning**, not keyword match, and
returning partial credit with explanatory feedback.

Six research gaps drive the design:

| Gap | Our answer |
|---|---|
| Crossed-out text blindly deleted | Classify strike-through **intent** (correction / emphasis / addition) |
| Fixed OCR sensitivity for all handwriting | **Adaptive thresholding** per answer block (quality score 0–1) |
| Margin content ignored | **Arrow-guided margin text stitching** into logical answer position |
| Single LLM pass → unstable marks | **Triple-pass majority vote** per concept |
| No feedback, no partial credit | **Retrieval-grounded partial credit** + 3-section feedback |
| Underlines treated as ordinary text | **Underline keyword detection** with weight boost |

This plan supersedes the existing `PLAN_OF_ACTION.md`, which assumed a Spring Boot backend and a local
Llama 3.1 8B. Three things changed after reviewing the actual target machine and the team's intent:

1. **Backend is Django**, not Spring Boot (single language across backend + AI pipeline).
2. **Inference moves to NVIDIA NIM** hosted endpoints — the dev machine has no GPU, 11 GB RAM and 12 GB
   free disk, which cannot run an 8B model at the required speed (see §3).
3. **RAG is a real subsystem, not a label.** Concepts extracted from the teacher's model answer are
   embedded and persisted; student answer chunks are retrieved against that store, and the retrieved
   evidence grounds the LLM's coverage judgment. This is the retrieve-then-generate core of the project.

**Intended outcome:** a demo-ready system where a teacher creates an exam, uploads a scanned sheet, watches
the pipeline run, reviews concept-by-concept scores with a confidence band, overrides if needed, and
approves — after which the student sees their marks, coverage bars and written feedback.

---

## 2. Decisions locked in

| Decision | Choice | Why |
|---|---|---|
| Backend | **Django 5 + DRF** | One language end-to-end; ORM covers the whole data model |
| Pipeline placement | **In-repo Python package + Celery** | No HTTP boundary to debug; async uploads |
| Frontend | **React (Vite) + DRF/JWT** | Chosen by team; better concept-coverage charts |
| LLM + VLM | **NVIDIA NIM (free credits)**, behind a provider interface | No GPU on target machine; NIM is free-tier and fast |
| Embeddings | **NVIDIA `nv-embedqa` via NIM**, local SBERT as fallback | Retrieval-tuned; keeps everything on one provider |
| Vector store | **PostgreSQL + pgvector** | MySQL 8 has no vector type; one DB for relational + vectors |
| RAG | **In scope, core** | Concept vectors are the retrieval layer, per team intent |

---

## 3. Environment constraints (verified on target machine)

```
Python 3.12.3 ✓   Tesseract 5.3.4 ✓   Docker 29.1.3 ✓   Node v24.15.0 ✓   Java 21 ✓
RAM   11 GB total / ~6.9 GB available
GPU   none
Disk  12 GB free of 106 GB (89% used)   ← tightest constraint
Ollama not installed · PostgreSQL not installed · Redis not installed
```

**Why local 8B inference was dropped.** `llama3.1:8b` needs ~4.7 GB disk and ~8–10 GB RAM; on CPU it runs
at roughly 2–5 tok/s. Triple-pass coverage is 3 calls per question, so a 5-question sheet would take
several minutes — against a stated target of **< 30 s per sheet**. NIM removes the constraint entirely
without local hardware.

**Disk budget — enforce this, 12 GB is not much.**

| Item | Budget |
|---|---|
| Postgres + Redis Docker images | ~0.6 GB |
| Python venv (OpenCV, sentence-transformers, torch-cpu) | ~3.0 GB |
| `node_modules` | ~0.4 GB |
| Datasets (**subsets only** — see §10) | ~2.5 GB |
| Uploaded sheets + working images | ~0.5 GB |
| **Headroom left** | **~5 GB** |

Do **not** download full IAM + CVL + SROIE. Pull a few hundred samples from each; that is enough for
threshold calibration and for the report. Keep `media/` out of git.

---

## 4. Tech stack

| Layer | Technology |
|---|---|
| Backend | Django 5.x, Django REST Framework, `djangorestframework-simplejwt`, `django-cors-headers` |
| Async | Celery 5 + Redis 7 (Docker) |
| Database | PostgreSQL 16 + **pgvector** (Docker), `pgvector-python` / `django-pgvector` |
| CV / preprocessing | OpenCV (`opencv-python-headless`), NumPy, SciPy, Pillow |
| OCR | Tesseract 5.3.4 via `pytesseract` (PSM 6 / PSM 11) |
| VLM (messy handwriting) | NVIDIA NIM vision endpoint (`meta/llama-3.2-11b-vision-instruct` or equivalent) |
| LLM (concepts / coverage / feedback) | NVIDIA NIM chat endpoint (Llama 3.1/3.3 Instruct family) |
| Embeddings | NIM `nvidia/nv-embedqa-*`; fallback `sentence-transformers/all-MiniLM-L6-v2` |
| API client | `openai` SDK pointed at `https://integrate.api.nvidia.com/v1` (NIM is OpenAI-compatible) |
| Frontend | React 18 + Vite + TypeScript, TanStack Query, Recharts, Tailwind CSS |
| Testing | pytest, pytest-django, pytest-cov, factory-boy, Vitest, Playwright |
| Tooling | ruff, black, mypy (loose), pre-commit, GitHub Actions |

**Provider abstraction is mandatory.** Every model call goes through `ai/providers/base.py`
(`LLMProvider`, `VLMProvider`, `EmbeddingProvider`). Concrete backends: `nim.py` (default),
`ollama.py` (offline demo fallback with a 3B model), `mock.py` (deterministic, used by all CI tests).
This is what makes the system testable without network and swappable if NIM credits run out.

**Free-tier fallbacks if NIM credits are exhausted** (same interface, ~1 hour to add): Groq free tier,
Google AI Studio (Gemini) free tier, OpenRouter free models. Note this in the risk register of the report.

---

## 5. Architecture

```
                        ┌──────────────────────────────┐
   Teacher (React SPA)  │  POST /api/exams/            │
   Student (React SPA)  │  POST /api/sheets/upload/    │
                        └──────────────┬───────────────┘
                                       │ JWT
                            ┌──────────▼──────────┐
                            │   Django + DRF      │  :8000
                            │   ORM · auth · API  │
                            └─────┬──────────┬────┘
                    enqueue task  │          │  read/write
                            ┌─────▼─────┐  ┌─▼─────────────────────┐
                            │  Celery   │  │ PostgreSQL + pgvector │
                            │  worker   │  │ relational + vectors  │
                            └─────┬─────┘  └─▲─────────────────────┘
                                  │          │
        ┌─────────────────────────▼──────────┴──────────────────────┐
        │                  ai/  — 10-layer pipeline                 │
        │                                                            │
        │  L1  Preprocess   → grayscale, denoise, CLAHE, deskew,     │
        │                      adaptive threshold, quality score     │
        │  L2  Segment      → projection profile → per-question crop │
        │  L3  Annotations  → strike / underline / arrow / margin    │
        │                      detection via OpenCV geometry         │
        │  L3.5 Adjudicate  → CV confidence low? VLM decides:        │
        │             ⟨VLM⟩   strike vs underline vs table/ruled line│
        │  L4  Adaptive OCR → quality ≥ .60 → Tesseract PSM 6        │
        │             ⟨VLM⟩   quality < .60 → morph + PSM 11 → VLM   │
        │  L4.5 Non-text    → diagram / table / equation block?      │
        │             ⟨VLM⟩   VLM describes it in words              │
        │  L5  Reconstruct  → drop deletions, stitch margins at      │
        │                      arrow tips, sort reading order        │
        │  ────────────── RAG BOUNDARY ───────────────────────────── │
        │  L6 Retrieve     → chunk + embed student answer, ANN query │
        │                     against stored concept vectors         │
        │  L7 Generate     → triple-pass LLM coverage check, given   │
        │                     ONLY retrieved evidence chunks         │
        │  L8 Score+Feedback → partial credit math, 3-section        │
        │                     feedback, composite confidence         │
        └────────────────────────────────────────────────────────────┘

   Teacher-side, runs ONCE per question (cached):
     model answer → LLM concept extraction → embed each concept → pgvector
```

### Where the VLM is used — three call sites, one principle

The vision model is **not** a general-purpose page reader. It is an escalation target: every layer tries
the cheap deterministic method first and calls the VLM only when that method reports low confidence.
This keeps credit burn proportional to how messy the input actually is, and it is the mechanism behind
research objective #3 (*dynamic VLM sensitivity adjustment per answer block*).

| # | Layer | Cheap method first | VLM fires when | VLM is asked |
|---|---|---|---|---|
| 1 | **L3.5** | OpenCV Hough / Sobel geometry | annotation confidence < 0.70 | *"Does this line cross out the text, sit beneath it as emphasis, or is it a table/ruled line?"* |
| 2 | **L4** | Tesseract PSM 6 → PSM 11 | quality < 0.60 **and** OCR confidence < 40% | *"Transcribe this handwritten answer exactly."* |
| 3 | **L4.5** | text-density / contour heuristic | block is non-text (diagram, table, equation) | *"Describe this diagram / table / equation in words."* |

**Why L3.5 matters.** Hough measures the angle and position of a line — it cannot see that the line passes
through the *middle* of the word "partial." A ruled margin line, a table border, an underline and a
strike-through are geometrically similar and semantically opposite. Geometry alone resolves the clear
cases; the VLM resolves the ambiguous ones. This makes strike-through intent classification a **CV + VLM
hybrid** rather than a Hough threshold, which is a materially stronger claim for objective #2.

**Why L4.5 matters.** Tesseract cannot read a diagram, a table or a mathematical expression at all — it
returns noise. Without this layer, a student who *draws* a functional-dependency diagram instead of writing
the sentence is silently scored zero: OCR yields garbage, retrieval finds nothing, the LLM reports
"missing." The VLM's description flows into the **same** chunking → retrieval → coverage path as ordinary
text, so drawn answers are graded on equal terms with written ones. This restores the *Specialized Content
Processing* layer from the original `workflow.jpeg`.

Every VLM invocation is recorded on the row it affected (`AnswerBlock.ocr_engine`,
`Annotation.resolved_by`) so the teacher dashboard and the benchmarking report can both state exactly how
often the vision model was needed.

### Where RAG actually lives

**Index time (once per question, when the teacher saves the model answer):**
1. LLM extracts 5–8 weighted concepts from the model answer (weights sum to 1.0).
2. Each concept description is embedded → stored in `Concept.embedding` (`vector(1024)`), namespaced by
   `(exam_id, question_id)`.
3. Cached permanently; re-run only if the teacher edits the model answer.

**Query time (per student answer):**
1. Reconstructed answer is chunked into sentences/clauses (`ai/rag/chunker.py`).
2. Chunks are embedded in one batched call.
3. For each concept, ANN-retrieve the **top-k (k=3) student chunks** by cosine similarity
   (`pgvector` `<=>` operator with an IVFFlat index).
4. Those retrieved chunks — **not the full answer** — are injected into the coverage-check prompt.

This is the "augmented" in RAG, and it buys three concrete things worth writing up:
- **Grounding:** the LLM judges against retrieved evidence, cutting hallucinated coverage claims.
- **Verification:** cosine similarity is an independent numeric check on the LLM's verdict — if the LLM
  says *covered* but max similarity < 0.45, the status is auto-downgraded to *partial*.
- **Token economy:** prompts stay small and constant-size regardless of answer length.

### Scoring rules (Layer 8)

| Condition | Award |
|---|---|
| similarity ≥ 0.72 **and** LLM = covered | `weight × max_marks` (full) |
| 0.50 ≤ similarity < 0.72 **or** LLM = partial **or** SBERT downgrade | `0.5 × weight × max_marks` |
| similarity < 0.50 **and** LLM = missing | 0 |
| Concept matched by an **underlined** chunk | similarity × 1.10 (capped at 1.0) before banding |

`total = Σ (weight × max_marks × award_factor)`. Thresholds are **calibrated on STS-B, not guessed** —
see §10.

```
confidence = 0.35 × ocr_quality + 0.40 × triple_pass_agreement + 0.25 × retrieval_verify_rate
≥ 0.80 🟢 auto-publishable   0.65–0.80 🟠 publish with note   < 0.65 🔴 force teacher review
```

---

## 6. Complete file layout

```
Evaluation_system(RAG)/
├── README.md                         # setup, datasets, API reference, demo script
├── .env.example                      # NIM_API_KEY, DB_URL, REDIS_URL, DJANGO_SECRET_KEY
├── .gitignore                        # media/, datasets/, .env, node_modules/, *.pyc
├── docker-compose.yml                # postgres+pgvector, redis
├── pyproject.toml                    # deps, ruff/black/pytest config
├── pytest.ini · .pre-commit-config.yaml
├── Makefile                          # make dev / test / worker / seed / bench
│
├── docs/                             # keep the originals + generated artefacts
│   ├── PLAN_OF_ACTION.md             # (existing — superseded by this file)
│   ├── architecture.md · api.md · benchmarking_report.md
│   └── (existing pptx / pdf / jpegs move here)
│
├── config/                           # Django project
│   ├── settings/{base,dev,prod}.py · urls.py · celery.py · wsgi.py · asgi.py
│
├── apps/
│   ├── accounts/                     # User(role=TEACHER|STUDENT), JWT serializers
│   │   ├── models.py · serializers.py · views.py · urls.py · permissions.py
│   │   └── tests/test_auth.py
│   ├── exams/                        # Exam, Question, Concept(+embedding)
│   │   ├── models.py · serializers.py · views.py · urls.py
│   │   ├── services.py               # extract+embed concepts on model-answer save
│   │   ├── tasks.py                  # index_question_concepts
│   │   └── tests/{test_models,test_api,test_indexing}.py
│   ├── students/                     # Student, CSV bulk import
│   │   ├── models.py · serializers.py · views.py · urls.py · importers.py
│   │   └── tests/test_csv_import.py
│   └── evaluation/                   # sheets, runs, results, review
│       ├── models.py                 # AnswerSheet, AnswerBlock, Annotation,
│       │                             # Evaluation, ConceptScore, EvaluationRun
│       ├── serializers.py · views.py · urls.py
│       ├── tasks.py                  # evaluate_sheet Celery task
│       ├── services.py               # override, approve, re-run
│       └── tests/{test_pipeline_task,test_review_api,test_permissions}.py
│
├── ai/                               # the pipeline — pure Python, no Django imports
│   ├── config.py                     # ALL thresholds in one place:
│   │                                 #   0.72/0.50 similarity bands · 0.45 downgrade
│   │                                 #   0.60 OCR routing · 0.40 OCR confidence
│   │                                 #   0.70 annotation ambiguity (L3.5 trigger)
│   │                                 #   text-density cutoff (L4.5 trigger)
│   ├── pipeline.py                   # orchestrator: run(sheet_path, question_ctx) -> Result
│   ├── types.py                      # dataclasses: Block, Annotation, ConceptVerdict, …
│   ├── preprocessing.py              # L1 + quality_score()
│   ├── segmentation.py               # L2
│   ├── annotations/
│   │   ├── strikethrough.py          # HoughLinesP + intent classification
│   │   ├── underline.py              # Sobel edges below baselines
│   │   ├── arrows.py                 # convexity defects → tip coords
│   │   ├── margins.py                # margin region text + KD-tree insertion point
│   │   └── adjudicator.py            # L3.5 — VLM resolves ambiguous lines
│   ├── ocr/
│   │   ├── quality.py                # stroke density, Laplacian var, pixel var
│   │   ├── tesseract_engine.py       # PSM 6 / PSM 11 + morphology
│   │   ├── vlm_engine.py             # NIM vision client (shared by L3.5/L4/L4.5)
│   │   ├── content_type.py           # L4.5a — TEXT | DIAGRAM | TABLE | EQUATION
│   │   ├── specialized.py            # L4.5b — VLM describes non-text blocks
│   │   └── router.py                 # adaptive routing decision
│   ├── reconstruct.py                # L5
│   ├── rag/
│   │   ├── chunker.py                # sentence/clause chunking + underline tags
│   │   ├── embedder.py               # batched embedding, provider-agnostic
│   │   ├── store.py                  # pgvector upsert / ANN query
│   │   └── retriever.py              # top-k evidence per concept
│   ├── concepts.py                   # L6a extraction (index time)
│   ├── coverage.py                   # L7 triple-pass + majority vote
│   ├── scoring.py                    # L8 partial credit math
│   ├── feedback.py                   # 3-section feedback
│   ├── confidence.py                 # composite confidence
│   ├── prompts/{concept_extraction,coverage_check,feedback,
│   │            annotation_adjudication,transcribe,specialized_content}.txt
│   └── providers/
│       ├── base.py                   # LLMProvider · VLMProvider · EmbeddingProvider ABCs
│       ├── nim.py  · ollama.py  · sbert.py  · mock.py
│       └── retry.py                  # JSON-repair + retry wrapper
│
├── frontend/
│   ├── package.json · vite.config.ts · tailwind.config.js · index.html
│   └── src/
│       ├── main.tsx · App.tsx · router.tsx
│       ├── api/{client.ts,auth.ts,exams.ts,sheets.ts,results.ts}
│       ├── hooks/{useAuth.ts,useEvaluationStatus.ts}
│       ├── components/{ConceptBar,ConfidenceBadge,AnnotationSummary,ProgressBar,
│       │                ScoreOverride,ProtectedRoute}.tsx
│       ├── pages/teacher/{Login,ExamList,ExamCreate,QuestionEditor,
│       │                  StudentManage,SheetUpload,ReviewDashboard,ReviewDetail}.tsx
│       ├── pages/student/{Login,ResultList,ResultDetail}.tsx
│       └── tests/                    # Vitest + RTL
│
├── tests/
│   ├── conftest.py                   # fixtures: mock providers, sample sheets, db
│   ├── fixtures/sheets/              # 8–10 committed sample images (small, <200 KB each)
│   ├── fixtures/golden/              # expected JSON per layer per sample
│   ├── unit/                         # per-layer, mock providers, fast
│   ├── integration/test_full_pipeline.py
│   └── datasets/                     # @pytest.mark.slow — needs downloaded data
│       ├── test_iam_ocr.py · test_funsd_segmentation.py
│       ├── test_sroie_strikethrough.py · test_stsb_thresholds.py
│       └── test_asap_correlation.py
│
├── scripts/
│   ├── download_datasets.py          # subset-only downloader with size caps
│   ├── seed_demo.py                  # demo exam + students + 3 sheets
│   ├── benchmark.py                  # Pearson r vs human marks → docs/benchmarking_report.md
│   ├── calibrate_thresholds.py       # STS-B sweep → ai/config.py values
│   └── smoke_nim.py                  # Day-1: verify NIM key, list models, time a call
│
└── .github/workflows/ci.yml          # ruff + pytest (mock providers, no network) + vitest
```

---

## 7. Data model (PostgreSQL + pgvector)

```
User(id, username, email, password, role[TEACHER|STUDENT], department)
Student(id, usn↑unique, name, email, user→User?)
Exam(id, teacher→User, name, subject, date, total_marks, created_at)
Question(id, exam→Exam, number, text, max_marks, model_answer, model_answer_hash,
         concepts_indexed_at)
Concept(id, question→Question, text, weight, order,
        embedding VECTOR(1024))            ← ivfflat index, cosine
Enrollment(exam→Exam, student→Student)     ← unique_together

AnswerSheet(id, exam, student, image, uploaded_at,
            status[QUEUED|RUNNING|DONE|FAILED|APPROVED], error)
AnswerBlock(id, sheet, question, crop_image, quality_score,
            content_type[TEXT|DIAGRAM|TABLE|EQUATION],     ← L4.5 routing decision
            ocr_engine[TESSERACT_6|TESSERACT_11|VLM|VLM_SPECIALIZED],
            raw_text, reconstructed_text)
Annotation(id, block, kind[STRIKE|UNDERLINE|ARROW|MARGIN],
           intent[CORRECTION|EMPHASIS|INSERTION], bbox JSON, confidence,
           resolved_by[CV|VLM])                            ← did L3.5 have to fire?

Evaluation(id, sheet, question, marks_awarded, max_marks, confidence, band[G|O|R],
           feedback_good, feedback_missing, feedback_improve,
           teacher_override_marks?, teacher_comment?, approved_at?)
ConceptScore(id, evaluation, concept, status[COVERED|PARTIAL|MISSING],
             similarity, evidence_text, marks)
EvaluationRun(id, evaluation, pass_no[1|2|3], raw_response JSON, latency_ms)  ← audit trail
```

Two constraints that matter: `model_answer_hash` makes concept re-indexing idempotent (skip if unchanged),
and `EvaluationRun` persists all three LLM passes so triple-pass variance is provable in the report rather
than merely claimed.

---

## 8. API surface (DRF)

```
POST   /api/auth/register/            POST /api/auth/login/     → JWT pair
POST   /api/auth/refresh/             GET  /api/auth/me/

GET    /api/exams/                    POST /api/exams/
GET    /api/exams/{id}/               PATCH /api/exams/{id}/
POST   /api/exams/{id}/questions/     PATCH /api/questions/{id}/    ← triggers re-index
GET    /api/questions/{id}/concepts/                                ← extracted concepts + weights

POST   /api/exams/{id}/students/      POST /api/exams/{id}/students/import/   ← CSV
GET    /api/exams/{id}/students/

POST   /api/sheets/upload/            → 202 {sheet_id}, enqueues Celery task
GET    /api/sheets/{id}/status/       → {status, stage, percent}   ← poll @2s
GET    /api/sheets/{id}/              → full result + per-concept breakdown
                                        + per-block GEOMETRY (see below)   ← overlay
GET    /api/exams/{id}/sheets/        → review queue; ?band=red&status=DONE ← new
GET    /api/exams/{id}/summary/       → distribution + concept miss-rate    ← new
POST   /api/sheets/{id}/reevaluate/
PATCH  /api/evaluations/{id}/         → teacher override marks + comment
POST   /api/sheets/{id}/approve/      → releases to student, locks result

GET    /api/student/results/          GET /api/student/results/{exam_id}/   ← approved only
```

**Frontend-driven requirements** — these come from `FRONTEND_PLAN.md` §3 and must be built on **Days
4 (Backend)**, because Phase 5 (Frontend) consumes them. Discovering them late stalls the FE track.

1. **`GET /api/sheets/{id}/` must return per-block geometry** so the review screen can draw annotation
   boxes over the scanned crop: `crop_image_url`, `image_width`, `image_height`, `content_type`,
   `ocr_engine`, `reconstructed_text`, and for each annotation `{kind, intent, bbox:{x,y,w,h},
   confidence, resolved_by}`. **`bbox` must be in the crop's own pixel coordinates** — not page
   coordinates, not normalised. The SVG `viewBox` handles all scaling.
2. **`GET /api/exams/{id}/summary/`** — `bands`, `mark_distribution`, `concept_miss_rate`
   (`GROUP BY concept, status` over `ConceptScore`), `avg_confidence`, `vlm_escalation_rate`.
3. **`GET /api/exams/{id}/sheets/`** — review queue rows with `band`, `confidence`, `approved_at`,
   filterable by band and status.

**Progress:** poll `status/` every 2 s from TanStack Query. The Celery task writes its current stage to
the sheet row. **The stage enum has 12 values after L3.5/L4.5** — the frontend stepper renders them
verbatim, so backend and frontend must agree exactly:

```
queued · preprocessing · segmentation · annotations · adjudication · ocr ·
specialized · reconstruction · retrieval · coverage · scoring · feedback · done
```

SSE is a stretch goal only — polling is robust and costs an hour, not a day.

**Auth boundaries** (write tests for these — they are the easiest marks to lose in a viva):
teachers only touch their own exams; students only see `approved_at IS NOT NULL` results; the student
result endpoint must never expose another student's sheet.

---

## 9. Build order — phases, gates, parallelism

There is no calendar here. What matters is **dependency order**: what blocks what, and what can proceed
in parallel. Each phase ends at a **gate** — something you can run and demonstrate — not a date. Work
continuously; a phase is done when its gate passes, however long that takes.

Tracks: **CV** (image → text) · **AI** (text → marks) · **BE** (Django/API) · **FE** (React).
Suggested owners: C and K on CV then FE, S on AI, U on BE — but the gates matter more than the names.

```
Phase 0 ──┬── Phase 1  CV ──┐
          ├── Phase 2  AI ──┼── Phase 3 ── Phase 6 ── Phase 7
          └── Phase 4  BE ──┴── Phase 5  FE ──┘
```

---

### Phase 0 — Foundation ▸ *blocks literally everything*

- Repo, branch strategy, pre-commit, `pyproject.toml`, CI skeleton.
- `docker compose up` → Postgres+pgvector + Redis; Django boots; migrations run; **`CREATE EXTENSION
  vector` succeeds**.
- `scripts/smoke_nim.py` — register at `build.nvidia.com`, confirm credit balance, and record the
  **exact model IDs** and measured latency for chat, vision, and `nv-embedqa` embedding.
- `ai/providers/base.py` + `ai/providers/nim.py` skeleton with three working methods: `chat()`,
  `describe_image()`, `embed()`. Skeleton only — retry/mock/ollama come in Phase 2.
- **Record the embedding dimension.** It fixes the `VECTOR(n)` column width; changing it later is a
  migration across every stored concept.
- Download dataset subsets (§3 caps).

**Gate:** a Python one-liner calls the VLM on a real image and gets text back; embedding dimension is
written down; Postgres + Redis + Django all up.

> ⚠️ **Start collecting physical answer sheets now.** 20–50 sheets, manually graded by a teacher, are a
> hard input to Phase 6 and the *only* item here you cannot compress by working harder. Everything else
> is code; this is logistics. Begin in Phase 0 and let it run in the background throughout.

---

### Phase 1 — CV track ▸ *needs Phase 0's provider skeleton*

Build in order; each step consumes the previous one's output.

| Step | Module | Note |
|---|---|---|
| L1 | `preprocessing.py` | denoise → CLAHE → deskew → adaptive threshold → `quality_score()` 0–1 |
| L2 | `segmentation.py` | projection profile + `find_peaks`; question-number matching; multi-page linking |
| L3 | `annotations/*` | strike / underline / arrow / margin. **Every detector must return a confidence, not just a label** — L3.5 keys off that number and cannot adjudicate a bare verdict |
| L3.5 ⟨VLM⟩ | `annotations/adjudicator.py` | confidence < 0.70 → VLM classifies strike vs underline vs ruled line; sets `resolved_by` |
| L4 ⟨VLM⟩ | `ocr/router.py`, `tesseract_engine.py`, `vlm_engine.py` | quality ≥ .60 → PSM 6; else morph + PSM 11; OCR confidence < 40% → VLM transcribe |
| L4.5 ⟨VLM⟩ | `ocr/content_type.py`, `specialized.py` | non-text block → VLM description → same text stream |
| L5 | `reconstruct.py` | drop deletions → stitch margins at arrow tips (KD-tree) → sort reading order |

**Parallelism inside this phase:** once L2 lands, the annotation chain (L3 → L3.5) and the OCR chain
(L4 → L4.5) are independent and can be built by two people simultaneously. They converge at L5.

**Gate:** a scanned image goes in; `reconstructed_text` + typed `Annotation[]` come out, verified against
the golden fixtures.

---

### Phase 2 — AI / RAG track ▸ *needs Phase 0; runs parallel to Phase 1*

1. **Harden providers** — `mock.py` (deterministic, **with a call counter** for the VLM-volume tests),
   `ollama.py`, `retry.py` (strict-JSON prompt + parse repair + bounded retry), per-call cost log.
2. **Concept indexing** — extraction prompt → strict JSON, weights normalised to 1.0 → embed → write
   `Concept.embedding` → `ivfflat` index → `model_answer_hash` guard so re-saving doesn't re-index.
3. **Retrieval** — `chunker.py` (sentence chunks + underline tags) → `embedder.py` (one batched call) →
   `retriever.py` (per-concept top-3 via pgvector `<=>`).
4. **Coverage** — prompt takes *only* retrieved evidence; 3 independent passes via `ThreadPoolExecutor`;
   majority vote per concept; all three persisted to `EvaluationRun`.
5. **Scoring, feedback, confidence** — bands from §5, underline ×1.10, similarity-vs-LLM downgrade,
   3-section feedback, composite confidence → 🟢/🟠/🔴.

**Gate:** given a plain-text answer plus a question's stored concepts, the module returns marks,
per-concept breakdown, feedback and a confidence band — **offline, using mock providers.**

---

### Phase 3 — Pipeline integration ▸ *needs 1 + 2*

`ai/pipeline.py` wires all ten stages into one callable and returns a typed result object.

**Gate:** `tests/integration/test_full_pipeline.py` green — fixture sheet in, complete result out.

---

### Phase 4 — Backend / API ▸ *needs Phase 0; can run parallel to 1 and 2 using mock providers*

1. Models + migrations (§7).
2. Auth — JWT, roles, and the permission boundaries from §8.
3. `evaluate_sheet` Celery task writing the **12-stage** progress enum.
4. Upload endpoint (UUID filename, MIME + size validation, traversal guard) + status endpoint.
5. Remaining endpoints, **including the three frontend-driven ones in §8** — block geometry on sheet
   detail, `/summary/`, `/sheets/` review queue. Agree the `bbox` coordinate space with the FE track
   before implementing.
6. Failure paths — OCR empty, VLM timeout, LLM JSON failure, NIM 429/quota. Every one marks the sheet
   `FAILED` with a readable error; nothing may hang or silently zero the marks.

**Gate:** upload → 202 → worker runs → rows land in the DB; permission tests green; full httpie/Postman
collection passes.

---

### Phase 5 — Frontend ▸ *see `FRONTEND_PLAN.md`*

Needs the §8 **contract agreed**, not necessarily implemented — MSW fixtures let the FE track start
before the endpoints exist. Its own phases and gates are in that document.

**Gate:** teacher completes upload → review → override → approve in the browser; student sees only their
own approved result.

---

### Phase 6 — Calibration + benchmarking ▸ *needs Phase 3 + the collected sheets*

- `scripts/calibrate_thresholds.py` on STS-B → **writes the calibrated values into `ai/config.py`**.
  This is what turns "we chose 0.72" into "0.72 is empirically justified".
- `scripts/benchmark.py` over the manually graded sheets → Pearson *r*, per-layer accuracy, triple-pass
  variance, VLM escalation rate, L3.5 adjudication lift.

**Gate:** `docs/benchmarking_report.md` exists with real measured numbers — including any that miss
target, with an analysis of why.

---

### Phase 7 — Delivery

README (setup, NIM key, datasets, API reference) · architecture diagrams · demo script · recorded video ·
final code review · Phase 2 report.

**Demo script:** login → create exam + model answer (show concepts appear) → add students → upload four
sheets exercising every path (neat / messy→VLM / ambiguous strike→L3.5 / hand-drawn diagram→L4.5) →
review → override one → approve → student view.

---

### Critical path

Everything else has slack. These do not:

```
Phase 0 provider skeleton  →  unblocks L3.5, L4, L4.5 (three separate modules stall without it)
Physical sheet collection  →  Phase 6 cannot start; longest lead time in the project
§8 contract agreement      →  BE and FE both build against it; a late change costs both tracks
Embedding dimension        →  fixes VECTOR(n); late change = migration across all stored concepts
```

---

## 10. Testing strategy

**Principle: CI never touches the network.** Every test runs against `providers/mock.py`, which returns
fixed concept lists, verdicts and embeddings. Real-provider tests are `@pytest.mark.slow` and run manually.

**1. Unit tests — per layer, golden fixtures** (`tests/unit/`)
Commit 8–10 small sample images to `tests/fixtures/sheets/` and a golden JSON per layer per sample.
Each layer asserts against its golden file, so a regression in preprocessing is caught before it silently
corrupts OCR three layers downstream.
- `test_preprocessing.py` — deskew corrects a known 5° rotation; quality score orders neat > messy.
- `test_segmentation.py` — block count and question-number extraction on synthetic multi-question pages.
- `test_annotations.py` — synthetic images with a drawn strike / underline / arrow at known coordinates;
  assert kind, intent and bbox within tolerance. **Synthetic images make this deterministic** — do not
  rely only on real scans here.
- `test_adjudicator.py` *(L3.5)* — three synthetic crops: a line **through** text, a line **under** text,
  and a table border. Assert each is classified correctly. **Then assert the cost guard:** with a
  high-confidence annotation, `mock_vlm.call_count == 0`; with an ambiguous one, `== 1`. A silent
  regression that sends every annotation to the VLM would otherwise only show up as a NIM bill.
- `test_content_type.py` / `test_specialized.py` *(L4.5)* — a text block classifies as `TEXT` and never
  calls the VLM; a diagram block classifies as `DIAGRAM`, calls it once, and its description reaches
  `reconstructed_text` so downstream retrieval can see it.
- `test_reconstruct.py` — struck text absent, margin text present at the right index, reading order correct.
- `test_scoring.py` — table-driven over every band boundary (0.49/0.50/0.71/0.72), underline boost,
  similarity-vs-LLM downgrade, weight normalisation. **Pure functions, zero mocks, highest ROI in the suite.**
- `test_confidence.py` — formula and band cutoffs.

**2. Provider contract tests** (`tests/unit/test_providers.py`)
One shared test class run against both `mock` and (marked slow) `nim`, asserting: valid JSON out,
weights sum to 1.0 ± 0.01, embedding dimension matches config, malformed JSON triggers the retry wrapper.
Guarantees a provider swap cannot silently break the pipeline.

**3. Integration test** (`tests/integration/test_full_pipeline.py`)
`ai/pipeline.run()` on a fixture sheet with mock providers → assert marks, per-concept statuses, annotation
counts and confidence band against a golden result. This is the regression net for the whole system.

**4. Django/API tests** (`apps/*/tests/`, `pytest-django` + `factory-boy`)
- Auth: register/login/refresh, role enforcement.
- **Permissions (write these deliberately):** teacher B cannot read teacher A's exam; student cannot read
  an unapproved result; student cannot read another student's result.
- Upload: rejects oversize files, wrong MIME, traversal-style filenames; stores under a UUID.
- Task: `evaluate_sheet` with `CELERY_TASK_ALWAYS_EAGER=True` + mock providers → DB rows correct.
- Idempotency: re-saving an unchanged model answer does **not** re-index concepts.
- Failure paths: provider raises → sheet marked `FAILED` with a message, never left `RUNNING`.

**5. Dataset / accuracy tests** (`tests/datasets/`, `@pytest.mark.slow`)

| Dataset | Validates | Target |
|---|---|---|
| IAM (subset) | OCR + preprocessing across handwriting quality | CER measured & reported |
| FUNSD (subset) | Segmentation on noisy layouts | ≥ 90% block boundary accuracy |
| SROIE (subset) | Strike-through detection on real lines | ≥ 90% classification accuracy |
| STS-B | **Threshold calibration** for 0.72 / 0.50 | correlation with human similarity |
| ASAP-SAS (subset) | LLM grading component | Pearson r reported |
| Own 20–50 graded sheets | **End-to-end ground truth** | **Pearson r ≥ 0.80** |

**6. Frontend**
- Vitest + React Testing Library: `ConceptBar` renders correct widths/colours per status;
  `ConfidenceBadge` maps score → 🟢/🟠/🔴; override form validation (cannot exceed `max_marks`).
- Mock Service Worker for API contract tests.
- **One** Playwright E2E happy path (login → upload → poll → review → approve). One is enough; a full E2E
  suite is not worth the effort relative to its return here.

**7. CI** (`.github/workflows/ci.yml`)
`ruff` → `black --check` → `pytest -m "not slow" --cov=ai --cov=apps` → `vitest run`.
Services: postgres+pgvector, redis. **Coverage gate: 70% on `ai/`** — that is where the marks and the
research contribution live; a bug in `scoring.py` is a wrong grade on a real student.

---

## 11. Verification — end-to-end

```bash
# 0. infra
docker compose up -d                    # postgres+pgvector :5432, redis :6379
cp .env.example .env                    # set NIM_API_KEY

# 1. backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/smoke_nim.py             # MUST pass before anything else
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver              # :8000
celery -A config worker -l info         # separate terminal

# 2. frontend
cd frontend && npm install && npm run dev   # :5173

# 3. seed + demo
python scripts/seed_demo.py             # exam, 3 students, 3 sample sheets

# 4. tests
pytest -m "not slow" --cov=ai --cov=apps
pytest -m slow                          # dataset accuracy (needs downloads)
cd frontend && npm run test && npx playwright test

# 5. benchmark
python scripts/calibrate_thresholds.py  # STS-B → writes ai/config.py
python scripts/benchmark.py             # → docs/benchmarking_report.md
```

**Manual acceptance run (this is the demo):** log in as teacher → create exam → add a question with a
model answer → confirm 5–8 concepts with weights appear → add 3 students → upload **four** sheets chosen to
exercise every path (neat → Tesseract only, no VLM at all / messy → VLM transcription / annotated with an
ambiguous strike-through → L3.5 adjudication / containing a hand-drawn diagram → L4.5) → watch the
progress bar advance through stages → open review, check concept bars, annotation summary and confidence
band → override one score, add a comment → approve → log in as that student → confirm marks, bars and
3-section feedback are visible, and that the other student's result is not.

---

## 12. Success criteria

| Metric | Target |
|---|---|
| Pearson r vs human grader | **≥ 0.80** |
| Overall accuracy on standard datasets | ≥ 85% |
| Strike-through intent classification | ≥ 90% |
| Margin arrow detection precision | ≥ 85% |
| Triple-pass variance | < 0.5 marks std-dev |
| Per-sheet latency | < 30 s |
| `ai/` test coverage | ≥ 70% |
| **VLM escalation rate** | report it (blocks sent to VLM ÷ total blocks) — evidence the adaptive routing is selective, not a blanket VLM pass |
| **Annotation adjudication lift** | report L3.5 accuracy vs CV-only baseline — quantifies the hybrid's value |

Report the numbers you actually measure, including any that miss target — a documented gap with an
analysis of *why* reads far better in a Phase 2 viva than a suspiciously round claim.

---

## 13. Risk register

| Risk | Mitigation |
|---|---|
| **NIM free credits exhausted mid-project** | Provider interface already abstracts it — Groq / Gemini / OpenRouter free tiers swap in via one class (~1 hr). Cache aggressively; concepts index once per question. |
| **VLM call volume creeps up** (3 call sites now, not 1) | Every site is escalation-only, gated on a confidence threshold in `ai/config.py`. Unit tests assert `call_count == 0` on clean input. `EvaluationRun` logs per-sheet VLM calls, so a regression shows up in the data, not the bill. |
| **VLM misreads a diagram** and the student is graded on a wrong description | `AnswerBlock.content_type != TEXT` lowers the confidence score, so diagram-bearing sheets bias toward 🟠/🔴 and land in front of the teacher. The reconstructed description is shown beside the original crop in the review UI. |
| **Disk exhaustion (12 GB free)** | Dataset subsets only with size caps in `download_datasets.py`; `media/` and `datasets/` gitignored; monitor with `df -h` daily. |
| Physical answer sheets not collected in time | **Start in Phase 0 and run it in the background.** Logistics, not code — the one input you cannot compress by working harder, and Phase 6 cannot begin without it. |
| LLM returns malformed JSON | `providers/retry.py`: strict JSON prompt + parse-repair + bounded retry + fallback verdict marked low-confidence. |
| OCR fails on very messy handwriting | Adaptive PSM → VLM fallback → below-threshold blocks flagged 🔴 for teacher review rather than silently mis-graded. |
| Network down on demo day | Ollama 3B fallback provider + `seed_demo.py` with pre-computed results; rehearse the offline path during Phase 6. |
| Frontend scope creep | `FRONTEND_PLAN.md` carries a pre-agreed cut list, ordered — so the decision is made calmly in advance, not under pressure. Teacher review is the demo-critical surface; the annotation overlay is never cut. |
| pgvector/Postgres unfamiliarity | Spike it in Phase 0; fallback is FAISS in-process with vectors in a `BYTEA` column (same `store.py` interface). |

---

## 14. Verify in Phase 0 before committing to the plan

These are assumptions, not facts, and each has a cheap fallback:

1. **NIM free-credit amount and exact model IDs** — chat, vision and `nv-embedqa` embedding. Record real
   IDs and measured latency in `.env.example` and `docs/architecture.md`. *(Fallback: Groq / Gemini free tier.)*
2. **NIM vision model quality — test all three jobs separately**, they are not equally easy:
   (a) transcribe one messy handwritten crop *(L4)*;
   (b) classify one line as strike-through vs underline *(L3.5)*;
   (c) describe one hand-drawn diagram *(L4.5)*.
   Expect (b) and (c) to work more reliably than (a) — transcribing bad handwriting is the hardest of the
   three. *(Fallback per job: (a) Tesseract PSM 11 only + flag for review; (b) Hough geometry alone;
   (c) mark the block `DIAGRAM` and route it straight to teacher review unscored.)*
3. **Embedding dimension** — sets the `VECTOR(n)` column width; changing it later means a migration.
4. **pgvector extension enables cleanly** in the chosen Postgres image.
5. **Tesseract accuracy on your actual sheet format** — scan resolution matters more than most people
   expect; standardise on 300 DPI for all collected sheets.
