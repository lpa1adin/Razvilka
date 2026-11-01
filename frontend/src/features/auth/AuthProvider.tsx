import { createContext, use, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { ApiError } from '@/lib/api'

import { authApi, type User } from './api'

type AuthState = {
  user: User | null
  /** true, пока не выяснили, есть ли активная сессия */
  checking: boolean
  /** ошибка проверки сессии, кроме «не вошёл» (например, сервер не отвечает) */
  error: string | null
  login: (login: string, password: string) => Promise<User>
  logout: () => Promise<void>
  retry: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    authApi
      .session()
      .then(({ user: me }) => !cancelled && (setUser(me), setError(null)))
      .catch((e: ApiError) => !cancelled && (setUser(null), setError(e.message)))
      .finally(() => !cancelled && setChecking(false))
    return () => {
      cancelled = true
    }
  }, [attempt])

  const login = useCallback(async (loginName: string, password: string) => {
    const me = await authApi.login(loginName, password)
    setUser(me)
    setError(null)
    return me
  }, [])

  const logout = useCallback(async () => {
    await authApi.logout().catch(() => undefined)
    setUser(null)
  }, [])

  const retry = useCallback(() => {
    setChecking(true)
    setAttempt((n) => n + 1)
  }, [])

  const value = useMemo(
    () => ({ user, checking, error, login, logout, retry }),
    [user, checking, error, login, logout, retry],
  )
  return <AuthContext value={value}>{children}</AuthContext>
}

export function useAuth() {
  const ctx = use(AuthContext)
  if (!ctx) throw new Error('useAuth вызван вне AuthProvider')
  return ctx
}
