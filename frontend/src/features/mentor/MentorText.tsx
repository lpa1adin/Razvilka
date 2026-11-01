import type { ReactNode } from 'react'
import { Link } from 'react-router'

/**
 * Небольшой markdown для ответов наставника: абзацы, списки, `код`, **жирный**, ссылки и блоки кода.
 * Без innerHTML — текст модели не может вставить на страницу разметку или скрипт.
 */
export function MentorText({ text }: { text: string }) {
  const parts = text.split(/```[\w-]*\n?/)
  return (
    <div className="flex flex-col gap-2.5 text-[15px] leading-relaxed">
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <pre key={i} className="overflow-x-auto rounded-md border border-line bg-bg/70 p-3 font-mono text-[13px] leading-relaxed">
            <code>{part.replace(/\n$/, '')}</code>
          </pre>
        ) : (
          <Blocks key={i} text={part} />
        ),
      )}
    </div>
  )
}

function Blocks({ text }: { text: string }) {
  const blocks = text.trim().split(/\n{2,}/).filter(Boolean)
  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split('\n')
        const bullet = /^\s*([-*•]|\d+[.)])\s+/
        if (lines.every((l) => bullet.test(l))) {
          const ordered = /^\s*\d/.test(lines[0])
          const Tag = ordered ? 'ol' : 'ul'
          return (
            <Tag key={i} className={`flex flex-col gap-1 pl-5 ${ordered ? 'list-decimal' : 'list-disc'} marker:text-faint`}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(bullet, ''))}</li>
              ))}
            </Tag>
          )
        }
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {inline(l.replace(/^#{1,4}\s+/, ''))}
              </span>
            ))}
          </p>
        )
      })}
    </>
  )
}

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const pattern = /(`[^`]+`)|(\*\*[^*]+\*\*)|\[([^\]]+)\]\(([^)\s]+)\)/g
  let last = 0
  for (const m of text.matchAll(pattern)) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const key = `${m.index}`
    if (m[1]) {
      out.push(
        <code key={key} className="rounded border border-line bg-surface-2 px-1 font-mono text-[0.88em]">
          {m[1].slice(1, -1)}
        </code>,
      )
    } else if (m[2]) {
      out.push(<strong key={key}>{m[2].slice(2, -2)}</strong>)
    } else if (m[4].startsWith('/')) {
      // Ссылки на свои страницы (статьи библиотеки) открываются внутри платформы
      out.push(
        <Link key={key} to={m[4]} className="text-accent underline-offset-2 hover:underline">
          {m[3]}
        </Link>,
      )
    } else if (/^https:\/\//.test(m[4])) {
      out.push(
        <a key={key} href={m[4]} target="_blank" rel="noreferrer noopener" className="text-accent underline-offset-2 hover:underline">
          {m[3]}
        </a>,
      )
    } else {
      out.push(m[3])
    }
    last = m.index + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}
