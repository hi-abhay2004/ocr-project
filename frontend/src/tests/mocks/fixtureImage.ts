import type { Annotation, BBox } from '@/types/api'

/**
 * Generates a synthetic "scanned answer crop" AND the annotation boxes that sit
 * on it — from the same layout constants.
 *
 * This matters more than it looks. The single most likely defect in the overlay
 * is a coordinate-space mismatch (§12): boxes drawn at the wrong scale, or
 * offset by a margin. If the fixture image and the fixture bboxes were written
 * by hand as two separate blobs, a wrong box would look like a wrong fixture and
 * the real bug would hide. Deriving both from one `LINES` array means any
 * misalignment you see on screen is a bug in AnnotationOverlay, full stop.
 *
 * Replace with real crops from the Django /media/ endpoint once Phase 4 lands.
 */

const CHAR_W = 19
const FONT_SIZE = 30
const LINE_H = 78
const MARGIN_X = 56
const BASE_Y = 96

export const CROP_W = 1240
export const CROP_H = 480

type Mark = 'strike' | 'underline'
interface Word {
  t: string
  mark?: Mark
}

/** Line 2 "non-trivial" is struck; line 3 "superkey" is underlined. */
const LINES: Word[][] = [
  [{ t: 'BCNF is a normal form used in database design.' }],
  [
    { t: 'A relation R is in BCNF if for every' },
    { t: 'non-trivial', mark: 'strike' },
    { t: 'functional' },
  ],
  [{ t: 'dependency X -> Y, X must be a' }, { t: 'superkey', mark: 'underline' }, { t: 'of R.' }],
  [{ t: 'It is stricter than 3NF and removes redundancy' }],
  [{ t: 'caused by transitive dependencies.' }],
]

interface Placed {
  word: Word
  x: number
  y: number // baseline
  w: number
}

function layout(): Placed[] {
  const placed: Placed[] = []
  LINES.forEach((line, i) => {
    let x = MARGIN_X
    const y = BASE_Y + i * LINE_H
    for (const word of line) {
      const w = word.t.length * CHAR_W
      placed.push({ word, x, y, w })
      x += w + CHAR_W // one space
    }
  })
  return placed
}

/** Glyph box of a word: the box a teacher expects to see drawn around it. */
function wordBox(p: Placed): BBox {
  return { x: p.x - 4, y: p.y - FONT_SIZE + 2, w: p.w + 8, h: FONT_SIZE + 6 }
}

const PLACED = layout()
const marked = (m: Mark) => PLACED.find((p) => p.word.mark === m)!

const strikeWord = marked('strike')
const underlineWord = marked('underline')

/* The margin insertion: a caret on line 4 with an arrow out to a right-margin note.
   x=940 places it just past the end of line 4 (56 + 45 chars × 19 = 911), where a
   student would actually write one — not on top of the last word. */
const CARET = { x: 940, y: BASE_Y + 3 * LINE_H }
const MARGIN_NOTE = { x: 960, y: 452, w: 240, h: 34 }

export const FIXTURE_ANNOTATIONS: Annotation[] = [
  {
    id: 1,
    kind: 'STRIKE',
    intent: 'CORRECTION',
    bbox: wordBox(strikeWord),
    confidence: 0.93,
    resolved_by: 'CV',
  },
  {
    id: 2,
    kind: 'UNDERLINE',
    intent: 'EMPHASIS',
    bbox: wordBox(underlineWord),
    // Below the 0.70 L3.5 threshold — this is the one that escalated to the VLM
    // and therefore renders dashed. It is the visual proof of adaptive routing.
    confidence: 0.58,
    resolved_by: 'VLM',
  },
  {
    id: 3,
    kind: 'ARROW',
    intent: 'INSERTION',
    bbox: { x: CARET.x - 10, y: CARET.y - 34, w: 96, h: 74 },
    confidence: 0.81,
    resolved_by: 'CV',
  },
  {
    id: 4,
    kind: 'MARGIN',
    intent: 'INSERTION',
    bbox: { x: MARGIN_NOTE.x - 8, y: MARGIN_NOTE.y - 26, w: MARGIN_NOTE.w + 16, h: MARGIN_NOTE.h },
    confidence: 0.67,
    resolved_by: 'VLM',
  },
]

