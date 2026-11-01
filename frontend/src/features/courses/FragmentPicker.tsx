import { Check, Plus, Search } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Dialog } from '@/components/ui/Dialog'
import { inputClass } from '@/components/ui/Field'
import { ErrorBlock, Skeleton } from '@/components/ui/States'
import { libraryApi, type FragmentBrief } from '@/features/library/api'
import { Snippet, SourceBadge } from '@/features/library/FragmentView'
import { useApi } from '@/lib/useApi'

type Props = { open: boolean; onClose: () => void; onPick: (fragment: FragmentBrief) => void; taken: Set<number> }

/** Выбор статьи из библиотеки для блока теории. */
export function FragmentPicker({ open, onClose, onPick, taken }: Props) {
  const [input, setInput] = useState('')
  const [q, setQ] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => setQ(input), 300)
    return () => window.clearTimeout(timer)
  }, [input])

  const results = useApi(() => (open ? libraryApi.search({ q, limit: 30 }) : Promise.resolve(null)), [q, open])

  return (
    <Dialog open={open} onClose={onClose} title="Статья из библиотеки" wide>
      <label className="relative block">
        <span className="sr-only">Поиск статьи</span>
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" aria-hidden />
        <input type="search" value={input} onChange={(e) => setInput(e.target.value)} placeholder="flexbox, семантика, массивы…" className={`${inputClass} h-11 pl-10`} data-autofocus />
      </label>
      <div className="mt-4">
        {results.error ? (
          <ErrorBlock message={results.error.message} onRetry={results.reload} />
        ) : results.loading || !results.data ? (
          <Skeleton lines={4} />
        ) : results.data.items.length === 0 ? (
          <p className="py-6 text-center text-muted">Ничего не нашлось. Попробуйте другое слово.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {results.data.items.map((item) => {
              const already = taken.has(item.id)
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    disabled={already}
                    onClick={() => onPick(item)}
                    className="flex w-full items-start gap-3 rounded-lg border border-line p-3 text-left transition-colors hover:border-accent/50 disabled:opacity-50"
                  >
                    <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-surface-2 text-muted">
                      {already ? <Check className="size-4" aria-hidden /> : <Plus className="size-4" aria-hidden />}
                    </span>
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{item.title}</span>
                        <SourceBadge fragment={item} />
                      </span>
                      {item.section && <span className="block text-xs text-faint">{item.section}</span>}
                      {(item.snippet || item.excerpt) && (
                        <span className="mt-1 line-clamp-2 block text-sm text-muted">{item.snippet ? <Snippet text={item.snippet} /> : item.excerpt}</span>
                      )}
                      {already && <span className="mt-1 block text-xs text-faint">Уже есть в этом уроке</span>}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </Dialog>
  )
}
