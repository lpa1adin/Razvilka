import { api } from '@/lib/api'

export type Kind = 'web' | 'python' | 'sql'
export type Files = Record<string, string>

export const FILES: Record<Kind, string[]> = {
  web: ['index.html', 'style.css', 'script.js'],
  python: ['main.py'],
  sql: ['query.sql'],
}

export const KIND_LABEL: Record<Kind, string> = { web: 'HTML · CSS · JS', python: 'Python', sql: 'SQL' }

export type SqlCheck = { name: string; type: 'same_result' | 'assert'; sql: string; order_matters: boolean; message: string }
export type SqlTable = { columns: string[]; rows: unknown[][] }

export type CheckResult = { name: string; passed: boolean; message: string; width?: number }

export type TaskCard = { slug: string; title: string; kind: Kind; version: number; started: boolean; solved: boolean; has_update: boolean }

export type LearnerTask = {
  slug: string
  title: string
  kind: Kind
  version: number
  preview: boolean
  statement_html: string
  files: Files
  starter: Files
  tests: string
  sql_setup: string
  sql_checks: SqlCheck[]
  sql_expected: (SqlTable | null)[]
  hints: string[]
  hints_total: number
  solved: boolean
  has_update: boolean
  fragments: { id: number; title: string; source: string }[]
}

const v = (version?: number | null) => (version ? `?version=${version}` : '')
const json = (method: string, body?: unknown) => ({ method, body: body === undefined ? undefined : JSON.stringify(body) })

export const practiceApi = {
  list: () => api<TaskCard[]>('/api/practice/tasks'),
  get: (slug: string, version?: number | null) => api<LearnerTask>(`/api/practice/tasks/${slug}${v(version)}`),
  save: (slug: string, files: Files) => api<void>(`/api/practice/tasks/${slug}/work`, json('PUT', { files })),
  hint: (slug: string) => api<{ hint: string }>(`/api/practice/tasks/${slug}/hint`, json('POST')),
  attempt: (slug: string, passed: boolean, results: CheckResult[]) => api<void>(`/api/practice/tasks/${slug}/attempts`, json('POST', { passed, results })),
  reset: (slug: string) => api<void>(`/api/practice/tasks/${slug}/reset`, json('POST')),
  upgrade: (slug: string) => api<void>(`/api/practice/tasks/${slug}/upgrade`, json('POST')),
}

let harnessCache: Partial<Record<'web' | 'python', Promise<string>>> = {}

/** Код проверок берётся с сервера — тот же файл, которым пользуется runner. */
export function loadHarness(name: 'web' | 'python'): Promise<string> {
  harnessCache[name] ??= fetch(`/api/practice/harness/${name}`, { credentials: 'same-origin' }).then((r) => {
    if (!r.ok) {
      harnessCache = { ...harnessCache, [name]: undefined }
      throw new Error('Не удалось загрузить проверки задания')
    }
    return r.text()
  })
  return harnessCache[name]!
}

// ---------- Мастерская ----------

export type TaskSpec = {
  title: string
  kind: Kind
  statement: string
  starter: Files
  solution: Files
  tests: string
  sql_setup: string
  sql_checks: SqlCheck[]
  hints: string[]
  fragment_ids: number[]
}

export type CheckStatus = 'not_checked' | 'queued' | 'passed' | 'failed'

export type CheckReport = {
  problems: string[]
  checked_at: string
  solution?: { results: CheckResult[]; error: string | null }
  starter?: { results: CheckResult[]; error: string | null }
}

export type AdminTask = {
  id: number
  slug: string
  published_version: number | null
  draft_version: number | null
  archived: boolean
  editing: {
    number: number
    status: 'draft' | 'published' | 'superseded'
    spec: TaskSpec
    check_status: CheckStatus
    check_report: CheckReport | null
    check_is_current: boolean
    /** правка условия/стартового кода/подсказок от Claude при исправлении эталона — ждёт админа */
    proposal: { fields: Partial<Pick<TaskSpec, 'statement' | 'starter' | 'hints'>>; note: string } | null
    change_note: string
    created_at: string
    updated_at: string
    published_at: string | null
  }
}

export type AdminTaskBrief = {
  id: number
  slug: string
  title: string
  kind: Kind
  published_version: number | null
  draft_version: number | null
  archived: boolean
  check_status: CheckStatus
  updated_at: string
}

export const workshopTasksApi = {
  list: () => api<AdminTaskBrief[]>('/api/workshop/tasks'),
  create: (title: string, kind: Kind) => api<AdminTask>('/api/workshop/tasks', json('POST', { title, kind })),
  get: (id: number | string) => api<AdminTask>(`/api/workshop/tasks/${id}`),
  startDraft: (id: number) => api<AdminTask>(`/api/workshop/tasks/${id}/draft`, json('POST')),
  save: (id: number, number: number, spec: TaskSpec) => api<AdminTask>(`/api/workshop/tasks/${id}/draft`, json('PUT', { number, spec })),
  discard: (id: number) => api<AdminTask>(`/api/workshop/tasks/${id}/draft`, json('DELETE')),
  check: (id: number) => api<AdminTask>(`/api/workshop/tasks/${id}/check`, json('POST')),
  proposal: (id: number, accept: boolean) => api<AdminTask>(`/api/workshop/tasks/${id}/proposal`, json('POST', { accept })),
  publish: (id: number, change_note: string) => api<AdminTask>(`/api/workshop/tasks/${id}/publish`, json('POST', { change_note })),
  archive: (id: number, archived: boolean) => api<AdminTask>(`/api/workshop/tasks/${id}/archive?archived=${archived}`, json('POST')),
  remove: (id: number) => api<void>(`/api/workshop/tasks/${id}`, json('DELETE')),
}
