import { Hammer } from 'lucide-react'
import { useLocation } from 'react-router'

import { STUDY_NAV, WORKSHOP_NAV } from '@/app/nav'

/** Честная заглушка раздела, который появится на одном из следующих этапов. */
export function SectionPage() {
  const { pathname } = useLocation()
  const item = [...STUDY_NAV, ...WORKSHOP_NAV].find((n) => n.to === pathname)
  if (!item) return null
  const Icon = item.icon

  return (
    <section className="rise-in" aria-labelledby="section-title">
      <p className="eyebrow">{pathname.startsWith('/workshop') ? 'Мастерская' : 'Учёба'}</p>
      <h1 id="section-title" className="mt-2 flex items-center gap-3 text-3xl font-semibold tracking-tight sm:text-4xl">
        <Icon className="size-7 text-muted" aria-hidden />
        {item.label}
      </h1>
      <p className="mt-3 max-w-2xl text-muted">{item.about}</p>

      <div className="panel mt-8 flex max-w-2xl items-start gap-4 p-5">
        <span className="grid size-10 shrink-0 place-items-center rounded-md bg-surface-2 text-muted">
          <Hammer className="size-5" aria-hidden />
        </span>
        <div>
          <p className="font-semibold">Раздел появится на этапе {item.stage}</p>
          <p className="mt-1 text-sm text-muted">
            Сейчас готов каркас: вход, роли, меню и мониторинг. План этапов — в <code className="font-mono text-text">docs/BRIEF.md</code>, §9.
          </p>
        </div>
      </div>
    </section>
  )
}
