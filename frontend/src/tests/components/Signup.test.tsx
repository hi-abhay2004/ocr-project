import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { Signup } from '@/pages/Signup'
import { server } from '../mocks/server'
import { renderWithProviders } from '../utils'

async function fillCommonFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Full name'), 'A Deepika')
  await user.type(screen.getByLabelText('Username'), 'deepika')
  await user.type(screen.getByLabelText('Email'), 'deepika@bmsit.in')
  await user.type(screen.getByLabelText('Password'), 'correct-horse')
  await user.type(screen.getByLabelText('Confirm password'), 'correct-horse')
}

describe('Signup', () => {
  it('defaults to the teacher role and hides the USN field', () => {
    renderWithProviders(<Signup />)
    expect(screen.getByRole('radio', { name: /teacher/i })).toBeChecked()
    expect(screen.queryByLabelText('USN')).toBeNull()
  })

  it('reveals the USN field only when the student role is chosen', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Signup />)

    await user.click(screen.getByRole('radio', { name: /student/i }))
    expect(await screen.findByLabelText('USN')).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: /teacher/i }))
    await waitFor(() => expect(screen.queryByLabelText('USN')).toBeNull())
  })

  it('requires a USN for students', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Signup />)

    await user.click(screen.getByRole('radio', { name: /student/i }))
    await fillCommonFields(user)
    await user.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByText(/your usn is required/i)).toBeInTheDocument()
  })

  it('rejects mismatched passwords', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Signup />)

    await user.type(screen.getByLabelText('Full name'), 'A Deepika')
    await user.type(screen.getByLabelText('Username'), 'deepika')
    await user.type(screen.getByLabelText('Email'), 'deepika@bmsit.in')
    await user.type(screen.getByLabelText('Password'), 'correct-horse')
    await user.type(screen.getByLabelText('Confirm password'), 'correct-hors')
    await user.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument()
  })

  it('rejects a short password', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Signup />)

    await user.type(screen.getByLabelText('Password'), 'short')
    await user.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByText(/at least 8 characters/i)).toBeInTheDocument()
  })

  it('omits usn from the request body for teachers', async () => {
    const user = userEvent.setup()
    let body: Record<string, unknown> | null = null

    server.use(
      http.post('/api/auth/register/', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ access: 'mock.teacher.1', refresh: 'refresh.teacher' }, { status: 201 })
      }),
    )

    renderWithProviders(<Signup />)
    await fillCommonFields(user)
    await user.click(screen.getByRole('button', { name: /create account/i }))

    // Sending `usn: ""` would make a NOT NULL / blank=False serializer reject a
    // perfectly valid teacher signup, so the key must be absent, not empty.
    await waitFor(() => expect(body).not.toBeNull())
    expect(body!).toMatchObject({ username: 'deepika', role: 'TEACHER' })
    expect(Object.hasOwn(body!, 'usn')).toBe(false)
  })

  it('surfaces a field-keyed 400 from the server', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('/api/auth/register/', () =>
        HttpResponse.json({ username: ['A user with that username already exists.'] }, { status: 400 }),
      ),
    )

    renderWithProviders(<Signup />)
    await fillCommonFields(user)
    await user.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument()
  })
})
