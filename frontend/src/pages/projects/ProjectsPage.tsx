import { CheckCircle2, Copy, FolderGit2, FolderPlus, Lock, Map as MapIcon, Play, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'

import { Button, ButtonLink } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { Badge, ErrorBlock, PageHeader, Progress, Skeleton } from '@/components/ui/States'
import { Diagram, Legend } from '@/features/arch/Diagram'
import { pathsApi } from '@/features/paths/api'
import { ApiError } from '@/lib/api'
import { useApi } from '@/lib/useApi'

export function ProjectsPage() {
  const { data, error, loading, reload } = useApi(() => pathsApi.list(), [])
  return (
    <div className="rise-in flex flex-col gap-8">
      <PageHeader
        eyebrow="Учёба"
        title="Мои проекты"
        text="Пути «напиши заново сам»: настоящий проект, разложенный на этапы. Вы пишете его с пустой папки в своём редакторе; каждый этап сдаётся на проверку — автотесты, Ревьюер и Оценщик."
      />
      {error ? (
        <ErrorBlock message={error.message} onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton lines={3} />
      ) : data.length === 0 ? (
        <EmptyState icon={<FolderGit2 className="size-5" />} title="Путей пока нет" text="Администратор строит пути в Мастерской → Генерация → «Путь „напиши заново сам“»." />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {data.map((p) => (
            <li key={p.slug}>
              <Link to={`/projects/${p.slug}`} className="panel group flex h-full flex-col gap-3 p-5 transition-colors hover:border-accent/40">
                <div className="flex flex-wrap gap-2">
                  <Badge>проект {p.project}</Badge>
                  {p.passed === p.stages && <Badge tone="accent">пройден</Badge>}
                </div>
                <h2 className="text-lg font-semibold group-hover:text-accent">{p.title}</h2>
                <p className="line-clamp-2 text-sm text-muted">{p.description}</p>
                <div className="mt-auto">
                  <Progress done={p.passed} total={p.stages} label="Этапов сдано" />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function PathPage() {
  const { slug = '' } = useParams()
  const { data, error, reload, setData } = useApi(() => pathsApi.get(slug), [slug])
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const [previewKey, setPreviewKey] = useState(0)
  const [message, setMessage] = useState<string | null>(null)

  const workspaceReady = data?.workspace.exists
  useEffect(() => {
    if (workspaceReady && data?.kind === 'web') pathsApi.preview(slug).then((r) => setPreview(r.url), () => undefined)
  }, [workspaceReady, slug, data?.kind])

  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (!data) return <Skeleton lines={6} />

  const createWorkspace = async () => {
    setBusy(true)
    try {
      const ws = await pathsApi.createWorkspace(slug)
      setData({ ...data, workspace: ws })
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : 'Не удалось создать папку')
    } finally {
      setBusy(false)
    }
  }
  const passed = data.stages.filter((s) => s.state === 'passed').length

  return (
    <div className="rise-in flex flex-col gap-6">
      <Link to="/projects" className="w-fit text-sm text-muted hover:text-text">
        ← Мои проекты
      </Link>
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          <Badge>оригинал: {data.project}</Badge>
          {!data.published && <Badge tone="ai">черновик — видит только админ</Badge>}
        </div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{data.title}</h1>
        <p className="max-w-3xl text-muted">{data.description}</p>
        <div className="max-w-md">
          <Progress done={passed} total={data.stages.length} label="Этапов сдано" />
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <section className="flex flex-col gap-3" aria-labelledby="stages-title">
          <h2 id="stages-title" className="text-xl font-semibold">
            Этапы
          </h2>
          <ol className="flex flex-col gap-3">
            {data.stages.map((s) => (
              <li key={s.slug} className={`panel flex flex-col gap-3 p-5 ${s.state === 'locked' ? 'opacity-60' : ''} ${s.state === 'open' ? 'border-accent/40' : ''}`}>
                <div className="flex flex-wrap items-center gap-2">
                  {s.state === 'passed' ? <CheckCircle2 className="size-5 text-accent" aria-hidden /> : s.state === 'locked' ? <Lock className="size-4 text-faint" aria-hidden /> : <Play className="size-4 text-accent" aria-hidden />}
                  <h3 className="flex-1 font-semibold">{s.title}</h3>
                  {s.best !== null && <Badge tone={s.state === 'passed' ? 'accent' : 'muted'}>лучший итог {s.best.toFixed(1)}</Badge>}
                  {s.running && <Badge tone="ai">проверяется…</Badge>}
                </div>
                <p className="text-sm text-muted">{s.goal}</p>
                {s.files.length > 0 && (
                  <p className="font-mono text-xs text-faint">
                    файлы: {s.files.join(', ')}
                  </p>
                )}
                {s.theory.length > 0 && (
                  <p className="text-sm">
                    <span className="text-muted">Теория: </span>
                    {s.theory.map((t, i) => (
                      <span key={t.id}>
                        {i > 0 && ', '}
                        <Link to={`/library/${t.id}`} className="text-accent hover:underline">
                          {t.title}
                        </Link>
                      </span>
                    ))}
                  </p>
                )}
                <div className="flex flex-wrap gap-2">
                  {s.state === 'locked' ? (
                    <span className="text-xs text-faint">Откроется, когда будет засчитан предыдущий этап</span>
                  ) : (
                    <ButtonLink to={`/practice/assignments/${s.slug}`} variant={s.state === 'open' ? 'primary' : 'secondary'} className="h-9">
                      {s.state === 'passed' ? 'Условие и сдачи' : `Развилки (${s.forks}) и сдача`}
                    </ButtonLink>
                  )}
                  {s.last_submission && (
                    <ButtonLink to={`/reviews/submissions/${s.last_submission}`} variant="ghost" className="h-9">
                      Последний отчёт
                    </ButtonLink>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>

        <aside className="flex flex-col gap-6">
          <section className="panel flex flex-col gap-3 p-5" aria-labelledby="ws-title">
            <h2 id="ws-title" className="flex items-center gap-2 font-semibold">
              <FolderGit2 className="size-4 text-muted" aria-hidden /> Рабочая папка
            </h2>
            {data.workspace.exists ? (
              <>
                <p className="text-sm text-muted">Пишите код здесь в своём редакторе (VS Code): оригинал не копируется, проект собирается заново.</p>
                <button
                  type="button"
                  onClick={() => navigator.clipboard?.writeText(data.workspace.host_path).then(() => setMessage('Путь скопирован'))}
                  className="flex w-full items-center gap-2 rounded-md border border-line bg-bg/60 px-3 py-2 text-left font-mono text-sm hover:border-accent/50"
                  title="Скопировать путь"
                >
                  <span className="flex-1 truncate">ProjectsWithClaude/{data.workspace.host_path}</span>
                  <Copy className="size-4 shrink-0 text-muted" aria-hidden />
                </button>
                <p className="font-mono text-xs text-faint">{data.workspace.list.join(' · ') || 'пусто'}</p>
              </>
            ) : (
              <>
                <p className="text-sm text-muted">Создайте пустую папку — в ней вы напишете проект с нуля, этап за этапом.</p>
                <Button onClick={createWorkspace} loading={busy} icon={<FolderPlus className="size-4" />} className="w-fit">
                  Создать рабочую папку
                </Button>
              </>
            )}
            {message && (
              <p role="status" className="text-xs text-accent">
                {message}
              </p>
            )}
          </section>

          {preview && (
            <section className="panel flex flex-col overflow-hidden" aria-labelledby="pv-title">
              <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
                <h2 id="pv-title" className="flex-1 text-sm font-semibold">
                  Превью рабочей папки
                </h2>
                <button type="button" onClick={() => (setPreviewKey((k) => k + 1), reload())} className="grid size-8 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-text" aria-label="Обновить превью">
                  <RefreshCw className="size-4" />
                </button>
              </div>
              {/* Код ученика — в изолированном iframe: без доступа к платформе (CSP sandbox приходит и с сервера) */}
              <iframe key={previewKey} src={preview} title="Превью рабочей папки" sandbox="allow-scripts allow-forms" className="h-[420px] w-full bg-white" />
            </section>
          )}

          <section className="panel flex flex-col gap-3 p-5" aria-labelledby="map-title">
            <h2 id="map-title" className="flex items-center gap-2 font-semibold">
              <MapIcon className="size-4 text-muted" aria-hidden /> Карта оригинала
            </h2>
            <p className="text-sm text-muted">Устройство проекта без кода: файлы, связи и роль каждой части. Код автора не показываем — вы пишете свой.</p>
            {data.map.nodes.length > 0 && (
              <>
                <div className="overflow-x-auto rounded-lg border border-line bg-bg/50">
                  <Diagram label="Карта проекта" graph={data.map} />
                </div>
                <Legend kinds={data.map.nodes.map((n) => n.kind)} />
              </>
            )}
            <dl className="flex flex-col gap-2 text-sm">
              {data.map.roles.map((r) => (
                <div key={r.path}>
                  <dt className="font-mono text-xs text-accent">{r.path}</dt>
                  <dd className="text-muted">{r.role}</dd>
                </div>
              ))}
            </dl>
          </section>
        </aside>
      </div>
    </div>
  )
}
