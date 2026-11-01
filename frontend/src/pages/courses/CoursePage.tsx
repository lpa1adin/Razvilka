import { ArrowLeft, ArrowRight, CheckCircle2, Circle, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { Button, ButtonLink } from '@/components/ui/Button'
import { ErrorBlock, Progress, Skeleton } from '@/components/ui/States'
import { coursesApi } from '@/features/courses/api'
import { PreviewBanner } from '@/features/courses/PreviewBanner'
import { useApi } from '@/lib/useApi'

export function CoursePage() {
  const { slug = '' } = useParams()
  const [params] = useSearchParams()
  const preview = params.get('version') ? Number(params.get('version')) : null
  const { data, error, loading, reload } = useApi(() => coursesApi.get(slug, preview), [slug, preview])
  const [upgrading, setUpgrading] = useState(false)

  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (loading || !data) return <Skeleton lines={4} />

  const query = preview ? `?version=${preview}` : ''
  const next = data.next_lesson_id ?? data.modules[0]?.lessons[0]?.id

  const upgrade = async () => {
    setUpgrading(true)
    try {
      await coursesApi.upgrade(slug)
      reload()
    } finally {
      setUpgrading(false)
    }
  }

  return (
    <div className="rise-in mx-auto flex max-w-3xl flex-col gap-8">
      {data.preview && <PreviewBanner version={data.version} />}
      <Link to="/courses" className="inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4" aria-hidden /> Все курсы
      </Link>

      <header className="flex flex-col gap-4">
        <p className="eyebrow">Курс · версия {data.version}</p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{data.title}</h1>
        {data.description && <p className="whitespace-pre-line text-muted">{data.description}</p>}
        <Progress done={data.lessons_done} total={data.lessons_total} label="Пройдено уроков" />
        {next && (
          <ButtonLink to={`/courses/${slug}/lessons/${next}${query}`} className="w-fit" icon={<ArrowRight className="size-4" />}>
            {!data.next_lesson_id ? 'Повторить с первого урока' : data.lessons_done ? 'Продолжить' : 'Начать с первого урока'}
          </ButtonLink>
        )}
      </header>

      {data.has_update && !data.preview && (
        <div className="panel flex flex-wrap items-center gap-4 border-ai/40 p-4">
          <Sparkles className="size-5 text-ai" aria-hidden />
          <p className="flex-1 text-sm">
            Вышла версия {data.published_version}. Вы проходите версию {data.version}; пройденные уроки при переходе сохранятся.
          </p>
          <Button variant="secondary" onClick={upgrade} loading={upgrading} loadingText="Переходим…">
            Перейти на новую версию
          </Button>
        </div>
      )}

      <ol className="flex flex-col gap-6">
        {data.modules.map((module, mi) => (
          <li key={module.id} className="panel p-5">
            <h2 className="flex items-baseline gap-3 font-semibold">
              <span className="font-mono text-xs text-faint">{String(mi + 1).padStart(2, '0')}</span>
              {module.title}
            </h2>
            <ol className="mt-3 flex flex-col">
              {module.lessons.map((lesson) => (
                <li key={lesson.id}>
                  <Link
                    to={`/courses/${slug}/lessons/${lesson.id}${query}`}
                    className="flex items-center gap-3 rounded-md px-2 py-2.5 hover:bg-surface-2"
                  >
                    {lesson.done ? (
                      <CheckCircle2 className="size-[18px] shrink-0 text-accent" aria-label="Пройден" />
                    ) : (
                      <Circle className="size-[18px] shrink-0 text-faint" aria-label="Не пройден" />
                    )}
                    <span className={lesson.done ? 'text-muted' : ''}>{lesson.title}</span>
                  </Link>
                </li>
              ))}
            </ol>
          </li>
        ))}
      </ol>
    </div>
  )
}
