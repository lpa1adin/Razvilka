import { api } from '@/lib/api'
import type { Review } from '@/features/review/api'

export type ForkAnswer = { choice: string; alternatives: string; reasons: string; risks: string; revisit: string }
export type SubmissionStatus = 'testing' | 'reviewing' | 'evaluating' | 'done' | 'failed'

export type SubmissionCard = {
  id: number
  assignment_slug: string
  assignment_title: string
  attempt: number
  status: SubmissionStatus
  score: number | null
  passed: boolean | null
  mismatches: number
  created_at: string
}

export type Reference = { id: number; name: string; url: string; about: string }

export type AssignmentCard = { slug: string; title: string; kind: string; forks: number; attempts: number; best_score: number | null; passed: boolean }

export type Assignment = {
  slug: string
  title: string
  statement_html: string
  kind: 'web' | 'python' | 'any'
  forks: { id: string; question: string; context: string }[]
  has_tests: boolean
  threshold: number
  references: Reference[]
  projects: string[]
  submissions: SubmissionCard[]
  path: { slug: string; title: string; position: number; total: number; workspace: { exists: boolean; host_path: string; list: string[] }; goal: string; files: string[] } | null
}

export type Mismatch = { fork_id: string; claim: string; claim_verified: boolean; file: string; line: number; code_line: string; code_says: string; why: string }
export type CriterionResult = { id: string; block: 'reasoning' | 'implementation'; title: string; score: number; explanation: string; evidence: { file: string; line: number | null; note: string }[] }

export type Evaluation = {
  criteria: CriterionResult[]
  reasoning: number
  implementation: number
  penalty: number
  mismatches: Mismatch[]
  contradictions: string[]
  reference_view: { fork_id: string; reference: string }[]
  summary: string
  notes: string[]
  score: number
  passed: boolean
}

export type Submission = {
  id: number
  assignment_slug: string
  assignment_title: string
  attempt: number
  source: string
  source_name: string
  status: SubmissionStatus
  steps: { key: string; label: string; state: 'pending' | 'running' | 'done' | 'failed' | 'skipped'; detail: string }[]
  warnings: string[]
  files: Record<string, string>
  forks: { id: string; question: string; context: string; answer: ForkAnswer | null; reference: string }[]
  summary: string
  tests: { results: { name: string; passed: boolean; message: string }[]; error: string | null; passed: boolean } | null
  review: Review | null
  evaluation: Evaluation | null
  score: number | null
  passed: boolean | null
  threshold: number
  rubric_version: number
  error: string | null
  created_at: string
  finished_at: string | null
}

export type JournalEntry = {
  assignment: string
  assignment_slug: string
  submission_id: number
  attempt: number
  fork_id: string
  question: string
  answer: ForkAnswer
  date: string
  score: number | null
  passed: boolean | null
  reference: string
  evaluator_reference: string
  mismatches: Mismatch[]
}

export type Criterion = { id: string; block: 'reasoning' | 'implementation'; title: string; description: string }
export type Rubric = { version: number; criteria: Criterion[]; mismatch_penalty: number; note: string; created_at: string }
export type AssignmentAdmin = {
  id: number
  slug: string
  submissions: number
  title: string
  statement: string
  kind: 'web' | 'python' | 'any'
  forks: { id: string; question: string; context: string; reference: string }[]
  tests: string
  reference_ids: number[]
  threshold: number
  published: boolean
}

export type SubmitBody = {
  answers: Record<string, ForkAnswer>
  summary: string
  source: 'zip' | 'folder' | 'workspace'
  project?: string
  focus?: string
  archive?: string
  archive_name?: string
}

const json = (method: string, body: unknown) => ({ method, body: JSON.stringify(body) })

export const assessApi = {
  assignments: () => api<AssignmentCard[]>('/api/assignments'),
  assignment: (slug: string) => api<Assignment>(`/api/assignments/${slug}`),
  submit: (slug: string, body: SubmitBody) => api<Submission>(`/api/assignments/${slug}/submissions`, json('POST', body)),
  submissions: () => api<SubmissionCard[]>('/api/submissions'),
  submission: (id: number) => api<Submission>(`/api/submissions/${id}`),
  journal: () => api<JournalEntry[]>('/api/forks'),
  // Мастерская
  rubric: () => api<Rubric>('/api/workshop/rubric'),
  saveRubric: (body: Omit<Rubric, 'version' | 'created_at'>) => api<Rubric>('/api/workshop/rubric', json('PUT', body)),
  references: () => api<Reference[]>('/api/workshop/references'),
  addReference: (body: Omit<Reference, 'id'>) => api<Reference>('/api/workshop/references', json('POST', body)),
  saveReference: (id: number, body: Omit<Reference, 'id'>) => api<Reference>(`/api/workshop/references/${id}`, json('PUT', body)),
  removeReference: (id: number) => api<void>(`/api/workshop/references/${id}`, { method: 'DELETE' }),
  adminAssignments: () => api<AssignmentAdmin[]>('/api/workshop/assignments'),
  createAssignment: (body: Omit<AssignmentAdmin, 'id' | 'slug' | 'submissions'>) => api<AssignmentAdmin>('/api/workshop/assignments', json('POST', body)),
  saveAssignment: (id: number, body: Omit<AssignmentAdmin, 'id' | 'slug' | 'submissions'>) => api<AssignmentAdmin>(`/api/workshop/assignments/${id}`, json('PUT', body)),
  allSubmissions: () => api<SubmissionCard[]>('/api/workshop/submissions'),
}

/** Пока сдача проверяется — обновляем раз в 2,5 секунды. */
export function pollSubmission(id: number, onUpdate: (s: Submission) => void): () => void {
  let stopped = false
  const tick = async () => {
    if (stopped) return
    try {
      const s = await assessApi.submission(id)
      onUpdate(s)
      if (s.status !== 'done' && s.status !== 'failed') window.setTimeout(tick, 2500)
    } catch {
      if (!stopped) window.setTimeout(tick, 5000)
    }
  }
  tick()
  return () => {
    stopped = true
  }
}

export async function fileToBase64(file: File): Promise<string> {
  const buf = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  for (let i = 0; i < buf.length; i += 0x8000) binary += String.fromCharCode(...buf.subarray(i, i + 0x8000))
  return btoa(binary)
}
