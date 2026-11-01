import { useRef, useState } from 'react'

import { type Frame, useCanvasLoop } from './useCanvasLoop'

// Фрагменты кода, которые плавают в глубине фона (как математические символы в зелёном референсе).
const TOKENS = [
  '{ }', '=>', '</>', 'def', 'SELECT *', 'async', '[ ]', 'git fork', 'import', '&&', '::', 'λ',
  'return', 'JOIN', '#!/bin', 'class', 'npm i', '0x1F', '!==', 'await', 'fn()', '...', 'docker', '200 OK',
]

type Token = { text: string; x: number; y: number; z: number; speed: number; drift: number; phase: number }

type Props = { density?: number; className?: string }

/** Поле плавающих фрагментов кода с параллаксом от курсора. */
export function CodeField({ density = 1, className = '' }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [scene] = useState(() => {
    let tokens: Token[] = []
    let px = 0
    let py = 0

    return {
      setup(width: number, height: number) {
        const count = Math.round(Math.min(46, (width * height) / 26000) * density)
        tokens = Array.from({ length: count }, () => ({
          text: TOKENS[Math.floor(Math.random() * TOKENS.length)],
          x: Math.random() * width,
          y: Math.random() * height,
          z: 0.25 + Math.random() * 0.75, // глубина: дальние меньше, бледнее и медленнее
          speed: 6 + Math.random() * 10,
          drift: Math.random() * 2 - 1,
          phase: Math.random() * Math.PI * 2,
        }))
      },
      draw({ ctx, width, height, dt, pointer, colors }: Frame) {
        const tx = pointer.active ? (pointer.x / width - 0.5) * 2 : 0
        const ty = pointer.active ? (pointer.y / height - 0.5) * 2 : 0
        px += (tx - px) * Math.min(1, dt * 2)
        py += (ty - py) * Math.min(1, dt * 2)

        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        for (const t of tokens) {
          t.y -= t.speed * t.z * dt
          t.phase += dt * 0.4
          if (t.y < -30) {
            t.y = height + 30
            t.x = Math.random() * width
          }
          const x = t.x + Math.sin(t.phase) * 8 * t.drift - px * 24 * t.z
          const y = t.y - py * 16 * t.z
          ctx.globalAlpha = 0.05 + t.z * 0.2
          ctx.fillStyle = t.z > 0.85 ? colors['--accent'] : colors['--code-token']
          ctx.font = `${Math.round(11 + t.z * 11)}px "JetBrains Mono Variable", monospace`
          ctx.fillText(t.text, x, y)
        }
        ctx.globalAlpha = 1
      },
    }
  })

  useCanvasLoop(ref, scene)
  return <canvas ref={ref} aria-hidden="true" className={`pointer-events-none absolute inset-0 h-full w-full ${className}`} />
}
