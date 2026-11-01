import {
  AlertTriangle,
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Eye,
  History,
  Pencil,
  Plus,
  Rocket,
  Save,
  Trash2,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useBlocker, useNavigate, useParams } from 'react-router'

import { Button, ButtonLink } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { inputClass, TextArea, TextField } from '@/components/ui/Field'
import { Badge, ErrorBlock, Skeleton } from '@/components/ui/States'
import { newId, workshopCoursesApi, type AdminCourse, type CourseContent, type Lesson, type Module, type VersionBrief } from '@/features/courses/api'
import { FragmentPicker } from '@/features/courses/FragmentPicker'
import { TaskPicker } from '@/features/courses/TaskPicker'
import { quizAdminApi, type TopicAdmin } from '@/features/quiz/api'
import type { FragmentBrief } from '@/features/library/api'
import { formatDate, SourceBadge } from '@/features/library/FragmentView'
import { KIND_LABEL } from '@/features/practice/api'
import { ApiError } from '@/lib/api'
import { useApi } from '@/lib/useApi'

import { CourseStatus } from './ContentPage'

type Draft = { title: string; description: string; content: CourseContent }
type Confirm = { title: string; text: string; action: string; run: () => void | Promise<void> }

function move<T>(items: T[], index: number, delta: number): T[] {
  const target = index + delta
  if (target < 0 || target >= items.length) return items
  const copy = [...items]
  ;[copy[index], copy[target]] = [copy[target], copy[index]]
  return copy
}

