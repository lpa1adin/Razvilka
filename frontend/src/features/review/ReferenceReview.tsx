import { Check, ScanSearch } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/Button'
import { inputClass } from '@/components/ui/Field'
import { ApiError } from '@/lib/api'

import { pollReview, reviewApi, type Review } from './api'
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
          <Button variant="secondary" onClick={start} loading={busy} loadingText="Ревьюер читает…" disabled={dirty} title={dirty ? 'Сначала сохраните задание' : undefined}>
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
      {review?.status === 'done' && review.verdict === 'changes_requested' && !review.accepted && editable && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
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
