import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { inputClass, TextArea, TextField } from '@/components/ui/Field'
import { Badge, ErrorBlock, Skeleton } from '@/components/ui/States'
import { ApiError } from '@/lib/api'
import { useApi } from '@/lib/useApi'

import { assessApi, type AssignmentAdmin, type Criterion, type Reference } from './api'
import { SubmissionBadge } from './SubmissionBadge'

const message = (e: unknown) => (e instanceof ApiError ? e.message : 'Не удалось сохранить')

// ---------- Рубрика ----------

export function RubricTab() {
  const { data, error, reload, setData } = useApi(() => assessApi.rubric(), [])
  const [criteria, setCriteria] = useState<Criterion[]>([])
  const [penalty, setPenalty] = useState(0.75)
  const [note, setNote] = useState('')
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (data) {
      setCriteria(data.criteria)
      setPenalty(data.mismatch_penalty)
    }
  }, [data])

  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (!data) return <Skeleton lines={5} />

  const set = (i: number, patch: Partial<Criterion>) => setCriteria((list) => list.map((c, j) => (j === i ? { ...c, ...patch } : c)))
  const save = async () => {
    setSaving(true)
    try {
      const saved = await assessApi.saveRubric({ criteria, mismatch_penalty: penalty, note })
      setData(saved)
      setNote('')
      setStatus({ ok: true, text: `Сохранено как версия ${saved.version}. Новые сдачи оцениваются по ней.` })
    } catch (e) {
      setStatus({ ok: false, text: message(e) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone="accent">версия {data.version}</Badge>
        <span className="text-sm text-muted">Каждый критерий — 0…5. Итог = среднее блоков «обоснование» и «реализация» минус штраф за каждое подтверждённое «сказал ≠ сделал».</span>
      </div>
      {(['reasoning', 'implementation'] as const).map((block) => (
        <div key={block} className="panel flex flex-col gap-3 p-4">
          <h3 className="font-semibold">{block === 'reasoning' ? 'Обоснование' : 'Реализация'}</h3>
          {criteria.map((c, i) =>
            c.block !== block ? null : (
              <div key={c.id} className="grid gap-2 sm:grid-cols-[48px_1fr_1.4fr]">
                <span className="mt-2 font-mono text-xs text-muted">{c.id}</span>
                <input className={`${inputClass} h-9 text-sm`} value={c.title} onChange={(e) => set(i, { title: e.target.value })} aria-label={`Название ${c.id}`} />
                <input className={`${inputClass} h-9 text-sm`} value={c.description} onChange={(e) => set(i, { description: e.target.value })} aria-label={`Пояснение ${c.id}`} />
              </div>
            ),
          )}
        </div>
      ))}
      <div className="flex flex-wrap items-end gap-3">
        <TextField label="Штраф за расхождение" type="number" step={0.25} min={0} max={5} value={penalty} onChange={(e) => setPenalty(Number(e.target.value))} className="w-48" />
        <TextField label="Что изменилось" value={note} onChange={(e) => setNote(e.target.value)} className="min-w-[240px] flex-1" />
        <Button onClick={save} loading={saving}>
          Сохранить новой версией
        </Button>
      </div>
      {status && <p className={`text-sm ${status.ok ? 'text-accent' : 'text-danger'}`}>{status.text}</p>}
    </div>
  )
}

// ---------- Эталоны ----------

export function ReferencesTab() {
  const { data, error, reload } = useApi(() => assessApi.references(), [])
  const [editing, setEditing] = useState<Reference | 'new' | null>(null)
  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (!data) return <Skeleton lines={4} />
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted">Открытые проекты с известной архитектурой (BRIEF §3.2). Оценщик сравнивает с ними решения и объясняет, «как в эталоне».</p>
        <Button onClick={() => setEditing('new')} icon={<Plus className="size-4" />}>
          Эталон
        </Button>
      </div>
      <ul className="panel divide-y divide-line overflow-hidden">
        {data.map((r) => (
          <li key={r.id} className="flex items-start gap-3 px-5 py-3">
            <span className="flex-1">
              <span className="font-medium">{r.name}</span>
              <span className="block text-xs text-faint">{r.url}</span>
              <span className="mt-1 block text-sm text-muted">{r.about}</span>
            </span>
            <button type="button" onClick={() => setEditing(r)} className="grid size-8 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-text" aria-label={`Изменить ${r.name}`}>
              <Pencil className="size-4" />
            </button>
            <button
              type="button"
              onClick={async () => {
                await assessApi.removeReference(r.id)
                reload()
              }}
              className="grid size-8 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-danger"
              aria-label={`Удалить ${r.name}`}
            >
              <Trash2 className="size-4" />
            </button>
          </li>
        ))}
      </ul>
      {editing && <ReferenceDialog initial={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} onSaved={reload} />}
    </div>
  )
}

function ReferenceDialog({ initial, onClose, onSaved }: { initial?: Reference; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ name: initial?.name ?? '', url: initial?.url ?? '', about: initial?.about ?? '' })
  const [error, setError] = useState<string | null>(null)
  const save = async () => {
    try {
      if (initial) await assessApi.saveReference(initial.id, form)
      else await assessApi.addReference(form)
      onSaved()
      onClose()
    } catch (e) {
      setError(message(e))
    }
  }
  return (
    <Dialog open onClose={onClose} title={initial ? 'Эталон' : 'Новый эталон'} footer={<Button onClick={save} disabled={form.name.trim().length < 2}>Сохранить</Button>}>
      <div className="flex flex-col gap-3">
        <TextField label="Название" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-autofocus />
        <TextField label="Ссылка" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
        <TextArea label="Что в нём показательно" rows={4} value={form.about} onChange={(e) => setForm({ ...form, about: e.target.value })} />
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Dialog>
  )
}

