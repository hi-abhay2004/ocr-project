import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ConceptBar } from '@/components/ConceptBar'
import { ConceptBarList } from '@/components/ConceptBarList'
import { renderPlain } from '../utils'
import type { ConceptScore } from '@/types/api'

const base: ConceptScore = {
  id: 1,
  concept_id: 1,
  concept_text: 'Every determinant X must be a superkey of R',
  status: 'COVERED',
  similarity: 0.87,
  marks: 3,
  max_marks: 3,
  evidence: 'X must be a superkey of R.',
  disagreed: false,
}

describe('ConceptBar', () => {
  it.each(['COVERED', 'PARTIAL', 'MISSING'] as const)('exposes the %s status', (status) => {
    renderPlain(<ConceptBar score={{ ...base, status }} />)
    expect(screen.getByTestId('concept-bar')).toHaveAttribute('data-status', status)
  })

  it('sets bar width from similarity, not from marks', () => {
    // Deliberate: the bar visualises how close the retrieved evidence was, which
    // is what the status was decided from. Marks are shown as a number instead.
    renderPlain(<ConceptBar score={{ ...base, similarity: 0.42, marks: 3, max_marks: 3 }} />)
    expect(screen.getByTestId('concept-bar-fill')).toHaveStyle({ width: '42%' })
  })

  it('flags triple-pass disagreement', () => {
    renderPlain(<ConceptBar score={{ ...base, disagreed: true }} />)
    expect(screen.getByTestId('disagreed-icon')).toBeInTheDocument()
  })

  it('hides the disagreement flag when the passes agreed', () => {
    renderPlain(<ConceptBar score={base} />)
    expect(screen.queryByTestId('disagreed-icon')).toBeNull()
  })

  it('shows evidence only when asked', () => {
    const { unmount } = renderPlain(<ConceptBar score={base} showEvidence />)
    expect(screen.getByText(/X must be a superkey of R\./)).toBeInTheDocument()
    unmount()

    // Students must never receive the retrieved chunk (§8 screen 12).
    renderPlain(<ConceptBar score={base} />)
    expect(screen.queryByText(/X must be a superkey of R\./)).toBeNull()
  })
})

describe('ConceptBarList', () => {
  it('sorts worst first', () => {
    const scores: ConceptScore[] = [
      { ...base, id: 1, concept_text: 'covered one', status: 'COVERED' },
      { ...base, id: 2, concept_text: 'missing one', status: 'MISSING' },
      { ...base, id: 3, concept_text: 'partial one', status: 'PARTIAL' },
    ]
    renderPlain(<ConceptBarList scores={scores} />)

    const rendered = screen.getAllByTestId('concept-bar').map((el) => el.getAttribute('data-status'))
    expect(rendered).toEqual(['MISSING', 'PARTIAL', 'COVERED'])
  })

  it('summarises coverage', () => {
    const scores: ConceptScore[] = [
      { ...base, id: 1, status: 'COVERED' },
      { ...base, id: 2, status: 'MISSING', marks: 0 },
    ]
    renderPlain(<ConceptBarList scores={scores} />)
    expect(screen.getByText('1 of 2 concepts covered')).toBeInTheDocument()
  })
})
