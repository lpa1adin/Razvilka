import { useEffect, type RefObject } from 'react'

import { prefersReducedMotion } from '@/lib/theme'

export type Frame = {
  ctx: CanvasRenderingContext2D
  width: number
  height: number
  /** секунды с прошлого кадра, не больше 0.05 — после паузы сцена не «прыгает» */
  dt: number
  pointer: { x: number; y: number; active: boolean }
  colors: Record<string, string>
}

type Scene = {
  /** вызывается при старте и при каждом изменении размера */
  setup: (width: number, height: number, colors: Record<string, string>) => void
  draw: (frame: Frame) => void
}

const COLOR_VARS = ['--accent', '--ai', '--code-token', '--muted', '--faint']

function readColors() {
  const style = getComputedStyle(document.documentElement)
  return Object.fromEntries(COLOR_VARS.map((name) => [name, style.getPropertyValue(name).trim()]))
}

/**
 * Общий цикл для canvas-эффектов: чёткость на Retina, пауза вне экрана и во фоновой вкладке,
 * один статичный кадр при prefers-reduced-motion, перерисовка при смене темы.
 */
export function useCanvasLoop(ref: RefObject<HTMLCanvasElement | null>, scene: Scene) {
  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return

    const still = prefersReducedMotion()
    const pointer = { x: -9999, y: -9999, active: false }
    let colors = readColors()
    let width = 0
    let height = 0
    let raf = 0
    let last = 0
    let visible = true

    const frame = (time: number) => {
      const dt = Math.min((time - last) / 1000 || 0, 0.05)
      last = time
      ctx.clearRect(0, 0, width, height)
      scene.draw({ ctx, width, height, dt: still ? 0 : dt, pointer, colors })
      if (!still && visible && !document.hidden) raf = requestAnimationFrame(frame)
    }

    const restart = () => {
      cancelAnimationFrame(raf)
      last = performance.now()
      raf = requestAnimationFrame(frame)
    }

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = rect.width
      height = rect.height
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      scene.setup(width, height, colors)
      restart()
    }

    const onMove = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      pointer.x = event.clientX - rect.left
      pointer.y = event.clientY - rect.top
      pointer.active = pointer.x >= 0 && pointer.y >= 0 && pointer.x <= rect.width && pointer.y <= rect.height
    }
    const onLeave = () => {
      pointer.active = false
    }
    const onTheme = () => {
      colors = readColors()
      scene.setup(width, height, colors)
      restart()
    }
    const onVisibility = () => {
      if (!document.hidden && visible) restart()
    }

    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(canvas)
    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
      if (visible) restart()
    })
    io.observe(canvas)
    window.addEventListener('pointermove', onMove, { passive: true })
    document.addEventListener('pointerleave', onLeave)
    window.addEventListener('rz:theme', onTheme)
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      cancelAnimationFrame(raf)
      resizeObserver.disconnect()
      io.disconnect()
      window.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerleave', onLeave)
      window.removeEventListener('rz:theme', onTheme)
      document.removeEventListener('visibilitychange', onVisibility)
    }
    // scene создаётся один раз на компонент (useMemo/useRef у вызывающего)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref])
}
