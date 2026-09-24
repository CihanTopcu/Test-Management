const TOKEN_KEY = 'tm.token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private window: the session simply does not survive a reload */
  }
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  // FormData has to set its own Content-Type: the header carries the
  // multipart boundary, and overwriting it makes the server reject the body.
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(path, { ...init, headers })
  if (response.status === 401) {
    setToken(null)
    throw new ApiError(401, 'oturum sona erdi')
  }
  if (!response.ok) {
    let detail = `${response.status}`
    try {
      const body = await response.json()
      // FastAPI's validation errors arrive as a list, not a string
      detail = typeof body.detail === 'string'
        ? body.detail
        : JSON.stringify(body.detail ?? detail)
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, String(detail))
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  del: <T = void>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'DELETE',
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),

  /**
   * Multipart upload.
   *
   * The Content-Type header is deliberately left alone: the browser has to
   * write it itself so that it carries the multipart boundary.
   */
  upload: <T>(path: string, file: File, fields: Record<string, string | number | undefined>) => {
    const form = new FormData()
    form.append('file', file)
    for (const [key, value] of Object.entries(fields)) {
      if (value !== undefined && value !== null) form.append(key, String(value))
    }
    return request<T>(path, { method: 'POST', body: form })
  },

  async logout() {
    // clears the cookie that lets <img> tags fetch attachments
    try {
      await fetch('/api/auth/logout', { method: 'POST' })
    } catch {
      /* going offline should not trap someone in a session */
    }
    setToken(null)
  },

  async login(email: string, password: string) {
    const form = new URLSearchParams({ username: email, password })
    const response = await fetch('/api/auth/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form,
    })
    if (!response.ok) throw new ApiError(response.status, 'e-posta veya parola hatalı')
    const data = (await response.json()) as { access_token: string }
    setToken(data.access_token)
    return data.access_token
  },
}
