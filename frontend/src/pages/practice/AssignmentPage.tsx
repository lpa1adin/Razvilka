import { ArrowLeft, ExternalLink, FileArchive, FolderGit2, GitFork, Send } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { Button } from '@/components/ui/Button'
import { inputClass, TextArea } from '@/components/ui/Field'
import { Glider } from '@/components/ui/Glider'
import { Badge, ErrorBlock, Skeleton } from '@/components/ui/States'
import { assessApi, fileToBase64, type ForkAnswer } from '@/features/assess/api'
import { SubmissionBadge } from '@/features/assess/SubmissionBadge'
import { ApiError } from '@/lib/api'
import { useApi } from '@/lib/useApi'

const EMPTY: ForkAnswer = { choice: '', alternatives: '', reasons: '', risks: '', revisit: '' }

export function AssignmentPage() {
  const { slug = '' } = useParams()
  const navigate = useNavigate()
  const { data, error, reload } = useApi(() => assessApi.assignment(slug), [slug])
  const [answers, setAnswers] = useState<Record<string, ForkAnswer>>({})
  const [summary, setSummary] = useState('')
  const [source, setSource] = useState<'zip' | 'folder' | 'workspace' | null>(null)
  const [archive, setArchive] = useState<File | null>(null)
  const [project, setProject] = useState('')
  const [focus, setFocus] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)

  if (error) return <ErrorBlock message={error.message} onRetry={reload} />
  if (!data) return <Skeleton lines={6} />
  // Этап пути сдаётся из рабочей папки — это и есть «напиши заново сам»
  const src = source ?? (data.path ? 'workspace' : 'zip')

  const set = (id: string, patch: Partial<ForkAnswer>) => setAnswers((a) => ({ ...a, [id]: { ...EMPTY, ...a[id], ...patch } }))
  const ready =
    data.forks.every((f) => (answers[f.id]?.choice ?? '').trim().length >= 2 && (answers[f.id]?.reasons ?? '').trim().length >= 10) &&
    (src === 'zip' ? !!archive : src === 'folder' ? !!project : !!data.path?.workspace.exists)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setSending(true)
    setSendError(null)
    try {
      const body =
        src === 'zip'
          ? { answers, summary, source: src, archive: await fileToBase64(archive!), archive_name: archive!.name }
          : src === 'workspace'
            ? { answers, summary, source: src }
            : { answers, summary, source: src, project, focus }
      const sent = await assessApi.submit(slug, body)
      navigate(`/reviews/submissions/${sent.id}`)
    } catch (err) {
      setSendError(err instanceof ApiError ? err.message : 'Не удалось отправить')
      setSending(false)
    }
  }

  return (
    <div className="rise-in mx-auto flex max-w-4xl flex-col gap-6">
      <Link to={data.path ? `/projects/${data.path.slug}` : '/practice?tab=assignments'} className="inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4" aria-hidden /> {data.path ? `${data.path.title} · этап ${data.path.position} из ${data.path.total}` : 'Все практикумы'}
      </Link>
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          <Badge>{data.kind === 'web' ? 'веб' : data.kind === 'python' ? 'Python' : 'любой стек'}</Badge>
          <Badge>{data.has_tests ? 'с автотестами' : 'без автотестов'}</Badge>
          <Badge tone="accent">зачёт от {data.threshold} из 5</Badge>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{data.title}</h1>
      </header>

      <section className="panel p-5">
        <div className="prose-content text-[15px]" dangerouslySetInnerHTML={{ __html: data.statement_html }} />
        <p className="mt-4 border-t border-line pt-4 text-sm text-muted">
          Конвейер: автотесты → независимый Ревьюер (дефекты кода) → Оценщик (решения вместе с кодом). Оценщик сверяет ваши ответы с реализацией: заявили одно, а в коде
          другое — это отдельное, самое заметное замечание «сказал ≠ сделал».
        </p>
      </section>

      {data.references.length > 0 && (
        <section className="flex flex-col gap-2" aria-label="Эталоны">
          <p className="eyebrow">С чем сравнивает Оценщик</p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {data.references.map((r) => (
              <li key={r.id} className="rounded-lg border border-line p-3 text-sm">
                <span className="flex items-center gap-1.5 font-medium">
                  {r.name}
                  {r.url.startsWith('http') && (
                    <a href={r.url} target="_blank" rel="noreferrer noopener" className="text-muted hover:text-accent" aria-label={`Открыть ${r.name}`}>
                      <ExternalLink className="size-3.5" />
                    </a>
                  )}
                </span>
                <span className="mt-1 block text-muted">{r.about}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <form onSubmit={submit} className="flex flex-col gap-6">
        <section className="flex flex-col gap-4" aria-labelledby="forks-title">
          <h2 id="forks-title" className="flex items-center gap-2 text-xl font-semibold">
            <GitFork className="size-5 text-ai" aria-hidden /> Развилки
          </h2>
          <p className="-mt-2 text-sm text-muted">Формат ADR, как в docs/DECISIONS.md: что выбрали, из чего, почему, чем платите и когда пересмотреть. Ответ эталона откроется после оценки.</p>
          {data.forks.map((f, i) => (
            <fieldset key={f.id} className="panel flex flex-col gap-3 p-5">
              <legend className="sr-only">{f.question}</legend>
              <p className="font-medium">
                <span className="mr-2 font-mono text-xs text-faint">{i + 1}</span>
                {f.question}
              </p>
              {f.context && <p className="-mt-1 text-sm text-muted">{f.context}</p>}
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Решение
                <input className={`${inputClass} h-10 font-normal`} placeholder="Что выбрали — коротко" value={answers[f.id]?.choice ?? ''} onChange={(e) => set(f.id, { choice: e.target.value })} />
              </label>
              <div className="grid gap-3 md:grid-cols-2">
                <TextArea label="Варианты" rows={2} placeholder="Что ещё рассматривали" value={answers[f.id]?.alternatives ?? ''} onChange={(e) => set(f.id, { alternatives: e.target.value })} />
                <TextArea label="Почему" rows={2} placeholder="Причины выбора в этом контексте" value={answers[f.id]?.reasons ?? ''} onChange={(e) => set(f.id, { reasons: e.target.value })} />
                <TextArea label="Цена и риски" rows={2} value={answers[f.id]?.risks ?? ''} onChange={(e) => set(f.id, { risks: e.target.value })} />
                <TextArea label="Пересмотреть, когда" rows={2} value={answers[f.id]?.revisit ?? ''} onChange={(e) => set(f.id, { revisit: e.target.value })} />
              </div>
            </fieldset>
          ))}
        </section>

        <TextArea label="Что сделали и почему" rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} hint="Коротко: что в сдаче и на что обратить внимание." />

        <section className="panel flex flex-col gap-4 p-5" aria-labelledby="source-title">
          <h2 id="source-title" className="font-semibold">
            Что сдаёте
          </h2>
          <div role="tablist" aria-label="Источник" className="relative flex w-fit rounded-md border border-line p-0.5 text-sm">
            <Glider />
            {(
              [
                ...(data.path ? ([['workspace', 'Рабочая папка', FolderGit2]] as const) : []),
                ['zip', 'Zip-архив', FileArchive],
                ['folder', 'Папка проекта', FolderGit2],
              ] as const
            ).map(([key, label, Icon]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={src === key}
                onClick={() => setSource(key)}
                className={`relative z-[1] inline-flex items-center gap-2 rounded-[5px] px-3 py-1.5 transition-colors duration-300 ${src === key ? 'text-text' : 'text-muted hover:text-text'}`}
              >
                <Icon className="size-4" aria-hidden /> {label}
              </button>
            ))}
          </div>
          {src === 'workspace' && data.path ? (
            data.path.workspace.exists ? (
              <p className="text-sm">
                Сдаётся папка <span className="font-mono">ProjectsWithClaude/{data.path.workspace.host_path}</span>
                <span className="block font-mono text-xs text-faint">{data.path.workspace.list.join(' · ')}</span>
              </p>
            ) : (
              <p className="text-sm text-ai">
                Рабочей папки ещё нет — создайте её на <Link to={`/projects/${data.path.slug}`} className="underline">странице пути</Link>.
              </p>
            )
          ) : src === 'zip' ? (
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="font-medium">Архив до 20 МБ</span>
              <input type="file" accept=".zip,application/zip" onChange={(e) => setArchive(e.target.files?.[0] ?? null)} className="text-sm file:mr-3 file:rounded-md file:border file:border-line-strong file:bg-surface-2 file:px-3 file:py-1.5 file:text-text" />
            </label>
          ) : (
            <div className="grid gap-3 sm:grid-cols-[1fr_1fr]">
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Папка из ProjectsWithClaude
                <select className={`${inputClass} h-10 font-normal`} value={project} onChange={(e) => setProject(e.target.value)}>
                  <option value="">Выберите…</option>
                  {data.projects.map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Часть проекта (необязательно)
                <input className={`${inputClass} h-10 font-normal`} placeholder="например, server" value={focus} onChange={(e) => setFocus(e.target.value)} />
              </label>
            </div>
          )}
          <p className="text-xs text-faint">node_modules, сборки, бинарные файлы и секреты (.env, ключи) отбрасываются — вы увидите предупреждение в отчёте.</p>
        </section>

        {sendError && <ErrorBlock message={sendError} />}
        <Button type="submit" loading={sending} loadingText="Отправляем…" disabled={!ready} icon={<Send className="size-4" />} className="w-fit">
          Сдать на проверку
        </Button>
        {!ready && <p className="-mt-3 text-xs text-faint">Нужны решение и причины (от 10 символов) по каждой развилке и сам код.</p>}
      </form>

      {data.submissions.length > 0 && (
        <section className="flex flex-col gap-2" aria-labelledby="attempts">
          <h2 id="attempts" className="text-lg font-semibold">
            Мои сдачи
          </h2>
          <ul className="panel divide-y divide-line overflow-hidden">
            {data.submissions.map((s) => (
              <li key={s.id}>
                <Link to={`/reviews/submissions/${s.id}`} className="flex flex-wrap items-center gap-3 px-5 py-3 hover:bg-surface-2/50">
                  <span className="font-mono text-sm">попытка {s.attempt}</span>
                  <span className="text-xs text-faint">{new Date(s.created_at).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}</span>
                  <span className="flex-1" />
                  <SubmissionBadge s={s} />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
