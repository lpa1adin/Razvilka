import { ArrowLeft, Lock } from 'lucide-react'

import { ButtonLink } from '@/components/ui/Button'

export function ForbiddenPage() {
  return (
    <section className="rise-in panel mx-auto mt-10 max-w-xl p-8" aria-labelledby="forbidden-title">
      <span className="grid size-11 place-items-center rounded-md bg-ai-soft text-ai">
        <Lock className="size-5" aria-hidden />
      </span>
      <p className="eyebrow mt-6">403 · Нет доступа</p>
      <h1 id="forbidden-title" className="mt-2 text-2xl font-semibold tracking-tight">
        Этот раздел — для администратора
      </h1>
      <p className="mt-3 text-muted">
        В Мастерской создают и редактируют курсы и задания. Если нужна новая тема, попросите администратора добавить её.
      </p>
      <ButtonLink to="/" variant="secondary" className="mt-6" icon={<ArrowLeft className="size-4" />}>
        Вернуться к учёбе
      </ButtonLink>
    </section>
  )
}
