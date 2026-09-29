import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { server } from './mocks/server'
import { api, clearTokens, setTokens } from '@/lib/axios'

/**
 * THE highest-value test in the suite — FRONTEND_PLAN §10.
 *
 * A dashboard mounting several queries fires them at once. If the access token
 * has expired they all 401 at the same instant. Without a shared in-flight
 * promise each one starts its own refresh: the first rotates the refresh token,
 * the rest present a token that is now dead, get 401 back, and the user is
 * thrown to /login mid-session.
 *
 * The failure is timing-dependent, only shows up under concurrency, and is
 * invisible in manual testing — which is exactly why it survives to demo day.
 */

describe('single-flight token refresh', () => {
  beforeEach(() => {
    clearTokens()
    setTokens({ access: 'expired-access', refresh: 'valid-refresh' })
  })

  it('refreshes exactly once for concurrent 401s and resolves all of them', async () => {
    let refreshCalls = 0
    let currentAccess = 'expired-access'

    server.use(
      http.post('/api/auth/refresh/', async ({ request }) => {
        const { refresh } = (await request.json()) as { refresh: string }
        // A rotated refresh token: presenting the old one a second time fails,
        // which is what turns a refresh storm into a forced logout.
        if (refresh !== 'valid-refresh') {
          return HttpResponse.json({ detail: 'Token is blacklisted' }, { status: 401 })
        }
        refreshCalls += 1
        currentAccess = 'fresh-access'
        // Latency is the whole point: without it the calls serialise by accident
        // and a broken implementation would pass.
        await new Promise((r) => setTimeout(r, 50))
        return HttpResponse.json({ access: currentAccess, refresh: 'rotated-refresh' })
      }),

      http.get('/api/exams/', ({ request }) => {
        const auth = request.headers.get('Authorization')
        if (auth !== `Bearer ${currentAccess}` || currentAccess === 'expired-access') {
          return HttpResponse.json({ detail: 'Token expired' }, { status: 401 })
        }
        return HttpResponse.json([{ id: 1 }])
      }),
    )

    const results = await Promise.all([
      api.get('/exams/'),
      api.get('/exams/'),
      api.get('/exams/'),
      api.get('/exams/'),
      api.get('/exams/'),
    ])

    expect(refreshCalls).toBe(1)
    expect(results).toHaveLength(5)
    for (const res of results) expect(res.status).toBe(200)
  })

  it('retries a request only once, so an expired session cannot loop', async () => {
    let protectedCalls = 0

    server.use(
      http.post('/api/auth/refresh/', () =>
        // Refresh keeps "succeeding" but the new token is still rejected below —
        // the pathological case where retrying forever would hang the app.
        HttpResponse.json({ access: 'still-bad', refresh: 'valid-refresh' }),
      ),
      http.get('/api/exams/', () => {
        protectedCalls += 1
        return HttpResponse.json({ detail: 'Token expired' }, { status: 401 })
      }),
    )

    await expect(api.get('/exams/')).rejects.toMatchObject({ response: { status: 401 } })
    // Original + exactly one retry.
    expect(protectedCalls).toBe(2)
  })

  it('clears tokens and notifies the app when the refresh itself fails', async () => {
    let failureNotified = false
    const { setOnAuthFailure, getRefreshToken } = await import('@/lib/axios')
    setOnAuthFailure(() => {
      failureNotified = true
    })

    server.use(
      http.post('/api/auth/refresh/', () =>
        HttpResponse.json({ detail: 'Token is invalid or expired' }, { status: 401 }),
      ),
      http.get('/api/exams/', () => HttpResponse.json({ detail: 'Token expired' }, { status: 401 })),
    )

    await expect(api.get('/exams/')).rejects.toBeDefined()
    expect(failureNotified).toBe(true)
    expect(getRefreshToken()).toBeNull()
    setOnAuthFailure(null)
  })

  it('does not attempt a refresh when the login endpoint itself returns 401', async () => {
    let refreshCalls = 0
    server.use(
      http.post('/api/auth/refresh/', () => {
        refreshCalls += 1
        return HttpResponse.json({ access: 'x', refresh: 'y' })
      }),
      http.post('/api/auth/login/', () =>
        HttpResponse.json({ detail: 'No active account found' }, { status: 401 }),
      ),
    )

    // Bad credentials are not a stale session; refreshing here would mask the
    // real error and show the user "something went wrong" instead of "wrong password".
    await expect(api.post('/auth/login/', { username: 'x', password: 'bad' })).rejects.toBeDefined()
    expect(refreshCalls).toBe(0)
  })
})
