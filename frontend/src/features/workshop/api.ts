import { api } from '@/lib/api'
import type { Role } from '@/features/auth/api'
import type { FragmentBrief, Source } from '@/features/library/api'

export type ImportRun = {
  id: number
  status: 'running' | 'done' | 'failed'
  started_at: string
  finished_at: string | null
  commit: string | null
  added: number
  changed: number
  removed: number
  unchanged: number
  error: string | null
}

export type AdminSource = Source & {
  license_status: 'ok' | 'needs_review'
  last_import_at: string | null
  fragments: number
  needs_review: number
  runs: ImportRun[]
  import_pending: boolean
}

export type ReviewItem = FragmentBrief & {
  changed_at: string | null
  used_in: { course_id: number; course_title: string; lesson_title: string; draft: boolean }[]
}

export type UserRow = { id: number; login: string; display_name: string; role: Role; created_at: string }

const post = (body?: unknown) => ({ method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const sourcesApi = {
  list: () => api<AdminSource[]>('/api/workshop/sources'),
  startImport: (slug: string) => api<{ queued: boolean }>(`/api/workshop/sources/${slug}/import`, post()),
  confirmLicense: (slug: string) => api<void>(`/api/workshop/sources/${slug}/confirm-license`, post()),
  review: () => api<ReviewItem[]>('/api/workshop/fragments/review'),
  markReviewed: (id: number) => api<void>(`/api/workshop/fragments/${id}/reviewed`, post()),
}

export const usersApi = {
  list: () => api<UserRow[]>('/api/workshop/users'),
  create: (body: { login: string; display_name: string; role: Role; password: string }) => api<UserRow>('/api/workshop/users', post(body)),
  resetPassword: (id: number, password: string) => api<void>(`/api/workshop/users/${id}/password`, post({ password })),
}
