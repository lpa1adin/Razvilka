import { ArrowLeft, ArrowRight, CheckCircle2, CircleX, ExternalLink, LoaderCircle, MousePointerClick, RotateCcw, Send, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'

import { Button, ButtonLink } from '@/components/ui/Button'
import { inputClass } from '@/components/ui/Field'
import { Glider } from '@/components/ui/Glider'
import { Badge, ErrorBlock, Skeleton } from '@/components/ui/States'
import { archApi, KIND_LABEL, LEVEL_LABEL, type Attempt, type Exercise, type Material } from '@/features/arch/api'
import { Diagram, Legend, NODE_H, NODE_W } from '@/features/arch/Diagram'
import { ApiError } from '@/lib/api'

export function ArchPage() {
  const { slug = '' } = useParams()
  const [ex, setEx] = useState<Exercise | null>(null)
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [counted, setCounted] = useState<Attempt | null>(null)
  const [next, setNext] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    setEx(null)
    setAttempt(null)
    archApi.get(slug).then(
      (d) => {
        setEx(d.exercise)
        setCounted(d.counted)
        setNext(d.next)
        // В «выборе» показываем засчитанный ответ: повторов там нет, а старые попытки — лишь история
        const shown = d.exercise.kind === 'choice' ? (d.counted ?? d.attempts[0]) : d.attempts[0]
        if (shown) follow(shown)
      },
      (e) => setError(e.message),
    )
    return () => window.clearTimeout(timer.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug])

  // «Своими словами» оценивается в очереди — опрашиваем, пока не готово
  const follow = (a: Attempt) => {
    setAttempt(a)
    if (a.counted) setCounted(a)
    window.clearTimeout(timer.current)
    if (a.status === 'evaluating') timer.current = window.setTimeout(() => archApi.attempt(a.id).then(follow, () => undefined), 2500)
  }

  // Новая попытка: прошлый результат убираем с экрана, он остаётся в истории
  const reset = () => {
    window.clearTimeout(timer.current)
    setAttempt(null)
  }

  if (error) return <ErrorBlock message={error} />
  if (!ex) return <Skeleton lines={6} />

  return (
    <div className="rise-in mx-auto flex max-w-6xl flex-col gap-6">
      <Link to="/practice?tab=arch" className="inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4" aria-hidden /> Все задания тренажёра
      </Link>
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <Badge tone={ex.level === 'high' ? 'accent' : 'ai'}>{LEVEL_LABEL[ex.level]}</Badge>
          <Badge>{KIND_LABEL[ex.kind]}</Badge>
          <Badge>{ex.project}</Badge>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{ex.title}</h1>
        <p className="max-w-3xl text-[17px]">{ex.question}</p>
      </header>

      {ex.kind === 'diagram' ? (
        // Доске нужна вся ширина: материал сверху, пониже
        <>
          <Materials materials={ex.materials} compact />
          {attempt?.status === 'done' && <AttemptScore attempt={attempt} counted={counted} next={next} />}
        </>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <Materials materials={ex.materials} />
          <section className="flex min-w-0 flex-col gap-4" aria-label="Ответ">
            {ex.kind === 'choice' && <ChoiceAnswer ex={ex} attempt={attempt} onDone={follow} onReset={reset} counted={counted} next={next} />}
            {ex.kind === 'describe' && <DescribeAnswer ex={ex} attempt={attempt} onDone={follow} onReset={reset} counted={counted} next={next} />}
          </section>
        </div>
      )}
      {ex.kind === 'diagram' && <DiagramAnswer ex={ex} attempt={attempt} onDone={follow} onReset={reset} counted={counted} next={next} />}
      {attempt?.status === 'done' && attempt.reveal && <RevealBlock attempt={attempt} />}
    </div>
  )
}

