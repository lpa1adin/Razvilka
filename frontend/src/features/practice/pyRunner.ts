import { loadHarness } from './api'

const RUN_TIMEOUT = 15000
const LOAD_TIMEOUT = 90000

type Pending = { resolve: (v: unknown) => void; reject: (e: Error) => void; timer: number }

/** Один поток с Python на вкладку; при зависании кода ученика поток пересоздаётся. */
class PyRunner {
  private worker: Worker | null = null
  private ready: Promise<void> | null = null
  private pending = new Map<number, Pending>()
  private nextId = 1

  private start() {
    this.worker = new Worker(new URL('./py.worker.ts', import.meta.url), { type: 'module' })
    this.worker.onmessage = (event: MessageEvent<{ id: number; ok: boolean; result?: unknown; error?: string }>) => {
      const task = this.pending.get(event.data.id)
      if (!task) return
      window.clearTimeout(task.timer)
      this.pending.delete(event.data.id)
      if (event.data.ok) task.resolve(event.data.result)
      else task.reject(new Error(event.data.error))
    }
    this.ready = loadHarness('python').then((harness) =>
      this.send('init', { harness }, LOAD_TIMEOUT, 'Python не загрузился за 90 с. Обновите страницу.').then(() => undefined),
    )
    this.ready.catch(() => this.restart())
  }

  private send(op: 'init' | 'dispatch', data: Record<string, unknown>, timeout: number, timeoutMessage: string) {
    const id = this.nextId++
    return new Promise<unknown>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        this.pending.delete(id)
        this.restart()
        reject(new Error(timeoutMessage))
      }, timeout)
      this.pending.set(id, { resolve, reject, timer })
      this.worker!.postMessage({ id, op, ...data })
    })
  }

  private restart() {
    this.worker?.terminate()
    this.worker = null
    this.ready = null
    for (const task of this.pending.values()) {
      window.clearTimeout(task.timer)
      task.reject(new Error('Выполнение остановлено'))
    }
    this.pending.clear()
  }

  /** Загружает Python заранее, пока человек читает условие. */
  warmUp() {
    if (!this.worker) this.start()
    return this.ready!
  }

  async dispatch<T>(payload: Record<string, unknown>): Promise<T> {
    await this.warmUp()
    return (await this.send('dispatch', { payload }, RUN_TIMEOUT, `Код выполнялся дольше ${RUN_TIMEOUT / 1000} с — возможно, бесконечный цикл. Выполнение остановлено.`)) as T
  }
}

export const pyRunner = new PyRunner()
