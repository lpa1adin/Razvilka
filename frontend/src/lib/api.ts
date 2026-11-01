export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** тело ответа сервера — например, список problems при отказе в публикации */
    public body: unknown = null,
  ) {
    super(message)
  }
}

const FALLBACK: Record<number, string> = {
  401: 'Войдите, чтобы продолжить',
  403: 'Раздел доступен только администратору',
  404: 'Не нашли то, что вы искали',
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...init.headers },
    })
  } catch {
    throw new ApiError(0, 'Сервер не отвечает. Проверьте, что платформа запущена (docker compose up).')
  }

  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    // FastAPI отдаёт ошибки проверки данных списком — показываем человеку их тексты
    const detail =
      typeof body?.detail === 'string'
        ? body.detail
        : Array.isArray(body?.detail)
          ? body.detail.map((d: { msg?: string }) => String(d.msg ?? '').replace(/^Value error, /, '')).join('; ')
          : null
    throw new ApiError(response.status, detail ?? FALLBACK[response.status] ?? 'Что-то пошло не так. Попробуйте ещё раз.', body)
  }
  return body as T
}
