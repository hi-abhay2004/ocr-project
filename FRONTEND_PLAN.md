# Frontend Implementation Plan

**Companion to `PLAN_OF_ACTION_V2.md` §6, §8, §9 — this is Phase 5 (Frontend).**
Target file when approved: `docs/FRONTEND_PLAN.md`

---

## 1. Context

`PLAN_OF_ACTION_V2.md` specifies the frontend as one line of stack ("React 18 + Vite + TS, TanStack
Query, Recharts, Tailwind") and a flat list of page names. That is enough to place the work in the build
order but not enough to build from — it leaves the auth mechanism, the data-fetching strategy, the
component contracts and the annotation visualisation entirely undefined.

This document specifies the frontend completely enough that work can start with no design decisions
still open.

**It also surfaces a sequencing problem.** Two of the four decisions below require data the current API
does not return. They belong to **Phase 4 (Backend)** in the main plan, which precedes this one — so
they must be agreed in §8 before the backend track implements its endpoints, or Phase D stalls. §3 lists
them.

### Decisions locked in

| Decision | Choice |
|---|---|
| Component layer | **shadcn/ui + Tailwind** — owned source, Radix a11y, no runtime dep |
| Annotation display | **SVG overlay** on the scanned crop, colour-coded, layer-toggleable |
| Analytics | Per-sheet review **+ one exam-summary page** (distribution, most-missed concepts) |
| Auth | **Access token in memory, refresh in localStorage**, silent rotation on 401 |

---

## 2. Stack

| Concern | Package | Note |
|---|---|---|
| Build | `vite` + `@vitejs/plugin-react` | dev proxy to `:8000`, no CORS in dev |
| Language | `typescript` | strict mode on |
| Routing | `react-router-dom` v6 | nested layouts + role guards |
| Server state | `@tanstack/react-query` v5 | **all** API state; no Redux |
| HTTP | `axios` | interceptors carry auth + refresh |
| Styling | `tailwindcss` | |
| Components | `shadcn/ui` | Radix + `cva` + `tailwind-merge` |
| Icons | `lucide-react` | ships with shadcn |
| Forms | `react-hook-form` + `zod` | schema validation, typed |
| Charts | `recharts` | **summary page only**, lazy-loaded |
| Test | `vitest`, `@testing-library/react`, `msw` | |
| E2E | `@playwright/test` | one happy path |

**Client state needs no library.** Everything that matters lives on the server; TanStack Query owns it.
The only genuinely local state is auth (React context) and per-screen UI toggles (`useState`). Adding
Redux or Zustand here would be pure ceremony.

shadcn components to pull in Phase A:
`button · input · label · select · table · dialog · card · badge · progress · tabs · toast · dropdown-menu · skeleton · alert · checkbox · textarea · separator`

---

## 3. ⚠️ API additions required — must be agreed before Phase 4 implements

These are consequences of the overlay and summary decisions. They are already recorded in
`PLAN_OF_ACTION_V2.md` §8 and assigned to the backend track (Phase 4).

### 3.1 Sheet detail must carry geometry

`GET /api/sheets/{id}/` currently returns "full result + per-concept breakdown". The overlay additionally
needs, **per block**:

```jsonc
{
  "blocks": [{
    "id": 12,
    "question_id": 3,
    "crop_image_url": "/media/blocks/uuid.png",
    "image_width": 1240,          // natural px — required for the SVG viewBox
    "image_height": 480,
    "quality_score": 0.71,
    "content_type": "TEXT",       // TEXT | DIAGRAM | TABLE | EQUATION
    "ocr_engine": "TESSERACT_6",
    "reconstructed_text": "...",
    "annotations": [{
      "kind": "STRIKE",           // STRIKE | UNDERLINE | ARROW | MARGIN
      "intent": "CORRECTION",     // CORRECTION | EMPHASIS | INSERTION
      "bbox": { "x": 210, "y": 88, "w": 96, "h": 14 },   // original-crop px
      "confidence": 0.62,
      "resolved_by": "VLM"        // CV | VLM
    }]
  }]
}
```

`bbox` **must be in the crop's own pixel coordinates**, not page coordinates and not normalised — the SVG
`viewBox` handles scaling (§7).

### 3.2 New endpoint — exam summary

```
GET /api/exams/{id}/summary/
{
  "sheet_count": 58, "approved_count": 41,
  "bands": { "green": 30, "orange": 19, "red": 9 },
  "mark_distribution": [{ "bucket": "0-2", "count": 3 }, ...],
  "concept_miss_rate": [
    { "concept": "BCNF every determinant is a candidate key", "missing": 34, "partial": 11, "covered": 13 }
  ],
  "avg_confidence": 0.78,
  "vlm_escalation_rate": 0.17
}
```

`concept_miss_rate` is a `GROUP BY concept, status` over `ConceptScore` — cheap, and it powers the one
screen a real teacher would actually use.

### 3.3 Review queue listing

```
GET /api/exams/{id}/sheets/?band=red&status=DONE
→ [{ id, student: {usn, name}, status, band, confidence, total_marks, approved_at }]
```

### 3.4 Registration payload

`POST /api/auth/register/` is already listed in `PLAN_OF_ACTION_V2.md` §8, but its body was never
specified. The signup screen sends:

```jsonc
{
  "username": "charan",
  "full_name": "P Charan Chandra",
  "email": "charan@bmsit.in",
  "password": "…",
  "role": "TEACHER",          // TEACHER | STUDENT
  "usn": "1BY22CS001"         // STUDENT only — key is ABSENT for teachers, not ""
}
```

Two things the serializer must do:

1. **Return a `TokenPair`**, not just the created user — a successful signup logs straight in rather
   than bouncing to a login form the person has already effectively filled.
2. **Create or link the `Student` row** when `role == STUDENT`, keyed on `usn`. That USN is the only
   thing joining a login to the answer sheets uploaded for that person; without it a student can
   authenticate and still see nothing. Reject a `usn` already claimed by another account.

Errors must be **field-keyed** (`{"usn": ["..."]}`), which is DRF's default — the form surfaces the
specific field message rather than a generic failure.

### 3.5 Stage vocabulary is stale

§8 lists 8 stages; the pipeline now has 12 after L3.5/L4.5. The progress bar renders these verbatim, so
fix the enum in both places:

```
queued · preprocessing · segmentation · annotations · adjudication · ocr ·
specialized · reconstruction · retrieval · coverage · scoring · feedback · done
```

---

## 4. File layout

```
frontend/
├── index.html · vite.config.ts · tsconfig.json
├── tailwind.config.js · components.json          # shadcn config
├── package.json · .env.development
└── src/
    ├── main.tsx                    # QueryClientProvider + AuthProvider + Router
    ├── App.tsx · router.tsx        # route table + role guards
    │
    ├── lib/
    │   ├── axios.ts                # instance + both interceptors  ← auth core
    │   ├── queryClient.ts          # defaults: staleTime, retry policy
    │   └── utils.ts                # cn() from shadcn
    │
    ├── types/api.ts                # hand-written mirrors of DRF serializers
    │
    ├── auth/
    │   ├── AuthContext.tsx         # {user, login, logout, isLoading}
    │   ├── useAuth.ts
    │   └── ProtectedRoute.tsx      # role-gated: requiredRole?: 'TEACHER'|'STUDENT'
    │
    ├── api/                        # one file per resource — thin wrappers only
    │   ├── auth.ts · exams.ts · questions.ts · students.ts
    │   ├── sheets.ts · evaluations.ts · results.ts
    │
    ├── hooks/                      # TanStack Query hooks — ALL server state
    │   ├── useExams.ts · useQuestions.ts · useConcepts.ts
    │   ├── useStudents.ts · useSheets.ts
    │   ├── useSheetStatus.ts       # ← the 2s poller
    │   ├── useEvaluation.ts · useExamSummary.ts · useStudentResults.ts
    │
    ├── components/
    │   ├── ui/                     # shadcn output — do not hand-edit
    │   ├── layout/{TeacherShell,StudentShell,Header,Nav}.tsx
    │   ├── AnnotationOverlay.tsx   # ★ the centrepiece (§7)
    │   ├── ConceptBar.tsx · ConceptBarList.tsx
    │   ├── ConfidenceBadge.tsx · BandPill.tsx
    │   ├── AnnotationLegend.tsx · AnnotationSummary.tsx
    │   ├── PipelineProgress.tsx    # 12-stage stepper
    │   ├── ScoreOverrideForm.tsx
    │   ├── FeedbackPanel.tsx       # 3-section feedback
    │   ├── CsvImportDialog.tsx
    │   └── states/{Loading,Empty,ErrorState}.tsx
    │
    ├── pages/
    │   ├── Landing.tsx             # public homepage — project description + auth CTAs
    │   ├── Login.tsx               # shared; redirects by role
    │   ├── Signup.tsx              # role picker; USN required for STUDENT only
    │   ├── teacher/
    │   │   ├── ExamList.tsx · ExamForm.tsx
    │   │   ├── QuestionEditor.tsx      # shows extracted concepts
    │   │   ├── StudentManage.tsx
    │   │   ├── SheetUpload.tsx
    │   │   ├── ReviewQueue.tsx
    │   │   ├── ReviewDetail.tsx        # ★ the big screen
    │   │   └── ExamSummary.tsx         # lazy-loaded (recharts)
    │   └── student/
    │       ├── ResultList.tsx · ResultDetail.tsx
    │
    └── tests/
        ├── setup.ts · mocks/handlers.ts     # MSW
        └── components/*.test.tsx
```

---

## 5. Auth — the one piece with real complexity

```
POST /api/auth/login/ → { access, refresh }
        access  → in-memory module variable (survives re-render, dies on tab close)
        refresh → localStorage
GET  /api/auth/me/    → { id, username, role } → drives redirect + route guards
```

**Request interceptor** attaches `Authorization: Bearer <access>`.

**Response interceptor** handles 401:

```
401 → is a refresh already in flight?
        yes → await the SAME promise (do not start a second)
        no  → start one: POST /api/auth/refresh/ { refresh }
      on success → store new access → retry the original request ONCE
      on failure → clear tokens → redirect /login
```

**The single-flight rule is the part that bites.** A dashboard mounting five queries at once will fire
five simultaneous 401s; without a shared in-flight promise you get five refresh calls, four of which fail
against a rotated refresh token and log the user out. Hold one `Promise` at module scope and have every
401 await it.

Mark the retried request (`config._retried = true`) so a genuinely-expired session cannot loop.

**Route guards.** `<ProtectedRoute requiredRole="TEACHER">` reads `useAuth()`; unauthenticated →
`/login`, wrong role → that role's home. This mirrors the DRF permission tests one-for-one — the same
boundaries enforced in two places, which is the correct posture: **the frontend guard is UX, the DRF
permission is security.** Never rely on the former.

---

## 6. Server state — TanStack Query

### Key scheme

```ts
['me']
['exams']                    ['exam', examId]
['questions', examId]        ['concepts', questionId]
['students', examId]
['sheets', examId, filters]  ['sheet', sheetId]
['sheetStatus', sheetId]     ['examSummary', examId]
['studentResults']           ['studentResult', examId]
```

### Polling — stop when terminal

```ts
useQuery({
  queryKey: ['sheetStatus', sheetId],
  queryFn: () => getSheetStatus(sheetId),
  refetchInterval: (q) =>
    ['DONE','FAILED','APPROVED'].includes(q.state.data?.status ?? '') ? false : 2000,
})
```

**A poller that never stops is the classic bug here** — it keeps hitting the API for every sheet the
teacher has ever opened. Returning `false` on a terminal status is what ends it.

When status flips `RUNNING → DONE`, invalidate `['sheet', id]` and `['sheets', examId]` so the result
appears without a manual refresh.

### Invalidation map

| Action | Invalidate |
|---|---|
| Save question / model answer | `['questions', examId]`, `['concepts', qId]` |
| Upload sheet | `['sheets', examId]` |
| Status → DONE | `['sheet', id]`, `['sheets', examId]` |
| Override marks | `['sheet', id]`, `['examSummary', examId]` |
| Approve | `['sheet', id]`, `['sheets', examId]`, `['examSummary', examId]` |

### Concept indexing is async — the UI must say so

Saving a model answer enqueues LLM extraction + embedding; concepts do **not** exist when the POST
returns. `QuestionEditor` therefore polls `['concepts', questionId]` until non-empty, showing
*"Extracting concepts…"* with a skeleton. Without this the teacher saves a question, sees nothing, and
assumes it failed.

---

## 7. ★ AnnotationOverlay — the demo centrepiece

This is what visually proves the project's novelty. Everything else is numbers in a table.

### The scaling trick

The crop is 1240 px wide; on screen it might render at 700 px, or 400 px on a laptop. Boxes must land in
the right place at any size. **Do not compute scale factors in JS** — give the SVG a `viewBox` in the
image's natural coordinates and let the browser do it:

```tsx
<div className="relative inline-block w-full">
  <img src={block.crop_image_url} className="w-full h-auto block" />
  <svg
    viewBox={`0 0 ${block.image_width} ${block.image_height}`}
    preserveAspectRatio="none"
    className="absolute inset-0 w-full h-full pointer-events-none"
  >
    {visible.map((a, i) => (
      <rect key={i} x={a.bbox.x} y={a.bbox.y} width={a.bbox.w} height={a.bbox.h}
            className={COLOR[a.kind]}
            strokeDasharray={a.resolved_by === 'VLM' ? '6 3' : undefined}
            style={{ pointerEvents: 'all' }}
            onMouseEnter={() => setHovered(a)} />
    ))}
  </svg>
</div>
```

Because `<img>` and `<svg>` share the same box and the viewBox matches natural dimensions, coordinates
are correct at every breakpoint with **zero arithmetic**. Responsive for free.

### Visual language

| Kind / state | Colour | Meaning |
|---|---|---|
| `STRIKE` + `CORRECTION` | red | text was excluded |
| `UNDERLINE` + `EMPHASIS` | blue | keyword weight-boosted |
| `ARROW` | green | insertion pointer |
| `MARGIN` | amber | text stitched in from margin |
| `resolved_by === 'VLM'` | **dashed border** | CV was unsure — L3.5 adjudicated |

That dashed border is worth the whole component: it makes the CV→VLM escalation **visible on screen**,
so "adaptive VLM sensitivity" stops being a claim in the report and becomes something an examiner can
point at.

### Interactions

- **Layer toggles** — four checkboxes; teacher isolates one annotation type at a time.
- **Hover** → tooltip: kind, intent, `confidence`, and *"decided by VLM"* when applicable.
- **Side-by-side** — original crop left, `reconstructed_text` right, with struck spans shown
  ~~struck~~ and underlined spans highlighted. This is how the teacher verifies the machine read it
  correctly, and it is the strongest single answer to *"how do you know the OCR was right?"*
- **`content_type !== 'TEXT'`** → banner: *"Diagram — described by vision model"*, with the description
  shown as the block's text.

---

## 8. Screen specs

### Public

| # | Screen | Contents |
|---|---|---|
| 0 | **Landing** (`/`) | Public homepage. Hero + the six research gaps + the 10-layer pipeline as a timeline with the three ⟨VLM⟩ layers marked and the RAG boundary drawn + the three VLM call sites with their trigger thresholds + index-time/query-time RAG + the confidence bands + what each role does + stack + measured targets + team, guide and institution. Every number on it (0.70, 0.60, 0.45, the bands, the §12 targets) is quoted from the implementation — **if a threshold changes in `ai/config.py`, change it here too**. Stays reachable while signed in; the CTAs swap for a dashboard link |
| 0b | **Signup** (`/signup`) | Role picker (Teacher / Student) → conditional USN field → RHF + zod with password confirm. Registration returns a token pair, so it lands directly in the new user's dashboard |

### Teacher

| # | Screen | Contents |
|---|---|---|
| 1 | **Login** | shadcn Card + form; role from `/me/` decides redirect. Links to signup |
| 2 | **ExamList** | Table: name, subject, date, sheet count, avg mark. "New exam" → dialog |
| 3 | **ExamForm** | RHF + zod: name, subject, date, total marks |
| 4 | **QuestionEditor** | Add question (number, text, max marks, model answer). On save → *"Extracting concepts…"* skeleton → concept table (text + weight bar), weights summing to 1.00. Editing the model answer warns **"this re-indexes concepts for all students"** |
| 5 | **StudentManage** | Table + manual add + `CsvImportDialog` (drop → **preview parsed rows with per-row errors** → confirm). Never import blind |
| 6 | **SheetUpload** | Student `Select` + drag-drop (JPG/PNG/PDF, ≤10 MB, client-side check). On 202 → `PipelineProgress`: 12-stage stepper, current stage highlighted, elapsed timer. `FAILED` → error + Retry |
| 7 | **ReviewQueue** | Sheets sorted **🔴 → 🟠 → 🟢** (worst first — the queue *is* the triage). Filter by band/status. Row: student, marks, `BandPill`, confidence, approved-tick |
| 8 | **ReviewDetail** ★ | Per question, tabs: **Overlay** (§7) · **Concepts** (`ConceptBarList` — status, similarity, evidence quote, marks, ⚠ on triple-pass disagreement) · **Feedback** (3 sections). Sticky footer: `ScoreOverrideForm` (0 ≤ x ≤ max_marks) + comment + **Approve** (confirm dialog: "the student will see this") |
| 9 | **ExamSummary** | Recharts histogram of marks; **concept miss-rate bar chart sorted worst-first**; band donut; avg confidence; VLM escalation rate. Lazy-loaded |

### Student

| # | Screen | Contents |
|---|---|---|
| 10 | **Login** | shared |
| 11 | **ResultList** | Approved exams only. Empty state: *"No results published yet."* |
| 12 | **ResultDetail** | Per question: marks, `ConceptBarList` (read-only, no evidence quotes), `AnnotationSummary` counts, `FeedbackPanel`, `ConfidenceBadge`, teacher comment if present. **No overrides, no raw crops, no other students** |

### Shared component contracts

```ts
ConceptBar        { concept, status: 'COVERED'|'PARTIAL'|'MISSING',
                    similarity, marks, maxMarks, evidence?, disagreed?: boolean }
ConfidenceBadge   { score: number }           // ≥.80 🟢 | ≥.65 🟠 | else 🔴
PipelineProgress  { stage: Stage, status: SheetStatus, startedAt: string }
AnnotationOverlay { block: Block }
ScoreOverrideForm { evaluationId, current, maxMarks, onSaved }
```

---

## 9. Build order — phases and gates

No calendar. Each phase ends at a gate you can demonstrate in a browser.

```
A Foundation ──┬── B Setup screens
               ├── C Upload + progress ── D Review ★ ── E Student portal
               └── F Analytics                        └── G Polish + tests
```

### Phase A — Foundation ▸ *blocks every screen*

1. `npm create vite@latest -- --template react-ts` · Tailwind · `npx shadcn@latest init` · pull the
   component list from §2
2. Vite proxy `/api → localhost:8000` — removes CORS from dev entirely
3. `types/api.ts` mirroring the DRF serializers
4. `lib/axios.ts` — both interceptors with the **single-flight refresh** (§5)
5. `AuthContext`, `useAuth`, `ProtectedRoute`, `router.tsx`, the two shells
6. Login page, Signup page, and the public Landing page

**Gate:** both roles log in and land on their own home; a wrong-role URL redirects; signup creates an
account of either role and lands in the right dashboard; the single-flight refresh test (§10) passes.
Do not start screens until this holds — every one of them depends on it.

### Phase B — Setup screens ▸ *needs A*

ExamList · ExamForm · QuestionEditor (including the *"Extracting concepts…"* polling skeleton) ·
StudentManage + `CsvImportDialog` with row preview.

**Gate:** a teacher creates an exam with a question, watches the extracted concepts appear with weights
summing to 1.00, and imports a class list from CSV.

### Phase C — Upload + progress ▸ *needs A; API upload/status or MSW fixtures*

SheetUpload · `PipelineProgress` (12-stage stepper) · `useSheetStatus` polling.

**Gate:** upload returns 202 immediately, the stepper advances through stages, polling **stops** on a
terminal status, and the finished result appears without a manual refresh.

### Phase D — Review ★ ▸ *needs C + block geometry (§3.1) live or mocked*

ReviewQueue (worst-band-first) → **ReviewDetail**: `AnnotationOverlay` + legend + layer toggles + hover,
`ConceptBarList`, `FeedbackPanel`, `ScoreOverrideForm`, approve dialog.

Splits cleanly between two people: one on the overlay, one on the concept/feedback/override column.

**Gate:** annotation boxes sit exactly on their features **at three browser widths**; a VLM-adjudicated
box renders dashed; override and approve both persist. This is the demo — treat its gate as the strictest
in the document.

### Phase E — Student portal ▸ *needs D's approve action*

ResultList · ResultDetail, read-only.

**Gate:** an approved result is visible to its own student; an unapproved one is not; another student's
result is unreachable by URL.

### Phase F — Analytics ▸ *needs `GET /api/exams/{id}/summary/`*

`ExamSummary` with recharts, lazy-loaded via `React.lazy`.

**Gate:** histogram + concept miss-rate chart render from real data.

### Phase G — Polish + tests ▸ *continuous, finish last*

Loading / empty / error states on every screen · toast on every mutation · responsive pass (ReviewDetail
is the one that breaks) · Vitest component tests · one Playwright E2E.

**Gate:** `npm run test` and `npx playwright test` green; `npm run build` with zero TS errors.

### If scope has to be cut

In this order — **never cut the overlay**, it is the demo:

1. Phase F analytics → ship after submission
2. Phase E student portal → static read-only page
3. CSV preview → plain upload
4. Layer toggles → always show all annotations

---

## 10. Testing

**Component (Vitest + RTL + MSW)**

| Test | Asserts |
|---|---|
| `ConceptBar` | status → colour + bar width; `disagreed` shows ⚠ |
| `ConfidenceBadge` | 0.81→🟢 0.72→🟠 0.51→🔴, **boundaries 0.80 / 0.65 exactly** |
| `AnnotationOverlay` | N annotations → N `<rect>`; correct `viewBox`; VLM ones dashed; toggling a layer removes only that kind |
| `ScoreOverrideForm` | rejects negative and `> maxMarks`; submits valid |
| `PipelineProgress` | stage → correct step highlighted; terminal stops the timer |
| `ProtectedRoute` | student hitting a teacher route is redirected |

**Auth (the highest-value test in the suite)** — MSW returns 401 once then 200. Fire **three concurrent**
requests; assert `/auth/refresh/` was called **exactly once** and all three succeed. This is the single-
flight rule from §5, and it is the bug most likely to reach demo day undetected.

**E2E (Playwright, one spec)** — teacher logs in → creates exam + question → uploads a fixture sheet →
progress reaches DONE → review shows concept bars → override → approve → student logs in → sees the
mark. Run against Django with `LLM_PROVIDER=mock`, so it's deterministic and offline.

---

## 11. Verification

```bash
# terminal 1 — backend
docker compose up -d && python manage.py runserver
celery -A config worker -l info

# terminal 2 — frontend
cd frontend && npm install && npm run dev        # :5173

# tests
npm run test          # vitest
npx playwright test   # E2E
npm run build         # must pass with zero TS errors
```

**Manual acceptance:** log in as teacher → create exam → add a question → **watch "Extracting concepts…"
resolve into a weighted concept table** → import students by CSV → upload the annotated fixture sheet →
watch the stepper advance through all 12 stages → open review → **toggle annotation layers and confirm
the red box sits exactly on the struck-out word at three browser widths** → hover a dashed box and see
"decided by VLM" → override a mark → approve → log in as that student → see marks, bars and feedback →
confirm a second student's result is unreachable by URL.

That overlay check at three widths is the one manual step worth doing every time — it is the assertion
that the `viewBox` maths (§7) is right, and it is the thing that will be on screen during the viva.

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| **API additions (§3) lag the frontend** | Frontend builds against MSW fixtures matching §3 from Phase A, so every screen progresses even if the endpoints arrive later. Only the final wiring blocks |
| Bbox coordinate space mismatch (page vs crop vs normalised) | Agree §3.1 explicitly with the backend track before either side implements; the first overlay test uses a fixture with a box at a known offset |
| Refresh-token storm logs users out | The single-flight test in §10 catches it |
| Review screen too dense on a laptop | Tabs (Overlay / Concepts / Feedback) instead of one long column; responsive pass in Phase G |
| 12 screens is a lot of surface | shadcn removes the primitive-building entirely; the cut list in §9 is pre-agreed so the decision isn't made under pressure |
| Recharts bloats the bundle | Only on `ExamSummary`, lazy-loaded via `React.lazy` |
