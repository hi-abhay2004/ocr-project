import { createContext, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  clearTokens,
  fetchMe,
  getRefreshToken,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  setOnAuthFailure,
} from '@/lib/axios'
import type { RegisterInput, Role, User } from '@/types/api'

export interface AuthState {
  user: User | null
  /** True during the startup session-restore. Guards must wait for this. */
  isLoading: boolean
  login: (username: string, password: string) => Promise<User>
  register: (input: RegisterInput) => Promise<User>
  logout: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

/** Where each role lands after login, and where a wrong-role URL bounces to. */
export const HOME_FOR_ROLE: Record<Role, string> = {
  TEACHER: '/exams',
  STUDENT: '/results',
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  // A ref, not state: the interceptor callback is registered once and must not
  // capture a stale setter across re-renders.
  const setUserRef = useRef(setUser)
  setUserRef.current = setUser

  useEffect(() => {
    // The axios layer cannot import the router (circular), so it calls back here
    // when a refresh fails. Dropping the user re-renders the guards, which
    // redirect to /login on their own.
    setOnAuthFailure(() => setUserRef.current(null))
    return () => setOnAuthFailure(null)
  }, [])

  useEffect(() => {
    // Session restore. The access token died with the last tab; the refresh
    // token in localStorage is what makes a reload not feel like a logout.
    // Any request will transparently mint a new access token via the
    // interceptor, so /auth/me/ is enough to prove the session is alive.
    if (!getRefreshToken()) {
      setIsLoading(false)
      return
    }
    fetchMe()
      .then(setUser)
      .catch(() => clearTokens())
      .finally(() => setIsLoading(false))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const u = await apiLogin(username, password)
    setUser(u)
    return u
  }, [])

  const register = useCallback(async (input: RegisterInput) => {
    const u = await apiRegister(input)
    setUser(u)
    return u
  }, [])

  const logout = useCallback(() => {
    apiLogout()
    setUser(null)
  }, [])

  const value = useMemo<AuthState>(
    () => ({ user, isLoading, login, register, logout }),
    [user, isLoading, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
