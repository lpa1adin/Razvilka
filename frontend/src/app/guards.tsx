import { RotateCw } from 'lucide-react'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import { Button } from '@/components/ui/Button'
import { Logo } from '@/components/ui/Logo'
import { useAuth } from '@/features/auth/AuthProvider'
import { ForbiddenPage } from '@/pages/ForbiddenPage'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, checking, error, retry } = useAuth()
  const location = useLocation()

  if (checking) {
    return (
      <div className="grid min-h-dvh place-items-center" role="status" aria-label="Проверяем вход">
        <span className="animate-pulse opacity-70">
          <Logo />
        </span>
      </div>
    )
  }
  if (error) {
    return (
      <div className="grid min-h-dvh place-items-center px-4">
        <div className="panel max-w-md p-6">
          <p className="eyebrow">Нет связи</p>
          <p className="mt-2 text-lg font-semibold">{error}</p>
          <Button variant="secondary" className="mt-5" onClick={retry} icon={<RotateCw className="size-4" />}>
            Проверить ещё раз
          </Button>
        </div>
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

/** Интерфейс прячет Мастерскую от пользователя, но настоящая защита — 403 на сервере (ADR-011). */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  return user?.role === 'admin' ? children : <ForbiddenPage />
}
