import { Check, Plus } from 'lucide-react'
import { Link } from 'react-router'

import { Dialog } from '@/components/ui/Dialog'
import { Badge, ErrorBlock, Skeleton } from '@/components/ui/States'
import { KIND_LABEL, workshopTasksApi, type AdminTaskBrief } from '@/features/practice/api'
import { useApi } from '@/lib/useApi'

type Props = { open: boolean; onClose: () => void; onPick: (task: AdminTaskBrief) => void; taken: Set<number> }

/** Выбор практического задания для урока. Взять можно только опубликованное. */
export function TaskPicker({ open, onClose, onPick, taken }: Props) {
  const tasks = useApi(() => (open ? workshopTasksApi.list() : Promise.resolve(null)), [open])

  return (
    <Dialog open={open} onClose={onClose} title="Задание для урока" wide>
      {tasks.error ? (
        <ErrorBlock message={tasks.error.message} onRetry={tasks.reload} />
      ) : !tasks.data ? (
        <Skeleton lines={3} />
      ) : tasks.data.length === 0 ? (
        <p className="py-6 text-center text-muted">
          Заданий ещё нет. <Link to="/workshop/content?tab=tasks" className="text-accent underline">Создать задание</Link>
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {tasks.data.map((task) => {
            const published = !!task.published_version && !task.archived
            const already = taken.has(task.id)
            return (
              <li key={task.id}>
                <button
                  type="button"
                  disabled={already || !published}
                  onClick={() => onPick(task)}
                  className="flex w-full items-start gap-3 rounded-lg border border-line p-3 text-left transition-colors hover:border-accent/50 disabled:opacity-50"
                >
                  <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-surface-2 text-muted">
                    {already ? <Check className="size-4" aria-hidden /> : <Plus className="size-4" aria-hidden />}
                  </span>
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{task.title}</span>
                      <Badge>{KIND_LABEL[task.kind]}</Badge>
                    </span>
                    {!published && <span className="mt-1 block text-xs text-faint">Сначала опубликуйте задание — черновик в урок не добавить</span>}
                    {already && <span className="mt-1 block text-xs text-faint">Уже есть в этом уроке</span>}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Dialog>
  )
}
