import {
  CheckCircle2,
  ArrowLeft,
  ArrowUpToLine,
  ChevronDown,
  Columns2,
  CircleX,
  Lightbulb,
  LoaderCircle,
  Maximize2,
  Monitor,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  RotateCcw,
  ScanSearch,
  Rows2,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Tablet,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Glider } from '@/components/ui/Glider'

import { useMentor, useMentorContext } from '@/features/mentor/MentorProvider'
import { pollReview, reviewApi, type Review } from '@/features/review/api'
import { ReviewReport } from '@/features/review/ReviewReport'
import { ApiError } from '@/lib/api'

import { FILES, practiceApi, type CheckResult, type Files, type LearnerTask, type SqlTable } from './api'
import { CodeEditor } from './CodeEditor'
import { pyRunner } from './pyRunner'
import { checkWeb, mountSandbox, previewHtml } from './webRunner'

type Check = { results: CheckResult[]; error: string | null }
type Output =
  | { kind: 'python'; stdout: string; error: string | null }
  | { kind: 'sql'; table: SqlTable | null; error: string | null }
  | null
type Pane = 'code' | 'result'
type ResultTab = 'page' | 'output' | 'checks' | 'console' | 'review'
type PanelKey = 'editor' | 'result'
/** Рядом (колонки) или друг под другом: развёрнутая панель сверху на всю ширину, вторая — под ней */
type Layout = { mode: 'columns' | 'rows'; top: PanelKey }

const passedAll = (check: Check) => !check.error && check.results.length > 0 && check.results.every((r) => r.passed)

function stored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}
function store(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // приватный режим — настройка просто не запомнится
  }
}

type WorkspaceProps = {
  task: LearnerTask
  onChanged?: () => void
  /** куда ведёт «назад» в верхней полосе: к списку заданий или к уроку */
  backTo: string
  backLabel: string
  /** плашка над рабочим местом (например, «предпросмотр версии») */
  banner?: ReactNode
}

