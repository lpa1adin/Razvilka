import { ArrowLeft } from 'lucide-react'
import { lazy, Suspense } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { ErrorBlock, Skeleton } from '@/components/ui/States'
import { PreviewBanner } from '@/features/courses/PreviewBanner'
import { practiceApi } from '@/features/practice/api'
import { useApi } from '@/lib/useApi'

// Редактор (Monaco) и Python тяжёлые — грузим их только на экранах практики
const Workspace = lazy(() => import('@/features/practice/Workspace').then((m) => ({ default: m.Workspace })))

export function TaskPage() {
  const { slug = '' } = useParams()
  const [params] = useSearchParams()
  const preview = params.get('version') ? Number(params.get('version')) : null
  // «from» — урок, из которого пришли; ведём обратно только на свои страницы
  const from = params.get('from')?.startsWith('/courses/') ? params.get('from') : null
  const { data, error, loading, reload } = useApi(() => practiceApi.get(slug, preview), [slug, preview])

  const back = { backTo: from ?? '/practice', backLabel: from ? 'К уроку' : 'Все задания' }

  if (error || loading || !data) {
    return (
      <div className="flex flex-col gap-4 xl:p-8">
        <Link to={back.backTo} className="inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
          <ArrowLeft className="size-4" aria-hidden /> {back.backLabel}
        </Link>
        {error ? <ErrorBlock message={error.message} onRetry={reload} /> : <Skeleton lines={4} />}
      </div>
    )
  }

  return (
    <Suspense fallback={<Skeleton lines={4} />}>
      <Workspace
        key={`${data.slug}-${data.version}`}
        task={data}
        onChanged={reload}
        {...back}
        banner={data.preview ? <PreviewBanner version={data.version} /> : undefined}
      />
    </Suspense>
  )
}