function Materials({ materials, compact }: { materials: Material[]; compact?: boolean }) {
  const [active, setActive] = useState(0)
  const m = materials[active]
  return (
    <section className="panel flex min-w-0 flex-col overflow-hidden" aria-label="Материал">
      <div role="tablist" aria-label="Файлы" className="relative flex gap-1 overflow-x-auto border-b border-line px-2">
        <Glider variant="underline" />
        {materials.map((x, i) => (
          <button key={x.path} role="tab" aria-selected={i === active} onClick={() => setActive(i)}
            className={`relative z-[1] shrink-0 px-3 py-2.5 font-mono text-[13px] transition-colors ${i === active ? 'text-text' : 'text-muted hover:text-text'}`}>
            {x.path}
          </button>
        ))}
      </div>
      <pre className={`${compact ? 'max-h-[34vh]' : 'max-h-[62vh]'} overflow-auto py-3 font-mono text-[12.5px] leading-relaxed`}>
        {m.text.replace(/\n$/, '').split('\n').map((line, i) => (
          <span key={i} className="block px-4 hover:bg-surface-2/50">
            <span className="mr-4 inline-block w-7 select-none text-right text-faint">{i + 1}</span>
            {line || ' '}
          </span>
        ))}
      </pre>
      <p className="flex flex-wrap items-center gap-x-2 border-t border-line px-4 py-2 text-xs text-faint">
        {m.project} · {m.license}
        {m.note && <span className="text-ai">· {m.note}</span>}
        {m.url && (
          <a href={m.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-accent hover:underline">
            оригинал на коммите <ExternalLink className="size-3" aria-hidden />
          </a>
        )}
      </p>
    </section>
  )
}

function AttemptScore({ attempt, counted, next }: { attempt: Attempt; counted: Attempt | null; next: string | null }) {
  if (attempt.score === null) return null
  const good = attempt.score >= 4
  return (
    <div className={`flex flex-wrap items-center gap-3 rounded-lg border p-4 ${good ? 'border-accent/40 bg-accent-soft/50' : 'border-ai/40 bg-ai-soft/40'}`} role="status">
      {good ? <CheckCircle2 className="size-6 text-accent" aria-hidden /> : <CircleX className="size-6 text-ai" aria-hidden />}
      <div className="min-w-[220px] flex-1">
        <p className="font-semibold">
          {attempt.score.toFixed(1)} из 5 · {attempt.counted ? 'засчитано' : 'тренировка'}
        </p>
        <p className="text-sm text-muted">
          {attempt.counted
            ? 'Засчитывается первый ответ: после него открыт разбор, и повтор уже ничего не проверяет.'
            : `На балл не влияет — засчитан первый ответ${counted?.score != null ? `: ${counted.score.toFixed(1)} из 5` : ''}.`}
        </p>
      </div>
      {next && (
        <ButtonLink to={`/practice/arch/${next}`} variant="secondary" icon={<ArrowRight className="size-4" />}>
          Следующее задание
        </ButtonLink>
      )}
    </div>
  )
}

type AnswerProps = { ex: Exercise; attempt: Attempt | null; onDone: (a: Attempt) => void; onReset: () => void; counted: Attempt | null; next: string | null }

function ChoiceAnswer({ ex, attempt, onDone, counted, next }: AnswerProps) {
  const [picked, setPicked] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const correct = new Set(attempt?.reveal?.correct ?? [])
  const answered = new Set(attempt?.answer.picked ?? [])
  const reviewing = attempt?.status === 'done'

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      onDone(await archApi.submit(ex.slug, { picked }))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не получилось')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {reviewing && <AttemptScore attempt={attempt!} counted={counted} next={next} />}
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 text-sm text-muted">{ex.multiple ? 'Отметьте все верные' : 'Один ответ'}</legend>
        {ex.options!.map((o) => {
          const on = reviewing ? answered.has(o.id) : picked.includes(o.id)
          const tone = reviewing ? (correct.has(o.id) ? 'border-accent/60 bg-accent-soft' : on ? 'border-danger/60 bg-danger-soft' : 'border-line') : on ? 'border-accent bg-accent-soft' : 'border-line hover:border-line-strong'
          return (
            <label key={o.id} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3.5 text-[15px] transition-colors ${tone}`}>
              <input type={ex.multiple ? 'checkbox' : 'radio'} name="arch-choice" checked={on} disabled={reviewing}
                onChange={() => setPicked((p) => (ex.multiple ? (p.includes(o.id) ? p.filter((x) => x !== o.id) : [...p, o.id]) : [o.id]))}
                className="mt-1 size-4 shrink-0 accent-[var(--accent)]" />
              <span>{o.text.split(/(`[^`]+`)/).map((part, i) => (part.startsWith('`') ? <code key={i} className="rounded border border-line bg-surface-2 px-1 font-mono text-[0.9em]">{part.slice(1, -1)}</code> : part))}</span>
            </label>
          )
        })}
      </fieldset>
      {error && <p className="text-sm text-danger">{error}</p>}
      {reviewing ? null : (
        <>
          <p className="text-xs text-faint">Засчитывается первый ответ — после него откроется разбор.</p>
          <Button onClick={submit} loading={busy} disabled={!picked.length} icon={<Send className="size-4" />} className="w-fit">
            Ответить
          </Button>
        </>
      )}
    </div>
  )
}

