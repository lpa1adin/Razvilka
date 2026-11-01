import { X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'

type Props = { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }

/** Модальное окно на нативном <dialog>: фокус, Esc и затемнение даёт браузер. */
export function Dialog({ open, onClose, title, children, footer, wide }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
      // Иначе браузер ставит фокус на крестик в шапке; нужен первый смысловой элемент
      const target = dialog.querySelector<HTMLElement>('[data-autofocus]') ?? dialog.querySelector<HTMLElement>('input:not([type=radio]), textarea, select')
      target?.focus()
    }
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className={`panel m-auto max-h-[88dvh] w-[calc(100%-32px)] overflow-hidden p-0 text-text backdrop:bg-black/60 backdrop:backdrop-blur-sm ${wide ? 'max-w-3xl' : 'max-w-lg'}`}
      aria-labelledby="dialog-title"
    >
      <div className="flex max-h-[88dvh] flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-4">
          <h2 id="dialog-title" className="font-semibold">
            {title}
          </h2>
          <button type="button" onClick={onClose} className="grid size-9 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-text" aria-label="Закрыть">
            <X className="size-4" />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-3 border-t border-line px-5 py-4">{footer}</footer>}
      </div>
    </dialog>
  )
}
