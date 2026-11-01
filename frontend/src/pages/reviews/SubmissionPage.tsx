import { ArrowLeft, CheckCircle2, CircleDashed, CircleX, GitFork, LoaderCircle, MinusCircle, Quote, Scale, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'

import { Badge, ErrorBlock, Skeleton } from '@/components/ui/States'
import { pollSubmission, type CriterionResult, type Mismatch, type Submission } from '@/features/assess/api'
import { ReviewReport } from '@/features/review/ReviewReport'

const STEP_ICON = {
  pending: <CircleDashed className="size-4 text-faint" aria-hidden />,
  running: <LoaderCircle className="size-4 animate-spin text-ai" aria-hidden />,
  done: <CheckCircle2 className="size-4 text-accent" aria-hidden />,
  failed: <CircleX className="size-4 text-danger" aria-hidden />,
  skipped: <MinusCircle className="size-4 text-faint" aria-hidden />,
}

export function SubmissionPage() {
  const { id = '' } = useParams()
  const [s, setS] = useState<Submission | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setS(null)
    let stop = () => {}
    try {
      stop = pollSubmission(Number(id), setS)
    } catch (e) {
      setError(String(e))
    }
    return () => stop()
  }, [id])

  if (error) return <ErrorBlock message={error} />
  if (!s) return <Skeleton lines={6} />
  const ev = s.evaluation
  const real = ev?.mismatches.filter((m) => m.claim_verified) ?? []
  const unverified = ev?.mismatches.filter((m) => !m.claim_verified) ?? []

  return (
    <div className="rise-in mx-auto flex max-w-4xl flex-col gap-6">
      <Link to="/reviews" className="inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4" aria-hidden /> Все проверки
      </Link>
      <header className="flex flex-col gap-2">
        <p className="eyebrow">
          Сдача · попытка {s.attempt} · {s.source === 'zip' ? 'архив' : 'папка'} {s.source_name}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{s.assignment_title}</h1>
        <Link to={`/practice/assignments/${s.assignment_slug}`} className="w-fit text-sm text-accent hover:underline">
          Условие и новая сдача
        </Link>
      </header>

      <ol className="panel flex flex-col gap-2 p-5" aria-label="Шаги проверки" aria-live="polite">
        {s.steps.map((st) => (
          <li key={st.key} className="flex items-start gap-3 text-sm">
            <span className="mt-0.5">{STEP_ICON[st.state]}</span>
            <span>
              {st.label}
              {st.detail && <span className="block font-mono text-xs text-faint">{st.detail}</span>}
            </span>
          </li>
        ))}
      </ol>
      {s.error && <ErrorBlock message={s.error} />}
      {s.warnings.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-lg border border-ai/30 bg-ai-soft/50 p-3 text-sm text-ai">
          {s.warnings.map((w, i) => (
            <li key={i}>• {w}</li>
          ))}
        </ul>
      )}

      {ev && (
        <>
          <section className="panel flex flex-wrap items-center gap-6 p-6" aria-label="Итог">
            <div
              className="grid size-24 shrink-0 place-items-center rounded-full"
              style={{ background: `conic-gradient(${ev.passed ? 'var(--accent)' : 'var(--ai)'} ${(ev.score / 5) * 360}deg, var(--surface-2) 0)` }}
              role="img"
              aria-label={`${ev.score} из 5`}
            >
              <span className="grid size-[84px] place-items-center rounded-full bg-surface font-mono text-xl">{ev.score.toFixed(1)}</span>
            </div>
            <div className="min-w-[220px] flex-1">
              <p className="eyebrow">Оценщик · рубрика v{s.rubric_version}</p>
              <p className="mt-1 text-xl font-semibold">{ev.passed ? 'Зачтено' : 'Не зачтено'}</p>
              <p className="mt-1 text-sm text-muted">{ev.summary}</p>
            </div>
            <dl className="grid grid-cols-3 gap-3 text-center text-sm">
              <Stat label="обоснование" value={ev.reasoning.toFixed(1)} />
              <Stat label="реализация" value={ev.implementation.toFixed(1)} />
              <Stat label="штраф" value={ev.penalty ? `−${ev.penalty}` : '0'} danger={ev.penalty > 0} />
            </dl>
            {ev.notes.length > 0 && (
              <ul className="basis-full border-t border-line pt-3 text-xs text-muted">
                {ev.notes.map((n, i) => (
                  <li key={i}>• {n}</li>
                ))}
              </ul>
            )}
          </section>

          {real.length > 0 && (
            <section className="flex flex-col gap-3" aria-labelledby="mismatch-title">
              <h2 id="mismatch-title" className="flex items-center gap-2 text-xl font-semibold text-danger">
                <TriangleAlert className="size-5" aria-hidden /> Сказал ≠ сделал
              </h2>
              {real.map((m, i) => (
                <MismatchCard key={i} m={m} code={s.files[m.file]} />
              ))}
            </section>
          )}

          <section className="flex flex-col gap-3" aria-labelledby="crit-title">
            <h2 id="crit-title" className="flex items-center gap-2 text-xl font-semibold">
              <Scale className="size-5 text-muted" aria-hidden /> По критериям
            </h2>
            {(['reasoning', 'implementation'] as const).map((block) => (
              <div key={block} className="panel flex flex-col divide-y divide-line">
                <p className="px-5 py-3 font-medium">{block === 'reasoning' ? 'Обоснование' : 'Реализация'}</p>
                {ev.criteria
                  .filter((c) => c.block === block)
                  .map((c) => (
                    <CriterionRow key={c.id} c={c} />
                  ))}
              </div>
            ))}
          </section>

          {ev.contradictions.length > 0 && (
            <section className="panel p-5">
              <h2 className="font-semibold">Противоречия с прошлыми сдачами</h2>
              <ul className="mt-2 flex flex-col gap-1 text-sm text-muted">
                {ev.contradictions.map((c, i) => (
                  <li key={i}>• {c}</li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {s.tests && (
        <section className="panel p-5" aria-labelledby="tests-title">
          <h2 id="tests-title" className="font-semibold">
            Автотесты {s.tests.passed ? <Badge tone="accent">пройдены</Badge> : <Badge tone="danger">не пройдены</Badge>}
          </h2>
          {s.tests.error && <p className="mt-2 text-sm text-danger">{s.tests.error}</p>}
          <ul className="mt-3 flex flex-col gap-1.5 text-sm">
            {s.tests.results.map((r, i) => (
              <li key={i} className="flex items-start gap-2">
                {r.passed ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden /> : <CircleX className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />}
                <span>
                  {r.name}
                  {r.message && <span className="block text-xs text-muted">{r.message}</span>}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {s.review && (
        <section className="panel p-5" aria-labelledby="review-title">
          <h2 id="review-title" className="mb-3 font-semibold">
            Ревьюер
          </h2>
          <ReviewReport review={s.review} withCode />
        </section>
      )}

      <section className="flex flex-col gap-3" aria-labelledby="forks-title">
        <h2 id="forks-title" className="flex items-center gap-2 text-xl font-semibold">
          <GitFork className="size-5 text-ai" aria-hidden /> Развилки
        </h2>
        {s.forks.map((f) => {
          const view = ev?.reference_view.find((r) => r.fork_id === f.id)
          return (
            <div key={f.id} className="panel flex flex-col gap-3 p-5 text-sm">
              <p className="font-medium">{f.question}</p>
              {f.answer && (
                <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-[140px_1fr]">
                  <Row label="Решение" value={f.answer.choice} strong />
                  <Row label="Варианты" value={f.answer.alternatives} />
                  <Row label="Почему" value={f.answer.reasons} />
                  <Row label="Цена и риски" value={f.answer.risks} />
                  <Row label="Пересмотреть" value={f.answer.revisit} />
                </dl>
              )}
              {(f.reference || view) && (
                <div className="rounded-md border border-accent/30 bg-accent-soft/40 p-3">
                  <p className="font-medium text-accent">Как в эталоне</p>
                  {f.reference && <p className="mt-1">{f.reference}</p>}
                  {view && <p className="mt-1 text-muted">Оценщик: {view.reference}</p>}
                </div>
              )}
            </div>
          )
        })}
      </section>

      {unverified.length > 0 && (
        <p className="text-xs text-faint">
          Не засчитано расхождений, где цитата не нашлась в ваших ответах: {unverified.length}. Это защита от ошибок Оценщика.
        </p>
      )}
    </div>
  )
}

function Stat({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="rounded-lg border border-line px-3 py-2">
      <dd className={`font-mono text-lg ${danger ? 'text-danger' : ''}`}>{value}</dd>
      <dt className="text-xs text-muted">{label}</dt>
    </div>
  )
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  if (!value) return null
  return (
    <>
      <dt className="text-muted">{label}</dt>
      <dd className={strong ? 'font-medium' : ''}>{value}</dd>
    </>
  )
}

function MismatchCard({ m, code }: { m: Mismatch; code?: string }) {
  const lines = code ? code.split('\n') : []
  const first = Math.max(1, m.line - 2)
  const shown = lines.slice(first - 1, m.line + 2)
  return (
    <article className="grid gap-3 rounded-lg border border-danger/40 bg-danger-soft/30 p-4 md:grid-cols-2">
      <div className="flex flex-col gap-2">
        <p className="eyebrow">Вы написали</p>
        <blockquote className="flex gap-2 text-[15px]">
          <Quote className="mt-1 size-4 shrink-0 text-faint" aria-hidden />
          <span className="font-medium">{m.claim}</span>
        </blockquote>
        <p className="text-sm text-muted">{m.why}</p>
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        <p className="eyebrow">
          А в коде · <span className="font-mono normal-case tracking-normal">{m.file}:{m.line}</span>
        </p>
        <pre className="overflow-x-auto rounded-md border border-line bg-bg/70 py-2 font-mono text-[12.5px] leading-relaxed">
          {(shown.length ? shown : [m.code_line]).map((l, i) => (
            <span key={i} className={`block px-3 ${first + i === m.line ? 'bg-danger-soft' : ''}`}>
              <span className="mr-3 inline-block w-6 select-none text-right text-faint">{shown.length ? first + i : m.line}</span>
              {l || ' '}
            </span>
          ))}
        </pre>
        <p className="text-sm">{m.code_says}</p>
      </div>
    </article>
  )
}

function CriterionRow({ c }: { c: CriterionResult }) {
  return (
    <div className="flex flex-col gap-1.5 px-5 py-3 text-sm">
      <div className="flex items-center gap-3">
        <span className="font-mono text-xs text-faint">{c.id}</span>
        <span className="flex-1">{c.title}</span>
        <span className="flex gap-0.5" aria-label={`${c.score} из 5`}>
          {[1, 2, 3, 4, 5].map((n) => (
            <span key={n} className={`h-2 w-4 rounded-full ${n <= c.score ? (c.score >= 3 ? 'bg-accent' : 'bg-ai') : 'bg-surface-2'}`} />
          ))}
        </span>
        <span className="w-8 text-right font-mono">{c.score}</span>
      </div>
      <p className="text-muted">{c.explanation}</p>
      {c.evidence.length > 0 && (
        <p className="font-mono text-xs text-faint">
          {c.evidence.map((e) => `${e.file}${e.line ? `:${e.line}` : ''} — ${e.note}`).join(' · ')}
        </p>
      )}
    </div>
  )
}
