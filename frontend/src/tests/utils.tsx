import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderOptions } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AuthProvider } from '@/auth/AuthContext'

/** Retry off and no caching between tests — a retry turns a failed assertion
 *  into a timeout, which is much harder to read than the actual error. */
function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })
}

export function renderWithProviders(
  ui: React.ReactElement,
  { route = '/', ...options }: RenderOptions & { route?: string } = {},
) {
  const client = makeClient()
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[route]}>
          <AuthProvider>
            <TooltipProvider>{ui}</TooltipProvider>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
      options,
    ),
  }
}

/** Lighter wrapper for pure presentational components. */
export function renderPlain(ui: React.ReactElement, options?: RenderOptions) {
  return render(<TooltipProvider>{ui}</TooltipProvider>, options)
}
