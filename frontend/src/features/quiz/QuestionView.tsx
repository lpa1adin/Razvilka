import { ArrowDown, ArrowUp, Check, X } from 'lucide-react'
import { useId } from 'react'

import { TYPE_LABEL, type AttemptItem, type Option, type Response } from './api'

type Props = {
  item: AttemptItem
  onChange?: (response: Response) => void
  /** разбор после теста: ответы не меняются, видно правильный вариант */
  review?: boolean
}

export function QuestionView({ item, onChange, review }: Props) {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="eyebrow">{TYPE_LABEL[item.type]}</p>
        <div className="prose-content mt-2 text-[17px] font-medium" dangerouslySetInnerHTML={{ __html: item.prompt_html }} />
      </div>
      {item.code && (
        <pre className="overflow-x-auto rounded-lg border border-line bg-bg/70 p-4 font-mono text-[13.5px] leading-relaxed" aria-label="Код к вопросу">
          <code>{item.code}</code>
        </pre>
      )}
      {(item.type === 'single' || item.type === 'multiple') && <Choice item={item} onChange={onChange} review={review} />}
      {item.type === 'order' && <Order item={item} onChange={onChange} review={review} />}
      {item.type === 'match' && <Match item={item} onChange={onChange} review={review} />}
    </div>
  )
}

/** Подпись варианта: в тексте бывают `код` в обратных кавычках — показываем его моноширинным. */
export function Label({ text }: { text: string }) {
  return (
    <span>
      {text.split(/(`[^`]+`)/).map((part, i) =>
        part.startsWith('`') && part.endsWith('`') ? (
          <code key={i} className="rounded border border-line bg-surface-2 px-1 font-mono text-[0.9em]">
            {part.slice(1, -1)}
          </code>
        ) : (
          part
        ),
      )}
    </span>
  )
}

function Choice({ item, onChange, review }: Props) {
  const name = useId()
  const multiple = item.type === 'multiple'
  const selected = new Set(item.response?.selected ?? [])
  const correct = new Set(item.answer?.correct ?? [])

  const toggle = (id: string) => {
    if (!onChange) return
    if (!multiple) return onChange({ selected: [id] })
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChange({ selected: [...next] })
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="sr-only">Варианты ответа</legend>
      {multiple && !review && <p className="text-sm text-muted">Отметьте все верные варианты — засчитывается только полностью верный набор.</p>}
      {(item.options.items ?? []).map((o) => {
        const isOn = selected.has(o.id)
        const state = review ? (correct.has(o.id) ? 'right' : isOn ? 'wrong' : 'idle') : isOn ? 'on' : 'idle'
        const tone = {
          on: 'border-accent bg-accent-soft',
          right: 'border-accent/60 bg-accent-soft',
          wrong: 'border-danger/60 bg-danger-soft',
          idle: 'border-line hover:border-line-strong hover:bg-surface-2/50',
        }[state]
        return (
          <label key={o.id} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3.5 transition-colors ${tone} ${review ? 'cursor-default' : ''}`}>
            <input
              type={multiple ? 'checkbox' : 'radio'}
              name={name}
              checked={isOn}
              disabled={review}
              onChange={() => toggle(o.id)}
              className="mt-1 size-4 shrink-0 accent-[var(--accent)]"
            />
            <span className="flex-1">
              <Label text={o.text} />
            </span>
            {review && state === 'right' && <Check className="mt-0.5 size-4 shrink-0 text-accent" aria-label="Верный вариант" />}
            {review && state === 'wrong' && <X className="mt-0.5 size-4 shrink-0 text-danger" aria-label="Неверно выбран" />}
          </label>
        )
      })}
    </fieldset>
  )
}

function Order({ item, onChange, review }: Props) {
  const all = item.options.items ?? []
  const byId = new Map(all.map((o) => [o.id, o]))
  const current = (item.response?.order ?? all.map((o) => o.id)).map((id) => byId.get(id)).filter(Boolean) as Option[]
  const right = item.answer?.order ?? []

  const move = (index: number, delta: number) => {
    const target = index + delta
    if (!onChange || target < 0 || target >= current.length) return
    const ids = current.map((o) => o.id)
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    onChange({ order: ids })
  }

  return (
    <div className="flex flex-col gap-2">
      {!review && <p className="text-sm text-muted">Переставляйте стрелками. Если порядок уже верный — нажмите «Порядок такой».</p>}
      <ol className="flex flex-col gap-2">
        {current.map((o, i) => {
          const ok = review && right[i] === o.id
          return (
            <li key={o.id} className={`flex items-center gap-3 rounded-lg border p-3 ${review ? (ok ? 'border-accent/60 bg-accent-soft' : 'border-danger/60 bg-danger-soft') : 'border-line'}`}>
              <span className="w-6 font-mono text-sm text-faint">{i + 1}.</span>
              <span className="flex-1">
                <Label text={o.text} />
                {review && !ok && (
                  <span className="mt-1 block text-xs text-muted">
                    Должно быть на месте {right.indexOf(o.id) + 1}
                  </span>
                )}
              </span>
              {!review && (
                <span className="flex">
                  <button type="button" onClick={() => move(i, -1)} disabled={i === 0} className="grid size-8 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-text disabled:opacity-30" aria-label={`Выше: ${o.text}`}>
                    <ArrowUp className="size-4" />
                  </button>
                  <button type="button" onClick={() => move(i, 1)} disabled={i === current.length - 1} className="grid size-8 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-text disabled:opacity-30" aria-label={`Ниже: ${o.text}`}>
                    <ArrowDown className="size-4" />
                  </button>
                </span>
              )}
            </li>
          )
        })}
      </ol>
      {!review && !item.response && (
        <button type="button" onClick={() => onChange?.({ order: current.map((o) => o.id) })} className="w-fit rounded-md px-3 py-1.5 text-sm text-accent hover:bg-accent-soft">
          Порядок такой
        </button>
      )}
    </div>
  )
}

function Match({ item, onChange, review }: Props) {
  const pairs = item.response?.pairs ?? {}
  const right = item.options.right ?? []
  const correct = item.answer?.pairs ?? {}
  const text = (id?: string) => right.find((o) => o.id === id)?.text ?? '—'

  return (
    <div className="flex flex-col gap-2">
      {(item.options.left ?? []).map((l) => {
        const chosen = pairs[l.id]
        const ok = review && chosen === correct[l.id]
        return (
          <div key={l.id} className={`grid items-center gap-2 rounded-lg border p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] ${review ? (ok ? 'border-accent/60 bg-accent-soft' : 'border-danger/60 bg-danger-soft') : 'border-line'}`}>
            <span className="font-medium">
              <Label text={l.text} />
            </span>
            {review ? (
              <span className="text-sm">
                {ok ? (
                  <Label text={text(chosen)} />
                ) : (
                  <>
                    <span className="text-danger line-through">
                      <Label text={text(chosen)} />
                    </span>
                    <span className="block">
                      → <Label text={text(correct[l.id])} />
                    </span>
                  </>
                )}
              </span>
            ) : (
              <select
                aria-label={`Пара для: ${l.text}`}
                value={chosen ?? ''}
                onChange={(e) => onChange?.({ pairs: { ...pairs, [l.id]: e.target.value } })}
                className="h-10 w-full rounded-md border border-line-strong bg-bg/60 px-2 text-[15px] text-text outline-none focus:border-accent"
              >
                <option value="" disabled>
                  Выберите…
                </option>
                {right.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.text.replaceAll('`', '')}
                  </option>
                ))}
              </select>
            )}
          </div>
        )
      })}
    </div>
  )
}
