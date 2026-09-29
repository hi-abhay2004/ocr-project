import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Boxes,
  Braces,
  CheckCircle2,
  Database,
  Eye,
  FileSearch,
  GraduationCap,
  LogIn,
  PenLine,
  ScanLine,
  Sparkles,
  Target,
  UserPlus,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { HOME_FOR_ROLE } from '@/auth/AuthContext'
import { useAuth } from '@/auth/useAuth'
import { cn } from '@/lib/utils'

/**
 * Public homepage.
 *
 * Content is taken from PLAN_OF_ACTION_V2.md §1, §2, §5 and §12 rather than
 * written fresh — the numbers and thresholds quoted here (0.70, 0.60, 0.45,
 * 0.72, the confidence bands, the success targets) are the ones the system
 * actually implements, so the page stays defensible in a viva. If a threshold
 * changes in `ai/config.py`, change it here too.
 */

/* ── Content ──────────────────────────────────────────────────────────── */

const GAPS = [
  {
    gap: 'Crossed-out text is blindly deleted',
    answer: 'Strike-through intent is classified — correction, emphasis or addition — before anything is dropped.',
  },
  {
    gap: 'One OCR sensitivity for every handwriting',
    answer: 'Each answer block gets a quality score of 0–1, and the OCR path adapts to it.',
  },
  {
    gap: 'Margin content is ignored',
    answer: 'Arrows are traced from their tip back to the insertion point, and margin text is stitched into place.',
  },
  {
    gap: 'A single LLM pass gives unstable marks',
    answer: 'Three independent passes vote per concept; disagreement is recorded and flagged for review.',
  },
  {
    gap: 'No partial credit and no feedback',
    answer: 'Retrieval-grounded partial credit, plus feedback in three sections: strengths, gaps, next steps.',
  },
  {
    gap: 'Underlines are read as ordinary text',
    answer: 'Underlined keywords are detected and their similarity is weighted up by 1.10 before banding.',
  },
]

interface Layer {
  id: string
  title: string
  detail: string
  vlm?: boolean
}

const LAYERS_CV: Layer[] = [
  { id: 'L1', title: 'Preprocess', detail: 'Grayscale, denoise, CLAHE, deskew, adaptive threshold — and a quality score that drives every later decision.' },
  { id: 'L2', title: 'Segment', detail: 'Projection profile finds line and block boundaries, producing one crop per question.' },
  { id: 'L3', title: 'Detect annotations', detail: 'OpenCV geometry finds strike-throughs, underlines, arrows and margin notes — each with a confidence, not just a label.' },
  { id: 'L3.5', title: 'Adjudicate', detail: 'Confidence below 0.70? The vision model decides whether the line crosses the words out, sits under them as emphasis, or is just a ruled line.', vlm: true },
  { id: 'L4', title: 'Adaptive OCR', detail: 'Quality ≥ 0.60 goes to Tesseract PSM 6. Below that: morphology plus PSM 11, and if OCR confidence is still under 40%, the vision model transcribes it.', vlm: true },
  { id: 'L4.5', title: 'Specialized content', detail: 'A diagram, table or equation is not text at all. The vision model describes it in words so a drawn answer is graded on equal terms with a written one.', vlm: true },
  { id: 'L5', title: 'Reconstruct', detail: 'Deletions are dropped, margin text is stitched in at the arrow tip, and the result is sorted back into reading order.' },
]

const LAYERS_RAG: Layer[] = [
  { id: 'L6', title: 'Retrieve', detail: 'The answer is chunked and embedded, then each stored concept retrieves its top-3 closest chunks by cosine similarity.' },
  { id: 'L7', title: 'Generate', detail: 'Three independent coverage passes run against only the retrieved evidence — never the whole answer — and vote.' },
  { id: 'L8', title: 'Score & explain', detail: 'Partial-credit arithmetic, three-section feedback, and a composite confidence that decides whether a human must look.' },
]

