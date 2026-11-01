import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Glider } from '@/components/ui/Glider'
import { Dialog } from '@/components/ui/Dialog'
import { inputClass, TextArea, TextField } from '@/components/ui/Field'
import { FragmentPicker } from '@/features/courses/FragmentPicker'
import { ApiError } from '@/lib/api'

import { quizAdminApi, TYPE_LABEL, type QuestionAdmin, type QuestionData, type QuestionStatus, type QuestionType, type Similar } from './api'

/** Удобная для формы модель вопроса; в формат API переводится при сохранении. */
type Draft = {
  type: QuestionType
  prompt: string
  code: string
  code_lang: string
  choices: { id: string; text: string; correct: boolean }[] // single / multiple
  steps: { id: string; text: string }[] // order — в правильном порядке
  pairs: { left: string; right: string }[] // match
  explanation: string
  fragment: { id: number; title: string } | null
  subtopic: string
  difficulty: number
  status: QuestionStatus
}

const LETTERS = 'abcdefgh'

function fromQuestion(q?: QuestionAdmin): Draft {
  if (!q) {
    return {
      type: 'single', prompt: '', code: '', code_lang: '', explanation: '', fragment: null, subtopic: '', difficulty: 2, status: 'draft',
      choices: [{ id: 'a', text: '', correct: true }, { id: 'b', text: '', correct: false }],
      steps: [{ id: 'a', text: '' }, { id: 'b', text: '' }],
      pairs: [{ left: '', right: '' }, { left: '', right: '' }],
    }
  }
  const items = q.options.items ?? []
  const correct = new Set(q.answer.correct ?? [])
  const order = q.answer.order ?? []
  return {
    type: q.type, prompt: q.prompt, code: q.code, code_lang: q.code_lang, explanation: q.explanation,
    fragment: q.fragment_id ? { id: q.fragment_id, title: q.fragment_title ?? `Статья №${q.fragment_id}` } : null,
    subtopic: q.subtopic, difficulty: q.difficulty, status: q.status,
    choices: items.map((o) => ({ ...o, correct: correct.has(o.id) })),
    steps: order.map((id) => items.find((o) => o.id === id)!).filter(Boolean),
    pairs: (q.options.left ?? []).map((l) => ({ left: l.text, right: (q.options.right ?? []).find((r) => r.id === q.answer.pairs?.[l.id])?.text ?? '' })),
  }
}

function toData(d: Draft): QuestionData {
  const base = { type: d.type, prompt: d.prompt, code: d.code, code_lang: d.code_lang, explanation: d.explanation, fragment_id: d.fragment?.id ?? null, subtopic: d.subtopic, difficulty: d.difficulty, status: d.status }
  if (d.type === 'order') return { ...base, options: { items: d.steps }, answer: { order: d.steps.map((s) => s.id) } }
  if (d.type === 'match') {
    return {
      ...base,
      options: { left: d.pairs.map((p, i) => ({ id: `l${i}`, text: p.left })), right: d.pairs.map((p, i) => ({ id: `r${i}`, text: p.right })) },
      answer: { pairs: Object.fromEntries(d.pairs.map((_, i) => [`l${i}`, `r${i}`])) },
    }
  }
  return { ...base, options: { items: d.choices.map(({ id, text }) => ({ id, text })) }, answer: { correct: d.choices.filter((c) => c.correct).map((c) => c.id) } }
}

const nextId = (used: { id: string }[]) => LETTERS.split('').find((l) => !used.some((u) => u.id === l)) ?? 'h'

type Props = { open: boolean; onClose: () => void; topicId: number; question?: QuestionAdmin; subtopics: string[]; onSaved: () => void }