export function CourseEditorPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const loaded = useApi(() => workshopCoursesApi.get(id), [id])

  const [course, setCourse] = useState<AdminCourse | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [fragments, setFragments] = useState<Record<string, FragmentBrief>>({})
  const [dirty, setDirty] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const [picker, setPicker] = useState(false)
  const [taskPicker, setTaskPicker] = useState(false)
  const [tasks, setTasks] = useState<AdminCourse['tasks']>({})
  const [quizPicker, setQuizPicker] = useState(false)
  const [quizTopics, setQuizTopics] = useState<AdminCourse['quiz_topics']>({})
  const [publishing, setPublishing] = useState(false)
  const [changeNote, setChangeNote] = useState('')
  const [versions, setVersions] = useState<VersionBrief[] | null>(null)
  const [confirm, setConfirm] = useState<Confirm | null>(null)

  const accept = useCallback((data: AdminCourse) => {
    setCourse(data)
    setDraft({ title: data.editing.title, description: data.editing.description, content: data.editing.content })
    setFragments((f) => ({ ...f, ...data.fragments }))
    setTasks((t) => ({ ...t, ...data.tasks }))
    setQuizTopics((t) => ({ ...t, ...data.quiz_topics }))
    setDirty(false)
  }, [])

  useEffect(() => {
    if (loaded.data) accept(loaded.data)
  }, [loaded.data, accept])

  useEffect(() => {
    const firstLesson = draft?.content.modules.flatMap((m) => m.lessons)[0]?.id ?? null
    if (draft && (!selected || !draft.content.modules.some((m) => m.lessons.some((l) => l.id === selected)))) setSelected(firstLesson)
  }, [draft, selected])

  // Защита от потери изменений: уход со страницы и закрытие вкладки
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname)
  useEffect(() => {
    if (!dirty) return
    const handler = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  const editable = !!course?.draft_version

  const run = async (label: string, action: () => Promise<AdminCourse | void>, success?: string) => {
    setBusy(label)
    setMessage(null)
    try {
      const result = await action()
      if (result) accept(result)
      if (success) setMessage({ tone: 'ok', text: success })
      return true
    } catch (e) {
      setMessage({ tone: 'error', text: e instanceof Error ? e.message : 'Что-то пошло не так' })
      return false
    } finally {
      setBusy(null)
    }
  }

  const save = () =>
    run('save', () => workshopCoursesApi.saveDraft(course!.id, { number: course!.draft_version!, ...draft! }), 'Черновик сохранён')

  const publish = async () => {
    setProblems([])
    if (dirty && !(await save())) return
    setBusy('publish')
    try {
      accept(await workshopCoursesApi.publish(course!.id, changeNote))
      setPublishing(false)
      setChangeNote('')
      setMessage({ tone: 'ok', text: 'Опубликовано. Пользователи уже видят новую версию.' })
    } catch (e) {
      const body = e instanceof ApiError ? (e.body as { problems?: string[] } | null) : null
      setProblems(body?.problems ?? [e instanceof Error ? e.message : 'Не удалось опубликовать'])
    } finally {
      setBusy(null)
    }
  }

  // ---------- изменение содержимого ----------

  const change = (fn: (d: Draft) => Draft) => {
    setDraft((d) => (d ? fn(d) : d))
    setDirty(true)
  }
  const setModules = (fn: (modules: Module[]) => Module[]) => change((d) => ({ ...d, content: { modules: fn(d.content.modules) } }))
  const updateModule = (moduleId: string, fn: (m: Module) => Module) => setModules((ms) => ms.map((m) => (m.id === moduleId ? fn(m) : m)))
  const updateLesson = (lessonId: string, fn: (l: Lesson) => Lesson) =>
    setModules((ms) => ms.map((m) => ({ ...m, lessons: m.lessons.map((l) => (l.id === lessonId ? fn(l) : l)) })))

  const addModule = () => {
    const lesson: Lesson = { id: newId('les'), title: 'Новый урок', goal: '', blocks: [] }
    setModules((ms) => [...ms, { id: newId('mod'), title: `Модуль ${ms.length + 1}`, lessons: [lesson] }])
    setSelected(lesson.id)
  }
  const addLesson = (moduleId: string) => {
    const lesson: Lesson = { id: newId('les'), title: 'Новый урок', goal: '', blocks: [] }
    updateModule(moduleId, (m) => ({ ...m, lessons: [...m.lessons, lesson] }))
    setSelected(lesson.id)
  }

  const current = useMemo(() => {
    for (const module of draft?.content.modules ?? []) {
      const lesson = module.lessons.find((l) => l.id === selected)
      if (lesson) return { module, lesson }
    }
    return null
  }, [draft, selected])

  if (loaded.error) return <ErrorBlock message={loaded.error.message} onRetry={loaded.reload} />
  if (!course || !draft) return <Skeleton lines={5} />

  const previewVersion = course.draft_version ?? course.published_version
  const previewLink = `/courses/${course.slug}${current ? `/lessons/${current.lesson.id}` : ''}?version=${previewVersion}`

  return (
    <div className="flex flex-col gap-6">
      <Link to="/workshop/content" className="inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4" aria-hidden /> Все курсы
      </Link>

      <header className="panel flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-center gap-3">
          <CourseStatus course={course} />
          <span className="text-xs text-faint">
            {editable ? `Редактируется черновик v${course.draft_version}` : `Показана опубликованная версия v${course.published_version} — только чтение`}
          </span>
          {dirty && <Badge tone="ai">есть несохранённые изменения</Badge>}
        </div>

        {editable ? (
          <div className="grid gap-4 md:grid-cols-[1fr_1.4fr]">
            <TextField label="Название курса" value={draft.title} onChange={(e) => change((d) => ({ ...d, title: e.target.value }))} />
            <TextArea label="Описание" value={draft.description} onChange={(e) => change((d) => ({ ...d, description: e.target.value }))} className="[&_textarea]:min-h-10" rows={2} />
          </div>
        ) : (
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{draft.title}</h1>
            {draft.description && <p className="mt-1 text-muted">{draft.description}</p>}
          </div>
        )}

        <div className="flex flex-wrap gap-2 border-t border-line pt-4">
          {editable ? (
            <>
              <Button onClick={save} disabled={!dirty} loading={busy === 'save'} loadingText="Сохраняем…" icon={<Save className="size-4" />}>
                Сохранить черновик
              </Button>
              <Button variant="secondary" onClick={() => (setProblems([]), setPublishing(true))} icon={<Rocket className="size-4" />}>
                Опубликовать…
              </Button>
            </>
          ) : (
            <Button onClick={() => run('draft', () => workshopCoursesApi.startDraft(course.id))} loading={busy === 'draft'} icon={<Pencil className="size-4" />}>
              Редактировать (создать v{(course.published_version ?? 0) + 1})
            </Button>
          )}
          <ButtonLink to={previewLink} variant="ghost" icon={<Eye className="size-4" />}>
            Предпросмотр{dirty ? ' (без несохранённого)' : ''}
          </ButtonLink>
          <Button variant="ghost" onClick={async () => setVersions(await workshopCoursesApi.versions(course.id))} icon={<History className="size-4" />}>
            Версии
          </Button>
          <span className="flex-1" />
          {course.published_version && (
            <Button
              variant="ghost"
              onClick={() =>
                course.archived
                  ? run('archive', () => workshopCoursesApi.archive(course.id, false), 'Курс снова виден пользователям')
                  : setConfirm({
                      title: 'Снять курс с публикации?',
                      text: 'Пользователи перестанут видеть курс. Их прогресс сохранится, курс можно вернуть в любой момент.',
                      action: 'Снять с публикации',
                      run: () => void run('archive', () => workshopCoursesApi.archive(course.id, true), 'Курс снят с публикации'),
                    })
              }
            >
              {course.archived ? 'Вернуть в публикацию' : 'Снять с публикации'}
            </Button>
          )}
          {course.draft_version && course.published_version && (
            <Button
              variant="danger"
              onClick={() =>
                setConfirm({
                  title: `Отменить черновик v${course.draft_version}?`,
                  text: 'Все изменения черновика пропадут. Опубликованная версия останется как есть.',
                  action: 'Отменить черновик',
                  run: () => void run('discard', () => workshopCoursesApi.discardDraft(course.id), 'Черновик отменён'),
                })
              }
            >
              Отменить черновик
            </Button>
          )}
          {!course.published_version && (
            <Button
              variant="danger"
              icon={<Trash2 className="size-4" />}
              onClick={() =>
                setConfirm({
                  title: 'Удалить курс?',
                  text: 'Курс ещё не публиковался, пользователи его не видели. Удаление нельзя отменить.',
                  action: 'Удалить курс',
                  run: async () => {
                    await workshopCoursesApi.remove(course.id)
                    setDirty(false)
                    navigate('/workshop/content')
                  },
                })
              }
            >
              Удалить
            </Button>
          )}
        </div>
        {message && (
          <p role={message.tone === 'error' ? 'alert' : 'status'} className={`text-sm ${message.tone === 'error' ? 'text-danger' : 'text-accent'}`}>
            {message.text}
          </p>
        )}
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[300px_1fr]">
        {/* Структура курса */}
        <nav aria-label="Структура курса" className="panel flex flex-col gap-4 p-4 lg:sticky lg:top-6">
          <p className="eyebrow">Структура</p>
          {draft.content.modules.length === 0 && <p className="text-sm text-muted">Пока пусто. Добавьте первый модуль — в нём сразу появится урок.</p>}
          <ol className="flex flex-col gap-4">
            {draft.content.modules.map((module, mi) => (
              <li key={module.id} className="flex flex-col gap-1.5">
                <div className="group flex items-center gap-1">
                  <span className="w-6 shrink-0 font-mono text-xs text-faint">{String(mi + 1).padStart(2, '0')}</span>
                  {editable ? (
                    <input
                      aria-label={`Название модуля ${mi + 1}`}
                      value={module.title}
                      onChange={(e) => updateModule(module.id, (m) => ({ ...m, title: e.target.value }))}
                      className={`${inputClass} h-8 border-transparent bg-transparent px-1.5 font-medium hover:border-line-strong`}
                    />
                  ) : (
                    <span className="font-medium">{module.title}</span>
                  )}
                  {editable && (
                    <ItemTools
                      label={`модуль «${module.title}»`}
                      onUp={mi > 0 ? () => setModules((ms) => move(ms, mi, -1)) : undefined}
                      onDown={mi < draft.content.modules.length - 1 ? () => setModules((ms) => move(ms, mi, 1)) : undefined}
                      onDelete={() =>
                        setConfirm({
                          title: `Удалить модуль «${module.title}»?`,
                          text: `Вместе с ним удалятся уроки: ${module.lessons.length}. Изменение попадёт в черновик — опубликованная версия не изменится.`,
                          action: 'Удалить модуль',
                          run: () => setModules((ms) => ms.filter((m) => m.id !== module.id)),
                        })
                      }
                    />
                  )}
                </div>
                <ol className="ml-6 flex flex-col">
                  {module.lessons.map((lesson, li) => (
                    <li key={lesson.id} className="group flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setSelected(lesson.id)}
                        aria-current={lesson.id === selected ? 'true' : undefined}
                        className={`flex-1 truncate rounded-md px-2 py-1.5 text-left text-sm ${
                          lesson.id === selected ? 'bg-surface-2 text-text shadow-[inset_2px_0_0_var(--accent)]' : 'text-muted hover:bg-surface-2/60 hover:text-text'
                        }`}
                      >
                        {lesson.title || 'Без названия'}
                        {!lesson.blocks.some((b) => b.type === 'theory') && <span className="ml-1 text-danger" title="Нет теории"> •</span>}
                      </button>
                      {editable && (
                        <ItemTools
                          label={`урок «${lesson.title}»`}
                          onUp={li > 0 ? () => updateModule(module.id, (m) => ({ ...m, lessons: move(m.lessons, li, -1) })) : undefined}
                          onDown={li < module.lessons.length - 1 ? () => updateModule(module.id, (m) => ({ ...m, lessons: move(m.lessons, li, 1) })) : undefined}
                          onDelete={() =>
                            setConfirm({
                              title: `Удалить урок «${lesson.title}»?`,
                              text: 'Изменение попадёт в черновик — опубликованная версия не изменится.',
                              action: 'Удалить урок',
                              run: () => updateModule(module.id, (m) => ({ ...m, lessons: m.lessons.filter((l) => l.id !== lesson.id) })),
                            })
                          }
                        />
                      )}
                    </li>
                  ))}
                </ol>
                {editable && (
                  <button type="button" onClick={() => addLesson(module.id)} className="ml-6 inline-flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted hover:text-accent">
                    <Plus className="size-3.5" aria-hidden /> Урок
                  </button>
                )}
              </li>
            ))}
          </ol>
          {editable && (
            <Button variant="secondary" onClick={addModule} icon={<Plus className="size-4" />}>
              Модуль
            </Button>
          )}
        </nav>

        {/* Урок */}
        <section aria-label="Урок" className="panel flex flex-col gap-5 p-5">
          {!current ? (
            <p className="text-muted">Выберите урок слева{editable ? ' или добавьте модуль' : ''}.</p>
          ) : (
            <>
              <p className="eyebrow">{current.module.title}</p>
              {editable ? (
                <>
                  <TextField label="Название урока" value={current.lesson.title} onChange={(e) => updateLesson(current.lesson.id, (l) => ({ ...l, title: e.target.value }))} />
                  <TextArea
                    label="Цель урока"
                    hint="Ваш текст — что человек сможет сделать после урока. Это не теория: теория берётся только из источников."
                    value={current.lesson.goal}
                    onChange={(e) => updateLesson(current.lesson.id, (l) => ({ ...l, goal: e.target.value }))}
                  />
                </>
              ) : (
                <>
                  <h2 className="text-xl font-semibold">{current.lesson.title}</h2>
                  {current.lesson.goal && <p className="text-muted">{current.lesson.goal}</p>}
                </>
              )}

              <div className="flex flex-col gap-3 border-t border-line pt-5">
                <h3 className="font-semibold">Блоки урока</h3>
                {!current.lesson.blocks.some((b) => b.type === 'theory') && (
                  <p className="text-sm text-muted">Добавьте хотя бы одну статью — без теории урок нельзя опубликовать.</p>
                )}
                <ol className="flex flex-col gap-3">
                  {current.lesson.blocks.map((block, bi) => {
                    const tools = editable && (
                      <ItemTools
                        label={
                          block.type === 'theory'
                            ? `статью «${fragments[block.fragment_id]?.title ?? block.fragment_id}»`
                            : block.type === 'practice'
                              ? `задание «${tasks[block.task_id]?.title ?? block.task_id}»`
                              : `тест «${quizTopics[block.topic_id]?.title ?? block.topic_id}»`
                        }
                        onUp={bi > 0 ? () => updateLesson(current.lesson.id, (l) => ({ ...l, blocks: move(l.blocks, bi, -1) })) : undefined}
                        onDown={bi < current.lesson.blocks.length - 1 ? () => updateLesson(current.lesson.id, (l) => ({ ...l, blocks: move(l.blocks, bi, 1) })) : undefined}
                        onDelete={() => updateLesson(current.lesson.id, (l) => ({ ...l, blocks: l.blocks.filter((b) => b.id !== block.id) }))}
                      />
                    )
                    const number = <span className="font-mono text-xs text-faint">.{String(bi + 1).padStart(2, '0')}</span>

                    if (block.type === 'quiz') {
                      const topic = quizTopics[block.topic_id]
                      return (
                        <li key={block.id} className="group rounded-lg border border-line p-4">
                          <div className="flex flex-wrap items-start gap-2">
                            {number}
                            <div className="min-w-0 flex-1">
                              <Link to={`/workshop/content/quiz/${block.topic_id}`} className="font-medium hover:text-accent">
                                {topic?.title ?? `Тема теста №${block.topic_id}`}
                              </Link>
                              <div className="mt-1 flex flex-wrap items-center gap-2">
                                <Badge>тест</Badge>
                                {topic && !topic.published && <Badge tone="danger">не опубликована</Badge>}
                              </div>
                            </div>
                            {tools}
                          </div>
                        </li>
                      )
                    }

                    if (block.type === 'practice') {
                      const task = tasks[block.task_id]
                      return (
                        <li key={block.id} className="group rounded-lg border border-line p-4">
                          <div className="flex flex-wrap items-start gap-2">
                            {number}
                            <div className="min-w-0 flex-1">
                              <Link to={`/workshop/content/tasks/${block.task_id}`} className="font-medium hover:text-accent">
                                {task?.title ?? `Задание №${block.task_id}`}
                              </Link>
                              <div className="mt-1 flex flex-wrap items-center gap-2">
                                <Badge>практика · {task ? KIND_LABEL[task.kind] : '?'}</Badge>
                                {task && !task.published && <Badge tone="danger">не опубликовано</Badge>}
                              </div>
                            </div>
                            {tools}
                          </div>
                        </li>
                      )
                    }

                    const fragment = fragments[block.fragment_id]
                    return (
                      <li key={block.id} className="group rounded-lg border border-line p-4">
                        <div className="flex flex-wrap items-start gap-2">
                          {number}
                          <div className="min-w-0 flex-1">
                            <Link to={`/library/${block.fragment_id}`} target="_blank" className="font-medium hover:text-accent">
                              {fragment?.title ?? `Статья №${block.fragment_id}`}
                            </Link>
                            <div className="mt-1 flex flex-wrap items-center gap-2">
                              {fragment && <SourceBadge fragment={fragment} />}
                              {fragment?.status === 'removed' && (
                                <Badge tone="danger">
                                  <AlertTriangle className="size-3" aria-hidden /> удалена из источника
                                </Badge>
                              )}
                            </div>
                          </div>
                          {tools}
                        </div>
                        {editable ? (
                          <TextArea
                            className="mt-3"
                            label="Зачем читать"
                            hint="Заметка для ученика: на что обратить внимание в статье."
                            value={block.why}
                            onChange={(e) =>
                              updateLesson(current.lesson.id, (l) => ({
                                ...l,
                                blocks: l.blocks.map((b) => (b.id === block.id && b.type === 'theory' ? { ...b, why: e.target.value } : b)),
                              }))
                            }
                          />
                        ) : (
                          block.why && <p className="mt-2 text-sm text-muted">Зачем читать: {block.why}</p>
                        )}
                      </li>
                    )
                  })}
                </ol>
                {editable && (
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" onClick={() => setPicker(true)} icon={<Plus className="size-4" />}>
                      Добавить статью
                    </Button>
                    <Button variant="secondary" onClick={() => setTaskPicker(true)} icon={<Plus className="size-4" />}>
                      Добавить задание
                    </Button>
                    <Button variant="secondary" onClick={() => setQuizPicker(true)} icon={<Plus className="size-4" />}>
                      Добавить тест
                    </Button>
                  </div>
                )}
              </div>
            </>
          )}
        </section>
      </div>

      {current && (
        <FragmentPicker
          open={picker}
          onClose={() => setPicker(false)}
          taken={new Set(current.lesson.blocks.flatMap((b) => (b.type === 'theory' ? [b.fragment_id] : [])))}
          onPick={(fragment) => {
            setFragments((f) => ({ ...f, [fragment.id]: fragment }))
            updateLesson(current.lesson.id, (l) => ({ ...l, blocks: [...l.blocks, { id: newId('blk'), type: 'theory', fragment_id: fragment.id, why: '' }] }))
            setPicker(false)
          }}
        />
      )}
      {current && (
        <TaskPicker
          open={taskPicker}
          onClose={() => setTaskPicker(false)}
          taken={new Set(current.lesson.blocks.flatMap((b) => (b.type === 'practice' ? [b.task_id] : [])))}
          onPick={(task) => {
            setTasks((t) => ({ ...t, [task.id]: { title: task.title, kind: task.kind, published: !!task.published_version && !task.archived } }))
            updateLesson(current.lesson.id, (l) => ({ ...l, blocks: [...l.blocks, { id: newId('blk'), type: 'practice', task_id: task.id }] }))
            setTaskPicker(false)
          }}
        />
      )}
      {current && (
        <QuizTopicPicker
          open={quizPicker}
          onClose={() => setQuizPicker(false)}
          taken={new Set(current.lesson.blocks.flatMap((b) => (b.type === 'quiz' ? [b.topic_id] : [])))}
          onPick={(topic) => {
            setQuizTopics((t) => ({ ...t, [topic.id]: { title: topic.title, published: topic.published } }))
            updateLesson(current.lesson.id, (l) => ({ ...l, blocks: [...l.blocks, { id: newId('blk'), type: 'quiz', topic_id: topic.id }] }))
            setQuizPicker(false)
          }}
        />
      )}

      <Dialog
        open={publishing}
        onClose={() => setPublishing(false)}
        title={`Опубликовать v${course.draft_version}`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPublishing(false)}>
              Отмена
            </Button>
            <Button onClick={publish} loading={busy === 'publish' || busy === 'save'} loadingText="Публикуем…" icon={<Rocket className="size-4" />}>
              Опубликовать
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted">
            {course.published_version
              ? `Новые пользователи начнут с v${course.draft_version}. Те, кто уже учится на v${course.published_version}, останутся на ней и увидят предложение перейти.`
              : 'Курс появится у пользователей в разделе «Курсы».'}
            {dirty && ' Несохранённые изменения сначала сохранятся.'}
          </p>
          <TextArea label="Что изменилось (необязательно)" value={changeNote} onChange={(e) => setChangeNote(e.target.value)} hint="Попадёт в историю версий." />
          {problems.length > 0 && (
            <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-4 text-sm">
              <p className="font-medium text-danger">Пока нельзя опубликовать:</p>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Dialog>

      <Dialog open={versions !== null} onClose={() => setVersions(null)} title="История версий">
        <ol className="flex flex-col gap-3">
          {versions?.map((v) => (
            <li key={v.number} className="flex flex-wrap items-center gap-3 rounded-lg border border-line p-3">
              <span className="font-mono">v{v.number}</span>
              <Badge tone={v.status === 'published' ? 'accent' : v.status === 'draft' ? 'ai' : 'muted'}>
                {v.status === 'published' ? 'опубликована' : v.status === 'draft' ? 'черновик' : 'заменена'}
              </Badge>
              <span className="text-sm text-muted">{v.published_at ? `опубликована ${formatDate(v.published_at)}` : `создана ${formatDate(v.created_at)}`}</span>
              {v.change_note && <p className="w-full text-sm">{v.change_note}</p>}
              <Link to={`/courses/${course.slug}?version=${v.number}`} className="text-sm text-accent hover:underline">
                Посмотреть
              </Link>
            </li>
          ))}
        </ol>
      </Dialog>

      <ConfirmDialog confirm={confirm} onClose={() => setConfirm(null)} />

      <Dialog
        open={blocker.state === 'blocked'}
        onClose={() => blocker.reset?.()}
        title="Есть несохранённые изменения"
        footer={
          <>
            <Button variant="ghost" onClick={() => blocker.reset?.()}>
              Остаться
            </Button>
            <Button variant="danger" onClick={() => blocker.proceed?.()}>
              Не сохранять
            </Button>
            <Button onClick={async () => ((await save()) ? blocker.proceed?.() : blocker.reset?.())} loading={busy === 'save'}>
              Сохранить и перейти
            </Button>
          </>
        }
      >
        <p className="text-muted">Черновик курса изменён, но не сохранён. Если уйти сейчас, изменения пропадут.</p>
      </Dialog>
    </div>
  )
}

function ItemTools({ label, onUp, onDown, onDelete }: { label: string; onUp?: () => void; onDown?: () => void; onDelete: () => void }) {
  const tool = 'grid size-7 place-items-center rounded-md text-faint hover:bg-surface-2 hover:text-text disabled:opacity-30'
  return (
    // На компьютере инструменты появляются при наведении или фокусе в строке — больше места названиям
    <span className="flex shrink-0 items-center lg:hidden lg:group-hover:flex lg:group-focus-within:flex">
      <button type="button" className={tool} onClick={onUp} disabled={!onUp} aria-label={`Выше: ${label}`}>
        <ArrowUp className="size-3.5" />
      </button>
      <button type="button" className={tool} onClick={onDown} disabled={!onDown} aria-label={`Ниже: ${label}`}>
        <ArrowDown className="size-3.5" />
      </button>
      <button type="button" className={`${tool} hover:text-danger`} onClick={onDelete} aria-label={`Удалить ${label}`}>
        <Trash2 className="size-3.5" />
      </button>
    </span>
  )
}

function ConfirmDialog({ confirm, onClose }: { confirm: Confirm | null; onClose: () => void }): ReactNode {
  const [running, setRunning] = useState(false)
  return (
    <Dialog
      open={confirm !== null}
      onClose={onClose}
      title={confirm?.title ?? ''}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} data-autofocus>
            Отмена
          </Button>
          <Button
            variant="danger"
            loading={running}
            onClick={async () => {
              setRunning(true)
              try {
                await confirm?.run()
              } finally {
                setRunning(false)
                onClose()
              }
            }}
          >
            {confirm?.action}
          </Button>
        </>
      }
    >
      <p className="text-muted">{confirm?.text}</p>
    </Dialog>
  )
}

function QuizTopicPicker({ open, onClose, onPick, taken }: { open: boolean; onClose: () => void; onPick: (t: TopicAdmin) => void; taken: Set<number> }) {
  const topics = useApi(() => (open ? quizAdminApi.topics() : Promise.resolve(null)), [open])
  return (
    <Dialog open={open} onClose={onClose} title="Тест для урока">
      {topics.error ? (
        <ErrorBlock message={topics.error.message} onRetry={topics.reload} />
      ) : !topics.data ? (
        <Skeleton lines={2} />
      ) : (
        <ul className="flex flex-col gap-2">
          {topics.data.map((t) => {
            const ready = t.published && (t.counts.published ?? 0) > 0
            return (
              <li key={t.id}>
                <button
                  type="button"
                  disabled={!ready || taken.has(t.id)}
                  onClick={() => onPick(t)}
                  className="flex w-full flex-col items-start gap-1 rounded-lg border border-line p-3 text-left hover:border-accent/50 disabled:opacity-50"
                >
                  <span className="font-medium">{t.title}</span>
                  <span className="text-xs text-muted">
                    {taken.has(t.id) ? 'Уже есть в этом уроке' : ready ? `опубликовано вопросов: ${t.counts.published}` : 'Тема не опубликована или в ней нет опубликованных вопросов'}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Dialog>
  )
}

