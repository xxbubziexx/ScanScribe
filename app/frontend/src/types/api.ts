/** Shared API payload types — mirrors FastAPI schemas in app/routes/auth.py */

export interface Token {
  access_token: string
  token_type: string
}

export interface UserResponse {
  id: number
  username: string
  email: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}

export interface ApiError {
  detail: string | { msg: string; type: string }[]
}

/** Narrows an unknown catch value to a readable message. */
export function errorMessage(err: unknown, fallback = 'An unexpected error occurred'): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return fallback
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}
