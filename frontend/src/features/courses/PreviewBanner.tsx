import { Eye } from 'lucide-react'

export function PreviewBanner({ version }: { version: number }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-ai/40 bg-ai-soft px-4 py-3 text-sm text-ai" role="note">
      <Eye className="size-4 shrink-0" aria-hidden />
      <span className="flex-1">Предпросмотр версии {version}: так курс увидит пользователь. Прогресс здесь не сохраняется.</span>
    </div>
  )
}
