import { ArrowLeft, ArrowRight, BookOpen, Check, CheckCircle2, ClipboardList, GitFork, Lightbulb, SquareTerminal, Target } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { Button, ButtonLink } from '@/components/ui/Button'
import { Glider } from '@/components/ui/Glider'
import { Badge, ErrorBlock, Skeleton } from '@/components/ui/States'
import { coursesApi } from '@/features/courses/api'
import { PreviewBanner } from '@/features/courses/PreviewBanner'
import { Attribution, FragmentBody } from '@/features/library/FragmentView'
import { KIND_LABEL } from '@/features/practice/api'
import { useMentorContext } from '@/features/mentor/MentorProvider'
import { useApi } from '@/lib/useApi'

const LATER_TABS = [{ label: 'Развилка', icon: GitFork, stage: '6' }]

type Tab = 'theory' | 'practice' | 'quiz'

export function LessonPage() {
  const { slug = '', lessonId = '' } = useParams()
  const [params] = useSearchParams()
  const preview = params.get('version') ? Number(params.get('version')) : null
  const navigate = useNavigate()
  const { data, error, loading, reload, setData } = useApi(() => coursesApi.lesson(slug, lessonId, preview), [slug, lessonId, preview])
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('theory')
  useEffect(() => setTab('theory'), [lessonId])
  useMentorContext(data && !data.preview ? { kind: 'lesson', ref: `${slug}/${lessonId}`, label: `Урок: ${data.title}` } : null)

  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (loading || !data) return <Skeleton lines={5} />

  const query = preview ? `?version=${preview}` : ''

  const toggleDone = async (goNext: boolean) => {
    setSaving(true)
    setSaveError(null)
    try {
      await coursesApi.setDone(slug, lessonId, !data.done)
      setData({ ...data, done: !data.done })
      if (goNext && data.next_lesson) navigate(`/courses/${slug}/lessons/${data.next_lesson.id}`)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Не удалось сохранить')
    } finally {
      setSaving(false)
    }
  }

  return (
    <article className="rise-in mx-auto flex max-w-3xl flex-col gap-8">
      {data.preview && <PreviewBanner version={data.version} />}
      <nav aria-label="Хлебные крошки" className="flex flex-wrap items-center gap-2 text-sm text-muted">
        <Link to={`/courses/${slug}${query}`} className="inline-flex items-center gap-2 hover:text-text">
          <ArrowLeft className="size-4" aria-hidden /> {data.course_title}
        </Link>
        <span aria-hidden>/</span>
        <span>{data.module_title}</span>
      </nav>

      <header className="flex flex-col gap-4">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{data.title}</h1>
        {data.goal && (
          <p className="flex items-start gap-3 rounded-lg border border-line bg-surface-2/50 p-4">
            <Target className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
            <span>
              <span className="font-medium">Цель урока. </span>
              <span className="text-muted">{data.goal}</span>
            </span>
          </p>
        )}
      </header>

      <div role="tablist" aria-label="Части урока" className="relative flex gap-1 overflow-x-auto border-b border-line">
        <Glider variant="underline" />
        {(
          [
            ['theory', 'Теория', BookOpen, data.blocks.length],
            ['practice', 'Практика', SquareTerminal, data.practice.length],
            ['quiz', 'Тест', ClipboardList, data.quizzes.length],
          ] as const
        ).map(([key, label, Icon, count]) =>
          count ? (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`relative z-[1] inline-flex shrink-0 items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-300 ${tab === key ? 'font-medium text-text' : 'text-muted hover:text-text'}`}
            >
              <Icon className="size-4" aria-hidden /> {label}
              {key !== 'theory' && <span className="font-mono text-[11px] text-faint">{count}</span>}
            </button>
          ) : (
            <span key={key} role="tab" aria-disabled className="inline-flex shrink-0 cursor-not-allowed items-center gap-2 px-4 py-2.5 text-sm text-faint" title="В этом уроке такого блока нет">
              <Icon className="size-4" aria-hidden /> {label}
            </span>
          ),
        )}
        {LATER_TABS.map(({ label, icon: Icon, stage }) => (
          <span key={label} role="tab" aria-disabled title={`Появится на этапе ${stage}`} className="inline-flex shrink-0 cursor-not-allowed items-center gap-2 px-4 py-2.5 text-sm text-faint">
            <Icon className="size-4" aria-hidden /> {label}
            <span className="font-mono text-[10px]">этап {stage}</span>
          </span>
        ))}
      </div>

      {tab === 'practice' && (
        <ul className="flex flex-col gap-3">
          {data.practice.map((block) =>
            block.task ? (
              <li key={block.id} className="panel flex flex-wrap items-center gap-4 p-5">
                <div className="min-w-[200px] flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge>{KIND_LABEL[block.task.kind]}</Badge>
                    {block.task.solved && (
                      <Badge tone="accent">
                        <CheckCircle2 className="size-3" aria-hidden /> решено
                      </Badge>
                    )}
                  </div>
                  <h2 className="mt-2 text-lg font-semibold">{block.task.title}</h2>
                </div>
                <ButtonLink
                  to={`/practice/${block.task.slug}?from=${encodeURIComponent(`/courses/${slug}/lessons/${lessonId}${query}`)}`}
                  variant={block.task.solved ? 'secondary' : 'primary'}
                  icon={<SquareTerminal className="size-4" />}
                >
                  {block.task.solved ? 'Открыть решение' : 'Решать задание'}
                </ButtonLink>
              </li>
            ) : (
              <li key={block.id} className="panel p-5 text-sm text-muted">
                Задание снято с публикации.
              </li>
            ),
          )}
        </ul>
      )}

      {tab === 'quiz' && (
        <ul className="flex flex-col gap-3">
          {data.quizzes.map((q) =>
            q.topic ? (
              <li key={q.id} className="panel flex flex-wrap items-center gap-4 p-5">
                <div className="min-w-[200px] flex-1">
                  <p className="eyebrow">Тест · {Math.min(q.topic.size, q.topic.questions)} вопросов</p>
                  <h2 className="mt-2 text-lg font-semibold">{q.topic.title}</h2>
                </div>
                <ButtonLink to={`/practice/tests/${q.topic.slug}?from=${encodeURIComponent(`/courses/${slug}/lessons/${lessonId}${query}`)}`} icon={<ClipboardList className="size-4" />}>
                  Пройти тест
                </ButtonLink>
              </li>
            ) : (
              <li key={q.id} className="panel p-5 text-sm text-muted">
                Тест снят с публикации.
              </li>
            ),
          )}
        </ul>
      )}

      <div className={`flex flex-col gap-12 ${tab === 'theory' ? '' : 'hidden'}`}>
        {data.blocks.map((block, i) => (
          <section key={block.id} aria-labelledby={`block-${block.id}`} className="flex flex-col gap-5">
            <div className="flex items-baseline gap-3">
              <span className="font-mono text-xs text-faint">.{String(i + 1).padStart(2, '0')}</span>
              <h2 id={`block-${block.id}`} className="text-xl font-semibold">
                {block.fragment?.title ?? 'Статья удалена из библиотеки'}
              </h2>
            </div>
            {block.why && (
              <p className="flex items-start gap-3 text-sm">
                <Lightbulb className="mt-0.5 size-4 shrink-0 text-ai" aria-hidden />
                <span>
                  <span className="font-medium">Зачем читать: </span>
                  <span className="text-muted">{block.why}</span>
                </span>
              </p>
            )}
            {block.fragment && (
              <>
                <Attribution fragment={block.fragment} source={block.fragment.source} />
                <FragmentBody fragment={block.fragment} />
              </>
            )}
          </section>
        ))}
      </div>

      <footer className="panel flex flex-col gap-4 p-5">
        {data.preview ? (
          <p className="text-sm text-muted">В предпросмотре урок нельзя отметить пройденным.</p>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            {data.done ? (
              <>
                <span className="inline-flex items-center gap-2 text-accent">
                  <Check className="size-4" aria-hidden /> Урок пройден
                </span>
                <Button variant="ghost" onClick={() => toggleDone(false)} loading={saving}>
                  Снять отметку
                </Button>
              </>
            ) : (
              <Button onClick={() => toggleDone(true)} loading={saving} loadingText="Сохраняем…" icon={<Check className="size-4" />}>
                {data.next_lesson ? 'Урок пройден — дальше' : 'Отметить урок пройденным'}
              </Button>
            )}
          </div>
        )}
        {saveError && (
          <p role="alert" className="text-sm text-danger">
            {saveError}
          </p>
        )}
        <div className="flex flex-wrap justify-between gap-3 border-t border-line pt-4 text-sm">
          {data.prev_lesson ? (
            <Link to={`/courses/${slug}/lessons/${data.prev_lesson.id}${query}`} className="inline-flex items-center gap-2 text-muted hover:text-text">
              <ArrowLeft className="size-4" aria-hidden /> {data.prev_lesson.title}
            </Link>
          ) : (
            <span />
          )}
          {data.next_lesson ? (
            <Link to={`/courses/${slug}/lessons/${data.next_lesson.id}${query}`} className="inline-flex items-center gap-2 text-muted hover:text-text">
              {data.next_lesson.title} <ArrowRight className="size-4" aria-hidden />
            </Link>
          ) : (
            <ButtonLink to={`/courses/${slug}${query}`} variant="ghost">
              К программе курса
            </ButtonLink>
          )}
        </div>
      </footer>
    </article>
  )
}
