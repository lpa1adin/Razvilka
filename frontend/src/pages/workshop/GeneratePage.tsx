import { Bot, FolderGit2, Lightbulb, Plus, UserRound } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { Badge, ErrorBlock, PageHeader, Skeleton } from '@/components/ui/States'
import { genApi, STATUS_LABEL, WHAT_LABEL, type RequestCard } from '@/features/generation/api'
import { RequestForm } from '@/features/generation/RequestForm'
import { useApi } from '@/lib/useApi'

const FLOW = ['Заявка', 'План', 'Черновик', 'Автопроверки', 'Проверка', 'Публикация']

export function GeneratePage() {
  const navigate = useNavigate()
  const { data, error, loading, reload } = useApi(() => genApi.list(), [])
  const [creating, setCreating] = useState(false)

  const proposals = (data ?? []).filter((r) => r.status === 'proposed')
  const rest = (data ?? []).filter((r) => r.status !== 'proposed')

  return (
    <div className="rise-in flex flex-col gap-8">
      <PageHeader
        eyebrow="Мастерская"
        ai
        title="Генерация"
        text="Наставник (Claude) изучает проект и строит план, вы его правите, затем он пишет черновик. Автопроверки идут без Claude. Пользователь видит только то, что вы опубликовали."
        actions={
          <Button onClick={() => setCreating(true)} icon={<Plus className="size-4" />}>
            Новая заявка
          </Button>
        }
      />

      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-xs text-muted" aria-label="Шаги генерации">
        {FLOW.map((s, i) => (
          <li key={s} className="flex items-center gap-2">
            <span className={i === 1 || i === 2 ? 'text-ai' : ''}>{s}</span>
            {i < FLOW.length - 1 && <span className="text-faint">→</span>}
          </li>
        ))}
      </ol>

      {error ? (
        <ErrorBlock message={error.message} onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton lines={4} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={<Bot className="size-5" />}
          title="Заявок пока нет"
          text="Выберите проект из ProjectsWithClaude или тему — наставник предложит план курса, заданий или теста."
          action={
            <Button onClick={() => setCreating(true)} icon={<Plus className="size-4" />}>
              Новая заявка
            </Button>
          }
        />
      ) : (
        <>
          {proposals.length > 0 && (
            <section aria-labelledby="proposals" className="flex flex-col gap-3">
              <h2 id="proposals" className="flex items-center gap-2 text-lg font-semibold">
                Предложения пользователей <Badge tone="ai">{proposals.length}</Badge>
              </h2>
              <List items={proposals} />
            </section>
          )}
          <section aria-labelledby="all" className="flex flex-col gap-3">
            <h2 id="all" className="text-lg font-semibold">
              Заявки
            </h2>
            {rest.length ? <List items={rest} /> : <p className="text-sm text-muted">Своих заявок пока нет.</p>}
          </section>
        </>
      )}

      {creating && <RequestForm open onClose={() => setCreating(false)} onSaved={(req) => navigate(`/workshop/generate/${req.id}`)} />}
    </div>
  )
}

function List({ items }: { items: RequestCard[] }) {
  return (
    <ul className="panel divide-y divide-line overflow-hidden">
      {items.map((r) => {
        const status = r.published ? { label: 'опубликовано', tone: 'accent' as const } : STATUS_LABEL[r.status]
        return (
          <li key={r.id}>
            <Link to={`/workshop/generate/${r.id}`} className="group flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4 transition-colors hover:bg-surface-2/50">
              <span className="grid size-9 shrink-0 place-items-center rounded-md bg-surface-2 text-muted">
                {r.origin === 'user' ? <UserRound className="size-4" aria-hidden /> : r.project ? <FolderGit2 className="size-4" aria-hidden /> : <Lightbulb className="size-4" aria-hidden />}
              </span>
              <span className="min-w-[200px] flex-1">
                <span className="block font-medium group-hover:text-accent">{r.title}</span>
                <span className="text-xs text-faint">
                  №{r.id} · {WHAT_LABEL[r.what]}
                  {r.project && ` · ${r.project}`}
                  {r.origin === 'user' && r.author && ` · предложил ${r.author}`} · {new Date(r.updated_at).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}
                </span>
              </span>
              {r.busy && <span className="size-2 animate-pulse rounded-full bg-ai" aria-label="наставник работает" />}
              <Badge tone={status.tone}>{status.label}</Badge>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
