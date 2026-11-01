import { ArrowRight, Eye, EyeOff } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'

import { CodeField } from '@/components/effects/CodeField'
import { Button } from '@/components/ui/Button'
import { Logo } from '@/components/ui/Logo'
import { useAuth } from '@/features/auth/AuthProvider'
import { ApiError } from '@/lib/api'

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/'

  const [loginName, setLoginName] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (user) return <Navigate to={from} replace />

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!loginName.trim() || !password) {
      setError('Введите логин и пароль')
      return
    }
    setSending(true)
    setError(null)
    try {
      await login(loginName, password)
      navigate(from, { replace: true })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не получилось войти. Попробуйте ещё раз.')
    } finally {
      setSending(false)
    }
  }

  const field =
    'h-11 w-full rounded-md border border-line-strong bg-bg/60 px-3 text-[15px] text-text outline-none transition-colors ' +
    'placeholder:text-faint focus:border-accent focus-visible:outline-none aria-[invalid=true]:border-danger'

  return (
    <div className="relative flex min-h-dvh flex-col overflow-hidden">
      <CodeField />
      {/* Свечение из центра, как в зелёном референсе */}
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-[38%] size-[min(900px,140vw)] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-60 blur-3xl"
        style={{ background: 'radial-gradient(circle, var(--accent-soft) 0%, transparent 60%)' }}
      />

      <header className="relative flex items-center justify-between px-4 py-5 sm:px-8">
        <Logo />
        <p className="eyebrow hidden sm:block">Локальная платформа · v0.1</p>
      </header>

      <main className="relative flex flex-1 flex-col items-center justify-center px-4 pb-16">
        <section aria-labelledby="login-title" className="w-full max-w-[880px] text-center">
          <p className="eyebrow rise-in">Точка входа</p>
          <h1
            id="login-title"
            className="wordmark rise-in mt-4 text-[clamp(52px,12vw,128px)] text-text [animation-delay:80ms] [text-shadow:0_20px_60px_rgb(0_0_0/0.5)]"
          >
            Развилка
          </h1>
          <p className="rise-in mx-auto mt-5 max-w-md text-muted [animation-delay:160ms] sm:ml-auto sm:mr-6 sm:text-right">
            Учимся писать код, понимать архитектуру и обосновывать каждое решение.
          </p>
        </section>

        <form
          onSubmit={onSubmit}
          noValidate
          className="panel rise-in mt-12 w-full max-w-[400px] p-6 text-left [animation-delay:240ms] sm:p-7"
          aria-describedby={error ? 'login-error' : undefined}
        >
          <p className="font-mono text-sm text-muted">
            <span className="text-accent">$</span> razvilka login<span className="caret" />
          </p>

          <label htmlFor="login" className="mt-6 block text-sm font-medium">
            Логин
          </label>
          <input
            id="login"
            name="username"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            className={`${field} mt-2`}
            value={loginName}
            onChange={(e) => (setLoginName(e.target.value), setError(null))}
            aria-invalid={!!error}
          />

          <label htmlFor="password" className="mt-4 block text-sm font-medium">
            Пароль
          </label>
          <div className="relative mt-2">
            <input
              id="password"
              name="password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              className={`${field} pr-11`}
              value={password}
              onChange={(e) => (setPassword(e.target.value), setError(null))}
              aria-invalid={!!error}
            />
            <button
              type="button"
              onClick={() => setShowPassword((s) => !s)}
              className="absolute right-1 top-1 grid size-9 place-items-center rounded-md text-muted hover:text-text"
              aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
            >
              {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>

          {error && (
            <p id="login-error" role="alert" className="mt-3 text-sm text-danger">
              {error}
            </p>
          )}

          <Button type="submit" className="mt-6 h-11 w-full" loading={sending} loadingText="Входим…" icon={<ArrowRight className="size-4" />}>
            Войти
          </Button>
          <p className="mt-4 text-center text-xs text-faint">Учётки создаёт администратор — регистрации нет.</p>
        </form>
      </main>

      {/* Вертикальная подпись у края, как «SCROLL» в TURA */}
      <p
        aria-hidden
        className="eyebrow absolute bottom-10 right-6 hidden origin-bottom-right translate-x-full rotate-90 lg:block"
      >
        выбор · обоснование · реализация
      </p>
    </div>
  )
}
