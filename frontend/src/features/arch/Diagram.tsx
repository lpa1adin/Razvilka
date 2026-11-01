import { useMemo, useRef, useState, type PointerEvent } from 'react'

import type { DEdge, DNode, Graph } from './api'

export const NODE_W = 150
export const NODE_H = 46
const GAP_X = 70
const GAP_Y = 26

/** Цвет блока по роли — чтобы схема читалась с первого взгляда, как в документации проектов. */
export const KIND_STYLE: Record<string, { stroke: string; fill: string; label: string }> = {
  app: { stroke: 'var(--accent)', fill: 'var(--accent-soft)', label: 'сервис' },
  db: { stroke: '#60a5fa', fill: 'rgb(96 165 250 / 0.12)', label: 'база' },
  cache: { stroke: '#f472b6', fill: 'rgb(244 114 182 / 0.12)', label: 'кэш' },
  broker: { stroke: 'var(--ai)', fill: 'var(--ai-soft)', label: 'брокер' },
  proxy: { stroke: '#a78bfa', fill: 'rgb(167 139 250 / 0.12)', label: 'прокси / вход' },
  monitoring: { stroke: '#94a3b8', fill: 'rgb(148 163 184 / 0.12)', label: 'мониторинг' },
  class: { stroke: 'var(--accent)', fill: 'var(--accent-soft)', label: 'класс' },
  function: { stroke: 'var(--accent)', fill: 'var(--accent-soft)', label: 'функция' },
  external: { stroke: '#94a3b8', fill: 'rgb(148 163 184 / 0.12)', label: 'из другого модуля' },
  // Карта проекта (пути «напиши заново сам»): файлы по языкам
  html: { stroke: '#f97316', fill: 'rgb(249 115 22 / 0.12)', label: 'HTML' },
  css: { stroke: '#60a5fa', fill: 'rgb(96 165 250 / 0.12)', label: 'CSS' },
  js: { stroke: '#facc15', fill: 'rgb(250 204 21 / 0.12)', label: 'JavaScript' },
  py: { stroke: 'var(--accent)', fill: 'var(--accent-soft)', label: 'Python' },
  md: { stroke: '#94a3b8', fill: 'rgb(148 163 184 / 0.08)', label: 'документация' },
  data: { stroke: '#94a3b8', fill: 'rgb(148 163 184 / 0.08)', label: 'данные' },
}
const style = (kind: string) => KIND_STYLE[kind] ?? KIND_STYLE.app

/** Послойная раскладка: слой = длина самого длинного пути от входа. Циклы не ломают её — обход с меткой. */
export function layout(nodes: DNode[], edges: DEdge[]): Record<string, { x: number; y: number }> {
  const out = new Map<string, string[]>()
  const indeg = new Map<string, number>()
  nodes.forEach((n) => (out.set(n.id, []), indeg.set(n.id, 0)))
  edges.forEach((e) => {
    if (out.has(e.from) && out.has(e.to)) {
      out.get(e.from)!.push(e.to)
      indeg.set(e.to, (indeg.get(e.to) ?? 0) + 1)
    }
  })
  const layer = new Map<string, number>()
  const visit = (id: string, depth: number, seen: Set<string>) => {
    if (seen.has(id) || (layer.get(id) ?? -1) >= depth) return
    layer.set(id, depth)
    seen.add(id)
    out.get(id)!.forEach((t) => visit(t, depth + 1, seen))
    seen.delete(id)
  }
  nodes.filter((n) => !indeg.get(n.id)).forEach((n) => visit(n.id, 0, new Set()))
  nodes.forEach((n) => layer.has(n.id) || visit(n.id, 0, new Set()))
  const columns = new Map<number, string[]>()
  nodes.forEach((n) => {
    const l = layer.get(n.id) ?? 0
    columns.set(l, [...(columns.get(l) ?? []), n.id])
  })
  // Длинный слой (часто — «связей не объявлено») переносим на несколько колонок, иначе схема — одна высокая лента
  const MAX_ROWS = 6
  const split: string[][] = []
  ;[...columns.entries()].sort(([a], [b]) => a - b).forEach(([, ids]) => {
    for (let i = 0; i < ids.length; i += MAX_ROWS) split.push(ids.slice(i, i + MAX_ROWS))
  })
  const pos: Record<string, { x: number; y: number }> = {}
  const tallest = Math.max(...split.map((c) => c.length))
  split.forEach((ids, col) => {
    const offset = ((tallest - ids.length) * (NODE_H + GAP_Y)) / 2
    ids.forEach((id, i) => (pos[id] = { x: 16 + col * (NODE_W + GAP_X), y: 16 + offset + i * (NODE_H + GAP_Y) }))
  })
  return pos
}

type EdgeTone = 'plain' | 'ok' | 'reversed' | 'extra' | 'missed'
const EDGE_COLOR: Record<EdgeTone, string> = {
  plain: 'var(--muted)',
  ok: 'var(--accent)',
  reversed: 'var(--ai)',
  extra: 'var(--danger)',
  missed: 'var(--faint)',
}

type Props = {
  graph: Graph
  /** раскраска связей после проверки */
  tones?: Record<string, EdgeTone>
  positions?: Record<string, { x: number; y: number }>
  onMove?: (id: string, x: number, y: number) => void
  onNodeClick?: (id: string) => void
  onEdgeClick?: (from: string, to: string) => void
  selected?: string | null
  label: string
}

