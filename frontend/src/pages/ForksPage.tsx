import { Download, GitFork, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router'

import { ButtonLink } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { Badge, ErrorBlock, PageHeader, Skeleton } from '@/components/ui/States'
import { assessApi } from '@/features/assess/api'
import { useApi } from '@/lib/useApi'

export function ForksPage() {
  const { data, error, loading, reload } = useApi(() => assessApi.journal(), [])

  return (
    <div className="rise-in flex flex-col gap-8">
      <PageHeader
        eyebrow="Учёба"
        title="Развилки"
        text="Журнал ваших решений из оценённых сдач: вопрос, выбор, обоснование, расхождения с кодом и как это решено в эталоне. Можно выгрузить в docs/DECISIONS.md своего проекта."
        actions={
          data?.length ? (
            <a href="/api/forks/export.md" download="DECISIONS.md" className="inline-flex h-10 items-center gap-2 rounded-md border border-line-strong bg-surface-2/60 px-4 text-[15px] font-medium transition-colors hover:border-accent/60 hover:text-accent">
              <Download className="size-4" aria-hidden /> DECISIONS.md
            </a>
          ) : undefined
        }
      />
      {error ? (
        <ErrorBlock message={error.message} onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton lines={4} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={<GitFork className="size-5" />}
          title="Решений пока нет"
          text="Развилки появляются, когда вы сдаёте практикум и Оценщик его проверит."
          action={<ButtonLink to="/practice?tab=assignments">К практикумам</ButtonLink>}
        />
      ) : (
        <ol className="flex flex-col gap-4">
          {data.map((e) => (
            <li key={`${e.submission_id}-${e.fork_id}`} className="panel flex flex-col gap-3 p-5">
              <div className="flex flex-wrap items-center gap-2 text-xs text-faint">
                <Link to={`/reviews/submissions/${e.submission_id}`} className="hover:text-accent">
                  {e.assignment} · попытка {e.attempt}
                </Link>
                <span>· {new Date(e.date).toLocaleDateString('ru-RU')}</span>
                <span className="flex-1" />
                {e.mismatches.length > 0 && (
                  <Badge tone="danger">
                    <TriangleAlert className="size-3" aria-hidden /> сказал ≠ сделал
                  </Badge>
                )}
                {e.score !== null && <Badge tone={e.passed ? 'accent' : 'muted'}>{e.score.toFixed(1)} из 5</Badge>}
              </div>
              <h2 className="text-lg font-semibold">{e.question}</h2>
              <p>
                <span className="text-muted">Решение: </span>
                <span className="font-medium">{e.answer.choice}</span>
              </p>
              <p className="text-sm text-muted">{e.answer.reasons}</p>
              {e.mismatches.map((m, i) => (
                <p key={i} className="rounded-md border border-danger/40 bg-danger-soft/30 px-3 py-2 text-sm">
                  «{m.claim}» — а в <span className="font-mono">{m.file}:{m.line}</span>: {m.code_says}
                </p>
              ))}
              {(e.reference || e.evaluator_reference) && (
                <div className="rounded-md border border-accent/30 bg-accent-soft/40 p-3 text-sm">
                  <p className="font-medium text-accent">Как в эталоне</p>
                  <p className="mt-1">{e.reference || e.evaluator_reference}</p>
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