const COLUMN: Record<string, number> = { proxy: 0, app: 1, class: 1, function: 1, broker: 2, cache: 2, db: 3, external: 3, monitoring: 4 }

function initialPositions(nodes: { id: string; kind: string }[]) {
  const cols = new Map<number, string[]>()
  nodes.forEach((n) => {
    const c = COLUMN[n.kind] ?? 1
    cols.set(c, [...(cols.get(c) ?? []), n.id])
  })
  const order = [...cols.keys()].sort((a, b) => a - b)
  const pos: Record<string, { x: number; y: number }> = {}
  order.forEach((c, ci) => cols.get(c)!.forEach((id, i) => (pos[id] = { x: 16 + ci * (NODE_W + 60), y: 16 + i * (NODE_H + 22) })))
  return pos
}

function DiagramAnswer({ ex, attempt, onDone, onReset }: AnswerProps) {
  const nodes = ex.nodes!
  const [positions, setPositions] = useState(() => initialPositions(nodes))
  const [edges, setEdges] = useState<[string, string][]>([])
  const [from, setFrom] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const checked = attempt?.status === 'done' ? attempt : null
  const shown: [string, string][] = checked ? [...(checked.answer.edges ?? []), ...(checked.result?.missed ?? [])] : edges
  const tones = useMemo(() => {
    if (!checked?.result) return {}
    const t: Record<string, 'ok' | 'reversed' | 'extra' | 'missed'> = {}
    checked.result.matched?.forEach(([a, b]) => (t[`${a}->${b}`] = 'ok'))
    checked.result.reversed?.forEach(([a, b]) => (t[`${a}->${b}`] = 'reversed'))
    checked.result.extra?.forEach(([a, b]) => (t[`${a}->${b}`] = 'extra'))
    checked.result.missed?.forEach(([a, b]) => (t[`${a}->${b}`] = 'missed'))
    return t
  }, [checked])

  const clickNode = (id: string) => {
    if (checked) return
    if (!from) return setFrom(id)
    if (from !== id && !edges.some(([a, b]) => a === from && b === id)) setEdges((e) => [...e, [from, id]])
    setFrom(null)
  }

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      onDone(await archApi.submit(ex.slug, { edges }))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не получилось')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel flex flex-col gap-3 p-4" aria-label="Схема">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-semibold">{checked ? 'Ваша схема после проверки' : 'Соберите схему'}</h2>
        {!checked && (
          <p className="flex items-center gap-1.5 text-sm text-muted">
            <MousePointerClick className="size-4" aria-hidden />
            {from ? <>Теперь щёлкните, <b className="font-medium text-text">куда</b> идёт стрелка из «{from}»</> : 'Щёлкните блок-источник, затем блок-цель. Блоки можно перетаскивать, стрелку — убрать щелчком.'}
          </p>
        )}
        <span className="flex-1" />
        {checked && (
          <ul className="flex flex-wrap gap-3 text-xs">
            <li className="text-accent">— верно</li>
            <li className="text-ai">— направление перепутано</li>
            <li className="text-danger">- - лишняя</li>
            <li className="text-faint">- - пропущена</li>
          </ul>
        )}
      </div>
      <div className="overflow-x-auto rounded-lg border border-line bg-bg/50">
        <Diagram
          label="Схема ученика"
          graph={{ nodes, edges: shown.map(([a, b]) => ({ from: a, to: b })) }}
          positions={positions}
          tones={tones}
          selected={from}
          onMove={(id, x, y) => setPositions((p) => ({ ...p, [id]: { x, y } }))}
          onNodeClick={clickNode}
          onEdgeClick={checked ? undefined : (a, b) => setEdges((e) => e.filter(([x, y]) => !(x === a && y === b)))}
        />
      </div>
      <Legend kinds={nodes.map((n) => n.kind)} />
      {error && <p className="text-sm text-danger">{error}</p>}
      <div className="flex flex-wrap gap-3">
        {checked ? (
          <Button variant="secondary" onClick={() => (setEdges([]), onReset())} icon={<RotateCcw className="size-4" />}>
            Потренироваться ещё раз — на балл не влияет
          </Button>
        ) : (
          <>
            <Button onClick={submit} loading={busy} disabled={!edges.length} icon={<Send className="size-4" />}>
              Проверить схему · стрелок {edges.length}
            </Button>
            {edges.length > 0 && (
              <Button variant="ghost" onClick={() => setEdges([])}>
                Очистить
              </Button>
            )}
          </>
        )}
      </div>
    </section>
  )
}

