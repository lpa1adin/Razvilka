import { ArrowUp, Bot, Lightbulb, MessageSquarePlus, Sparkles, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'

import { Button } from '@/components/ui/Button'
import { inputClass } from '@/components/ui/Field'
import { ApiError } from '@/lib/api'

import { mentorApi, streamAnswer, type MentorContext, type MentorMessage } from './api'
import { useMentor } from './MentorProvider'
import { MentorText } from './MentorText'

const GENERAL: MentorContext = { kind: 'general', ref: '', label: 'Общий вопрос' }

const STARTERS: Record<MentorContext['kind'], string[]> = {
  task: ['С чего начать это задание?', 'Почему не проходит проверка?', 'Что прочитать по теме задания?'],
  lesson: ['Зачем этот урок и что из него вынести?', 'С какой статьи начать?', 'Объясни на простом примере'],
  general: ['Что изучать дальше?', 'Как устроена платформа?'],
}

/** Кнопка вызова наставника — на всех экранах, кроме задания на компьютере (там она в верхней полосе). */
export function MentorLauncher({ hiddenOnDesktop }: { hiddenOnDesktop?: boolean }) {
  const { open, setOpen } = useMentor()
  if (open) return null
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className={`group fixed bottom-5 right-5 z-40 inline-flex h-12 items-center gap-2 rounded-full border border-ai/40 bg-surface px-4 text-sm font-medium text-ai shadow-[0_10px_40px_-12px_var(--ai)] transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[0_14px_44px_-10px_var(--ai)] ${hiddenOnDesktop ? 'xl:hidden' : ''}`}
      aria-label="Открыть наставника"
    >
      <Sparkles className="size-4 transition-transform duration-300 group-hover:rotate-12" aria-hidden />
      <span className="max-sm:sr-only">Наставник</span>
    </button>
  )
}