function esc(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function buildSvg(): string {
  const rules = Array.from({ length: 5 }, (_, i) => {
    const y = BASE_Y + i * LINE_H + 12
    return `<line x1="30" y1="${y}" x2="${CROP_W - 30}" y2="${y}" stroke="#dfe7f0" stroke-width="1.5"/>`
  }).join('')

  const words = PLACED.map(({ word, x, y, w }) => {
    // textLength + lengthAdjust forces an exact pixel width regardless of which
    // font the machine actually has — so the bboxes above stay correct everywhere.
    const t = `<text x="${x}" y="${y}" textLength="${w}" lengthAdjust="spacingAndGlyphs" font-family="'Segoe Script','Bradley Hand',cursive,sans-serif" font-size="${FONT_SIZE}" fill="#1b3a6b">${esc(word.t)}</text>`
    if (word.mark === 'strike') {
      const sy = y - FONT_SIZE * 0.3
      return `${t}<line x1="${x - 2}" y1="${sy + 2}" x2="${x + w + 2}" y2="${sy - 2}" stroke="#c0392b" stroke-width="3.5" stroke-linecap="round"/>`
    }
    if (word.mark === 'underline') {
      return `${t}<path d="M ${x} ${y + 9} Q ${x + w / 2} ${y + 14}, ${x + w} ${y + 8}" stroke="#1b3a6b" stroke-width="3" fill="none" stroke-linecap="round"/>`
    }
    return t
  }).join('')

  const arrow =
    `<path d="M ${CARET.x} ${CARET.y + 6} l 14 -20 l 14 20" stroke="#1b3a6b" stroke-width="3" fill="none" stroke-linejoin="round"/>` +
    `<path d="M ${CARET.x + 20} ${CARET.y + 12} C ${CARET.x + 60} ${CARET.y + 40}, ${MARGIN_NOTE.x - 40} ${MARGIN_NOTE.y - 50}, ${MARGIN_NOTE.x - 6} ${MARGIN_NOTE.y - 14}" stroke="#1b3a6b" stroke-width="2.5" fill="none"/>` +
    `<path d="M ${MARGIN_NOTE.x - 6} ${MARGIN_NOTE.y - 14} l -14 -3 m 14 3 l -4 -13" stroke="#1b3a6b" stroke-width="2.5" fill="none" stroke-linecap="round"/>`

  const note = `<text x="${MARGIN_NOTE.x}" y="${MARGIN_NOTE.y}" textLength="${MARGIN_NOTE.w}" lengthAdjust="spacingAndGlyphs" font-family="'Segoe Script','Bradley Hand',cursive,sans-serif" font-size="26" fill="#1b3a6b">and update anomalies</text>`

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${CROP_W}" height="${CROP_H}" viewBox="0 0 ${CROP_W} ${CROP_H}">
<rect width="${CROP_W}" height="${CROP_H}" fill="#fbfaf4"/>
<rect width="${CROP_W}" height="${CROP_H}" fill="none" stroke="#e6e2d6" stroke-width="2"/>
${rules}${words}${arrow}${note}
</svg>`
}

/** Inline data URL — no server, no /media/, works in <img src> and in jsdom. */
export const FIXTURE_CROP_URL = `data:image/svg+xml;utf8,${encodeURIComponent(buildSvg())}`

/* ── A non-text block, to exercise the L4.5 specialized-content path ─────── */

function buildDiagramSvg(): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="520" viewBox="0 0 900 520">
<rect width="900" height="520" fill="#fbfaf4"/>
<rect width="900" height="520" fill="none" stroke="#e6e2d6" stroke-width="2"/>
<g stroke="#1b3a6b" stroke-width="3" fill="none" font-family="'Segoe Script',cursive" font-size="24">
<rect x="70" y="90" width="220" height="90" rx="6"/>
<text x="120" y="145" stroke="none" fill="#1b3a6b">STUDENT</text>
<path d="M 290 135 l 70 -35 l 70 35 l -70 35 z"/>
<text x="330" y="143" stroke="none" fill="#1b3a6b" font-size="18">enrols</text>
<rect x="500" y="90" width="220" height="90" rx="6"/>
<text x="555" y="145" stroke="none" fill="#1b3a6b">COURSE</text>
<line x1="180" y1="180" x2="180" y2="300"/>
<ellipse cx="180" cy="340" rx="105" ry="42"/>
<text x="130" y="348" stroke="none" fill="#1b3a6b" font-size="20">usn</text>
<line x1="610" y1="180" x2="610" y2="300"/>
<ellipse cx="610" cy="340" rx="105" ry="42"/>
<text x="545" y="348" stroke="none" fill="#1b3a6b" font-size="20">code</text>
<text x="300" y="90" stroke="none" fill="#1b3a6b" font-size="20">M</text>
<text x="455" y="90" stroke="none" fill="#1b3a6b" font-size="20">N</text>
</g>
</svg>`
}

export const FIXTURE_DIAGRAM_URL = `data:image/svg+xml;utf8,${encodeURIComponent(buildDiagramSvg())}`
export const DIAGRAM_W = 900
export const DIAGRAM_H = 520