export function Workspace({ task, onChanged, backTo, backLabel, banner }: WorkspaceProps) {
  const [files, setFiles] = useState<Files>(task.files)
  const [active, setActive] = useState(FILES[task.kind][0])
  const [save, setSave] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [busy, setBusy] = useState<'check' | 'run' | null>(null)
  const [check, setCheck] = useState<Check | null>(null)
  const [output, setOutput] = useState<Output>(null)
  const [consoleLines, setConsoleLines] = useState<{ level: string; text: string }[]>([])
  const [hints, setHints] = useState(task.hints)
  const [hintError, setHintError] = useState<string | null>(null)
  const [solved, setSolved] = useState(task.solved)
  const [resetting, setResetting] = useState(false)
  const [pane, setPane] = useState<Pane>('code')
  const [resultTab, setResultTab] = useState<ResultTab>(task.kind === 'web' ? 'page' : 'output')
  const [layout, setLayoutState] = useState<Layout>(() => stored('rz.task.layout', { mode: 'columns', top: 'editor' }))
  const [statementOpen, setStatementOpen] = useState(() => stored('rz.task.statement', true))
  const [split, setSplit] = useState(() => stored('rz.task.split', 0.5))
  const [vsplit, setVsplit] = useState(() => stored('rz.task.vsplit', 0.62))
  const [sideWidth, setSideWidth] = useState(() => stored('rz.task.side', 380))
  const [pyLoading, setPyLoading] = useState(task.kind !== 'web')
  const mentor = useMentor()
  const [review, setReview] = useState<Review | null>(null)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [reveal, setReveal] = useState<{ line: number; key: number } | null>(null)
  const stopPoll = useRef<(() => void) | null>(null)

  // Последнее ревью этого задания — чтобы отчёт не пропадал после перезагрузки
  useEffect(() => {
    if (task.preview) return
    reviewApi.mine(task.slug).then(
      (list) => list[0] && (stopPoll.current = pollReview(list[0].id, setReview)),
      () => undefined,
    )
    return () => stopPoll.current?.()
  }, [task.slug, task.preview])

  const askReview = async () => {
    setReviewError(null)
    showResult('review')
    try {
      const started = await reviewApi.request(task.slug, files)
      setReview(started)
      stopPoll.current?.()
      stopPoll.current = pollReview(started.id, setReview)
    } catch (e) {
      setReviewError(e instanceof ApiError ? e.message : 'Не удалось отправить код Ревьюеру')
    }
  }
  const reviewing = review?.status === 'queued' || review?.status === 'running'
  const jumpTo = (file: string, line: number | null) => {
    setActive(file)
    setPane('code')
    if (line) setReveal({ line, key: Date.now() })
  }
  // Наставник видит условие и текущий код; черновик в предпросмотре админа ему не показываем
  useMentorContext(task.preview ? null : { kind: 'task', ref: task.slug, label: `Задание: ${task.title}`, getFiles: () => files })

  // Python грузится заранее, пока человек читает условие
  useEffect(() => {
    if (task.kind === 'web') return
    pyRunner.warmUp().then(
      () => setPyLoading(false),
      () => setPyLoading(false),
    )
  }, [task.kind])

  // Автосохранение через секунду после последней правки
  const first = useRef(true)
  useEffect(() => {
    if (first.current || task.preview) {
      first.current = false
      return
    }
    setSave('saving')
    const timer = window.setTimeout(() => {
      practiceApi.save(task.slug, files).then(
        () => setSave('saved'),
        () => setSave('error'),
      )
    }, 1000)
    return () => window.clearTimeout(timer)
  }, [files, task.slug, task.preview])

  const showResult = (tab: ResultTab) => {
    setResultTab(tab)
    setPane('result')
  }

  const setLayout = (next: Layout) => {
    setLayoutState(next)
    store('rz.task.layout', next)
  }

  const runCheck = async () => {
    setBusy('check')
    showResult('checks')
    let outcome: Check
    try {
      if (task.kind === 'web') outcome = await checkWeb(files, task.tests)
      else if (task.kind === 'python') outcome = await pyRunner.dispatch<Check>({ op: 'check_python', files, tests: task.tests })
      else
        outcome = await pyRunner.dispatch<Check>({
          op: 'check_sql',
          setup: task.sql_setup,
          script: files['query.sql'] ?? '',
          checks: task.sql_checks,
          expected: task.sql_expected,
        })
    } catch (e) {
      outcome = { results: [], error: e instanceof Error ? e.message : 'Проверка не удалась' }
    }
    setCheck(outcome)
    setBusy(null)
    const ok = passedAll(outcome)
    if (ok) setSolved(true)
    if (!task.preview) practiceApi.attempt(task.slug, ok, outcome.results).catch(() => undefined)
  }

  const run = async () => {
    setBusy('run')
    showResult('output')
    try {
      if (task.kind === 'python') {
        const r = await pyRunner.dispatch<{ stdout: string; error: string | null }>({ op: 'run_python', files })
        setOutput({ kind: 'python', stdout: r.stdout, error: r.error })
      } else {
        const r = await pyRunner.dispatch<{ result: SqlTable | null; error: string | null }>({ op: 'run_sql', setup: task.sql_setup, script: files['query.sql'] ?? '' })
        setOutput({ kind: 'sql', table: r.result, error: r.error })
      }
    } catch (e) {
      const error = e instanceof Error ? e.message : 'Не удалось выполнить'
      setOutput(task.kind === 'python' ? { kind: 'python', stdout: '', error } : { kind: 'sql', table: null, error })
    } finally {
      setBusy(null)
    }
  }

  const askHint = async () => {
    setHintError(null)
    setStatementOpen(true)
    try {
      const { hint } = await practiceApi.hint(task.slug)
      setHints((h) => [...h, hint])
    } catch (e) {
      setHintError(e instanceof Error ? e.message : 'Подсказка не загрузилась')
    }
  }

  const doReset = async () => {
    setFiles(task.starter)
    setCheck(null)
    setResetting(false)
    if (!task.preview) await practiceApi.reset(task.slug).catch(() => undefined)
  }

  const toggleStatement = () =>
    setStatementOpen((open) => {
      store('rz.task.statement', !open)
      return !open
    })

  const onConsole = useCallback((level: string, text: string) => setConsoleLines((lines) => [...lines.slice(-199), { level, text }]), [])
  const clearConsole = useCallback(() => setConsoleLines([]), [])

  const passed = check?.results.filter((r) => r.passed).length ?? 0
  const errorsInConsole = consoleLines.filter((l) => l.level === 'error').length
  const tabs: { key: ResultTab; label: string; badge?: ReactNode }[] = [
    task.kind === 'web' ? { key: 'page', label: 'Страница' } : { key: 'output', label: task.kind === 'sql' ? 'Таблица' : 'Вывод' },
    {
      key: 'checks',
      label: 'Проверки',
      badge: check && (
        <span className={`rounded-full px-1.5 font-mono text-[10px] ${passedAll(check) ? 'bg-accent-soft text-accent' : 'bg-danger-soft text-danger'}`}>
          {passed}/{check.results.length}
        </span>
      ),
    },
    ...(task.kind === 'web'
      ? [
          {
            key: 'console' as const,
            label: 'Консоль',
            badge: errorsInConsole > 0 && <span className="rounded-full bg-danger-soft px-1.5 font-mono text-[10px] text-danger">{errorsInConsole}</span>,
          },
        ]
      : []),
    ...(task.preview
      ? []
      : [
          {
            key: 'review' as const,
            label: 'Ревью',
            badge: review?.status === 'done' && review.findings.length > 0 && (
              <span className={`rounded-full px-1.5 font-mono text-[10px] ${review.verdict === 'pass' ? 'bg-surface-2 text-muted' : 'bg-ai-soft text-ai'}`}>{review.findings.length}</span>
            ),
          },
        ]),
  ]

  // ---------- условие, подсказки, теория: общий блок для боковой панели и мобильной шапки ----------
  const statementBody = (
    <div className="flex flex-col gap-5">
      <div className="prose-content text-[15px]" dangerouslySetInnerHTML={{ __html: task.statement_html }} />
      {hints.map((hint, i) => (
        <p key={i} className="rise-in flex gap-2 rounded-lg border border-ai/30 bg-ai-soft p-3 text-sm">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-ai" aria-hidden />
          <span>
            <span className="font-medium">Подсказка {i + 1}. </span>
            {hint}
          </span>
        </p>
      ))}
      {hintError && <p className="text-sm text-danger">{hintError}</p>}
      {task.fragments.length > 0 && (
        <div className="rounded-lg border border-line p-3 text-sm">
          <p className="font-medium">Теория к заданию</p>
          <ul className="mt-1.5 flex flex-col gap-1">
            {task.fragments.map((f) => (
              <li key={f.id}>
                <Link to={`/library/${f.id}`} target="_blank" className="text-accent hover:underline">
                  {f.title}
                </Link>{' '}
                <span className="text-faint">· {f.source}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )

  const hintButton = task.hints_total > 0 && hints.length < task.hints_total && !task.preview && (
    <Button variant="ghost" onClick={askHint} icon={<Lightbulb className="size-4" />}>
      Подсказка · {hints.length + 1}/{task.hints_total}
    </Button>
  )
  const reviewButton = !task.preview && (
    <Button variant="ghost" onClick={askReview} loading={reviewing} loadingText="Ревью…" icon={<ScanSearch className="size-4" />} title="Независимый Ревьюер проверит код по правилам: безопасность, корректность, семантика">
      Ревью кода
    </Button>
  )
  const solvedBadge = solved && (
    <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-accent/40 bg-accent-soft px-3 py-1 text-sm text-accent" role="status">
      <CheckCircle2 className="size-4" aria-hidden /> решено
    </span>
  )
  const runButtons = (
    <>
      {task.kind !== 'web' && (
        <Button variant="secondary" onClick={run} loading={busy === 'run'} disabled={busy !== null || pyLoading} icon={<Play className="size-4" />}>
          Запустить
        </Button>
      )}
      <Button onClick={runCheck} loading={busy === 'check'} loadingText="Проверяем…" disabled={busy !== null || pyLoading} icon={<ShieldCheck className="size-4" />} className="max-sm:w-full">
        Проверить
      </Button>
    </>
  )

  // ---------- телефон и планшет: сворачиваемая шапка с условием ----------
  const mobileHeader = (
    <section aria-label="Условие задания" className="panel overflow-hidden xl:hidden">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5">
        <div className="min-w-0 flex-1">
          <p className="eyebrow">Задание · v{task.version}</p>
          <h1 className="mt-1 text-lg font-semibold">{task.title}</h1>
        </div>
        {solvedBadge}
        {hintButton}
        <Button variant="secondary" onClick={toggleStatement} aria-expanded={statementOpen} icon={<ChevronDown className={`size-4 transition-transform duration-300 ${statementOpen ? 'rotate-180' : ''}`} />}>
          {statementOpen ? 'Свернуть условие' : 'Показать условие'}
        </Button>
      </div>
      {/* grid-rows 0fr → 1fr: плавное раскрытие на любую высоту */}
      <div className={`grid transition-[grid-template-rows] duration-300 ease-[var(--ease)] ${statementOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
        <div className="min-h-0 overflow-hidden" inert={!statementOpen}>
          <div className="max-h-[50vh] overflow-y-auto border-t border-line px-5 py-5">{statementBody}</div>
        </div>
      </div>
    </section>
  )

  // ---------- компьютер: тонкая верхняя полоса, как в LeetCode / freeCodeCamp ----------
  const topBar = (
    <header className="hidden h-14 shrink-0 items-center gap-3 border-b border-line bg-surface/70 px-4 backdrop-blur xl:flex">
      <Link to={backTo} className="group inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted hover:bg-surface-2 hover:text-text">
        <ArrowLeft className="size-4 transition-transform" aria-hidden /> {backLabel}
      </Link>
      <span className="h-5 w-px bg-line" aria-hidden />
      <h1 className="min-w-0 truncate font-semibold">{task.title}</h1>
      <span className="shrink-0 font-mono text-xs text-faint">v{task.version}</span>
      {solvedBadge}
      <span className="flex-1" />
      {hintButton}
      {reviewButton}
      {!task.preview && (
        <Button variant="ghost" onClick={() => mentor.setOpen(true)} icon={<Sparkles className="size-4" />} className="text-ai hover:text-ai">
          Наставник
        </Button>
      )}
      <div className="relative flex shrink-0 rounded-md border border-line p-0.5" role="group" aria-label="Раскладка">
        <Glider />
        {(
          [
            ['columns', 'Код и результат рядом', Columns2],
            ['rows', 'Код и результат друг под другом', Rows2],
          ] as const
        ).map(([mode, label, Icon]) => (
          <button
            key={mode}
            type="button"
            onClick={() => setLayout({ mode, top: layout.top })}
            aria-pressed={layout.mode === mode}
            title={label}
            className={`relative z-[1] grid size-8 place-items-center rounded-[5px] transition-colors duration-300 ${layout.mode === mode ? 'text-accent' : 'text-muted hover:text-text'}`}
          >
            <Icon className="size-4" aria-hidden />
            <span className="sr-only">{label}</span>
          </button>
        ))}
      </div>
      <Button variant="ghost" onClick={() => setResetting(true)} icon={<RotateCcw className="size-4" />} aria-label="Сбросить код" title="Вернуть стартовый код" />
      {runButtons}
    </header>
  )

  // ---------- компьютер: условие — левая панель во всю высоту, сворачивается в полосу ----------
  const side = (
    <aside aria-label="Условие задания" className="panel hidden min-h-0 flex-col overflow-hidden xl:flex">
      {statementOpen ? (
        <>
          <div className="flex shrink-0 items-center justify-between border-b border-line py-1.5 pl-4 pr-1.5">
            <p className="eyebrow">Условие</p>
            <button type="button" onClick={toggleStatement} className="grid size-8 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-text" aria-label="Свернуть условие" title="Свернуть условие">
              <PanelLeftClose className="size-4" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-5">{statementBody}</div>
        </>
      ) : (
        <button type="button" onClick={toggleStatement} className="flex h-full flex-col items-center gap-3 py-3 text-muted hover:bg-surface-2/50 hover:text-text" aria-label="Показать условие" title="Показать условие">
          <PanelLeftOpen className="size-4" aria-hidden />
          <span className="eyebrow [writing-mode:vertical-rl]">Условие{hints.length ? ` · подсказок ${hints.length}` : ''}</span>
        </button>
      )}
    </aside>
  )

  // ---------- редактор ----------
  const editor = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b border-line pl-2 pr-1">
        <div role="tablist" aria-label="Файлы" className="relative flex min-w-0 items-center gap-1 overflow-x-auto">
          <Glider variant="underline" />
          {FILES[task.kind].map((name) => (
            <button
              key={name}
              role="tab"
              aria-selected={name === active}
              onClick={() => setActive(name)}
              className={`relative z-[1] shrink-0 px-3 py-2.5 font-mono text-[13px] transition-colors duration-300 ${name === active ? 'text-text' : 'text-muted hover:text-text'}`}
            >
              {name}
            </button>
          ))}
        </div>
        <span className="ml-auto shrink-0 px-2 text-xs text-faint" role="status">
          {task.preview ? 'предпросмотр — не сохраняется' : save === 'saving' ? 'сохраняем…' : save === 'saved' ? 'сохранено' : save === 'error' ? <span className="text-danger">не сохранилось</span> : ''}
        </span>
        <LayoutButtons panel="editor" layout={layout} setLayout={setLayout} label="редактор" />
      </div>
      <div className="min-h-0 flex-1">
        <CodeEditor path={`${task.slug}/${active}`} label={`Код: ${active}`} value={files[active] ?? ''} onChange={(code) => setFiles((f) => ({ ...f, [active]: code }))} reveal={reveal} />
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-line p-3 xl:hidden">
        <Button variant="ghost" onClick={() => setResetting(true)} icon={<RotateCcw className="size-4" />} aria-label="Сбросить код" title="Вернуть стартовый код">
          <span className="max-2xl:sr-only">Сбросить</span>
        </Button>
        {pyLoading && <span className="text-xs text-faint">Загружаем Python в браузер…</span>}
        <span className="flex-1" />
        {runButtons}
      </div>
    </div>
  )

  // ---------- результат: вкладки занимают всю высоту панели ----------
  const result = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b border-line pl-2 pr-1">
        <div role="tablist" aria-label="Результат" className="relative flex min-w-0 items-center gap-1 overflow-x-auto">
          <Glider variant="underline" />
          {tabs.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={resultTab === t.key}
              onClick={() => setResultTab(t.key)}
              className={`relative z-[1] inline-flex shrink-0 items-center gap-1.5 px-3 py-2.5 text-[13px] transition-colors duration-300 ${resultTab === t.key ? 'font-medium text-text' : 'text-muted hover:text-text'}`}
            >
              {t.label}
              {t.badge}
            </button>
          ))}
        </div>
        <span className="flex-1" />
        <LayoutButtons panel="result" layout={layout} setLayout={setLayout} label="результат" />
      </div>
      <div className="relative min-h-0 flex-1">
        {/* Вкладки не размонтируются: превью страницы не перезагружается при переключении */}
        {task.kind === 'web' && (
          <div className={`absolute inset-0 ${resultTab === 'page' ? '' : 'invisible'}`}>
            <WebPreview files={files} onConsole={onConsole} onReset={clearConsole} />
          </div>
        )}
        {task.kind !== 'web' && (
          <div className={`absolute inset-0 overflow-auto p-4 ${resultTab === 'output' ? '' : 'invisible'}`}>
            <OutputView output={output} busy={busy === 'run'} kind={task.kind} />
          </div>
        )}
        <div className={`absolute inset-0 overflow-auto p-4 ${resultTab === 'checks' ? '' : 'invisible'}`}>
          {busy === 'check' ? (
            <p className="flex items-center gap-2 text-sm text-muted">
              <LoaderCircle className="size-4 animate-spin" aria-hidden /> Проверяем{task.kind === 'web' ? ' на ширинах 1280, 768 и 375 px…' : '…'}
            </p>
          ) : check ? (
            <CheckView check={check} />
          ) : (
            <p className="text-sm text-muted">Нажмите «Проверить» — здесь появится список требований: что уже выполнено, а что нет и почему.</p>
          )}
        </div>
        {!task.preview && (
          <div className={`absolute inset-0 overflow-auto p-4 ${resultTab === 'review' ? '' : 'invisible'}`}>
            {reviewError && (
              <p role="alert" className="mb-3 text-sm text-danger">
                {reviewError}
              </p>
            )}
            {review ? (
              <ReviewReport review={review} onJump={jumpTo} />
            ) : (
              <div className="flex flex-col gap-3 text-sm text-muted">
                <p>
                  «Ревью кода» отправляет код независимому Ревьюеру. Он не знает, кто вы, и видит только условие и код. Проверяет по правилам: корректность, безопасность,
                  семантику и доступность, читаемость. Каждое замечание — со строкой и сценарием, когда код сломается.
                </p>
                <Button variant="secondary" onClick={askReview} icon={<ScanSearch className="size-4" />} className="w-fit">
                  Ревью кода
                </Button>
              </div>
            )}
          </div>
        )}
        {task.kind === 'web' && (
          <div className={`absolute inset-0 overflow-auto p-3 ${resultTab === 'console' ? '' : 'invisible'}`}>
            <pre className="font-mono text-xs leading-relaxed">
              {consoleLines.length === 0 ? (
                <span className="text-faint">Здесь появятся console.log и ошибки скрипта страницы</span>
              ) : (
                consoleLines.map((l, i) => (
                  <span key={i} className={`block border-b border-line/60 py-1 ${l.level === 'error' ? 'text-danger' : l.level === 'warn' ? 'text-ai' : ''}`}>
                    {l.text}
                  </span>
                ))
              )}
            </pre>
          </div>
        )}
      </div>
    </div>
  )

  const rows = layout.mode === 'rows'
  // В режиме «друг под другом» порядок панелей задаёт CSS order: верхняя — 0, разделитель — 1, нижняя — 2
  const order = (panel: PanelKey) => (rows ? (layout.top === panel ? 0 : 2) : panel === 'editor' ? 0 : 2)

  return (
    // На компьютере — режим приложения: ровно высота окна, страница не прокручивается (как LeetCode, freeCodeCamp)
    <div className="flex flex-col gap-4 xl:h-dvh xl:gap-0">
      <Link to={backTo} className="inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text xl:hidden">
        <ArrowLeft className="size-4" aria-hidden /> {backLabel}
      </Link>
      {topBar}
      {(banner || task.has_update) && (
        <div className="flex flex-col gap-2 xl:px-2 xl:pt-2">
          {banner}
          {task.has_update && <UpgradeNote slug={task.slug} onDone={onChanged} />}
        </div>
      )}
      {mobileHeader}
      {pyLoading && <p className="hidden px-4 pt-2 text-xs text-faint xl:block">Загружаем Python в браузер — первый раз это несколько секунд…</p>}

      {/* Телефон и планшет: код и результат вкладками */}
      <div role="tablist" aria-label="Рабочая зона" className="relative grid grid-cols-2 rounded-md border border-line bg-surface-2/50 p-1 text-sm xl:hidden">
        <Glider className="!bg-surface shadow-sm" />
        {(
          [
            ['code', 'Код'],
            ['result', 'Результат'],
          ] as const
        ).map(([key, label]) => (
          <button key={key} role="tab" aria-selected={pane === key} onClick={() => setPane(key)} className={`relative z-[1] rounded-[6px] py-1.5 font-medium transition-colors duration-300 ${pane === key ? 'text-text' : 'text-muted'}`}>
            {label}
          </button>
        ))}
      </div>

      <div
        className="flex min-h-0 flex-col gap-4 xl:grid xl:flex-1 xl:gap-0 xl:p-2"
        style={{ gridTemplateColumns: statementOpen ? `${sideWidth}px 8px minmax(0,1fr)` : '44px 8px minmax(0,1fr)' }}
      >
        {side}
        <WidthHandle
          hidden={!statementOpen}
          width={sideWidth}
          onWidth={(w) => (setSideWidth(w), store('rz.task.side', w))}
        />
      <SplitArea
        rows={rows}
        ratio={rows ? vsplit : split}
        onRatio={(v) => (rows ? (setVsplit(v), store('rz.task.vsplit', v)) : (setSplit(v), store('rz.task.split', v)))}
      >
        <section aria-label="Редактор" style={{ order: order('editor') }} className={`panel h-[72dvh] min-h-0 overflow-hidden xl:h-full ${pane !== 'code' ? 'max-xl:hidden' : ''}`}>
          {editor}
        </section>
        <section aria-label="Результат" style={{ order: order('result') }} className={`panel h-[72dvh] min-h-0 overflow-hidden xl:h-full ${pane !== 'result' ? 'max-xl:hidden' : ''}`}>
          {result}
        </section>
      </SplitArea>
      </div>

      <Dialog
        open={resetting}
        onClose={() => setResetting(false)}
        title="Вернуть стартовый код?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setResetting(false)} data-autofocus>
              Отмена
            </Button>
            <Button variant="danger" onClick={doReset}>
              Сбросить код
            </Button>
          </>
        }
      >
        <p className="text-muted">Ваш код во всех файлах заменится стартовым. Это нельзя отменить.</p>
      </Dialog>
    </div>
  )
}

/**
 * Две панели с перетаскиваемым разделителем (на компьютере): рядом или друг под другом.
 * Тянуть мышью или стрелками с клавиатуры; двойной клик — вернуть исходное соотношение.
 */
function SplitArea({ rows, ratio, onRatio, children }: { rows: boolean; ratio: number; onRatio: (v: number) => void; children: [ReactNode, ReactNode] }) {
  const area = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)
  const clamp = (v: number) => Math.min(rows ? 0.8 : 0.75, Math.max(rows ? 0.2 : 0.25, v))

  const onPointerDown = (event: PointerEvent) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    setDragging(true)
  }
  const onPointerMove = (event: PointerEvent) => {
    if (!dragging || !area.current) return
    const rect = area.current.getBoundingClientRect()
    onRatio(clamp(rows ? (event.clientY - rect.top) / rect.height : (event.clientX - rect.left) / rect.width))
  }
  const track = `${ratio}fr 12px ${1 - ratio}fr`

  return (
    <div
      ref={area}
      // Пока тянем разделитель, iframe превью не должен перехватывать мышь
      className={`flex flex-col gap-4 xl:grid xl:h-full xl:min-h-0 xl:gap-0 ${dragging ? `${rows ? 'cursor-row-resize' : 'cursor-col-resize'} select-none [&_iframe]:pointer-events-none` : ''}`}
      style={rows ? { gridTemplateRows: track, gridTemplateColumns: '1fr' } : { gridTemplateColumns: track }}
    >
      {children[0]}
      <div
        role="separator"
        aria-orientation={rows ? 'horizontal' : 'vertical'}
        aria-label="Граница между редактором и результатом"
        aria-valuemin={rows ? 20 : 25}
        aria-valuemax={rows ? 80 : 75}
        aria-valuenow={Math.round(ratio * 100)}
        tabIndex={0}
        style={{ order: 1 }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => setDragging(false)}
        onDoubleClick={() => onRatio(rows ? 0.62 : 0.5)}
        onKeyDown={(e) => {
          const less = rows ? 'ArrowUp' : 'ArrowLeft'
          const more = rows ? 'ArrowDown' : 'ArrowRight'
          if (e.key === less) onRatio(clamp(ratio - 0.05))
          if (e.key === more) onRatio(clamp(ratio + 0.05))
        }}
        className={`group hidden items-center justify-center xl:flex ${rows ? 'cursor-row-resize' : 'cursor-col-resize'}`}
        title={`Потяните, чтобы поменять ${rows ? 'высоту' : 'ширину'}. Двойной клик — как было`}
      >
        <span
          className={`rounded-full transition-colors ${rows ? 'h-1 w-12' : 'h-12 w-1'} ${dragging ? 'bg-accent' : 'bg-line-strong group-hover:bg-accent/70 group-focus-visible:bg-accent'}`}
        />
      </div>
      {children[1]}
    </div>
  )
}

/** Разделитель между условием и рабочей зоной: тянется мышью или стрелками, двойной клик — 380 px. */
function WidthHandle({ hidden, width, onWidth }: { hidden: boolean; width: number; onWidth: (w: number) => void }) {
  const [drag, setDrag] = useState<{ x: number; w: number } | null>(null)
  const clamp = (w: number) => Math.round(Math.min(640, Math.max(260, w)))
  if (hidden) return <div className="hidden xl:block" aria-hidden />
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Ширина условия"
      aria-valuemin={260}
      aria-valuemax={640}
      aria-valuenow={width}
      tabIndex={0}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId)
        setDrag({ x: e.clientX, w: width })
      }}
      onPointerMove={(e) => drag && onWidth(clamp(drag.w + e.clientX - drag.x))}
      onPointerUp={() => setDrag(null)}
      onDoubleClick={() => onWidth(380)}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') onWidth(clamp(width - 24))
        if (e.key === 'ArrowRight') onWidth(clamp(width + 24))
      }}
      className="group hidden cursor-col-resize items-center justify-center xl:flex"
      title="Потяните, чтобы поменять ширину условия. Двойной клик — как было"
    >
      <span className={`h-12 w-1 rounded-full transition-colors ${drag ? 'bg-accent' : 'bg-line-strong group-hover:bg-accent/70 group-focus-visible:bg-accent'}`} />
    </div>
  )
}

/** Кнопки раскладки в шапке панели (только на компьютере). */
function LayoutButtons({ panel, layout, setLayout, label }: { panel: PanelKey; layout: Layout; setLayout: (l: Layout) => void; label: string }) {
  const tool = 'hidden size-8 shrink-0 place-items-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-text xl:grid'
  if (layout.mode === 'columns') {
    return (
      <button type="button" className={tool} onClick={() => setLayout({ mode: 'rows', top: panel })} aria-label={`Развернуть ${label} на всю ширину`} title="На всю ширину — вторая панель переедет вниз">
        <Maximize2 className="size-4" />
      </button>
    )
  }
  return (
    <span className="flex shrink-0 items-center">
      {layout.top !== panel && (
        <button type="button" className={tool} onClick={() => setLayout({ mode: 'rows', top: panel })} aria-label={`Поднять ${label} наверх`} title="Поднять наверх">
          <ArrowUpToLine className="size-4" />
        </button>
      )}
      <button type="button" className={tool} onClick={() => setLayout({ mode: 'columns', top: 'editor' })} aria-label="Поставить панели рядом" title="Вернуть рядом">
        <Columns2 className="size-4" />
      </button>
    </span>
  )
}

function CheckView({ check }: { check: Check }) {
  const passed = check.results.filter((r) => r.passed).length
  const ok = passedAll(check)
  return (
    <div className="rise-in flex flex-col gap-3" role="status">
      <p className={`font-semibold ${ok ? 'text-accent' : 'text-text'}`}>
        {ok ? 'Все проверки пройдены' : check.results.length ? `Пройдено ${passed} из ${check.results.length}` : 'Проверка не выполнилась'}
      </p>
      {check.error && <p className="rounded-lg border border-danger/40 bg-danger-soft p-3 text-sm">{check.error}</p>}
      <ul className="flex flex-col gap-2">
        {check.results.map((r, i) => (
          <li key={i} className="flex gap-2.5 text-sm">
            {r.passed ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" aria-label="Пройдено" /> : <CircleX className="mt-0.5 size-4 shrink-0 text-danger" aria-label="Не пройдено" />}
            <span>
              <span className={r.passed ? 'text-muted' : 'font-medium'}>{r.name}</span>
              {r.width && r.width !== 1280 && <span className="ml-1.5 font-mono text-[11px] text-faint">{r.width} px</span>}
              {!r.passed && r.message && <span className="block text-muted">{r.message}</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

const DEVICES = [
  { width: 0, label: 'По ширине панели', icon: Monitor },
  { width: 768, label: 'Планшет, 768 px', icon: Tablet },
  { width: 375, label: 'Телефон, 375 px', icon: Smartphone },
] as const

function WebPreview({ files, onConsole, onReset }: { files: Files; onConsole: (level: string, text: string) => void; onReset: () => void }) {
  const holder = useRef<HTMLDivElement>(null)
  const [device, setDevice] = useState<number>(0)

  useEffect(() => {
    let cleanup: (() => void) | undefined
    let cancelled = false
    // Превью обновляется через 0,6 с после последней правки, а не на каждую букву
    const timer = window.setTimeout(async () => {
      const html = await previewHtml(files)
      if (cancelled || !holder.current) return
      onReset()
      cleanup = mountSandbox(holder.current, html, (m) => m.type === 'console' && onConsole(m.level ?? 'log', m.text ?? ''))
    }, 600)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      cleanup?.()
    }
  }, [files, onConsole, onReset])

  return (
    <div className="flex h-full flex-col">
      <div className="relative flex shrink-0 items-center gap-1 px-3 py-2" role="group" aria-label="Ширина превью">
        <Glider className="!bg-accent-soft" />
        {DEVICES.map(({ width, label, icon: Icon }) => (
          <button
            key={width}
            type="button"
            onClick={() => setDevice(width)}
            aria-pressed={device === width}
            title={label}
            className={`relative z-[1] grid size-8 place-items-center rounded-md transition-colors duration-300 ${device === width ? 'text-accent' : 'text-muted hover:bg-surface-2 hover:text-text'}`}
          >
            <Icon className="size-4" aria-hidden />
            <span className="sr-only">{label}</span>
          </button>
        ))}
        <span className="ml-2 font-mono text-xs text-faint">{device ? `${device} px` : 'по ширине'}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto bg-[repeating-conic-gradient(var(--surface-2)_0_25%,transparent_0_50%)] bg-[length:16px_16px] px-3 pb-3">
        <div
          ref={holder}
          className="mx-auto h-full overflow-hidden rounded-lg border border-line bg-white transition-[width] duration-300 ease-[var(--ease)]"
          style={{ width: device ? `${device}px` : '100%', maxWidth: device ? 'none' : '100%' }}
        />
      </div>
    </div>
  )
}

function OutputView({ output, busy, kind }: { output: Output; busy: boolean; kind: 'web' | 'python' | 'sql' }) {
  if (busy) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted">
        <LoaderCircle className="size-4 animate-spin" aria-hidden /> Выполняем…
      </p>
    )
  }
  if (!output) {
    return <p className="text-sm text-muted">{kind === 'sql' ? '«Запустить» покажет результат запроса таблицей.' : '«Запустить» выполнит main.py и покажет вывод print().'}</p>
  }
  if (output.kind === 'python') {
    return (
      <pre className="rise-in overflow-auto font-mono text-xs leading-relaxed">
        {output.stdout || <span className="text-faint">(программа ничего не напечатала)</span>}
        {output.error && <span className="mt-2 block text-danger">{output.error}</span>}
      </pre>
    )
  }
  if (output.error) return <p className="rounded-lg border border-danger/40 bg-danger-soft p-3 text-sm">{output.error}</p>
  if (!output.table) return <p className="text-sm text-muted">Запрос выполнен, но не вернул строк-результата (например, это был INSERT или UPDATE).</p>
  return (
    <div className="rise-in flex flex-col gap-2">
      <p className="text-xs text-muted">Строк: {output.table.rows.length}</p>
      <div className="overflow-auto rounded-lg border border-line">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-surface-2">
            <tr>
              {output.table.columns.map((c, i) => (
                <th key={i} className="px-3 py-2 font-mono text-xs font-medium">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {output.table.rows.map((row, i) => (
              <tr key={i} className="border-t border-line">
                {row.map((cell, j) => (
                  <td key={j} className="px-3 py-1.5 font-mono text-xs">
                    {cell === null ? <span className="text-faint">NULL</span> : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function UpgradeNote({ slug, onDone }: { slug: string; onDone?: () => void }) {
  const [busy, setBusy] = useState(false)
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-ai/40 bg-ai-soft px-4 py-3 text-sm">
      <Sparkles className="size-4 text-ai" aria-hidden />
      <span className="flex-1">Задание обновилось. Ваш код сохранится, но проверки могли поменяться — задание нужно будет решить заново.</span>
      <Button
        variant="secondary"
        loading={busy}
        onClick={async () => {
          setBusy(true)
          await practiceApi.upgrade(slug).catch(() => undefined)
          onDone?.()
        }}
      >
        Перейти на новую версию
      </Button>
    </div>
  )
}