const VLM_SITES = [
  {
    layer: 'L3.5',
    cheap: 'OpenCV Hough / Sobel geometry',
    fires: 'annotation confidence < 0.70',
    asks: 'Does this line cross out the text, sit beneath it as emphasis, or is it a table or ruled line?',
  },
  {
    layer: 'L4',
    cheap: 'Tesseract PSM 6 → PSM 11',
    fires: 'quality < 0.60 and OCR confidence < 40%',
    asks: 'Transcribe this handwritten answer exactly.',
  },
  {
    layer: 'L4.5',
    cheap: 'Text-density / contour heuristic',
    fires: 'the block is not text at all',
    asks: 'Describe this diagram, table or equation in words.',
  },
]

const TEACHER_STEPS = [
  'Create an exam and add each question with the answer you would give full marks for.',
  'The model answer is broken into 5–8 weighted concepts automatically and embedded once.',
  'Import the class list as CSV — every parsed row is previewed before anything is saved.',
  'Upload the scanned pages. Evaluation runs in the background across 12 stages.',
  'Review with the annotation overlay: see what was struck, what the vision model decided, what the grader actually read.',
  'Override any mark with a comment, then approve to publish it to the student.',
]

const STUDENT_STEPS = [
  'Sign in and see every result your teacher has published.',
  'Per-concept coverage bars show exactly which points earned marks and which were missed.',
  'Feedback in three sections: what you did well, what was missing, how to improve.',
  'Any comment your teacher left on an overridden mark appears alongside it.',
]

const STACK = [
  { group: 'Backend', items: ['Django 5', 'DRF', 'Celery', 'Redis'] },
  { group: 'Data', items: ['PostgreSQL', 'pgvector', 'IVFFlat ANN'] },
  { group: 'Vision', items: ['OpenCV', 'Tesseract', 'NVIDIA NIM VLM'] },
  { group: 'Language', items: ['NIM chat model', 'nv-embedqa', 'SBERT fallback'] },
  { group: 'Frontend', items: ['React', 'Vite', 'TypeScript', 'TanStack Query', 'Tailwind'] },
]

const TARGETS = [
  { metric: 'Correlation with a human grader', target: 'Pearson r ≥ 0.80' },
  { metric: 'Overall accuracy on standard datasets', target: '≥ 85%' },
  { metric: 'Strike-through intent classification', target: '≥ 90%' },
  { metric: 'Margin arrow detection precision', target: '≥ 85%' },
  { metric: 'Triple-pass variance', target: '< 0.5 marks std-dev' },
  { metric: 'Time to evaluate one sheet', target: '< 30 seconds' },
]

const TEAM = ['P Charan Chandra', 'R T Kesav Reddy', 'Sai Charan M M', 'Nunna Uma Shankar']

/* ── Page ─────────────────────────────────────────────────────────────── */

