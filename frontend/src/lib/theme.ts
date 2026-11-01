export type Theme = 'dark' | 'light'

export function getTheme(): Theme {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'
}

function apply(theme: Theme) {
  if (theme === 'light') document.documentElement.dataset.theme = 'light'
  else delete document.documentElement.dataset.theme
}

/**
 * Смена темы. С координатами клика новая тема раскрывается кругом от кнопки (View Transitions);
 * где API нет или включено «уменьшить движение» — меняется сразу.
 */
export function setTheme(theme: Theme, origin?: { x: number; y: number }): Promise<void> {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => { ready: Promise<void>; finished: Promise<void> } }
  let done: Promise<void> = Promise.resolve()
  if (origin && doc.startViewTransition && !prefersReducedMotion()) {
    const transition = doc.startViewTransition(() => apply(theme))
    const radius = Math.hypot(Math.max(origin.x, innerWidth - origin.x), Math.max(origin.y, innerHeight - origin.y))
    transition.ready
      .then(() =>
        document.documentElement.animate(
          { clipPath: [`circle(0px at ${origin.x}px ${origin.y}px)`, `circle(${radius}px at ${origin.x}px ${origin.y}px)`] },
          { duration: 550, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', pseudoElement: '::view-transition-new(root)' },
        ),
      )
      .catch(() => undefined)
    done = transition.finished.catch(() => undefined)
  } else {
    apply(theme)
  }
  try {
    localStorage.setItem('rz.theme', theme)
  } catch {
    // приватный режим — тема просто не запомнится
  }
  window.dispatchEvent(new Event('rz:theme'))
  // Резолвится, когда анимация закончилась: на её время страницу перекрывает слой перехода
  return done
}

export function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
