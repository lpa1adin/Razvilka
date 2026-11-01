import { Check, LoaderCircle, ScanSearch, Wrench } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { inputClass } from '@/components/ui/Field'
import { ApiError } from '@/lib/api'

import { pollReview, reviewApi, type FixState, type Review } from './api'
import { ReviewReport } from './ReviewReport'

type Props = {
  taskId: number
  /** меняется при сохранении задания: у новой редакции эталона — своё ревью */
  specKey: string
  dirty: boolean
  editable: boolean
  /** клик по адресу замечания — открыть эталон на этой строке */
  onJump?: (file: string, line: number | null) => void
  /** ревью закончилось или замечания приняты — обновить сводку снаружи */
  onChange?: () => void
}

/** Ревью эталона в редакторе задания: без него (или без принятых замечаний) задание не публикуется. */
export function ReferenceReview({ taskId, specKey, dirty, editable, onJump, onChange }: Props) {
  const [review, setReview] = useState<Review | null | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [accepting, setAccepting] = useState(false)
  const stop = useRef<(() => void) | null>(null)
  // Исправление по замечаниям идёт в agent-worker: правка эталона → автотесты → повторное ревью
  const [fix, setFix] = useState<FixState | null>(null)

  useEffect(() => {
    stop.current?.()
    reviewApi.reference(taskId).then(
      (r) => {
        setReview(r)
        if (r && (r.status === 'queued' || r.status === 'running')) stop.current = pollReview(r.id, setReview)
      },
      () => setReview(null),
    )
    return () => stop.current?.()
  }, [taskId, specKey])

  const start = async () => {
    setError(null)
    try {
      const r = await reviewApi.requestReference(taskId)
      setReview(r)
      stop.current?.()
      stop.current = pollReview(r.id, setReview)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось запустить ревью')
    }
  }

  const accept = async () => {
    if (!review) return
    setAccepting(true)
    try {
      setReview(await reviewApi.accept(review.id, note))
      setNote('')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось')
    } finally {
      setAccepting(false)
    }
  }

  const busy = review?.status === 'queued' || review?.status === 'running'

  useEffect(() => {
    reviewApi.fixState(taskId).then(setFix, () => undefined)
  }, [taskId])
  const fixing = !!fix?.running
  useEffect(() => {
    if (!fixing) return
    const timer = window.setInterval(async () => {
      const next = await reviewApi.fixState(taskId).catch(() => null)
      if (!next) return
      setFix(next)
      if (!next.running) {
        setReview(await reviewApi.reference(taskId).catch(() => null))
        onChange?.()
      }
    }, 3000)
    return () => window.clearInterval(timer)
  }, [fixing, taskId, onChange])

  const startFix = async () => {
    setError(null)
    try {
      setFix(await reviewApi.fix(taskId))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось запустить исправление')
    }
  }
  // Сообщаем наружу только о переменах после загрузки, не о самой загрузке
  const outcome = review ? `${review.id}:${review.status}:${review.accepted}` : null
  const seen = useRef<string | null>(null)
  useEffect(() => {
    if (!outcome) return
    if (seen.current && seen.current !== outcome && !busy) onChange?.()
    seen.current = outcome
  }, [outcome, busy, onChange])

  return (
    <section className="panel flex flex-col gap-4 p-5" aria-labelledby="ref-review">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="ref-review" className="flex items-center gap-2 font-semibold">
          <ScanSearch className="size-4 text-muted" aria-hidden /> Ревью эталона
        </h2>
        <span className="text-sm text-muted">эталон не должен учить плохому — без ревью задание не публикуется</span>
        <span className="flex-1" />
        {editable && (
          <Button variant="secondary" onClick={start} loading={busy} loadingText="Ревьюер читает…" disabled={dirty || fixing} title={dirty ? 'Сначала сохраните задание' : undefined}>
            {review ? 'Проверить снова' : 'Ревью эталона'}
          </Button>
        )}
      </div>
      {dirty && <p className="text-xs text-ai">Есть несохранённые правки — ревью проверяет сохранённую редакцию.</p>}
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      {review === undefined ? null : review === null ? (
        <p className="text-sm text-muted">Эту редакцию эталона Ревьюер ещё не проверял.</p>
      ) : (
        <ReviewReport review={review} withCode onJump={onJump} />
      )}
      {fixing && (
        <p role="status" className="flex items-center gap-2 rounded-md border border-ai/30 bg-ai-soft/50 px-3 py-2 text-sm text-ai">
          <LoaderCircle className="size-4 shrink-0 animate-spin" aria-hidden />
          Наставник исправляет эталон по замечаниям, затем автотесты и повторное ревью — обычно 2–5 минут.
        </p>
      )}
      {!fixing && fix && (fix.error || fix.notes.length > 0) && (
        <ul className={`flex flex-col gap-0.5 rounded-md border px-3 py-2 text-xs ${fix.error ? 'border-danger/40 text-danger' : 'border-line text-muted'}`}>
          {fix.error && <li>Исправление не удалось: {fix.error}</li>}
          {fix.notes.map((n, i) => (
            <li key={i}>• {n}</li>
          ))}
        </ul>
      )}
      {review?.status === 'done' && review.verdict === 'changes_requested' && !review.accepted && editable && !fixing && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
          <Button onClick={startFix} disabled={dirty} icon={<Wrench className="size-4" />} title={dirty ? 'Сначала сохраните задание' : undefined}>
            Исправить по замечаниям
          </Button>
          <span className="text-xs text-faint">или примите их:</span>
          <input
            className={`${inputClass} h-10 min-w-[260px] flex-1`}
            placeholder="Почему замечания можно принять (видно в отчёте)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            aria-label="Пояснение"
          />
          <Button variant="ghost" onClick={accept} loading={accepting} disabled={note.trim().length < 3} icon={<Check className="size-4" />}>
            Принять замечания
          </Button>
        </div>
      )}
    </section>
  )
}
