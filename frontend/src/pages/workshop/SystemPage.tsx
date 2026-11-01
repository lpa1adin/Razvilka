import { ExternalLink } from 'lucide-react'

import { GRAFANA_URL } from '@/app/nav'
import { WORKER_LABELS, useSystemStatus } from '@/features/system/useSystemStatus'

const ROLE: Record<string, string> = {
  agent: 'Claude: план и черновики курсов в Мастерской',
  chat: 'Claude: ответы наставника в чате',
  review: 'Claude: независимый Ревьюер кода',
  collector: 'Импорт теории из белого списка (этап 1)',
  runner: 'Автотесты сданных проектов, без интернета (этап 2)',
}

function ago(iso: string | null) {
  if (!iso) return 'ещё не запускался'
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  return seconds < 60 ? `пульс ${seconds} с назад` : `пульс ${Math.round(seconds / 60)} мин назад`
}

export function SystemPage() {
  const status = useSystemStatus()

  return (
    <div className="rise-in flex flex-col gap-8">
      <header>
        <p className="eyebrow text-ai">Мастерская</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Система</h1>
        <p className="mt-3 max-w-2xl text-muted">
          Платформа — модульный монолит: один код, несколько процессов в Docker. Здесь видно, какие из них живы.
        </p>
      </header>

      <section aria-labelledby="services-title" className="panel overflow-hidden">
        <h2 id="services-title" className="border-b border-line px-5 py-4 font-semibold">
          Процессы
        </h2>
        <ul className="divide-y divide-line">
          <Row name="API" role="HTTP для интерфейса, вход и права" ok={status !== 'down' && status !== null} note={status === 'down' ? 'не отвечает' : 'отвечает'} />
          {status && status !== 'down'
            ? status.workers.map((w) => <Row key={w.name} name={WORKER_LABELS[w.name]} role={ROLE[w.name]} ok={w.alive} note={ago(w.seen_at)} />)
            : null}
        </ul>
      </section>

      <section aria-labelledby="monitoring-title" className="panel p-5">
        <h2 id="monitoring-title" className="font-semibold">
          Мониторинг
        </h2>
        <p className="mt-2 text-sm text-muted">
          Prometheus собирает метрики API и воркеров, Grafana показывает их на дашборде «Развилка — сервисы».
        </p>
        <a
          href={GRAFANA_URL}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex items-center gap-2 text-accent underline-offset-4 hover:underline"
        >
          Открыть Grafana <ExternalLink className="size-4" aria-hidden />
        </a>
      </section>
    </div>
  )
}

function Row({ name, role, ok, note }: { name: string; role: string; ok: boolean; note: string }) {
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-4">
      <span className={`size-2.5 rounded-full ${ok ? 'bg-accent shadow-[0_0_10px_var(--accent)]' : 'bg-danger'}`} aria-hidden />
      <span className="min-w-[180px] font-medium">{name}</span>
      <span className="flex-1 text-sm text-muted">{role}</span>
      <span className={`font-mono text-xs ${ok ? 'text-muted' : 'text-danger'}`}>
        {ok ? '● работает' : '● не работает'} · {note}
      </span>
    </li>
  )
}
