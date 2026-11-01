/*
  Monaco (движок VS Code, ADR-005) — собирается вместе с приложением, без CDN.
  Этот модуль грузится только на экранах практики (React.lazy), поэтому не утяжеляет остальные страницы.
*/
import { loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor'
import EditorWorker from 'monaco-editor/editor/editor.worker?worker'
import CssWorker from 'monaco-editor/language/css/css.worker?worker'
import HtmlWorker from 'monaco-editor/language/html/html.worker?worker'
import TsWorker from 'monaco-editor/language/typescript/ts.worker?worker'

self.MonacoEnvironment = {
  getWorker(_: string, label: string) {
    if (label === 'css') return new CssWorker()
    if (label === 'html') return new HtmlWorker()
    if (label === 'typescript' || label === 'javascript') return new TsWorker()
    return new EditorWorker()
  },
}

monaco.editor.defineTheme('razvilka-dark', {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: 'comment', foreground: '6b7480', fontStyle: 'italic' },
    { token: 'keyword', foreground: '5be49b' },
    { token: 'string', foreground: 'f5c97a' },
    { token: 'number', foreground: 'f5a524' },
    { token: 'tag', foreground: '5be49b' },
    { token: 'attribute.name', foreground: '9cd7ff' },
  ],
  colors: {
    'editor.background': '#0e1115',
    'editor.lineHighlightBackground': '#161a20',
    'editorLineNumber.foreground': '#3c444f',
    'editorLineNumber.activeForeground': '#8a93a0',
    'editorCursor.foreground': '#5be49b',
    'editor.selectionBackground': '#5be49b33',
    'editorIndentGuide.background1': '#1f242c',
  },
})

monaco.editor.defineTheme('razvilka-light', {
  base: 'vs',
  inherit: true,
  rules: [
    { token: 'keyword', foreground: '12804a' },
    { token: 'tag', foreground: '12804a' },
  ],
  colors: { 'editor.background': '#fbfcfa', 'editorCursor.foreground': '#12804a' },
})

loader.config({ monaco })

export const LANGUAGE: Record<string, string> = {
  'index.html': 'html',
  'style.css': 'css',
  'script.js': 'javascript',
  'main.py': 'python',
  'query.sql': 'sql',
  'tests.js': 'javascript',
  'tests.py': 'python',
  'setup.sql': 'sql',
}
