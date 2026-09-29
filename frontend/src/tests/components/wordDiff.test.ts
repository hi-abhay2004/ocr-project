import { describe, expect, it } from 'vitest'
import { wordDiff } from '@/lib/wordDiff'

describe('wordDiff', () => {
  it('marks words dropped by L5 as removed', () => {
    const tokens = wordDiff('for every non-trivial functional dependency', 'for every functional dependency')
    expect(tokens.find((t) => t.op === 'removed')?.text).toBe('non-trivial')
  })

  it('marks words stitched in from the margin as added', () => {
    const tokens = wordDiff('removes redundancy caused by', 'removes redundancy and update anomalies caused by')
    expect(tokens.find((t) => t.op === 'added')?.text).toBe('and update anomalies')
  })

  it('reports no changes when reconstruction was a no-op', () => {
    const text = 'BCNF is stricter than 3NF'
    const tokens = wordDiff(text, text)
    expect(tokens.every((t) => t.op === 'same')).toBe(true)
  })

  it('ignores punctuation and case when matching', () => {
    const tokens = wordDiff('X is a Superkey.', 'X is a superkey')
    expect(tokens.every((t) => t.op === 'same')).toBe(true)
  })

  it('handles an empty side', () => {
    expect(wordDiff('', 'all new text').every((t) => t.op === 'added')).toBe(true)
    expect(wordDiff('all gone', '').every((t) => t.op === 'removed')).toBe(true)
  })
})
