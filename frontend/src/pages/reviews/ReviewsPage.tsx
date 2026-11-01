import { ArrowLeft, ClipboardCheck, GitFork, ScanSearch, SquareTerminal } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'

import { ButtonLink } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { Badge, ErrorBlock, PageHeader, Skeleton } from '@/components/ui/States'
import { assessApi } from '@/features/assess/api'
import { SubmissionBadge } from '@/features/assess/SubmissionBadge'
import { pollReview, reviewApi, SEVERITY, type Review } from '@/features/review/api'
import { ReviewReport } from '@/features/review/ReviewReport'
import { useApi } from '@/lib/useApi'

const when = (iso: string) => new Date(iso).toLocaleString('ru-RU', { dateStyle: 'medium', timeStyle: 'short' })

export function ReviewsPage() {
  const { data, error, loading, reload } = useApi(() => reviewApi.mine(), [])
  const subs = useApi(() => assessApi.submissions(), [])

  return (
    <div className="rise-in flex flex-col gap-8">
      <PageHeader
        eyebrow="Учёба"
        title="Проверки"
        text="Сдачи практикумов с оценкой Оценщика и отчёты независимого Ревьюера по коду из песочницы."
      />
      <section aria-labelledby="subs-title" className="flex flex-col gap-3">
        <h2 id="subs-title" className="text-lg font-semibold">
          Сдачи
        </h2>
        {subs.error ? (
          <ErrorBlock message={subs.error.message} onRetry={subs.reload} />
        ) : !subs.data ? (
          <Skeleton lines={2} />
        ) : subs.data.length === 0 ? (
          <p className="text-sm text-muted">
            Сдач пока нет. <Link to="/practice?tab=assignments" className="text-accent hover:underline">Практикумы</Link> — проект и развилки, которые Оценщик сверит с кодом.
          </p>
        ) : (
          <ul className="panel divide-y divide-line overflow-hidden">
            {subs.data.map((s) => (
              <li key={s.id}>
                <Link to={`/reviews/submissions/${s.id}`} className="group flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4 transition-colors hover:bg-surface-2/50">
                  <GitFork className="size-5 shrink-0 text-muted" aria-hidden />
                  <span className="min-w-[200px] flex-1">
                    <span className="block font-medium group-hover:text-accent">{s.assignment_title}</span>
                    <span className="text-xs text-faint">
                      попытка {s.attempt} · {when(s.created_at)}
                    </span>
                  </span>
                  <SubmissionBadge s={s} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <h2 className="-mb-4 text-lg font-semibold">Ревью кода</h2>
      {error ? (
        <ErrorBlock message={error.message} onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton lines={4} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={<ScanSearch className="size-5" />}
          title="Ревью пока не было"
          text="Откройте задание в Практике и нажмите «Ревью кода» — отчёт появится здесь."
          action={
            <ButtonLink to="/practice" icon={<SquareTerminal className="size-4" />}>
              К заданиям
            </ButtonLink>
          }
        />
      ) : (
        <ul className="panel divide-y divide-line overflow-hidden">
          {data.map((r) => (
            <li key={r.id}>
              <Link to={`/reviews/${r.id}`} className="group flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4 transition-colors hover:bg-surface-2/50">
                <ClipboardCheck className="size-5 shrink-0 text-muted" aria-hidden />
                <span className="min-w-[200px] flex-1">
                  <span className="block font-medium group-hover:text-accent">{r.title}</span>
                  <span className="text-xs text-faint">{when(r.created_at)}</span>
                </span>
                {r.status !== 'done' ? (
                  <Badge tone={r.status === 'failed' ? 'danger' : 'ai'}>{r.status === 'failed' ? 'не удалось' : 'идёт'}</Badge>
                ) : r.verdict === 'pass' ? (
                  <Badge tone="accent">{r.counts.minor ? `мелочи · ${r.counts.minor}` : 'без замечаний'}</Badge>
                ) : (
                  (['blocker', 'major', 'minor'] as const).map((s) =>
                    r.counts[s] ? (
                      <Badge key={s} tone={SEVERITY[s].tone}>
                        {s} · {r.counts[s]}
                      </Badge>
                    ) : null,
                  )
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ReviewDetailPage() {
  const { id = '' } = useParams()
  const [review, setReview] = useState<Review | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setReview(null)
    let stop: (() => void) | undefined
    reviewApi.get(Number(id)).then(
      (r) => {
        setReview(r)
        if (r.status === 'queued' || r.status === 'running') stop = pollReview(r.id, setReview)
      },
      (e) => setError(e.message),
    )
    return () => stop?.()
  }, [id])

  if (error) return <ErrorBlock message={error} />
  if (!review) return <Skeleton lines={5} />

  return (
    <div className="rise-in mx-auto flex max-w-3xl flex-col gap-6">
      <Link to="/reviews" className="inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4" aria-hidden /> Все проверки
      </Link>
      <header>
        <p className="eyebrow">Ревью кода · {when(review.created_at)}</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{review.title}</h1>
        {review.task_slug && (
          <Link to={`/practice/${review.task_slug}`} className="mt-2 inline-flex items-center gap-1.5 text-sm text-accent hover:underline">
            <SquareTerminal className="size-4" aria-hidden /> Открыть задание
          </Link>
        )}
      </header>
      <section className="panel p-5">
        <ReviewReport review={review} withCode />
      </section>
    </div>
  )
}
