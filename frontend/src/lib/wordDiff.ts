export type DiffOp = 'same' | 'removed' | 'added'
export interface DiffToken {
  op: DiffOp
  text: string
}

/**
 * Word-level LCS diff between the raw OCR output and the reconstructed text.
 *
 * This is what makes L5 visible. The pipeline claims it "drops struck text and
 * stitches in margin notes"; diffing the two strings shows exactly which words
 * that removed and which it inserted. It is the strongest available answer to
 * "how do you know the machine read the answer correctly?" — the teacher can
 * see the transformation rather than trust it.
 *
 * O(n·m); answer blocks are a few hundred words, so this is not worth optimising.
 */
export function wordDiff(before: string, after: string): DiffToken[] {
  const a = before.split(/\s+/).filter(Boolean)
  const b = after.split(/\s+/).filter(Boolean)

  const norm = (s: string) => s.toLowerCase().replace(/[.,;:!?()"']/g, '')

  // lcs[i][j] = length of the longest common subsequence of a[i:] and b[j:]
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] =
        norm(a[i]) === norm(b[j]) ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }

  const out: DiffToken[] = []
  const push = (op: DiffOp, text: string) => {
    const last = out[out.length - 1]
    if (last && last.op === op) last.text += ` ${text}`
    else out.push({ op, text })
  }

  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (norm(a[i]) === norm(b[j])) {
      push('same', b[j])
      i++
      j++
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      push('removed', a[i])
      i++
    } else {
      push('added', b[j])
      j++
    }
  }
  while (i < a.length) push('removed', a[i++])
  while (j < b.length) push('added', b[j++])

  return out
}
