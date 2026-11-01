import { FolderGit2, Lightbulb } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { inputClass, TextArea, TextField } from '@/components/ui/Field'
import { Glider } from '@/components/ui/Glider'
import { ErrorBlock, Skeleton } from '@/components/ui/States'
import { ApiError } from '@/lib/api'
import { plural } from '@/lib/plural'
import { useApi } from '@/lib/useApi'

import { genApi, LEVEL_LABEL, WHAT_LABEL, type GenRequest, type GenWhat, type RequestIn } from './api'

type Props = {
  open: boolean
  onClose: () => void
  onSaved: (req: GenRequest) => void
  /** правка заявки (в том числе принятие заявки пользователя) */
  initial?: GenRequest
}

const WHAT_HINT: Record<GenWhat, string> = {
  path: 'Проект по этапам с пустой папки: развилки с ответом автора, сдача каждого этапа',
  course: 'Модули и уроки: теория из библиотеки, задания, тесты',
  task: 'Практические задания с автопроверкой, без курса',
  quiz: 'Вопросы со ссылками на источники для тестов',
}

export function RequestForm({ open, onClose, onSaved, initial }: Props) {
  const projects = useApi(() => (open ? genApi.projects() : Promise.resolve([])), [open])
  const [form, setForm] = useState<RequestIn>(() => ({
    what: initial?.what ?? 'course',
    project: initial?.project ?? '',
    focus: initial?.focus ?? '',
    topic: initial?.topic ?? '',
    level: initial?.level ?? 2,
    notes: initial?.notes ?? '',
  }))
  const [source, setSource] = useState<'project' | 'topic'>(initial && !initial.project ? 'topic' : 'project')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    const body = { ...form, project: source === 'project' ? form.project : '', focus: source === 'project' ? form.focus : '' }
    try {
      onSaved(initial ? await genApi.update(initial.id, body) : await genApi.create(body))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить заявку')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={initial ? (initial.status === 'proposed' ? 'Принять заявку' : 'Заявка') : 'Новая заявка'}
      wide
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" form="gen-request" loading={saving} disabled={source === 'project' ? !form.project : form.topic.trim().length < 3}>
            {initial?.status === 'proposed' ? 'Принять' : 'Сохранить'}
          </Button>
        </>
      }
    >
      <form id="gen-request" onSubmit={submit} className="flex flex-col gap-5">
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm font-medium">Что создать</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {(Object.keys(WHAT_LABEL) as GenWhat[]).map((w) => (
              <label key={w} className={`flex cursor-pointer flex-col gap-1 rounded-lg border p-3 transition-colors ${form.what === w ? 'border-accent bg-accent-soft' : 'border-line hover:border-line-strong'}`}>
                <span className="flex items-center gap-2 font-medium">
                  <input type="radio" name="what" checked={form.what === w} onChange={() => setForm({ ...form, what: w })} className="accent-[var(--accent)]" />
                  {WHAT_LABEL[w][0].toUpperCase() + WHAT_LABEL[w].slice(1)}
                </span>
                <span className="text-xs text-muted">{WHAT_HINT[w]}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="flex flex-col gap-3">
          <div role="tablist" aria-label="Источник" className="relative flex w-fit rounded-md border border-line p-0.5 text-sm">
            <Glider />
            {(
              [
                ['project', 'Мой проект', FolderGit2],
                ['topic', 'Тема без проекта', Lightbulb],
              ] as const
            ).map(([key, label, Icon]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={source === key}
                onClick={() => setSource(key)}
                className={`relative z-[1] inline-flex items-center gap-2 rounded-[5px] px-3 py-1.5 transition-colors duration-300 ${source === key ? 'text-text' : 'text-muted hover:text-text'}`}
              >
                <Icon className="size-4" aria-hidden /> {label}
              </button>
            ))}
          </div>

          {source === 'project' ? (
            projects.error ? (
              <ErrorBlock message={projects.error.message} onRetry={projects.reload} />
            ) : !projects.data ? (
              <Skeleton lines={2} />
            ) : projects.data.length === 0 ? (
              <p className="text-sm text-muted">Папка с проектами не подключена (том /projects в docker-compose).</p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-[1.2fr_1fr]">
                <label className="flex flex-col gap-2 text-sm font-medium">
                  Проект (только чтение)
                  <select className={`${inputClass} h-10 font-normal`} value={form.project} onChange={(e) => setForm({ ...form, project: e.target.value })}>
                    <option value="">Выберите папку…</option>
                    {projects.data.map((p) => (
                      <option key={p.name} value={p.name}>
                        {p.name} — {p.files} {plural(p.files, 'файл', 'файла', 'файлов')}{p.languages.length ? `, ${p.languages.join(', ')}` : ''}
                      </option>
                    ))}
                  </select>
                </label>
                <TextField
                  label="Часть проекта"
                  placeholder="например, src/components"
                  value={form.focus}
                  onChange={(e) => setForm({ ...form, focus: e.target.value })}
                  hint="Необязательно: папка внутри проекта"
                />
              </div>
            )
          ) : null}
          <TextField
            label={source === 'project' ? 'Тема (необязательно)' : 'Тема'}
            placeholder="например, «Адаптивная вёрстка на flexbox»"
            value={form.topic}
            onChange={(e) => setForm({ ...form, topic: e.target.value })}
          />
        </div>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm font-medium">Уровень ученика</legend>
          <div className="relative flex flex-wrap gap-2">
            <Glider variant="chip" />
            {[1, 2, 3].map((l) => (
              <label key={l} data-active={form.level === l} className={`relative z-[1] cursor-pointer rounded-full border px-3 py-1.5 text-sm transition-colors duration-300 ${form.level === l ? 'border-transparent text-text' : 'border-line text-muted hover:text-text'}`}>
                <input type="radio" name="level" className="sr-only" checked={form.level === l} onChange={() => setForm({ ...form, level: l })} />
                {LEVEL_LABEL[l]}
              </label>
            ))}
          </div>
        </fieldset>

        <TextArea
          label="Пожелания наставнику"
          rows={3}
          placeholder="Что важно: акцент на адаптиве, 3–4 урока, без JavaScript…"
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
        />
        {error && <ErrorBlock message={error} />}
      </form>
    </Dialog>
  )
}
