import { api } from '@/lib/api'

export type Role = 'user' | 'admin'

export type User = {
  id: number
  login: string
  display_name: string
  role: Role
}

export const authApi = {
  session: () => api<{ user: User | null }>('/api/auth/session'),
  login: (login: string, password: string) =>
    api<User>('/api/auth/login', { method: 'POST', body: JSON.stringify({ login, password }) }),
  logout: () => api<void>('/api/auth/logout', { method: 'POST' }),
}
