import { expect, test } from '@playwright/test'
import { setUpReviewableSheet, signUpStudent, uniqueId } from './helpers'

/**
 * The one end-to-end spec (§10).
 *
 * Covers the demo script: teacher signs up → creates an exam and a question
 * → adds a student → uploads a sheet → watches the real pipeline (stub
 * evaluator, Phase B3) run → reviews with the annotation overlay → overrides
 * a mark → approves → student signs up (linking the pre-added USN) and sees
 * the published result, and cannot reach anyone else's.
 */

test('teacher reviews, overrides and approves; student sees the result', async ({ page }) => {
  test.setTimeout(60_000) // the real stub pipeline runs 12 stages, not an MSW timeout

  const { usn, runId } = await setUpReviewableSheet(page)

  // ── The overlay: the thing the whole project is demonstrating ──────────
  const rects = page.locator('[data-testid="annotation-rect"]')
  await expect(rects.first()).toBeVisible()
  expect(await rects.count()).toBeGreaterThan(0)

  // A VLM-adjudicated box renders dashed — visible proof of CV → VLM
  // escalation, and exactly what apps/evaluation/fixtures.py's ported
  // geometry guarantees is present on the first block.
  const vlmRect = page.locator('[data-testid="annotation-rect"][data-resolved-by="VLM"]').first()
  await expect(vlmRect).toHaveAttribute('stroke-dasharray', /\d/)

  // Toggling a layer removes only that kind.
  await page.getByLabel(/show struck out annotations/i).click()
  await expect(page.locator('[data-testid="annotation-rect"][data-kind="STRIKE"]')).toHaveCount(0)
  await expect(rects.first()).toBeVisible()

  // Concept breakdown is populated from real cosine similarity.
  await page.getByRole('tab', { name: /Concepts/ }).click()
  await expect(page.locator('[data-testid="concept-bar"]').first()).toBeVisible()

  // ── Override a mark ────────────────────────────────────────────────────
  const marks = page.getByLabel('Final marks')
  await marks.fill('7')
  await page.getByLabel(/^Comment/).fill('Diagram was acceptable')
  await page.getByRole('button', { name: 'Save override' }).click()
  await expect(page.getByText('Marks overridden')).toBeVisible()

  // ── Approve ────────────────────────────────────────────────────────────
  await page.getByRole('button', { name: 'Approve & publish' }).click()
  await page.getByRole('button', { name: 'Approve & publish' }).last().click()
  await expect(page.getByText(/the student can now see this result/i)).toBeVisible()

  // ── Student: sign up with the SAME usn, linking the pre-added row ──────
  await page.getByRole('button', { name: 'Log out' }).click()
  await signUpStudent(page, 'P Charan Chandra', usn, runId)

  await expect(page.getByRole('heading', { name: 'My results' })).toBeVisible()
  // Matches the exam name setUpReviewableSheet() actually creates (helpers.ts).
  await page.getByText('CIE-2 DBMS (E2E)').first().click()

  await expect(page.locator('[data-testid="concept-bar"]').first()).toBeVisible()
  // No override controls and no raw crop on the student side.
  await expect(page.getByLabel('Final marks')).toHaveCount(0)
  await expect(page.locator('[data-testid="annotation-rect"]')).toHaveCount(0)
})

test('a student cannot reach a teacher route by URL', async ({ page }) => {
  const runId = uniqueId()
  await signUpStudent(page, 'A Deepika', `1DY${runId}`.slice(0, 12), runId)

  // A hard navigation, so this also exercises session restore: the access
  // token died with the page, and only the refresh token in localStorage
  // brings it back.
  await page.goto('/exams')

  // Guard bounces them to their own home. The DRF permission is the real
  // boundary; this only asserts they never see a screen meant for a teacher.
  await expect(page).toHaveURL(/\/results$/)
  await expect(page.getByRole('heading', { name: 'My results' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Exams' })).toHaveCount(0)
})
