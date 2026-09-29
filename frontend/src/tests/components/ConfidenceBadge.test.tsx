import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ConfidenceBadge, bandFor } from '@/components/ConfidenceBadge'
import { renderPlain } from '../utils'

describe('bandFor', () => {
  it('maps scores to bands', () => {
    expect(bandFor(0.95)).toBe('GREEN')
    expect(bandFor(0.72)).toBe('ORANGE')
    expect(bandFor(0.51)).toBe('RED')
  })

  it('treats the thresholds as INCLUSIVE lower bounds', () => {
    // The spec says "≥ .80 green, ≥ .65 orange". Written as ">" instead of "≥"
    // these two cases silently move into the next band down, which pushes
    // borderline sheets into the review queue for no reason.
    expect(bandFor(0.8)).toBe('GREEN')
    expect(bandFor(0.65)).toBe('ORANGE')

    // And just below each boundary must fall through.
    expect(bandFor(0.7999)).toBe('ORANGE')
    expect(bandFor(0.6499)).toBe('RED')
  })
})

describe('ConfidenceBadge', () => {
  it.each([
    [0.81, 'GREEN'],
    [0.72, 'ORANGE'],
    [0.51, 'RED'],
  ])('renders %s as the %s band', (score, band) => {
    renderPlain(<ConfidenceBadge score={score} />)
    expect(screen.getByTestId('confidence-badge')).toHaveAttribute('data-band', band)
  })

  it('shows the score as a whole percentage', () => {
    renderPlain(<ConfidenceBadge score={0.784} />)
    expect(screen.getByText('78%')).toBeInTheDocument()
  })
})
