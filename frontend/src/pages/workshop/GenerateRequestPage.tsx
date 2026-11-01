import {
  ArrowLeft,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  CircleX,
  ClipboardList,
  Eye,
  LoaderCircle,
  MinusCircle,
  Pause,
  Pencil,
  Play,
  RefreshCw,
  Rocket,
  Sparkles,
  Square,
  SquareTerminal,
  Trash2,
  Wand2,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { Button, ButtonLink } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { TextArea } from '@/components/ui/Field'
import { Badge, ErrorBlock, Skeleton } from '@/components/ui/States'
import { genApi, LEVEL_LABEL, STATUS_LABEL, WHAT_LABEL, type CreatedLesson, type GenRequest, type Plan, type Step } from '@/features/generation/api'
import { PlanEditor } from '@/features/generation/PlanEditor'
import { RequestForm } from '@/features/generation/RequestForm'
import { ReferenceReview } from '@/features/review/ReferenceReview'
import { ApiError } from '@/lib/api'
import { useApi } from '@/lib/useApi'

const POLL_MS = 2000
const FLOW = ['Заявка', 'План', 'Черновик', 'Автопроверки', 'Проверка', 'Публикация'] as const

function flowIndex(req: GenRequest): number {
  if (req.published) return 6
  switch (req.status) {
    case 'proposed':
    case 'new':
    case 'rejected':
      return 0
    case 'planning':
    case 'plan_ready':
      return 1
    case 'drafting':
      return req.steps.some((s) => s.key === 'checks' && s.state === 'running') ? 3 : 2
    case 'draft_ready':
      return 4
    case 'paused':
      return 2
    case 'failed':
      return req.lessons.length ? 2 : req.plan ? 1 : 0
  }
}

export function GenerateRequestPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { data: req, error, reload, setData } = useApi(() => genApi.get(Number(id)), [id])
  const [action, setAction] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

  // Пока наставник работает — обновляем экран: шаги и «что делает сейчас»
  const busy = req?.busy
  useEffect(() => {
    if (!busy) return
    const timer = window.setInterval(() => genApi.get(Number(id)).then(setData, () => undefined), POLL_MS)
    return () => window.clearInterval(timer)
  }, [busy, id, setData])

  const run = async (name: string, fn: () => Promise<GenRequest>) => {
    setAction(name)
    setActionError(null)
    try {
      setData(await fn())
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Не получилось')
    } finally {
      setAction(null)
    }
  }

  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (!req) return <Skeleton lines={5} />

  const status = req.published ? { label: 'опубликовано', tone: 'accent' as const } : STATUS_LABEL[req.status]
  const step = flowIndex(req)

  return (
    <div className="rise-in flex flex-col gap-6">
      <Link to="/workshop/generate" className="inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4" aria-hidden /> Все заявки
      </Link>

      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={status.tone}>{status.label}</Badge>
          <Badge>{WHAT_LABEL[req.what]}</Badge>
          <Badge>{LEVEL_LABEL[req.level]}</Badge>
          {req.origin === 'user' && <Badge tone="ai">от пользователя {req.author}</Badge>}
        </div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{req.plan?.title ?? (req.topic || req.project)}</h1>
        <p className="text-sm text-muted">
          №{req.id} · {req.project ? `проект ${req.project}${req.focus ? `/${req.focus}` : ''}` : 'без проекта'}
          {req.topic && req.plan && ` · тема: ${req.topic}`}
          {req.notes && ` · пожелания: ${req.notes}`}
        </p>
      </header>

      <ol className="grid grid-cols-3 gap-1.5 sm:grid-cols-6" aria-label="Шаги генерации">
        {FLOW.map((s, i) => (
          <li
            key={s}
            aria-current={i === step ? 'step' : undefined}
            className={`rounded-md border px-2 py-2 text-center text-xs font-medium ${
              i < step ? 'border-accent/40 bg-accent-soft text-accent' : i === step ? 'border-ai/50 bg-ai-soft text-ai' : 'border-line text-faint'
            }`}
          >
            {i < step && <Check className="mr-1 inline size-3" aria-hidden />}
            {s}
          </li>
        ))}
      </ol>

      {/* Ошибку упавшего шага видно в «Ходе работы» — второй раз сверху её не повторяем */}
      {req.error && !req.steps.some((s) => s.state === 'failed') && <ErrorBlock message={req.error} />}
      {actionError && <ErrorBlock message={actionError} />}

      {req.status === 'paused' && (
        <section className="panel flex flex-wrap items-center gap-3 border-ai/30 p-5" aria-label="Пауза">
          <Pause className="size-5 shrink-0 text-ai" aria-hidden />
          <p className="min-w-[240px] flex-1 text-sm text-muted">
            <span className="font-medium text-text">Генерация на паузе.</span> Готовые уроки сохранены, Claude лимит не тратит. Когда лимит подписки сбросится,
            продолжите — работа пойдёт с первого недописанного шага.
          </p>
          <Button onClick={() => run('resume', () => genApi.resume(req.id))} loading={action === 'resume'} icon={<Play className="size-4" />}>
            Продолжить
          </Button>
        </section>
      )}

      {req.steps.length > 0 && (req.busy || req.status === 'failed' || req.status === 'draft_ready' || req.status === 'paused') && (
        <Steps
          steps={req.steps}
          busy={req.busy}
          controls={
            req.status === 'drafting' && (
              <PauseControls req={req} busyAction={action} run={run} />
            )
          }
        />
      )}


      {(req.status === 'proposed' || req.status === 'rejected') && (
        <section className="panel flex flex-col gap-4 p-5">
          <p>
            Пользователь <b>{req.author}</b> предложил тему «{req.topic}».{req.notes && ` Пожелания: ${req.notes}`}
          </p>
          {req.status === 'proposed' ? (
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => setEditing(true)} icon={<Check className="size-4" />}>
                Принять и уточнить
              </Button>
              <Button variant="ghost" onClick={() => run('reject', () => genApi.reject(req.id))} loading={action === 'reject'}>
                Отклонить
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted">Заявка отклонена.</p>
          )}
        </section>
      )}

      {(req.status === 'new' || (req.status === 'failed' && !req.plan)) && (
        <section className="panel flex flex-col gap-4 p-5">
          <p className="text-muted">
            {req.project
              ? `Наставник прочитает проект «${req.project}» (только чтение), подберёт статьи из библиотеки и предложит план. Без вашего утверждения черновик не создаётся.`
              : 'Наставник подберёт статьи из библиотеки по теме и предложит план. Без вашего утверждения черновик не создаётся.'}
          </p>
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => run('plan', () => genApi.plan(req.id))} loading={action === 'plan'} icon={<Wand2 className="size-4" />}>
              {req.status === 'failed' ? 'Повторить план' : 'Построить план'}
            </Button>
            <Button variant="ghost" onClick={() => setEditing(true)} icon={<Pencil className="size-4" />}>
              Изменить заявку
            </Button>
          </div>
        </section>
      )}

      {req.plan && (req.status === 'plan_ready' || (req.status === 'failed' && !req.lessons.length)) && (
        <PlanStep req={req} busyAction={action} run={run} />
      )}

      {req.lessons.length > 0 && <DraftStep req={req} busyAction={action} run={run} onPublished={reload} />}

      {!req.busy && (
        <button
          type="button"
          onClick={async () => {
            if (!window.confirm('Удалить заявку? Созданные курсы и задания останутся в Контенте.')) return
            await genApi.remove(req.id)
            navigate('/workshop/generate')
          }}
          className="inline-flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted hover:text-danger"
        >
          <Trash2 className="size-4" aria-hidden /> Удалить заявку
        </button>
      )}

      {editing && (
        <RequestForm
          open
          initial={req}
          onClose={() => setEditing(false)}
          onSaved={(next) => {
            setData(next)
            setEditing(false)
          }}
        />
      )}
    </div>
  )
}

