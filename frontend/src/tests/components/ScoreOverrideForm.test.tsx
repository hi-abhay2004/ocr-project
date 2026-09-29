import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ScoreOverrideForm } from '@/components/ScoreOverrideForm'
import { renderPlain } from '../utils'

function setup(overrides: Partial<Parameters<typeof ScoreOverrideForm>[0]> = {}) {
  const onSave = vi.fn()
  const onClear = vi.fn()
  renderPlain(
    <ScoreOverrideForm
      evaluationId={1}
      autoMarks={6.5}
      currentOverride={null}
      currentComment={null}
      maxMarks={10}
      onSave={onSave}
      onClear={onClear}
      {...overrides}
    />,
  )
  return { onSave, onClear }
}

describe('ScoreOverrideForm', () => {
  it('pre-fills with the machine mark when there is no override', () => {
    setup()
    expect(screen.getByLabelText(/final marks/i)).toHaveValue(6.5)
  })

  it('rejects a negative mark', async () => {
    const user = userEvent.setup()
    const { onSave } = setup()

    const input = screen.getByLabelText(/final marks/i)
    await user.clear(input)
    await user.type(input, '-3')
    await user.click(screen.getByRole('button', { name: /save override/i }))

    expect(await screen.findByText(/cannot be negative/i)).toBeInTheDocument()
    expect(onSave).not.toHaveBeenCalled()
  })

  it('rejects a mark above the question maximum', async () => {
    const user = userEvent.setup()
    const { onSave } = setup()

    const input = screen.getByLabelText(/final marks/i)
    await user.clear(input)
    await user.type(input, '11')
    await user.click(screen.getByRole('button', { name: /save override/i }))

    expect(await screen.findByText(/cannot exceed 10/i)).toBeInTheDocument()
    expect(onSave).not.toHaveBeenCalled()
  })

  it('submits a valid override with its comment', async () => {
    const user = userEvent.setup()
    const { onSave } = setup()

    const input = screen.getByLabelText(/final marks/i)
    await user.clear(input)
    await user.type(input, '8')
    await user.type(screen.getByLabelText(/comment/i), 'Diagram was correct')
    await user.click(screen.getByRole('button', { name: /save override/i }))

    expect(onSave).toHaveBeenCalledWith({
      override_marks: 8,
      override_comment: 'Diagram was correct',
    })
  })

  it('offers a reset only when an override exists', async () => {
    const user = userEvent.setup()
    const { onClear } = setup({ currentOverride: 8, currentComment: 'bumped' })

    const reset = screen.getByRole('button', { name: /reset to 6.5/i })
    await user.click(reset)
    expect(onClear).toHaveBeenCalled()
  })

  it('hides the reset button when the mark is untouched', () => {
    setup()
    expect(screen.queryByRole('button', { name: /reset to/i })).toBeNull()
  })
})
