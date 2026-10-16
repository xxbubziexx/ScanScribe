/**
 * API client methods for Scanner Intelligence chat.
 */
import type {
  ChatThread,
  ChatThreadDetail,
  ChatPromptInput,
  TransmissionLookup,
  ChatStreamEvent,
} from '@/types/chat'
import { ApiError } from '@/types/api'

const BASE = import.meta.env.VITE_API_BASE ?? ''

function getToken(): string | null {
  return localStorage.getItem('access_token')
}

async function authFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join(', ')
    } catch {
      // non-json error
    }
    throw new ApiError(detail, res.status)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const chatApi = {
  async listThreads(): Promise<ChatThread[]> {
    return authFetch<ChatThread[]>('/api/chat/threads')
  },

  async createThread(data: {
    title?: string
    time_scope_preset?: string
    start_time?: string | null
    end_time?: string | null
  }): Promise<ChatThread> {
    return authFetch<ChatThread>('/api/chat/threads', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  },

  async getThread(threadId: number): Promise<ChatThreadDetail> {
    return authFetch<ChatThreadDetail>(`/api/chat/threads/${threadId}`)
  },

  async updateThread(
    threadId: number,
    data: {
      title?: string
      time_scope_preset?: string
      start_time?: string | null
      end_time?: string | null
    },
  ): Promise<ChatThread> {
    return authFetch<ChatThread>(`/api/chat/threads/${threadId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
  },

  async deleteThread(threadId: number): Promise<{ ok: boolean }> {
    return authFetch<{ ok: boolean }>(`/api/chat/threads/${threadId}`, {
      method: 'DELETE',
    })
  },

  async getTransmission(logId: number): Promise<TransmissionLookup> {
    return authFetch<TransmissionLookup>(`/api/chat/transmissions/${logId}`)
  },

  /**
   * Stream natural-language response tokens via Server-Sent Events.
   */
  async streamQuery(
    threadId: number,
    payload: ChatPromptInput,
    callbacks: {
      onEvent: (event: ChatStreamEvent) => void
      onError?: (err: Error) => void
      onDone?: () => void
    },
    signal?: AbortSignal,
  ): Promise<void> {
    const token = getToken()
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const res = await fetch(`${BASE}/api/chat/threads/${threadId}/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal,
    })

    if (!res.ok) {
      let detail = `Error ${res.status}: ${res.statusText}`
      try {
        const body = await res.json()
        if (body.detail) detail = body.detail
      } catch {
        // non-json
      }
      throw new Error(detail)
    }

    if (!res.body) {
      throw new Error('Response body is null')
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed || !trimmed.startsWith('data: ')) continue

          const jsonStr = trimmed.slice(6).trim()
          try {
            const parsed = JSON.parse(jsonStr) as ChatStreamEvent
            callbacks.onEvent(parsed)
          } catch (e) {
            // ignore malformed chunks
          }
        }
      }

      // flush remaining buffer
      if (buffer.trim().startsWith('data: ')) {
        const jsonStr = buffer.trim().slice(6).trim()
        try {
          const parsed = JSON.parse(jsonStr) as ChatStreamEvent
          callbacks.onEvent(parsed)
        } catch {
          // ignore
        }
      }

      callbacks.onDone?.()
    } catch (err) {
      if (signal?.aborted) return
      callbacks.onError?.(err instanceof Error ? err : new Error(String(err)))
    }
  },
}
