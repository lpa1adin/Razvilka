import { useEffect, useState } from 'react'

import { api } from '@/lib/api'

export type WorkerStatus = { name: 'agent' | 'chat' | 'review' | 'collector' | 'runner'; alive: boolean; seen_at: string | null }
export type SystemStatus = { api: 'ok'; workers: WorkerStatus[] }

export const WORKER_LABELS: Record<WorkerStatus['name'], string> = {
  agent: 'Генерация (Claude)',
  chat: 'Наставник (Claude)',
  review: 'Ревьюер (Claude)',
  collector: 'Сборщик источников',
  runner: 'Исполнитель проверок',
}

/** Статус сервисов, обновляется раз в 15 секунд. null — ещё не загрузили, 'down' — API не отвечает. */
export function useSystemStatus() {
  const [status, setStatus] = useState<SystemStatus | 'down' | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = () =>
      api<SystemStatus>('/api/system/status')
        .then((s) => !cancelled && setStatus(s))
        .catch(() => !cancelled && setStatus('down'))
    load()
    const timer = window.setInterval(load, 15000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  return status
}