export function MentorPanel() {
  const { open, setOpen, context: pageContext } = useMentor()
  const context = pageContext ?? GENERAL
  const [messages, setMessages] = useState<MentorMessage[]>([])
  const [status, setStatus] = useState<{ available: boolean; reason: string | null } | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [proposing, setProposing] = useState(false)
  const stop = useRef<(() => void) | null>(null)
  const list = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)

  const busy = messages.some((m) => m.role === 'assistant' && (m.status === 'pending' || m.status === 'streaming'))

  const follow = useCallback((id: number) => {
    stop.current?.()
    stop.current = streamAnswer(id, (event) => {
      setMessages((list) =>
        list.map((m) =>
          m.id !== id
            ? m
            : event.status
              ? { ...m, status: event.status, error: event.error ?? null, content: event.content ?? m.content }
              : { ...m, status: 'streaming', content: m.content + (event.delta ?? '') },
        ),
      )
    })
  }, [])

  // Переписка своя у каждого урока и задания
  useEffect(() => {
    if (!open) return
    let cancelled = false
    setError(null)
    setProposing(false)
    mentorApi.status().then((s) => !cancelled && setStatus(s), () => !cancelled && setStatus({ available: false, reason: 'API не отвечает' }))
    mentorApi.thread(context.kind, context.ref).then(
      ({ messages }) => {
        if (cancelled) return
        setMessages(messages)
        const live = messages.find((m) => m.role === 'assistant' && (m.status === 'pending' || m.status === 'streaming'))
        if (live) follow(live.id)
      },
      (e) => !cancelled && setError(e instanceof ApiError ? e.message : 'Не удалось загрузить переписку'),
    )
    return () => {
      cancelled = true
      stop.current?.()
    }
  }, [open, context.kind, context.ref, follow])

  useEffect(() => {
    if (!open) return
    input.current?.focus()
    const onKey = (e: globalThis.KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, setOpen])

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const send = async (value: string, hint = false) => {
    if (busy || (!value.trim() && !hint)) return
    setError(null)
    try {
      const { answer_id } = await mentorApi.send({
        context_kind: context.kind,
        context_ref: context.ref,
        text: value.trim(),
        hint,
        files: context.getFiles?.(),
      })
      setText('')
      setMessages((list) => [
        ...list,
        { id: -answer_id, role: 'user', content: value.trim() || 'Дай подсказку', status: 'done', hint, error: null },
        { id: answer_id, role: 'assistant', content: '', status: 'pending', hint: false, error: null },
      ])
      follow(answer_id)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Не удалось отправить вопрос')
    }
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    send(text)
  }
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      send(text)
    }
  }

  const clear = async () => {
    stop.current?.()
    await mentorApi.clear(context.kind, context.ref).catch(() => undefined)
    setMessages([])
  }

  const offline = status !== null && !status.available

  return (
    <>
      {open && <div className="fixed inset-0 z-[54] bg-black/40 sm:hidden" onClick={() => setOpen(false)} aria-hidden />}
      <aside
        aria-label="Наставник"
        aria-hidden={!open}
        inert={!open}
        className={`fixed inset-y-0 right-0 z-[55] flex w-full flex-col border-l border-line bg-surface transition-[translate,box-shadow] duration-500 ease-[var(--ease)] sm:w-[420px] ${
          // Тень только у открытой панели: у закрытой она выглядывала бы из-за края экрана
          open ? 'translate-x-0 shadow-[-24px_0_60px_-20px_rgb(0_0_0/0.6)]' : 'translate-x-full shadow-none'
        }`}
      >
        <header className="flex shrink-0 items-center gap-3 border-b border-line px-4 py-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-ai-soft text-ai">
            <Bot className="size-[18px]" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-semibold">Наставник</p>
            <p className="truncate text-xs text-muted" title={context.label}>
              {context.label}
            </p>
          </div>
          {messages.length > 0 && (
            <button type="button" onClick={clear} disabled={busy} className="grid size-9 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-text disabled:opacity-40" aria-label="Очистить переписку" title="Очистить переписку">
              <Trash2 className="size-4" />
            </button>
          )}
          <button type="button" onClick={() => setOpen(false)} className="grid size-9 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-text" aria-label="Закрыть наставника">
            <X className="size-5" />
          </button>
        </header>

        <div ref={list} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-4" aria-live="polite">
          {offline && (
            <p role="status" className="rounded-lg border border-ai/30 bg-ai-soft p-3 text-sm text-ai">
              {status.reason} Уроки, тесты и песочница работают и без наставника.
            </p>
          )}
          {messages.length === 0 && !offline && (
            <div className="flex flex-col gap-3 py-4">
              <p className="text-sm text-muted">
                Спросите про {context.kind === 'task' ? 'задание' : context.kind === 'lesson' ? 'урок' : 'учёбу'}: наставник объяснит и подскажет, где почитать. Готовое решение он не даёт.
              </p>
              <div className="flex flex-wrap gap-2">
                {STARTERS[context.kind].map((s) => (
                  <button key={s} type="button" onClick={() => send(s)} className="rounded-full border border-line px-3 py-1.5 text-left text-sm text-muted transition-colors hover:border-ai/50 hover:text-text">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => (
            <Message key={m.id} message={m} />
          ))}
        </div>

        <footer className="shrink-0 border-t border-line p-3">
          {error && (
            <p role="alert" className="mb-2 text-sm text-danger">
              {error}
            </p>
          )}
          {proposing ? (
            <Proposal onDone={() => setProposing(false)} />
          ) : (
            <>
              <form onSubmit={onSubmit} className="flex items-end gap-2">
                <label className="sr-only" htmlFor="mentor-input">
                  Вопрос наставнику
                </label>
                <textarea
                  id="mentor-input"
                  ref={input}
                  rows={2}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={onKeyDown}
                  disabled={offline}
                  placeholder={offline ? 'Наставник недоступен' : 'Вопрос… (Enter — отправить, Shift+Enter — новая строка)'}
                  className={`${inputClass} max-h-40 min-h-[52px] resize-none py-2.5 leading-snug`}
                />
                <Button type="submit" disabled={offline || busy || !text.trim()} aria-label="Отправить" className="size-[52px] shrink-0 rounded-lg px-0">
                  <ArrowUp className="size-5" aria-hidden />
                </Button>
              </form>
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                {context.kind === 'task' && (
                  <button
                    type="button"
                    onClick={() => send('', true)}
                    disabled={offline || busy}
                    className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-ai hover:bg-ai-soft disabled:opacity-40"
                    title="Подсказки идут по нарастающей и отмечаются в попытке"
                  >
                    <Lightbulb className="size-4" aria-hidden /> Подсказка
                  </button>
                )}
                <button type="button" onClick={() => setProposing(true)} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted hover:bg-surface-2 hover:text-text">
                  <MessageSquarePlus className="size-4" aria-hidden /> Предложить тему
                </button>
              </div>
            </>
          )}
        </footer>
      </aside>
    </>
  )
}

function Message({ message }: { message: MentorMessage }) {
  if (message.role === 'user') {
    return (
      <div className="ml-8 self-end rounded-2xl rounded-br-md bg-surface-2 px-3.5 py-2.5 text-[15px]">
        {message.hint && (
          <span className="mb-1 flex items-center gap-1 text-xs text-ai">
            <Lightbulb className="size-3" aria-hidden /> подсказка
          </span>
        )}
        <p className="whitespace-pre-wrap">{message.content}</p>
      </div>
    )
  }
  const waiting = message.status === 'pending' || (message.status === 'streaming' && !message.content)
  return (
    <div className="mr-4 flex flex-col gap-1.5">
      {waiting ? (
        <p className="flex items-center gap-2 text-sm text-muted" role="status">
          <span className="flex gap-1" aria-hidden>
            {[0, 1, 2].map((i) => (
              <span key={i} className="size-1.5 animate-pulse rounded-full bg-ai" style={{ animationDelay: `${i * 160}ms` }} />
            ))}
          </span>
          Наставник думает…
        </p>
      ) : (
        message.content && <MentorText text={message.content} />
      )}
      {message.status === 'failed' && (
        <p role="alert" className="text-sm text-danger">
          {message.error ?? 'Наставник не ответил.'}
        </p>
      )}
    </div>
  )
}

function Proposal({ onDone }: { onDone: () => void }) {
  const [topic, setTopic] = useState('')
  const [notes, setNotes] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent'>('idle')
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setState('sending')
    setError(null)
    try {
      await mentorApi.propose(topic, notes)
      setState('sent')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось отправить')
      setState('idle')
    }
  }

  if (state === 'sent') {
    return (
      <div className="flex flex-col gap-2 text-sm">
        <p role="status" className="text-accent">
          Заявка отправлена администратору. Когда курс будет готов и опубликован, он появится в «Курсах».
        </p>
        <Button variant="ghost" onClick={onDone} className="w-fit">
          Вернуться к чату
        </Button>
      </div>
    )
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <p className="text-sm text-muted">Курсы создаёт администратор. Опишите тему — заявка попадёт к нему в Мастерскую.</p>
      <input className={`${inputClass} h-10`} placeholder="Тема, например «CSS Grid»" value={topic} onChange={(e) => setTopic(e.target.value)} aria-label="Тема" data-autofocus />
      <textarea className={`${inputClass} min-h-16 py-2`} placeholder="Что хочется уметь после курса (необязательно)" value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Пожелания" />
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" loading={state === 'sending'} disabled={topic.trim().length < 3}>
          Отправить заявку
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Отмена
        </Button>
      </div>
    </form>
  )
}
