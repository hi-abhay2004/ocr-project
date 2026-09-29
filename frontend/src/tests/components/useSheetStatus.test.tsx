import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../mocks/server'
import { useSheetStatus } from '@/hooks/useSheets'
import { setTokens } from '@/lib/axios'
import { qk } from '@/hooks/keys'
import type { SheetStatus } from '@/types/api'

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
}

/** Serves a scripted sequence of statuses and counts how often it was asked. */
function scriptStatus(sequence: SheetStatus[]) {
  const state = { calls: 0 }
  server.use(
    http.get('/api/sheets/:sheetId/status/', () => {
      const status = sequence[Math.min(state.calls, sequence.length - 1)]
      state.calls += 1
      return HttpResponse.json({
        id: 1,
        status,
        stage: status === 'DONE' ? 'done' : 'ocr',
        started_at: new Date().toISOString(),
        error_message: null,
      })
    }),
  )
  return state
}

describe('useSheetStatus', () => {
  it('STOPS polling once the status is terminal', async () => {
    // The classic bug on this screen: a poller with no terminal condition keeps
    // hitting the API every 2s for every sheet the teacher has ever opened. This
    // asserts the call count stops growing after DONE.
    setTokens({ access: 'mock.teacher.1', refresh: 'refresh.teacher' })
    const state = scriptStatus(['RUNNING', 'RUNNING', 'DONE'])
    const client = makeClient()

    const { result } = renderHook(() => useSheetStatus(1, 101), { wrapper: wrapper(client) })

    await waitFor(() => expect(result.current.data?.status).toBe('DONE'), { timeout: 10_000 })

    const callsAtTerminal = state.calls
    await new Promise((r) => setTimeout(r, 2600)) // longer than the 2s interval
    expect(state.calls).toBe(callsAtTerminal)
    expect(result.current.isTerminal).toBe(true)
  }, 20_000)

  it('invalidates the full sheet payload on the RUNNING → DONE edge', async () => {
    // Polling /status/ only refreshes the lightweight status object. Without this
    // invalidation the finished marks never appear until a manual refresh.
    setTokens({ access: 'mock.teacher.1', refresh: 'refresh.teacher' })
    scriptStatus(['RUNNING', 'DONE'])

    const client = makeClient()
    const invalidated: unknown[][] = []
    const original = client.invalidateQueries.bind(client)
    client.invalidateQueries = ((filters: { queryKey?: unknown[] }) => {
      if (filters?.queryKey) invalidated.push(filters.queryKey)
      return original(filters as never)
    }) as typeof client.invalidateQueries

    const { result } = renderHook(() => useSheetStatus(1, 101), { wrapper: wrapper(client) })
    await waitFor(() => expect(result.current.data?.status).toBe('DONE'), { timeout: 10_000 })

    await waitFor(() =>
      expect(invalidated.map((k) => JSON.stringify(k))).toContain(JSON.stringify(qk.sheet(1))),
    )
    expect(invalidated.map((k) => JSON.stringify(k))).toContain(JSON.stringify(qk.sheetsAll(101)))
  }, 20_000)

  it('does not poll at all when there is no sheet id', async () => {
    setTokens({ access: 'mock.teacher.1', refresh: 'refresh.teacher' })
    const state = scriptStatus(['RUNNING'])
    const client = makeClient()

    renderHook(() => useSheetStatus(null), { wrapper: wrapper(client) })
    await new Promise((r) => setTimeout(r, 500))
    expect(state.calls).toBe(0)
  })
})
