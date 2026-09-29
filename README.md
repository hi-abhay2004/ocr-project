# AI-Driven Automated Answer Sheet Evaluation System

Major project, BMS Institute of Technology & Management, CSE Dept, 2025–26.
Team: P Charan Chandra, R T Kesav Reddy, Sai Charan M M, Nunna Uma Shankar. Guide: Dr. Gireesh Babu C N.

A teacher uploads scanned handwritten answer sheets; the system segments them per question, reads
strikethroughs/underlines/margin notes/diagrams, transcribes the handwriting, retrieves the relevant part
of the model answer for each concept, checks coverage with an LLM (three independent passes, majority
voted), and produces a mark, a confidence band, and written feedback — all reviewable and overridable by
the teacher before a student ever sees it.

See `PLAN_OF_ACTION_V2.md` for the full project rationale/design and `BACKEND_PLAN.md` /
`FRONTEND_PLAN.md` for how each half was actually built, phase by phase.

## Stack

- **Backend:** Django 5 + DRF + SimpleJWT, Celery + Redis, Postgres 16 + pgvector, OpenCV/Tesseract for the
  CV/OCR pipeline, NVIDIA NIM (OpenAI-compatible) for LLM/VLM/embeddings — with a fully mock provider
  path, so the whole system runs and is tested with zero network calls and zero API keys.
- **Frontend:** React + Vite + TypeScript, MSW for mock-backed development.

## Running it

```bash
cp .env.example .env                  # defaults to LLM_PROVIDER=mock — no API key needed
docker compose up -d                  # postgres+pgvector, redis
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python manage.py migrate
python manage.py createsuperuser      # optional

python manage.py runserver            # :8000
celery -A config worker -l info       # separate terminal — required for uploads to evaluate

python scripts/seed_demo.py           # one full exam with real (mocked-provider) evaluation results
```

```bash
cd frontend
npm install
VITE_USE_MSW=false npm run dev        # :5173, talking to the real Django backend above
```

## Testing

```bash
pytest                                          # backend: apps/* (Django+DB) + ai/ (pure Python)
pytest --cov=ai --cov=apps --cov-report=term-missing

cd frontend
npm test                                        # component/unit tests (Vitest)
npx tsc -b                                      # typecheck
VITE_USE_MSW=false npx playwright test          # E2E against the real backend above — the real acceptance test
```

## Layout

```
ai/            Pure-Python AI pipeline — no Django imports, testable with nothing but pytest.
               preprocessing / segmentation / annotations / ocr  (L1-L5, computer vision + OCR)
               concepts / rag / coverage / scoring / confidence / feedback / pipeline  (L6-L8, RAG + LLM grading)
               providers/  mock | nim | ollama | sbert, behind one interface each (LLMProvider/VLMProvider/EmbeddingProvider)
apps/          Django apps — accounts, students, exams, evaluation (the Celery task wiring ai/ into the DB)
config/        Django settings (base/dev/prod/test), Celery app, URL root
scripts/       seed_demo.py, download_datasets.py, calibrate_thresholds.py
frontend/      React app (see frontend/README.md)
```

## What's genuinely real vs. what's a known, documented gap

Everything above the provider boundary is real: real Hough-transform annotation detection, real adaptive
OCR routing, real pgvector retrieval, real triple-pass LLM voting, real composite confidence — all
independently unit-tested (`pytest`, ~250 tests) against synthetic golden fixtures, and exercised
end-to-end through the actual Django+Celery+Postgres stack by the Playwright suite.

Two things are **provider-dependent, not code-dependent**, and this environment doesn't have them:

- A live **NVIDIA NIM API key** — `ai/providers/nim.py` is fully built and unit-tested against a scripted
  client shape, but has never made a real network call. Add `NIM_API_KEY` to `.env` and set
  `LLM_PROVIDER=nim` to switch over; nothing else changes.
- **20–50 real teacher-graded answer sheets** for `scripts/benchmark.py`-style accuracy reporting against
  real ground truth — this is a logistics input (BACKEND_PLAN.md flagged it from the start as the one
  thing that can't be compressed by writing more code), not a missing feature.

`scripts/calibrate_thresholds.py` already runs for real against STS-B — with the mock provider it
correctly reports ~zero correlation (a content-hash isn't a semantic embedder, and the script says so
rather than pretending otherwise); re-run it with a real NIM key for numbers worth acting on.
