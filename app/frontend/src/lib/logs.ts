import { request } from '@/lib/api'
import { ApiError } from '@/types/api'
import type { LogsListResponse } from '@/types/logs'

const BASE = import.meta.env.VITE_API_BASE ?? ''

function getToken(): string | null {
  return localStorage.getItem('access_token')
}

function buildListParams(args: {
  page: number
  pageSize: number
  search: string
  dateFrom: string
  dateTo: string
  sortBy: string
  is_reviewed?: boolean
}): URLSearchParams {
  const sp = new URLSearchParams()
  sp.set('page', String(args.page))
  sp.set('page_size', String(args.pageSize))
  if (args.search.trim()) sp.set('search', args.search.trim())
  if (args.dateFrom) sp.set('date_from', args.dateFrom)
  if (args.dateTo) sp.set('date_to', args.dateTo)
  if (args.is_reviewed !== undefined) sp.set('is_reviewed', String(args.is_reviewed))
  sp.set('sort_by', args.sortBy)
  return sp
}

export const logsApi = {
  list: (sp: URLSearchParams) => request<LogsListResponse>(`/api/logs?${sp.toString()}`),

  /** Distinct talkgroups from log entries; `today` limits to today's `log_date`. */
  talkgroups: (args?: { today?: boolean }) => {
    const sp = new URLSearchParams()
    if (args?.today) sp.set('today', 'true')
    const q = sp.toString()
    return request<{ talkgroups: string[] }>(`/api/logs/talkgroups${q ? `?${q}` : ''}`)
  },

  activeDates: () => request<{ dates: string[] }>('/api/logs/active-dates'),

  delete: (id: number) =>
    request<{ success: boolean; message: string }>(`/api/logs/${id}`, { method: 'DELETE' }),

  unreview: (id: number) => request(`/api/logs/${id}/unreview`, { method: 'PATCH' }),
  clearReviewed: () =>
    request<{ success: boolean; count: number; message: string }>('/api/logs/reviewed', {
      method: 'DELETE',
    }),
  review: (id: number, corrected_transcript: string) =>
    request<{ success: boolean; log_id: number; is_reviewed: boolean; corrected_transcript: string }>(
      `/api/logs/${id}`,
      { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ corrected_transcript }) }
    ),
}

/** Stream CSV export with current filter params (no pagination). */
export async function downloadLogsExport(args: {
  search: string
  dateFrom: string
  dateTo: string
  is_reviewed?: boolean
}): Promise<void> {
  const sp = new URLSearchParams()
  if (args.search.trim()) sp.set('search', args.search.trim())
  if (args.dateFrom) sp.set('date_from', args.dateFrom)
  if (args.dateTo) sp.set('date_to', args.dateTo)
  if (args.is_reviewed !== undefined) sp.set('is_reviewed', String(args.is_reviewed))
  const token = getToken()
  const res = await fetch(`${BASE}/api/logs/export?${sp.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body: unknown = await res.json()
      if (body && typeof body === 'object' && 'detail' in body) {
        const d = (body as { detail: unknown }).detail
        detail = typeof d === 'string' ? d : String(d)
      }
    } catch {
      // ignore
    }
    if (res.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('username')
    }
    throw new ApiError(detail, res.status)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'scanscribe_logs.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export async function downloadDatasetExport(): Promise<void> {
  const token = getToken()
  const res = await fetch(`${BASE}/api/logs/export-dataset`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body: unknown = await res.json()
      if (body && typeof body === 'object' && 'detail' in body) {
        const d = (body as { detail: unknown }).detail
        detail = typeof d === 'string' ? d : String(d)
      }
    } catch {
      // ignore
    }
    if (res.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('username')
    }
    throw new ApiError(detail, res.status)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `whisper_dataset_${new Date().toISOString().split('T')[0]}.zip`
  a.click()
  URL.revokeObjectURL(url)
}

export { buildListParams }
