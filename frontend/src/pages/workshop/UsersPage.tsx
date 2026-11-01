import { KeyRound, UserPlus } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { TextField } from '@/components/ui/Field'
import { Badge, ErrorBlock, PageHeader, Skeleton } from '@/components/ui/States'
import type { Role } from '@/features/auth/api'
import { useAuth } from '@/features/auth/AuthProvider'
import { formatDate } from '@/features/library/FragmentView'
import { usersApi, type UserRow } from '@/features/workshop/api'
import { useApi } from '@/lib/useApi'

export function UsersPage() {
  const { user: me } = useAuth()
  const { data, error, loading, reload } = useApi(() => usersApi.list(), [])
  const [adding, setAdding] = useState(false)
  const [resetFor, setResetFor] = useState<UserRow | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  return (
    <div className="rise-in flex flex-col gap-8">
      <PageHeader
        ai
        eyebrow="Мастерская"
        title="Пользователи"
        text="Регистрации нет — учётки создаёт администратор. Пароль сообщите человеку лично."
        actions={
          <Button onClick={() => setAdding(true)} icon={<UserPlus className="size-4" />}>
            Добавить пользователя
          </Button>
        }
      />
      {notice && (
        <p role="status" className="text-sm text-accent">
          {notice}
        </p>
      )}
      {error ? (
        <ErrorBlock message={error.message} onRetry={reload} />
      ) : loading || !data ? (
        <Skeleton lines={3} />
      ) : (
        <ul className="panel divide-y divide-line">
          {data.map((u) => (
            <li key={u.id} className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-4">
              <div className="min-w-[180px] flex-1">
                <p className="font-medium">
                  {u.display_name} {u.id === me?.id && <span className="text-sm text-faint">(вы)</span>}
                </p>
                <p className="font-mono text-sm text-muted">{u.login}</p>
              </div>
              <Badge tone={u.role === 'admin' ? 'ai' : 'muted'}>{u.role === 'admin' ? 'администратор' : 'пользователь'}</Badge>
              <span className="text-sm text-faint">с {formatDate(u.created_at)}</span>
              <Button variant="ghost" onClick={() => setResetFor(u)} icon={<KeyRound className="size-4" />}>
                Сменить пароль
              </Button>
            </li>
          ))}
        </ul>
      )}

      <AddUserDialog
        open={adding}
        onClose={() => setAdding(false)}
        onDone={(u) => {
          setAdding(false)
          setNotice(`Учётка ${u.login} создана.`)
          reload()
        }}
      />
      <ResetPasswordDialog
        user={resetFor}
        onClose={() => setResetFor(null)}
        onDone={(u) => {
          setResetFor(null)
          setNotice(`Пароль для ${u.login} изменён. Все его сессии завершены — нужно войти заново.`)
        }}
      />
    </div>
  )
}

function AddUserDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: (u: UserRow) => void }) {
  const [form, setForm] = useState({ login: '', display_name: '', role: 'user' as Role, password: '' })
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!/^[A-Za-z0-9._-]{3,64}$/.test(form.login)) return setError('Логин: от 3 символов, латиница, цифры, точка, дефис или подчёркивание')
    if (!form.display_name.trim()) return setError('Введите имя — его увидит человек в интерфейсе')
    if (form.password.length < 8) return setError('Пароль — не короче 8 символов')
    setSending(true)
    try {
      onDone(await usersApi.create(form))
      setForm({ login: '', display_name: '', role: 'user', password: '' })
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось создать учётку')
    } finally {
      setSending(false)
    }
  }

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => (setForm((f) => ({ ...f, [key]: e.target.value })), setError(null))

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Новый пользователь"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" form="add-user" loading={sending} loadingText="Создаём…">
            Создать учётку
          </Button>
        </>
      }
    >
      <form id="add-user" onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <TextField label="Логин" value={form.login} onChange={set('login')} autoComplete="off" autoCapitalize="none" hint="Латиница, цифры, точка, дефис." />
        <TextField label="Имя" value={form.display_name} onChange={set('display_name')} placeholder="Анна" />
        <fieldset>
          <legend className="text-sm font-medium">Роль</legend>
          <div className="mt-2 flex gap-4">
            {(['user', 'admin'] as const).map((role) => (
              <label key={role} className="flex items-center gap-2 text-sm">
                <input type="radio" name="role" checked={form.role === role} onChange={() => setForm((f) => ({ ...f, role }))} className="accent-[var(--accent)]" />
                {role === 'user' ? 'Пользователь — учится' : 'Администратор — ведёт Мастерскую'}
              </label>
            ))}
          </div>
        </fieldset>
        <TextField label="Пароль" type="text" value={form.password} onChange={set('password')} autoComplete="new-password" hint="Не короче 8 символов. Передайте его человеку лично." />
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  )
}

function ResetPasswordDialog({ user, onClose, onDone }: { user: UserRow | null; onClose: () => void; onDone: (u: UserRow) => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!user) return
    if (password.length < 8) return setError('Пароль — не короче 8 символов')
    setSending(true)
    try {
      await usersApi.resetPassword(user.id, password)
      setPassword('')
      onDone(user)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сменить пароль')
    } finally {
      setSending(false)
    }
  }

  return (
    <Dialog
      open={user !== null}
      onClose={onClose}
      title={`Новый пароль для ${user?.login ?? ''}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" form="reset-password" loading={sending} loadingText="Сохраняем…">
            Сменить пароль
          </Button>
        </>
      }
    >
      <form id="reset-password" onSubmit={submit} className="flex flex-col gap-3" noValidate>
        <TextField label="Новый пароль" type="text" value={password} onChange={(e) => (setPassword(e.target.value), setError(null))} error={error} autoComplete="new-password" />
        <p className="text-sm text-muted">Человека выкинет из всех открытых сессий — войти можно будет только с новым паролем.</p>
      </form>
    </Dialog>
  )
}
