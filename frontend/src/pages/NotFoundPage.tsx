import { ArrowLeft } from 'lucide-react'

import { ButtonLink } from '@/components/ui/Button'
import { CodeField } from '@/components/effects/CodeField'

export function NotFoundPage() {
  return (
    <main className="relative grid min-h-dvh place-items-center overflow-hidden px-4">
      <CodeField density={0.6} />
      <section className="rise-in relative text-center" aria-labelledby="nf-title">
        <p className="font-mono text-sm text-muted">
          <span className="text-accent">$</span> cd {location.pathname}
        </p>
        <p className="mt-1 font-mono text-sm text-danger">bash: нет такой страницы</p>
        <h1 id="nf-title" className="wordmark mt-6 text-[clamp(64px,14vw,140px)] text-text">
          404
        </h1>
        <p className="mx-auto mt-4 max-w-sm text-muted">Ссылка устарела или в адресе опечатка. Начните с главной.</p>
        <ButtonLink to="/" className="mt-8" icon={<ArrowLeft className="size-4" />}>
          На главную
        </ButtonLink>
      </section>
    </main>
  )
}
