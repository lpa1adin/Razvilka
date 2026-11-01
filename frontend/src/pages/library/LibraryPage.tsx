import { Library, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { EmptyState } from '@/components/ui/EmptyState'
import { Glider } from '@/components/ui/Glider'
import { inputClass } from '@/components/ui/Field'
import { Button } from '@/components/ui/Button'
import { ErrorBlock, PageHeader, Skeleton } from '@/components/ui/States'
import { libraryApi, type FragmentBrief } from '@/features/library/api'
import { Snippet, SourceBadge } from '@/features/library/FragmentView'
import { useApi } from '@/lib/useApi'

const PAGE = 20

export function LibraryPage() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const source = params.get('source') ?? ''
  const [input, setInput] = useState(q)
  const [extra, setExtra] = useState<FragmentBrief[]>([])
  const [loadingMore, setLoadingMore] = useState(false)

  // Ищем, когда человек перестал печатать на 300 мс
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (input !== q) setParams((p) => (input ? p.set('q', input) : p.delete('q'), p), { replace: true })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [input, q, setParams])

  const sources = useApi(() => libraryApi.sources(), [])
  const results = useApi(() => libraryApi.search({ q, source, limit: PAGE }), [q, source])
  useEffect(() => setExtra([]), [q, source])

  const items = [...(results.data?.items ?? []), ...extra]
  const total = results.data?.total ?? 0

  const loadMore = async () => {
    setLoadingMore(true)
    try {
      const next = await libraryApi.search({ q, source, limit: PAGE, offset: items.length })
      setExtra((e) => [...e, ...next.items])
    } finally {
      setLoadingMore(false)
    }
  }

  const setSource = (slug: string) => setParams((p) => (slug ? p.set('source', slug) : p.delete('source'), p), { replace: true })

  return (
    <div className="rise-in flex flex-col gap-8">
      <PageHeader
        eyebrow="Учёба"
        title="Библиотека"
        text="Теория только из проверенных источников. У каждой статьи — автор, лицензия и ссылка на оригинал."
      />

      <div className="flex flex-col gap-4">
        <label className="relative block">
          <span className="sr-only">Поиск по библиотеке</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" aria-hidden />
          <input
            type="search"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Например: flexbox, замыкание, семантическая разметка"
            className={`${inputClass} h-12 pl-10 text-base`}
          />
        </label>
        <div className="relative flex flex-wrap gap-2" role="group" aria-label="Источник">
          <Glider variant="chip" />
          {[{ slug: '', title: 'Все источники' }, ...(sources.data ?? [])].map((s) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => setSource(s.slug)}
              aria-pressed={source === s.slug}
              className={`relative z-[1] rounded-full border px-3.5 py-1.5 text-sm transition-colors duration-300 ${
                source === s.slug ? 'border-transparent text-accent' : 'border-line-strong text-muted hover:border-line-strong hover:text-text'
              }`}
            >
              {s.title}
            </button>
          ))}
        </div>
      </div>

      {results.error ? (
        <ErrorBlock message={results.error.message} onRetry={results.reload} />
      ) : results.loading ? (
        <Skeleton lines={5} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Library className="size-5" />}
          title={q ? 'Ничего не нашлось' : 'Библиотека пока пуста'}
          text={
            q
              ? 'Попробуйте другое слово или уберите фильтр источника.'
              : 'Сборщик ещё не импортировал источники. Администратор может запустить импорт в Мастерской → Источники.'
          }
        />
      ) : (
        <section aria-label="Результаты">
          <p className="mb-3 text-sm text-muted" role="status">
            {q ? `Нашлось: ${total}` : `Всего статей: ${total}`}
          </p>
          <ul className="flex flex-col gap-3">
            {items.map((item) => (
              <li key={item.id}>
                <Link to={`/library/${item.id}`} className="panel group block p-4 transition-colors hover:border-accent/40 sm:p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <SourceBadge fragment={item} />
                    {item.section && <span className="text-xs text-faint">{item.section}</span>}
                  </div>
                  <h2 className="mt-2 text-lg font-semibold group-hover:text-accent">{item.title}</h2>
                  {(item.snippet || item.excerpt) && (
                    <p className="mt-1.5 line-clamp-2 text-sm text-muted">{item.snippet ? <Snippet text={item.snippet} /> : item.excerpt}</p>
                  )}
                </Link>
              </li>
            ))}
          </ul>
          {items.length < total && (
            <Button variant="secondary" className="mt-5" onClick={loadMore} loading={loadingMore} loadingText="Загружаем…">
              Показать ещё
            </Button>
          )}
        </section>
      )}
    </div>
  )
}
