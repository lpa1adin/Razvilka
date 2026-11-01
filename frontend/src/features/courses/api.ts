import { api } from '@/lib/api'
import type { Fragment, FragmentBrief } from '@/features/library/api'

export type TheoryBlock = { id: string; type: 'theory'; fragment_id: number; why: string }
export type PracticeBlock = { id: string; type: 'practice'; task_id: number }
export type QuizBlock = { id: string; type: 'quiz'; topic_id: number }
export type Block = TheoryBlock | PracticeBlock | QuizBlock
export type Lesson = { id: string; title: string; goal: string; blocks: Block[] }
export type Module = { id: string; title: string; lessons: Lesson[] }
export type CourseContent = { modules: Module[] }

export type CourseCard = {
  slug: string
  title: string
  description: string
  version: number
  lessons_total: number
  lessons_done: number
  next_lesson_id: string | null
  has_update: boolean
}

export type LessonRef = { id: string; title: string; done: boolean }

export type CourseDetail = CourseCard & {
  modules: { id: string; title: string; lessons: LessonRef[] }[]
  published_version: number | null
  preview: boolean
}

export type LessonDetail = {
  course_slug: string
  course_title: string
  version: number
  preview: boolean
  module_title: string
  id: string
  title: string
  goal: string
  blocks: { id: string; type: 'theory'; why: string; fragment: Fragment | null }[]
  practice: { id: string; type: 'practice'; task: { slug: string; title: string; kind: 'web' | 'python' | 'sql'; solved: boolean } | null }[]
  quizzes: { id: string; topic: { slug: string; title: string; questions: number; size: number } | null }[]
  done: boolean
  prev_lesson: LessonRef | null
  next_lesson: LessonRef | null
}

const v = (version?: number | null) => (version ? `?version=${version}` : '')

export const coursesApi = {
  list: () => api<CourseCard[]>('/api/courses'),
  get: (slug: string, version?: number | null) => api<CourseDetail>(`/api/courses/${slug}${v(version)}`),
  lesson: (slug: string, id: string, version?: number | null) => api<LessonDetail>(`/api/courses/${slug}/lessons/${id}${v(version)}`),
  setDone: (slug: string, id: string, done: boolean) => api<void>(`/api/courses/${slug}/lessons/${id}/done`, { method: done ? 'PUT' : 'DELETE' }),
  upgrade: (slug: string) => api<void>(`/api/courses/${slug}/upgrade`, { method: 'POST' }),
}

// ---------- Мастерская ----------

export type VersionStatus = 'draft' | 'published' | 'superseded'

export type AdminCourseBrief = {
  id: number
  slug: string
  title: string
  published_version: number | null
  draft_version: number | null
  archived: boolean
  lessons: number
  updated_at: string
}

export type AdminCourse = {
  id: number
  slug: string
  published_version: number | null
  draft_version: number | null
  archived: boolean
  editing: {
    number: number
    status: VersionStatus
    title: string
    description: string
    content: CourseContent
    change_note: string
    created_at: string
    updated_at: string
    published_at: string | null
  }
  fragments: Record<string, FragmentBrief>
  tasks: Record<string, { title: string; kind: 'web' | 'python' | 'sql'; published: boolean }>
  quiz_topics: Record<string, { title: string; published: boolean }>
}

export type VersionBrief = { number: number; status: VersionStatus; title: string; change_note: string; created_at: string; published_at: string | null }

const json = (method: string, body?: unknown) => ({ method, body: body === undefined ? undefined : JSON.stringify(body) })

export const workshopCoursesApi = {
  list: () => api<AdminCourseBrief[]>('/api/workshop/courses'),
  create: (title: string, description: string) => api<AdminCourse>('/api/workshop/courses', json('POST', { title, description })),
  get: (id: number | string) => api<AdminCourse>(`/api/workshop/courses/${id}`),
  startDraft: (id: number) => api<AdminCourse>(`/api/workshop/courses/${id}/draft`, json('POST')),
  saveDraft: (id: number, body: { number: number; title: string; description: string; content: CourseContent }) =>
    api<AdminCourse>(`/api/workshop/courses/${id}/draft`, json('PUT', body)),
  discardDraft: (id: number) => api<AdminCourse>(`/api/workshop/courses/${id}/draft`, json('DELETE')),
  publish: (id: number, change_note: string) => api<AdminCourse>(`/api/workshop/courses/${id}/publish`, json('POST', { change_note })),
  archive: (id: number, archived: boolean) => api<AdminCourse>(`/api/workshop/courses/${id}/archive?archived=${archived}`, json('POST')),
  remove: (id: number) => api<void>(`/api/workshop/courses/${id}`, json('DELETE')),
  versions: (id: number) => api<VersionBrief[]>(`/api/workshop/courses/${id}/versions`),
}

export function newId(prefix: string) {
  return `${prefix}-${crypto.randomUUID().slice(0, 8)}`
}
