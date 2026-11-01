import { Download, GitFork, History, Inbox, Library, Plus, Scale, ShieldCheck, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { Button } from '@/components/ui/Button'
import { inputClass, TextField } from '@/components/ui/Field'
import { Glider } from '@/components/ui/Glider'
import { Badge, ErrorBlock, PageHeader, Skeleton } from '@/components/ui/States'
import { AssignmentsTab, ReferencesTab, RubricTab, SubmissionsTab } from '@/features/assess/WorkshopTabs'
import { reviewApi, type Rule } from '@/features/review/api'
import { Sources } from '@/features/review/ReviewReport'
import { ApiError } from '@/lib/api'
import { useApi } from '@/lib/useApi'

type Tab = 'reviewer' | 'rubric' | 'references' | 'assignments' | 'submissions'
const TABS = ['reviewer', 'rubric', 'references', 'assignments', 'submissions'] as const

export function GradingPage() {
  const [params, setParams] = useSearchParams()
  const tab: Tab = (TABS as readonly string[]).includes(params.get('tab') ?? '') ? (params.get('tab') as Tab) : 'reviewer'

  return (
    <div className="rise-in flex flex-col gap-8">
      <PageHeader eyebrow="Мастерская" title="Оценивание" text="Правила Ревьюера, рубрика Оценщика, эталонные проекты, практикумы и все сдачи. Правила и рубрика хранятся версиями — каждая проверка помнит свою." />
      <div role="tablist" aria-label="Оценивание" className="relative flex gap-1 overflow-x-auto border-b border-line">
        <Glider variant="underline" />
        {(
          [
            ['reviewer', 'Правила Ревьюера', ShieldCheck],
            ['rubric', 'Рубрика Оценщика', Scale],
            ['references', 'Эталоны', Library],
            ['assignments', 'Практикумы', GitFork],
            ['submissions', 'Сдачи', Inbox],
          ] as const
        ).map(([key, label, Icon]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setParams(key === 'reviewer' ? {} : { tab: key }, { replace: true })}
            className={`relative z-[1] inline-flex shrink-0 items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-300 ${tab === key ? 'font-medium text-text' : 'text-muted hover:text-text'}`}
          >
            <Icon className="size-4" aria-hidden /> {label}
          </button>
        ))}
      </div>
      {tab === 'reviewer' && <ReviewerRules />}
      {tab === 'rubric' && <RubricTab />}
      {tab === 'references' && <ReferencesTab />}
      {tab === 'assignments' && <AssignmentsTab />}
      {tab === 'submissions' && <SubmissionsTab />}
    </div>
  )
}

