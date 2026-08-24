import { request } from '@/lib/api'
import type { UserResponse } from '@/types/api'

export const usersApi = {
  list: () => request<UserResponse[]>('/api/users/list'),

  promote: (userId: number) =>
    request<{ message: string }>(`/api/users/${userId}/promote`, { method: 'POST' }),

  demote: (userId: number) =>
    request<{ message: string }>(`/api/users/${userId}/demote`, { method: 'POST' }),

  toggleActive: (userId: number) =>
    request<{ message: string; is_active: boolean }>(`/api/users/${userId}/toggle-active`, {
      method: 'POST',
    }),

  delete: (userId: number) =>
    request<{ message: string }>(`/api/users/${userId}`, { method: 'DELETE' }),
}
