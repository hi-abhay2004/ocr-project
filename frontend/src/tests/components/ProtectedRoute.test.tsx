import { screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '@/auth/AuthContext'
import { ProtectedRoute } from '@/auth/ProtectedRoute'
import { setTokens } from '@/lib/axios'

function renderAt(route: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<p>login page</p>} />
            <Route path="/exams" element={<p>teacher home</p>} />
            <Route path="/results" element={<p>student home</p>} />
            <Route
              path="/teacher-only"
              element={
                <ProtectedRoute requiredRole="TEACHER">
                  <p>teacher secret</p>
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ProtectedRoute', () => {
  it('sends an unauthenticated visitor to /login', async () => {
    renderAt('/teacher-only')
    expect(await screen.findByText('login page')).toBeInTheDocument()
  })

  it('lets the right role through', async () => {
    setTokens({ access: 'mock.teacher.1', refresh: 'refresh.teacher' })
    renderAt('/teacher-only')
    expect(await screen.findByText('teacher secret')).toBeInTheDocument()
  })

  it('bounces a student off a teacher route to their own home', async () => {
    // The frontend mirror of the DRF permission class. It is UX, not security —
    // the server must reject this independently, which the MSW handler for
    // /api/sheets/{id}/ also does with a 403.
    setTokens({ access: 'mock.student.1', refresh: 'refresh.student' })
    renderAt('/teacher-only')

    expect(await screen.findByText('student home')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('teacher secret')).toBeNull())
  })
})
