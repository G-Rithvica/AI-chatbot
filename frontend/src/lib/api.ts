import type { AuthStatus, ChatHistoryResponse, LoginRequest, RegisterRequest, StreamEvent, Thread, ThreadListResponse, User } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: BodyInit | Record<string, unknown> | null
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, headers, ...rest } = options
  const isJsonBody = body !== null && typeof body === 'object' && !(body instanceof FormData) && !(body instanceof URLSearchParams) && !(body instanceof Blob)

  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      ...(isJsonBody ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: isJsonBody ? JSON.stringify(body) : (body ?? undefined),
    ...rest,
  })

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const err = await response.json() as { detail?: string }
      if (err.detail) detail = err.detail
    } catch { /* ignore parse errors */ }
    throw new Error(detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export const apiClient = {
  baseUrl: API_BASE_URL,
  request,
}

async function streamChat(message: string, threadId: string, onToken: (token: string) => void): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, thread_id: threadId }),
  })

  if (!response.ok || !response.body) {
    throw new Error(`Request failed with status ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''

    for (const event of events) {
      if (!event.startsWith('data: ')) {
        continue
      }

      const payload = event.slice(6)
      const parsed = JSON.parse(payload) as StreamEvent
      if (parsed.type === 'token') {
        onToken(parsed.content)
      }
      if (parsed.type === 'error') {
        throw new Error(parsed.message)
      }
    }
  }
}

export const api = {
  getCurrentUser: () => request<AuthStatus>('/api/auth/me'),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  getChatHistory: (threadId: string) => request<ChatHistoryResponse>(`/api/chat/history?thread_id=${encodeURIComponent(threadId)}`),
  streamChat,
  emailLogin: (body: LoginRequest) =>
    request<User>('/api/auth/login', { method: 'POST', body }),
  emailRegister: (body: RegisterRequest) =>
    request<User>('/api/auth/register', { method: 'POST', body }),
  // Thread endpoints
  getThreads: () => request<ThreadListResponse>('/api/threads'),
  createThread: () => request<Thread>('/api/threads', { method: 'POST', body: {} }),
  renameThread: (threadId: string, name: string) =>
    request<Thread>(`/api/threads/${encodeURIComponent(threadId)}`, { method: 'PATCH', body: { name } }),
  deleteThread: (threadId: string) =>
    request<void>(`/api/threads/${encodeURIComponent(threadId)}`, { method: 'DELETE' }),
}
