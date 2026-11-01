import { useEffect, useState } from 'react'

import { prefersReducedMotion } from '@/lib/theme'

/** Строка терминала, которая «печатается». При reduced-motion текст появляется сразу. */
export function TypeLine({ text, speed = 28, className = '' }: { text: string; speed?: number; className?: string }) {
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? text.length : 0))

  useEffect(() => {
    if (prefersReducedMotion()) {
      setShown(text.length)
      return
    }
    setShown(0)
    const timer = window.setInterval(() => {
      setShown((n) => {
        if (n >= text.length) window.clearInterval(timer)
        return Math.min(n + 1, text.length)
      })
    }, speed)
    return () => window.clearInterval(timer)
  }, [text, speed])

  return (
    <span className={className}>
      <span className="sr-only">{text}</span>
      <span aria-hidden className={shown < text.length ? 'caret' : ''}>
        {text.slice(0, shown)}
      </span>
    </span>
  )
}
