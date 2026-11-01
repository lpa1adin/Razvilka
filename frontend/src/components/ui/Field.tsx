import { useId, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react'

export const inputClass =
  'w-full rounded-md border border-line-strong bg-bg/60 px-3 text-[15px] text-text outline-none transition-colors ' +
  'placeholder:text-faint focus:border-accent focus-visible:outline-none aria-[invalid=true]:border-danger'

type Common = { label: string; hint?: ReactNode; error?: string | null }

export function TextField({ label, hint, error, className = '', ...rest }: Common & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  return (
    <div className={className}>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <input id={id} className={`${inputClass} mt-2 h-10`} aria-invalid={!!error} aria-describedby={`${id}-hint`} {...rest} />
      <FieldNote id={`${id}-hint`} hint={hint} error={error} />
    </div>
  )
}

export function TextArea({ label, hint, error, className = '', ...rest }: Common & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId()
  return (
    <div className={className}>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <textarea id={id} className={`${inputClass} mt-2 min-h-20 py-2 leading-relaxed`} aria-invalid={!!error} aria-describedby={`${id}-hint`} {...rest} />
      <FieldNote id={`${id}-hint`} hint={hint} error={error} />
    </div>
  )
}

function FieldNote({ id, hint, error }: { id: string; hint?: ReactNode; error?: string | null }) {
  if (error) {
    return (
      <p id={id} className="mt-1.5 text-sm text-danger">
        {error}
      </p>
    )
  }
  return hint ? (
    <p id={id} className="mt-1.5 text-xs text-faint">
      {hint}
    </p>
  ) : null
}
