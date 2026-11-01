import { ArrowUpRight, RotateCw, Wand2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Button, ButtonLink } from '@/components/ui/Button'
import { api } from '@/lib/api'

type Overview = { users: Partial<Record<'user' | 'admin', number>>; jobs: Partial<Record<'queued' | 'running' | 'done' | 'failed', number>> }

const STEPS = ['Заявка', 'План', 'Черновик', 'Автопроверки', 'Проверка админом', 'Публикация']

export function WorkshopOverviewPage() {
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    api<Overview>('/api/workshop/overview')
      .then(setData)
      .catch((e: Error) => setError(e.message))
  }, [])
  useEffect(load, [load])

  const stats = [
    { label: 'Пользователи', value: data?.users.user },
    { label: 'Администраторы', value: data?.users.admin },
    { label: 'Задачи в очереди', value: data?.jobs.queued },
    { label: 'Задачи с ошибкой', value: data?.jobs.failed },
  ]

  return (
    <div className="rise-in flex flex-col gap-8">
      <header>
        <p className="eyebrow text-ai">Мастерская</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Обзор</h1>
        <p className="mt-3 max-w-2xl text-muted">
          Здесь создаются курсы и задания. Пользователь видит только то, что вы опубликуете.
        </p>
      </header>

      {error ? (
        <div className="panel flex flex-wrap items-center justify-between gap-4 p-5">
          <p className="text-danger">{error}</p>
          <Button variant="secondary" onClick={load} icon={<RotateCw className="size-4" />}>
            Повторить
          </Button>
        </div>
      ) : (
        <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {stats.map((s) => (
            <div key={s.label} className="panel p-5">
              <dt className="text-sm text-muted">{s.label}</dt>
              <dd className="mt-2 font-mono text-3xl">
                {data ? (s.value ?? 0) : <span className="inline-block h-8 w-10 animate-pulse rounded bg-surface-2" aria-label="Загружаем" />}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <section className="panel p-6" aria-labelledby="pipeline-title">
        <h2 id="pipeline-title" className="font-semibold">
          Как появится задание
        </h2>
        <ol className="mt-5 flex flex-wrap items-center gap-2 font-mono text-[13px]">
          {STEPS.map((step, i) => (
            <li key={step} className="flex items-center gap-2">
              <span className="rounded-md border border-line-strong bg-surface-2 px-3 py-1.5">
                <span className="text-faint">{String(i + 1).padStart(2, '0')}</span> {step}
              </span>
              {i < STEPS.length - 1 && <span className="text-faint" aria-hidden>→</span>}
            </li>
          ))}
        </ol>
        <p className="mt-4 text-sm text-muted">
          Генерация с Claude откроется на этапе 4. До этого задания можно будет создавать вручную (этап 1).
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <ButtonLink to="/workshop/generate" variant="secondary" icon={<Wand2 className="size-4" />}>
            Генерация
          </ButtonLink>
          <ButtonLink to="/workshop/system" variant="ghost" icon={<ArrowUpRight className="size-4" />}>
            Состояние системы
          </ButtonLink>
        </div>
      </section>
    </div>
  )
}