/** SVG-схема: блоки по ролям и стрелки. Режим доски — перетаскивание блоков и клики (DiagramBoard). */
export function Diagram({ graph, tones = {}, positions, onMove, onNodeClick, onEdgeClick, selected, label }: Props) {
  const auto = useMemo(() => layout(graph.nodes, graph.edges), [graph])
  const pos = positions ?? auto
  const svg = useRef<SVGSVGElement>(null)
  const [drag, setDrag] = useState<{ id: string; dx: number; dy: number; moved: boolean } | null>(null)
  const width = Math.max(...graph.nodes.map((n) => (pos[n.id]?.x ?? 0) + NODE_W), 300) + 90
  const height = Math.max(...graph.nodes.map((n) => (pos[n.id]?.y ?? 0) + NODE_H), 120) + 16

  const point = (e: PointerEvent) => {
    const r = svg.current!.getBoundingClientRect()
    return { x: ((e.clientX - r.left) / r.width) * width, y: ((e.clientY - r.top) / r.height) * height }
  }

  const center = (id: string) => ({ x: (pos[id]?.x ?? 0) + NODE_W / 2, y: (pos[id]?.y ?? 0) + NODE_H / 2 })
  // Конец стрелки — на границе блока, а не в центре, иначе наконечник прячется под прямоугольником
  const clip = (from: { x: number; y: number }, to: { x: number; y: number }) => {
    const dx = to.x - from.x
    const dy = to.y - from.y
    const t = Math.min(Math.abs((NODE_W / 2 + 4) / (dx || 1e-6)), Math.abs((NODE_H / 2 + 4) / (dy || 1e-6)), 1)
    return { x: to.x - dx * t, y: to.y - dy * t }
  }

  return (
    <svg ref={svg} viewBox={`0 0 ${width} ${height}`} width={width} className="h-auto max-w-full touch-none select-none" role="img" aria-label={label}
      onPointerMove={(e) => {
        if (!drag || !onMove) return
        const p = point(e)
        onMove(drag.id, Math.max(0, p.x - drag.dx), Math.max(0, p.y - drag.dy))
        if (!drag.moved) setDrag({ ...drag, moved: true })
      }}
      onPointerUp={() => {
        if (drag && !drag.moved) onNodeClick?.(drag.id)
        setDrag(null)
      }}
    >
      <defs>
        {(Object.keys(EDGE_COLOR) as EdgeTone[]).map((t) => (
          <marker key={t} id={`arrow-${t}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill={EDGE_COLOR[t]} />
          </marker>
        ))}
      </defs>
      {graph.edges.map((e) => {
        if (!pos[e.from] || !pos[e.to]) return null
        const key = `${e.from}->${e.to}`
        const tone = tones[key] ?? 'plain'
        const a = center(e.from)
        const target = center(e.to)
        // Блоки в одной колонке через ряд: прямая прошла бы сквозь соседей — рисуем дугу в сторону,
        // чем дальше блоки, тем шире дуга, чтобы дуги не сливались
        const rows = Math.round(Math.abs(target.y - a.y) / (NODE_H + GAP_Y))
        const curved = Math.abs(target.x - a.x) < NODE_W / 2 && rows > 1
        const control = { x: a.x + NODE_W / 2 + 18 * rows, y: (a.y + target.y) / 2 }
        const start = curved ? { x: a.x + NODE_W / 2, y: a.y } : a
        const end = curved ? { x: target.x + NODE_W / 2 + 6, y: target.y } : clip(a, target)
        const d = curved ? `M${start.x},${start.y} Q${control.x},${control.y} ${end.x},${end.y}` : `M${a.x},${a.y} L${end.x},${end.y}`
        return (
          <g key={key} onClick={() => onEdgeClick?.(e.from, e.to)} className={onEdgeClick ? 'cursor-pointer' : ''}>
            <title>{`${e.from} → ${e.to}`}</title>
            <path d={d} fill="none" stroke="transparent" strokeWidth={14} />
            <path d={d} fill="none" stroke={EDGE_COLOR[tone]} strokeWidth={tone === 'plain' ? 1.5 : 2}
              strokeDasharray={tone === 'missed' || tone === 'extra' || e.kind === 'depends_on' ? '5 4' : undefined} markerEnd={`url(#arrow-${tone})`} />
          </g>
        )
      })}
      {graph.nodes.map((n) => {
        const p = pos[n.id]
        if (!p) return null
        const s = style(n.kind)
        return (
          <g key={n.id} transform={`translate(${p.x} ${p.y})`}
            className={onMove || onNodeClick ? 'cursor-pointer' : ''}
            onPointerDown={(e) => {
              if (!onMove && !onNodeClick) return
              ;(e.target as Element).setPointerCapture?.(e.pointerId)
              const q = point(e)
              setDrag({ id: n.id, dx: q.x - p.x, dy: q.y - p.y, moved: false })
            }}
          >
            <title>{n.detail || n.label || n.id}</title>
            <rect width={NODE_W} height={NODE_H} rx={8} fill="var(--surface)" stroke={selected === n.id ? 'var(--text)' : s.stroke} strokeWidth={selected === n.id ? 2.5 : 1.25} />
            <rect width={NODE_W} height={NODE_H} rx={8} fill={s.fill} />
            <text x={NODE_W / 2} y={NODE_H / 2 + 1} textAnchor="middle" dominantBaseline="middle" fontSize={12.5} fontFamily="var(--font-mono)" fill="var(--text)">
              {(n.label ?? n.id).length > 20 ? `${(n.label ?? n.id).slice(0, 19)}…` : n.label ?? n.id}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export function Legend({ kinds }: { kinds: string[] }) {
  return (
    <ul className="flex flex-wrap gap-3 text-xs text-muted">
      {[...new Set(kinds)].map((k) => (
        <li key={k} className="flex items-center gap-1.5">
          <span className="size-3 rounded-sm border" style={{ borderColor: style(k).stroke, background: style(k).fill }} aria-hidden />
          {style(k).label}
        </li>
      ))}
    </ul>
  )
}
