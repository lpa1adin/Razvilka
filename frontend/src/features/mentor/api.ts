import { api } from '@/lib/api'

export type ContextKind = 'lesson' | 'task' | 'general'

export type MentorContext = {
  kind: ContextKind
  ref: string
  /** что показать в шапке панели: «Урок: Шапка сайта» */
  label: string
  /** код из редактора — наставник видит его, даже если он ещё не сохранился */
  getFiles?: () => Record<string, string>
}

export type MentorMessage = {
  id: number
  role: 'user' | 'assistant'
  content: string
  status: 'pending' | 'streaming' | 'done' | 'failed'
  hint: boolean
  error: string | null
}

export const mentorApi = {
  status: () => api<{ available: boolean; reason: string | null }>('/api/mentor/status'),
  thread: (kind: ContextKind, ref: string) =>
    api<{ messages: MentorMessage[] }>(`/api/mentor/thread?kind=${kind}&ref=${encodeURIComponent(ref)}`),
  clear: (kind: ContextKind, ref: string) => api<void>(`/api/mentor/thread?kind=${kind}&ref=${encodeURIComponent(ref)}`, { method: 'DELETE' }),
  send: (body: { context_kind: ContextKind; context_ref: string; text: string; hint?: boolean; files?: Record<string, string> }) =>
    api<{ answer_id: number }>('/api/mentor/messages', { method: 'POST', body: JSON.stringify(body) }),
  propose: (topic: string, notes: string) =>
    api<{ id: number; message: string }>('/api/proposals', { method: 'POST', body: JSON.stringify({ topic, notes }) }),
}

type StreamEvent = { delta?: string; status?: 'done' | 'failed'; error?: string | null; content?: string }

/** Ответ наставника потоком (SSE). Возвращает функцию, которая закрывает соединение. */
export function streamAnswer(id: number, onEvent: (e: StreamEvent) => void): () => void {
  const source = new EventSource(`/api/mentor/messages/${id}/stream`)
  source.onmessage = (message) => {
    const event = JSON.parse(message.data) as StreamEvent
    onEvent(event)
    if (event.status) source.close()
  }
  source.onerror = () => {
    source.close()
    onEvent({ status: 'failed', error: 'Связь с сервером прервалась. Обновите панель, ответ мог сохраниться.' })
  }
  return () => source.close()
}
