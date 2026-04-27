/**
 * Typed API client — single fetch wrapper with Bearer auth and 401 handling.
 * All feature code should import from here rather than calling fetch directly.
 */
import { ApiError } from '@/types/api'
import type { Token, UserResponse } from '@/types/api'

const BASE = import.meta.env.VITE_API_BASE ?? ''

function getToken(): string | null {
  return localStorage.getItem('access_token')
}

interface RequestOptions extends RequestInit {
  auth?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { auth = true, headers: extraHeaders, ...rest } = options

  const headers: Record<string, string> = {
    ...(extraHeaders as Record<string, string>),
  }

  if (auth) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${BASE}${path}`, { headers, ...rest })

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join(', ')
    } catch {
      // non-JSON error body; use status text
    }

    if (res.status === 401) {
      // Token expired or invalid — clear storage; callers / AuthContext handle redirect
      localStorage.removeItem('access_token')
      localStorage.removeItem('username')
    }

    throw new ApiError(detail, res.status)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const auth = {
  /**
   * POST /api/auth/login — OAuth2PasswordRequestForm (form-encoded, not JSON).
   */
  login(username: string, password: string): Promise<Token> {
    const body = new URLSearchParams({ username, password })
    return request<Token>('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
      auth: false,
    })
  },

  /**
   * POST /api/auth/register — JSON body.
   */
  register(username: string, email: string, password: string): Promise<UserResponse> {
    return request<UserResponse>('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password }),
      auth: false,
    })
  },

  /**
   * GET /api/auth/me — returns current user from token.
   */
  me(): Promise<UserResponse> {
    return request<UserResponse>('/api/auth/me')
  },
}

// ─── Re-export generic requester for feature modules ──────────────────────────
export { request }
