import { ArrowRight, ClipboardCheck, GitFork, GraduationCap, Wand2 } from 'lucide-react'
import { Link } from 'react-router'
import type { ReactNode } from 'react'

import { CodeField } from '@/components/effects/CodeField'
import { ForkParticles } from '@/components/effects/ForkParticles'
import { TypeLine } from '@/components/effects/TypeLine'
import { ButtonLink } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { Progress, Skeleton } from '@/components/ui/States'
import { assessApi } from '@/features/assess/api'
import { SubmissionBadge } from '@/features/assess/SubmissionBadge'
import { useAuth } from '@/features/auth/AuthProvider'
import { coursesApi } from '@/features/courses/api'
import { useSystemStatus, type SystemStatus } from '@/features/system/useSystemStatus'
import { plural } from '@/lib/plural'
import { useApi } from '@/lib/useApi'

function statusText(status: SystemStatus | 'down' | null) {
  if (status === null) return 'razvilka status'
  if (status === 'down') return 'razvilka status → api: нет ответа'
  const workers = status.workers.map((w) => `${w.name} ${w.alive ? 'ok' : '✕'}`).join(' · ')
  return `razvilka status → api ok · ${workers}`
}

export function HomePage() {
  const { user } = useAuth()
  const status = useSystemStatus()
  const isAdmin = user?.role === 'admin'
  const courses = useApi(() => coursesApi.list(), [])
  const journal = useApi(() => assessApi.journal(), [])
  const submissions = useApi(() => assessApi.submissions(), [])
  // «Продолжить» ведёт в первый начатый и незаконченный курс, иначе — в первый курс
  const resume =
    courses.data?.find((c) => c.lessons_done > 0 && c.next_lesson_id) ?? courses.data?.find((c) => c.next_lesson_id)

  return (
    <div className="flex flex-col gap-10">
      <section aria-labelledby="home-title" className="panel relative overflow-hidden">
        <CodeField density={0.8} />
        <div
          aria-hidden
          className="pointer-events-none absolute -right-20 top-1/2 size-[520px] -translate-y-1/2 rounded-full blur-3xl"
          style={{ background: 'radial-gradient(circle, var(--accent-soft) 0%, transparent 65%)' }}
        />
        <div className="relative grid items-center gap-6 p-6 sm:p-10 lg:grid-cols-[1.25fr_1fr] lg:p-12">
          <div className="rise-in">
            <p className="eyebrow">.01 · Учёба</p>
            <h1 id="home-title" className="mt-4 text-[clamp(34px,5vw,56px)] font-semibold leading-[1.05] tracking-[-0.03em]">
              Привет, {user?.display_name}.
              <br />
              <span className="text-muted">Каждое решение — развилка.</span>
            </h1>
            <p className="mt-5 max-w-xl text-muted">
              Теория из проверенных источников, задания с автопроверкой и честная оценка того, как вы выбираете и обосновываете решения.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              {resume ? (
                <ButtonLink to={`/courses/${resume.slug}/lessons/${resume.next_lesson_id}`} icon={<ArrowRight className="size-4" />}>
                  {resume.lessons_done ? 'Продолжить урок' : 'Начать первый курс'}
                </ButtonLink>
              ) : (
                <ButtonLink to="/courses" icon={<GraduationCap className="size-4" />}>
                  Открыть курсы
                </ButtonLink>
              )}
              {isAdmin && (
                <ButtonLink to="/workshop/generate" variant="secondary" icon={<Wand2 className="size-4" />}>
                  Создать курс
                </ButtonLink>
              )}
            </div>
            <p className="mt-8 min-h-[1.5em] font-mono text-[13px] text-muted">
              <span className="text-accent">$ </span>
              <TypeLine key={statusText(status)} text={statusText(status)} />
            </p>
          </div>
          <div className="relative mx-auto aspect-square w-full max-w-[380px] max-lg:max-w-[260px]">
            <ForkParticles />
          </div>
        </div>
      </section>

      <section aria-labelledby="dash-title">
        <h2 id="dash-title" className="sr-only">
          Ваш прогресс
        </h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <DashCard index=".02" title="Прогресс по курсам">
            {courses.loading ? (
              <Skeleton lines={2} />
            ) : courses.data && courses.data.length > 0 ? (
              <ul className="flex flex-col gap-4">
                {courses.data.slice(0, 4).map((c) => (
                  <li key={c.slug}>
                    <Link to={`/courses/${c.slug}`} className="block rounded-md hover:text-accent">
                      <span className="mb-1.5 block truncate text-sm font-medium">{c.title}</span>
                      <Progress done={c.lessons_done} total={c.lessons_total} label="Уроки" />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
            <EmptyState
              icon={<GraduationCap className="size-5" />}
              title="Курсов пока нет"
              text={isAdmin ? 'Создайте первый курс в Мастерской — здесь появится прогресс.' : 'Администратор готовит первый курс — здесь появится ваш прогресс.'}
              action={
                isAdmin ? (
                  <ButtonLink to="/workshop/generate" variant="ghost" className="-ml-3" icon={<ArrowRight className="size-4" />}>
                    В Мастерскую
                  </ButtonLink>
                ) : undefined
              }
            />
            )}
          </DashCard>
          <DashCard index=".03" title="Журнал развилок">
            {journal.loading ? (
              <Skeleton lines={2} />
            ) : journal.data && journal.data.length > 0 ? (
              <ul className="flex flex-col gap-3">
                {journal.data.slice(0, 3).map((j) => (
                  <li key={`${j.submission_id}-${j.fork_id}`} className="min-w-0 text-sm">
                    <span className="block truncate text-muted">{j.question}</span>
                    <span className="block truncate font-medium">→ {j.answer.choice}</span>
                  </li>
                ))}
                <li>
                  <Link to="/forks" className="text-sm text-accent hover:underline">
                    Весь журнал · {journal.data.length} {plural(journal.data.length, 'решение', 'решения', 'решений')}
                  </Link>
                </li>
              </ul>
            ) : (
              <EmptyState
                icon={<GitFork className="size-5" />}
                title="Пока ни одной"
                text="Развилки — в практикумах и этапах проектов: выбираете вариант, объясняете почему, Оценщик сверяет ответ с кодом."
              />
            )}
          </DashCard>
          <DashCard index=".04" title="Свежие оценки">
            {submissions.loading ? (
              <Skeleton lines={2} />
            ) : submissions.data && submissions.data.length > 0 ? (
              <ul className="flex flex-col gap-3">
                {submissions.data.slice(0, 3).map((s) => (
                  <li key={s.id}>
                    <Link to={`/reviews/submissions/${s.id}`} className="flex min-w-0 flex-col gap-1.5 rounded-md hover:text-accent">
                      <span className="truncate text-sm font-medium">
                        {s.assignment_title} · попытка {s.attempt}
                      </span>
                      <SubmissionBadge s={s} />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={<ClipboardCheck className="size-5" />}
                title="Проверок ещё не было"
                text="Сдайте задание или этап проекта — сюда придут автотесты, замечания Ревьюера и оценка."
              />
            )}
          </DashCard>
        </div>
      </section>
    </div>
  )
}

function DashCard({ index, title, children }: { index: string; title: string; children: ReactNode }) {
  return (
    <article className="panel rise-in flex flex-col gap-4 p-5">
      <header className="flex items-baseline justify-between">
        <h3 className="font-semibold">{title}</h3>
        <span className="font-mono text-xs text-faint">{index}</span>
      </header>
      {children}
    </article>
  )
}