export function Landing() {
  const { user } = useAuth()

  return (
    <div className="bg-background min-h-svh">
      <PublicHeader user={user} />

      {/* ── Hero ──────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border-b">
        <div
          aria-hidden
          // Tailwind v4 exposes palette colours as CSS variables; theme() in an
          // arbitrary value is v3 syntax and silently produces nothing here.
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_30rem_at_50%_-10%,var(--color-violet-200),transparent)] opacity-60 dark:opacity-20"
        />
        <div className="relative mx-auto max-w-5xl px-4 py-16 text-center sm:py-24">
          <Badge variant="secondary" className="mb-5">
            Major Project Phase 2 · CSE · 2025–26
          </Badge>

          <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl lg:text-6xl">
            Grading handwritten answer sheets the way an examiner reads them
          </h1>

          <p className="text-muted-foreground mx-auto mt-5 max-w-2xl text-lg text-pretty">
            Most automated graders flatten a scanned page into text and match keywords. This system
            reads the page — strike-throughs, underlines, arrows, margin notes and hand-drawn
            diagrams — then grades by <strong className="text-foreground">meaning</strong>, awards
            partial credit, and explains every mark it gives.
          </p>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            {user ? (
              <Button size="lg" asChild>
                <Link to={HOME_FOR_ROLE[user.role]}>
                  Go to your dashboard
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
            ) : (
              <>
                <Button size="lg" asChild>
                  <Link to="/signup">
                    <UserPlus className="size-4" />
                    Create an account
                  </Link>
                </Button>
                <Button size="lg" variant="outline" asChild>
                  <Link to="/login">
                    <LogIn className="size-4" />
                    Sign in
                  </Link>
                </Button>
              </>
            )}
          </div>

          <dl className="mx-auto mt-12 grid max-w-3xl grid-cols-2 gap-x-6 gap-y-6 sm:grid-cols-4">
            {[
              ['10', 'pipeline layers'],
              ['3', 'vision-model call sites'],
              ['3×', 'independent scoring passes'],
              ['< 30s', 'per sheet'],
            ].map(([value, label]) => (
              <div key={label}>
                <dt className="font-mono text-2xl font-semibold sm:text-3xl">{value}</dt>
                <dd className="text-muted-foreground mt-0.5 text-xs">{label}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ── Research gaps ─────────────────────────────────────────────── */}
      <Section
        eyebrow="The problem"
        title="Six things existing systems get wrong"
        lead="Each one is a documented gap in the literature, and each one has a specific answer in this design."
      >
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {GAPS.map(({ gap, answer }) => (
            <Card key={gap} className="h-full">
              <CardContent className="space-y-2">
                <p className="text-muted-foreground text-sm line-through decoration-red-500/60">
                  {gap}
                </p>
                <p className="flex gap-2 text-sm">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-green-600" />
                  <span>{answer}</span>
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </Section>

      {/* ── Pipeline ──────────────────────────────────────────────────── */}
      <Section
        eyebrow="How it works"
        title="Ten layers, from scanned pixels to an explained mark"
        lead="Every layer tries the cheap deterministic method first. The vision model is an escalation target, not a general-purpose page reader."
        muted
      >
        <div className="mx-auto max-w-3xl">
          <ol className="relative space-y-3 border-l pl-6">
            {LAYERS_CV.map((layer) => (
              <LayerRow key={layer.id} layer={layer} />
            ))}

            {/* The line that separates computer vision from retrieval. */}
            <li className="relative py-3">
              <span className="bg-background absolute top-1/2 -left-[1.6rem] size-3 -translate-y-1/2 rounded-full border-2 border-dashed" />
              <div className="flex items-center gap-3">
                <span className="text-muted-foreground shrink-0 font-mono text-[11px] tracking-widest uppercase">
                  RAG boundary
                </span>
                <span className="h-px flex-1 border-t border-dashed" />
              </div>
              <p className="text-muted-foreground mt-1.5 text-xs">
                Above this line the system is reading the page. Below it, the reconstructed text is
                graded against the teacher's stored concepts.
              </p>
            </li>

            {LAYERS_RAG.map((layer) => (
              <LayerRow key={layer.id} layer={layer} />
            ))}
          </ol>
        </div>
      </Section>

      {/* ── VLM escalation ────────────────────────────────────────────── */}
      <Section
        eyebrow="Adaptive vision"
        title="Where the vision model actually fires"
        lead="Three call sites, one principle: escalate only when the cheap method reports low confidence. Every invocation is recorded on the row it affected, so the system can state exactly how often it was needed."
      >
        <div className="grid gap-4 lg:grid-cols-3">
          {VLM_SITES.map(({ layer, cheap, fires, asks }) => (
            <Card key={layer} className="h-full border-violet-300/60 dark:border-violet-900">
              <CardContent className="space-y-3">
                <div className="flex items-center gap-2">
                  <Badge className="bg-violet-600 font-mono hover:bg-violet-600">{layer}</Badge>
                  <Sparkles className="size-4 text-violet-500" />
                </div>
                <div className="space-y-1.5 text-sm">
                  <p>
                    <span className="text-muted-foreground">Tries first — </span>
                    {cheap}
                  </p>
                  <p>
                    <span className="text-muted-foreground">Escalates when — </span>
                    <span className="font-medium">{fires}</span>
                  </p>
                </div>
                <p className="text-muted-foreground border-l-2 border-violet-400 pl-3 text-sm italic">
                  “{asks}”
                </p>
              </CardContent>
            </Card>
          ))}
        </div>

        <p className="text-muted-foreground mx-auto mt-6 max-w-3xl text-center text-sm">
          Geometry can measure a line's angle and position, but it cannot see that the line passes
          through the <em>middle</em> of a word. A ruled margin line, a table border, an underline and
          a strike-through are geometrically similar and semantically opposite — so the clear cases go
          to geometry and the ambiguous ones go to the vision model.
        </p>
      </Section>

      {/* ── RAG ───────────────────────────────────────────────────────── */}
      <Section
        eyebrow="Retrieval-augmented grading"
        title="The teacher's model answer becomes the marking scheme"
        lead="Concepts are extracted and embedded once per question. Every student answer is then retrieved against that store, and only the retrieved evidence reaches the grading prompt."
        muted
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardContent className="space-y-3">
              <p className="flex items-center gap-2 font-medium">
                <Database className="size-4" />
                Index time — once per question
              </p>
              <ol className="text-muted-foreground list-inside list-decimal space-y-1.5 text-sm">
                <li>The model answer is split into 5–8 concepts with weights summing to 1.00.</li>
                <li>Each concept is embedded and stored in pgvector, namespaced by exam and question.</li>
                <li>Cached permanently — re-run only when the teacher edits the model answer.</li>
              </ol>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3">
              <p className="flex items-center gap-2 font-medium">
                <FileSearch className="size-4" />
                Query time — once per student answer
              </p>
              <ol className="text-muted-foreground list-inside list-decimal space-y-1.5 text-sm">
                <li>The reconstructed answer is chunked into sentences and embedded in one batch.</li>
                <li>Each concept retrieves its top-3 closest chunks by cosine similarity.</li>
                <li>Only those chunks enter the coverage prompt — never the full answer.</li>
              </ol>
            </CardContent>
          </Card>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          {[
            ['Grounding', 'The model judges against retrieved evidence, which cuts hallucinated coverage claims.'],
            ['Verification', 'Cosine similarity is an independent numeric check — a “covered” verdict with similarity under 0.45 is downgraded automatically.'],
            ['Token economy', 'Prompts stay small and constant-size no matter how long the answer is.'],
          ].map(([title, body]) => (
            <div key={title} className="rounded-lg border p-4">
              <p className="text-sm font-medium">{title}</p>
              <p className="text-muted-foreground mt-1 text-sm">{body}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Confidence ────────────────────────────────────────────────── */}
      <Section
        eyebrow="Human in the loop"
        title="The system says how sure it is, and nothing publishes itself"
        lead="Confidence combines OCR quality, agreement between the three passes, and how well retrieval verified each verdict. It decides how much attention a sheet needs — a teacher always approves before a student sees anything."
      >
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            { band: '≥ 0.80', dot: 'bg-green-600', label: 'High confidence', body: 'Ready to approve after a quick look.' },
            { band: '0.65 – 0.80', dot: 'bg-amber-500', label: 'Needs a look', body: 'Publishable, but worth reading the flagged concepts.' },
            { band: '< 0.65', dot: 'bg-red-600', label: 'Review required', body: 'Sorted to the top of the queue — the queue is the triage.' },
          ].map(({ band, dot, label, body }) => (
            <Card key={band}>
              <CardContent className="space-y-1.5">
                <p className="flex items-center gap-2 text-sm font-medium">
                  <span className={cn('size-2.5 rounded-full', dot)} aria-hidden />
                  {label}
                </p>
                <p className="font-mono text-2xl font-semibold">{band}</p>
                <p className="text-muted-foreground text-sm">{body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </Section>

      {/* ── Roles ─────────────────────────────────────────────────────── */}
      <Section eyebrow="Who does what" title="Two roles, one loop" muted>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardContent>
              <p className="flex items-center gap-2 font-medium">
                <PenLine className="size-4" />
                Teacher
              </p>
              <ol className="mt-3 space-y-2.5">
                {TEACHER_STEPS.map((step, i) => (
                  <li key={step} className="flex gap-3 text-sm">
                    <span className="bg-secondary text-secondary-foreground flex size-5 shrink-0 items-center justify-center rounded-full font-mono text-[11px]">
                      {i + 1}
                    </span>
                    <span className="text-muted-foreground">{step}</span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <p className="flex items-center gap-2 font-medium">
                <GraduationCap className="size-4" />
                Student
              </p>
              <ol className="mt-3 space-y-2.5">
                {STUDENT_STEPS.map((step, i) => (
                  <li key={step} className="flex gap-3 text-sm">
                    <span className="bg-secondary text-secondary-foreground flex size-5 shrink-0 items-center justify-center rounded-full font-mono text-[11px]">
                      {i + 1}
                    </span>
                    <span className="text-muted-foreground">{step}</span>
                  </li>
                ))}
              </ol>
              <p className="text-muted-foreground mt-4 border-t pt-3 text-xs">
                Students never see another student's sheet, an unapproved result, the raw scans, or the
                retrieved evidence quotes.
              </p>
            </CardContent>
          </Card>
        </div>
      </Section>

      {/* ── Stack + targets ───────────────────────────────────────────── */}
      <Section eyebrow="Under the hood" title="Built on">
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-4">
            {STACK.map(({ group, items }) => (
              <div key={group} className="flex flex-wrap items-center gap-2">
                <span className="text-muted-foreground w-20 shrink-0 text-xs">{group}</span>
                {items.map((item) => (
                  <Badge key={item} variant="outline" className="font-mono text-xs">
                    {item}
                  </Badge>
                ))}
              </div>
            ))}
            <p className="text-muted-foreground flex gap-2 pt-2 text-xs">
              <Braces className="mt-0.5 size-3.5 shrink-0" />
              Language, vision and embedding models are all reached through one provider interface, so
              the whole pipeline can be run offline against deterministic mocks.
            </p>
          </div>

          <div>
            <p className="mb-3 flex items-center gap-2 text-sm font-medium">
              <Target className="size-4" />
              Targets we measure against
            </p>
            <dl className="divide-y rounded-lg border">
              {TARGETS.map(({ metric, target }) => (
                <div key={metric} className="flex items-center justify-between gap-4 px-4 py-2.5">
                  <dt className="text-muted-foreground text-sm">{metric}</dt>
                  <dd className="shrink-0 font-mono text-sm font-medium">{target}</dd>
                </div>
              ))}
            </dl>
            <p className="text-muted-foreground mt-2 text-xs">
              Measured numbers are reported as measured, including any that miss target.
            </p>
          </div>
        </div>
      </Section>

      {/* ── CTA ───────────────────────────────────────────────────────── */}
      {!user && (
        <section className="border-y bg-violet-50/60 dark:bg-violet-950/20">
          <div className="mx-auto max-w-3xl px-4 py-14 text-center">
            <h2 className="text-2xl font-semibold">Get started</h2>
            <p className="text-muted-foreground mx-auto mt-2 max-w-lg">
              Create a teacher account to set up an exam and evaluate a sheet, or a student account to
              view published results.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Button size="lg" asChild>
                <Link to="/signup">
                  <UserPlus className="size-4" />
                  Create an account
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link to="/login">
                  <LogIn className="size-4" />
                  Sign in
                </Link>
              </Button>
            </div>
          </div>
        </section>
      )}

      {/* ── Footer ────────────────────────────────────────────────────── */}
      <footer className="mx-auto max-w-6xl px-4 py-10">
        <div className="flex flex-wrap justify-between gap-6">
          <div>
            <p className="flex items-center gap-2 font-semibold">
              <ScanLine className="size-4" />
              AI-Driven Answer Sheet Evaluation
            </p>
            <p className="text-muted-foreground mt-1 text-sm">
              BMS Institute of Technology &amp; Management
              <br />
              Department of Computer Science &amp; Engineering · 2025–26
            </p>
          </div>

          <div className="text-sm">
            <p className="text-muted-foreground mb-1 text-xs">Project team</p>
            <ul className="space-y-0.5">
              {TEAM.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          </div>

          <div className="text-sm">
            <p className="text-muted-foreground mb-1 text-xs">Guide</p>
            <p>Dr. Gireesh Babu C N</p>
          </div>
        </div>
      </footer>
    </div>
  )
}

/* ── Building blocks ──────────────────────────────────────────────────── */

function PublicHeader({ user }: { user: ReturnType<typeof useAuth>['user'] }) {
  return (
    <header className="bg-background/95 supports-[backdrop-filter]:bg-background/70 sticky top-0 z-40 border-b backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
        <Link to="/" className="flex items-center gap-2 font-semibold">
          <ScanLine className="size-5" />
          <span className="hidden sm:inline">Answer Sheet Evaluation</span>
          <span className="sm:hidden">AES</span>
        </Link>

        <nav className="text-muted-foreground ml-4 hidden items-center gap-4 text-sm md:flex">
          <a href="#how-it-works" className="hover:text-foreground transition-colors">
            How it works
          </a>
          <a href="#adaptive-vision" className="hover:text-foreground transition-colors">
            Adaptive vision
          </a>
          <a href="#retrieval-augmented-grading" className="hover:text-foreground transition-colors">
            Grading
          </a>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          {user ? (
            <Button size="sm" asChild>
              <Link to={HOME_FOR_ROLE[user.role]}>
                Dashboard
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          ) : (
            <>
              <Button size="sm" variant="ghost" asChild>
                <Link to="/login">Sign in</Link>
              </Button>
              <Button size="sm" asChild>
                <Link to="/signup">Create account</Link>
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  )
}

/** Section ids are derived from the eyebrow so the header anchors stay in sync. */
function Section({
  eyebrow,
  title,
  lead,
  muted,
  children,
}: {
  eyebrow: string
  title: string
  lead?: string
  muted?: boolean
  children: React.ReactNode
}) {
  const id = eyebrow.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  return (
    <section id={id} className={cn('scroll-mt-16 border-b', muted && 'bg-muted/30')}>
      <div className="mx-auto max-w-6xl px-4 py-14 sm:py-16">
        <p className="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs font-medium tracking-widest uppercase">
          <Boxes className="size-3.5" />
          {eyebrow}
        </p>
        <h2 className="max-w-3xl text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
          {title}
        </h2>
        {lead && <p className="text-muted-foreground mt-3 max-w-3xl text-pretty">{lead}</p>}
        <div className="mt-8">{children}</div>
      </div>
    </section>
  )
}

function LayerRow({ layer }: { layer: Layer }) {
  return (
    <li className="relative">
      <span
        className={cn(
          'absolute top-1.5 -left-[1.72rem] size-3 rounded-full border-2',
          layer.vlm ? 'border-violet-500 bg-violet-500' : 'bg-background border-foreground/40',
        )}
        aria-hidden
      />
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground font-mono text-xs">{layer.id}</span>
        <span className="font-medium">{layer.title}</span>
        {layer.vlm && (
          <Badge
            variant="outline"
            className="gap-1 border-violet-400 text-[10px] text-violet-600 dark:text-violet-400"
          >
            <Eye className="size-2.5" />
            vision model
          </Badge>
        )}
      </div>
      <p className="text-muted-foreground mt-0.5 text-sm">{layer.detail}</p>
    </li>
  )
}
