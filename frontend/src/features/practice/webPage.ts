/*
  Сборка страницы веб-задания. Та же логика есть в runner
  (backend/app/modules/practice/webpage.py) — менять оба места вместе.
*/
import type { Files } from './api'

export const WIDTHS = [1280, 768, 375] as const

const OWN_CSS = /<link\b[^>]*href=["']\.?\/?style\.css["'][^>]*>/gi
const OWN_JS = /<script\b[^>]*src=["']\.?\/?script\.js["'][^>]*>\s*<\/script>/gi

const inline = (code: string, tag: string) => code.replace(new RegExp(`</${tag}`, 'gi'), `<\\/${tag}`)

export function buildPage(files: Files, tests: string, width: number, mode: 'preview' | 'check', harness: string) {
  let html = (files['index.html'] ?? '').replace(OWN_CSS, '').replace(OWN_JS, '')
  const head =
    `<style>${inline(files['style.css'] ?? '', 'style')}</style>` +
    `<script>window.__rzMode=${JSON.stringify(mode)};window.__rzWidth=${Math.round(width)};\n${harness}\n` +
    `${mode === 'check' ? inline(tests, 'script') : ''}</script>`
  const tail = `<script>${inline(files['script.js'] ?? '', 'script')}</script>`

  const headAt = html.search(/<\/head>/i)
  html = headAt >= 0 ? html.slice(0, headAt) + head + html.slice(headAt) : head + html
  const bodyAt = html.toLowerCase().lastIndexOf('</body>')
  return bodyAt >= 0 ? html.slice(0, bodyAt) + tail + html.slice(bodyAt) : html + tail
}