const STEP_ICON = {
  pending: <CircleDashed className="size-4 text-faint" aria-hidden />,
  running: <LoaderCircle className="size-4 animate-spin text-ai" aria-hidden />,
  done: <CheckCircle2 className="size-4 text-accent" aria-hidden />,
  failed: <CircleX className="size-4 text-danger" aria-hidden />,
  skipped: <MinusCircle className="size-4 text-faint" aria-hidden />,
}

function Steps({ steps, busy, controls }: { steps: Step[]; busy: boolean; controls?: ReactNode }) {
  return (
    <section className="panel p-5" aria-labelledby="steps-title">
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h2 id="steps-title" className="flex flex-1 items-center gap-2 font-semibold">
          <Sparkles className="size-4 text-ai" aria-hidden /> {busy ? 'Наставник работает' : 'Ход работы'}
        </h2>
        {controls}
      </div>
      <ol className="flex flex-col gap-2" aria-live="polite">
        {steps.map((s) => (
          <li key={s.key} className="flex items-start gap-3 text-sm">
            <span className="mt-0.5">{STEP_ICON[s.state]}</span>
            <span className="min-w-0 flex-1">
              <span className={s.state === 'pending' ? 'text-muted' : ''}>{s.label}</span>
              {s.detail && <span className={`block truncate font-mono text-xs ${s.state === 'failed' ? 'text-danger' : 'text-faint'}`}>{s.detail}</span>}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}

/** Пауза черновика: например, когда от 5-часового лимита подписки осталось немного. */
function PauseControls({ req, busyAction, run }: StepProps) {
  if (req.pause) {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-ai">
        <LoaderCircle className="size-4 animate-spin" aria-hidden />
        {req.pause === 'now' ? 'Останавливаем Claude…' : 'Пауза после текущего урока'}
        {req.pause === 'after' && (
          <button type="button" onClick={() => run('pause', () => genApi.pause(req.id, 'now'))} className="text-muted underline hover:text-text">
            остановить сейчас
          </button>
        )}
      </p>
    )
  }
  return (
    <div className="flex flex-wrap gap-2">
      <Button
        variant="secondary"
        className="h-9"
        onClick={() => run('pause', () => genApi.pause(req.id, 'after'))}
        loading={busyAction === 'pause'}
        icon={<Pause className="size-4" />}
        title="Текущий урок допишется и сохранится, следующий не начнётся"
      >
        Пауза после урока
      </Button>
      <Button
        variant="ghost"
        className="h-9"
        onClick={() => run('pause', () => genApi.pause(req.id, 'now'))}
        icon={<Square className="size-3.5" />}
        title="Claude прерывается сразу; недописанный урок начнётся заново после продолжения"
      >
        Остановить сейчас
      </Button>
    </div>
  )
}

type StepProps = { req: GenRequest; busyAction: string | null; run: (name: string, fn: () => Promise<GenRequest>) => Promise<void> }

function PlanStep({ req, busyAction, run }: StepProps) {
  const [plan, setPlan] = useState<Plan>(req.plan!)
  const [fragments, setFragments] = useState(req.fragments)
  const [dirty, setDirty] = useState(false)
  const [replanning, setReplanning] = useState(false)
  const [feedback, setFeedback] = useState('')
  useEffect(() => {
    setPlan(req.plan!)
    setFragments(req.fragments)
    setDirty(false)
  }, [req.plan, req.fragments])

  const lessons = plan.modules.reduce((n, m) => n + m.lessons.length, 0)
  const tasks = plan.modules.reduce((n, m) => n + m.lessons.filter((l) => l.practice).length, 0)
  const questions = plan.modules.reduce((n, m) => n + m.lessons.reduce((q, l) => q + l.quiz, 0), 0)
  const editable = req.status === 'plan_ready'

  return (
    <section className="flex flex-col gap-4" aria-labelledby="plan-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="plan-title" className="text-xl font-semibold">
          План
        </h2>
        <span className="font-mono text-xs text-muted">
          модулей {plan.modules.length} · уроков {lessons} · заданий {tasks} · вопросов {questions}
        </span>
      </div>
      {plan.summary && (
        <p className="rounded-lg border border-ai/30 bg-ai-soft/60 p-4 text-sm">
          <span className="font-medium text-ai">Наставник: </span>
          {plan.summary}
        </p>
      )}
      <PlanEditor
        path={req.what === 'path'}
        plan={plan}
        fragments={fragments}
        onFragmentTitle={(fid, title) => setFragments((f) => ({ ...f, [fid]: title }))}
        onChange={(next) => {
          setPlan(next)
          setDirty(true)
        }}
      />
      {editable && (
        <div className="sticky bottom-0 z-10 -mx-4 flex flex-wrap items-center gap-3 border-t border-line bg-bg/90 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-lg sm:border">
          <Button
            onClick={() =>
              run('draft', async () => {
                if (dirty) await genApi.savePlan(req.id, plan)
                return genApi.draft(req.id)
              })
            }
            loading={busyAction === 'draft'}
            icon={<Wand2 className="size-4" />}
          >
            Утвердить план и создать черновик
          </Button>
          <Button variant="secondary" onClick={() => run('save', () => genApi.savePlan(req.id, plan))} loading={busyAction === 'save'} disabled={!dirty}>
            Сохранить правки
          </Button>
          <Button variant="ghost" onClick={() => setReplanning(true)} icon={<RefreshCw className="size-4" />}>
            Переделать план
          </Button>
          {dirty && <span className="text-xs text-ai">есть несохранённые правки</span>}
        </div>
      )}
      {req.status === 'failed' && (
        <Button onClick={() => run('draft', () => genApi.draft(req.id))} loading={busyAction === 'draft'} className="w-fit" icon={<RefreshCw className="size-4" />}>
          Продолжить черновик
        </Button>
      )}

      <Dialog
        open={replanning}
        onClose={() => setReplanning(false)}
        title="Переделать план"
        footer={
          <>
            <Button variant="ghost" onClick={() => setReplanning(false)}>
              Отмена
            </Button>
            <Button
              disabled={feedback.trim().length < 3}
              onClick={() => {
                setReplanning(false)
                run('replan', () => genApi.replan(req.id, feedback))
              }}
            >
              Отправить наставнику
            </Button>
          </>
        }
      >
        <TextArea
          label="Что поменять"
          rows={4}
          placeholder="Меньше теории про DOM, добавь урок про адаптив, задания — только веб…"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          hint="Наставник получит текущий план и вашу просьбу и предложит новый вариант."
        />
      </Dialog>
    </section>
  )
}

function DraftStep({ req, busyAction, run, onPublished }: StepProps & { onPublished: () => void }) {
  const navigate = useNavigate()
  const [openReview, setOpenReview] = useState<string | null>(null)
  const [redo, setRedo] = useState<CreatedLesson | null>(null)
  const [instruction, setInstruction] = useState('')
  const [publishing, setPublishing] = useState(false)
  const [result, setResult] = useState<{ published: string[]; problems: string[] } | null>(null)

  const publish = async () => {
    setPublishing(true)
    try {
      const out = await genApi.publish(req.id)
      setResult(out)
      if (out.problems.length === 0) onPublished()
    } catch (e) {
      setResult({ published: [], problems: [e instanceof ApiError ? e.message : 'Не удалось опубликовать'] })
    } finally {
      setPublishing(false)
    }
  }

  const coursePreview = req.course ? `/courses/${req.course.slug}?version=${req.course.draft_version ?? req.course.published_version}` : null

  return (
    <section className="flex flex-col gap-4" aria-labelledby="draft-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="draft-title" className="text-xl font-semibold">
          Черновик
        </h2>
        <div className="flex flex-wrap gap-2">
          {req.path && (
            <ButtonLink variant="secondary" to={`/projects/${req.path.slug}`} icon={<Eye className="size-4" />}>
              Страница пути
            </ButtonLink>
          )}
          {req.course && (
            <>
              <ButtonLink variant="secondary" to={`/workshop/content/${req.course.id}`} icon={<Pencil className="size-4" />}>
                Редактор курса
              </ButtonLink>
              {coursePreview && (
                <ButtonLink variant="ghost" to={coursePreview} icon={<Eye className="size-4" />}>
                  Глазами пользователя
                </ButtonLink>
              )}
            </>
          )}
          {req.topics.map((t) => (
            <ButtonLink key={t.id} variant="ghost" to={`/workshop/content/quiz/${t.id}`} icon={<ClipboardList className="size-4" />}>
              {req.topics.length > 1 ? t.title.split(': ').pop() : 'Банк вопросов'} · {t.questions}
            </ButtonLink>
          ))}
        </div>
      </div>

      <ol className="flex flex-col gap-3">
        {req.lessons.map((lesson, i) => (
          <li key={lesson.id} className="panel flex flex-col gap-3 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-faint">урок {i + 1}</span>
              <h3 className="flex-1 font-medium">{lesson.title}</h3>
              {req.status === 'draft_ready' && !req.published && (
                <Button variant="ghost" onClick={() => setRedo(lesson)} icon={<RefreshCw className="size-4" />} className="h-8 px-2 text-sm">
                  Переделать урок
                </Button>
              )}
            </div>
            <div className="grid gap-3 text-sm md:grid-cols-3">
              <div>
                <p className="eyebrow mb-1">Теория</p>
                {lesson.theory.length ? (
                  <ul className="flex flex-col gap-0.5">
                    {lesson.theory.map((t) => (
                      <li key={t.id}>
                        <Link to={`/library/${t.id}`} className="text-accent hover:underline">
                          {t.title}
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-danger">нет</p>
                )}
              </div>
              <div>
                <p className="eyebrow mb-1">{lesson.stage ? 'Этап и автопроверка' : 'Задание'}</p>
                {lesson.stage ? (
                  <div className="flex flex-col gap-1">
                    <span className="flex items-start gap-1.5">
                      {STEP_ICON[lesson.stage.check_status === 'passed' ? 'done' : lesson.stage.check_status === 'failed' ? 'failed' : lesson.stage.check_status === 'queued' ? 'running' : 'pending']}
                      <span className={`text-xs ${lesson.stage.check_status === 'failed' ? 'text-danger' : 'text-muted'}`}>{lesson.stage.check_summary}</span>
                    </span>
                    {lesson.stage.forks.map((f, i) => (
                      <span key={i} className="text-xs text-ai">
                        развилка: {f}
                      </span>
                    ))}
                  </div>
                ) : lesson.task ? (
                  <div className="flex flex-col gap-1">
                    <Link to={`/workshop/content/tasks/${lesson.task.id}`} className="inline-flex items-center gap-1.5 hover:text-accent">
                      <SquareTerminal className="size-4 text-muted" aria-hidden /> {lesson.task.title}
                    </Link>
                    <span className="flex items-start gap-1.5">
                      {STEP_ICON[lesson.task.check_status === 'passed' ? 'done' : lesson.task.check_status === 'failed' ? 'failed' : lesson.task.check_status === 'queued' ? 'running' : 'pending']}
                      <span className={`text-xs ${lesson.task.check_status === 'failed' ? 'text-danger' : 'text-muted'}`}>{lesson.task.check_summary}</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => setOpenReview((o) => (o === lesson.id ? null : lesson.id))}
                      aria-expanded={openReview === lesson.id}
                      className="group flex w-fit items-start gap-1.5 rounded text-left"
                    >
                      {STEP_ICON[lesson.task.review_verdict === 'pass' ? 'done' : lesson.task.review_verdict === 'changes_requested' ? 'failed' : 'pending']}
                      <span className={`text-xs group-hover:underline ${lesson.task.review_verdict === 'changes_requested' ? 'text-ai' : 'text-muted'}`}>
                        Ревьюер: {lesson.task.review_summary}
                      </span>
                      <ChevronDown className={`mt-px size-3.5 shrink-0 text-muted transition-transform duration-300 ${openReview === lesson.id ? 'rotate-180' : ''}`} aria-hidden />
                    </button>
                  </div>
                ) : (
                  <p className="text-muted">—</p>
                )}
              </div>
              <div>
                <p className="eyebrow mb-1">Вопросы</p>
                <p className={lesson.questions ? '' : 'text-muted'}>
                  {lesson.questions ? `${lesson.questions}${lesson.questions_published ? `, опубликовано ${lesson.questions_published}` : ''}` : '—'}
                </p>
              </div>
            </div>
            {lesson.task && openReview === lesson.id && (
              <div className="border-t border-line pt-3">
                <ReferenceReview
                  taskId={lesson.task.id}
                  specKey={`${lesson.task.draft_version}`}
                  dirty={false}
                  editable={!req.published}
                  onJump={(file, line) => navigate(`/workshop/content/tasks/${lesson.task!.id}?file=${encodeURIComponent(file)}${line ? `&line=${line}` : ''}`)}
                  onChange={onPublished}
                />
              </div>
            )}
            {lesson.notes.length > 0 && (
              <ul className="flex flex-col gap-0.5 rounded-md border border-ai/25 bg-ai-soft/50 px-3 py-2 text-xs text-ai">
                {lesson.notes.map((n, j) => (
                  <li key={j}>• {n}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>

      {req.status === 'failed' && (
        <div className="panel flex flex-wrap items-center gap-3 p-5">
          <p className="min-w-[240px] flex-1 text-sm text-muted">Готовые уроки сохранены. Продолжение начнётся с упавшего урока.</p>
          <Button onClick={() => run('draft', () => genApi.draft(req.id))} loading={busyAction === 'draft'} icon={<RefreshCw className="size-4" />}>
            Продолжить черновик
          </Button>
        </div>
      )}

      {req.status === 'draft_ready' && (
        <div className="panel flex flex-col gap-3 p-5">
          {req.published ? (
            <p className="flex items-center gap-2 text-accent">
              <CheckCircle2 className="size-5" aria-hidden /> Всё опубликовано — пользователь уже видит {req.what === 'course' ? 'курс' : req.what === 'quiz' ? 'тест' : req.what === 'path' ? 'путь в «Моих проектах»' : 'задания'}.
            </p>
          ) : (
            <>
              <p className="text-sm text-muted">
                Проверьте черновик глазами пользователя и поправьте что нужно в редакторах. Публикация одной кнопкой: задания, вопросы, тесты и курс — либо всё сразу, либо ничего, если что-то не готово.
              </p>
              <div className="flex flex-wrap gap-3">
                <Button onClick={publish} loading={publishing} icon={<Rocket className="size-4" />}>
                  Опубликовать всё
                </Button>
                <Button variant="secondary" onClick={() => run('recheck', () => genApi.recheck(req.id))} loading={busyAction === 'recheck'} icon={<RefreshCw className="size-4" />}>
                  Перезапустить автопроверки
                </Button>
              </div>
            </>
          )}
          {result && result.problems.length > 0 && (
            <div role="alert" className="rounded-md border border-danger/40 bg-danger-soft p-3 text-sm">
              <p className="mb-1 font-medium text-danger">Пока не опубликовано — сначала исправьте:</p>
              <ul className="flex flex-col gap-0.5">
                {result.problems.map((p, i) => (
                  <li key={i}>• {p}</li>
                ))}
              </ul>
            </div>
          )}
          {result && result.published.length > 0 && <p role="status" className="text-sm text-accent">Опубликовано: {result.published.join(', ')}.</p>}
        </div>
      )}

      <Dialog
        open={redo !== null}
        onClose={() => setRedo(null)}
        title={`Переделать урок «${redo?.title ?? ''}»`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setRedo(null)}>
              Отмена
            </Button>
            <Button
              disabled={instruction.trim().length < 3}
              onClick={() => {
                const lesson = redo!
                setRedo(null)
                run('redo', () => genApi.redo(req.id, lesson.id, instruction)).then(() => setInstruction(''))
              }}
            >
              Переделать
            </Button>
          </>
        }
      >
        <TextArea
          label="Что поменять"
          rows={3}
          placeholder="Усложни тесты задания · замени теорию на статью про flex-wrap · вопросы попроще"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          hint="Старые черновики урока заменятся; то, что пользователи уже видели, не удаляется."
        />
      </Dialog>
    </section>
  )
}
