import { ArrowDown, ArrowUp, BookOpen, Plus, SquareTerminal, Trash2, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { inputClass, TextArea, TextField } from '@/components/ui/Field'
import { FragmentPicker } from '@/features/courses/FragmentPicker'

import type { Plan, PlanLesson, TaskKind } from './api'

type Props = {
  /** путь «напиши заново сам»: у этапов развилки вместо задания и теста */
  path?: boolean
  plan: Plan
  onChange: (plan: Plan) => void
  fragments: Record<string, string>
  onFragmentTitle: (id: number, title: string) => void
}

const KIND_LABEL: Record<TaskKind, string> = { web: 'веб', python: 'Python', sql: 'SQL' }

function move<T>(list: T[], index: number, delta: number): T[] {
  const next = [...list]
  const target = index + delta
  if (target < 0 || target >= next.length) return list
  ;[next[index], next[target]] = [next[target], next[index]]
  return next
}

/** План от наставника: админ правит формулировки, переставляет и удаляет уроки, меняет статьи. */
export function PlanEditor({ plan, onChange, fragments, onFragmentTitle, path }: Props) {
  const [picking, setPicking] = useState<{ m: number; l: number } | null>(null)

  const setLesson = (m: number, l: number, patch: Partial<PlanLesson>) =>
    onChange({
      ...plan,
      modules: plan.modules.map((mod, mi) => (mi !== m ? mod : { ...mod, lessons: mod.lessons.map((les, li) => (li !== l ? les : { ...les, ...patch })) })),
    })
  const setLessons = (m: number, lessons: PlanLesson[]) =>
    onChange({ ...plan, modules: plan.modules.map((mod, mi) => (mi === m ? { ...mod, lessons } : mod)) })

  const pickedLesson = picking ? plan.modules[picking.m].lessons[picking.l] : null

  return (
    <div className="flex flex-col gap-5">
      {path && !!plan.roles?.length && (
        <details className="rounded-lg border border-line p-3 text-sm">
          <summary className="cursor-pointer font-medium">Роли частей проекта ({plan.roles.length}) — увидит ученик на карте</summary>
          <dl className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-[200px_1fr]">
            {plan.roles.map((r) => (
              <div key={r.path} className="contents">
                <dt className="font-mono text-xs text-accent">{r.path}</dt>
                <dd className="text-muted">{r.role}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
      <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <TextField label="Название" value={plan.title} onChange={(e) => onChange({ ...plan, title: e.target.value })} />
        <TextArea label="Описание для ученика" rows={2} value={plan.description} onChange={(e) => onChange({ ...plan, description: e.target.value })} className="[&_textarea]:min-h-10" />
      </div>

      <ol className="flex flex-col gap-4">
        {plan.modules.map((module, m) => (
          <li key={module.id || m} className="panel flex flex-col gap-3 p-4">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-faint">модуль {m + 1}</span>
              <input
                aria-label={`Название модуля ${m + 1}`}
                className={`${inputClass} h-9 flex-1 font-medium`}
                value={module.title}
                onChange={(e) => onChange({ ...plan, modules: plan.modules.map((x, i) => (i === m ? { ...x, title: e.target.value } : x)) })}
              />
              <IconButton label="Модуль выше" onClick={() => onChange({ ...plan, modules: move(plan.modules, m, -1) })} disabled={m === 0}>
                <ArrowUp className="size-4" />
              </IconButton>
              <IconButton label="Модуль ниже" onClick={() => onChange({ ...plan, modules: move(plan.modules, m, 1) })} disabled={m === plan.modules.length - 1}>
                <ArrowDown className="size-4" />
              </IconButton>
              <IconButton label="Удалить модуль" danger onClick={() => onChange({ ...plan, modules: plan.modules.filter((_, i) => i !== m) })} disabled={plan.modules.length === 1}>
                <Trash2 className="size-4" />
              </IconButton>
            </div>

            <ol className="flex flex-col gap-3">
              {module.lessons.map((lesson, l) => (
                <li key={lesson.id || l} className="flex flex-col gap-3 rounded-lg border border-line bg-bg/40 p-3">
                  <div className="flex items-start gap-2">
                    <span className="mt-2.5 w-14 shrink-0 font-mono text-xs text-faint">урок {l + 1}</span>
                    <div className="flex min-w-0 flex-1 flex-col gap-2">
                      <input aria-label="Название урока" className={`${inputClass} h-9 font-medium`} value={lesson.title} onChange={(e) => setLesson(m, l, { title: e.target.value })} />
                      <textarea aria-label="Цель урока" className={`${inputClass} min-h-14 py-2 text-sm`} value={lesson.goal} onChange={(e) => setLesson(m, l, { goal: e.target.value })} />
                    </div>
                    <div className="flex flex-col">
                      <IconButton label="Урок выше" onClick={() => setLessons(m, move(module.lessons, l, -1))} disabled={l === 0}>
                        <ArrowUp className="size-4" />
                      </IconButton>
                      <IconButton label="Урок ниже" onClick={() => setLessons(m, move(module.lessons, l, 1))} disabled={l === module.lessons.length - 1}>
                        <ArrowDown className="size-4" />
                      </IconButton>
                      <IconButton label="Удалить урок" danger onClick={() => setLessons(m, module.lessons.filter((_, i) => i !== l))} disabled={module.lessons.length === 1}>
                        <Trash2 className="size-4" />
                      </IconButton>
                    </div>
                  </div>

                  <div className="flex flex-col gap-2 sm:pl-16">
                    {lesson.files.length > 0 && <p className="font-mono text-xs text-faint">файлы: {lesson.files.join(', ')}</p>}
                    <div className="flex flex-wrap items-center gap-1.5">
                      <BookOpen className="size-4 text-muted" aria-hidden />
                      {lesson.fragment_ids.map((f) => (
                        <span key={f} className="inline-flex max-w-full items-center gap-1 rounded-full border border-line bg-surface-2/60 py-0.5 pl-2.5 pr-1 text-xs">
                          <span className="truncate">{fragments[String(f)] ?? `статья №${f}`}</span>
                          <button type="button" onClick={() => setLesson(m, l, { fragment_ids: lesson.fragment_ids.filter((x) => x !== f) })} className="grid size-5 place-items-center rounded-full text-faint hover:text-danger" aria-label="Убрать статью">
                            <X className="size-3" />
                          </button>
                        </span>
                      ))}
                      {lesson.fragment_ids.length === 0 && <span className="text-xs text-danger">нет статей — урок без теории не опубликовать</span>}
                      <button type="button" onClick={() => setPicking({ m, l })} className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs text-accent hover:bg-accent-soft">
                        <Plus className="size-3" aria-hidden /> статья
                      </button>
                    </div>
                    {path ? (
                      <div className="flex flex-col gap-1.5">
                        {(lesson.forks ?? []).map((f, fi) => (
                          <div key={fi} className="flex gap-2">
                            <input
                              aria-label="Развилка этапа"
                              className={`${inputClass} h-8 flex-1 text-sm`}
                              value={f.question}
                              onChange={(e) => setLesson(m, l, { forks: (lesson.forks ?? []).map((x, xi) => (xi === fi ? { ...x, question: e.target.value } : x)) })}
                            />
                            <button type="button" onClick={() => setLesson(m, l, { forks: (lesson.forks ?? []).filter((_, xi) => xi !== fi) })} className="grid size-8 place-items-center rounded-md text-muted hover:text-danger" aria-label="Убрать развилку">
                              <X className="size-4" />
                            </button>
                          </div>
                        ))}
                        {(lesson.forks ?? []).length < 3 && (
                          <button type="button" onClick={() => setLesson(m, l, { forks: [...(lesson.forks ?? []), { question: '', context: '' }] })} className="inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-xs text-ai hover:bg-ai-soft">
                            <Plus className="size-3" aria-hidden /> развилка
                          </button>
                        )}
                      </div>
                    ) : (
                    <div className="flex flex-wrap items-start gap-3">
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={!!lesson.practice}
                          onChange={(e) => setLesson(m, l, { practice: e.target.checked ? { kind: 'web', idea: '' } : null })}
                          className="accent-[var(--accent)]"
                        />
                        <SquareTerminal className="size-4 text-muted" aria-hidden /> задание
                      </label>
                      {lesson.practice && (
                        <>
                          <select
                            aria-label="Вид задания"
                            className={`${inputClass} h-8 !w-28 text-sm`}
                            value={lesson.practice.kind}
                            onChange={(e) => setLesson(m, l, { practice: { ...lesson.practice!, kind: e.target.value as TaskKind } })}
                          >
                            {(Object.keys(KIND_LABEL) as TaskKind[]).map((k) => (
                              <option key={k} value={k}>
                                {KIND_LABEL[k]}
                              </option>
                            ))}
                          </select>
                          <input
                            aria-label="Идея задания"
                            className={`${inputClass} h-8 !w-auto min-w-[220px] flex-1 text-sm`}
                            value={lesson.practice.idea}
                            placeholder="Что ученик сделает руками"
                            onChange={(e) => setLesson(m, l, { practice: { ...lesson.practice!, idea: e.target.value } })}
                          />
                        </>
                      )}
                      <label className="flex items-center gap-2 text-sm">
                        вопросов
                        <input
                          type="number"
                          min={0}
                          max={10}
                          aria-label="Сколько вопросов теста"
                          className={`${inputClass} h-8 !w-16 text-sm`}
                          value={lesson.quiz}
                          onChange={(e) => setLesson(m, l, { quiz: Math.max(0, Math.min(10, Number(e.target.value) || 0)) })}
                        />
                      </label>
                    </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            <button
              type="button"
              onClick={() => setLessons(m, [...module.lessons, { id: '', title: path ? 'Новый этап' : 'Новый урок', goal: '', files: [], fragment_ids: [], practice: null, quiz: 0, forks: [] }])}
              className="inline-flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-sm text-accent hover:bg-accent-soft"
            >
              <Plus className="size-4" aria-hidden /> Урок
            </button>
          </li>
        ))}
      </ol>
      <button
        type="button"
        onClick={() => onChange({ ...plan, modules: [...plan.modules, { id: '', title: 'Новый модуль', lessons: [{ id: '', title: path ? 'Новый этап' : 'Новый урок', goal: '', files: [], fragment_ids: [], practice: null, quiz: 0, forks: [] }] }] })}
        className="inline-flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-sm text-accent hover:bg-accent-soft"
      >
        <Plus className="size-4" aria-hidden /> Модуль
      </button>

      <FragmentPicker
        open={picking !== null}
        onClose={() => setPicking(null)}
        taken={new Set(pickedLesson?.fragment_ids ?? [])}
        onPick={(f) => {
          if (!picking || !pickedLesson) return
          onFragmentTitle(f.id, `${f.title} · ${f.source.title}`)
          setLesson(picking.m, picking.l, { fragment_ids: [...pickedLesson.fragment_ids, f.id] })
          setPicking(null)
        }}
      />
    </div>
  )
}

function IconButton({ label, onClick, disabled, danger, children }: { label: string; onClick: () => void; disabled?: boolean; danger?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={`grid size-8 shrink-0 place-items-center rounded-md text-muted hover:bg-surface-2 disabled:opacity-30 ${danger ? 'hover:text-danger' : 'hover:text-text'}`}
    >
      {children}
    </button>
  )
}
