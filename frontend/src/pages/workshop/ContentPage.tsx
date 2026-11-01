import { ClipboardList, Code2, FileStack, Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { Button } from '@/components/ui/Button'
import { Glider } from '@/components/ui/Glider'
import { Dialog } from '@/components/ui/Dialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { TextArea, TextField } from '@/components/ui/Field'
import { Badge, ErrorBlock, PageHeader, Skeleton } from '@/components/ui/States'
import { workshopCoursesApi, type AdminCourseBrief } from '@/features/courses/api'
import { KIND_LABEL, workshopTasksApi, type CheckStatus, type Kind } from '@/features/practice/api'
import { quizAdminApi } from '@/features/quiz/api'
import { formatDate } from '@/features/library/FragmentView'
import { useApi } from '@/lib/useApi'

export function CourseStatus({ course }: { course: Pick<AdminCourseBrief, 'published_version' | 'draft_version' | 'archived'> }) {
  return (
    <span className="flex flex-wrap gap-1.5">
      {course.archived && <Badge tone="danger">снят с публикации</Badge>}
      {course.published_version && !course.archived && <Badge tone="accent">опубликован · v{course.published_version}</Badge>}
      {course.draft_version && <Badge tone="ai">черновик · v{course.draft_version}</Badge>}
    </span>
  )
}

export function ContentPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'tasks' ? 'tasks' : params.get('tab') === 'quiz' ? 'quiz' : 'courses'
  const { data, error, loading, reload } = useApi(() => workshopCoursesApi.list(), [])
  const [creating, setCreating] = useState(false)
  const [creatingTask, setCreatingTask] = useState(false)
  const [creatingTopic, setCreatingTopic] = useState(false)

  return (
    <div className="rise-in flex flex-col gap-8">
      <PageHeader
        ai
        eyebrow="Мастерская"
        title="Контент"
        text="Курсы, уроки и практические задания. Правка опубликованного создаёт новую версию — пользователи увидят её только после публикации."
        actions={
          tab === 'courses' ? (
            <Button onClick={() => setCreating(true)} icon={<Plus className="size-4" />}>
              Новый курс
            </Button>
          ) : tab === 'quiz' ? (
            <Button onClick={() => setCreatingTopic(true)} icon={<Plus className="size-4" />}>
              Новая тема теста
            </Button>
          ) : (
            <Button onClick={() => setCreatingTask(true)} icon={<Plus className="size-4" />}>
              Новое задание
            </Button>
          )
        }
      />

      <div role="tablist" aria-label="Вид контента" className="relative flex gap-1 border-b border-line">
        <Glider variant="underline" />
        {(
          [
            ['courses', 'Курсы', FileStack],
            ['tasks', 'Задания', Code2],
            ['quiz', 'Тесты', ClipboardList],
          ] as const
        ).map(([key, label, Icon]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setParams(key === 'courses' ? {} : { tab: key }, { replace: true })}
            className={`relative z-[1] inline-flex items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-300 ${tab === key ? 'font-medium text-text' : 'text-muted hover:text-text'}`}
          >
            <Icon className="size-4" aria-hidden /> {label}
          </button>
        ))}
      </div>

      {tab === 'tasks' ? (
        <TasksList onCreate={() => setCreatingTask(true)} />
      ) : tab === 'quiz' ? (
        <TopicsList onCreate={() => setCreatingTopic(true)} />
      ) : (
      <>

      {error ? (
        <ErrorBlock message={error.message} onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton lines={3} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={<FileStack className="size-5" />}
          title="Курсов ещё нет"
          text="Создайте курс, добавьте модули и уроки, привяжите к урокам статьи из библиотеки и опубликуйте."
          action={
            <Button variant="secondary" onClick={() => setCreating(true)}>
              Создать первый курс
            </Button>
          }
        />
      ) : (
        <ul className="panel divide-y divide-line overflow-hidden">
          {data.map((course) => (
            <li key={course.id}>
              <Link to={`/workshop/content/${course.id}`} className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-4 hover:bg-surface-2/60">
                <span className="min-w-[200px] flex-1 font-medium">{course.title}</span>
                <CourseStatus course={course} />
                <span className="text-sm text-muted">{course.lessons} ур.</span>
                <span className="text-sm text-faint">изменён {formatDate(course.updated_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      </>
      )}

      <CreateCourseDialog open={creating} onClose={() => setCreating(false)} />
      <CreateTaskDialog open={creatingTask} onClose={() => setCreatingTask(false)} />
      <CreateTopicDialog open={creatingTopic} onClose={() => setCreatingTopic(false)} />
    </div>
  )
}

function CreateCourseDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!title.trim()) {
      setError('Введите название курса')
      return
    }
    setSending(true)
    try {
      const course = await workshopCoursesApi.create(title.trim(), description.trim())
      navigate(`/workshop/content/${course.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось создать курс')
      setSending(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Новый курс"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" form="create-course" loading={sending} loadingText="Создаём…">
            Создать черновик
          </Button>
        </>
      }
    >
      <form id="create-course" onSubmit={submit} className="flex flex-col gap-4">
        <TextField label="Название" value={title} onChange={(e) => (setTitle(e.target.value), setError(null))} error={error} placeholder="Вёрстка сайта про гору Фишт" data-autofocus />
        <TextArea label="Описание (необязательно)" value={description} onChange={(e) => setDescription(e.target.value)} hint="Что человек научится делать после курса." />
      </form>
    </Dialog>
  )
}

const CHECK_BADGE: Record<CheckStatus, { label: string; tone: 'muted' | 'accent' | 'ai' | 'danger' }> = {
  not_checked: { label: 'не проверено', tone: 'muted' },
  queued: { label: 'проверяется', tone: 'ai' },
  passed: { label: 'автопроверка ✓', tone: 'accent' },
  failed: { label: 'автопроверка ✗', tone: 'danger' },
}

function TasksList({ onCreate }: { onCreate: () => void }) {
  const { data, error, loading, reload } = useApi(() => workshopTasksApi.list(), [])
  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (loading || !data) return <Skeleton lines={3} />
  if (data.length === 0) {
    return (
      <EmptyState
        icon={<Code2 className="size-5" />}
        title="Заданий ещё нет"
        text="Задание — это условие, стартовый код, эталон и проверки. Публикуется только после автопроверки: эталон проходит, стартовый код — нет."
        action={
          <Button variant="secondary" onClick={onCreate}>
            Создать первое задание
          </Button>
        }
      />
    )
  }
  return (
    <ul className="panel divide-y divide-line overflow-hidden">
      {data.map((task) => (
        <li key={task.id}>
          <Link to={`/workshop/content/tasks/${task.id}`} className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-4 hover:bg-surface-2/60">
            <span className="min-w-[200px] flex-1 font-medium">{task.title}</span>
            <Badge>{KIND_LABEL[task.kind]}</Badge>
            <CourseStatus course={task} />
            <Badge tone={CHECK_BADGE[task.check_status].tone}>{CHECK_BADGE[task.check_status].label}</Badge>
            <span className="text-sm text-faint">изменено {formatDate(task.updated_at)}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function CreateTaskDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<Kind>('web')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!title.trim()) return setError('Введите название задания')
    setSending(true)
    try {
      const task = await workshopTasksApi.create(title.trim(), kind)
      navigate(`/workshop/content/tasks/${task.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось создать задание')
      setSending(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Новое задание"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" form="create-task" loading={sending} loadingText="Создаём…">
            Создать черновик
          </Button>
        </>
      }
    >
      <form id="create-task" onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <TextField label="Название" value={title} onChange={(e) => (setTitle(e.target.value), setError(null))} error={error} placeholder="Шапка сайта про гору Фишт" />
        <fieldset>
          <legend className="text-sm font-medium">Что пишет ученик</legend>
          <div className="mt-2 flex flex-col gap-2">
            {(Object.keys(KIND_LABEL) as Kind[]).map((k) => (
              <label key={k} className="flex items-center gap-2 text-sm">
                <input type="radio" name="kind" checked={kind === k} onChange={() => setKind(k)} className="accent-[var(--accent)]" />
                {KIND_LABEL[k]}
                <span className="text-faint">— {k === 'web' ? 'страница с живым превью, проверки на 3 ширинах' : k === 'python' ? 'функции и классы, проверки на Python' : 'запросы к готовой базе SQLite'}</span>
              </label>
            ))}
          </div>
          <p className="mt-2 text-xs text-faint">Вид задания после создания не меняется.</p>
        </fieldset>
      </form>
    </Dialog>
  )
}

function TopicsList({ onCreate }: { onCreate: () => void }) {
  const { data, error, loading, reload } = useApi(() => quizAdminApi.topics(), [])
  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (loading || !data) return <Skeleton lines={3} />
  if (data.length === 0) {
    return (
      <EmptyState
        icon={<ClipboardList className="size-5" />}
        title="Тем пока нет"
        text="Тема — это банк вопросов. Тест собирается из него случайно и без повторов, поэтому вопросов нужно в несколько раз больше, чем в одном тесте."
        action={
          <Button variant="secondary" onClick={onCreate}>
            Создать тему
          </Button>
        }
      />
    )
  }
  return (
    <ul className="panel divide-y divide-line overflow-hidden">
      {data.map((t) => (
        <li key={t.id}>
          <Link to={`/workshop/content/quiz/${t.id}`} className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-4 hover:bg-surface-2/60">
            <span className="min-w-[200px] flex-1 font-medium">{t.title}</span>
            <Badge tone={t.published ? 'accent' : 'ai'}>{t.published ? 'опубликована' : 'скрыта'}</Badge>
            <span className="text-sm text-muted">
              вопросов: {t.counts.published ?? 0} опубл. · {t.counts.draft ?? 0} черн.
            </span>
            <span className="text-sm text-faint">в тесте: {t.size}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function CreateTopicDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!title.trim()) return setError('Введите название темы')
    setSending(true)
    try {
      const topic = await quizAdminApi.createTopic({ title: title.trim(), description: '', size: 10, published: false })
      navigate(`/workshop/content/quiz/${topic.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось создать тему')
      setSending(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Новая тема теста"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" form="create-topic" loading={sending} loadingText="Создаём…">
            Создать
          </Button>
        </>
      }
    >
      <form id="create-topic" onSubmit={submit} noValidate>
        <TextField label="Название" value={title} onChange={(e) => (setTitle(e.target.value), setError(null))} error={error} placeholder="CSS: селекторы и каскад" />
      </form>
    </Dialog>
  )
}

