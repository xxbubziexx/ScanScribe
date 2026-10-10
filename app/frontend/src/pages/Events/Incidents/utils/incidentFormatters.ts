import type { EventDetailResponse, EventListItem, EventTranscript } from '@/types/events'

export type PipelineEvent = {
  id: number
  eventId: string
  monitorId: number
  monitorName: string
  status: 'open' | 'closed'
  eventType: string | null
  broadcastType: string | null
  location: string | null
  latitude?: number | null
  longitude?: number | null
  resolvedAddress?: string | null
  units: string | null
  statusDetail: string | null
  talkgroup: string
  originalTranscription: string | null
  summary: string | null
  createdAt: string
  updatedAt?: string | null
  incidentAt: string | null
  lastSpanAt?: string | null
  closedAt: string | null
  spansAttached: number
  audioPath?: string | null
  isManuallyPlaced?: boolean
}

export type DetailTab = 'event-thread' | 'transcription' | 'raw'

export function typeDisplayFor(event: Pick<PipelineEvent, 'eventType' | 'broadcastType'>): string {
  const bt = (event.broadcastType || '').trim()
  if (bt) return `BROADCAST:${bt}`
  return (event.eventType || '').trim() || 'Incident'
}

export function formatRelativeTime(
  updatedIso: string | null | undefined,
  createdIso?: string | null | undefined,
): string {
  const targetUpdated = updatedIso || createdIso
  if (!targetUpdated) return '—'

  const dCreated = new Date(createdIso || targetUpdated)
  const dUpdated = new Date(targetUpdated)

  const datePart = !Number.isNaN(dCreated.getTime())
    ? dCreated.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: '2-digit',
        hour: 'numeric',
        minute: '2-digit',
      })
    : (createdIso || targetUpdated)

  const now = new Date()
  const diffMs = !Number.isNaN(dUpdated.getTime()) ? now.getTime() - dUpdated.getTime() : 0

  let rel = 'just now'
  if (diffMs > 0) {
    const diffSec = Math.floor(diffMs / 1000)
    if (diffSec < 60) {
      rel = `${diffSec}s ago`
    } else {
      const diffMin = Math.floor(diffSec / 60)
      if (diffMin < 60) {
        rel = `${diffMin}m ago`
      } else {
        const diffHour = Math.floor(diffMin / 60)
        if (diffHour < 24) {
          rel = `${diffHour}h ago`
        } else {
          rel = 'over 24h ago'
        }
      }
    }
  }

  return `created: ${datePart} • last updated: ${rel}`
}

export function getEventActivityTime(ev: PipelineEvent): number {
  const t = Math.max(
    ev.lastSpanAt ? new Date(ev.lastSpanAt).getTime() : 0,
    ev.updatedAt ? new Date(ev.updatedAt).getTime() : 0,
    ev.incidentAt ? new Date(ev.incidentAt).getTime() : 0,
    ev.createdAt ? new Date(ev.createdAt).getTime() : 0,
  )
  return isNaN(t) || t <= 0 ? (ev.createdAt ? new Date(ev.createdAt).getTime() : 0) : t
}

export function formatTime(
  updatedIso: string | null | undefined,
  createdIso?: string | null | undefined,
) {
  return formatRelativeTime(updatedIso, createdIso)
}

export function formatTimeLong(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

export function formatTimeOnly(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

export function splitBadgeEntries(value: string | null | undefined): string[] {
  if (!value) return []
  return value
    .split(',')
    .map((v) => v.trim())
    .filter((v) => v.length > 0)
}

export function toPipelineEvent(item: EventListItem): PipelineEvent {
  return {
    id: item.id,
    eventId: item.event_id,
    monitorId: item.monitor_id,
    monitorName: '',
    status: item.status === 'closed' ? 'closed' : 'open',
    eventType: item.event_type,
    broadcastType: item.broadcast_type,
    location: item.location,
    latitude: item.latitude,
    longitude: item.longitude,
    resolvedAddress: item.resolved_address,
    units: item.units,
    statusDetail: item.status_detail,
    talkgroup: item.talkgroup || '',
    originalTranscription: item.original_transcription,
    summary: item.summary,
    createdAt: item.created_at || '',
    updatedAt: item.updated_at,
    incidentAt: item.incident_at,
    lastSpanAt: item.last_span_at,
    closedAt: item.closed_at,
    spansAttached: item.spans_attached ?? 0,
    audioPath: item.audio_path,
  }
}

export function toDetailEvent(
  detail: EventDetailResponse,
  listEvent: PipelineEvent | null,
): PipelineEvent {
  const e = detail.event
  return {
    id: listEvent?.id ?? 0,
    eventId: e.event_id,
    monitorId: e.monitor_id,
    monitorName: e.monitor_name || listEvent?.monitorName || '',
    status: e.status === 'closed' ? 'closed' : 'open',
    eventType: e.event_type,
    broadcastType: e.broadcast_type,
    location: e.location,
    latitude: e.latitude,
    longitude: e.longitude,
    resolvedAddress: e.resolved_address,
    units: e.units,
    statusDetail: e.status_detail,
    talkgroup: listEvent?.talkgroup || '',
    originalTranscription: e.original_transcription,
    summary: e.summary,
    createdAt: e.created_at || '',
    updatedAt: e.updated_at,
    incidentAt: e.incident_at,
    lastSpanAt: e.last_span_at,
    closedAt: e.closed_at,
    spansAttached: detail.transcripts.length || listEvent?.spansAttached || 0,
  }
}

export function nerEntityChips(entities: EventTranscript['entities']): string[] {
  if (!entities || typeof entities !== 'object') return []
  return Object.entries(entities).flatMap(([label, vals]) => {
    if (!Array.isArray(vals)) return []
    return vals
      .filter((v): v is string => typeof v === 'string' && v.trim().length > 0)
      .map((v) => `${label}:${v}`)
  })
}

export function formatCountdown(sec: number): string {
  if (sec <= 0) return '00:00:00'
  const hours = Math.floor(sec / 3600)
  const minutes = Math.floor((sec % 3600) / 60)
  const seconds = sec % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  if (hours >= 24) {
    const days = Math.floor(hours / 24)
    const remHours = hours % 24
    return `${days}d ${pad(remHours)}:${pad(minutes)}:${pad(seconds)}`
  }
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
}
