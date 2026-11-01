import { useLayoutEffect, useRef } from 'react'

type Variant = 'underline' | 'pill' | 'chip'

const ACTIVE = [
  '[aria-selected="true"]',
  '[aria-pressed="true"]',
  '[aria-current="page"]',
  '[aria-current="true"]',
  '[data-active="true"]',
]
  .map((s) => `:scope > ${s}`)
  .join(', ')

const LOOK: Record<Variant, string> = {
  // линия под активной вкладкой
  underline: 'h-0.5 rounded-full bg-accent shadow-[0_0_10px_var(--accent-glow)]',
  // подложка сегмента в переключателе
  pill: 'rounded-[6px] bg-surface-2 shadow-[0_1px_0_rgb(255_255_255/0.04)_inset]',
  // фильтр-чип
  chip: 'rounded-full border border-accent/50 bg-accent-soft',
}

/**
 * Подложка, которая плавно переезжает к активному пункту — вкладке, сегменту или чипу.
 * Кладётся первым ребёнком в контейнер с `relative`; активный пункт находится сам по aria-selected,
 * aria-pressed, aria-current или data-active. Пунктам нужен `relative z-[1]`, чтобы быть над подложкой.
 */
export function Glider({ variant = 'pill', className = '' }: { variant?: Variant; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null)

  useLayoutEffect(() => {
    const glider = ref.current
    const box = glider?.parentElement
    if (!glider || !box) return
    let first = true

    const place = () => {
      const active = box.querySelector<HTMLElement>(ACTIVE)
      if (!active) {
        glider.style.opacity = '0'
        return
      }
      const { offsetLeft: x, offsetTop: y, offsetWidth: w, offsetHeight: h } = active
      // При первом показе — сразу на месте, без «выезда» из левого угла
      glider.style.transition = first ? 'none' : ''
      glider.style.opacity = '1'
      glider.style.width = `${w}px`
      if (variant === 'underline') {
        glider.style.transform = `translate(${x}px, ${y + h - 2}px)`
      } else {
        glider.style.height = `${h}px`
        glider.style.transform = `translate(${x}px, ${y}px)`
      }
      first = false
    }

    place()
    const mutations = new MutationObserver(place)
    mutations.observe(box, { subtree: true, attributes: true, attributeFilter: ['aria-selected', 'aria-pressed', 'aria-current', 'data-active'] })
    const sizes = new ResizeObserver(place)
    sizes.observe(box)
    Array.from(box.children).forEach((child) => sizes.observe(child))
    return () => {
      mutations.disconnect()
      sizes.disconnect()
    }
  }, [variant])

  return (
    <span
      ref={ref}
      aria-hidden
      className={`pointer-events-none absolute left-0 top-0 opacity-0 transition-[transform,width,height,opacity] duration-500 ease-[var(--ease)] motion-reduce:transition-none ${LOOK[variant]} ${className}`}
    />
  )
}