// ---------- Практикумы ----------

type Draft = Omit<AssignmentAdmin, 'id' | 'slug' | 'submissions'>
const BLANK: Draft = { title: '', statement: '', kind: 'any', forks: [], tests: '', reference_ids: [], threshold: 3, published: false }

export function AssignmentsTab() {
  const list = useApi(() => assessApi.adminAssignments(), [])
  const refs = useApi(() => assessApi.references(), [])
  const [editing, setEditing] = useState<AssignmentAdmin | 'new' | null>(null)
  if (list.error) return <ErrorBlock message={list.error.message} onRetry={list.reload} />
  if (!list.data) return <Skeleton lines={4} />
  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Button onClick={() => setEditing('new')} icon={<Plus className="size-4" />}>
          Практикум
        </Button>
      </div>
      <ul className="panel divide-y divide-line overflow-hidden">
        {list.data.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
            <span className="min-w-[220px] flex-1">
              <span className="font-medium">{a.title}</span>
              <span className="block text-xs text-faint">
                {a.slug} · развилок {a.forks.length} · сдач {a.submissions}
              </span>
            </span>
            <Badge tone={a.published ? 'accent' : 'ai'}>{a.published ? 'опубликован' : 'скрыт'}</Badge>
            <Button variant="ghost" onClick={() => setEditing(a)} icon={<Pencil className="size-4" />} className="h-8 px-2 text-sm">
              Изменить
            </Button>
          </li>
        ))}
      </ul>
      {editing && (
        <AssignmentDialog initial={editing === 'new' ? undefined : editing} references={refs.data ?? []} onClose={() => setEditing(null)} onSaved={list.reload} />
      )}
    </div>
  )
}

