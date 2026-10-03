# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Repo root is `eval-sys-rag-/` (contains `manage.py`, `.git`). Answer-sheet evaluation system: scanned handwritten sheets go through a CV/OCR pipeline, then RAG + LLM grading against a model answer. Django/DRF/Celery backend, React/Vite frontend in `frontend/`.

## Commands

Backend (Python >=3.12, run from repo root):

```bash
docker compose up -d                 # postgres+pgvector (host port 5435), redis. `make up` uses sudo docker-compose (Makefile comment: machine-specific)
pip install -e ".[dev]"
python manage.py migrate
python manage.py runserver           # :8000
celery -A config worker -l info      # REQUIRED for uploads to evaluate
python scripts/seed_demo.py          # demo exam with mock-provider results

pytest                               # excludes `slow` marker by default (addopts)
pytest path/to/test_x.py::test_name  # single test
pytest -m slow                       # needs downloaded datasets / real network provider
pytest --cov=ai --cov=apps --cov-report=term-missing   # = make test
ruff check . && black --check .      # = make lint; make fmt to fix. line-length 100
```

Frontend (`cd frontend`): `npm run dev` (:5173), `npm test` (Vitest), `npm run typecheck`, `npm run verify` (typecheck+test+build), `npm run test:e2e` / `VITE_USE_MSW=false npx playwright test` (E2E against real backend).

Frontend defaults to MSW mock API (`VITE_USE_MSW=true` in `.env.development`). Set `VITE_USE_MSW=false` to hit the real Django API; Vite proxies `/api` and `/media` to :8000.

## Architecture

**`ai/` is pure Python — no Django imports anywhere.** Keep it that way; it is testable with bare `pytest`. `ai/providers/factory.py` reads `os.environ` directly (not Django settings) for the same reason. Duck-typing used in place of model imports (e.g. `ai/pipeline.py` takes concept objects with `.id/.text/.weight/.embedding`).

Pipeline layers:
- L1-L5 (CV/OCR): `preprocessing`, `segmentation`, `annotations/` (strikethrough/underline/arrows/margins + `adjudicator`), `ocr/` (router picks Tesseract vs VLM by quality/content type), `reconstruct`.
- L6-L8 (grading): `concepts`, `rag/` (chunker, embedder, retriever, pgvector store), `coverage` (LLM check), `scoring`, `confidence`, `feedback`; `pipeline.evaluate_question` orchestrates one question.
- `ai/config.py`: all thresholds/weights/targets in one place. Tune here, not inline.

Providers: `LLMProvider`/`VLMProvider`/`EmbeddingProvider` interfaces in `ai/providers/base.py`; implementations `mock`, `nim`, `gemini`, `ollama`, `sbert`. Selected by `LLM_PROVIDER` env (default `mock`; mock is forced under pytest). Everything runs with zero keys/network on mock.

Django glue (`apps/`): `accounts`, `students`, `exams`, `evaluation`, `core`. Flow: upload -> Celery `apps/evaluation/tasks.py:evaluate_sheet` -> `pipeline_runner.py` (decode pages incl. PDF via PyMuPDF, segment each page, group blocks by question number across pages, run L3-L5 per block, then `ai.pipeline.evaluate_question`). A question with no matching blocks still gets an Evaluation (all concepts MISSING, zero marks), not a skip. `manage.py reset_stuck_evaluations` recovers stuck sheets. Settings split in `config/settings/{base,dev,prod,test}.py`; pytest uses `config.settings.test`.

Tests: `tests/unit/` (pure `ai/`, synthetic CV fixtures in `cv_fixtures.py`) plus per-app `apps/*/tests/`. Root `conftest.py` (next to `manage.py`) holds shared fixtures so it reaches both trees.

## Gotchas

- README says "three independent passes, majority voted"; code has `COVERAGE_PASS_COUNT = 1` in `ai/config.py`. Trust the code.
- `MAX_CONCURRENT_CONCEPTS = 2` in `ai/pipeline.py` is tuned against NIM free-tier rate limits (429s at 4). Don't raise without reason.
- `EMBEDDING_DIM = 2048` — changing it needs a pgvector migration.
- README's `LLM_PROVIDER` comment omits `gemini`; factory supports it.
- Stray `ai/rag/chunker.py.patch` exists; not part of the test suite. `scripts/manual_vlm_check.py` is a manual real-Gemini smoke script, also not part of the suite.
- Docs: `docs/api.md`, `docs/evaluation_workflow.md`; README references `PLAN_OF_ACTION_V2.md`, `BACKEND_PLAN.md`, `FRONTEND_PLAN.md` which are not in the repo.
