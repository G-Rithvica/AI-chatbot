import type {
  Attachment,
  AttachmentListResponse,
  AuthStatus,
  ChatHistoryResponse,
  ImageGenerationRequest,
  ImageGenerationResponse,
  ImageValidationBatchRequest,
  ImageValidationBatchResult,
  ImageValidationRequest,
  ImageValidationResponse,
  LoginRequest,
  RegisterRequest,
  DatabaseConnectRequest,
  DatabaseConnectResponse,
  DatabaseQueryRequest,
  DatabaseQueryResponse,
  SpreadsheetQueryRequest,
  SpreadsheetQueryResponse,
  ResearchDigestQueryRequest,
  ResearchDigestResponse,
  ResearchDigestStreamEvent,
  TicTacToeMoveRequest,
  TicTacToeMoveResponse,
  McpResearchQueryRequest,
  McpResearchResponse,
  McpResearchStreamEvent,
  StreamEvent,
  Thread,
  ThreadListResponse,
  User,
} from '../types'

const runtimeHost = typeof window !== 'undefined' ? window.location.hostname : 'localhost'
const defaultApiHost = runtimeHost === '127.0.0.1' ? '127.0.0.1' : 'localhost'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? `http://${defaultApiHost}:8000`

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

async function streamChat(
  message: string,
  threadId: string,
  attachmentIds: string[] | undefined,
  onToken: (token: string) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, thread_id: threadId, attachment_ids: attachmentIds && attachmentIds.length ? attachmentIds : undefined }),
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

async function streamResearchDigest(
  body: ResearchDigestQueryRequest,
  onEvent: (event: ResearchDigestStreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/project10/research-digest/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
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
      const parsed = JSON.parse(payload) as ResearchDigestStreamEvent
      onEvent(parsed)
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
  streamResearchDigest,
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
  // Attachment endpoints
  getAttachments: (threadId: string) =>
    request<AttachmentListResponse>(`/api/attachments?thread_id=${encodeURIComponent(threadId)}`),
  uploadAttachment: async (threadId: string, file: File): Promise<Attachment> => {
    const formData = new FormData()
    formData.append('file', file)
    return request<Attachment>(`/api/attachments/upload?thread_id=${encodeURIComponent(threadId)}`, {
      method: 'POST',
      body: formData,
    })
  },
  deleteAttachment: (attachmentId: string) =>
    request<void>(`/api/attachments/${encodeURIComponent(attachmentId)}`, { method: 'DELETE' }),
  generateImage: (body: ImageGenerationRequest) =>
    request<ImageGenerationResponse>('/api/image-generation/generate', { method: 'POST', body }),
  validateImage: (body: ImageValidationRequest) =>
    request<ImageValidationResponse>('/api/project8/data-qa/image-validation/validate', { method: 'POST', body }),
  validateImagesBatch: (body: ImageValidationBatchRequest) =>
    request<ImageValidationBatchResult>('/api/project8/data-qa/image-validation/validate-batch', { method: 'POST', body }),
  databaseConnect: (body: DatabaseConnectRequest) =>
    request<DatabaseConnectResponse>('/api/database/connect', { method: 'POST', body }),
  databaseQuery: (body: DatabaseQueryRequest) =>
    request<DatabaseQueryResponse>('/api/database/query', { method: 'POST', body }),
  spreadsheetQuery: (body: SpreadsheetQueryRequest) =>
    request<SpreadsheetQueryResponse>('/api/database/spreadsheet/query', { method: 'POST', body }),
  researchDigestQuery: (body: ResearchDigestQueryRequest) =>
    request<ResearchDigestResponse>('/api/project10/research-digest/query', { method: 'POST', body }),
  ticTacToeAgentMove: (body: TicTacToeMoveRequest) =>
    request<TicTacToeMoveResponse>('/api/project11/tic-tac-toe-agent/move', { method: 'POST', body }),
  mcpResearchQuery: (body: McpResearchQueryRequest) =>
    request<McpResearchResponse>('/api/project12/mcp-research/query', { method: 'POST', body }),
}

export async function streamMcpResearch(
  body: McpResearchQueryRequest,
  onEvent: (event: McpResearchStreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/project12/mcp-research/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok || !response.body) {
    throw new Error(`Request failed with status ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''
    for (const evt of events) {
      if (!evt.startsWith('data: ')) continue
      const parsed = JSON.parse(evt.slice(6)) as McpResearchStreamEvent
      onEvent(parsed)
      if (parsed.type === 'error') throw new Error(parsed.message)
    }
  }
}