function ReviewerRules() {
  const current = useApi(() => reviewApi.rules(), [])
  const versions = useApi(() => reviewApi.versions(), [])
  const [rules, setRules] = useState<Rule[]>([])
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [filter, setFilter] = useState('')

  useEffect(() => {
    if (current.data) setRules(current.data.rules)
  }, [current.data])

  const dirty = useMemo(() => JSON.stringify(rules) !== JSON.stringify(current.data?.rules ?? []), [rules, current.data])
  const groups = useMemo(() => [...new Set(rules.map((r) => r.group))], [rules])
  const enabled = rules.filter((r) => r.enabled).length

  if (current.error) return <ErrorBlock message={current.error.message} onRetry={current.reload} />
  if (!current.data) return <Skeleton lines={6} />

  const set = (i: number, patch: Partial<Rule>) => setRules((list) => list.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const addRule = (group: string) => {
    const prefix = rules.find((r) => r.group === group)?.id.split('-')[0] ?? 'NEW'
    const used = rules.filter((r) => r.id.startsWith(prefix + '-')).map((r) => Number(r.id.split('-')[1]))
    const id = `${prefix}-${String(Math.max(0, ...used) + 1).padStart(2, '0')}`
    const at = rules.map((r) => r.group).lastIndexOf(group) + 1
    setRules((list) => [...list.slice(0, at), { id, group, text: '', enabled: true }, ...list.slice(at)])
  }

  const save = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const saved = await reviewApi.saveRules(rules, note)
      current.setData(saved)
      versions.reload()
      setNote('')
      setMessage({ ok: true, text: `Сохранено как версия ${saved.version}. Новые ревью пойдут по ней, старые отчёты остаются на своей.` })
    } catch (e) {
      setMessage({ ok: false, text: e instanceof ApiError ? e.message : 'Не удалось сохранить' })
    } finally {
      setSaving(false)
    }
  }

  const shown = (r: Rule) => !filter || `${r.id} ${r.text}`.toLowerCase().includes(filter.toLowerCase())

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section className="flex flex-col gap-5" aria-label="Правила">
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone="accent">версия {current.data.version}</Badge>
          <span className="text-sm text-muted">
            включено {enabled} из {rules.length}
          </span>
          <span className="flex-1" />
          <input className={`${inputClass} h-9 !w-56`} placeholder="Найти правило" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Найти правило" />
        </div>

        {groups.map((group) => (
          <div key={group} className="panel flex flex-col gap-1 p-4">
            <h3 className="mb-2 font-semibold">{group}</h3>
            {rules.map((r, i) =>
              r.group !== group || !shown(r) ? null : (
                <div key={i} className={`flex items-start gap-3 rounded-md px-2 py-2 transition-colors ${r.enabled ? '' : 'opacity-50'}`}>
                  <input type="checkbox" checked={r.enabled} onChange={(e) => set(i, { enabled: e.target.checked })} className="mt-2 size-4 accent-[var(--accent)]" aria-label={`Правило ${r.id} включено`} />
                  <span className="mt-1.5 w-16 shrink-0 font-mono text-xs text-muted">{r.id}</span>
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <textarea
                      value={r.text}
                      onChange={(e) => set(i, { text: e.target.value })}
                      rows={Math.max(1, Math.ceil(r.text.length / 90))}
                      aria-label={`Текст правила ${r.id}`}
                      className={`${inputClass} min-h-9 resize-y py-1.5 text-sm leading-snug`}
                    />
                    <p className="px-1 text-xs text-faint">
                      {r.source ? (
                        <>
                          Источник: <Sources text={r.source} />
                        </>
                      ) : (
                        'Источник не указан — правило платформы'
                      )}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setRules((list) => list.filter((_, j) => j !== i))}
                    className="mt-1 grid size-8 shrink-0 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-danger"
                    aria-label={`Удалить правило ${r.id}`}
                  >
                    <Trash2 className="size-4" />
                  </button>
                </div>
              ),
            )}
            <button type="button" onClick={() => addRule(group)} className="mt-1 inline-flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-sm text-accent hover:bg-accent-soft">
              <Plus className="size-4" aria-hidden /> Правило
            </button>
          </div>
        ))}

        <div className="sticky bottom-0 z-10 -mx-4 flex flex-wrap items-end gap-3 border-t border-line bg-bg/90 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-lg sm:border">
          <TextField label="Что изменилось" placeholder="Например: добавил правило про шрифты" value={note} onChange={(e) => setNote(e.target.value)} className="min-w-[240px] flex-1" />
          <Button onClick={save} loading={saving} disabled={!dirty}>
            Сохранить новой версией
          </Button>
          {dirty && (
            <Button variant="ghost" onClick={() => setRules(current.data!.rules)}>
              Отменить правки
            </Button>
          )}
          {message && (
            <p role="status" className={`basis-full text-sm ${message.ok ? 'text-accent' : 'text-danger'}`}>
              {message.text}
            </p>
          )}
        </div>
      </section>

      <aside className="flex flex-col gap-4">
        <div className="panel flex flex-col gap-3 p-4">
          <h3 className="font-semibold">Агент для Claude Code</h3>
          <p className="text-sm text-muted">
            Те же правила как агент <code className="font-mono text-text">reviewer</code>: положите файл в <code className="font-mono text-text">.claude/agents/</code> проекта и
            просите «проверь изменения агентом reviewer». Ответ — тот же JSON.
          </p>
          <a href="/api/workshop/review-rules/agent.md" download="reviewer.md" className="inline-flex h-10 w-fit items-center gap-2 rounded-md border border-line-strong bg-surface-2/60 px-4 text-[15px] font-medium transition-colors hover:border-accent/60 hover:text-accent">
            <Download className="size-4" aria-hidden /> reviewer.md
          </a>
        </div>
        <div className="panel flex flex-col gap-3 p-4">
          <h3 className="flex items-center gap-2 font-semibold">
            <History className="size-4 text-muted" aria-hidden /> Версии
          </h3>
          {versions.data ? (
            <ol className="flex flex-col gap-2 text-sm">
              {versions.data.map((v) => (
                <li key={v.version} className="flex flex-col">
                  <span>
                    <span className="font-mono">v{v.version}</span> · {new Date(v.created_at).toLocaleDateString('ru-RU')}
                    {v.author && <span className="text-faint"> · {v.author}</span>}
                  </span>
                  {v.note && <span className="text-xs text-muted">{v.note}</span>}
                </li>
              ))}
            </ol>
          ) : (
            <Skeleton lines={2} />
          )}
        </div>
      </aside>
    </div>
  )
}
