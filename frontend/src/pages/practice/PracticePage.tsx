import { CheckCircle2, ClipboardList, Code2, GitFork, Network, Sparkles } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { EmptyState } from '@/components/ui/EmptyState'
import { Glider } from '@/components/ui/Glider'
import { Badge, ErrorBlock, PageHeader, Skeleton } from '@/components/ui/States'
import { useAuth } from '@/features/auth/AuthProvider'
import { KIND_LABEL, practiceApi } from '@/features/practice/api'
import { archApi, LEVEL_LABEL } from '@/features/arch/api'
import { assessApi } from '@/features/assess/api'
import { quizApi } from '@/features/quiz/api'
import { useApi } from '@/lib/useApi'

type Tab = 'sandbox' | 'tests' | 'assignments' | 'arch'
const TABS: { key: Tab; label: string; icon: typeof Code2 }[] = [
  { key: 'sandbox', label: 'Песочница', icon: Code2 },
  { key: 'tests', label: 'Тесты', icon: ClipboardList },
  { key: 'arch', label: 'Тренажёр архитектуры', icon: Network },
  { key: 'assignments', label: 'Практикумы', icon: GitFork },
]

export function PracticePage() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  const tab: Tab = raw === 'tests' || raw === 'assignments' || raw === 'arch' ? raw : 'sandbox'
  const { data, error, loading, reload } = useApi(() => practiceApi.list(), [])

  return (
    <div className="rise-in flex flex-col gap-8">
      <PageHeader eyebrow="Учёба" title="Практика" text="Задания с автопроверкой прямо в браузере, тесты по темам без повторов и практикумы: сдача проекта с оценкой решений вместе с кодом." />

      <div role="tablist" aria-label="Разделы практики" className="relative flex gap-1 overflow-x-auto border-b border-line">
        <Glider variant="underline" />
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setParams(key === 'sandbox' ? {} : { tab: key }, { replace: true })}
            className={`relative z-[1] inline-flex shrink-0 items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-300 ${tab === key ? 'font-medium text-text' : 'text-muted hover:text-text'}`}
          >
            <Icon className="size-4" aria-hidden /> {label}
          </button>
        ))}
      </div>

      {tab === 'arch' ? (
        <ArchList />
      ) : tab === 'assignments' ? (
        <AssignmentsList />
      ) : tab === 'tests' ? (
        <TestsList />
      ) : error ? (
        <ErrorBlock message={error.message} onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton lines={3} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={<Code2 className="size-5" />}
          title="Заданий пока нет"
          text={user?.role === 'admin' ? 'Создайте задание в Мастерской → Контент → Задания и опубликуйте его после автопроверки.' : 'Администратор готовит задания — загляните позже.'}
        />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((task) => (
            <li key={task.slug}>
              <Link to={`/practice/${task.slug}`} className="panel group flex h-full flex-col gap-3 p-5 transition-colors hover:border-accent/40">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>{KIND_LABEL[task.kind]}</Badge>
                  {task.solved && (
                    <Badge tone="accent">
                      <CheckCircle2 className="size-3" aria-hidden /> решено
                    </Badge>
                  )}
                  {!task.solved && task.started && <Badge tone="ai">начато</Badge>}
                  {task.has_update && (
                    <Badge tone="ai">
                      <Sparkles className="size-3" aria-hidden /> обновлено
                    </Badge>
                  )}
                </div>
                <h2 className="text-lg font-semibold group-hover:text-accent">{task.title}</h2>
                <span className="mt-auto text-sm text-muted">{task.solved ? 'Открыть решение' : task.started ? 'Продолжить' : 'Начать'} →</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function TestsList() {
  const { data, error, loading, reload } = useApi(() => quizApi.topics(), [])
  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (loading || !data) return <Skeleton lines={3} />
  if (data.length === 0) {
    return <EmptyState icon={<ClipboardList className="size-5" />} title="Тестов пока нет" text="Администратор готовит банки вопросов — загляните позже." />
  }
  return (
    <ul className="grid gap-4 md:grid-cols-2">
      {data.map((t) => (
        <li key={t.slug}>
          <Link to={`/practice/tests/${t.slug}`} className="panel group flex h-full flex-col gap-3 p-5 transition-colors hover:border-accent/40">
            <div className="flex flex-wrap items-center gap-2">
              <Badge>{Math.min(t.size, t.questions)} вопросов</Badge>
              {t.active_attempt_id && <Badge tone="ai">тест начат</Badge>}
              {t.last_total !== null && (
                <Badge tone={t.last_score === t.last_total ? 'accent' : 'muted'}>
                  прошлый раз {t.last_score} из {t.last_total}
                </Badge>
              )}
            </div>
            <h2 className="text-lg font-semibold group-hover:text-accent">{t.title}</h2>
            {t.description && <p className="line-clamp-2 text-sm text-muted">{t.description}</p>}
            <p className="mt-auto text-sm text-muted">
              Новых для вас вопросов: <span className="font-mono text-text">{t.unseen}</span> из {t.questions} ·{' '}
              {t.active_attempt_id ? 'Продолжить' : 'Пройти тест'} →
            </p>
          </Link>
        </li>
      ))}
    </ul>
  )
}


function AssignmentsList() {
  const { data, error, loading, reload } = useApi(() => assessApi.assignments(), [])
  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (loading || !data) return <Skeleton lines={3} />
  if (data.length === 0) {
    return <EmptyState icon={<GitFork className="size-5" />} title="Практикумов пока нет" text="Администратор готовит практикумы — загляните позже." />
  }
  return (
    <ul className="grid gap-4 md:grid-cols-2">
      {data.map((a) => (
        <li key={a.slug}>
          <Link to={`/practice/assignments/${a.slug}`} className="panel group flex h-full flex-col gap-3 p-5 transition-colors hover:border-accent/40">
            <div className="flex flex-wrap items-center gap-2">
              <Badge>{a.kind === 'web' ? 'веб' : a.kind === 'python' ? 'Python' : 'любой стек'}</Badge>
              <Badge tone="ai">развилок · {a.forks}</Badge>
              {a.passed && <Badge tone="accent">зачтено</Badge>}
              {!a.passed && a.best_score !== null && <Badge>лучший итог {a.best_score.toFixed(1)}</Badge>}
            </div>
            <h2 className="text-lg font-semibold group-hover:text-accent">{a.title}</h2>
            <span className="mt-auto text-sm text-muted">{a.attempts ? `Сдач: ${a.attempts} · Сдать снова` : 'Сдать на проверку'} →</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function ArchList() {
  const { data, error, loading, reload } = useApi(() => archApi.list(), [])
  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (loading || !data) return <Skeleton lines={4} />
  const groups = [
    { kind: 'choice', title: 'Шаг 1. Выбрать из вариантов' },
    { kind: 'diagram', title: 'Шаг 2. Собрать схему' },
    { kind: 'describe', title: 'Шаг 3. Описать своими словами' },
  ] as const
  return (
    <div className="flex flex-col gap-6">
      <p className="max-w-3xl text-sm text-muted">
        Реальные открытые проекты: верхний уровень (compose, Kubernetes, дерево репозитория) и нижний (классы, функции, вызовы). Засчитывается первый ответ — после него
        открываются разбор и схема, которую платформа построила по файлу; повторять можно для тренировки.
      </p>
      {groups.map((g) => (
        <section key={g.kind} className="flex flex-col gap-3" aria-label={g.title}>
          <h2 className="text-lg font-semibold">{g.title}</h2>
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.filter((c) => c.kind === g.kind).map((c) => (
              <li key={c.slug}>
                <Link to={`/practice/arch/${c.slug}`} className="panel group flex h-full flex-col gap-2 p-4 transition-colors hover:border-accent/40">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-faint">{String(c.n).padStart(2, '0')}</span>
                    <Badge tone={c.level === 'high' ? 'accent' : 'ai'}>{LEVEL_LABEL[c.level]}</Badge>
                    {c.score !== null && <Badge tone={c.score >= 4 ? 'accent' : 'muted'}>{c.score.toFixed(1)} из 5</Badge>}
                  </div>
                  <h3 className="font-semibold group-hover:text-accent">{c.title}</h3>
                  <p className="mt-auto text-xs text-faint">{c.project}</p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
