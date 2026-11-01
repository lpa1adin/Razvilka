import { AlertTriangle, ExternalLink, FileText, Scale } from 'lucide-react'
import { Fragment as ReactFragment } from 'react'

import { Badge } from '@/components/ui/States'

import type { Fragment, FragmentBrief, OutlineItem, Source } from './api'

const dateFmt = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })

export function formatDate(iso: string | null) {
  return iso ? dateFmt.format(new Date(iso)) : '—'
}

/**
 * Указание авторства одной строкой: источник, автор, лицензия, оригинал, дата версии.
 * Для открытых текстов добавляем «текст адаптирован» — этого требует CC BY-SA (указать изменения).
 */
export function Attribution({ fragment, source }: { fragment: Pick<Fragment, 'url' | 'source_commit'> & Partial<Fragment>; source: Source }) {
  const dot = <span className="text-faint" aria-hidden>·</span>
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-line bg-surface-2/50 px-4 py-2.5 text-sm text-muted">
      <span className="font-medium text-text">{source.title}</span>
      {dot}
      <span>{source.author}</span>
      {dot}
      <a href={source.license_url} target="_blank" rel="noreferrer" title={source.license_note} className="inline-flex items-center gap-1 underline-offset-4 hover:text-text hover:underline">
        <Scale className="size-3.5" aria-hidden />
        {source.license_mode === 'full_text' ? `${source.license_name}, текст адаптирован` : 'лицензия'}
      </a>
      {source.last_commit_at && (
        <>
          {dot}
          <span title={`Версия источника ${fragment.source_commit.slice(0, 7)}`}>версия от {formatDate(source.last_commit_at)}</span>
        </>
      )}
      {/* для «ссылки на материал» ниже есть большая кнопка «Читать на …» — здесь не дублируем */}
      {source.license_mode === 'full_text' && (
        <a href={fragment.url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-accent underline-offset-4 hover:underline">
          Оригинал <ExternalLink className="size-3.5" aria-hidden />
        </a>
      )}
    </p>
  )
}

// Служебные разделы, которые в «о чём статья» только мешают
const SKIP = /^(итого|задачи|резюме|заключение|итоги|смотрите также|см\. также)$/i

/** Краткое содержание по заголовкам статьи — без копирования её текста. */
export function summarize(outline: OutlineItem[]): string {
  const top = outline.filter((o) => o.level === 2 && !SKIP.test(o.title.trim()))
  const items = (top.length ? top : outline.filter((o) => !SKIP.test(o.title.trim()))).map((o) => {
    const t = o.title.trim().replace(/[.:]$/, '')
    // «Сравнение строк» → «сравнение строк», но «JSON», «DOM-дерево» и «null» оставляем как есть
    return /^[А-ЯЁA-Z][а-яёa-z]/.test(t) ? t[0].toLowerCase() + t.slice(1) : t
  })
  if (!items.length) return ''
  const list = items.length === 1 ? items[0] : `${items.slice(0, -1).join(', ')} и ${items[items.length - 1]}`
  return `В статье разбираются: ${list}.`
}

export function FragmentBody({ fragment }: { fragment: Fragment }) {
  if (fragment.status === 'removed') {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
        <p>
          Эта статья пропала из источника при последнем обновлении. Последняя сохранённая версия может быть в{' '}
          <a className="text-accent underline" href={`https://web.archive.org/web/*/${fragment.url}`} target="_blank" rel="noreferrer">
            веб-архиве
          </a>
          .
        </p>
      </div>
    )
  }

  if (fragment.source.license_mode === 'reference' || !fragment.content_html) {
    const summary = summarize(fragment.outline)
    return (
      <div className="flex flex-col gap-4 rounded-lg border border-line p-5">
        <div>
          <p className="eyebrow">О чём статья</p>
          <p className="mt-2 leading-relaxed">{summary || 'Статья открывается на сайте источника.'}</p>
        </div>
        <a
          href={fragment.url}
          target="_blank"
          rel="noreferrer"
          className="group inline-flex w-fit items-center gap-2 rounded-md border border-line-strong bg-surface-2/60 px-4 py-2.5 font-medium transition-[border-color,color,transform] hover:-translate-y-px hover:border-accent/60 hover:text-accent"
        >
          <FileText className="size-4" aria-hidden />
          Читать на {new URL(fragment.url).hostname}
          <ExternalLink className="size-4" aria-hidden />
        </a>
      </div>
    )
  }

  // HTML очищен на сервере при импорте (nh3, белый список тегов) — вставлять его безопасно
  return <div className="prose-content" dangerouslySetInnerHTML={{ __html: fragment.content_html }} />
}

/** Фрагмент текста с найденными словами: части между \x01 и \x02 подсвечиваются. */
export function Snippet({ text }: { text: string }) {
  const parts = text.split(/[\x01\x02]/)
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="rounded-sm bg-accent-soft px-0.5 text-accent">
            {part}
          </mark>
        ) : (
          <ReactFragment key={i}>{part}</ReactFragment>
        ),
      )}
    </>
  )
}

export function SourceBadge({ fragment }: { fragment: FragmentBrief }) {
  return (
    <Badge tone={fragment.source.license_mode === 'full_text' ? 'accent' : 'muted'}>
      {fragment.source.license_mode === 'full_text' ? 'полный текст' : 'ссылка на материал'}
    </Badge>
  )
}
