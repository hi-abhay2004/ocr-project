# Frontend — AI-Driven Answer Sheet Evaluation

React + TypeScript SPA for the teacher and student sides of the evaluation system.
Implements `../FRONTEND_PLAN.md`.

## Run it

```bash
npm install
npm run dev          # http://localhost:5173
```

It boots **against mock data by default** — no Django, no Postgres, no NIM key needed.
Log in as `teacher` or `student` with any password.

## Mock mode vs. real backend

`.env.development` sets `VITE_USE_MSW=true`, which starts [MSW](https://mswjs.io) in the
browser and serves the entire §8 API from `src/tests/mocks/`. That includes a **simulated
pipeline**: an uploaded sheet walks all 12 stages on a timer, so the progress stepper and
the polling logic are exercised without a Celery worker.

To point at the real Django API instead:

```bash
# .env.development
VITE_USE_MSW=false
```

`vite.config.ts` proxies `/api` and `/media` to `localhost:8000`, so there is no CORS
configuration in development. Nothing else changes — if a screen breaks when you flip this
flag, the backend has drifted from `src/types/api.ts`, which is exactly the signal the mock
layer exists to give.

## Commands

| Command | What it does |
|---|---|
| `npm run dev` | Dev server on :5173 |
| `npm run typecheck` | `tsc -b`, strict mode |
| `npm test` | Vitest — component and unit tests |
| `npm run test:e2e` | Playwright — boots the dev server itself |
| `npm run build` | Typecheck + production build |
| `npm run verify` | All three, in order |

## The two tests worth knowing about

**`src/tests/auth.test.ts` — single-flight refresh.** Fires five concurrent requests against
an expired token and asserts `/auth/refresh/` was called exactly **once**. Without a shared
in-flight promise, four of five refreshes fail against the rotated token and the user is
logged out mid-session. The bug only appears under concurrency and never in manual testing.

**`e2e/overlay-scaling.spec.ts` — the three-width overlay check.** Measures every annotation
box as a *fraction* of the rendered crop at 1440 / 1024 / 768 px and asserts the fractions
match. That is precisely the property the SVG `viewBox` is supposed to guarantee, and it
fails immediately if anyone reintroduces JS scale maths or the backend sends `bbox` in page
coordinates instead of crop coordinates.

## Layout

```
src/
├── lib/axios.ts        ← auth core: both interceptors + single-flight refresh
├── types/api.ts        ← the §8 contract; change with the serializer, same commit
├── auth/               ← context, useAuth, role guards
├── api/                ← one thin wrapper per resource
├── hooks/              ← TanStack Query; ALL server state lives here
├── components/
│   ├── AnnotationOverlay.tsx   ← ★ the demo centrepiece
│   ├── PipelineProgress.tsx    ← 12-stage stepper
│   └── ui/                     ← shadcn output, do not hand-edit
├── pages/teacher/ · pages/student/
└── tests/mocks/        ← the whole mock backend
```

## Deviations from FRONTEND_PLAN.md

Recorded because the plan was written before the packages were installed:

| Plan says | Actually used | Why |
|---|---|---|
| React 18 | React 19 | current stable; no API we use changed |
| react-router-dom v6 | v7 | the APIs used here are identical |
| `tailwind.config.js` | Tailwind v4, CSS-first | v4 removed the JS config; theme lives in `src/index.css` |
| shadcn `toast` | `sonner` | shadcn deprecated `toast` in favour of `sonner` |
| zod v3 | zod v4 | current major |

One npm advisory is knowingly accepted: `react-router` has an RSC-mode CSRF advisory
affecting 7.12–8.2. This app is a pure SPA with no RSC and no server, so the affected code
path is never reached. Downgrading to the "fixed" 7.11.0 pulls in **14** other advisories,
which is strictly worse.
