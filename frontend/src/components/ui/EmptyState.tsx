import type { ReactNode } from 'react'

type Props = { icon: ReactNode; title: string; text: string; action?: ReactNode }

export function EmptyState({ icon, title, text, action }: Props) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-line-strong p-5">
      <span className="grid size-9 place-items-center rounded-md bg-surface-2 text-muted">{icon}</span>
      <div>
        <p className="font-semibold text-text">{title}</p>
        <p className="mt-1 text-sm text-muted">{text}</p>
      </div>
      {action}
    </div>
  )
}
