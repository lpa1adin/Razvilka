import { ArrowLeft, ArrowRight, BookOpen, CheckCircle2, CircleX, ClipboardList, Flag, RotateCcw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Badge, ErrorBlock, Progress, Skeleton } from '@/components/ui/States'
import { answered, quizApi, type Attempt, type Response, type TopicCard } from '@/features/quiz/api'
import { QuestionView } from '@/features/quiz/QuestionView'
import { ApiError } from '@/lib/api'
import { useApi } from '@/lib/useApi'

export function QuizPage() {
  const { slug = '' } = useParams()
  const [params] = useSearchParams()
  const from = params.get('from')?.startsWith('/courses/') ? params.get('from') : null
  const topic = useApi(() => quizApi.topic(slug), [slug])
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Прерванный тест — продолжаем с того же места
  const activeId = topic.data?.active_attempt_id
  useEffect(() => {
    if (activeId) quizApi.attempt(activeId).then(setAttempt, () => undefined)
  }, [activeId])

  const start = async (mistakes = false) => {
    setBusy(true)
    setError(null)
    try {
      setAttempt(await quizApi.start(slug, mistakes))
      window.scrollTo({ top: 0 })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось начать тест')
    } finally {
      setBusy(false)
    }
  }

  const back = (
    <Link to={from ?? '/practice?tab=tests'} className="group inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
      <ArrowLeft className="size-4 transition-transform" aria-hidden /> {from ? 'К уроку' : 'Все тесты'}
    </Link>
  )

  if (topic.error) return <ErrorBlock message={topic.error.message} onRetry={topic.reload} />
  if (!topic.data) return <Skeleton lines={3} />

  return (
    <div className="rise-in mx-auto flex max-w-3xl flex-col gap-6">
      {back}
      {error && <ErrorBlock message={error} />}
      {attempt?.status === 'in_progress' ? (
        <Runner
          key={attempt.id}
          attempt={attempt}
          onFinished={(done) => {
            setAttempt(done)
            topic.reload()
            window.scrollTo({ top: 0 })
          }}
        />
      ) : attempt?.status === 'finished' ? (
        <Results attempt={attempt} busy={busy} onAgain={() => start(false)} onMistakes={() => start(true)} />
      ) : (
        <Intro topic={topic.data} busy={busy} onStart={() => start(false)} />
      )}
    </div>
  )
}

function Intro({ topic, busy, onStart }: { topic: TopicCard; busy: boolean; onStart: () => void }) {
  const count = Math.min(topic.size, topic.questions)
  return (
    <section className="panel flex flex-col gap-5 p-6" aria-labelledby="quiz-title">
      <div>
        <p className="eyebrow">Тест</p>
        <h1 id="quiz-title" className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
          {topic.title}
        </h1>
        {topic.description && <p className="mt-2 text-muted">{topic.description}</p>}
      </div>
      <dl className="grid gap-3 text-sm sm:grid-cols-3">
        <Stat label="Вопросов в тесте" value={count} />
        <Stat label="Ещё не видели" value={`${topic.unseen} из ${topic.questions}`} />
        <Stat label="Прошлый результат" value={topic.last_total ? `${topic.last_score} из ${topic.last_total}` : '—'} />
      </dl>
      <ul className="flex flex-col gap-1.5 text-sm text-muted">
        <li>• Вопросы подбираются из банка темы: сначала те, что вы ещё не видели.</li>
        <li>• Ответы сохраняются сразу — тест можно прервать и продолжить позже.</li>
        <li>• Правильные ответы и разбор появятся после завершения.</li>
      </ul>
      {topic.questions < topic.size && <p className="text-sm text-ai">В теме пока {topic.questions} вопросов — тест будет короче обычного.</p>}
      <Button onClick={onStart} loading={busy} loadingText="Собираем вопросы…" icon={<ClipboardList className="size-4" />} className="w-fit">
        Начать тест
      </Button>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-line p-3">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-lg">{value}</dd>
    </div>
  )
}

