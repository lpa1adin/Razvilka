import { loadHarness, type CheckResult, type Files } from './api'
import { buildPage, WIDTHS } from './webPage'

const CHECK_TIMEOUT = 15000

type SandboxMessage = { rz: true; type: 'ready' | 'console' | 'results'; level?: string; text?: string; results?: CheckResult[]; errors?: string[] }

/**
 * Изолированный iframe: /sandbox.html с sandbox="allow-scripts" (без allow-same-origin) —
 * у кода ученика нет доступа ни к cookie, ни к API платформы.
 */
export function mountSandbox(container: HTMLElement, html: string, onMessage: (m: SandboxMessage) => void, style = '') {
  const frame = document.createElement('iframe')
  frame.setAttribute('sandbox', 'allow-scripts allow-modals')
  frame.setAttribute('title', 'Результат: ваша страница')
  frame.src = '/sandbox.html'
  frame.style.cssText = `border:0;width:100%;height:100%;background:#fff;${style}`

  const listener = (event: MessageEvent) => {
    if (event.source !== frame.contentWindow || !event.data?.rz) return
    const message = event.data as SandboxMessage
    if (message.type === 'ready') frame.contentWindow?.postMessage({ rz: 'render', html }, '*')
    else onMessage(message)
  }
  window.addEventListener('message', listener)
  container.appendChild(frame)
  return () => {
    window.removeEventListener('message', listener)
    frame.remove()
  }
}

export async function previewHtml(files: Files) {
  return buildPage(files, '', 1280, 'preview', await loadHarness('web'))
}

/** Проверка на трёх ширинах параллельно: 1280, 768 и 375 — как в runner. */
export async function checkWeb(files: Files, tests: string): Promise<{ results: CheckResult[]; error: string | null }> {
  const harness = await loadHarness('web')
  const runs = WIDTHS.map(
    (width) =>
      new Promise<{ results: CheckResult[]; errors: string[] }>((resolve, reject) => {
        const holder = document.createElement('div')
        // Вне экрана, но с настоящей шириной — чтобы работали @media и размеры элементов
        holder.style.cssText = `position:fixed;left:-20000px;top:0;width:${width}px;height:900px;pointer-events:none;`
        holder.setAttribute('aria-hidden', 'true')
        document.body.appendChild(holder)
        const timer = window.setTimeout(() => {
          cleanup()
          holder.remove()
          reject(new Error(`Проверка на ширине ${width} px не завершилась за ${CHECK_TIMEOUT / 1000} с — возможно, в скрипте бесконечный цикл`))
        }, CHECK_TIMEOUT)
        const cleanup = mountSandbox(holder, buildPage(files, tests, width, 'check', harness), (message) => {
          if (message.type !== 'results') return
          window.clearTimeout(timer)
          cleanup()
          holder.remove()
          resolve({ results: message.results ?? [], errors: message.errors ?? [] })
        })
      }),
  )
  try {
    const outcomes = await Promise.all(runs)
    const errors = [...new Set(outcomes.flatMap((o) => o.errors))]
    return { results: outcomes.flatMap((o) => o.results), error: errors.length ? `Ошибки в скрипте страницы: ${errors.join('; ')}` : null }
  } catch (e) {
    return { results: [], error: e instanceof Error ? e.message : 'Проверка не удалась' }
  }
}
