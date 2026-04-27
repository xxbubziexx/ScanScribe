import { request } from './api'
import { ApiError } from '../types/api'
import type {
  EventDetailResponse,
  EventsListResponse,
  MonitorCreate,
  MonitorResponse,
  MonitorUpdate,
  NerLabelsResponse,
  PipelineDebugEntry,
} from '../types/events'

const BASE = import.meta.env.VITE_API_BASE ?? ''

function getToken(): string | null {
  return localStorage.getItem('access_token')
}

const jsonHeaders = { 'Content-Type': 'application/json' }

export const eventsApi = {
  monitors: () => request<MonitorResponse[]>('/api/events/monitors'),

  nerLabels: () => request<NerLabelsResponse>('/api/events/ner-labels'),

  createMonitor: (body: MonitorCreate) =>
    request<MonitorResponse>('/api/events/monitors', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),

  updateMonitor: (monitorId: number, body: MonitorUpdate) =>
    request<MonitorResponse>(`/api/events/monitors/${monitorId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),

  deleteMonitor: (monitorId: number) =>
    request<{ ok: boolean }>(`/api/events/monitors/${monitorId}`, {
      method: 'DELETE',
    }),

  debugRecent: (limit = 80) =>
    request<PipelineDebugEntry[]>(`/api/events/debug?limit=${encodeURIComponent(String(limit))}`),

  clearDebug: () =>
    request<{ ok: boolean; removed: number }>('/api/events/debug', {
      method: 'DELETE',
    }),

  list: (args: { monitorId?: number; status?: string; limit?: number; offset?: number }) => {
    const sp = new URLSearchParams()
    if (typeof args.monitorId === 'number') sp.set('monitor_id', String(args.monitorId))
    if (args.status) sp.set('status', args.status)
    sp.set('limit', String(args.limit ?? 200))
    sp.set('offset', String(args.offset ?? 0))
    return request<EventsListResponse>(`/api/events/events?${sp.toString()}`)
  },

  detail: (eventId: string) =>
    request<EventDetailResponse>(`/api/events/events/${encodeURIComponent(eventId)}`),

  close: (eventId: string) =>
    request<{ ok: boolean; status: string }>(`/api/events/events/${encodeURIComponent(eventId)}/close`, {
      method: 'POST',
    }),

  remove: (eventId: string) =>
    request<{ ok: boolean }>(`/api/events/events/${encodeURIComponent(eventId)}`, {
      method: 'DELETE',
    }),
}

export async function downloadEventsExportHeaders(args: {
  monitorId?: number
  status?: string
  limit?: number
}): Promise<void> {
  const sp = new URLSearchParams()
  if (typeof args.monitorId === 'number') sp.set('monitor_id', String(args.monitorId))
  if (args.status) sp.set('status', args.status)
  sp.set('limit', String(args.limit ?? 10000))
  const token = getToken()
  const res = await fetch(`${BASE}/api/events/events/export-headers?${sp.toString()}`, {
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
      // ignore parse errors
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
  a.download = `scanscribe_events_headers_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