export function QuestionEditor({ open, onClose, topicId, question, subtopics, onSaved }: Props) {
  const [d, setD] = useState<Draft>(() => fromQuestion(question))
  const [error, setError] = useState<string | null>(null)
  const [similar, setSimilar] = useState<Similar[]>([])
  const [saving, setSaving] = useState(false)
  const [picker, setPicker] = useState(false)

  useEffect(() => {
    if (open) {
      setD(fromQuestion(question))
      setError(null)
      setSimilar([])
    }
  }, [open, question])

  const set = (patch: Partial<Draft>) => setD((x) => ({ ...x, ...patch }))

  const save = async (force = false) => {
    setSaving(true)
    setError(null)
    try {
      const data = toData(d)
      if (question) await quizAdminApi.updateQuestion(question.id, data, force)
      else await quizAdminApi.createQuestion(topicId, data, force)
      onSaved()
      onClose()
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setSimilar((e.body as { similar?: Similar[] })?.similar ?? [])
      else setError(e instanceof Error ? e.message : 'Не удалось сохранить')
    } finally {
      setSaving(false)
    }
  }

  const rowTool = 'grid size-8 shrink-0 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-text disabled:opacity-30'

  return (
    <>
      <Dialog
        open={open}
        onClose={onClose}
        title={question ? 'Вопрос' : 'Новый вопрос'}
        wide
        footer={
          <>
            <Button variant="ghost" onClick={onClose}>
              Отмена
            </Button>
            {similar.length > 0 && (
              <Button variant="secondary" onClick={() => save(true)} loading={saving}>
                Всё равно сохранить
              </Button>
            )}
            <Button onClick={() => save(false)} loading={saving} loadingText="Сохраняем…">
              Сохранить
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-5">
          <fieldset>
            <legend className="text-sm font-medium">Вид вопроса</legend>
            <div className="relative mt-2 flex flex-wrap gap-2">
              <Glider variant="chip" />
              {(Object.keys(TYPE_LABEL) as QuestionType[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  aria-pressed={d.type === t}
                  onClick={() => set({ type: t })}
                  className={`relative z-[1] rounded-full border px-3 py-1.5 text-sm transition-colors duration-300 ${d.type === t ? 'border-transparent text-accent' : 'border-line-strong text-muted hover:text-text'}`}
                >
                  {TYPE_LABEL[t]}
                </button>
              ))}
            </div>
          </fieldset>

          <TextArea label="Вопрос" hint="Можно `код` в обратных кавычках." value={d.prompt} onChange={(e) => set({ prompt: e.target.value })} data-autofocus />
          <div className="grid gap-3 sm:grid-cols-[1fr_160px]">
            <TextArea label="Код к вопросу (необязательно)" hint="Для «найди ошибку», docker-compose, дерева файлов." value={d.code} onChange={(e) => set({ code: e.target.value })} className="[&_textarea]:font-mono [&_textarea]:text-[13px]" />
            <TextField label="Язык кода" value={d.code_lang} onChange={(e) => set({ code_lang: e.target.value })} placeholder="html, css, yaml…" />
          </div>

          {(d.type === 'single' || d.type === 'multiple') && (
            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium">Варианты · отметьте {d.type === 'single' ? 'один верный' : 'все верные'}</p>
              {d.choices.map((c, i) => (
                <div key={c.id} className="flex items-center gap-2">
                  <input
                    type={d.type === 'single' ? 'radio' : 'checkbox'}
                    name="correct"
                    checked={c.correct}
                    onChange={() => set({ choices: d.choices.map((x, j) => (d.type === 'single' ? { ...x, correct: j === i } : j === i ? { ...x, correct: !x.correct } : x)) })}
                    aria-label={`Верный: вариант ${i + 1}`}
                    className="size-4 accent-[var(--accent)]"
                  />
                  <input className={`${inputClass} h-10`} value={c.text} onChange={(e) => set({ choices: d.choices.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })} aria-label={`Вариант ${i + 1}`} />
                  <button type="button" className={rowTool} disabled={d.choices.length <= 2} onClick={() => set({ choices: d.choices.filter((_, j) => j !== i) })} aria-label={`Удалить вариант ${i + 1}`}>
                    <Trash2 className="size-4" />
                  </button>
                </div>
              ))}
              {d.choices.length < 8 && (
                <Button variant="ghost" className="-ml-3 w-fit" icon={<Plus className="size-4" />} onClick={() => set({ choices: [...d.choices, { id: nextId(d.choices), text: '', correct: false }] })}>
                  Вариант
                </Button>
              )}
            </div>
          )}

          {d.type === 'order' && (
            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium">Шаги в правильном порядке · ученику они покажутся перемешанными</p>
              {d.steps.map((s, i) => (
                <div key={s.id} className="flex items-center gap-2">
                  <span className="w-5 font-mono text-xs text-faint">{i + 1}.</span>
                  <input className={`${inputClass} h-10`} value={s.text} onChange={(e) => set({ steps: d.steps.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })} aria-label={`Шаг ${i + 1}`} />
                  <button type="button" className={rowTool} disabled={i === 0} onClick={() => set({ steps: swap(d.steps, i, i - 1) })} aria-label={`Выше: шаг ${i + 1}`}>
                    <ArrowUp className="size-4" />
                  </button>
                  <button type="button" className={rowTool} disabled={i === d.steps.length - 1} onClick={() => set({ steps: swap(d.steps, i, i + 1) })} aria-label={`Ниже: шаг ${i + 1}`}>
                    <ArrowDown className="size-4" />
                  </button>
                  <button type="button" className={rowTool} disabled={d.steps.length <= 2} onClick={() => set({ steps: d.steps.filter((_, j) => j !== i) })} aria-label={`Удалить шаг ${i + 1}`}>
                    <Trash2 className="size-4" />
                  </button>
                </div>
              ))}
              {d.steps.length < 8 && (
                <Button variant="ghost" className="-ml-3 w-fit" icon={<Plus className="size-4" />} onClick={() => set({ steps: [...d.steps, { id: nextId(d.steps), text: '' }] })}>
                  Шаг
                </Button>
              )}
            </div>
          )}

          {d.type === 'match' && (
            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium">Пары · правая колонка у ученика перемешается</p>
              {d.pairs.map((p, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input className={`${inputClass} h-10`} value={p.left} placeholder="Слева" onChange={(e) => set({ pairs: d.pairs.map((x, j) => (j === i ? { ...x, left: e.target.value } : x)) })} aria-label={`Пара ${i + 1}, слева`} />
                  <span className="text-faint" aria-hidden>
                    →
                  </span>
                  <input className={`${inputClass} h-10`} value={p.right} placeholder="Справа" onChange={(e) => set({ pairs: d.pairs.map((x, j) => (j === i ? { ...x, right: e.target.value } : x)) })} aria-label={`Пара ${i + 1}, справа`} />
                  <button type="button" className={rowTool} disabled={d.pairs.length <= 2} onClick={() => set({ pairs: d.pairs.filter((_, j) => j !== i) })} aria-label={`Удалить пару ${i + 1}`}>
                    <Trash2 className="size-4" />
                  </button>
                </div>
              ))}
              {d.pairs.length < 6 && (
                <Button variant="ghost" className="-ml-3 w-fit" icon={<Plus className="size-4" />} onClick={() => set({ pairs: [...d.pairs, { left: '', right: '' }] })}>
                  Пара
                </Button>
              )}
            </div>
          )}

          <TextArea label="Почему так" hint="Покажется ученику в разборе после теста." value={d.explanation} onChange={(e) => set({ explanation: e.target.value })} />

          <div className="flex flex-col gap-2">
            <p className="text-sm font-medium">Источник</p>
            <div className="flex flex-wrap items-center gap-3">
              <span className={d.fragment ? '' : 'text-sm text-muted'}>{d.fragment?.title ?? 'Не выбран — без источника вопрос не публикуется'}</span>
              <Button variant="ghost" onClick={() => setPicker(true)}>
                {d.fragment ? 'Заменить' : 'Выбрать статью'}
              </Button>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <TextField label="Подтема" value={d.subtopic} onChange={(e) => set({ subtopic: e.target.value })} list="quiz-subtopics" />
              <datalist id="quiz-subtopics">
                {subtopics.map((s) => (
                  <option key={s} value={s} />
                ))}
              </datalist>
            </div>
            <label className="text-sm font-medium">
              Сложность
              <select className={`${inputClass} mt-2 h-10`} value={d.difficulty} onChange={(e) => set({ difficulty: Number(e.target.value) })}>
                <option value={1}>1 — база</option>
                <option value={2}>2 — средне</option>
                <option value={3}>3 — сложно</option>
              </select>
            </label>
            <label className="text-sm font-medium">
              Статус
              <select className={`${inputClass} mt-2 h-10`} value={d.status} onChange={(e) => set({ status: e.target.value as QuestionStatus })}>
                <option value="draft">Черновик</option>
                <option value="published">Опубликован</option>
                <option value="archived">В архиве</option>
              </select>
            </label>
          </div>

          {similar.length > 0 && (
            <div role="alert" className="rounded-lg border border-ai/40 bg-ai-soft p-4 text-sm">
              <p className="font-medium text-ai">Похожие вопросы уже есть в теме:</p>
              <ul className="mt-2 flex flex-col gap-1">
                {similar.map((s) => (
                  <li key={s.id}>
                    <span className="font-mono text-xs text-faint">{Math.round(s.similarity * 100)}%</span> {s.prompt}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-muted">Переформулируйте или сохраните всё равно, если вопросы на самом деле о разном.</p>
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
        </div>
      </Dialog>
      <FragmentPicker
        open={picker}
        onClose={() => setPicker(false)}
        taken={new Set(d.fragment ? [d.fragment.id] : [])}
        onPick={(f) => {
          set({ fragment: { id: f.id, title: f.title } })
          setPicker(false)
        }}
      />
    </>
  )
}

function swap<T>(list: T[], a: number, b: number): T[] {
  const copy = [...list]
  ;[copy[a], copy[b]] = [copy[b], copy[a]]
  return copy
}
