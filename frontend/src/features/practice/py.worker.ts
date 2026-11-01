/// <reference lib="webworker" />
/*
  Python в браузере (Pyodide) — в отдельном потоке: бесконечный цикл ученика не повесит страницу,
  поток просто перезапустится по таймауту. Тут же работает SQL — через sqlite3 из стандартной библиотеки.
*/

type PyDict = { set: (key: string, value: unknown) => void; get: (key: string) => (arg: string) => string }
type PyodideApi = { runPython: (code: string, options?: { globals: PyDict }) => unknown; globals: { get: (name: 'dict') => () => PyDict } }

let dispatch: ((payload: string) => string) | null = null

self.onmessage = async (event: MessageEvent<{ id: number; op: 'init' | 'dispatch'; harness?: string; payload?: unknown }>) => {
  const { id, op } = event.data
  try {
    if (op === 'init') {
      // Файлы Pyodide лежат в public/pyodide (scripts/copy-runtime.mjs) — без CDN и без интернета
      const { loadPyodide } = await import(/* @vite-ignore */ `${self.location.origin}/pyodide/pyodide.mjs`)
      const pyodide = (await loadPyodide({ indexURL: `${self.location.origin}/pyodide/` })) as PyodideApi
      // Своё пространство имён: иначе __name__ == "__main__" и харнесс пытается читать stdin, как в runner
      const namespace = pyodide.globals.get('dict')()
      namespace.set('__name__', 'rz_harness')
      pyodide.runPython(event.data.harness ?? '', { globals: namespace })
      dispatch = namespace.get('dispatch_json')
      self.postMessage({ id, ok: true })
      return
    }
    if (!dispatch) throw new Error('Python ещё не загрузился')
    const answer = dispatch(JSON.stringify(event.data.payload))
    self.postMessage({ id, ok: true, result: JSON.parse(answer) })
  } catch (error) {
    self.postMessage({ id, ok: false, error: error instanceof Error ? error.message : String(error) })
  }
}
