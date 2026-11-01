import { CheckCircle2, CircleAlert, LoaderCircle, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/States'

import { SEVERITY, type Finding, type Review } from './api'

type Props = {
  review: Review
  /** клик по адресу замечания — перейти к строке в редакторе */
  onJump?: (file: string, line: number | null) => void
  /** показать строки кода рядом с замечанием (на странице «Проверки», где редактора нет) */
  withCode?: boolean
}

export function ReviewStatus({ review }: { review: Review }) {
  if (review.status === 'queued' || review.status === 'running') {
    return (
      <p className="flex items-center gap-2 text-sm text-muted" role="status">
        <LoaderCircle className="size-4 animate-spin text-ai" aria-hidden />
        {review.status === 'queued' ? 'Ревью в очереди…' : 'Ревьюер читает код — обычно до минуты…'}
      </p>
    )
  }
  if (review.status === 'failed') {
    return (
      <p role="alert" className="text-sm text-danger">
        Ревью не удалось: {review.error}
      </p>
    )
  }
  const pass = review.verdict === 'pass'
  return (
    <div className="flex flex-wrap items-center gap-2">
      {pass ? <CheckCircle2 className="size-5 text-accent" aria-hidden /> : <CircleAlert className="size-5 text-ai" aria-hidden />}
      <span className="font-medium">{pass ? (review.findings.length ? 'Серьёзных замечаний нет' : 'Замечаний нет') : 'Нужны правки'}</span>
      {(['blocker', 'major', 'minor'] as const).map((s) =>
        review.counts[s] ? (
          <Badge key={s} tone={SEVERITY[s].tone}>
            {SEVERITY[s].label} · {review.counts[s]}
          </Badge>
        ) : null,
      )}
      {review.accepted && <Badge tone="accent">приняты админом</Badge>}
    </div>
  )
}

export function ReviewReport({ review, onJump, withCode }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <ReviewStatus review={review} />
      {review.status === 'done' && (
        <>
          {review.findings.length === 0 && (
            <p className="text-sm text-muted">Ревьюер проверил код по правилам v{review.rules_version} и не нашёл нарушений.</p>
          )}
          <ol className="flex flex-col gap-3">
            {review.findings.map((f, i) => (
              <FindingCard key={i} finding={f} onJump={onJump} code={withCode ? review.files[f.file] : undefined} />
            ))}
          </ol>
          <p className="flex items-start gap-2 text-xs text-faint">
            <ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <span>
              Независимая проверка: Ревьюер видел только условие, код и правила v{review.rules_version} — не переписку с наставником и не автора.
              {review.dropped > 0 && ` Отброшено замечаний с неверным адресом или правилом: ${review.dropped}.`}
              {review.accepted_note && ` Пояснение админа: ${review.accepted_note}`}
            </span>
          </p>
        </>
      )}
    </div>
  )
}

function FindingCard({ finding: f, onJump, code }: { finding: Finding; onJump?: Props['onJump']; code?: string }) {
  const address = `${f.file}${f.line ? `:${f.line}` : ''}`
  const lines = code && f.line ? code.split('\n').slice(Math.max(0, f.line - 3), f.line + 2) : null
  const first = f.line ? Math.max(1, f.line - 2) : 1
  return (
    <li
      className={`flex flex-col gap-2 rounded-lg border p-3.5 text-sm ${
        f.severity === 'blocker' ? 'border-danger/40 bg-danger-soft/40' : f.severity === 'major' ? 'border-ai/35 bg-ai-soft/40' : 'border-line'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={SEVERITY[f.severity].tone}>{f.severity}</Badge>
        <span className="font-mono text-xs text-muted" title={f.rule_text}>
          {f.rule}
        </span>
        {onJump ? (
          <button type="button" onClick={() => onJump(f.file, f.line)} className="font-mono text-xs text-accent hover:underline">
            {address}
          </button>
        ) : (
          <span className="font-mono text-xs text-muted">{address}</span>
        )}
      </div>
      <p className="font-medium">
        <Inline text={f.problem} />
      </p>
      {lines && (
        <pre className="overflow-x-auto rounded-md border border-line bg-bg/70 py-2 font-mono text-[12.5px] leading-relaxed">
          {lines.map((l, i) => (
            <span key={i} className={`block px-3 ${first + i === f.line ? 'bg-ai-soft' : ''}`}>
              <span className="mr-3 inline-block w-6 select-none text-right text-faint">{first + i}</span>
              {l || ' '}
            </span>
          ))}
        </pre>
      )}
      <p className="text-muted">
        <span className="text-text">Когда сломается: </span>
        <Inline text={f.scenario} />
      </p>
      <p className="text-muted">
        <span className="text-text">Куда смотреть: </span>
        <Inline text={f.fix_hint} />
      </p>
      <p className="text-xs text-faint">
        Правило {f.rule}: <Inline text={f.rule_text} />
        {f.source && ` · ${f.source}`}
      </p>
    </li>
  )
}

/** Ревьюер пишет код в `обратных кавычках` — показываем его моноширинным, а не сырыми символами. */
function Inline({ text }: { text: string }) {
  return (
    <>
      {text.split(/(`[^`]+`)/).map((part, i) =>
        part.length > 2 && part.startsWith('`') && part.endsWith('`') ? (
          <code key={i} className="rounded bg-surface-2 px-1 py-px font-mono text-[0.9em] text-text">
            {part.slice(1, -1)}
          </code>
        ) : (
          part
        ),
      )}
    </>
  )
}
