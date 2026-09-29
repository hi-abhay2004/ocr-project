import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { AnnotationOverlay } from '@/components/AnnotationOverlay'
import { renderPlain } from '../utils'
import {
  CROP_H,
  CROP_W,
  FIXTURE_ANNOTATIONS,
  FIXTURE_CROP_URL,
} from '../mocks/fixtureImage'
import type { Block } from '@/types/api'

const block: Block = {
  id: 1,
  question_id: 1,
  crop_image_url: FIXTURE_CROP_URL,
  image_width: CROP_W,
  image_height: CROP_H,
  quality_score: 0.71,
  content_type: 'TEXT',
  ocr_engine: 'TESSERACT_6',
  raw_text: 'raw',
  reconstructed_text: 'reconstructed',
  annotations: FIXTURE_ANNOTATIONS,
}

describe('AnnotationOverlay', () => {
  it('renders one rect per annotation', () => {
    renderPlain(<AnnotationOverlay block={block} />)
    expect(screen.getAllByTestId('annotation-rect')).toHaveLength(FIXTURE_ANNOTATIONS.length)
  })

  it('sets the viewBox to the crop\'s NATURAL dimensions', () => {
    // This single attribute is what makes the boxes land correctly at every
    // screen width without any JS scale maths (§7). If it ever gets computed
    // from the rendered size instead, every box drifts.
    renderPlain(<AnnotationOverlay block={block} />)
    expect(screen.getByTestId('annotation-svg')).toHaveAttribute(
      'viewBox',
      `0 0 ${CROP_W} ${CROP_H}`,
    )
  })

  it('uses raw bbox pixel values as SVG coordinates — no arithmetic', () => {
    renderPlain(<AnnotationOverlay block={block} />)
    const strike = FIXTURE_ANNOTATIONS.find((a) => a.kind === 'STRIKE')!
    const rect = screen
      .getAllByTestId('annotation-rect')
      .find((r) => r.getAttribute('data-kind') === 'STRIKE')!

    expect(rect).toHaveAttribute('x', String(strike.bbox.x))
    expect(rect).toHaveAttribute('y', String(strike.bbox.y))
    expect(rect).toHaveAttribute('width', String(strike.bbox.w))
    expect(rect).toHaveAttribute('height', String(strike.bbox.h))
  })

  it('draws VLM-adjudicated annotations dashed and CV ones solid', () => {
    // The dashed border is the visual proof of CV → VLM escalation. It is the
    // one mark on screen that makes "adaptive VLM sensitivity" demonstrable.
    renderPlain(<AnnotationOverlay block={block} />)
    const rects = screen.getAllByTestId('annotation-rect')

    for (const rect of rects) {
      const dashed = rect.getAttribute('stroke-dasharray')
      if (rect.getAttribute('data-resolved-by') === 'VLM') expect(dashed).toBeTruthy()
      else expect(dashed).toBeNull()
    }

    expect(rects.filter((r) => r.getAttribute('data-resolved-by') === 'VLM').length).toBeGreaterThan(0)
    expect(rects.filter((r) => r.getAttribute('data-resolved-by') === 'CV').length).toBeGreaterThan(0)
  })

  it('toggling a layer removes only that kind', async () => {
    const user = userEvent.setup()
    renderPlain(<AnnotationOverlay block={block} />)

    const before = screen.getAllByTestId('annotation-rect').length
    const strikeCount = FIXTURE_ANNOTATIONS.filter((a) => a.kind === 'STRIKE').length

    await user.click(screen.getByLabelText(/show struck out annotations/i))

    const after = screen.getAllByTestId('annotation-rect')
    expect(after).toHaveLength(before - strikeCount)
    expect(after.some((r) => r.getAttribute('data-kind') === 'STRIKE')).toBe(false)
    // The other kinds are untouched.
    expect(after.some((r) => r.getAttribute('data-kind') === 'UNDERLINE')).toBe(true)
  })

  it('shows a "decided by VLM" tooltip on hover for escalated annotations', async () => {
    const user = userEvent.setup()
    renderPlain(<AnnotationOverlay block={block} />)

    const vlmRect = screen
      .getAllByTestId('annotation-rect')
      .find((r) => r.getAttribute('data-resolved-by') === 'VLM')!

    await user.hover(vlmRect)
    expect(await screen.findByText(/decided by the vision model/i)).toBeInTheDocument()
  })

  it('banners a non-text block as vision-model described', () => {
    renderPlain(
      <AnnotationOverlay
        block={{ ...block, content_type: 'DIAGRAM', ocr_engine: 'VLM_SPECIALIZED', annotations: [] }}
      />,
    )
    expect(screen.getByText(/described by the vision model/i)).toBeInTheDocument()
  })

  it('renders no layer toggles when there are no annotations', () => {
    const { container } = renderPlain(<AnnotationOverlay block={{ ...block, annotations: [] }} />)
    expect(screen.queryAllByTestId('annotation-rect')).toHaveLength(0)
    expect(within(container).queryByRole('checkbox')).toBeNull()
  })
})
