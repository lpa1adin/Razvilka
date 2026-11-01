import { GitFork } from 'lucide-react'

/** Знак: развилка в рамке + название, сложенное в две строки, как TU/RA в референсе. */
export function Logo({ compact = false, textClassName = '' }: { compact?: boolean; textClassName?: string }) {
  return (
    <span className="flex items-center gap-3">
      <span className="grid size-9 shrink-0 place-items-center rounded-md border border-line-strong bg-surface-2 text-accent">
        <GitFork className="size-[18px]" aria-hidden />
      </span>
      {!compact && (
        <span className={`wordmark text-[13px] leading-[1.05] text-text ${textClassName}`} aria-label="Развилка">
          <span aria-hidden>
            Раз
            <br />
            вилка
          </span>
        </span>
      )}
    </span>
  )
}
