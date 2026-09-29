import { expect, test } from '@playwright/test'
import { setUpReviewableSheet } from './helpers'

/**
 * The three-width overlay check (§11), automated.
 *
 * FRONTEND_PLAN calls this "the one manual step worth doing every time" — it is
 * the assertion that the viewBox scaling in §7 is right, and it is what will be
 * on screen during the viva. A manual check done every time is a check that
 * eventually is not done, so it lives here instead.
 *
 * The assertion is scale-invariant on purpose: rather than checking pixel
 * positions (which differ at every width), it checks that each box occupies the
 * same FRACTION of the rendered image at every width. That is exactly the
 * property `viewBox` is supposed to guarantee, and the property that breaks the
 * moment someone reintroduces a JS scale factor or the backend switches bbox to
 * page coordinates.
 *
 * The absolute-position check depends on apps/evaluation/fixtures.py being a
 * line-for-line port of frontend/src/tests/mocks/fixtureImage.ts's layout
 * arithmetic (verified in apps/evaluation/tests/test_pipeline.py too, from the
 * backend side) — this is the frontend-side half of that same guarantee.
 */

const WIDTHS = [1440, 1024, 768]

const CROP_W = 1240
const CROP_H = 480

test('annotation boxes hold their position on the crop at every browser width', async ({ page }) => {
  test.setTimeout(60_000) // the real stub pipeline runs 12 stages, not an MSW timeout

  await setUpReviewableSheet(page)
  await expect(page.locator('[data-testid="annotation-rect"]').first()).toBeVisible()

  const measurements: Record<string, { x: number; y: number; w: number; h: number }[]> = {}

  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 })
    // Let layout settle before measuring.
    await page.waitForTimeout(150)

    const img = page.locator('img[alt^="Answer crop"]').first()
    const imgBox = (await img.boundingBox())!
    expect(imgBox.width).toBeGreaterThan(0)

    // The <img> must keep the crop's aspect ratio, or the SVG overlaid on it
    // (preserveAspectRatio="none") would stretch differently from the picture.
    expect(imgBox.height / imgBox.width).toBeCloseTo(CROP_H / CROP_W, 2)

    const rects = page.locator('[data-testid="annotation-rect"]')
    const count = await rects.count()
    expect(count).toBeGreaterThan(0)

    const frames: { x: number; y: number; w: number; h: number }[] = []
    for (let i = 0; i < count; i++) {
      const box = (await rects.nth(i).boundingBox())!
      // Position and size as a fraction of the rendered image.
      frames.push({
        x: (box.x - imgBox.x) / imgBox.width,
        y: (box.y - imgBox.y) / imgBox.height,
        w: box.width / imgBox.width,
        h: box.height / imgBox.height,
      })
    }
    measurements[String(width)] = frames
  }

  const reference = measurements[String(WIDTHS[0])]

  for (const width of WIDTHS.slice(1)) {
    const frames = measurements[String(width)]
    expect(frames).toHaveLength(reference.length)

    frames.forEach((frame, i) => {
      // 1% of the image width. Anything larger means the box has visibly slid
      // off the word it is supposed to be marking.
      expect(frame.x, `box ${i} x drifted at ${width}px`).toBeCloseTo(reference[i].x, 2)
      expect(frame.y, `box ${i} y drifted at ${width}px`).toBeCloseTo(reference[i].y, 2)
      expect(frame.w, `box ${i} width drifted at ${width}px`).toBeCloseTo(reference[i].w, 2)
      expect(frame.h, `box ${i} height drifted at ${width}px`).toBeCloseTo(reference[i].h, 2)
    })
  }

  // And the absolute placement matches the fixture's own geometry: the STRIKE
  // box starts at x=755 of 1240, i.e. ~60.9% across the crop. This is what
  // catches a page-coordinate or normalised-coordinate bbox contract (§3.1).
  const strike = page.locator('[data-testid="annotation-rect"][data-kind="STRIKE"]').first()
  const img = page.locator('img[alt^="Answer crop"]').first()
  const strikeBox = (await strike.boundingBox())!
  const imgBox = (await img.boundingBox())!
  expect((strikeBox.x - imgBox.x) / imgBox.width).toBeCloseTo(755 / CROP_W, 2)
  expect(strikeBox.width / imgBox.width).toBeCloseTo(217 / CROP_W, 2)
})
