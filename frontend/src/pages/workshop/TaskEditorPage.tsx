import { ArrowLeft, CheckCircle2, CircleX, Eye, LoaderCircle, Pencil, Plus, Rocket, Save, ShieldCheck, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useBlocker, useNavigate, useParams, useSearchParams } from 'react-router'

import { Button, ButtonLink } from '@/components/ui/Button'
import { Glider } from '@/components/ui/Glider'
import { ReferenceReview } from '@/features/review/ReferenceReview'
import { Dialog } from '@/components/ui/Dialog'
import { TextArea, TextField } from '@/components/ui/Field'
import { Badge, ErrorBlock, Skeleton } from '@/components/ui/States'
import { FragmentPicker } from '@/features/courses/FragmentPicker'
import type { FragmentBrief } from '@/features/library/api'
import { FILES, KIND_LABEL, workshopTasksApi, type AdminTask, type CheckReport, type CheckStatus, type SqlCheck, type TaskSpec } from '@/features/practice/api'
import { CodeEditor } from '@/features/practice/CodeEditor'
import { ApiError } from '@/lib/api'
import { useApi } from '@/lib/useApi'

type Section = 'statement' | 'starter' | 'solution' | 'tests'

const SECTIONS: { key: Section; label: string }[] = [
  { key: 'statement', label: 'Условие и подсказки' },
  { key: 'starter', label: 'Стартовый код' },
  { key: 'solution', label: 'Эталон' },
  { key: 'tests', label: 'Проверки' },
]

const STATUS: Record<CheckStatus, { label: string; tone: 'muted' | 'accent' | 'ai' | 'danger' }> = {
  not_checked: { label: 'автопроверка не запускалась', tone: 'muted' },
  queued: { label: 'автопроверка идёт…', tone: 'ai' },
  passed: { label: 'автопроверка пройдена', tone: 'accent' },
  failed: { label: 'автопроверка не пройдена', tone: 'danger' },
}

const TESTS_HELP: Record<'web' | 'python', string> = {
  web: "test('Название', () => { expect(условие, 'что не так') }) · { width: 375 } — проверка на телефоне · есть $, $$, style(el, 'свойство'), click(el), wait(мс)",
  python: 'def test_что_то(): с docstring — это название проверки; from main import функция; assert условие, "что не так"',
}

