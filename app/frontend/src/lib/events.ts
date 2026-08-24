import { request } from './api'
import { ApiError } from '../types/api'
import type {
  EntityObservationListResponse,
  EventDetailResponse,
  EventsListResponse,
  MonitorCreate,
  MonitorResponse,
  MonitorUpdate,
  NerLabelsResponse,
  PipelineDebugEntry,
  SpanStoreListResponse,
} from '../types/events'

const BASE = import.meta.env.VITE_API_BASE ?? ''
/** Events pipeline API prefix — always root-absolute so fetch never resolves under /app/events/… */
const EVENTS_API = '/api/events'

function getToken(): string | null {
  return localStorage.getItem('access_token')
}

const jsonHeaders = { 'Content-Type': 'application/json' }

export const eventsApi = {
  monitors: () => request<MonitorResponse[]>(`${EVENTS_API}/monitors`),

  nerLabels: () => request<NerLabelsResponse>(`${EVENTS_API}/ner-labels`),

  createMonitor: (body: MonitorCreate) =>
    request<MonitorResponse>(`${EVENTS_API}/monitors`, {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),

  updateMonitor: (monitorId: number, body: MonitorUpdate) =>
    request<MonitorResponse>(`${EVENTS_API}/monitors/${monitorId}`, {
      method: 'PATCH',
      headers: jsonHeaders,
      body: JSON.stringify(body),
    }),

  deleteMonitor: (monitorId: number) =>
    request<{ ok: boolean }>(`${EVENTS_API}/monitors/${monitorId}`, {
      method: 'DELETE',
    }),

  debugRecent: (limit = 80) =>
    request<PipelineDebugEntry[]>(`${EVENTS_API}/debug?limit=${encodeURIComponent(String(limit))}`),

  clearDebug: () =>
    request<{ ok: boolean; removed: number }>(`${EVENTS_API}/debug`, {
      method: 'DELETE',
    }),

  list: (args: {
    monitorId?: number
    status?: string
    q?: string
    sortBy?: string
    sortOrder?: 'asc' | 'desc'
    limit?: number
    offset?: number
  }) => {
    const sp = new URLSearchParams()
    if (typeof args.monitorId === 'number') sp.set('monitor_id', String(args.monitorId))
    if (args.status) sp.set('status', args.status)
    if (args.q) sp.set('q', args.q)
    if (args.sortBy) sp.set('sort_by', args.sortBy)
    if (args.sortOrder) sp.set('sort_order', args.sortOrder)
    sp.set('limit', String(args.limit ?? 50))
    sp.set('offset', String(args.offset ?? 0))
    return request<EventsListResponse>(`${EVENTS_API}/events?${sp.toString()}`)
  },

  detail: (eventId: string) =>
    request<EventDetailResponse>(`${EVENTS_API}/events/${encodeURIComponent(eventId)}`),

  close: (eventId: string) =>
    request<{ ok: boolean; status: string }>(`${EVENTS_API}/events/${encodeURIComponent(eventId)}/close`, {
      method: 'POST',
    }),

  remove: (eventId: string) =>
    request<{ ok: boolean }>(`${EVENTS_API}/events/${encodeURIComponent(eventId)}`, {
      method: 'DELETE',
    }),

  geocode: (eventId: string) =>
    request<{ ok: boolean; latitude?: number; longitude?: number; resolved_address?: string; message?: string }>(
      `${EVENTS_API}/events/${encodeURIComponent(eventId)}/geocode`,
      { method: 'POST' },
    ),

  spanStore: (args: {
    monitorId?: number
    talkgroup?: string
    logEntryId?: number
    q?: string
    sortBy?: string
    sortOrder?: 'asc' | 'desc'
    limit?: number
    offset?: number
  }) => {
    const sp = new URLSearchParams()
    if (typeof args.monitorId === 'number') sp.set('monitor_id', String(args.monitorId))
    if (args.talkgroup) sp.set('talkgroup', args.talkgroup)
    if (typeof args.logEntryId === 'number') sp.set('log_entry_id', String(args.logEntryId))
    if (args.q) sp.set('q', args.q)
    if (args.sortBy) sp.set('sort_by', args.sortBy)
    if (args.sortOrder) sp.set('sort_order', args.sortOrder)
    sp.set('limit', String(args.limit ?? 50))
    sp.set('offset', String(args.offset ?? 0))
    return request<SpanStoreListResponse>(`${EVENTS_API}/span-store?${sp.toString()}`)
  },

  entities: (args: {
    monitorId?: number
    label?: string
    talkgroup?: string
    logEntryId?: number
    spanStoreId?: number
    q?: string
    sortBy?: string
    sortOrder?: 'asc' | 'desc'
    limit?: number
    offset?: number
  }) => {
    const sp = new URLSearchParams()
    if (typeof args.monitorId === 'number') sp.set('monitor_id', String(args.monitorId))
    if (args.label) sp.set('label', args.label)
    if (args.talkgroup) sp.set('talkgroup', args.talkgroup)
    if (typeof args.logEntryId === 'number') sp.set('log_entry_id', String(args.logEntryId))
    if (typeof args.spanStoreId === 'number') sp.set('span_store_id', String(args.spanStoreId))
    if (args.q) sp.set('q', args.q)
    if (args.sortBy) sp.set('sort_by', args.sortBy)
    if (args.sortOrder) sp.set('sort_order', args.sortOrder)
    sp.set('limit', String(args.limit ?? 50))
    sp.set('offset', String(args.offset ?? 0))
    return request<EntityObservationListResponse>(`${EVENTS_API}/entities?${sp.toString()}`)
  },
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
  const res = await fetch(`${BASE}${EVENTS_API}/events/export-headers?${sp.toString()}`, {
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
