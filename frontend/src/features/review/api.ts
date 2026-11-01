import { api } from '@/lib/api'

export type Severity = 'blocker' | 'major' | 'minor'

export type Finding = {
  rule: string
  rule_text: string
  severity: Severity
  file: string
  line: number | null
  problem: string
  scenario: string
  fix_hint: string
  source: string
  by?: string
}

export type Review = {
  id: number
  kind: 'learner' | 'reference'
  status: 'queued' | 'running' | 'done' | 'failed'
  title: string
  task_slug: string | null
  task_version: number | null
  rules_version: number
  verdict: 'pass' | 'changes_requested' | null
  findings: Finding[]
  counts: Record<Severity, number>
  dropped: number
  second_opinion: boolean
  files: Record<string, string>
  error: string | null
  accepted: boolean
  accepted_note: string
  created_at: string
  finished_at: string | null
}

export type FixState = { running: boolean; error: string | null; notes: string[]; job_id: number | null }

export type ReviewCard = Pick<Review, 'id' | 'kind' | 'status' | 'title' | 'task_slug' | 'verdict' | 'counts' | 'created_at'>

export type Rule = { id: string; group: string; text: string; enabled: boolean; source?: string }
export type RuleSet = { version: number; rules: Rule[]; note: string; created_at: string; author: string | null }

export const SEVERITY: Record<Severity, { label: string; tone: 'danger' | 'ai' | 'muted' }> = {
  blocker: { label: 'blocker', tone: 'danger' },
  major: { label: 'major', tone: 'ai' },
  minor: { label: 'minor', tone: 'muted' },
}

export const reviewApi = {
  request: (task_slug: string, files: Record<string, string>) =>
    api<Review>('/api/reviews', { method: 'POST', body: JSON.stringify({ task_slug, files }) }),
  get: (id: number) => api<Review>(`/api/reviews/${id}`),
  mine: (task?: string) => api<ReviewCard[]>(`/api/reviews${task ? `?task=${encodeURIComponent(task)}` : ''}`),
  // Мастерская
  rules: () => api<RuleSet>('/api/workshop/review-rules'),
  saveRules: (rules: Rule[], note: string) => api<RuleSet>('/api/workshop/review-rules', { method: 'PUT', body: JSON.stringify({ rules, note }) }),
  versions: () => api<RuleSet[]>('/api/workshop/review-rules/versions'),
  reference: (taskId: number) => api<Review | null>(`/api/workshop/tasks/${taskId}/review`),
  requestReference: (taskId: number) => api<Review>(`/api/workshop/tasks/${taskId}/review`, { method: 'POST' }),
  fixState: (taskId: number) => api<FixState>(`/api/workshop/tasks/${taskId}/review/fix`),
  fix: (taskId: number) => api<FixState>(`/api/workshop/tasks/${taskId}/review/fix`, { method: 'POST' }),
  accept: (id: number, note: string) => api<Review>(`/api/workshop/reviews/${id}/accept`, { method: 'POST', body: JSON.stringify({ note }) }),
}

/** Пока Ревьюер работает — опрашиваем раз в 2 секунды. Возвращает функцию остановки. */
export function pollReview(id: number, onUpdate: (r: Review) => void): () => void {
  let stopped = false
  const tick = async () => {
    if (stopped) return
    try {
      const review = await reviewApi.get(id)
      onUpdate(review)
      if (review.status === 'queued' || review.status === 'running') window.setTimeout(tick, 2000)
    } catch {
      if (!stopped) window.setTimeout(tick, 4000)
    }
  }
  tick()
  return () => {
    stopped = true
  }
}
