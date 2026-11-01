import { ArrowRight, GraduationCap, Sparkles } from 'lucide-react'

import { ButtonLink } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { Badge, ErrorBlock, PageHeader, Progress, Skeleton } from '@/components/ui/States'
import { useAuth } from '@/features/auth/AuthProvider'
import { coursesApi, type CourseCard } from '@/features/courses/api'
import { useApi } from '@/lib/useApi'

export function CoursesPage() {
  const { user } = useAuth()
  const { data, error, loading, reload } = useApi(() => coursesApi.list(), [])

  return (
    <div className="rise-in flex flex-col gap-8">
      <PageHeader eyebrow="Учёба" title="Курсы" text="Каждый урок: цель, теория из источников, а дальше — тест, практика и развилка (появятся на следующих этапах)." />
      {error ? (
        <ErrorBlock message={error.message} onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton lines={3} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={<GraduationCap className="size-5" />}
          title="Курсов пока нет"
          text={user?.role === 'admin' ? 'Создайте первый курс в Мастерской → Контент.' : 'Администратор готовит первый курс — загляните позже.'}
          action={user?.role === 'admin' ? <ButtonLink to="/workshop/content" variant="secondary">Создать курс</ButtonLink> : undefined}
        />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {data.map((course) => (
            <li key={course.slug}>
              <CourseTile course={course} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function CourseTile({ course }: { course: CourseCard }) {
  const started = course.lessons_done > 0
  const finished = course.lessons_total > 0 && course.lessons_done === course.lessons_total
  const target = course.next_lesson_id ? `/courses/${course.slug}/lessons/${course.next_lesson_id}` : `/courses/${course.slug}`
  return (
    <article className="panel flex h-full flex-col gap-4 p-5">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-lg font-semibold">{course.title}</h2>
        {course.has_update && (
          <Badge tone="ai">
            <Sparkles className="size-3" aria-hidden /> новая версия
          </Badge>
        )}
      </div>
      {course.description && <p className="line-clamp-3 text-sm text-muted">{course.description}</p>}
      <div className="mt-auto flex flex-col gap-4">
        <Progress done={course.lessons_done} total={course.lessons_total} label="Пройдено уроков" />
        <div className="flex flex-wrap gap-3">
          <ButtonLink to={finished ? `/courses/${course.slug}` : target} icon={<ArrowRight className="size-4" />}>
            {finished ? 'Повторить курс' : started ? 'Продолжить' : 'Начать курс'}
          </ButtonLink>
          {started && !finished && (
            <ButtonLink to={`/courses/${course.slug}`} variant="ghost">
              Программа
            </ButtonLink>
          )}
        </div>
      </div>
    </article>
  )
}
