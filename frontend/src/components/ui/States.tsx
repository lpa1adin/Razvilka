import { RotateCw } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from './Button'

/** Скелетон по форме будущего контента. */
export function Skeleton({ lines = 3, className = '' }: { lines?: number; className?: string }) {
  return (
    <div className={`flex flex-col gap-3 ${className}`} role="status" aria-label="Загружаем">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-16 animate-pulse rounded-lg bg-surface-2/70" style={{ opacity: 1 - i * 0.18 }} />
      ))}
    </div>
  )
}

export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="panel flex flex-wrap items-center justify-between gap-4 p-5" role="alert">
      <p className="text-danger">{message}</p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry} icon={<RotateCw className="size-4" />}>
          Повторить
        </Button>
      )}
    </div>
  )
}

export function PageHeader({ eyebrow, title, text, actions, ai }: { eyebrow: string; title: ReactNode; text?: ReactNode; actions?: ReactNode; ai?: boolean }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <p className={`eyebrow ${ai ? 'text-ai' : ''}`}>{eyebrow}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
        {text && <p className="mt-3 max-w-2xl text-muted">{text}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-3">{actions}</div>}
    </header>
  )
}

export function Badge({ tone = 'muted', children }: { tone?: 'muted' | 'accent' | 'ai' | 'danger'; children: ReactNode }) {
  const tones = {
    muted: 'border-line-strong text-muted',
    accent: 'border-accent/40 bg-accent-soft text-accent',
    ai: 'border-ai/40 bg-ai-soft text-ai',
    danger: 'border-danger/40 bg-danger-soft text-danger',
  }
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 font-mono text-[11px] ${tones[tone]}`}>{children}</span>
}

export function Progress({ done, total, label }: { done: number; total: number; label: string }) {
  const pct = total ? Math.round((done / total) * 100) : 0
  return (
    <div>
      <div className="flex justify-between text-xs text-muted">
        <span>{label}</span>
        <span className="font-mono">
          {done} из {total}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className="h-full rounded-full bg-accent shadow-[0_0_12px_var(--accent)] transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
