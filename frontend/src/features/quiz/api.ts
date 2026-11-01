import { api } from '@/lib/api'

export type QuestionType = 'single' | 'multiple' | 'order' | 'match'
export type Option = { id: string; text: string }
export type Options = { items?: Option[]; left?: Option[]; right?: Option[] }
export type Response = { selected?: string[]; order?: string[]; pairs?: Record<string, string> }
export type Answer = { correct?: string[]; order?: string[]; pairs?: Record<string, string> }

export const TYPE_LABEL: Record<QuestionType, string> = {
  single: 'Один ответ',
  multiple: 'Несколько ответов',
  order: 'Расставьте по порядку',
  match: 'Сопоставьте',
}

export type TopicCard = {
  slug: string
  title: string
  description: string
  questions: number
  size: number
  unseen: number
  active_attempt_id: number | null
  last_score: number | null
  last_total: number | null
  attempts: number
}

export type AttemptItem = {
  position: number
  type: QuestionType
  prompt_html: string
  code: string
  code_lang: string
  options: Options
  response: Response | null
  correct: boolean | null
  answer: Answer | null
  explanation_html: string | null
  source: { fragment_id: number; title: string; source: string } | null
}

export type Attempt = {
  id: number
  topic_slug: string
  topic_title: string
  status: 'in_progress' | 'finished'
  mistakes_only: boolean
  score: number
  total: number
  created_at: string
  finished_at: string | null
  note: string | null
  items: AttemptItem[]
}

const json = (method: string, body?: unknown) => ({ method, body: body === undefined ? undefined : JSON.stringify(body) })

export const quizApi = {
  topics: () => api<TopicCard[]>('/api/quiz/topics'),
  topic: (slug: string) => api<TopicCard>(`/api/quiz/topics/${slug}`),
  start: (slug: string, mistakes_only = false) => api<Attempt>(`/api/quiz/topics/${slug}/attempts`, json('POST', { mistakes_only })),
  attempt: (id: number) => api<Attempt>(`/api/quiz/attempts/${id}`),
  answer: (id: number, position: number, response: Response) => api<void>(`/api/quiz/attempts/${id}/items/${position}`, json('PUT', { response })),
  finish: (id: number) => api<Attempt>(`/api/quiz/attempts/${id}/finish`, json('POST')),
}

/** Есть ли в ответе хоть что-то — для счётчика «отвечено N из M». */
export function answered(item: AttemptItem) {
  const r = item.response
  if (!r) return false
  if (item.type === 'match') return Object.keys(r.pairs ?? {}).length === (item.options.left ?? []).length
  if (item.type === 'order') return (r.order ?? []).length > 0
  return (r.selected ?? []).length > 0
}

// ---------- Мастерская ----------

export type TopicAdmin = { id: number; slug: string; title: string; description: string; size: number; published: boolean; counts: Record<string, number> }

export type QuestionStatus = 'draft' | 'published' | 'archived'

export type QuestionData = {
  type: QuestionType
  prompt: string
  code: string
  code_lang: string
  options: Options
  answer: Answer
  explanation: string
  fragment_id: number | null
  subtopic: string
  difficulty: number
  status: QuestionStatus
}

export type QuestionAdmin = QuestionData & { id: number; topic_id: number; fragment_title: string | null; updated_at: string }

export type Similar = { id: number; prompt: string; similarity: number }

export type TopupState = { running: boolean; error: string | null; added: number | null; notes: string[] }

/** Тест — 5–10 вопросов из банка темы; банк — 20–50 (как в quiz.service на сервере) */
export const TEST_SIZE = { min: 5, max: 10 }
export const BANK_SIZE = { min: 20, max: 50 }

export const quizAdminApi = {
  topics: () => api<TopicAdmin[]>('/api/workshop/quiz/topics'),
  createTopic: (body: { title: string; description: string; size: number; published: boolean }) => api<TopicAdmin>('/api/workshop/quiz/topics', json('POST', body)),
  updateTopic: (id: number, body: { title: string; description: string; size: number; published: boolean }) => api<TopicAdmin>(`/api/workshop/quiz/topics/${id}`, json('PUT', body)),
  questions: (topicId: number) => api<QuestionAdmin[]>(`/api/workshop/quiz/topics/${topicId}/questions`),
  createQuestion: (topicId: number, body: QuestionData, force = false) => api<QuestionAdmin>(`/api/workshop/quiz/topics/${topicId}/questions${force ? '?force=true' : ''}`, json('POST', body)),
  updateQuestion: (id: number, body: QuestionData, force = false) => api<QuestionAdmin>(`/api/workshop/quiz/questions/${id}${force ? '?force=true' : ''}`, json('PUT', body)),
  topupState: (topicId: number) => api<TopupState>(`/api/workshop/quiz/topics/${topicId}/topup`),
  topup: (topicId: number, target: number) => api<TopupState>(`/api/workshop/quiz/topics/${topicId}/topup`, json('POST', { target })),
  removeQuestion: (id: number) => api<void>(`/api/workshop/quiz/questions/${id}`, json('DELETE')),
}