export function TaskEditorPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const loaded = useApi(() => workshopTasksApi.get(id), [id])

  const [task, setTask] = useState<AdminTask | null>(null)
  const [spec, setSpec] = useState<TaskSpec | null>(null)
  const [dirty, setDirty] = useState(false)
  const [section, setSection] = useState<Section>('statement')
  const [file, setFile] = useState<string>('')
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const [publishing, setPublishing] = useState(false)
  const [problems, setProblems] = useState<string[]>([])
  const [changeNote, setChangeNote] = useState('')
  const [picker, setPicker] = useState(false)
  const [fragments, setFragments] = useState<Record<number, FragmentBrief>>({})
  const [reveal, setReveal] = useState<{ line: number; key: number } | null>(null)
  const codeRef = useRef<HTMLDivElement>(null)
  const [params, setParams] = useSearchParams()

  const accept = useCallback((data: AdminTask) => {
    setTask(data)
    setSpec(data.editing.spec)
    setDirty(false)
    setFile((f) => f || FILES[data.editing.spec.kind][0])
  }, [])
  useEffect(() => {
    if (loaded.data) accept(loaded.data)
  }, [loaded.data, accept])

  // Замечание Ревьюера → эталон, нужный файл, строка подсвечена
  const jumpTo = useCallback((target: string, line: number | null) => {
    setSection('solution')
    setFile(target)
    if (line) setReveal({ line, key: Date.now() })
    window.setTimeout(() => codeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50)
  }, [])
  // Пришли из генерации по ссылке «открыть в эталоне»: ?file=index.html&line=9
  const jumpFile = params.get('file')
  const jumpLine = Number(params.get('line')) || null
  useEffect(() => {
    if (!task || !jumpFile) return
    jumpTo(jumpFile, jumpLine)
    setParams({}, { replace: true })
  }, [task, jumpFile, jumpLine, jumpTo, setParams])

  // Пока runner проверяет задание — обновляем статус раз в 2 секунды (без потери несохранённого)
  const queued = task?.editing.check_status === 'queued'
  useEffect(() => {
    if (!queued || !task) return
    const timer = window.setInterval(async () => {
      const fresh = await workshopTasksApi.get(task.id).catch(() => null)
      if (fresh && fresh.editing.check_status !== 'queued') setTask((t) => (t ? { ...t, editing: { ...t.editing, ...pickCheck(fresh) } } : t))
    }, 2000)
    return () => window.clearInterval(timer)
  }, [queued, task])

  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname)
  useEffect(() => {
    if (!dirty) return
    const handler = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  if (loaded.error) return <ErrorBlock message={loaded.error.message} onRetry={loaded.reload} />
  if (!task || !spec) return <Skeleton lines={5} />

  const editable = !!task.draft_version
  const kind = spec.kind
  const change = (patch: Partial<TaskSpec>) => {
    setSpec((s) => (s ? { ...s, ...patch } : s))
    setDirty(true)
  }

  const run = async (label: string, action: () => Promise<AdminTask | void>, success?: string) => {
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

  const save = () => run('save', () => workshopTasksApi.save(task.id, task.draft_version!, spec), 'Черновик сохранён')
  const check = async () => {
    if (dirty && !(await save())) return
    await run('check', () => workshopTasksApi.check(task.id))
  }
  const publish = async () => {
    setProblems([])
    if (dirty && !(await save())) return
    setBusy('publish')
    try {
      accept(await workshopTasksApi.publish(task.id, changeNote))
      setPublishing(false)
      setMessage({ tone: 'ok', text: 'Опубликовано. Задание появилось в «Практике».' })
    } catch (e) {
      const body = e instanceof ApiError ? (e.body as { problems?: string[] } | null) : null
      setProblems(body?.problems ?? [e instanceof Error ? e.message : 'Не удалось опубликовать'])
    } finally {
      setBusy(null)
    }
  }

  const status = STATUS[task.editing.check_status]
  const stale = task.editing.check_status !== 'not_checked' && task.editing.check_status !== 'queued' && (!task.editing.check_is_current || dirty)
  const files = FILES[kind]

  const codeSection = (part: 'starter' | 'solution') => (
    <div ref={codeRef} className="flex h-[60dvh] min-h-[420px] flex-col overflow-hidden rounded-lg border border-line">
      <FileTabs files={files} active={file} onChange={setFile} />
      <div className="min-h-0 flex-1">
        <CodeEditor
          path={`task-${task.id}/${part}/${file}`}
          label={`${part === 'starter' ? 'Стартовый код' : 'Эталон'}: ${file}`}
          value={spec[part][file] ?? ''}
          readOnly={!editable}
          reveal={part === 'solution' ? reveal : null}
          onChange={(code) => change({ [part]: { ...spec[part], [file]: code } } as Partial<TaskSpec>)}
        />
      </div>
    </div>
  )

  return (
    <div className="flex flex-col gap-6">
      <Link to="/workshop/content?tab=tasks" className="inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4" aria-hidden /> Все задания
      </Link>

      <header className="panel flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{KIND_LABEL[kind]}</Badge>
          {task.published_version && !task.archived && <Badge tone="accent">опубликовано · v{task.published_version}</Badge>}
          {task.archived && <Badge tone="danger">снято с публикации</Badge>}
          {task.draft_version && <Badge tone="ai">черновик · v{task.draft_version}</Badge>}
          <Badge tone={stale ? 'muted' : status.tone}>
            {queued && <LoaderCircle className="size-3 animate-spin" aria-hidden />}
            {stale ? 'после правок нужна новая автопроверка' : status.label}
          </Badge>
          {dirty && <Badge tone="ai">есть несохранённые изменения</Badge>}
        </div>
        {editable ? (
          <TextField label="Название задания" value={spec.title} onChange={(e) => change({ title: e.target.value })} />
        ) : (
          <h1 className="text-2xl font-semibold tracking-tight">{spec.title}</h1>
        )}
        <div className="flex flex-wrap gap-2 border-t border-line pt-4">
          {editable ? (
            <>
              <Button onClick={save} disabled={!dirty} loading={busy === 'save'} loadingText="Сохраняем…" icon={<Save className="size-4" />}>
                Сохранить
              </Button>
              <Button variant="secondary" onClick={check} loading={busy === 'check' || queued} loadingText="Проверяем…" icon={<ShieldCheck className="size-4" />}>
                Проверить задание
              </Button>
              <Button variant="secondary" onClick={() => (setProblems([]), setPublishing(true))} icon={<Rocket className="size-4" />}>
                Опубликовать…
              </Button>
            </>
          ) : (
            <Button onClick={() => run('draft', () => workshopTasksApi.startDraft(task.id))} loading={busy === 'draft'} icon={<Pencil className="size-4" />}>
              Редактировать (создать v{(task.published_version ?? 0) + 1})
            </Button>
          )}
          <ButtonLink to={`/practice/${task.slug}?version=${task.editing.number}`} variant="ghost" icon={<Eye className="size-4" />}>
            Глазами ученика{dirty ? ' (без несохранённого)' : ''}
          </ButtonLink>
          <span className="flex-1" />
          {task.published_version && (
            <Button variant="ghost" onClick={() => run('archive', () => workshopTasksApi.archive(task.id, !task.archived), task.archived ? 'Задание снова опубликовано' : 'Задание снято с публикации')}>
              {task.archived ? 'Вернуть в публикацию' : 'Снять с публикации'}
            </Button>
          )}
          {task.draft_version && task.published_version && (
            <Button variant="danger" onClick={() => run('discard', () => workshopTasksApi.discard(task.id), 'Черновик отменён')}>
              Отменить черновик
            </Button>
          )}
          {!task.published_version && (
            <Button
              variant="danger"
              icon={<Trash2 className="size-4" />}
              onClick={async () => {
                if (await run('delete', () => workshopTasksApi.remove(task.id))) {
                  setDirty(false)
                  navigate('/workshop/content?tab=tasks')
                }
              }}
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

      {task.editing.proposal && <ProposalPanel task={task} dirty={dirty} onResolved={accept} />}
      {task.editing.check_report && !queued && <CheckReportView report={task.editing.check_report} stale={stale} />}
      <ReferenceReview taskId={task.id} specKey={`${task.editing.number}:${JSON.stringify(task.editing.spec)}`} dirty={dirty} editable={editable} onJump={jumpTo} onChange={loaded.reload} />

      <div role="tablist" aria-label="Части задания" className="relative flex gap-1 overflow-x-auto border-b border-line">
        <Glider variant="underline" />
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            role="tab"
            aria-selected={section === s.key}
            onClick={() => setSection(s.key)}
            className={`relative z-[1] shrink-0 px-4 py-2.5 text-sm transition-colors duration-300 ${section === s.key ? 'font-medium text-text' : 'text-muted hover:text-text'}`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {section === 'statement' && (
        <div className="grid gap-5 lg:grid-cols-2">
          <TextArea
            label="Условие (markdown)"
            hint="Ваш текст: что сделать и какие критерии. Теорию сюда не пишем — привяжите статьи из библиотеки."
            value={spec.statement}
            readOnly={!editable}
            onChange={(e) => change({ statement: e.target.value })}
            className="[&_textarea]:min-h-[420px] [&_textarea]:font-mono [&_textarea]:text-[13px]"
          />
          <div className="flex flex-col gap-5">
            <ListEditor
              title="Подсказки"
              hint="Открываются по одной, от общей к конкретной. Каждая открытая подсказка отмечается в попытке."
              items={spec.hints}
              editable={editable}
              onChange={(hints) => change({ hints })}
            />
            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium">Теория к заданию</p>
              <ul className="flex flex-col gap-1.5">
                {spec.fragment_ids.map((fid) => (
                  <li key={fid} className="flex items-center gap-2 text-sm">
                    <Link to={`/library/${fid}`} target="_blank" className="flex-1 hover:text-accent">
                      {fragments[fid]?.title ?? `Статья №${fid}`}
                    </Link>
                    {editable && (
                      <button type="button" onClick={() => change({ fragment_ids: spec.fragment_ids.filter((x) => x !== fid) })} className="text-faint hover:text-danger" aria-label="Убрать статью">
                        <X className="size-4" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {editable && (
                <Button variant="ghost" className="-ml-3 w-fit" onClick={() => setPicker(true)} icon={<Plus className="size-4" />}>
                  Привязать статью
                </Button>
              )}
            </div>
          </div>
        </div>
      )}
      {section === 'starter' && (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">С этого кода ученик начинает. Он не должен проходить все проверки — иначе задание пустое.</p>
          {codeSection('starter')}
        </div>
      )}
      {section === 'solution' && (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted">Эталонное решение. Ученику не показывается; обязано пройти все проверки.</p>
          {codeSection('solution')}
        </div>
      )}
      {section === 'tests' &&
        (kind === 'sql' ? (
          <SqlChecksEditor spec={spec} editable={editable} taskId={task.id} onChange={change} />
        ) : (
          <div className="flex flex-col gap-2">
            <p className="font-mono text-xs text-muted">{TESTS_HELP[kind]}</p>
            <div className="h-[60dvh] min-h-[420px] overflow-hidden rounded-lg border border-line">
              <CodeEditor path={`task-${task.id}/tests.${kind === 'web' ? 'js' : 'py'}`} label="Проверки" value={spec.tests} readOnly={!editable} onChange={(tests) => change({ tests })} />
            </div>
          </div>
        ))}

      <FragmentPicker
        open={picker}
        onClose={() => setPicker(false)}
        taken={new Set(spec.fragment_ids)}
        onPick={(fragment) => {
          setFragments((f) => ({ ...f, [fragment.id]: fragment }))
          change({ fragment_ids: [...spec.fragment_ids, fragment.id] })
          setPicker(false)
        }}
      />

      <Dialog
        open={publishing}
        onClose={() => setPublishing(false)}
        title={`Опубликовать v${task.draft_version}`}
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
            Публикация возможна только после пройденной автопроверки этой самой версии.
            {task.published_version ? ' Кто уже решает прошлую версию, останется на ней и увидит предложение перейти.' : ''}
          </p>
          <TextArea label="Что изменилось (необязательно)" value={changeNote} onChange={(e) => setChangeNote(e.target.value)} />
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
        <p className="text-muted">Задание изменено, но не сохранено. Если уйти сейчас, изменения пропадут.</p>
      </Dialog>
    </div>
  )
}

function pickCheck(fresh: AdminTask) {
  const { check_status, check_report, check_is_current } = fresh.editing
  return { check_status, check_report, check_is_current }
}

function FileTabs({ files, active, onChange }: { files: string[]; active: string; onChange: (f: string) => void }) {
  return (
    <div role="tablist" aria-label="Файлы" className="relative flex shrink-0 gap-1 border-b border-line px-2">
      <Glider variant="underline" />
      {files.map((name) => (
        <button
          key={name}
          role="tab"
          aria-selected={name === active}
          onClick={() => onChange(name)}
          className={`relative z-[1] px-3 py-2 font-mono text-[13px] transition-colors duration-300 ${name === active ? 'text-text' : 'text-muted hover:text-text'}`}
        >
          {name}
        </button>
      ))}
    </div>
  )
}

function CheckReportView({ report, stale }: { report: CheckReport; stale: boolean }) {
  const ok = report.problems.length === 0
  const list = (title: string, part?: { results: { name: string; passed: boolean; message: string }[]; error: string | null }, expectPass?: boolean): ReactNode =>
    part && (
      <div>
        <p className="text-sm font-medium">{title}</p>
        {part.error && <p className="mt-1 text-sm text-danger">{part.error}</p>}
        <ul className="mt-1.5 flex flex-col gap-1">
          {part.results.map((r, i) => (
            <li key={i} className="flex gap-2 text-sm">
              {r.passed ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden /> : <CircleX className={`mt-0.5 size-4 shrink-0 ${expectPass ? 'text-danger' : 'text-muted'}`} aria-hidden />}
              <span className={r.passed ? 'text-muted' : ''}>
                {r.name}
                {!r.passed && r.message && <span className="block text-xs text-faint">{r.message}</span>}
              </span>
            </li>
          ))}
        </ul>
      </div>
    )

  return (
    <section aria-label="Отчёт автопроверки" className={`panel flex flex-col gap-4 p-5 ${ok ? '' : 'border-danger/40'}`}>
      <p className={`font-semibold ${ok ? 'text-accent' : 'text-danger'}`}>
        {ok ? 'Автопроверка пройдена: эталон проходит все проверки, стартовый код — нет.' : 'Автопроверка нашла проблемы'}
        {stale && <span className="ml-2 text-sm font-normal text-muted">(отчёт для прошлой редакции задания)</span>}
      </p>
      {!ok && (
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {report.problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {list('Эталон — должен пройти всё', report.solution, true)}
        {list('Стартовый код — должен что-то не пройти', report.starter)}
      </div>
    </section>
  )
}

function ListEditor({ title, hint, items, editable, onChange }: { title: string; hint: string; items: string[]; editable: boolean; onChange: (items: string[]) => void }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-medium">{title}</p>
      <p className="text-xs text-faint">{hint}</p>
      {items.map((item, i) => (
        <div key={i} className="flex items-start gap-2">
          <span className="mt-2 w-5 font-mono text-xs text-faint">{i + 1}.</span>
          <TextArea label={`${title}: ${i + 1}`} className="flex-1 [&_label]:sr-only [&_textarea]:mt-0 [&_textarea]:min-h-14" value={item} readOnly={!editable} onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))} />
          {editable && (
            <button type="button" onClick={() => onChange(items.filter((_, j) => j !== i))} className="mt-2 text-faint hover:text-danger" aria-label={`Удалить: ${title} ${i + 1}`}>
              <X className="size-4" />
            </button>
          )}
        </div>
      ))}
      {editable && items.length < 10 && (
        <Button variant="ghost" className="-ml-3 w-fit" onClick={() => onChange([...items, ''])} icon={<Plus className="size-4" />}>
          Добавить подсказку
        </Button>
      )}
    </div>
  )
}

function SqlChecksEditor({ spec, editable, taskId, onChange }: { spec: TaskSpec; editable: boolean; taskId: number; onChange: (patch: Partial<TaskSpec>) => void }) {
  const update = (i: number, patch: Partial<SqlCheck>) => onChange({ sql_checks: spec.sql_checks.map((c, j) => (j === i ? { ...c, ...patch } : c)) })
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">Схема и данные (выполняются перед запросом ученика)</p>
        <div className="h-[55dvh] min-h-[380px] overflow-hidden rounded-lg border border-line">
          <CodeEditor path={`task-${taskId}/setup.sql`} label="Схема и данные" value={spec.sql_setup} readOnly={!editable} onChange={(sql_setup) => onChange({ sql_setup })} />
        </div>
      </div>
      <div className="flex flex-col gap-3">
        <p className="text-sm font-medium">Проверки</p>
        <p className="text-xs text-faint">
          «Результат как у эталона» сравнивает таблицу ученика с результатом эталонного запроса (его посчитает автопроверка). «Условие» — ваш SELECT после кода ученика, должен вернуть истину.
        </p>
        {spec.sql_checks.map((c, i) => (
          <div key={i} className="flex flex-col gap-2 rounded-lg border border-line p-3">
            <div className="flex items-start gap-2">
              <TextField label="Название проверки" className="flex-1" value={c.name} readOnly={!editable} onChange={(e) => update(i, { name: e.target.value })} />
              {editable && (
                <button type="button" className="mt-9 text-faint hover:text-danger" onClick={() => onChange({ sql_checks: spec.sql_checks.filter((_, j) => j !== i) })} aria-label={`Удалить проверку ${i + 1}`}>
                  <Trash2 className="size-4" />
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-4 text-sm">
              {(['same_result', 'assert'] as const).map((type) => (
                <label key={type} className="flex items-center gap-2">
                  <input type="radio" disabled={!editable} checked={c.type === type} onChange={() => update(i, { type })} className="accent-[var(--accent)]" />
                  {type === 'same_result' ? 'Результат как у эталона' : 'Условие'}
                </label>
              ))}
              {c.type === 'same_result' && (
                <label className="flex items-center gap-2">
                  <input type="checkbox" disabled={!editable} checked={c.order_matters} onChange={(e) => update(i, { order_matters: e.target.checked })} className="accent-[var(--accent)]" />
                  важен порядок строк
                </label>
              )}
            </div>
            {c.type === 'assert' && <TextArea label="SELECT, который должен вернуть истину" className="[&_textarea]:font-mono [&_textarea]:text-[13px]" value={c.sql} readOnly={!editable} onChange={(e) => update(i, { sql: e.target.value })} />}
            <TextField label="Сообщение, если не прошла" value={c.message} readOnly={!editable} onChange={(e) => update(i, { message: e.target.value })} />
          </div>
        ))}
        {editable && (
          <Button variant="secondary" className="w-fit" onClick={() => onChange({ sql_checks: [...spec.sql_checks, { name: 'Новая проверка', type: 'same_result', sql: '', order_matters: false, message: '' }] })} icon={<Plus className="size-4" />}>
            Добавить проверку
          </Button>
        )}
      </div>
    </div>
  )
}

const PROPOSAL_LABEL = { statement: 'Условие', starter: 'Стартовый код', hints: 'Подсказки', sql_setup: 'Схема и данные SQL' } as const

/** Claude, исправляя эталон по замечаниям Ревьюера, сам меняет только эталон и тесты. Условие, стартовый код
 *  и подсказки — то, что видит ученик и по чему судит Ревьюер: их правку применяет только админ. */
function ProposalPanel({ task, dirty, onResolved }: { task: AdminTask; dirty: boolean; onResolved: (t: AdminTask) => void }) {
  const [busy, setBusy] = useState<'accept' | 'reject' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const proposal = task.editing.proposal!
  const spec = task.editing.spec
  const resolve = async (accept: boolean) => {
    setBusy(accept ? 'accept' : 'reject')
    setError(null)
    try {
      onResolved(await workshopTasksApi.proposal(task.id, accept))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не получилось')
    } finally {
      setBusy(null)
    }
  }
  const pairs: { label: string; before: string; after: string }[] = []
  if (proposal.fields.statement !== undefined) pairs.push({ label: PROPOSAL_LABEL.statement, before: spec.statement, after: proposal.fields.statement })
  if (proposal.fields.hints !== undefined) pairs.push({ label: PROPOSAL_LABEL.hints, before: spec.hints.join('\n\n'), after: proposal.fields.hints.join('\n\n') })
  if (proposal.fields.sql_setup !== undefined) pairs.push({ label: PROPOSAL_LABEL.sql_setup, before: spec.sql_setup, after: proposal.fields.sql_setup })
  for (const [file, code] of Object.entries(proposal.fields.starter ?? {})) {
    if ((spec.starter[file] ?? '') !== code) pairs.push({ label: `${PROPOSAL_LABEL.starter}: ${file}`, before: spec.starter[file] ?? '', after: code })
  }
  return (
    <section className="panel flex flex-col gap-4 border-ai/40 p-5" aria-labelledby="proposal-title">
      <div className="flex flex-col gap-1">
        <h2 id="proposal-title" className="font-semibold">
          Claude предлагает изменить задание
        </h2>
        <p className="text-sm text-muted">
          Исправляя эталон по замечаниям Ревьюера, Claude решил, что без этой правки не обойтись: {proposal.note}. Сам он её не применил — условие нельзя подгонять под
          код без вас. Пока правка не принята или не отклонена, задание не публикуется.
        </p>
      </div>
      {pairs.map((p) => (
        <div key={p.label} className="flex flex-col gap-1.5">
          <p className="text-sm font-medium">{p.label}</p>
          <div className="grid gap-2 lg:grid-cols-2">
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-bg/60 p-3 font-mono text-[12.5px]" aria-label="Было">
              <span className="mb-1 block font-sans text-xs text-faint">Было</span>
              {p.before || '—'}
            </pre>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-ai/40 bg-ai-soft/30 p-3 font-mono text-[12.5px]" aria-label="Станет">
              <span className="mb-1 block font-sans text-xs text-ai">Станет</span>
              {p.after || '—'}
            </pre>
          </div>
        </div>
      ))}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      <div className="flex flex-wrap gap-3">
        <Button onClick={() => resolve(true)} loading={busy === 'accept'} disabled={dirty || busy !== null} title={dirty ? 'Сначала сохраните задание' : undefined}>
          Принять правку
        </Button>
        <Button variant="ghost" onClick={() => resolve(false)} loading={busy === 'reject'} disabled={dirty || busy !== null}>
          Отклонить
        </Button>
      </div>
    </section>
  )
}
