import { api } from '@/lib/api'

export type GenStatus = 'proposed' | 'new' | 'planning' | 'plan_ready' | 'drafting' | 'draft_ready' | 'paused' | 'failed' | 'rejected'
export type GenWhat = 'course' | 'task' | 'quiz' | 'path'
export type TaskKind = 'web' | 'python' | 'sql'

export type PlanLesson = {
  id: string
  title: string
  goal: string
  files: string[]
  fragment_ids: number[]
  practice: { kind: TaskKind; idea: string } | null
  quiz: number
  forks?: { question: string; context: string }[]
}
export type PlanModule = { id: string; title: string; lessons: PlanLesson[] }
export type Plan = { title: string; description: string; summary: string; modules: PlanModule[]; roles?: { path: string; role: string }[] }

export type Step = { key: string; label: string; state: 'pending' | 'running' | 'done' | 'failed' | 'skipped'; detail: string }

export type CreatedTask = {
  id: number
  slug: string
  title: string
  kind: TaskKind
  draft_version: number | null
  published: boolean
  check_status: 'not_checked' | 'queued' | 'passed' | 'failed'
  check_summary: string
  review_verdict: 'pass' | 'changes_requested' | null
  review_summary: string
}

export type CreatedLesson = {
  id: string
  title: string
  task: CreatedTask | null
  questions: number
  questions_published: number
  theory: { id: number; title: string }[]
  notes: string[]
  stage: { assignment_id: number; slug: string; check_status: string; check_summary: string; forks: string[] } | null
}

export type GenRequest = {
  id: number
  status: GenStatus
  what: GenWhat
  origin: 'admin' | 'user'
  project: string
  focus: string
  topic: string
  level: number
  notes: string
  author: string | null
  plan: Plan | null
  fragments: Record<string, string>
  steps: Step[]
  error: string | null
  busy: boolean
  /** запрошенная пауза, пока воркер не остановился */
  pause: '' | 'after' | 'now'
  published: boolean
  course: { id: number; slug: string; title: string; draft_version: number | null; published_version: number | null } | null
  topics: { id: number; title: string; published: boolean; questions: number }[]
  path: { slug: string; title: string; published: boolean } | null
  lessons: CreatedLesson[]
  created_at: string
  updated_at: string
}

export type RequestCard = Pick<GenRequest, 'id' | 'status' | 'what' | 'origin' | 'project' | 'author' | 'busy' | 'published' | 'updated_at'> & { title: string }
export type RequestIn = { what: GenWhat; project: string; focus: string; topic: string; level: number; notes: string }
export type Project = { name: string; files: number; languages: string[] }

export const WHAT_LABEL: Record<GenWhat, string> = { course: 'курс', task: 'задания', quiz: 'банк вопросов', path: 'путь «напиши заново сам»' }
export const LEVEL_LABEL: Record<number, string> = { 1: 'новичок', 2: 'средний', 3: 'продвинутый' }
export const STATUS_LABEL: Record<GenStatus, { label: string; tone: 'muted' | 'accent' | 'ai' | 'danger' }> = {
  proposed: { label: 'заявка пользователя', tone: 'ai' },
  new: { label: 'нужен план', tone: 'muted' },
  planning: { label: 'строится план', tone: 'ai' },
  plan_ready: { label: 'план на проверке', tone: 'ai' },
  drafting: { label: 'пишется черновик', tone: 'ai' },
  draft_ready: { label: 'черновик на проверке', tone: 'ai' },
  paused: { label: 'на паузе', tone: 'muted' },
  failed: { label: 'шаг не удался', tone: 'danger' },
  rejected: { label: 'отклонена', tone: 'muted' },
}

const base = '/api/workshop/generate'
const post = <T,>(path: string, body?: unknown) => api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const genApi = {
  projects: () => api<Project[]>(`${base}/projects`),
  list: () => api<RequestCard[]>(`${base}/requests`),
  get: (id: number) => api<GenRequest>(`${base}/requests/${id}`),
  create: (body: RequestIn) => post<GenRequest>(`${base}/requests`, body),
  update: (id: number, body: RequestIn) => api<GenRequest>(`${base}/requests/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  remove: (id: number) => api<void>(`${base}/requests/${id}`, { method: 'DELETE' }),
  reject: (id: number) => post<GenRequest>(`${base}/requests/${id}/reject`),
  plan: (id: number) => post<GenRequest>(`${base}/requests/${id}/plan`),
  replan: (id: number, feedback: string) => post<GenRequest>(`${base}/requests/${id}/replan`, { feedback }),
  savePlan: (id: number, plan: Plan) => api<GenRequest>(`${base}/requests/${id}/plan`, { method: 'PUT', body: JSON.stringify(plan) }),
  draft: (id: number) => post<GenRequest>(`${base}/requests/${id}/draft`),
  redo: (id: number, lessonId: string, instruction: string) => post<GenRequest>(`${base}/requests/${id}/lessons/${lessonId}/redo`, { instruction }),
  pause: (id: number, mode: 'after' | 'now') => post<GenRequest>(`${base}/requests/${id}/pause`, { mode }),
  resume: (id: number) => post<GenRequest>(`${base}/requests/${id}/resume`),
  recheck: (id: number) => post<GenRequest>(`${base}/requests/${id}/checks`),
  publish: (id: number) => post<{ published: string[]; problems: string[] }>(`${base}/requests/${id}/publish`),
}
