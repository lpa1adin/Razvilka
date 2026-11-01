import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import type { MentorContext } from './api'

type Value = {
  context: MentorContext | null
  open: boolean
  setOpen: (open: boolean) => void
  /** страница сообщает, о чём сейчас речь; при уходе со страницы контекст снимается */
  register: (context: MentorContext | null) => void
}

const Ctx = createContext<Value | null>(null)

export function MentorProvider({ children }: { children: ReactNode }) {
  const [context, setContext] = useState<MentorContext | null>(null)
  const [open, setOpen] = useState(false)
  const value = useMemo(() => ({ context, open, setOpen, register: setContext }), [context, open])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useMentor() {
  const value = useContext(Ctx)
  if (!value) throw new Error('useMentor вне MentorProvider')
  return value
}

/** Подключить наставника к экрану: `useMentorContext({ kind: 'task', ref: slug, label, getFiles })`. */
export function useMentorContext(context: MentorContext | null) {
  const { register } = useMentor()
  // getFiles меняется на каждом рендере — держим последнюю версию в ref, чтобы не перерегистрировать
  const files = useRef(context?.getFiles)
  files.current = context?.getFiles
  const getFiles = useCallback(() => files.current?.() ?? {}, [])
  const key = context ? `${context.kind}:${context.ref}:${context.label}` : ''

  useEffect(() => {
    if (!context) return
    register({ ...context, getFiles: context.getFiles ? getFiles : undefined })
    return () => register(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, register, getFiles])
}
