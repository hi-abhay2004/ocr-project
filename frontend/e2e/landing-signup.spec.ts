import { expect, test } from '@playwright/test'

/**
 * The public entry path: homepage → create account → land in the right dashboard.
 *
 * The role radios are `sr-only` inputs inside their label (a standard pattern —
 * clicking the label toggles them). Playwright will not click a visually
 * clipped input, so these tests click the label, which is what a user does.
 *
 * Usernames are run-unique (RUN_ID suffix): this suite runs against a REAL,
 * PERSISTENT Postgres database, not MSW's per-test in-memory reset — a fixed
 * "newteacher" would 400 as "already exists" on the second run.
 */

const RUN_ID = Date.now()

test('homepage presents the project and both auth entry points', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { level: 1 })).toContainText('handwritten answer sheets')

  // The sections a viva would actually ask about are all on the page.
  await expect(page.getByRole('heading', { name: /six things existing systems get wrong/i })).toBeVisible()
  await expect(page.getByRole('heading', { name: /ten layers/i })).toBeVisible()
  await expect(page.getByRole('heading', { name: /where the vision model actually fires/i })).toBeVisible()
  await expect(page.getByRole('heading', { name: /becomes the marking scheme/i })).toBeVisible()

  // All three VLM call sites are named.
  for (const layer of ['L3.5', 'L4', 'L4.5']) {
    await expect(page.getByText(layer, { exact: true }).first()).toBeVisible()
  }

  await expect(page.getByText('Dr. Gireesh Babu C N')).toBeVisible()

  // Header anchors resolve to real sections.
  await page.getByRole('link', { name: 'How it works' }).click()
  await expect(page).toHaveURL(/#how-it-works$/)
})

test('signing up as a teacher lands on the exam list', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Create account' }).first().click()
  await expect(page).toHaveURL(/\/signup$/)

  await page.getByLabel('Full name').fill('New Teacher')
  await page.getByLabel('Username').fill(`newteacher_${RUN_ID}`)
  await page.getByLabel('Email').fill(`newteacher_${RUN_ID}@bmsit.in`)
  await page.getByLabel('Password', { exact: true }).fill('correct-horse')
  await page.getByLabel('Confirm password').fill('correct-horse')

  // No USN field for teachers.
  await expect(page.getByLabel('USN')).toHaveCount(0)

  await page.getByRole('button', { name: 'Create account' }).click()

  // Registration returns tokens, so the user is signed in already.
  await expect(page).toHaveURL(/\/exams$/)
  await expect(page.getByRole('heading', { name: 'Exams' })).toBeVisible()
  await expect(page.getByText('New Teacher')).toBeVisible()
})

test('signing up as a student requires a USN and lands on results', async ({ page }) => {
  await page.goto('/signup')
  await page.getByText('Student', { exact: true }).click()

  await page.getByLabel('Full name').fill('New Student')
  await page.getByLabel('Username').fill(`newstudent_${RUN_ID}`)
  await page.getByLabel('Email').fill(`newstudent_${RUN_ID}@bmsit.in`)
  await page.getByLabel('Password', { exact: true }).fill('correct-horse')
  await page.getByLabel('Confirm password').fill('correct-horse')

  // Submitting without the USN must not create the account.
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByText(/your usn is required/i)).toBeVisible()
  await expect(page).toHaveURL(/\/signup$/)

  await page.getByLabel('USN').fill(`1BY${RUN_ID % 100000}`.slice(0, 12))
  await page.getByRole('button', { name: 'Create account' }).click()

  await expect(page).toHaveURL(/\/results$/)
  await expect(page.getByRole('heading', { name: 'My results' })).toBeVisible()
})

test('a signed-in user sees a dashboard link on the homepage instead of the auth CTAs', async ({
  page,
}) => {
  // A fresh signup, not a login against a seeded "teacher"/"demo" account —
  // no such account exists in a real, freshly-migrated database. Seeded demo
  // credentials are a Phase B8 concern (scripts/seed_demo.py), separate from
  // what this suite can assume exists.
  await page.goto('/signup')
  await page.getByLabel('Full name').fill('Dashboard Check')
  await page.getByLabel('Username').fill(`dashcheck_${RUN_ID}`)
  await page.getByLabel('Email').fill(`dashcheck_${RUN_ID}@bmsit.in`)
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery')
  await page.getByLabel('Confirm password').fill('correct-horse-battery')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/exams$/)

  // The homepage stays reachable while signed in — it is the project
  // description, and bouncing people off it would hide it from the demo.
  await page.goto('/')
  await expect(page.getByRole('link', { name: /go to your dashboard/i })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Create account' })).toHaveCount(0)
})
