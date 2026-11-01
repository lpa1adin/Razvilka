import { useCallback, useEffect, useState } from 'react'

import { ApiError } from './api'

type State<T> = { data: T | null; error: ApiError | null; loading: boolean }

/** Загрузка данных для экрана: состояние загрузки, ошибка и «Повторить». */
export function useApi<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setState((s) => ({ ...s, loading: true, error: null }))
    load()
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((error: ApiError) => !cancelled && setState({ data: null, error, loading: false }))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  const setData = useCallback((data: T) => setState({ data, error: null, loading: false }), [])
  return { ...state, reload, setData }
}
