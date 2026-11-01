import { Badge } from '@/components/ui/States'

import type { SubmissionCard } from './api'

const RUNNING = { testing: 'автотесты…', reviewing: 'Ревьюер…', evaluating: 'Оценщик…' } as const

/** Статус сдачи одной строкой: идёт / не удалась / итог и «сказал ≠ сделал». */
export function SubmissionBadge({ s }: { s: Pick<SubmissionCard, 'status' | 'score' | 'passed' | 'mismatches'> }) {
  if (s.status === 'failed') return <Badge tone="danger">не удалась</Badge>
  if (s.status !== 'done') return <Badge tone="ai">{RUNNING[s.status]}</Badge>
  return (
    <span className="flex flex-wrap gap-1.5">
      {s.mismatches > 0 && <Badge tone="danger">сказал ≠ сделал · {s.mismatches}</Badge>}
      <Badge tone={s.passed ? 'accent' : 'muted'}>
        {s.score?.toFixed(1)} из 5 · {s.passed ? 'зачтено' : 'не зачтено'}
      </Badge>
    </span>
  )
}
