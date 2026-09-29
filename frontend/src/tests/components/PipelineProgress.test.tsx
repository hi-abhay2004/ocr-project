import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PipelineProgress } from '@/components/PipelineProgress'
import { renderPlain } from '../utils'
import { STAGES } from '@/types/api'

describe('PipelineProgress', () => {
  it('renders all 12 pipeline stages', () => {
    // The count is asserted deliberately: §3.4 found the API enum still listing
    // the pre-L3.5/L4.5 set of 8. If a stage is added to STAGES and the backend
    // does not send it, this is where the mismatch surfaces.
    renderPlain(<PipelineProgress stage="ocr" status="RUNNING" startedAt={new Date().toISOString()} />)
    for (const stage of STAGES) {
      expect(screen.getByTestId(`stage-${stage}`)).toBeInTheDocument()
    }
    expect(STAGES).toHaveLength(13) // 12 working stages + the terminal "done"
  })

  it('marks the current stage, completes the earlier ones, leaves later ones pending', () => {
    renderPlain(
      <PipelineProgress stage="adjudication" status="RUNNING" startedAt={new Date().toISOString()} />,
    )
    expect(screen.getByTestId('stage-segmentation')).toHaveAttribute('data-state', 'done')
    expect(screen.getByTestId('stage-adjudication')).toHaveAttribute('data-state', 'current')
    expect(screen.getByTestId('stage-scoring')).toHaveAttribute('data-state', 'pending')
  })

  it('shows every stage complete once the sheet is DONE', () => {
    renderPlain(<PipelineProgress stage="done" status="DONE" startedAt={new Date().toISOString()} />)
    expect(screen.getByText(/evaluation complete/i)).toBeInTheDocument()
    for (const stage of STAGES) {
      expect(screen.getByTestId(`stage-${stage}`)).toHaveAttribute('data-state', 'done')
    }
  })

  it('surfaces the error message on failure', () => {
    renderPlain(
      <PipelineProgress
        stage="ocr"
        status="FAILED"
        startedAt={new Date().toISOString()}
        errorMessage="OCR returned no text for page 2"
      />,
    )
    expect(screen.getByText(/evaluation failed/i)).toBeInTheDocument()
    expect(screen.getByText(/ocr returned no text for page 2/i)).toBeInTheDocument()
  })

  it('freezes the elapsed timer once the status is terminal', () => {
    const startedAt = new Date(Date.now() - 95_000).toISOString()
    renderPlain(<PipelineProgress stage="done" status="DONE" startedAt={startedAt} />)
    // 95s → 1:35, and no interval is registered because running === false.
    expect(screen.getByTestId('elapsed')).toHaveTextContent('1:35')
  })
})