function AssignmentDialog({ initial, references, onClose, onSaved }: { initial?: AssignmentAdmin; references: Reference[]; onClose: () => void; onSaved: () => void }) {
  const [d, setD] = useState<Draft>(() => (initial ? { ...BLANK, ...initial } : BLANK))
  const [error, setError] = useState<string | null>(null)
  const setFork = (i: number, patch: Partial<Draft['forks'][number]>) => setD((x) => ({ ...x, forks: x.forks.map((f, j) => (j === i ? { ...f, ...patch } : f)) }))
  const save = async () => {
    try {
      if (initial) await assessApi.saveAssignment(initial.id, d)
      else await assessApi.createAssignment(d)
      onSaved()
      onClose()
    } catch (e) {
      setError(message(e))
    }
  }
  return (
    <Dialog open wide onClose={onClose} title={initial ? 'Практикум' : 'Новый практикум'} footer={<Button onClick={save} disabled={d.title.trim().length < 3}>Сохранить</Button>}>
      <div className="flex flex-col gap-4">
        <TextField label="Название" value={d.title} onChange={(e) => setD({ ...d, title: e.target.value })} data-autofocus />
        <TextArea label="Условие (markdown)" rows={6} value={d.statement} onChange={(e) => setD({ ...d, statement: e.target.value })} />
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Автотесты
            <select className={`${inputClass} h-10 w-48 font-normal`} value={d.kind} onChange={(e) => setD({ ...d, kind: e.target.value as Draft['kind'] })}>
              <option value="any">нет (любой стек)</option>
              <option value="python">Python (test_*)</option>
              <option value="web">веб-страница (test(...))</option>
            </select>
          </label>
          <TextField label="Зачёт от" type="number" step={0.5} min={0} max={5} value={d.threshold} onChange={(e) => setD({ ...d, threshold: Number(e.target.value) })} className="w-32" />
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input type="checkbox" checked={d.published} onChange={(e) => setD({ ...d, published: e.target.checked })} className="accent-[var(--accent)]" />
            Показывать пользователям
          </label>
        </div>
        {d.kind !== 'any' && (
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Код автотестов
            <textarea className={`${inputClass} min-h-40 py-2 font-mono text-[13px]`} value={d.tests} onChange={(e) => setD({ ...d, tests: e.target.value })} />
          </label>
        )}
        <fieldset className="flex flex-col gap-3">
          <legend className="mb-1 text-sm font-medium">Развилки</legend>
          {d.forks.map((f, i) => (
            <div key={i} className="flex flex-col gap-2 rounded-lg border border-line p-3">
              <div className="flex gap-2">
                <input className={`${inputClass} h-9 w-32 font-mono text-sm`} value={f.id} onChange={(e) => setFork(i, { id: e.target.value })} aria-label="id развилки" />
                <input className={`${inputClass} h-9 flex-1 text-sm`} placeholder="Вопрос" value={f.question} onChange={(e) => setFork(i, { question: e.target.value })} aria-label="Вопрос" />
                <button type="button" onClick={() => setD({ ...d, forks: d.forks.filter((_, j) => j !== i) })} className="grid size-9 place-items-center rounded-md text-muted hover:text-danger" aria-label="Удалить развилку">
                  <Trash2 className="size-4" />
                </button>
              </div>
              <input className={`${inputClass} h-9 text-sm`} placeholder="Контекст (масштаб, нагрузка…)" value={f.context} onChange={(e) => setFork(i, { context: e.target.value })} aria-label="Контекст" />
              <textarea className={`${inputClass} min-h-16 py-2 text-sm`} placeholder="Как в эталоне — ученик увидит после оценки" value={f.reference} onChange={(e) => setFork(i, { reference: e.target.value })} aria-label="Ответ эталона" />
            </div>
          ))}
          <button type="button" onClick={() => setD({ ...d, forks: [...d.forks, { id: `fork-${d.forks.length + 1}`, question: '', context: '', reference: '' }] })} className="inline-flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-sm text-accent hover:bg-accent-soft">
            <Plus className="size-4" aria-hidden /> Развилка
          </button>
        </fieldset>
        <fieldset className="flex flex-col gap-1.5">
          <legend className="mb-1 text-sm font-medium">Эталоны</legend>
          {references.map((r) => (
            <label key={r.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={d.reference_ids.includes(r.id)}
                onChange={(e) => setD({ ...d, reference_ids: e.target.checked ? [...d.reference_ids, r.id] : d.reference_ids.filter((x) => x !== r.id) })}
                className="accent-[var(--accent)]"
              />
              {r.name}
            </label>
          ))}
        </fieldset>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </Dialog>
  )
}

// ---------- Все сдачи ----------

export function SubmissionsTab() {
  const { data, error, reload } = useApi(() => assessApi.allSubmissions(), [])
  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (!data) return <Skeleton lines={4} />
  if (data.length === 0) return <p className="text-muted">Сдач пока нет.</p>
  return (
    <ul className="panel divide-y divide-line overflow-hidden">
      {data.map((s) => (
        <li key={s.id}>
          <Link to={`/reviews/submissions/${s.id}`} className="flex flex-wrap items-center gap-3 px-5 py-3 hover:bg-surface-2/50">
            <span className="min-w-[220px] flex-1">
              <span className="font-medium">{s.assignment_title}</span>
              <span className="block text-xs text-faint">
                №{s.id} · попытка {s.attempt} · {new Date(s.created_at).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}
              </span>
            </span>
            <SubmissionBadge s={s} />
          </Link>
        </li>
      ))}
    </ul>
  )
}
