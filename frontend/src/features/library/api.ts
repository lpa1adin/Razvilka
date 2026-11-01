import { api } from '@/lib/api'

export type LicenseMode = 'full_text' | 'reference'

export type Source = {
  slug: string
  title: string
  author: string
  kind: string
  homepage: string
  license_name: string
  license_url: string
  license_mode: LicenseMode
  license_note: string
  last_commit: string | null
  last_commit_at: string | null
}

export type FragmentBrief = {
  id: number
  title: string
  section: string
  url: string
  status: 'active' | 'removed'
  source: Source
  excerpt: string
  snippet: string | null
}

export type OutlineItem = { level: number; title: string }

export type Fragment = Omit<FragmentBrief, 'excerpt' | 'snippet'> & {
  content_html: string | null
  outline: OutlineItem[]
  source_commit: string
  imported_at: string
  changed_at: string | null
}

export type SearchResult = { total: number; items: FragmentBrief[] }

export const libraryApi = {
  sources: () => api<Source[]>('/api/library/sources'),
  search: (params: { q?: string; source?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') query.set(k, String(v))
    return api<SearchResult>(`/api/library/fragments?${query}`)
  },
  fragment: (id: number | string) => api<Fragment>(`/api/library/fragments/${id}`),
}
