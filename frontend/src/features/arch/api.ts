import { api } from '@/lib/api'

export type Level = 'high' | 'low'
export type Kind = 'choice' | 'diagram' | 'describe'

export type DNode = { id: string; label?: string; kind: string; detail?: string }
export type DEdge = { from: string; to: string; kind?: string }
export type Graph = { nodes: DNode[]; edges: DEdge[] }

export type Material = { file: string; lang: string; path: string; project: string; license: string; url: string; text: string; note: string }

export type Exercise = {
  slug: string
  level: Level
  kind: Kind
  project: string
  title: string
  question: string
  materials: Material[]
  options?: { id: string; text: string }[]
  multiple?: boolean
  nodes?: { id: string; kind: string }[]
  keypoints_count?: number
}

export type Reveal = {
  explanation: string
  auto_diagram: Graph
  auto_from: string
  correct?: string[]
  expected?: [string, string][]
  keypoints?: { id: string; text: string }[]
}

export type Attempt = {
  id: number
  slug: string
  status: 'done' | 'evaluating' | 'failed'
  answer: { picked?: string[]; edges?: [string, string][]; text?: string }
  result: {
    correct?: boolean
    matched?: [string, string][]
    reversed?: [string, string][]
    extra?: [string, string][]
    missed?: [string, string][]
    points?: { id: string; text: string; covered: boolean; quote: string; comment: string }[]
    errors?: string[]
    feedback?: string
    covered?: number
    total?: number
  } | null
  score: number | null
  counted: boolean
  error: string | null
  reveal?: Reveal
  created_at: string
}

export type Card = { n: number; slug: string; title: string; level: Level; kind: Kind; project: string; attempts: number; score: number | null; done: boolean }

export const KIND_LABEL: Record<Kind, string> = { choice: 'выбор', diagram: 'схема', describe: 'своими словами' }
export const LEVEL_LABEL: Record<Level, string> = { high: 'верхний уровень', low: 'нижний уровень' }

export const archApi = {
  list: () => api<Card[]>('/api/arch'),
  get: (slug: string) => api<{ exercise: Exercise; attempts: Attempt[]; counted: Attempt | null; next: string | null }>(`/api/arch/${slug}`),
  submit: (slug: string, answer: unknown) => api<Attempt>(`/api/arch/${slug}/attempts`, { method: 'POST', body: JSON.stringify(answer) }),
  attempt: (id: number) => api<Attempt>(`/api/arch/attempts/${id}`),
}
