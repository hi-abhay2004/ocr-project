import axios, {
  AxiosError,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'
import type { RegisterInput, TokenPair, User } from '@/types/api'

/**
 * Auth transport — FRONTEND_PLAN §5.
 *
 * Access token lives in a MODULE variable: it survives every re-render and dies
 * with the tab. Refresh token lives in localStorage so a reload can recover the
 * session. Deliberately not the reverse — an XSS that can read localStorage gets
 * a refresh token either way, but keeping the access token out of storage means
 * it is never at rest.
 */

const REFRESH_STORAGE_KEY = 'aes.refresh'

let accessToken: string | null = null

/** Set once at startup by AuthContext, so this module never imports the router. */
let onAuthFailure: (() => void) | null = null

export function setOnAuthFailure(fn: (() => void) | null) {
  onAuthFailure = fn
}

export function getAccessToken() {
  return accessToken
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_STORAGE_KEY)
}

export function setTokens(tokens: TokenPair) {
  accessToken = tokens.access
  localStorage.setItem(REFRESH_STORAGE_KEY, tokens.refresh)
}

export function clearTokens() {
  accessToken = null
  localStorage.removeItem(REFRESH_STORAGE_KEY)
}

export const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

/**
 * A SEPARATE bare client for the refresh call itself.
 *
 * If the refresh went through `api` it would hit the response interceptor below,
 * and a 401 from the refresh endpoint would trigger another refresh — infinite
 * recursion on an expired session.
 */
const refreshClient = axios.create({ baseURL: '/api' })

/* ── Request interceptor ──────────────────────────────────────────────── */

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    config.headers.set('Authorization', `Bearer ${accessToken}`)
  }
  // Let the browser set the multipart boundary itself on sheet uploads.
  if (config.data instanceof FormData) {
    config.headers.delete('Content-Type')
  }
  return config
})

/* ── Single-flight refresh ────────────────────────────────────────────── */

/**
 * THE critical variable in this file.
 *
 * A dashboard mounting five queries fires five simultaneous requests; if the
 * access token has expired, all five come back 401 at nearly the same moment.
 * Without this shared promise each one starts its own refresh: the first
 * succeeds and rotates the refresh token, the other four present the now-rotated
 * token, get 401, and log the user out mid-session. Every 401 must await the
 * SAME promise.
 */
let refreshPromise: Promise<string> | null = null

function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise

  const refresh = getRefreshToken()
  if (!refresh) return Promise.reject(new Error('no refresh token'))

  refreshPromise = refreshClient
    .post<TokenPair>('/auth/refresh/', { refresh })
    .then((res) => {
      // SimpleJWT returns a new refresh only when ROTATE_REFRESH_TOKENS is on.
      setTokens({ access: res.data.access, refresh: res.data.refresh ?? refresh })
      return res.data.access
    })
    .finally(() => {
      // Cleared in BOTH outcomes: leaving a rejected promise cached would make
      // every future 401 reuse the same failure forever.
      refreshPromise = null
    })

  return refreshPromise
}

/** `_retried` marks a request that has already had one refresh spent on it. */
type RetriableConfig = AxiosRequestConfig & { _retried?: boolean }

/* ── Response interceptor ─────────────────────────────────────────────── */

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as (InternalAxiosRequestConfig & RetriableConfig) | undefined

    if (error.response?.status !== 401 || !config || config._retried) {
      return Promise.reject(error)
    }

    // A 401 from the login endpoint means bad credentials, not a stale token.
    if (config.url?.includes('/auth/login/') || config.url?.includes('/auth/refresh/')) {
      return Promise.reject(error)
    }

    config._retried = true

    try {
      const token = await refreshAccessToken()
      config.headers.set('Authorization', `Bearer ${token}`)
      return api(config)
    } catch {
      clearTokens()
      onAuthFailure?.()
      return Promise.reject(error)
    }
  },
)

/* ── Auth calls ───────────────────────────────────────────────────────── */

export async function login(username: string, password: string): Promise<User> {
  const { data } = await refreshClient.post<TokenPair>('/auth/login/', { username, password })
  setTokens(data)
  return fetchMe()
}

export async function register(input: RegisterInput): Promise<User> {
  // Same bare client as login: a 400 here is a validation error to show the
  // user, never a stale session to refresh.
  const { data } = await refreshClient.post<TokenPair>('/auth/register/', input)
  setTokens(data)
  return fetchMe()
}

export async function fetchMe(): Promise<User> {
  const { data } = await api.get<User>('/auth/me/')
  return data
}

export function logout() {
  clearTokens()
}

/** Turns an axios failure into something worth showing a user. */
export function errorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as Record<string, unknown> | undefined
    if (typeof data?.detail === 'string') return data.detail
    if (data && typeof data === 'object') {
      const first = Object.values(data)[0]
      if (Array.isArray(first) && typeof first[0] === 'string') return first[0]
      if (typeof first === 'string') return first
    }
    if (error.code === 'ERR_NETWORK') return 'Cannot reach the server'
  }
  return fallback
}
