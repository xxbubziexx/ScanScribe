import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { downloadEventsExportHeaders, eventsApi } from '../../lib/events'
import { errorMessage } from '../../types/api'
import { useToast } from '../../context/ToastContext'
import type {
  EventDetailResponse,
  EventListItem,
  EventTranscript,
  MonitorResponse,
} from '../../types/events'

type PipelineEvent = {
  id: number
  eventId: string
  monitorId: number
  monitorName: string
  status: 'open' | 'closed'
  eventType: string | null
  broadcastType: string | null
  location: string | null
  units: string | null
  statusDetail: string | null
  talkgroup: string
  originalTranscription: string | null
  summary: string | null
  closeRecommendation: boolean | null
  createdAt: string
  incidentAt: string | null
  closedAt: string | null
  spansAttached: number
}

type DetailTab = 'event-thread' | 'transcription' | 'raw'

function typeDisplayFor(event: Pick<PipelineEvent, 'eventType' | 'broadcastType'>): string {
  const bt = (event.broadcastType || '').trim()
  if (bt) return `BROADCAST:${bt}`
  const t = (event.eventType || '').trim()
  if (t.toUpperCase() === 'BROADCAST' && !bt) return 'BROADCAST'
  return t || '—'
}

function formatTime(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

function formatTimeLong(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function formatTimeOnly(iso: string | null | undefined) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

function splitBadgeEntries(value: string | null | undefined): string[] {
  if (!value) return []
  return value
    .split(',')
    .map((v) => v.trim())
    .filter((v) => v.length > 0)
}

function EventListCard({
  event,
  active,
  onSelect,
}: {
  event: PipelineEvent
  active: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      className={active ? 'ss-events-row ss-events-row--active' : 'ss-events-row'}
      onClick={onSelect}
    >
      <div className="ss-events-row-head">
        <span
          className={
            event.status === 'open'
              ? 'ss-events-status ss-events-status--open'
              : 'ss-events-status ss-events-status--closed'
          }
        >
          {event.status}
        </span>
        <span className="ss-events-eyebrow">
          {event.monitorName} · {event.spansAttached} span{event.spansAttached === 1 ? '' : 's'}
        </span>
        <span className="ss-events-time">{formatTime(event.incidentAt ?? event.createdAt)}</span>
      </div>
      <p className="ss-events-row-title">{typeDisplayFor(event)}</p>
      <p className="ss-events-row-meta">
        {splitBadgeEntries(event.talkgroup).map((tg) => (
          <span key={`${event.eventId}-tg-${tg}`} className="ss-events-chip-tg">
            {tg}
          </span>
        ))}
        {event.statusDetail ? <span className="text-gray-500">· {event.statusDetail}</span> : null}
      </p>
      {splitBadgeEntries(event.location).length > 0 ? (
        <div className="ss-events-row-locations">
          {splitBadgeEntries(event.location).map((loc) => (
            <span key={`${event.eventId}-loc-${loc}`} className="ss-events-chip-loc">
              {loc}
            </span>
          ))}
        </div>
      ) : null}
      {splitBadgeEntries(event.units).length > 0 ? (
        <div className="ss-events-row-units">
          {splitBadgeEntries(event.units).map((unit) => (
            <span key={`${event.eventId}-unit-${unit}`} className="ss-events-chip-loc">
              {unit}
            </span>
          ))}
        </div>
      ) : null}
      <p className="ss-events-type">{event.summary || event.originalTranscription || '—'}</p>
    </button>
  )
}

function toPipelineEvent(item: EventListItem): PipelineEvent {
  return {
    id: item.id,
    eventId: item.event_id,
    monitorId: item.monitor_id,
    monitorName: '',
    status: item.status === 'closed' ? 'closed' : 'open',
    eventType: item.event_type,
    broadcastType: item.broadcast_type,
    location: item.location,
    units: item.units,
    statusDetail: item.status_detail,
    talkgroup: item.talkgroup || '',
    originalTranscription: item.original_transcription,
    summary: item.summary,
    closeRecommendation: item.close_recommendation,
    createdAt: item.created_at || '',
    incidentAt: item.incident_at,
    closedAt: item.closed_at,
    spansAttached: item.spans_attached ?? 0,
  }
}

function toDetailEvent(detail: EventDetailResponse, listEvent: PipelineEvent | null): PipelineEvent {
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
    units: e.units,
    statusDetail: e.status_detail,
    talkgroup: listEvent?.talkgroup || '',
    originalTranscription: e.original_transcription,
    summary: e.summary,
    closeRecommendation: e.close_recommendation,
    createdAt: e.created_at || '',
    incidentAt: e.incident_at,
    closedAt: e.closed_at,
    spansAttached: detail.transcripts.length || listEvent?.spansAttached || 0,
  }
}

function nerEntityChips(entities: EventTranscript['entities']): string[] {
  if (!entities || typeof entities !== 'object') return []
  return Object.entries(entities).flatMap(([label, vals]) => {
    if (!Array.isArray(vals)) return []
    return vals
      .filter((v): v is string => typeof v === 'string' && v.trim().length > 0)
      .map((v) => `${label}:${v}`)
  })
}

export function EventsIncidentsPage() {
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [query, setQuery] = useState('')
  const [monitor, setMonitor] = useState<number | 'all'>('all')
  const [status, setStatus] = useState<'all' | 'open' | 'closed'>('all')
  const [cardCount, setCardCount] = useState<number>(50)
  const [activeTab, setActiveTab] = useState<DetailTab>('event-thread')
  const [selectedId, setSelectedId] = useState<string>('')

  const monitorsQuery = useQuery({
    queryKey: ['events-monitors'],
    queryFn: () => eventsApi.monitors(),
    staleTime: 60_000,
  })

  const listQuery = useQuery({
    queryKey: ['events-list', monitor, status, cardCount],
    queryFn: () =>
      eventsApi.list({
        monitorId: monitor === 'all' ? undefined : monitor,
        status: status === 'all' ? undefined : status,
        limit: cardCount,
        offset: 0,
      }),
    refetchInterval: 10_000,
    refetchIntervalInBackground: true,
  })

  const events = useMemo(() => {
    const items = listQuery.data?.items ?? []
    const byMonitor = new Map<number, string>((monitorsQuery.data ?? []).map((m) => [m.id, m.name]))
    return items.map((item) => {
      const e = toPipelineEvent(item)
      return { ...e, monitorName: byMonitor.get(e.monitorId) || `Monitor ${e.monitorId}` }
    })
  }, [listQuery.data?.items, monitorsQuery.data])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q.length) return events
    return events.filter((event) => {
      const hay = [
        event.eventId,
        typeDisplayFor(event),
        event.summary ?? '',
        event.location ?? '',
        event.units ?? '',
        event.talkgroup,
        event.statusDetail ?? '',
        event.eventType ?? '',
        event.originalTranscription ?? '',
        event.monitorName,
        String(event.spansAttached),
      ]
        .join('\n')
        .toLowerCase()
      return hay.includes(q)
    })
  }, [events, query])

  useEffect(() => {
    if (filtered.length === 0) {
      setSelectedId('')
      return
    }
    if (!selectedId || !filtered.some((e) => e.eventId === selectedId)) {
      setSelectedId(filtered[0].eventId)
    }
  }, [filtered, selectedId])

  const selectedListEvent = useMemo(() => filtered.find((e) => e.eventId === selectedId) ?? null, [filtered, selectedId])

  const detailQuery = useQuery({
    queryKey: ['events-detail', selectedId],
    queryFn: () => eventsApi.detail(selectedId),
    enabled: !!selectedId,
    refetchInterval: 10_000,
    refetchIntervalInBackground: true,
  })

  const selected = useMemo(() => {
    if (!selectedListEvent) return null
    if (!detailQuery.data) return selectedListEvent
    return toDetailEvent(detailQuery.data, selectedListEvent)
  }, [selectedListEvent, detailQuery.data])
  const openInView = useMemo(
    () => filtered.reduce((n, e) => n + (e.status === 'open' ? 1 : 0), 0),
    [filtered],
  )
  const downloadCsv = async () => {
    await downloadEventsExportHeaders({
      monitorId: monitor === 'all' ? undefined : monitor,
      status: status === 'all' ? undefined : status,
    })
  }

  const spanLinks = useMemo(() => detailQuery.data?.transcripts ?? [], [detailQuery.data?.transcripts])

  const closeMutation = useMutation({
    mutationFn: (eventId: string) => eventsApi.close(eventId),
    onSuccess: () => {
      addToast('Event closed', 'success')
      void queryClient.invalidateQueries({ queryKey: ['events-list'] })
      void queryClient.invalidateQueries({ queryKey: ['events-detail', selectedId] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Failed to close event'), 'error'),
  })

  const deleteMutation = useMutation({
    mutationFn: (eventId: string) => eventsApi.remove(eventId),
    onSuccess: () => {
      addToast('Event deleted', 'success')
      setSelectedId('')
      void queryClient.invalidateQueries({ queryKey: ['events-list'] })
    },
    onError: (e: unknown) => addToast(errorMessage(e, 'Failed to delete event'), 'error'),
  })

  return (
    <div className="ss-events-page">
      <div className="ss-events-topbar">
        <h1 className="ss-events-title">Incidents &amp; broadcasts</h1>
        <div className="ss-events-live">
          <span className="ss-events-rate">{listQuery.isFetching ? 'Refreshing…' : 'Live'}</span>
          <span className="ss-events-pill-tiny">{openInView} open in view</span>
          <button
            type="button"
            className="ss-btn-ghost"
            onClick={() => {
              void listQuery.refetch()
              if (selectedId) void detailQuery.refetch()
            }}
          >
            Refresh
          </button>
          <button type="button" className="ss-btn-ghost" onClick={() => void downloadCsv()}>
            Download CSV
          </button>
        </div>
      </div>
      <p className="ss-events-sub">
        Monitored radio / scanner pipeline: monitors (departments), span-linked transcripts, and event headers from the
        events service — not application error logs.
      </p>

      <div className="ss-events-filters">
        <input
          type="search"
          className="ss-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search id, type, talkgroup, location, units, summary…"
        />
        <select
          className="ss-select"
          value={monitor === 'all' ? 'all' : String(monitor)}
          onChange={(e) => {
            const v = e.target.value
            setMonitor(v === 'all' ? 'all' : Number(v))
          }}
        >
          <option value="all">All monitors (departments)</option>
          {(monitorsQuery.data ?? []).map((m: MonitorResponse) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
        <select
          className="ss-select"
          value={status}
          onChange={(e) => setStatus(e.target.value as 'all' | 'open' | 'closed')}
        >
          <option value="all">All statuses</option>
          <option value="open">Open</option>
          <option value="closed">Closed</option>
        </select>
        <button
          type="button"
          className="ss-btn-ghost"
          onClick={() => {
            setQuery('')
            setStatus('all')
            setMonitor('all')
          }}
        >
          Clear
        </button>
      </div>

      <div className="ss-events-shell">
        <section className="ss-events-list-pane" aria-label="Event list">
          <div className="ss-events-pane-head">
            <span>{filtered.length} shown</span>
            <div className="ss-events-pane-head-controls">
              <label className="ss-events-pane-head-label" htmlFor="events-card-count">
                Cards
              </label>
              <select
                id="events-card-count"
                className="ss-select h-8 min-w-[5rem] text-xs"
                value={String(cardCount)}
                onChange={(e) => setCardCount(Number(e.target.value))}
              >
                {[20, 50, 100, 200].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <span className="text-gray-500">Newest (created) first</span>
            </div>
          </div>
          {listQuery.isError && (
            <p className="ss-form-error px-4 py-2">{errorMessage(listQuery.error, 'Failed to load events')}</p>
          )}
          {filtered.length === 0 ? (
            <p className="ss-empty not-italic">No events match current filters.</p>
          ) : (
            <ul className="ss-events-list">
              {filtered.map((event) => {
                const active = selectedId === event.eventId
                return (
                  <li
                    key={event.eventId}
                    className={active ? 'ss-events-row-item ss-events-row-item--active' : 'ss-events-row-item'}
                  >
                    <EventListCard event={event} active={active} onSelect={() => setSelectedId(event.eventId)} />
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <section className="ss-events-detail-pane" aria-label="Event detail">
          <div className="ss-events-pane-head">
            <span>Incident / broadcast</span>
            <span className="font-mono text-xs text-gray-500">{selected?.eventId ?? '—'}</span>
          </div>

          <div className="ss-events-tabs">
            <div className="ss-events-tabs-left" role="tablist">
              {(
                [
                  { id: 'event-thread' as const, label: 'Event Thread' },
                  { id: 'transcription' as const, label: 'Transcription' },
                  { id: 'raw' as const, label: 'Raw' },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === tab.id}
                  className={activeTab === tab.id ? 'ss-events-tab ss-events-tab--active' : 'ss-events-tab'}
                  onClick={() => setActiveTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            {selected ? (
              <div className="ss-events-tabs-actions">
                <button
                  type="button"
                  className="ss-btn-ghost"
                  disabled={selected.status === 'closed' || closeMutation.isPending}
                  onClick={() => closeMutation.mutate(selected.eventId)}
                >
                  Close
                </button>
                <button
                  type="button"
                  className="ss-btn-danger-soft"
                  disabled={deleteMutation.isPending}
                  onClick={() => {
                    if (!window.confirm(`Delete ${selected.eventId}?`)) return
                    deleteMutation.mutate(selected.eventId)
                  }}
                >
                  Delete
                </button>
              </div>
            ) : null}
          </div>

          {!selected ? (
            <p className="ss-empty not-italic">Select an event on the left.</p>
          ) : activeTab === 'event-thread' ? (
            <div className="ss-events-thread-wrap">
              <h3 className="ss-events-section-title">HEADER</h3>
              <div className="ss-events-detail-grid-badge">
                <div className="ss-events-detail-grid">
                <div className="ss-events-kv">
                  <span className="ss-events-k">Event ID</span>
                  <p className="ss-events-kv-value font-mono text-sm text-gray-200">{selected.eventId}</p>
                </div>
                <div className="ss-events-kv">
                  <span className="ss-events-k">Type (display)</span>
                  <p className="ss-events-kv-value text-sm text-gray-200">{typeDisplayFor(selected)}</p>
                </div>
                <div className="ss-events-kv">
                  <span className="ss-events-k">Status</span>
                  <div className="ss-events-kv-value">
                    <p className="capitalize text-gray-200">{selected.status}</p>
                    {selected.statusDetail ? <p className="ss-events-low-badge mt-1">{selected.statusDetail}</p> : null}
                  </div>
                </div>
                <div className="ss-events-kv">
                  <span className="ss-events-k">Close recommendation</span>
                  <p className="ss-events-kv-value text-sm text-gray-200">
                    {selected.closeRecommendation == null
                      ? '—'
                      : selected.closeRecommendation
                        ? 'Yes (pipeline hint)'
                        : 'No'}
                  </p>
                </div>
                <div className="ss-events-kv">
                  <span className="ss-events-k">Monitor (department)</span>
                  <p className="ss-events-kv-value text-sm text-gray-200">
                    {selected.monitorName}{' '}
                    <span className="text-gray-500">(id {selected.monitorId})</span>
                  </p>
                </div>
                <div className="ss-events-kv">
                  <span className="ss-events-k">Time window</span>
                  <p className="ss-events-kv-value text-xs text-gray-300">
                    <span className="block">Incident: {formatTimeOnly(selected.incidentAt)}</span>
                    <span className="block">Created: {formatTimeOnly(selected.createdAt)}</span>
                    <span className="block">Closed: {formatTimeOnly(selected.closedAt)}</span>
                  </p>
                </div>
                <div className="ss-events-kv">
                  <span className="ss-events-k">Location</span>
                  {splitBadgeEntries(selected.location).length > 0 ? (
                    <div className="ss-events-kv-value ss-events-kv-badge-list">
                      {splitBadgeEntries(selected.location).map((loc) => (
                        <span key={`detail-loc-${loc}`} className="ss-events-kv-badge">
                          {loc}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="ss-events-kv-value text-sm text-gray-200">—</p>
                  )}
                </div>
                <div className="ss-events-kv">
                  <span className="ss-events-k">Units</span>
                  {splitBadgeEntries(selected.units).length > 0 ? (
                    <div className="ss-events-kv-value ss-events-kv-badge-list">
                      {splitBadgeEntries(selected.units).map((unit) => (
                        <span key={`detail-unit-${unit}`} className="ss-events-kv-badge">
                          {unit}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="ss-events-kv-value text-sm text-gray-200">—</p>
                  )}
                </div>
                <div className="ss-events-kv">
                  <span className="ss-events-k">Talkgroups (aggregated)</span>
                  {splitBadgeEntries(selected.talkgroup).length > 0 ? (
                    <div className="ss-events-kv-value ss-events-kv-badge-list">
                      {splitBadgeEntries(selected.talkgroup).map((tg) => (
                        <span key={`detail-tg-${tg}`} className="ss-events-kv-badge">
                          {tg}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="ss-events-kv-value text-sm text-gray-200">—</p>
                  )}
                </div>
                <div className="ss-events-kv">
                  <span className="ss-events-k">Transcript spans</span>
                  <p className="ss-events-kv-value text-sm text-gray-200">{selected.spansAttached}</p>
                </div>
                <div className="ss-events-detail-span ss-events-kv">
                  <span className="ss-events-k">Narrative summary</span>
                  <p className="ss-events-kv-value text-sm text-gray-200">{selected.summary || '—'}</p>
                </div>
                </div>
              </div>

              <h3 className="ss-events-section-title">SPAN LINKS</h3>
              <div className="ss-events-spans-list-wrap">
                {detailQuery.isFetching && !detailQuery.data ? (
                  <p className="ss-empty not-italic">Loading span links…</p>
                ) : spanLinks.length === 0 ? (
                  <p className="ss-events-placeholder">No span links attached.</p>
                ) : (
                  <ul className="ss-events-spans-list">
                    {spanLinks.map((span, idx) => (
                      <li key={span.log_entry_id ?? `${selected?.eventId}-span-${idx + 1}`} className="ss-events-span-item">
                        <div className="ss-events-span-item-head">
                          <p className="ss-events-k mb-0">Span #{idx + 1}</p>
                          <p className="text-sm text-gray-300">{formatTimeLong(span.timestamp)}</p>
                        </div>
                        <p className="ss-events-talkgroup-badge mt-1">{span.talkgroup || 'N/A'}</p>

                        <div className="ss-events-span-section ss-events-span-section--attach mt-2">
                          <div className="ss-events-kv">
                            <p className="ss-events-k mb-0.5">Attach reason</p>
                            <p className="ss-events-kv-value text-sm text-indigo-200/90">
                              {span.llm_reason || (span.is_trigger ? 'Trigger span matched event header extraction' : 'Linked context span')}
                            </p>
                          </div>
                        </div>

                        <div className="ss-events-span-section mt-2">
                          <div className="ss-events-kv">
                            <p className="ss-events-k mb-0.5">NER extractions</p>
                            <div className="ss-events-kv-value ss-events-ner-list">
                              {nerEntityChips(span.entities).length === 0 ? (
                                <span className="text-xs text-gray-500">None</span>
                              ) : (
                                nerEntityChips(span.entities).map((entity) => (
                                  <span key={entity} className="ss-events-ner-chip">
                                    {entity}
                                  </span>
                                ))
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="ss-events-span-section ss-events-span-section--transcript mt-2">
                          <div className="ss-events-kv">
                            <p className="ss-events-k mb-0.5">Transcript</p>
                            <p className="ss-events-kv-value text-sm text-gray-300">{span.transcript || '—'}</p>
                          </div>
                        </div>

                        {span.has_playback && span.audio_path ? (
                          <div className="mt-2">
                            <p className="ss-events-k mb-0.5">Audio</p>
                            <audio className="ss-events-span-audio" controls preload="none" src={`/${span.audio_path}`}>
                              Your browser does not support audio playback.
                            </audio>
                          </div>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : activeTab === 'transcription' ? (
            <div className="ss-events-txt-block">
              <p className="ss-events-hint">Trigger / header text stored on the event (first span is highlighted in API responses).</p>
              <p className="ss-events-body">{selected.originalTranscription || '—'}</p>
            </div>
          ) : (
            <pre className="ss-events-pre">{JSON.stringify(selected, null, 2)}</pre>
          )}
        </section>
      </div>
    </div>
  )
}
