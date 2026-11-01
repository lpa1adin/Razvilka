import { useRef, useState } from 'react'

import { type Frame, useCanvasLoop } from './useCanvasLoop'

type Particle = { x: number; y: number; vx: number; vy: number; tx: number; ty: number; size: number; ai: boolean }

/** Рисует знак развилки (как git fork) в скрытом canvas и возвращает точки, из которых его собрать. */
function sampleFork(width: number, height: number, step: number) {
  const off = document.createElement('canvas')
  off.width = Math.max(1, Math.floor(width))
  off.height = Math.max(1, Math.floor(height))
  const g = off.getContext('2d')
  if (!g) return []

  const s = Math.min(width, height) / 32 // знак нарисован в сетке 32×32, как favicon
  const ox = (width - 32 * s) / 2
  const oy = (height - 32 * s) / 2
  g.translate(ox, oy)
  g.scale(s, s)
  g.strokeStyle = '#fff'
  g.lineWidth = 2.6
  g.lineCap = 'round'
  for (const [cx, cy] of [[10, 7], [22, 7], [16, 25]]) {
    g.beginPath()
    g.arc(cx, cy, 2.8, 0, Math.PI * 2)
    g.stroke()
  }
  g.beginPath()
  g.moveTo(10, 9.8)
  g.lineTo(10, 12.5)
  g.quadraticCurveTo(10, 15.5, 13, 15.5)
  g.lineTo(19, 15.5)
  g.quadraticCurveTo(22, 15.5, 22, 12.5)
  g.lineTo(22, 9.8)
  g.moveTo(16, 15.5)
  g.lineTo(16, 22.2)
  g.stroke()

  const data = g.getImageData(0, 0, off.width, off.height).data
  const points: [number, number][] = []
  for (let y = 0; y < off.height; y += step) {
    for (let x = 0; x < off.width; x += step) {
      if (data[(y * off.width + x) * 4 + 3] > 128) points.push([x, y])
    }
  }
  return points
}

/** Знак «Развилки» собирается из частиц и разлетается от курсора (референс с ракетой из частиц). */
export function ForkParticles({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [scene] = useState(() => {
    let particles: Particle[] = []

    return {
      setup(width: number, height: number) {
        const step = width < 360 ? 4 : 5
        const targets = sampleFork(width, height, step)
        const previous = particles
        particles = targets.map(([tx, ty], i) => {
          // При смене размера частицы летят со своих мест, при первом запуске — из случайных точек.
          const from = previous[i]
          return {
            x: from?.x ?? Math.random() * width,
            y: from?.y ?? Math.random() * height,
            vx: 0,
            vy: 0,
            tx: tx + (Math.random() - 0.5) * step,
            ty: ty + (Math.random() - 0.5) * step,
            size: 0.8 + Math.random() * 1.4,
            ai: Math.random() < 0.08,
          }
        })
      },
      draw({ ctx, dt, pointer, colors, width }: Frame) {
        const still = dt === 0
        const radius = Math.max(60, width * 0.16)
        for (const p of particles) {
          if (still) {
            p.x = p.tx
            p.y = p.ty
          } else {
            p.vx += (p.tx - p.x) * 9 * dt
            p.vy += (p.ty - p.y) * 9 * dt
            if (pointer.active) {
              const dx = p.x - pointer.x
              const dy = p.y - pointer.y
              const dist = Math.hypot(dx, dy)
              if (dist < radius && dist > 0.1) {
                const force = (1 - dist / radius) * 2600 * dt
                p.vx += (dx / dist) * force
                p.vy += (dy / dist) * force
              }
            }
            p.vx *= 1 - Math.min(1, 5.5 * dt)
            p.vy *= 1 - Math.min(1, 5.5 * dt)
            p.x += p.vx * dt
            p.y += p.vy * dt
          }
          const speed = Math.min(1, Math.hypot(p.vx, p.vy) / 300)
          ctx.globalAlpha = 0.55 + 0.45 * (1 - speed)
          ctx.fillStyle = p.ai ? colors['--ai'] : colors['--accent']
          ctx.fillRect(p.x, p.y, p.size, p.size)
        }
        ctx.globalAlpha = 1
      },
    }
  })

  useCanvasLoop(ref, scene)
  return <canvas ref={ref} aria-hidden="true" className={`block h-full w-full ${className}`} />
}
