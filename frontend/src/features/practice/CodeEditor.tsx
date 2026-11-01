import Editor, { type OnMount } from '@monaco-editor/react'
import { useEffect, useRef, useState } from 'react'

import { getTheme } from '@/lib/theme'

import { LANGUAGE } from './monaco'

type Props = {
  /** имя файла: по нему выбирается подсветка и отдельная модель (история правок у каждого файла своя) */
  path: string
  value: string
  onChange?: (value: string) => void
  readOnly?: boolean
  label: string
  /** перейти к строке и подсветить её (замечание Ревьюера); key меняется — переход повторяется */
  reveal?: { line: number; key: number } | null
}

export function CodeEditor({ path, value, onChange, readOnly, label, reveal }: Props) {
  const [theme, setTheme] = useState(getTheme)
  const editor = useRef<Parameters<OnMount>[0] | null>(null)
  const marks = useRef<{ clear: () => void } | null>(null)
  // Переход может прийти раньше, чем редактор загрузился (открыли сразу на строке) — ждём монтирования
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const ed = editor.current
    if (!ed || !reveal) return
    ed.revealLineInCenter(reveal.line)
    ed.setPosition({ lineNumber: reveal.line, column: 1 })
    ed.focus()
    marks.current?.clear()
    marks.current = ed.createDecorationsCollection([
      { range: { startLineNumber: reveal.line, startColumn: 1, endLineNumber: reveal.line, endColumn: 1 }, options: { isWholeLine: true, className: 'rz-review-line' } },
    ])
    const timer = window.setTimeout(() => marks.current?.clear(), 2500)
    return () => window.clearTimeout(timer)
  }, [reveal, path, mounted])
  useEffect(() => {
    const sync = () => setTheme(getTheme())
    window.addEventListener('rz:theme', sync)
    return () => window.removeEventListener('rz:theme', sync)
  }, [])

  return (
    <div className="h-full min-h-[120px]" aria-label={label}>
      <Editor
        path={path}
        language={LANGUAGE[path.split('/').pop() ?? ''] ?? 'plaintext'}
        value={value}
        onChange={(v) => onChange?.(v ?? '')}
        onMount={(ed) => {
          editor.current = ed
          setMounted(true)
        }}
        theme={theme === 'dark' ? 'razvilka-dark' : 'razvilka-light'}
        loading={<div className="grid h-full place-items-center text-sm text-muted">Загружаем редактор…</div>}
        options={{
          readOnly,
          fontFamily: "'JetBrains Mono Variable', ui-monospace, monospace",
          fontSize: 14,
          lineHeight: 22,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: path.endsWith('.py') ? 4 : 2,
          padding: { top: 12, bottom: 12 },
          wordWrap: 'on',
          renderLineHighlight: 'line',
          ariaLabel: label,
          // Иначе редактор обводит кириллицу как «похожие на латиницу» символы — для русского текста это шум
          unicodeHighlight: { ambiguousCharacters: false, invisibleCharacters: true },
        }}
      />
    </div>
  )
}
