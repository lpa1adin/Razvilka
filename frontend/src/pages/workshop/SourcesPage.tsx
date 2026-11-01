import { AlertTriangle, Check, CheckCircle2, DownloadCloud, ExternalLink, Scale, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/Button'
import { Badge, ErrorBlock, PageHeader, Skeleton } from '@/components/ui/States'
import { formatDate } from '@/features/library/FragmentView'
import { sourcesApi, type AdminSource } from '@/features/workshop/api'
import { useApi } from '@/lib/useApi'

export function SourcesPage() {
  const sources = useApi(() => sourcesApi.list(), [])
  const review = useApi(() => sourcesApi.review(), [])
  const [actionError, setActionError] = useState<string | null>(null)

  // Пока идёт импорт, обновляем статус раз в 4 секунды
  const pending = sources.data?.some((s) => s.import_pending)
  const { reload: reloadSources } = sources
  useEffect(() => {
    if (!pending) return
    const timer = window.setInterval(reloadSources, 4000)
    return () => window.clearInterval(timer)
  }, [pending, reloadSources])

  const act = async (action: () => Promise<unknown>) => {
    setActionError(null)
    try {
      await action()
      sources.reload()
      review.reload()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Не получилось')
    }
  }

  return (
    <div className="rise-in flex flex-col gap-8">
      <PageHeader
        ai
        eyebrow="Мастерская"
        title="Источники"
        text="Белый список задаётся в коде (backend/app/modules/library/sources.py). Сборщик обновляет источники раз в неделю и перед каждым импортом сверяет лицензию."
      />
      {actionError && <ErrorBlock message={actionError} />}

      {sources.error ? (
        <ErrorBlock message={sources.error.message} onRetry={sources.reload} />
      ) : !sources.data ? (
        <Skeleton lines={2} />
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {sources.data.map((source) => (
            <SourceCard key={source.slug} source={source} onImport={() => act(() => sourcesApi.startImport(source.slug))} onConfirm={() => act(() => sourcesApi.confirmLicense(source.slug))} />
          ))}
        </div>
      )}

      <section aria-labelledby="review-title" className="flex flex-col gap-4">
        <div>
          <h2 id="review-title" className="text-xl font-semibold">
            Изменилось в источниках
          </h2>
          <p className="mt-1 text-sm text-muted">Статьи, которые обновились или пропали при последнем импорте. Перечитайте уроки, где они используются, и отметьте проверенными.</p>
        </div>
        {review.error ? (
          <ErrorBlock message={review.error.message} onRetry={review.reload} />
        ) : !review.data ? (
          <Skeleton lines={2} />
        ) : review.data.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-muted">
            <CheckCircle2 className="size-4 text-accent" aria-hidden /> Проверять нечего.
          </p>
        ) : (
          <ul className="panel divide-y divide-line">
            {review.data.map((item) => (
              <li key={item.id} className="flex flex-wrap items-start gap-4 p-4">
                <div className="min-w-[240px] flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/library/${item.id}`} className="font-medium hover:text-accent">
                      {item.title}
                    </Link>
                    {item.status === 'removed' ? <Badge tone="danger">пропала из источника</Badge> : <Badge tone="ai">обновилась</Badge>}
                    <span className="text-xs text-faint">{formatDate(item.changed_at)}</span>
                  </div>
                  <p className="mt-1 text-sm text-muted">
                    {item.used_in.length
                      ? `Используется: ${item.used_in.map((u) => `«${u.course_title}» → ${u.lesson_title}${u.draft ? ' (черновик)' : ''}`).join('; ')}`
                      : 'Пока ни в одном уроке.'}
                  </p>
                </div>
                <Button variant="secondary" onClick={() => act(() => sourcesApi.markReviewed(item.id))} icon={<Check className="size-4" />}>
                  Проверено
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function SourceCard({ source, onImport, onConfirm }: { source: AdminSource; onImport: () => void; onConfirm: () => void }) {
  const last = source.runs[0]
  return (
    <article className="panel flex flex-col gap-4 p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{source.title}</h2>
          <p className="text-sm text-muted">{source.author}</p>
        </div>
        <Badge tone={source.license_mode === 'full_text' ? 'accent' : 'muted'}>{source.license_mode === 'full_text' ? 'полный текст' : 'ссылка на материал'}</Badge>
      </header>

      <p className="flex items-start gap-2 text-sm">
        <Scale className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
        <span>
          <a href={source.license_url} target="_blank" rel="noreferrer" className="font-medium underline-offset-4 hover:underline">
            {source.license_name}
          </a>
          <span className="text-muted"> — {source.license_note}</span>
        </span>
      </p>

      {source.license_status === 'needs_review' && (
        <div role="alert" className="flex flex-col gap-3 rounded-lg border border-danger/40 bg-danger-soft p-4 text-sm">
          <p className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
            Файл лицензии изменился, импорт остановлен. Прочитайте новую лицензию в репозитории и подтвердите, что условия подходят.
          </p>
          <Button variant="danger" className="w-fit" onClick={onConfirm}>
            Лицензию прочитал(а), условия подходят
          </Button>
        </div>
      )}

      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-muted">Статей</dt>
          <dd className="font-mono text-lg">{source.fragments}</dd>
        </div>
        <div>
          <dt className="text-muted">Импорт</dt>
          <dd>{formatDate(source.last_import_at)}</dd>
        </div>
        <div>
          <dt className="text-muted">Версия</dt>
          <dd className="font-mono">{source.last_commit?.slice(0, 7) ?? '—'}</dd>
        </div>
      </dl>

      {last && (
        <p className={`flex items-start gap-2 text-sm ${last.status === 'failed' ? 'text-danger' : 'text-muted'}`}>
          {last.status === 'failed' ? <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden /> : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />}
          {last.status === 'running'
            ? 'Импорт идёт…'
            : last.status === 'failed'
              ? `Последний импорт не удался: ${last.error}`
              : `Последний импорт: новых ${last.added}, изменилось ${last.changed}, пропало ${last.removed}, без изменений ${last.unchanged}.`}
        </p>
      )}

      <div className="mt-auto flex flex-wrap gap-3">
        <Button variant="secondary" onClick={onImport} loading={source.import_pending} loadingText="Импорт в очереди…" icon={<DownloadCloud className="size-4" />}>
          Импортировать сейчас
        </Button>
        <a href={source.homepage} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 px-2 text-sm text-muted hover:text-text">
          Сайт источника <ExternalLink className="size-3.5" aria-hidden />
        </a>
      </div>
    </article>
  )
}
