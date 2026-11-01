import { ArrowLeft, LoaderCircle, Pencil, Plus, Search, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router'

import { Button } from '@/components/ui/Button'
import { inputClass, TextArea, TextField } from '@/components/ui/Field'
import { Badge, ErrorBlock, Skeleton } from '@/components/ui/States'
import { BANK_SIZE, quizAdminApi, TEST_SIZE, TYPE_LABEL, type QuestionAdmin, type QuestionStatus, type TopupState } from '@/features/quiz/api'
import { QuestionEditor } from '@/features/quiz/QuestionEditor'
import { Label } from '@/features/quiz/QuestionView'
import { useApi } from '@/lib/useApi'

const STATUS: Record<QuestionStatus, { label: string; tone: 'accent' | 'ai' | 'muted' }> = {
  published: { label: 'опубликован', tone: 'accent' },
  draft: { label: 'черновик', tone: 'ai' },
  archived: { label: 'в архиве', tone: 'muted' },
}

export function QuizTopicPage() {
  const { id = '' } = useParams()
  const topicId = Number(id)
  const topics = useApi(() => quizAdminApi.topics(), [])
  const questions = useApi(() => quizAdminApi.questions(topicId), [topicId])
  const topic = topics.data?.find((t) => t.id === topicId)

  const [form, setForm] = useState({ title: '', description: '', size: 10, published: false })
  const [savingTopic, setSavingTopic] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [status, setStatus] = useState<QuestionStatus | ''>('')
  const [editing, setEditing] = useState<QuestionAdmin | 'new' | null>(null)

  useEffect(() => {
    if (topic) setForm({ title: topic.title, description: topic.description, size: topic.size, published: topic.published })
  }, [topic])

  const subtopics = useMemo(() => [...new Set((questions.data ?? []).map((q) => q.subtopic).filter(Boolean))], [questions.data])
  const shown = (questions.data ?? []).filter(
    (q) => (!status || q.status === status) && (!filter || `${q.prompt} ${q.subtopic}`.toLowerCase().includes(filter.toLowerCase())),
  )

  if (topics.error) return <ErrorBlock message={topics.error.message} onRetry={topics.reload} />
  if (!topics.data) return <Skeleton lines={4} />
  if (!topic) return <ErrorBlock message="Тема не найдена" />

  const saveTopic = async () => {
    setSavingTopic(true)
    setNotice(null)
    try {
      await quizAdminApi.updateTopic(topicId, form)
      topics.reload()
      setNotice('Тема сохранена')
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Не удалось сохранить')
    } finally {
      setSavingTopic(false)
    }
  }

  const published = topic.counts.published ?? 0

  return (
    <div className="flex flex-col gap-6">
      <Link to="/workshop/content?tab=quiz" className="group inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4 transition-transform" aria-hidden /> Все темы тестов
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">{topic.title}</h1>

      <section className="panel flex flex-col gap-4 p-5" aria-label="Тема">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={form.published ? 'accent' : 'ai'}>{form.published ? 'тема опубликована' : 'тема скрыта'}</Badge>
          <Badge>опубликовано вопросов: {published}</Badge>
          {published < form.size && <Badge tone="ai">меньше, чем вопросов в тесте ({form.size}) — тест будет короче</Badge>}
          {published < BANK_SIZE.min && <span className="text-xs text-faint">Банк теста — {BANK_SIZE.min}–{BANK_SIZE.max} вопросов: тогда попытки почти не повторяются.</span>}
        </div>
        <div className="grid gap-4 md:grid-cols-[1fr_1.4fr_140px]">
          <TextField label="Название" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <TextArea label="Описание" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="[&_textarea]:min-h-10" />
          <TextField label="Вопросов в тесте" type="number" min={TEST_SIZE.min} max={TEST_SIZE.max} hint={`${TEST_SIZE.min}–${TEST_SIZE.max}`} value={form.size} onChange={(e) => setForm({ ...form, size: Number(e.target.value) })} />
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.published} onChange={(e) => setForm({ ...form, published: e.target.checked })} className="accent-[var(--accent)]" />
            Показывать тему пользователям
          </label>
          <Button variant="secondary" onClick={saveTopic} loading={savingTopic}>
            Сохранить тему
          </Button>
          {notice && (
            <span role="status" className="text-sm text-accent">
              {notice}
            </span>
          )}
        </div>
      </section>

      <BankTopup topicId={topicId} total={questions.data?.length ?? 0} onDone={questions.reload} />

      <section aria-labelledby="bank-title" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="bank-title" className="text-xl font-semibold">
            Банк вопросов
          </h2>
          <span className="text-sm text-muted">{questions.data?.length ?? 0}</span>
          <span className="flex-1" />
          <Button onClick={() => setEditing('new')} icon={<Plus className="size-4" />}>
            Новый вопрос
          </Button>
        </div>
        <div className="flex flex-wrap gap-3">
          <label className="relative min-w-[240px] flex-1">
            <span className="sr-only">Поиск по вопросам</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" aria-hidden />
            <input className={`${inputClass} h-10 pl-9`} placeholder="Поиск по тексту или подтеме" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </label>
          <select aria-label="Статус" className={`${inputClass} h-10 sm:w-56`} value={status} onChange={(e) => setStatus(e.target.value as QuestionStatus | '')}>
            <option value="">Все статусы</option>
            <option value="published">Опубликованные</option>
            <option value="draft">Черновики</option>
            <option value="archived">В архиве</option>
          </select>
        </div>

        {questions.error ? (
          <ErrorBlock message={questions.error.message} onRetry={questions.reload} />
        ) : !questions.data ? (
          <Skeleton lines={4} />
        ) : (
          <ul className="panel divide-y divide-line overflow-hidden">
            {shown.length === 0 && <li className="p-5 text-sm text-muted">Ничего не нашлось.</li>}
            {shown.map((q) => (
              <li key={q.id} className="group flex flex-wrap items-start gap-x-4 gap-y-2 px-5 py-3.5">
                <div className="min-w-[260px] flex-1">
                  <p className="line-clamp-2">
                    <Label text={q.prompt} />
                  </p>
                  <p className="mt-1 text-xs text-faint">
                    {q.subtopic || 'без подтемы'} · сложность {q.difficulty} · {q.fragment_title ? `источник: ${q.fragment_title}` : <span className="text-danger">нет источника</span>}
                  </p>
                </div>
                <Badge>{TYPE_LABEL[q.type]}</Badge>
                <Badge tone={STATUS[q.status].tone}>{STATUS[q.status].label}</Badge>
                <span className="flex">
                  <button type="button" onClick={() => setEditing(q)} className="grid size-8 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-text" aria-label="Редактировать вопрос">
                    <Pencil className="size-4" />
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      await quizAdminApi.removeQuestion(q.id)
                      questions.reload()
                      topics.reload()
                    }}
                    className="grid size-8 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-danger"
                    aria-label="Удалить вопрос"
                    title="Если вопрос уже был в чьих-то тестах, он уйдёт в архив, а не удалится"
                  >
                    <Trash2 className="size-4" />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <QuestionEditor
        open={editing !== null}
        onClose={() => setEditing(null)}
        topicId={topicId}
        question={editing && editing !== 'new' ? editing : undefined}
        subtopics={subtopics}
        onSaved={() => {
          questions.reload()
          topics.reload()
        }}
      />
    </div>
  )
}

/** Банк меньше 20 — наставник дописывает вопросы по статьям темы (черновиками, их проверяет админ). */
function BankTopup({ topicId, total, onDone }: { topicId: number; total: number; onDone: () => void }) {
  const [state, setState] = useState<TopupState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const targets = [20, 30, 40, 50].filter((t) => t > total)
  const [target, setTarget] = useState(targets[0] ?? BANK_SIZE.max)
  useEffect(() => {
    quizAdminApi.topupState(topicId).then(setState, () => undefined)
  }, [topicId])
  const running = !!state?.running
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(async () => {
      const next = await quizAdminApi.topupState(topicId).catch(() => null)
      if (!next) return
      setState(next)
      if (!next.running) onDone()
    }, 3000)
    return () => window.clearInterval(timer)
  }, [running, topicId, onDone])

  if (!running && targets.length === 0 && !state?.notes.length) return null
  const start = async () => {
    setError(null)
    try {
      setState(await quizAdminApi.topup(topicId, target))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось запустить')
    }
  }
  return (
    <section className="panel flex flex-col gap-3 p-5" aria-label="Размер банка">
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-[240px] flex-1 text-sm text-muted">
          <span className="font-medium text-text">В банке {total} вопросов.</span> Тест берёт {TEST_SIZE.min}–{TEST_SIZE.max} случайных, банк —{' '}
          {BANK_SIZE.min}–{BANK_SIZE.max}. Наставник допишет недостающие по статьям темы, без повторов; новые придут черновиками.
        </p>
        {running ? (
          <span role="status" className="flex items-center gap-2 text-sm text-ai">
            <LoaderCircle className="size-4 animate-spin" aria-hidden /> Наставник пишет вопросы…
          </span>
        ) : (
          targets.length > 0 && (
            <div className="flex items-center gap-2">
              <select className={`${inputClass} h-10 !w-28`} value={target} onChange={(e) => setTarget(Number(e.target.value))} aria-label="До скольких вопросов">
                {targets.map((t) => (
                  <option key={t} value={t}>
                    до {t}
                  </option>
                ))}
              </select>
              <Button onClick={start} icon={<Sparkles className="size-4" />} className="shrink-0 whitespace-nowrap">
                Дописать вопросы
              </Button>
            </div>
          )
        )}
      </div>
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {!running && state && (state.error || state.added !== null) && (
        <ul className={`flex flex-col gap-0.5 text-xs ${state.error ? 'text-danger' : 'text-muted'}`}>
          {state.error ? <li>Не получилось: {state.error}</li> : <li>Добавлено вопросов: {state.added} — проверьте и опубликуйте их в банке ниже.</li>}
          {state.notes.slice(0, 6).map((n, i) => (
            <li key={i}>• {n}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