function Runner({ attempt, onFinished }: { attempt: Attempt; onFinished: (a: Attempt) => void }) {
  const [items, setItems] = useState(attempt.items)
  const firstOpen = Math.max(0, items.findIndex((i) => !answered(i)))
  const [index, setIndex] = useState(firstOpen)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [finishing, setFinishing] = useState(false)

  const item = items[index]
  const done = items.filter(answered).length

  const respond = useCallback(
    (response: Response) => {
      setItems((list) => list.map((it, i) => (i === index ? { ...it, response } : it)))
      setSaveError(null)
      quizApi.answer(attempt.id, items[index].position, response).catch((e) => setSaveError(e instanceof Error ? e.message : 'Ответ не сохранился'))
    },
    [attempt.id, index, items],
  )

  const finish = async () => {
    setFinishing(true)
    try {
      onFinished(await quizApi.finish(attempt.id))
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Не удалось завершить тест')
      setFinishing(false)
    }
  }

  return (
    <section className="flex flex-col gap-5" aria-label={`Тест: ${attempt.topic_title}`}>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="text-xl font-semibold">{attempt.topic_title}</h1>
          <span className="font-mono text-sm text-muted">
            вопрос {index + 1} из {items.length}
          </span>
        </div>
        {attempt.note && <p className="text-sm text-ai">{attempt.note}</p>}
        <Progress done={done} total={items.length} label="Отвечено" />
        {/* Навигация по вопросам: заполненные точки — уже отвечены */}
        <nav aria-label="Вопросы теста" className="flex flex-wrap gap-1.5">
          {items.map((it, i) => (
            <button
              key={it.position}
              type="button"
              onClick={() => setIndex(i)}
              aria-current={i === index ? 'step' : undefined}
              aria-label={`Вопрос ${i + 1}${answered(it) ? ', отвечен' : ''}`}
              className={`grid size-8 place-items-center rounded-md border font-mono text-xs transition-colors ${
                i === index ? 'border-accent text-accent' : answered(it) ? 'border-line-strong bg-surface-2 text-text' : 'border-line text-faint hover:text-text'
              }`}
            >
              {i + 1}
            </button>
          ))}
        </nav>
      </div>

      <div key={item.position} className="panel rise-in p-5 sm:p-6">
        <QuestionView item={item} onChange={respond} />
      </div>
      {saveError && (
        <p role="alert" className="text-sm text-danger">
          {saveError}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" onClick={() => setIndex((i) => i - 1)} disabled={index === 0} icon={<ArrowLeft className="size-4" />}>
          Назад
        </Button>
        <span className="flex-1" />
        {index < items.length - 1 ? (
          <Button variant="secondary" onClick={() => setIndex((i) => i + 1)}>
            Следующий <ArrowRight className="size-4" aria-hidden />
          </Button>
        ) : null}
        <Button onClick={() => (done < items.length ? setConfirming(true) : finish())} loading={finishing} loadingText="Считаем…" icon={<Flag className="size-4" />}>
          Завершить тест
        </Button>
      </div>

      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Завершить тест?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirming(false)} data-autofocus>
              Вернуться к вопросам
            </Button>
            <Button onClick={finish} loading={finishing}>
              Завершить
            </Button>
          </>
        }
      >
        <p className="text-muted">
          Без ответа: {items.length - done} из {items.length}. Такие вопросы засчитаются как ошибки и попадут в «Повторить ошибки».
        </p>
      </Dialog>
    </section>
  )
}

function Results({ attempt, busy, onAgain, onMistakes }: { attempt: Attempt; busy: boolean; onAgain: () => void; onMistakes: () => void }) {
  const [onlyMistakes, setOnlyMistakes] = useState(true)
  const wrong = attempt.items.filter((i) => !i.correct)
  const pct = attempt.total ? Math.round((attempt.score / attempt.total) * 100) : 0
  const shown = onlyMistakes ? wrong : attempt.items

  return (
    <section className="flex flex-col gap-6" aria-labelledby="result-title">
      <div className="panel flex flex-wrap items-center gap-6 p-6">
        <div
          className="grid size-24 shrink-0 place-items-center rounded-full"
          style={{ background: `conic-gradient(var(--accent) ${pct * 3.6}deg, var(--surface-2) 0)` }}
          role="img"
          aria-label={`${pct} процентов`}
        >
          <span className="grid size-[84px] place-items-center rounded-full bg-surface font-mono text-xl">{pct}%</span>
        </div>
        <div className="min-w-[200px] flex-1">
          <p className="eyebrow">{attempt.mistakes_only ? 'Работа над ошибками' : 'Результат теста'}</p>
          <h1 id="result-title" className="mt-1 text-2xl font-semibold">
            {attempt.score} из {attempt.total}
          </h1>
          <p className="mt-1 text-muted">
            {attempt.score === attempt.total ? 'Без единой ошибки.' : `Ошибок: ${wrong.length}. Ниже — разбор со ссылками на теорию.`}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          {wrong.length > 0 && (
            <Button onClick={onMistakes} loading={busy} icon={<RotateCcw className="size-4" />}>
              Повторить ошибки
            </Button>
          )}
          <Button variant="secondary" onClick={onAgain} loading={busy}>
            Новый тест
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Разбор</h2>
        <label className="flex items-center gap-2 text-sm text-muted">
          <input type="checkbox" checked={onlyMistakes} onChange={(e) => setOnlyMistakes(e.target.checked)} className="accent-[var(--accent)]" />
          только ошибки
        </label>
      </div>
      {shown.length === 0 && <p className="text-muted">Ошибок нет — показывать нечего.</p>}
      <ol className="flex flex-col gap-4">
        {shown.map((item) => (
          <li key={item.position} className={`panel flex flex-col gap-4 p-5 ${item.correct ? '' : 'border-danger/30'}`}>
            <div className="flex items-center gap-2">
              {item.correct ? <CheckCircle2 className="size-5 text-accent" aria-hidden /> : <CircleX className="size-5 text-danger" aria-hidden />}
              <span className="font-mono text-xs text-faint">вопрос {item.position}</span>
              {!item.response && <Badge tone="danger">без ответа</Badge>}
            </div>
            <QuestionView item={item} review />
            {item.explanation_html && (
              <div className="rounded-lg border border-line bg-surface-2/50 p-4 text-sm">
                <p className="font-medium">Почему так</p>
                <div className="prose-content mt-1 text-[15px] text-muted" dangerouslySetInnerHTML={{ __html: item.explanation_html }} />
              </div>
            )}
            {item.source && (
              <Link to={`/library/${item.source.fragment_id}`} className="inline-flex w-fit items-center gap-2 text-sm text-accent hover:underline">
                <BookOpen className="size-4" aria-hidden /> Теория: {item.source.title} · {item.source.source}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}
