import type { Graph } from '@/features/arch/api'
import { api } from '@/lib/api'

export type PathCard = { slug: string; title: string; description: string; project: string; stages: number; passed: number; workspace: boolean }

export type Workspace = { exists: boolean; files: number; host_path: string; list: string[] }

export type Stage = {
  n: number
  slug: string
  title: string
  goal: string
  goal_html: string
  files: string[]
  theory: { id: number; title: string }[]
  forks: number
  state: 'passed' | 'open' | 'locked'
  attempts: number
  best: number | null
  running: boolean
  last_submission: number | null
}

export type PathDetail = {
  slug: string
  title: string
  description: string
  project: string
  kind: 'web' | 'python'
  published: boolean
  map: Graph & { roles: { path: string; role: string }[]; languages: Record<string, number> }
  workspace: Workspace
  stages: Stage[]
}

export const pathsApi = {
  list: () => api<PathCard[]>('/api/paths'),
  get: (slug: string) => api<PathDetail>(`/api/paths/${slug}`),
  createWorkspace: (slug: string) => api<Workspace>(`/api/paths/${slug}/workspace`, { method: 'POST' }),
  preview: (slug: string) => api<{ url: string }>(`/api/paths/${slug}/preview`),
}
