import { expect, type Page } from '@playwright/test'

/**
 * Shared setup for specs that need a real, reviewable sheet against the real
 * backend (Phase B3's stub evaluator) — happy-path.spec.ts and
 * overlay-scaling.spec.ts both start from exactly this state.
 *
 * Runs against a REAL, PERSISTENT Postgres database, not MSW's per-test
 * in-memory reset — every account/USN is run-unique so repeated runs don't
 * collide with "already exists" 400s from a previous run.
 */

// One 1x1 PNG, reused by every spec that needs to upload "a sheet" — the
// stub evaluator ignores the actual uploaded bytes and renders its own
// fixture crop (apps/evaluation/fixtures.py), so the upload only needs to be
// a valid image, not a realistic scan.
const PNG_1X1_HEX =
  '89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c4944415478' +
  '9c63f8cfc000000301010018dd8db00000000049454e44ae426082'

export function uniqueId(): string {
  return `${Date.now()}${Math.floor(Math.random() * 1000)}`
}

export async function signUpTeacher(page: Page, fullName: string, runId: string) {
  await page.goto('/signup')
  await page.getByLabel('Full name').fill(fullName)
  await page.getByLabel('Username').fill(`teacher_${runId}`)
  await page.getByLabel('Email').fill(`teacher_${runId}@bmsit.in`)
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery')
  await page.getByLabel('Confirm password').fill('correct-horse-battery')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/exams$/)
}

export async function signUpStudent(page: Page, fullName: string, usn: string, runId: string) {
  await page.goto('/signup')
  await page.getByText('Student', { exact: true }).click()
  await page.getByLabel('Full name').fill(fullName)
  await page.getByLabel('Username').fill(`student_${runId}`)
  await page.getByLabel('Email').fill(`student_${runId}@bmsit.in`)
  await page.getByLabel('USN').fill(usn)
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery')
  await page.getByLabel('Confirm password').fill('correct-horse-battery')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/results$/)
}

/**
 * Signs up a fresh teacher, creates an exam with one question (waits for
 * real concept extraction), enrols a student, uploads a sheet for them, and
 * waits for the real Phase B3 stub evaluator to finish — then clicks through
 * to the review screen. Leaves `page` on ReviewDetail for a DONE sheet.
 *
 * Returns the USN used, so a caller that needs the student side later (e.g.
 * happy-path.spec.ts) can sign up with the exact same USN and have it link
 * to the pre-added Student row (the create-or-link behaviour from Phase B1).
 */
export async function setUpReviewableSheet(page: Page): Promise<{ usn: string; runId: string }> {
  const runId = uniqueId()
  const usn = `1BY${runId}`.slice(0, 12)

  await signUpTeacher(page, 'Dr Gireesh Babu C N', runId)

  await page.getByRole('button', { name: 'New exam' }).click()
  await page.getByLabel('Exam name').fill('CIE-2 DBMS (E2E)')
  await page.getByLabel('Subject').fill('22CS52 · DBMS')
  await page.getByLabel('Total marks').fill('30')
  await page.getByRole('button', { name: 'Create exam' }).click()
  await page.getByRole('link', { name: 'CIE-2 DBMS (E2E)' }).click()

  await page.getByRole('link', { name: /Questions & model answers/ }).click()
  await page.getByRole('button', { name: 'Add question' }).click()
  await page.getByLabel('Number').fill('1a')
  await page.getByLabel('Max marks').fill('10')
  await page.getByLabel('Question').fill('Define BCNF. Explain how it differs from 3NF.')
  await page.getByLabel('Model answer').fill(
    'BCNF is a normal form for relational schemas. A relation R is in BCNF if for every ' +
      'non-trivial functional dependency X to Y, X must be a superkey of R. It is stricter ' +
      'than 3NF and removes redundancy caused by transitive dependencies.',
  )
  await page.getByRole('button', { name: 'Save question' }).click()
  await expect(page.getByTestId('extracting-skeleton')).toBeHidden({ timeout: 15_000 })

  await page.getByRole('link', { name: /Back to exam/ }).click()
  // The ExamDetail card links wrap title + description together (e.g.
  // "Students No class list yet"), so an end-anchored regex would never
  // match — this only needs to anchor the start.
  await page.getByRole('link', { name: /^Students/ }).click()
  await page.getByRole('button', { name: 'Add student' }).click()
  await page.getByLabel('USN').fill(usn)
  await page.getByLabel('Name').fill('P Charan Chandra')
  await page.getByLabel('Email').fill(`charan_${runId}@bmsit.in`)
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await expect(page.getByText(usn)).toBeVisible()

  await page.getByRole('link', { name: /Back to exam/ }).click()
  await page.getByRole('link', { name: /Upload answer sheets/ }).click()
  await page.getByLabel('Student').click()
  await page.getByRole('option', { name: new RegExp(usn) }).click()
  await page.setInputFiles('input[type="file"]', {
    name: 'sheet.png',
    mimeType: 'image/png',
    buffer: Buffer.from(PNG_1X1_HEX, 'hex'),
  })
  await page.getByRole('button', { name: /^Upload/ }).click()

  const reviewLink = page.getByRole('link', { name: 'Review this sheet' })
  await expect(reviewLink).toBeVisible({ timeout: 30_000 })
  await reviewLink.click()

  return { usn, runId }
}