function DescribeAnswer({ ex, attempt, onDone, onReset, counted, next }: AnswerProps) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const evaluating = attempt?.status === 'evaluating'
  const done = attempt?.status === 'done' ? attempt : null

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      onDone(await archApi.submit(ex.slug, { text }))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не получилось')
    } finally {
      setBusy(false)
    }
  }

  if (evaluating) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted" role="status">
        <LoaderCircle className="size-4 animate-spin text-ai" aria-hidden /> Проверяющий читает ваш ответ — обычно до минуты…
      </p>
    )
  }
  if (attempt?.status === 'failed') return <ErrorBlock message={attempt.error ?? 'Оценка не удалась'} />
  if (done?.result) {
    return (
      <div className="flex flex-col gap-3">
        <AttemptScore attempt={done} counted={counted} next={next} />
        <p className="text-sm">{done.result.feedback}</p>
        <ul className="flex flex-col gap-2">
          {done.result.points?.map((p) => (
            <li key={p.id} className={`rounded-lg border p-3 text-sm ${p.covered ? 'border-accent/40 bg-accent-soft/40' : 'border-line'}`}>
              <span className="flex items-start gap-2">
                {p.covered ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden /> : <CircleX className="mt-0.5 size-4 shrink-0 text-faint" aria-hidden />}
                <span>
                  <span className={p.covered ? '' : 'text-muted'}>{p.text}</span>
                  {p.quote && <span className="mt-1 block text-xs text-muted">«{p.quote}»</span>}
                  {!p.covered && p.comment && <span className="mt-1 block text-xs text-faint">{p.comment}</span>}
                </span>
              </span>
            </li>
          ))}
        </ul>
        {!!done.result.errors?.length && (
          <div className="rounded-lg border border-danger/40 bg-danger-soft/30 p-3 text-sm">
            <p className="font-medium text-danger">Фактические ошибки</p>
            <ul className="mt-1 flex flex-col gap-0.5">
              {done.result.errors.map((e, i) => (
                <li key={i}>• {e}</li>
              ))}
            </ul>
          </div>
        )}
        <Button variant="secondary" onClick={onReset} icon={<RotateCcw className="size-4" />} className="w-fit">
          Потренироваться ещё раз — на балл не влияет
        </Button>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted">
        Ответ оценивает Claude в отдельной сессии по {ex.keypoints_count} ключевым пунктам. Пункт засчитывается, только если его подтверждает цитата из вашего ответа.
      </p>
      <label className="sr-only" htmlFor="describe">
        Ваше описание
      </label>
      <textarea id="describe" className={`${inputClass} min-h-64 py-3 leading-relaxed`} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Тип архитектуры, как связаны части, где что выполняется, чем за это платят…" />
      <p className="text-xs text-faint">{text.trim().length} символов · нужно хотя бы 80</p>
      {error && <p className="text-sm text-danger">{error}</p>}
      <Button onClick={submit} loading={busy} disabled={text.trim().length < 80} icon={<Sparkles className="size-4" />} className="w-fit">
        Отправить на оценку
      </Button>
    </div>
  )
}

function RevealBlock({ attempt }: { attempt: Attempt }) {
  const r = attempt.reveal!
  return (
    <section className="flex flex-col gap-4" aria-labelledby="reveal-title">
      <div className="panel p-5">
        <h2 id="reveal-title" className="font-semibold">
          Разбор
        </h2>
        <p className="mt-2 text-[15px] text-muted">
          {r.explanation.split(/(`[^`]+`)/).map((part, i) => (part.startsWith('`') ? <code key={i} className="rounded border border-line bg-surface-2 px-1 font-mono text-[0.9em] text-text">{part.slice(1, -1)}</code> : part))}
        </p>
        {r.keypoints && (
          <ul className="mt-3 flex flex-col gap-1 text-sm">
            {r.keypoints.map((k) => (
              <li key={k.id}>• {k.text}</li>
            ))}
          </ul>
        )}
      </div>
      <div className="panel flex flex-col gap-3 p-4">
        <h3 className="font-semibold">
          Схема, которую построил генератор по <span className="font-mono text-sm">{r.auto_from}</span>
        </h3>
        <p className="text-sm text-muted">Без Claude — только то, что объявлено в файле. Пунктир — depends_on (порядок запуска), сплошные — адреса, вызовы, наследование.</p>
        <div className="overflow-x-auto rounded-lg border border-line bg-bg/50">
          <Diagram label="Авто-схема" graph={r.auto_diagram} />
        </div>
        <Legend kinds={r.auto_diagram.nodes.map((n) => n.kind)} />
      </div>
    </section>
  )
}
