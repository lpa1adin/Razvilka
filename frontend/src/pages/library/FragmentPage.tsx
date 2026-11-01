import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { ErrorBlock, Skeleton } from '@/components/ui/States'
import { libraryApi } from '@/features/library/api'
import { Attribution, FragmentBody } from '@/features/library/FragmentView'
import { useApi } from '@/lib/useApi'

export function FragmentPage() {
  const { id = '' } = useParams()
  const { data, error, loading, reload } = useApi(() => libraryApi.fragment(id), [id])

  return (
    <article className="rise-in mx-auto flex max-w-3xl flex-col gap-6">
      <Link to="/library" className="inline-flex w-fit items-center gap-2 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4" aria-hidden /> Назад к библиотеке
      </Link>
      {error ? (
        <ErrorBlock message={error.message} onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton lines={4} />
      ) : (
        <>
          <header>
            {data.section && <p className="eyebrow">{data.section}</p>}
            <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">{data.title}</h1>
          </header>
          <Attribution fragment={data} source={data.source} />
          <FragmentBody fragment={data} />
        </>
      )}
    </article>
  )
}
